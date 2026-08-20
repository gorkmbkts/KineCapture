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

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from kinecapture.core.errors import StorageError, ValidationError
from kinecapture.core.ids import is_safe_id, participant_code, utc_now_iso
from kinecapture.core.jsonio import read_json_mapping, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.core.logging import get_logger
from kinecapture.domain.enums import TakeState
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import (
    CaptureProfile,
    Participant,
    Project,
    RepetitionSegment,
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
            self.derived_dir,
            self.annotations_dir,
            self.quality_dir,
        ):
            ensure_dir(directory)

    def checksum_targets(self) -> dict[str, Path]:
        """Relative-name -> path map for the take's checksum manifest."""
        return {
            f"raw/{NATIVE_RECORDING_FILE}": self.native_recording,
            f"derived/{SKELETON_STREAM_FILE}": self.skeleton_stream,
            f"derived/{PROXY_VIDEO_FILE}": self.proxy_video,
            TAKE_FILE: self.metadata,
        }


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
        """Create the next pseudonymous participant (``P0001``, ``P0002``, ...)."""
        project = self.project
        sequence = project.next_participant_sequence
        existing = {p.code for p in self.list_participants()}
        while participant_code(sequence) in existing:
            sequence += 1
        participant = Participant.create(participant_code(sequence), **kwargs)
        directory = self.participant_dir(participant.participant_id)
        ensure_dir(directory / "sessions")
        write_json(directory / PARTICIPANT_FILE, participant.to_dict())
        project.next_participant_sequence = sequence + 1
        self.save_project(project)
        logger.info("Katılımcı oluşturuldu: %s", participant.code)
        return participant

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
    def load_segments(self, take: Take) -> list[RepetitionSegment]:
        """Load a take's repetition segments; an unlabelled take returns ``[]``."""
        path = self.take_paths(take).segments
        if not path_exists(path):
            return []
        payload = read_json_mapping(path)
        segments: list[RepetitionSegment] = []
        for entry in payload.get("segments") or []:
            try:
                segments.append(RepetitionSegment.from_dict(entry))
            except (ValidationError, KeyError, TypeError) as exc:
                logger.warning(
                    "Geçersiz tekrar aralığı atlandı (%s): %s", take.take_id, exc
                )
        return sorted(segments, key=lambda s: (s.start_frame, s.end_frame))

    def save_segments(
        self, take: Take, segments: Iterable[RepetitionSegment]
    ) -> list[RepetitionSegment]:
        """Write the annotation sidecar. Never touches ``take.json``."""
        ordered = sorted(segments, key=lambda s: (s.start_frame, s.end_frame))
        paths = self.take_paths(take)
        ensure_dir(paths.annotations_dir)
        write_json(
            paths.segments,
            {
                "take_id": take.take_id,
                "updated_at": utc_now_iso(),
                "segments": [segment.to_dict() for segment in ordered],
            },
            overwrite=True,
        )
        return ordered

    # --------------------------------------------------------------- quality
    def load_quality(self, take: Take) -> dict[str, Any]:
        path = self.take_paths(take).quality
        return read_json_mapping(path) if path_exists(path) else {}

    def summary_counts(self) -> dict[str, int]:
        """Cheap counts for the dashboard, read from metadata only."""
        participants = self.list_participants()
        sessions = self.list_sessions()
        takes = self.list_takes()
        repetitions = sum(len(self.load_segments(take)) for take in takes)
        return {
            "participants": len(participants),
            "sessions": len(sessions),
            "takes": len(takes),
            "finalized_takes": sum(1 for t in takes if t.is_finalized),
            "partial_takes": sum(1 for t in takes if t.is_recoverable_partial),
            "repetitions": repetitions,
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
