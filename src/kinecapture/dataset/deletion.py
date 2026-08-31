"""Permanent deletion of a project and everything inside it.

This is the one place in the application that destroys user data on purpose,
and the only exception to the immutability rule the rest of the codebase is
built on. It exists because a project holds tens of gigabytes of raw RGB-D
archive and the person who owns the machine has to be able to get that space
back. "Remove from the list", "move to the Recycle Bin" and "leave it in a
hidden trash folder" all fail that test.

Because it is the exception, it is the most defensive code here. The shape of
the operation:

1. **Authorise.** Only the single system owner may delete a project, and the
   check lives in the identity service, not in the button that calls it.
2. **Preflight.** Resolve the path, and refuse unless it is the *exact*
   directory the database has on record, containing a project manifest whose
   ``project_id`` matches the row being deleted. See :func:`inspect_target`.
3. **Detach.** Rename the directory into a tombstone under the dataset root.
   A rename inside one volume is atomic, so after this instant either the
   project is at its old path or it is entirely in the tombstone - never half
   way between.
4. **Commit.** Clear the database rows in one transaction, keeping the audit
   history (see :meth:`ProjectDeletionService._forget_project`).
5. **Erase.** Only now remove the bytes, and report exactly what survived if
   anything does.

Steps 3 and 4 cannot be one transaction - a filesystem and SQLite have no
shared commit - so the tombstone is what makes the seam recoverable. A crash
leaves a marker that says which side finished, and :func:`recover_tombstones`
resolves it deterministically on the next start rather than leaving a folder
nobody can account for.

Nothing here follows a symlink or junction out of the project. A reparse point
inside a project is unlinked, never descended into: a shortcut to somewhere
else on the disk must not turn "delete this project" into "delete that too".
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture.core.errors import StorageError, ValidationError
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.jsonio import read_json_mapping, write_json
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import long_path, path_exists
from kinecapture.dataset.workspace import PROJECT_FILE, PROJECTS_DIRNAME

logger = get_logger(__name__)

#: Where a project waits between being detached and being erased. Inside the
#: dataset root on purpose: the rename has to stay on one volume to be atomic.
TOMBSTONE_DIRNAME = ".deleting"

#: The marker written inside a tombstone. Its presence says a deletion is in
#: progress; ``database_cleared`` says which side of the seam finished.
TOMBSTONE_FILE = "_kinecapture_deleting.json"

#: A directory this shallow is never a project, whatever the database says.
#: Deleting one would take the whole dataset, the user's home or a drive with
#: it, so the guard refuses instead of trusting the row.
_MIN_PATH_PARTS = 3


@dataclass(frozen=True)
class TargetReport:
    """What the preflight found. ``ok`` is the only thing callers may act on."""

    ok: bool
    reason: str = ""
    code: str = ""
    resolved: Optional[Path] = None
    manifest_project_id: str = ""

    def raise_if_bad(self) -> None:
        if not self.ok:
            raise ValidationError(self.reason, code=self.code or "delete_refused")


@dataclass
class DeletionResult:
    """The outcome, in the detail a user needs to trust or to act on it."""

    project_id: str
    project_name: str
    path: Path
    #: Bytes actually reclaimed, or ``None`` when it could not be measured.
    freed_bytes: Optional[int] = None
    database_cleared: bool = False
    files_removed: bool = False
    #: Paths that could not be removed. Non-empty means this was NOT a success.
    remaining: list[str] = field(default_factory=list)
    tombstone: Optional[Path] = None

    @property
    def complete(self) -> bool:
        return self.database_cleared and self.files_removed and not self.remaining

    def summary(self) -> str:
        if self.complete:
            if self.freed_bytes is None:
                return (
                    f"'{self.project_name}' silindi. Boşalan alan ölçülemedi."
                )
            return (
                f"'{self.project_name}' silindi. Yaklaşık "
                f"{self.freed_bytes / 1e9:.2f} GB boşaldı."
            )
        if self.remaining:
            return (
                f"'{self.project_name}' TAMAMEN silinemedi. "
                f"{len(self.remaining)} yol kaldı: {self.remaining[0]}"
            )
        return f"'{self.project_name}' silinemedi."


# ---------------------------------------------------------------- preflight
def inspect_target(
    *,
    recorded_path: Path,
    project_id: str,
    dataset_root: Path,
) -> TargetReport:
    """Decide whether ``recorded_path`` may be recursively deleted.

    Every check is a way this has gone wrong for somebody: a moved project, a
    reused directory, a database row pointing at a parent folder, a junction
    left behind by a backup tool. The function is pure and takes only what the
    *database* said, never anything the user typed, so a caller cannot widen
    the target by passing a different string.
    """
    try:
        resolved = Path(recorded_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return TargetReport(
            False,
            "Proje klasörü bulunamadı; silinecek bir şey yok.",
            "delete_target_missing",
        )

    if not resolved.is_dir():
        return TargetReport(
            False,
            "Kayıtlı yol bir klasör değil.",
            "delete_target_not_a_directory",
            resolved,
        )

    # A reparse point resolves elsewhere; deleting through one would destroy
    # whatever it points at rather than the project.
    if Path(recorded_path).is_symlink() or _is_reparse_point(Path(recorded_path)):
        return TargetReport(
            False,
            "Proje yolu bir sembolik bağlantı/junction; güvenli silinemez.",
            "delete_target_is_link",
            resolved,
        )

    if len(resolved.parts) < _MIN_PATH_PARTS or resolved == Path(resolved.anchor):
        return TargetReport(
            False,
            "Hedef bir sürücü kökü veya ona çok yakın; reddedildi.",
            "delete_target_too_shallow",
            resolved,
        )

    home = Path.home().resolve()
    if resolved in (home, home.parent):
        return TargetReport(
            False,
            "Hedef kullanıcı ana klasörü; reddedildi.",
            "delete_target_is_home",
            resolved,
        )

    try:
        root = Path(dataset_root).expanduser().resolve()
    except (OSError, RuntimeError):
        root = Path(dataset_root).expanduser()
    if resolved in (root, root / PROJECTS_DIRNAME):
        return TargetReport(
            False,
            "Hedef veri kökünün kendisi; tek bir proje değil.",
            "delete_target_is_dataset_root",
            resolved,
        )

    # The repository this application is running from is never a project.
    source_root = Path(__file__).resolve().parents[3]
    if resolved == source_root or source_root.is_relative_to(resolved):
        return TargetReport(
            False,
            "Hedef uygulamanın kaynak klasörünü içeriyor; reddedildi.",
            "delete_target_is_source_root",
            resolved,
        )

    manifest = resolved / PROJECT_FILE
    if not manifest.is_file():
        return TargetReport(
            False,
            f"Klasörde {PROJECT_FILE} yok; bir KineCapture projesi değil.",
            "delete_target_not_a_project",
            resolved,
        )

    try:
        found = str(read_json_mapping(manifest).get("project_id") or "")
    except Exception:  # pragma: no cover - unreadable manifest
        return TargetReport(
            False,
            "Proje dosyası okunamadı; kimlik doğrulanamadan silinmez.",
            "delete_manifest_unreadable",
            resolved,
        )
    if found != project_id:
        return TargetReport(
            False,
            (
                "Klasördeki proje kimliği kayıtla uyuşmuyor "
                f"({found or 'boş'} ≠ {project_id}). Taşınmış veya değişmiş "
                "olabilir; hiçbir şey silinmedi."
            ),
            "delete_identity_mismatch",
            resolved,
            found,
        )

    return TargetReport(True, resolved=resolved, manifest_project_id=found)


def _is_reparse_point(path: Path) -> bool:
    """Windows junctions are not symlinks to ``is_symlink`` but redirect alike."""
    try:
        attributes = os.lstat(long_path(path)).st_file_attributes  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


# ------------------------------------------------------------------- sizing
def measure_tree(root: Path) -> tuple[Optional[int], int]:
    """Total bytes under ``root`` and how many entries could not be read.

    Returns ``(None, n)`` when nothing at all could be measured, so a caller
    can say "could not be measured" instead of showing a confident 0.00 GB.
    This walks a whole project tree and belongs on a worker thread.
    """
    total = 0
    unreadable = 0
    measured = False
    for directory, _dirnames, filenames in os.walk(long_path(root)):
        for name in filenames:
            try:
                total += os.stat(os.path.join(directory, name)).st_size
                measured = True
            except OSError:
                unreadable += 1
    return (total if measured else None), unreadable


# ----------------------------------------------------------------- removal
def _force_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def remove_tree(root: Path) -> list[str]:
    """Delete ``root`` recursively; return the paths that survived.

    Read-only files are made writable and retried, which is the common Windows
    failure: an archive chunk written with the read-only bit refuses to go and
    would otherwise abort the whole delete half way. A file held open by
    another process cannot be forced, and is reported rather than swallowed.

    Links inside the tree are unlinked, never followed - ``os.walk`` with
    ``followlinks=False`` (the default) plus unlinking directory reparse points
    keeps the deletion inside the project.
    """
    remaining: list[str] = []

    def on_error(func: Callable[..., Any], path: str, _info: Any) -> None:
        _force_writable(path)
        try:
            func(path)
        except OSError as exc:
            remaining.append(f"{path} ({exc.strerror or exc})")

    target = long_path(root)
    if not path_exists(root):
        return remaining
    try:
        shutil.rmtree(target, onerror=on_error)
    except OSError as exc:  # pragma: no cover - rmtree itself refusing
        remaining.append(f"{root} ({exc.strerror or exc})")
    if path_exists(root) and not remaining:
        remaining.append(str(root))
    return remaining


# --------------------------------------------------------------- tombstones
def tombstone_root(dataset_root: Path) -> Path:
    return Path(dataset_root).expanduser() / TOMBSTONE_DIRNAME


def recover_tombstones(dataset_root: Path, *, known_project_ids: set[str]) -> list[str]:
    """Resolve deletions interrupted by a crash. Returns human-readable notes.

    The marker records whether the database side finished, which is the only
    thing needed to decide:

    * **database cleared** - the application has already forgotten this
      project, so finish the job and free the space.
    * **database not cleared** - the project still exists as far as everything
      else is concerned, so put it back where it came from.

    Ambiguity is resolved towards *keeping* data: a tombstone with an
    unreadable marker is left alone and reported, never erased on a guess.
    """
    base = tombstone_root(dataset_root)
    if not base.is_dir():
        return []

    notes: list[str] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        marker = entry / TOMBSTONE_FILE
        if not marker.is_file():
            notes.append(
                f"{entry.name}: işaret dosyası yok, dokunulmadı. Elle inceleyin."
            )
            continue
        try:
            data = read_json_mapping(marker)
        except Exception:
            notes.append(f"{entry.name}: işaret dosyası okunamadı, dokunulmadı.")
            continue

        project_id = str(data.get("project_id") or "")
        original = str(data.get("original_path") or "")
        if data.get("database_cleared"):
            leftover = remove_tree(entry)
            if leftover:
                notes.append(
                    f"{project_id}: yarım kalan silme tamamlanamadı "
                    f"({len(leftover)} yol kaldı)."
                )
            else:
                notes.append(f"{project_id}: yarım kalan silme tamamlandı.")
            continue

        # The database still knows about it, so the project must come back.
        if not original:
            notes.append(f"{entry.name}: özgün yol bilinmiyor, dokunulmadı.")
            continue
        destination = Path(original)
        if path_exists(destination):
            notes.append(
                f"{project_id}: özgün yolda başka bir klasör var, dokunulmadı."
            )
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(long_path(entry), long_path(destination))
            (destination / TOMBSTONE_FILE).unlink(missing_ok=True)
            notes.append(f"{project_id}: yarım kalan silme geri alındı.")
        except OSError as exc:
            notes.append(f"{project_id}: geri alınamadı ({exc.strerror or exc}).")
        _ = known_project_ids
    return notes


class ProjectDeletionService:
    """Coordinates the identity database and the filesystem for one deletion.

    Held apart from the GUI so the dangerous part is testable without a window,
    and apart from :class:`IdentityService` so the database layer never grows a
    reason to import ``shutil``.
    """

    def __init__(self, identity, dataset_root: Path) -> None:
        self.identity = identity
        self.dataset_root = Path(dataset_root).expanduser()

    # ------------------------------------------------------------ preflight
    def preflight(self, actor, project_id: str) -> TargetReport:
        """Authorise and inspect without changing anything at all."""
        record = self.identity.authorize_project_deletion(actor, project_id)
        return inspect_target(
            recorded_path=Path(record.path),
            project_id=project_id,
            dataset_root=self.dataset_root,
        )

    # ---------------------------------------------------- orphaned record
    def forget_orphan(self, actor, project_id: str) -> DeletionResult:
        """Remove the *record* of a project whose folder is genuinely gone.

        A separate operation from :meth:`delete`, and deliberately narrow. It
        exists because a project whose directory was moved or removed outside
        the application could not be got rid of at all: the delete flow refuses
        - correctly - to touch a target it cannot verify, so the stale row sat
        in the list forever.

        This never touches the filesystem. It is only reachable when the
        preflight says the recorded path is *missing*; every other refusal
        (unreadable manifest, mismatched id, symlink, permission error) means
        something is there and this application does not understand it, which
        is exactly when guessing would be dangerous.
        """
        record = self.identity.authorize_project_deletion(actor, project_id)
        report = inspect_target(
            recorded_path=Path(record.path),
            project_id=project_id,
            dataset_root=self.dataset_root,
        )
        if report.code != "delete_target_missing":
            raise ValidationError(
                "Bu kayıt yetim değil: kayıtlı klasör diskte duruyor. "
                "Kalıcı silme akışını kullanın."
                if report.ok
                else (
                    "Kayıtlı hedef doğrulanamadı, fakat 'bulunamadı' da değil: "
                    f"{report.reason} Yetim kayıt kaldırma bu durumda "
                    "kullanılamaz."
                ),
                code="not_an_orphan_record",
            )

        self.identity.forget_project(
            actor, project_id, path=str(record.path), orphaned=True
        )
        logger.info(
            "Yetim proje kaydı kaldırıldı: %s (%s) - klasör bulunamadı: %s",
            record.name,
            project_id,
            record.path,
        )
        return DeletionResult(
            project_id=project_id,
            project_name=record.name or project_id,
            path=Path(record.path),
            freed_bytes=0,
            database_cleared=True,
            # Nothing was on disk to remove, which is the whole premise.
            files_removed=True,
        )

    # --------------------------------------------------------------- delete
    def delete(
        self,
        actor,
        project_id: str,
        *,
        measure: bool = True,
        progress: Optional[Callable[[str], None]] = None,
    ) -> DeletionResult:
        """Permanently delete one project. Blocking - call it off the GUI thread."""

        def step(message: str) -> None:
            if progress is not None:
                progress(message)

        record = self.identity.authorize_project_deletion(actor, project_id)
        step("Hedef doğrulanıyor…")
        report = inspect_target(
            recorded_path=Path(record.path),
            project_id=project_id,
            dataset_root=self.dataset_root,
        )
        report.raise_if_bad()
        assert report.resolved is not None
        source = report.resolved

        result = DeletionResult(
            project_id=project_id,
            project_name=record.name or project_id,
            path=source,
        )

        if measure:
            step("Boyut hesaplanıyor…")
            size, unreadable = measure_tree(source)
            result.freed_bytes = size
            if unreadable:
                logger.warning(
                    "Proje boyutu hesaplanırken %d dosya okunamadı: %s",
                    unreadable,
                    project_id,
                )

        # --- detach: after this rename the project is no longer at its path --
        step("Proje ayrılıyor…")
        tombstone = self._detach(source, project_id, record)
        result.tombstone = tombstone

        # --- commit: forget it in the database ------------------------------
        step("Kayıtlar temizleniyor…")
        try:
            self.identity.forget_project(actor, project_id, path=str(source))
        except Exception as exc:
            # The bytes are still intact in the tombstone; put them back so the
            # user is exactly where they started rather than in limbo.
            self._reattach(tombstone, source)
            logger.exception("Proje kaydı silinemedi: %s", project_id)
            raise StorageError(
                "Proje kaydı silinemedi; hiçbir dosya kaldırılmadı.",
                code="delete_db_failed",
                remedy="Uygulamayı yeniden başlatıp tekrar deneyin.",
                details={"project_id": project_id, "error": str(exc)},
            ) from exc
        result.database_cleared = True
        self._mark_database_cleared(tombstone)

        # --- erase ----------------------------------------------------------
        step("Dosyalar siliniyor…")
        remaining = remove_tree(tombstone)
        result.remaining = remaining
        result.files_removed = not remaining
        if remaining:
            logger.error(
                "Proje dosyaları tamamen silinemedi (%s): %s",
                project_id,
                "; ".join(remaining[:5]),
            )
            self.identity.note_deletion_outcome(
                actor, project_id, ok=False, detail=remaining[0]
            )
        else:
            self.identity.note_deletion_outcome(actor, project_id, ok=True)
            self._prune_tombstone_root()
        return result

    # --------------------------------------------------------------- pieces
    def _detach(self, source: Path, project_id: str, record) -> Path:
        base = tombstone_root(self.dataset_root)
        base.mkdir(parents=True, exist_ok=True)
        stamp = utc_now_iso().replace(":", "").replace("-", "")[:15]
        tombstone = base / f"{project_id}__{stamp}"
        try:
            os.replace(long_path(source), long_path(tombstone))
        except OSError as exc:
            raise StorageError(
                "Proje klasörü taşınamadı; muhtemelen bir dosya açık.",
                code="delete_detach_failed",
                remedy=(
                    "Kaydı durdurun, proje dosyalarını kullanan programları "
                    "kapatın ve tekrar deneyin."
                ),
                details={"path": str(source), "error": str(exc)},
            ) from exc
        write_json(
            tombstone / TOMBSTONE_FILE,
            {
                "project_id": project_id,
                "project_name": record.name,
                "original_path": str(source),
                "started_at": utc_now_iso(),
                "database_cleared": False,
            },
            overwrite=True,
        )
        return tombstone

    def _reattach(self, tombstone: Path, source: Path) -> None:
        (tombstone / TOMBSTONE_FILE).unlink(missing_ok=True)
        try:
            os.replace(long_path(tombstone), long_path(source))
        except OSError:  # pragma: no cover - both halves broken at once
            logger.exception("Proje geri taşınamadı: %s", tombstone)

    def _mark_database_cleared(self, tombstone: Path) -> None:
        marker = tombstone / TOMBSTONE_FILE
        try:
            data = read_json_mapping(marker) if marker.is_file() else {}
        except Exception:  # pragma: no cover
            data = {}
        data["database_cleared"] = True
        data["database_cleared_at"] = utc_now_iso()
        write_json(marker, data, overwrite=True)

    def _prune_tombstone_root(self) -> None:
        base = tombstone_root(self.dataset_root)
        try:
            if base.is_dir() and not any(base.iterdir()):
                base.rmdir()
        except OSError:  # pragma: no cover
            pass


__all__ = [
    "DeletionResult",
    "ProjectDeletionService",
    "TOMBSTONE_DIRNAME",
    "TOMBSTONE_FILE",
    "TargetReport",
    "inspect_target",
    "measure_tree",
    "recover_tombstones",
    "remove_tree",
    "tombstone_root",
]
