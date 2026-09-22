"""A rebuildable cache of what a project contains.

Listing takes used to mean ``rglob("*.json")`` over the whole project and a
``stat`` on every file it found - measured at 650 ms for a thousand takes, paid
on the GUI thread on *every* refresh, cache hit or not.

This index walks the four-deep take directories with ``os.scandir`` instead -
which hands back the stat the listing already produced - and re-reads metadata
only for the takes whose folder changed since last time. The result is written
next to the project as a cache, and only when something actually moved.

It is not free: a thousand takes is still tens of milliseconds of file-system
work, so a screen runs this on a worker thread. What it buys is that the work
is small enough to run often.

**It is derived, never authoritative.** Delete it, corrupt it, ship a project
without it - every answer is still on disk in ``take.json`` and ``job.json``,
and the next refresh rebuilds it. Nothing may be recorded here that cannot be
recomputed from those files.

No Qt, no SDK.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists

logger = logging.getLogger(__name__)

TAKE_INDEX_SCHEMA_VERSION = "1.0.0"
#: Named so nobody mistakes it for project data. Safe to delete at any time.
CACHE_DIRNAME = "cache"
TAKE_INDEX_FILE = "take_index.json"


@dataclass(frozen=True)
class ProcessingRunSummary:
    """One version of one take, as the library screen needs to list it."""

    run_id: str
    state: str = "unknown"
    frames: int = 0
    issues: tuple[str, ...] = ()
    #: The subset of ``issues`` that stopped this version being published.
    #: Empty for every version a screen can list, by construction.
    blocking_issues: tuple[str, ...] = ()
    #: Frames the live recording wrote, and how many of them were found again
    #: in the replayed source. Carried as numbers so a list row can say
    #: "521/524" instead of asking the reader to trust a yes/no.
    capture_frames: int = 0
    matched_frames: int = 0
    #: Processed frames, and how many of them the chosen person was tracked
    #: in. A different axis from source coverage: a version can find every
    #: frame of the raw recording and still have nobody in most of them.
    #: ``tracked_frames`` is ``None`` for a run produced before schema 1.3.0,
    #: which means "not recorded", never "none".
    subject_frames: int = 0
    tracked_frames: Optional[int] = None
    #: When this attempt started, and when its job file was last written.
    #: Several versions of one take share the take's timestamp, so this is the
    #: only thing that can put them in the order they were produced.
    created_at: str = ""
    job_mtime_ns: int = 0

    @property
    def order_key(self) -> tuple:
        """Oldest first. Falls back to the file's own clock, then the name."""
        return (self.created_at, self.job_mtime_ns, self.run_id)
    subject_status: str = ""
    body_format: str = ""
    schema_version: str = ""
    has_thumbnails: bool = False
    has_summary: bool = False
    has_depth: bool = False
    #: The folder this run actually lives in, relative to ``derived/processing``.
    #: Recorded rather than rebuilt from ``run_id`` because a run in progress
    #: sits in ``.<run_id>.partial`` until it is promoted.
    folder: str = ""
    #: False while the run is still in its staging folder.
    promoted: bool = True

    @property
    def is_published(self) -> bool:
        """Finished **and** promoted to its final folder.

        A staging folder can already contain a job file claiming a finished
        state: processing writes the state, then the checksums, then renames.
        Trusting the claim gave the library a version whose directory did not
        exist yet. Promotion is the event that makes a version real, so it is
        what this asks about.

        ``partial`` counts. A version with recorded caveats is still a version
        - that is the whole point of recording the caveats - and refusing to
        list it is how two perfectly annotatable 16 September recordings became
        invisible. What a version may *not* be is unfinished or broken, and
        those never reach a promoted folder.
        """
        return self.promoted and self.state in ("complete", "partial")

    @property
    def is_flawless(self) -> bool:
        """Published with nothing at all to report. Never rounded up to."""
        return self.is_published and self.state == "complete" and not self.issues

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = list(self.issues)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProcessingRunSummary":
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in payload.items() if k in known}
        data["issues"] = tuple(data.get("issues") or ())
        return cls(**data)


@dataclass(frozen=True)
class TakeSummary:
    """One take. Enough to filter and sort a list without opening anything."""

    take_id: str
    participant_id: str
    session_id: str
    directory: str
    started_at: str = ""
    state: str = ""
    processing_status: str = ""
    origin: str = ""
    frames: int = 0
    duration_s: float = 0.0
    quality: str = ""
    runs: tuple[ProcessingRunSummary, ...] = ()
    #: Folder modification times, so the next refresh knows what to re-read.
    take_mtime_ns: int = 0
    derived_mtime_ns: int = 0

    @property
    def awaits_processing(self) -> bool:
        return self.processing_status == "awaiting_processing" and not self.published_runs

    @property
    def published_runs(self) -> tuple[ProcessingRunSummary, ...]:
        return tuple(run for run in self.runs if run.is_published)

    @property
    def latest_published_run(self) -> Optional[ProcessingRunSummary]:
        runs = self.published_runs
        return runs[-1] if runs else None

    @property
    def is_legacy(self) -> bool:
        """Recorded before the raw-first policy, so the new screens do not open it.

        Detected, not deleted: these takes stay on disk and stay listed, marked
        as what they are.
        """
        return self.processing_status == "live"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["runs"] = [run.to_dict() for run in self.runs]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TakeSummary":
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in payload.items() if k in known}
        data["runs"] = tuple(
            ProcessingRunSummary.from_dict(entry) for entry in payload.get("runs") or ()
        )
        return cls(**data)


def _mtime_ns(path: Path) -> int:
    try:
        return int(os.stat(long_path(path)).st_mtime_ns)
    except OSError:
        return 0


def _scandir(path: str) -> list[os.DirEntry]:
    """``os.scandir`` that treats a missing or unreadable directory as empty.

    Used instead of ``Path.glob`` because a ``DirEntry`` carries the stat the
    directory listing already returned. Globbing the same tree stats every
    entry a second time, and on this machine a single ``stat`` costs about
    65 microseconds - at a thousand takes that is the whole budget.
    """
    try:
        with os.scandir(path) as entries:
            return list(entries)
    except OSError:
        return []


def _tracked_frames(job: dict, directory: Path) -> Optional[int]:
    """How many frames held the chosen person, or ``None`` when unrecorded.

    Schema 1.3.0 writes the number into the job file. An older run kept the
    same counters only in its ``features.json``, so that is read as a fallback
    - a small file beside the job, not the version itself. ``None`` means the
    question was never answered, which is not the same as "nobody".
    """
    block = job.get("subject_coverage")
    if isinstance(block, dict) and block.get("tracked_frames") is not None:
        return int(block["tracked_frames"])
    features = directory / "features.json"
    if not features.is_file():
        return None
    try:
        counters = (
            dict(read_json(features)).get("subject_association", {}).get("counters", {})
        )
    except Exception as exc:  # noqa: BLE001 - a stale sidecar must not hide the run
        logger.debug("Kişi kapsamı okunamadı (%s): %s", directory.name, exc)
        return None
    locked = counters.get("locked_frames")
    return None if locked is None else int(locked)


def _read_runs(take_dir: Path) -> tuple[ProcessingRunSummary, ...]:
    base = Path(long_path(take_dir / "derived" / "processing"))
    if not base.is_dir():
        return ()
    runs: list[ProcessingRunSummary] = []
    for child in sorted(base.iterdir()):
        # ``.run_*.partial`` directories are attempts in progress. They are
        # listed with whatever state their job file claims, never as results.
        if not child.is_dir():
            continue
        job_path = child / "job.json"
        if not job_path.is_file():
            continue
        try:
            job = dict(read_json(job_path))
        except Exception as exc:  # noqa: BLE001 - a bad job file must not hide the take
            logger.warning("İş dosyası okunamadı (%s): %s", child.name, exc)
            continue
        promoted = not child.name.startswith(".")
        runs.append(
            ProcessingRunSummary(
                run_id=str(job.get("run_id", child.name)),
                folder=child.name,
                promoted=promoted,
                state=str(job.get("state", "unknown")),
                frames=int(job.get("frames_processed", 0) or 0),
                issues=tuple(job.get("issues") or ()),
                blocking_issues=tuple(job.get("blocking_issues") or ()),
                capture_frames=int((job.get("coverage") or {}).get("capture_frames", 0) or 0),
                matched_frames=int((job.get("coverage") or {}).get("matched_frames", 0) or 0),
                subject_frames=int(
                    (job.get("subject_coverage") or {}).get(
                        "frames", job.get("frames_processed", 0) or 0
                    )
                    or 0
                ),
                tracked_frames=_tracked_frames(job, child),
                created_at=str(job.get("created_at") or ""),
                job_mtime_ns=_mtime_ns(job_path),
                subject_status=str(job.get("subject_status", "")),
                body_format=str(job.get("skeleton_format") or ""),
                schema_version=str(job.get("schema_version", "")),
                has_thumbnails=(child / "thumbs" / "index.json").is_file(),
                has_summary=(child / "summary" / "index.json").is_file(),
                has_depth=(child / "depth").is_dir(),
            )
        )
    # Produced order, so "the latest version" means the latest one.
    runs.sort(key=lambda run: run.order_key)
    return tuple(runs)


def _read_take(take_dir: Path, participant_id: str, session_id: str) -> Optional[TakeSummary]:
    metadata = take_dir / "take.json"
    if not path_exists(metadata):
        return None
    try:
        take = dict(read_json(metadata))
    except Exception as exc:  # noqa: BLE001 - one unreadable take must not stop the list
        logger.warning("Kayıt metadata'sı okunamadı (%s): %s", take_dir.name, exc)
        return None
    metrics = take.get("metrics") or {}
    return TakeSummary(
        take_id=str(take.get("take_id", take_dir.name)),
        participant_id=participant_id,
        session_id=session_id,
        directory=str(take_dir),
        started_at=str(take.get("started_at", "")),
        state=str(take.get("state", "")),
        processing_status=str(take.get("processing_status", "live")),
        origin=str(take.get("origin", "")),
        frames=int(metrics.get("frames_written", 0) or 0),
        duration_s=float(metrics.get("duration_s", 0.0) or 0.0),
        quality=str(take.get("quality", "")),
        runs=_read_runs(take_dir),
        take_mtime_ns=_mtime_ns(take_dir),
        derived_mtime_ns=_mtime_ns(take_dir / "derived" / "processing"),
    )


@dataclass
class TakeIndex:
    """The cache plus the refresh that keeps it honest."""

    project_root: Path
    takes: dict[str, TakeSummary] = field(default_factory=dict)
    #: Takes whose metadata was actually re-read by the last refresh.
    rescanned: int = 0
    scanned_directories: int = 0
    #: Whether the last refresh found anything different from the cache.
    changed: bool = True

    # ------------------------------------------------------------------ paths
    @property
    def cache_file(self) -> Path:
        return self.project_root / CACHE_DIRNAME / TAKE_INDEX_FILE

    # ------------------------------------------------------------- lifecycle
    @classmethod
    def load(cls, project_root: Path) -> "TakeIndex":
        """Read the cache. A missing or unusable one is simply an empty index."""
        index = cls(project_root=Path(project_root))
        if not path_exists(index.cache_file):
            return index
        try:
            payload = dict(read_json(index.cache_file))
            if payload.get("schema_version") != TAKE_INDEX_SCHEMA_VERSION:
                return index
            index.takes = {
                str(entry["take_id"]): TakeSummary.from_dict(entry)
                for entry in payload.get("takes") or ()
            }
        except Exception as exc:  # noqa: BLE001 - the cache is never authoritative
            logger.warning("Kayıt indeksi okunamadı, yeniden üretilecek: %s", exc)
            index.takes = {}
        return index

    def save(self) -> Optional[Path]:
        try:
            ensure_dir(self.cache_file.parent)
            return write_json(
                self.cache_file,
                {
                    "schema_version": TAKE_INDEX_SCHEMA_VERSION,
                    "note": "Türetilmiş önbellek. Silinebilir; sonraki yenilemede yeniden üretilir.",
                    "takes": [take.to_dict() for take in self.sorted_takes()],
                },
                overwrite=True,
            )
        except Exception as exc:  # noqa: BLE001 - a cache that cannot be written is not an error
            logger.warning("Kayıt indeksi yazılamadı: %s", exc)
            return None

    # --------------------------------------------------------------- refresh
    def refresh(self, *, force: bool = False) -> "TakeIndex":
        """Bring the index up to date, re-reading only what changed.

        A take is re-read when its own folder or its ``derived/processing``
        folder has a newer modification time than the cache recorded - that is,
        when a take or a processing version appeared, vanished or was
        republished. Everything else is carried over untouched.

        **This detects structure, not live progress.** A job writing its
        progress into an existing ``job.json`` does not move either folder, so
        a screen that wants a running job's percentage reads that file
        directly. Making the index notice would mean statting every run
        directory on every refresh, which is the cost this exists to avoid.

        Not free at scale: with a thousand takes this is tens of milliseconds
        of file-system work and belongs on a worker thread, not in a paint.
        """
        participants = str(Path(long_path(self.project_root / "participants")))
        by_directory = {Path(t.directory).name: t for t in self.takes.values()}
        found: dict[str, TakeSummary] = {}
        rescanned = 0
        directories = 0

        for participant_entry in sorted(_scandir(participants), key=lambda e: e.name):
            if not participant_entry.is_dir():
                continue
            sessions = os.path.join(participant_entry.path, "sessions")
            for session_entry in sorted(_scandir(sessions), key=lambda e: e.name):
                if not session_entry.is_dir():
                    continue
                takes = os.path.join(session_entry.path, "takes")
                for take_entry in sorted(_scandir(takes), key=lambda e: e.name):
                    if not take_entry.is_dir():
                        continue
                    directories += 1
                    take_dir = Path(take_entry.path)
                    existing = by_directory.get(take_entry.name)
                    # DirEntry.stat() is served from the listing on Windows;
                    # only the derived folder costs a real stat.
                    take_mtime = int(take_entry.stat().st_mtime_ns)
                    derived_mtime = _mtime_ns(take_dir / "derived" / "processing")
                    unchanged = (
                        not force
                        and existing is not None
                        and existing.take_mtime_ns == take_mtime
                        and existing.derived_mtime_ns == derived_mtime
                    )
                    if unchanged and existing is not None:
                        found[existing.take_id] = existing
                        continue
                    summary = _read_take(
                        take_dir, participant_entry.name, session_entry.name
                    )
                    if summary is not None:
                        found[summary.take_id] = summary
                        rescanned += 1

        self.changed = rescanned > 0 or set(found) != set(self.takes)
        self.takes = found
        self.rescanned = rescanned
        self.scanned_directories = directories
        return self

    # ---------------------------------------------------------------- access
    def sorted_takes(self) -> list[TakeSummary]:
        return sorted(self.takes.values(), key=lambda take: (take.started_at, take.take_id))

    def by_id(self, take_id: str) -> Optional[TakeSummary]:
        return self.takes.get(take_id)

    def awaiting_processing(self) -> list[TakeSummary]:
        return [take for take in self.sorted_takes() if take.awaits_processing]

    def with_published_runs(self) -> list[TakeSummary]:
        return [take for take in self.sorted_takes() if take.published_runs]

    def legacy_takes(self) -> list[TakeSummary]:
        return [take for take in self.sorted_takes() if take.is_legacy]

    def published_runs(self) -> list[tuple[TakeSummary, ProcessingRunSummary]]:
        """Every listable version in the project, newest take last."""
        pairs: list[tuple[TakeSummary, ProcessingRunSummary]] = []
        for take in self.sorted_takes():
            pairs.extend((take, run) for run in take.published_runs)
        return pairs

    def __len__(self) -> int:
        return len(self.takes)

    def __iter__(self) -> Iterable[TakeSummary]:
        return iter(self.sorted_takes())


def build_index(project_root: Path, *, force: bool = False, save: bool = True) -> TakeIndex:
    """Load the cache, refresh it against the disk, and write it back if it moved.

    An unchanged project is not rewritten: serialising a thousand entries costs
    more than the scan that proved nothing happened, and rewriting a file to
    say "still the same" is how a cache starts costing more than it saves.
    """
    index = TakeIndex.load(project_root).refresh(force=force)
    if save and (index.changed or not path_exists(index.cache_file)):
        index.save()
    return index


__all__ = [
    "CACHE_DIRNAME",
    "TAKE_INDEX_FILE",
    "TAKE_INDEX_SCHEMA_VERSION",
    "ProcessingRunSummary",
    "TakeIndex",
    "TakeSummary",
    "build_index",
]
