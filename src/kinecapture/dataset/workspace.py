"""On-disk project workspace.

Layout
------
```text
dataset_root/
└── projects/<project_id>/
    ├── project.json
    ├── label_schema.json
    ├── participants/<participant_id>/
    │   ├── participant.json
    │   └── sessions/<session_id>/
    │       ├── session.json
    │       └── takes/<take_id>/
    │           ├── take.json          capture metadata + provenance
    │           ├── raw/               immutable native recording (SVO2)
    │           ├── derived/           skeleton sidecar + review proxy video
    │           ├── annotations/       segments.json (human curation)
    │           ├── quality/           quality.json (measured metrics)
    │           └── checksums.json
    └── releases/<dataset_vNNN>/
```

Guarantees
----------
* Raw capture and human curation live in different files, so labelling never
  rewrites a take's provenance.
* Every write goes through the atomic helpers in
  :mod:`kinecapture.core.jsonio`; an interrupted save never destroys the
  previous document.
* Nothing here deletes user data. ``discard_take`` is the single destructive
  operation and it requires the caller to name the exact take it intends to
  remove.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from kinecapture import ANNOTATION_SCHEMA_VERSION
from kinecapture.core.errors import StorageError, ValidationError
from kinecapture.core.ids import is_safe_id, participant_code, utc_now_iso
from kinecapture.core.jsonio import read_json_mapping, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.core.logging import get_logger
from kinecapture.domain.enums import TakeState
from kinecapture.domain.activity import ActivityInterval
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import (
    CaptureProfile,
    MovementSample,
    Participant,
    Project,
    RepetitionSegment,  # noqa: F401  (legacy alias re-export)
    Session,
    Take,
)

logger = get_logger(__name__)

PROJECTS_DIRNAME = "projects"
RELEASES_DIRNAME = "releases"
PROJECT_FILE = "project.json"
LABEL_SCHEMA_FILE = "label_schema.json"
PARTICIPANT_FILE = "participant.json"
SESSION_FILE = "session.json"
TAKE_FILE = "take.json"
SEGMENTS_FILE = "segments.json"
QUALITY_FILE = "quality.json"
CHECKSUMS_FILE = "checksums.json"

#: File names inside a take directory. Kept in one place so the writer, the
#: reader, the checksum manifest and the export all agree.
SKELETON_STREAM_FILE = "skeleton.jsonl"
#: Directory holding the exact colour/depth the recording measured.
RGBD_DIR = "rgbd"
#: One line per recorded frame, mapping every stream onto one position.
RAW_INDEX_FILE = "index.jsonl"
#: Versioned description of the raw archive: format, codec, provenance, sync.
RAW_MANIFEST_FILE = "raw_capture_manifest.json"
PROXY_VIDEO_FILE = "proxy.mp4"
NATIVE_RECORDING_FILE = "capture.svo2"


@dataclass(frozen=True)
class TakePaths:
    """Every path belonging to one take, derived from its directory."""

    root: Path

    @property
    def metadata(self) -> Path:
        return self.root / TAKE_FILE

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def derived_dir(self) -> Path:
        return self.root / "derived"

    @property
    def annotations_dir(self) -> Path:
        return self.root / "annotations"

    @property
    def quality_dir(self) -> Path:
        return self.root / "quality"

    @property
    def native_recording(self) -> Path:
        return self.raw_dir / NATIVE_RECORDING_FILE

    @property
    def rgbd_dir(self) -> Path:
        """Chunked colour/depth archive. Immutable once the take is finalised."""
        return self.raw_dir / RGBD_DIR

    @property
    def raw_index(self) -> Path:
        """Per-frame synchronisation index across every raw stream."""
        return self.rgbd_dir / RAW_INDEX_FILE

    @property
    def raw_manifest(self) -> Path:
        """What the raw archive is, how it was produced and what it contains."""
        return self.raw_dir / RAW_MANIFEST_FILE

    @property
    def skeleton_stream(self) -> Path:
        return self.derived_dir / SKELETON_STREAM_FILE

    @property
    def proxy_video(self) -> Path:
        return self.derived_dir / PROXY_VIDEO_FILE

    @property
    def segments(self) -> Path:
        return self.annotations_dir / SEGMENTS_FILE

    @property
    def quality(self) -> Path:
        return self.quality_dir / QUALITY_FILE

    @property
    def checksums(self) -> Path:
        return self.root / CHECKSUMS_FILE

    def ensure_dirs(self) -> None:
        for directory in (
            self.root,
            self.raw_dir,
            self.rgbd_dir,
            self.derived_dir,
            self.annotations_dir,
            self.quality_dir,
        ):
            ensure_dir(directory)

    def checksum_targets(self) -> dict[str, Path]:
        """Relative-name -> path map for the take's checksum manifest."""
        targets: dict[str, Path] = {
            f"raw/{NATIVE_RECORDING_FILE}": self.native_recording,
            f"raw/{RAW_MANIFEST_FILE}": self.raw_manifest,
            f"raw/{RGBD_DIR}/{RAW_INDEX_FILE}": self.raw_index,
            f"derived/{SKELETON_STREAM_FILE}": self.skeleton_stream,
            f"derived/{PROXY_VIDEO_FILE}": self.proxy_video,
            TAKE_FILE: self.metadata,
        }
        # Every archive chunk is checksummed individually, so a single
        # corrupted chunk is identified rather than invalidating the take.
        if self.rgbd_dir.is_dir():
            for chunk in sorted(self.rgbd_dir.iterdir()):
                if chunk.suffix in (".kcd", ".kcc"):
                    targets[f"raw/{RGBD_DIR}/{chunk.name}"] = chunk
        return targets


#: Top-level keys of ``annotations/segments.json`` this version writes itself.
#: Anything else found in an existing sidecar is preserved verbatim rather than
#: dropped - see :meth:`ProjectWorkspace.save_samples`.
_ANNOTATION_KNOWN_KEYS = frozenset(
    {
        "schema_version",
        "take_id",
        "updated_at",
        "boundary_convention",
        "samples",
        "segments",
        "activity_intervals",
        "activity_note",
    }
)


class ProjectWorkspace:
    """Read/write access to one project directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self._project: Optional[Project] = None
        self._label_schema: Optional[LabelSchema] = None

    # ------------------------------------------------------------ discovery
    @classmethod
    def create(
        cls,
        dataset_root: Path,
        name: str,
        *,
        description: str = "",
        capture_profile: Optional[CaptureProfile] = None,
        label_schema: Optional[LabelSchema] = None,
    ) -> "ProjectWorkspace":
        """Create a new project directory. Never touches an existing one."""
        project = Project.create(
            name=name,
            description=description,
            default_capture_profile=capture_profile or CaptureProfile(),
        )
        root = Path(dataset_root).expanduser() / PROJECTS_DIRNAME / project.project_id
        if path_exists(root):
            raise StorageError(
                f"Proje klasörü zaten var: {root.name}",
                code="project_exists",
                remedy="Farklı bir proje adı deneyin.",
                details={"path": str(root)},
            )
        workspace = cls(root)
        ensure_dir(workspace.root / "participants")
        ensure_dir(workspace.root / RELEASES_DIRNAME)
        write_json(workspace.project_file, project.to_dict())
        write_json(
            workspace.label_schema_file, (label_schema or LabelSchema.default()).to_dict()
        )
        logger.info("Proje oluşturuldu: %s (%s)", project.name, project.project_id)
        return workspace

    @classmethod
    def open(cls, root: Path) -> "ProjectWorkspace":
        """Open an existing project, verifying it really is one."""
        workspace = cls(root)
        if not path_exists(workspace.project_file):
            raise StorageError(
                f"Bu klasör bir KineCapture projesi değil: {workspace.root.name}",
                code="project_not_found",
                remedy=f"{PROJECT_FILE} dosyasını içeren klasörü seçin.",
                details={"path": str(workspace.root)},
            )
        workspace.project  # eager load so a corrupt file fails here, not later
        return workspace

    @staticmethod
    def discover(dataset_root: Path) -> list[Path]:
        """Return every project directory under ``dataset_root``."""
        base = Path(dataset_root).expanduser() / PROJECTS_DIRNAME
        if not base.is_dir():
            return []
        return sorted(
            child for child in base.iterdir() if (child / PROJECT_FILE).is_file()
        )

    # ---------------------------------------------------------------- paths
    @property
    def project_file(self) -> Path:
        return self.root / PROJECT_FILE

    @property
    def label_schema_file(self) -> Path:
        return self.root / LABEL_SCHEMA_FILE

    @property
    def participants_dir(self) -> Path:
        return self.root / "participants"

    @property
    def releases_dir(self) -> Path:
        return self.root / RELEASES_DIRNAME

    def participant_dir(self, participant_id: str) -> Path:
        self._guard_id(participant_id, "participant_id")
        return self.participants_dir / participant_id

    def session_dir(self, participant_id: str, session_id: str) -> Path:
        self._guard_id(session_id, "session_id")
        return self.participant_dir(participant_id) / "sessions" / session_id

    def take_dir(self, participant_id: str, session_id: str, take_id: str) -> Path:
        self._guard_id(take_id, "take_id")
        return self.session_dir(participant_id, session_id) / "takes" / take_id

    def take_paths(self, take: Take) -> TakePaths:
        return TakePaths(
            self.take_dir(take.participant_id, take.session_id, take.take_id)
        )

    @staticmethod
    def _guard_id(value: str, field: str) -> None:
        """Refuse an identifier that could escape the workspace directory."""
        if not is_safe_id(value):
            raise ValidationError(
                f"Geçersiz kimlik: {value!r}",
                field=field,
                code="unsafe_identifier",
                remedy="Kimlikler yalnızca harf, rakam, '-', '_' ve '.' içerebilir.",
            )

    # -------------------------------------------------------------- project
    @property
    def project(self) -> Project:
        if self._project is None:
            self._project = Project.from_dict(read_json_mapping(self.project_file))
        return self._project

    def save_project(self, project: Optional[Project] = None) -> Project:
        target = project or self.project
        target.updated_at = utc_now_iso()
        write_json(self.project_file, target.to_dict(), overwrite=True)
        self._project = target
        return target

    @property
    def label_schema(self) -> LabelSchema:
        if self._label_schema is None:
            if self.label_schema_file.is_file():
                self._label_schema = LabelSchema.from_dict(
                    read_json_mapping(self.label_schema_file)
                )
            else:
                self._label_schema = LabelSchema.default()
        return self._label_schema

    def save_label_schema(self, schema: Optional[LabelSchema] = None) -> LabelSchema:
        target = schema or self.label_schema
        write_json(self.label_schema_file, target.to_dict(), overwrite=True)
        self._label_schema = target
        return target

    # ---------------------------------------------------------- participants
    def create_participant(self, **kwargs: Any) -> Participant:
        """Atomically allocate the next project-local anonymous code."""
        lock_path = self.root / ".participant-allocation.lock"
        descriptor: Optional[int] = None
        deadline = time.monotonic() + 5.0
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise StorageError(
                        "Katılımcı kodu şu anda ayrılamıyor.",
                        code="participant_allocation_busy",
                        remedy="Birkaç saniye sonra yeniden deneyin.",
                    )
                time.sleep(0.02)
        directory: Optional[Path] = None
        try:
            # Reload inside the allocation lock so another process's counter
            # update cannot be hidden by this workspace's cache.
            project = Project.from_dict(read_json_mapping(self.project_file))
            sequence = project.next_participant_sequence
            existing = {p.code for p in self.list_participants()}
            while participant_code(sequence) in existing:
                sequence += 1
            participant = Participant.create(participant_code(sequence), **kwargs)
            directory = self.participant_dir(participant.participant_id)
            directory.mkdir(parents=False, exist_ok=False)
            ensure_dir(directory / "sessions")
            write_json(directory / PARTICIPANT_FILE, participant.to_dict())
            project.next_participant_sequence = sequence + 1
            try:
                write_json(self.project_file, project.to_dict(), overwrite=True)
            except Exception:
                # Compensation is limited to the directory allocated by this
                # call and cannot reach outside participants/.
                if directory.parent.resolve() == self.participants_dir.resolve():
                    shutil.rmtree(directory)
                raise
            self._project = project
            logger.info("Katılımcı oluşturuldu: %s", participant.code)
            return participant
        finally:
            if descriptor is not None:
                os.close(descriptor)
            lock_path.unlink(missing_ok=True)

    def preview_next_participant_code(self) -> str:
        """Informational preview; the real allocation happens under a lock."""
        project = Project.from_dict(read_json_mapping(self.project_file))
        sequence = project.next_participant_sequence
        existing = {p.code for p in self.list_participants()}
        while participant_code(sequence) in existing:
            sequence += 1
        return participant_code(sequence)

    def save_participant(self, participant: Participant) -> Participant:
        directory = self.participant_dir(participant.participant_id)
        ensure_dir(directory)
        write_json(directory / PARTICIPANT_FILE, participant.to_dict(), overwrite=True)
        return participant

    def load_participant(self, participant_id: str) -> Participant:
        path = self.participant_dir(participant_id) / PARTICIPANT_FILE
        return Participant.from_dict(read_json_mapping(path))

    def list_participants(self) -> list[Participant]:
        if not self.participants_dir.is_dir():
            return []
        participants: list[Participant] = []
        for directory in sorted(self.participants_dir.iterdir()):
            path = directory / PARTICIPANT_FILE
            if not path.is_file():
                continue
            try:
                participants.append(Participant.from_dict(read_json_mapping(path)))
            except StorageError as exc:
                logger.warning("Katılımcı okunamadı (%s): %s", directory.name, exc)
        return participants

    # -------------------------------------------------------------- sessions
    def create_session(self, participant_id: str, **kwargs: Any) -> Session:
        session = Session.create(
            participant_id=participant_id,
            project_id=self.project.project_id,
            **kwargs,
        )
        directory = self.session_dir(participant_id, session.session_id)
        ensure_dir(directory / "takes")
        write_json(directory / SESSION_FILE, session.to_dict())
        logger.info("Oturum oluşturuldu: %s (%s)", session.session_id, participant_id)
        return session

    def save_session(self, session: Session) -> Session:
        directory = self.session_dir(session.participant_id, session.session_id)
        ensure_dir(directory)
        write_json(directory / SESSION_FILE, session.to_dict(), overwrite=True)
        return session

    def load_session(self, participant_id: str, session_id: str) -> Session:
        path = self.session_dir(participant_id, session_id) / SESSION_FILE
        return Session.from_dict(read_json_mapping(path))

    def list_sessions(self, participant_id: Optional[str] = None) -> list[Session]:
        participant_ids = (
            [participant_id]
            if participant_id
            else [p.participant_id for p in self.list_participants()]
        )
        sessions: list[Session] = []
        for pid in participant_ids:
            base = self.participant_dir(pid) / "sessions"
            if not base.is_dir():
                continue
            for directory in sorted(base.iterdir()):
                path = directory / SESSION_FILE
                if not path.is_file():
                    continue
                try:
                    sessions.append(Session.from_dict(read_json_mapping(path)))
                except StorageError as exc:
                    logger.warning("Oturum okunamadı (%s): %s", directory.name, exc)
        return sessions

    # ----------------------------------------------------------------- takes
    def prepare_take(self, session: Session, **kwargs: Any) -> tuple[Take, TakePaths]:
        """Allocate a take directory and its metadata stub.

        The stub is written immediately with ``state=RECORDING`` so that a crash
        during capture still leaves a discoverable, recoverable take on disk
        rather than an anonymous directory.
        """
        existing = self.list_takes(session.participant_id, session.session_id)
        take = Take.create(
            session_id=session.session_id,
            participant_id=session.participant_id,
            project_id=self.project.project_id,
            index_in_session=len(existing) + 1,
            capture_profile=session.capture_profile,
            **kwargs,
        )
        paths = self.take_paths(take)
        if path_exists(paths.metadata):
            raise StorageError(
                f"Kayıt klasörü zaten kullanılıyor: {take.take_id}",
                code="take_exists",
                details={"path": str(paths.root)},
            )
        paths.ensure_dirs()
        write_json(paths.metadata, take.to_dict())
        return take, paths

    def save_take(self, take: Take) -> Take:
        paths = self.take_paths(take)
        paths.ensure_dirs()
        write_json(paths.metadata, take.to_dict(), overwrite=True)
        return take

    def load_take(self, participant_id: str, session_id: str, take_id: str) -> Take:
        path = self.take_dir(participant_id, session_id, take_id) / TAKE_FILE
        return Take.from_dict(read_json_mapping(path))

    def list_takes(
        self, participant_id: Optional[str] = None, session_id: Optional[str] = None
    ) -> list[Take]:
        """List takes, optionally filtered to one participant and/or session."""
        takes: list[Take] = []
        for session in self.list_sessions(participant_id):
            if session_id and session.session_id != session_id:
                continue
            base = (
                self.session_dir(session.participant_id, session.session_id) / "takes"
            )
            if not base.is_dir():
                continue
            for directory in sorted(base.iterdir()):
                path = directory / TAKE_FILE
                if not path.is_file():
                    continue
                try:
                    takes.append(Take.from_dict(read_json_mapping(path)))
                except StorageError as exc:
                    logger.warning("Kayıt okunamadı (%s): %s", directory.name, exc)
        return takes

    def iter_takes(self) -> Iterator[Take]:
        yield from self.list_takes()

    def find_partial_takes(self) -> list[Take]:
        """Takes whose writer never finished - candidates for recovery.

        Called at start-up so an interrupted session surfaces as a decision the
        user makes, not as a directory nobody ever looks at again.
        """
        return [take for take in self.list_takes() if take.is_recoverable_partial]

    def discard_take(self, take: Take, *, confirm_take_id: str) -> None:
        """Permanently delete one take directory.

        The caller must repeat the take id in ``confirm_take_id``. This is the
        only destructive operation in the workspace and it never runs
        implicitly.
        """
        if confirm_take_id != take.take_id:
            raise ValidationError(
                "Silme onayı kayıt kimliğiyle eşleşmiyor; hiçbir şey silinmedi.",
                field="confirm_take_id",
                code="discard_confirmation_mismatch",
            )
        paths = self.take_paths(take)
        if not path_exists(paths.root):
            return
        logger.warning("Kayıt siliniyor: %s (%s)", take.take_id, paths.root)
        shutil.rmtree(long_path(paths.root))

    # ----------------------------------------------------------- annotations
    #
    # The label sidecar keeps its file name across schema versions so existing
    # takes stay discoverable. Version 2 stores movement samples under
    # ``samples``; version 1 stored repetition segments under ``segments``.
    # Reading accepts both and never rewrites the file - a v1 document is only
    # converted on disk when the user actually saves an edit, so merely opening
    # a project can never destroy an older annotation.

    def load_samples(self, take: Take) -> list[MovementSample]:
        """Load a take's movement samples; an unlabelled take returns ``[]``."""
        path = self.take_paths(take).segments
        if not path_exists(path):
            return []
        payload = read_json_mapping(path)
        entries = payload.get("samples")
        if entries is None:
            entries = payload.get("segments") or []
            if entries:
                logger.info(
                    "Etiket dosyası v1 biçiminde okundu (%s); kaydedilene kadar "
                    "diskte değiştirilmiyor.",
                    take.take_id,
                )
        samples: list[MovementSample] = []
        for entry in entries:
            try:
                samples.append(MovementSample.from_dict(entry))
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                # A single unreadable entry must not cost the user the rest of
                # the file, but it is never dropped quietly either.
                logger.warning(
                    "Geçersiz hareket aralığı atlandı (%s): %s", take.take_id, exc
                )
        return sorted(samples, key=lambda s: (s.start_frame, s.end_frame))

    def load_activity_intervals(self, take: Take) -> list[ActivityInterval]:
        """Load the take's activity strip, if it has one.

        Purely additive: a sidecar written before this layer existed simply has
        no ``activity_intervals`` key and yields an empty strip. Reading never
        rewrites the file, so opening an old take cannot alter it.
        """
        path = self.take_paths(take).segments
        if not path_exists(path):
            return []
        payload = read_json_mapping(path)
        entries = payload.get("activity_intervals") or []
        intervals: list[ActivityInterval] = []
        for entry in entries:
            try:
                intervals.append(ActivityInterval.from_dict(entry))
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "Geçersiz aktivite aralığı atlandı (%s): %s", take.take_id, exc
                )
        return sorted(intervals, key=lambda i: (i.start_frame, i.end_frame))

    def save_samples(
        self,
        take: Take,
        samples: Iterable[MovementSample],
        activity_intervals: Optional[Iterable[ActivityInterval]] = None,
    ) -> list[MovementSample]:
        """Write the annotation sidecar. Never touches ``take.json``.

        ``activity_intervals`` defaults to *keeping what is already on disk*,
        so a caller that only knows about movement samples cannot delete an
        activity strip it never loaded.

        Any top-level block this version does not recognise is carried over
        untouched. That covers a sidecar written by a newer build, and it covers
        retired features: activity authoring was removed from the review screen,
        and the recorded ``activity_intervals`` of takes labelled before that
        must survive every subsequent save rather than being quietly dropped by
        the first edit made afterwards.
        """
        ordered = sorted(samples, key=lambda s: (s.start_frame, s.end_frame))
        paths = self.take_paths(take)
        ensure_dir(paths.annotations_dir)
        if activity_intervals is None:
            activity = self.load_activity_intervals(take)
        else:
            activity = sorted(
                activity_intervals, key=lambda i: (i.start_frame, i.end_frame)
            )
        existing = read_json_mapping(paths.segments) if path_exists(paths.segments) else {}
        carried = {
            key: value
            for key, value in existing.items()
            if key not in _ANNOTATION_KNOWN_KEYS
        }
        document: dict[str, Any] = {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "take_id": take.take_id,
            "updated_at": utc_now_iso(),
            "boundary_convention": (
                "start_frame ve end_frame, derived/skeleton.jsonl kare "
                "listesindeki 0 tabanlı konumlardır ve her iki uç dahildir."
            ),
            "samples": [sample.to_dict() for sample in ordered],
        }
        if activity:
            document["activity_intervals"] = [
                interval.to_dict() for interval in activity
            ]
            document["activity_note"] = (
                "Aktivite durumları karşılıklı dışlayandır. Etiketlenmemiş "
                "kareler burada hiç görünmez ve background sayılmaz. Bu blok "
                "yalnızca okunur: inceleme ekranında aktivite düzenlenmez."
            )
        if carried:
            logger.info(
                "Tanınmayan %d annotation bloğu korundu: %s",
                len(carried),
                ", ".join(sorted(carried)),
            )
            document.update(carried)
        write_json(paths.segments, document, overwrite=True)
        return ordered

    #: Pre-redesign names, kept so older call sites keep working.
    load_segments = load_samples
    save_segments = save_samples

    # --------------------------------------------------------------- quality
    def load_quality(self, take: Take) -> dict[str, Any]:
        path = self.take_paths(take).quality
        return read_json_mapping(path) if path_exists(path) else {}

    def summary_counts(self) -> dict[str, int]:
        """Cheap counts for the dashboard, read from metadata only."""
        participants = self.list_participants()
        sessions = self.list_sessions()
        takes = self.list_takes()
        movement_samples = sum(len(self.load_samples(take)) for take in takes)
        return {
            "participants": len(participants),
            "sessions": len(sessions),
            "takes": len(takes),
            "finalized_takes": sum(1 for t in takes if t.is_finalized),
            "partial_takes": sum(1 for t in takes if t.is_recoverable_partial),
            "movement_samples": movement_samples,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ProjectWorkspace {self.root}>"


def take_state_label(state: TakeState) -> str:
    """Turkish label for a take state, used by every list view."""
    return {
        TakeState.RECORDING: "Kaydediliyor",
        TakeState.PARTIAL: "Yarım kalmış",
        TakeState.FINALIZED: "Tamamlandı",
        TakeState.FAILED: "Başarısız",
    }[state]


__all__ = [
    "CHECKSUMS_FILE",
    "NATIVE_RECORDING_FILE",
    "PROJECTS_DIRNAME",
    "PROXY_VIDEO_FILE",
    "ProjectWorkspace",
    "SKELETON_STREAM_FILE",
    "TakePaths",
    "take_state_label",
]
