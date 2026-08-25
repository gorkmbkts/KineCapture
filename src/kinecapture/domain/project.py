"""Persistent dataset entities: Project, Participant, Session, Take, labels.

These are the documents that live on disk. Every one of them:

* carries a stable identifier that is never derived from mutable metadata;
* carries the schema version it was written with;
* round-trips losslessly through ``to_dict`` / ``from_dict``;
* contains no personal information in any field that becomes a file name.

Raw capture metadata and human curation are deliberately separate objects.
:class:`Take` describes what the camera produced. What a person decided about
it lives in a two-level label hierarchy stored in a separate sidecar, so that
editing a label never rewrites a take:

``MovementSample``
    One repetition inside the take. Carries the exercise and a **binary**
    correct/incorrect verdict. A take may hold several, and each becomes one
    exported sample.

``ErrorInterval``
    A sub-range *inside* one movement sample where a specific error class is
    visible. Zero or more per sample; they may repeat and may overlap. These
    are the temporal targets a future model would learn to localise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from kinecapture import (
    ANNOTATION_SCHEMA_VERSION,
    APP_VERSION,
    LABEL_SCHEMA_VERSION,
    PROJECT_SCHEMA_VERSION,
    SESSION_SCHEMA_VERSION,
    TAKE_SCHEMA_VERSION,
)
from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import new_id, timestamped_id, utc_now_iso
from kinecapture.domain.enums import (
    CaptureMode,
    ConsentStatus,
    Correctness,
    DataOrigin,
    SampleReadiness,
    SegmentSource,
    SegmentStatus,
    TakeQuality,
    TakeState,
)
from kinecapture.domain.models import CameraInfo


def _enum(value: Any, enum_cls: type, default: Any) -> Any:
    """Coerce a stored value back into its enum, falling back to ``default``."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Capture profile
# ---------------------------------------------------------------------------


@dataclass
class CaptureProfile:
    """The capture settings a take was requested with.

    Stored separately from :class:`CameraInfo`: this is what was *asked for*,
    while ``CameraInfo`` is what the device *reported*. Comparing the two is how
    a silent fallback (a camera refusing 60 fps and giving 30) becomes visible.
    """

    name: str = "default"
    resolution: str = "HD720"
    fps: int = 30
    depth_mode: str = "NEURAL_LIGHT"
    enable_depth: bool = True
    enable_body_tracking: bool = True
    body_format: str = "BODY_34"
    body_tracking_model: str = "HUMAN_BODY_MEDIUM"
    enable_body_fitting: bool = True
    detection_confidence: int = 40
    coordinate_system: str = "RIGHT_HANDED_Y_UP"
    length_unit: str = "METER"
    store_native_recording: bool = True
    #: How the exact measured depth is archived. Never off for a real capture:
    #: replaying an SVO2 was verified not to reproduce the depth that was
    #: measured, so a take without this stream has permanently lost it. Only an
    #: explicitly synthetic profile may set this to ``"none"``.
    depth_archive: str = "float32_lossless"
    #: SVO2 compression, verified against this SDK. ``H264`` is *lossy*; the
    #: lossless modes cost roughly 12x and 30x more. Recorded honestly rather
    #: than being described as lossless.
    native_compression: str = "H264"
    proxy_video_width: int = 640
    #: Refuse to start a recording that could not run this long on the free
    #: space of the target disk.
    min_free_disk_minutes: float = 3.0

    #: Historical name for the depth archive switch. Kept only so an old
    #: ``take.json`` still loads; the archive itself is no longer optional.
    store_depth_frames: bool = True

    def __post_init__(self) -> None:
        if self.fps <= 0:
            raise ValidationError(
                "Hedef FPS 0'dan büyük olmalıdır.", field="fps", code="fps_invalid"
            )
        if self.proxy_video_width < 160:
            raise ValidationError(
                "Proxy video genişliği en az 160 piksel olmalıdır.",
                field="proxy_video_width",
                code="proxy_width_invalid",
            )

    @property
    def archives_depth(self) -> bool:
        """Whether this profile keeps the measured depth."""
        return str(self.depth_archive or "none").lower() != "none"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaptureProfile":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@dataclass
class ProtocolTask:
    """One planned capture task inside a protocol.

    A protocol turns "which takes still need recording?" from a spreadsheet
    question into something the capture screen can answer by itself.
    """

    task_id: str
    exercise: str
    label: str = ""
    target_correct_takes: int = 0
    target_incorrect_takes: int = 0
    planned_error_type: str = ""
    side: str = "both"
    camera_orientation: str = ""
    reps_per_take: int = 0
    operator_instruction: str = ""
    safety_note: str = ""

    @classmethod
    def create(cls, exercise: str, **kwargs: Any) -> "ProtocolTask":
        return cls(task_id=new_id("task"), exercise=exercise, **kwargs)

    @property
    def display_label(self) -> str:
        return self.label or self.exercise

    @property
    def target_total_takes(self) -> int:
        return self.target_correct_takes + self.target_incorrect_takes

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProtocolTask":
        known = {f for f in cls.__dataclass_fields__}
        data = {k: v for k, v in payload.items() if k in known}
        data.setdefault("task_id", new_id("task"))
        data.setdefault("exercise", "unknown")
        return cls(**data)


@dataclass
class CaptureProtocol:
    """An ordered list of planned tasks, plus a free-capture escape hatch."""

    protocol_id: str
    name: str
    description: str = ""
    tasks: list[ProtocolTask] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> "CaptureProtocol":
        return cls(protocol_id=new_id("proto"), name=name, **kwargs)

    def task_by_id(self, task_id: str) -> Optional[ProtocolTask]:
        return next((t for t in self.tasks if t.task_id == task_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "name": self.name,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaptureProtocol":
        return cls(
            protocol_id=str(payload.get("protocol_id") or new_id("proto")),
            name=str(payload.get("name", "Protokol")),
            description=str(payload.get("description", "")),
            tasks=[ProtocolTask.from_dict(t) for t in payload.get("tasks") or []],
        )


# ---------------------------------------------------------------------------
# Project / Participant / Session
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """Top-level dataset workspace descriptor (``project.json``)."""

    project_id: str
    name: str
    description: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    default_capture_profile: CaptureProfile = field(default_factory=CaptureProfile)
    protocols: list[CaptureProtocol] = field(default_factory=list)
    label_schema_version: str = LABEL_SCHEMA_VERSION
    required_session_fields: tuple[str, ...] = ("operator",)
    anonymous_participants: bool = True
    next_participant_sequence: int = 1
    app_version: str = APP_VERSION
    schema_version: str = PROJECT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ValidationError(
                "Proje adı boş olamaz.", field="name", code="project_name_empty"
            )
        self.required_session_fields = tuple(self.required_session_fields)

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> "Project":
        return cls(project_id=timestamped_id("prj"), name=name, **kwargs)

    def protocol_by_id(self, protocol_id: str) -> Optional[CaptureProtocol]:
        return next((p for p in self.protocols if p.protocol_id == protocol_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "default_capture_profile": self.default_capture_profile.to_dict(),
            "protocols": [p.to_dict() for p in self.protocols],
            "label_schema_version": self.label_schema_version,
            "required_session_fields": list(self.required_session_fields),
            "anonymous_participants": self.anonymous_participants,
            "next_participant_sequence": self.next_participant_sequence,
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Project":
        return cls(
            project_id=str(payload["project_id"]),
            name=str(payload.get("name", "Proje")),
            description=str(payload.get("description", "")),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            default_capture_profile=CaptureProfile.from_dict(
                payload.get("default_capture_profile") or {}
            ),
            protocols=[
                CaptureProtocol.from_dict(p) for p in payload.get("protocols") or []
            ],
            label_schema_version=str(
                payload.get("label_schema_version") or LABEL_SCHEMA_VERSION
            ),
            required_session_fields=tuple(
                payload.get("required_session_fields") or ("operator",)
            ),
            anonymous_participants=bool(payload.get("anonymous_participants", True)),
            next_participant_sequence=int(payload.get("next_participant_sequence", 1)),
            app_version=str(payload.get("app_version") or APP_VERSION),
            schema_version=str(payload.get("schema_version") or PROJECT_SCHEMA_VERSION),
        )


@dataclass
class Participant:
    """A pseudonymous subject (``participant.json``).

    ``code`` is the only identity that ever reaches a file name or an exported
    dataset. Optional biometric fields exist because they are needed for
    normalisation research, not because they identify anyone.
    """

    participant_id: str
    code: str
    created_at: str = field(default_factory=utc_now_iso)
    notes: str = ""
    height_cm: Optional[float] = None
    mass_kg: Optional[float] = None
    dominant_side: str = "unknown"
    attributes: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SESSION_SCHEMA_VERSION

    @classmethod
    def create(cls, code: str, **kwargs: Any) -> "Participant":
        return cls(participant_id=code, code=code, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "participant_id": self.participant_id,
            "code": self.code,
            "created_at": self.created_at,
            "notes": self.notes,
            "height_cm": self.height_cm,
            "mass_kg": self.mass_kg,
            "dominant_side": self.dominant_side,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Participant":
        return cls(
            participant_id=str(payload["participant_id"]),
            code=str(payload.get("code") or payload["participant_id"]),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            notes=str(payload.get("notes", "")),
            height_cm=payload.get("height_cm"),
            mass_kg=payload.get("mass_kg"),
            dominant_side=str(payload.get("dominant_side", "unknown")),
            attributes=dict(payload.get("attributes") or {}),
            schema_version=str(payload.get("schema_version") or SESSION_SCHEMA_VERSION),
        )


@dataclass
class Session:
    """One capture sitting for one participant (``session.json``)."""

    session_id: str
    participant_id: str
    project_id: str
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    operator: str = ""
    protocol_id: Optional[str] = None
    notes: str = ""
    consent: ConsentStatus = ConsentStatus.UNKNOWN
    capture_profile: CaptureProfile = field(default_factory=CaptureProfile)
    attributes: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.consent = _enum(self.consent, ConsentStatus, ConsentStatus.UNKNOWN)

    @classmethod
    def create(cls, participant_id: str, project_id: str, **kwargs: Any) -> "Session":
        return cls(
            session_id=timestamped_id("ses"),
            participant_id=participant_id,
            project_id=project_id,
            **kwargs,
        )

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "project_id": self.project_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "operator": self.operator,
            "protocol_id": self.protocol_id,
            "notes": self.notes,
            "consent": self.consent.value,
            "capture_profile": self.capture_profile.to_dict(),
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Session":
        return cls(
            session_id=str(payload["session_id"]),
            participant_id=str(payload["participant_id"]),
            project_id=str(payload.get("project_id", "")),
            started_at=str(payload.get("started_at") or utc_now_iso()),
            ended_at=payload.get("ended_at"),
            operator=str(payload.get("operator", "")),
            protocol_id=payload.get("protocol_id"),
            notes=str(payload.get("notes", "")),
            consent=_enum(payload.get("consent"), ConsentStatus, ConsentStatus.UNKNOWN),
            capture_profile=CaptureProfile.from_dict(
                payload.get("capture_profile") or {}
            ),
            attributes=dict(payload.get("attributes") or {}),
            schema_version=str(payload.get("schema_version") or SESSION_SCHEMA_VERSION),
        )


# ---------------------------------------------------------------------------
# Take
# ---------------------------------------------------------------------------


@dataclass
class TakeQualityMetrics:
    """Measured health of one finished take.

    Every number here is observed, never assumed. ``target_fps`` is what was
    requested; ``measured_fps`` is what actually happened.
    """

    duration_s: float = 0.0
    target_fps: float = 0.0
    measured_fps: float = 0.0
    frames_written: int = 0
    frames_dropped_recording: int = 0
    backend_dropped_frames: int = 0
    missing_frame_indices: int = 0
    frames_with_body: int = 0
    frames_with_multiple_bodies: int = 0
    tracking_coverage: float = 0.0
    mean_joint_confidence: float = float("nan")
    mean_valid_joint_ratio: float = float("nan")
    body_id_changes: int = 0
    distinct_body_ids: int = 0
    max_frame_gap_ms: float = 0.0

    # --- raw archive, counted per stream ------------------------------
    # One number cannot honestly represent four different losses: a preview
    # frame thrown away to keep the GUI responsive, a pose record that never
    # reached the sidecar, a colour frame the archive could not take and a
    # depth frame the archive could not take are four different problems.
    color_frames_archived: int = 0
    color_frames_dropped: int = 0
    depth_frames_archived: int = 0
    depth_frames_dropped: int = 0
    raw_archive_failure: str = ""

    # --- selected subject ---------------------------------------------
    subject_locked_frames: int = 0
    subject_lost_frames: int = 0
    subject_ambiguous_frames: int = 0
    subject_reassociations: int = 0
    subject_manual_confirmations: int = 0
    frames_with_other_people: int = 0

    @property
    def has_capture_loss(self) -> bool:
        return self.frames_dropped_recording > 0 or self.missing_frame_indices > 0

    @property
    def has_raw_archive_loss(self) -> bool:
        """True when the immutable RGB-D source is incomplete.

        This is not the same as capture loss: the pose stream can be perfect
        while the archive that would allow reprocessing is not.
        """
        return (
            self.color_frames_dropped > 0
            or self.depth_frames_dropped > 0
            or bool(self.raw_archive_failure)
        )

    @property
    def subject_coverage(self) -> float:
        """Fraction of recorded frames where the selected person was found."""
        total = self.subject_locked_frames + self.subject_lost_frames
        return self.subject_locked_frames / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (round(value, 4) if isinstance(value, float) else value)
            for key, value in self.__dict__.items()
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TakeQualityMetrics":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class Take:
    """One recording (``take.json``).

    This document describes the capture only. Human decisions about it - which
    repetitions it contains, what they are labelled - live in the annotation
    sidecar, so a labelling session never rewrites capture provenance.
    """

    take_id: str
    session_id: str
    participant_id: str
    project_id: str
    index_in_session: int = 1
    started_at: str = field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    state: TakeState = TakeState.RECORDING
    quality: TakeQuality = TakeQuality.UNDECIDED
    capture_mode: CaptureMode = CaptureMode.FREE
    origin: DataOrigin = DataOrigin.REAL
    protocol_task_id: Optional[str] = None
    exercise: str = ""
    notes: str = ""
    capture_profile: CaptureProfile = field(default_factory=CaptureProfile)
    camera_info: Optional[CameraInfo] = None
    skeleton_format: str = ""
    files: dict[str, str] = field(default_factory=dict)
    markers: list[dict[str, Any]] = field(default_factory=list)
    body_id_events: list[dict[str, Any]] = field(default_factory=list)
    metrics: TakeQualityMetrics = field(default_factory=TakeQualityMetrics)
    app_version: str = APP_VERSION
    schema_version: str = TAKE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.state = _enum(self.state, TakeState, TakeState.RECORDING)
        self.quality = _enum(self.quality, TakeQuality, TakeQuality.UNDECIDED)
        self.capture_mode = _enum(self.capture_mode, CaptureMode, CaptureMode.FREE)
        self.origin = _enum(self.origin, DataOrigin, DataOrigin.REAL)

    @classmethod
    def create(
        cls, session_id: str, participant_id: str, project_id: str, **kwargs: Any
    ) -> "Take":
        return cls(
            take_id=timestamped_id("take"),
            session_id=session_id,
            participant_id=participant_id,
            project_id=project_id,
            **kwargs,
        )

    @property
    def is_synthetic(self) -> bool:
        return self.origin is DataOrigin.SYNTHETIC

    @property
    def is_finalized(self) -> bool:
        return self.state is TakeState.FINALIZED

    @property
    def is_recoverable_partial(self) -> bool:
        """A take whose writer never finished but which still holds frames."""
        return self.state in (TakeState.RECORDING, TakeState.PARTIAL)

    @property
    def usable_for_export(self) -> bool:
        return self.is_finalized and self.quality not in (
            TakeQuality.EXCLUDED,
            TakeQuality.TECHNICAL_ISSUE,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "take_id": self.take_id,
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "project_id": self.project_id,
            "index_in_session": self.index_in_session,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "state": self.state.value,
            "quality": self.quality.value,
            "capture_mode": self.capture_mode.value,
            "origin": self.origin.value,
            "protocol_task_id": self.protocol_task_id,
            "exercise": self.exercise,
            "notes": self.notes,
            "capture_profile": self.capture_profile.to_dict(),
            "camera_info": self.camera_info.to_dict() if self.camera_info else None,
            "skeleton_format": self.skeleton_format,
            "files": dict(self.files),
            "markers": list(self.markers),
            "body_id_events": list(self.body_id_events),
            "metrics": self.metrics.to_dict(),
            "app_version": self.app_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Take":
        camera_info = payload.get("camera_info")
        return cls(
            take_id=str(payload["take_id"]),
            session_id=str(payload.get("session_id", "")),
            participant_id=str(payload.get("participant_id", "")),
            project_id=str(payload.get("project_id", "")),
            index_in_session=int(payload.get("index_in_session", 1)),
            started_at=str(payload.get("started_at") or utc_now_iso()),
            ended_at=payload.get("ended_at"),
            state=_enum(payload.get("state"), TakeState, TakeState.PARTIAL),
            quality=_enum(payload.get("quality"), TakeQuality, TakeQuality.UNDECIDED),
            capture_mode=_enum(
                payload.get("capture_mode"), CaptureMode, CaptureMode.FREE
            ),
            origin=_enum(payload.get("origin"), DataOrigin, DataOrigin.REAL),
            protocol_task_id=payload.get("protocol_task_id"),
            exercise=str(payload.get("exercise", "")),
            notes=str(payload.get("notes", "")),
            capture_profile=CaptureProfile.from_dict(
                payload.get("capture_profile") or {}
            ),
            camera_info=CameraInfo.from_dict(camera_info) if camera_info else None,
            skeleton_format=str(payload.get("skeleton_format", "")),
            files=dict(payload.get("files") or {}),
            markers=list(payload.get("markers") or []),
            body_id_events=list(payload.get("body_id_events") or []),
            metrics=TakeQualityMetrics.from_dict(payload.get("metrics") or {}),
            app_version=str(payload.get("app_version") or APP_VERSION),
            schema_version=str(payload.get("schema_version") or TAKE_SCHEMA_VERSION),
        )


# ---------------------------------------------------------------------------
# Movement samples and error intervals
# ---------------------------------------------------------------------------
#
# Boundary convention, used identically by the timeline, the sidecar JSON and
# the exporter:
#
#   * positions are 0-based indices into the take's recorded pose stream
#     (``derived/skeleton.jsonl`` frame records), NOT the camera's own frame
#     numbers, which skip whenever a frame is dropped;
#   * ranges are INCLUSIVE at both ends, so ``frames[start:end + 1]`` is the
#     span and ``end - start + 1`` is its length.
#
# The camera's identity for a span is never lost: samples and intervals carry
# timestamps, and an exported sample additionally carries per-frame
# ``frame_indices`` and ``camera_timestamps_ns`` arrays.


@dataclass
class ErrorInterval:
    """A sub-range of one movement sample where a specific error is visible.

    **One interval carries exactly one error class.** Two different errors seen
    at the same moment are expressed as two overlapping intervals rather than
    one multi-class interval. That keeps a temporal-localisation target
    unambiguous: every interval is a clean ``(class, start, end)`` triple, and
    the same class may legitimately appear several times in one sample.

    ``error_code`` refers to the project's label schema. Nothing here invents an
    error vocabulary.
    """

    interval_id: str
    error_code: str = ""
    start_frame: int = 0
    end_frame: int = 0
    start_timestamp_ns: Optional[int] = None
    end_timestamp_ns: Optional[int] = None
    note: str = ""
    source: SegmentSource = SegmentSource.MANUAL
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    #: Fields carried over from an older sidecar that the current model has no
    #: place for. Preserved so a round trip never loses user data.
    legacy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = _enum(self.source, SegmentSource, SegmentSource.MANUAL)
        self.start_frame = int(self.start_frame)
        self.end_frame = int(self.end_frame)

    @classmethod
    def create(
        cls, start_frame: int, end_frame: int, error_code: str = "", **kwargs: Any
    ) -> "ErrorInterval":
        start, end = sorted((int(start_frame), int(end_frame)))
        return cls(
            interval_id=new_id("err"),
            error_code=error_code,
            start_frame=start,
            end_frame=end,
            **kwargs,
        )

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    @property
    def is_well_formed(self) -> bool:
        """Ordered, non-empty and carrying an error class."""
        return bool(self.error_code) and self.end_frame >= self.start_frame

    def overlaps(self, other: "ErrorInterval") -> bool:
        return not (
            self.end_frame < other.start_frame or other.end_frame < self.start_frame
        )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interval_id": self.interval_id,
            "error_code": self.error_code,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "note": self.note,
            "source": self.source.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.legacy:
            payload["legacy"] = dict(self.legacy)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ErrorInterval":
        data = dict(payload)
        legacy = dict(data.get("legacy") or {})

        # A pre-2.0 EvidenceInterval carried `error_type` plus fields the new
        # model does not keep at interval level.
        code = data.get("error_code")
        if not code:
            code = data.get("error_type") or ""
            if data.get("error_type"):
                legacy.setdefault("error_type", data["error_type"])
        for dropped in ("affected_joints", "severity"):
            if data.get(dropped):
                legacy.setdefault(dropped, data[dropped])

        start = int(data.get("start_frame", 0))
        end = int(data.get("end_frame", start))
        if end < start:
            legacy.setdefault("reversed_original", [start, end])
            start, end = end, start

        return cls(
            interval_id=str(data.get("interval_id") or new_id("err")),
            error_code=str(code or ""),
            start_frame=start,
            end_frame=end,
            start_timestamp_ns=data.get("start_timestamp_ns"),
            end_timestamp_ns=data.get("end_timestamp_ns"),
            note=str(data.get("note", "")),
            source=_enum(data.get("source"), SegmentSource, SegmentSource.MANUAL),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            legacy=legacy,
        )


@dataclass
class MovementSample:
    """One movement repetition inside a take - the unit that becomes a sample.

    A take may contain several of these. Each carries its own exercise and its
    own binary correctness decision, and may localise zero or more
    :class:`ErrorInterval` sub-ranges inside its own bounds.

    Curation lives here, never in ``take.json``: labelling must not rewrite
    capture provenance.
    """

    sample_id: str
    take_id: str
    start_frame: int
    end_frame: int
    start_timestamp_ns: Optional[int] = None
    end_timestamp_ns: Optional[int] = None
    index: int = 1
    revision: int = 1
    source: SegmentSource = SegmentSource.MANUAL
    status: SegmentStatus = SegmentStatus.ACTIVE

    # ---- the label itself -------------------------------------------------
    exercise: str = ""
    correctness: Correctness = Correctness.UNLABELLED
    error_intervals: list[ErrorInterval] = field(default_factory=list)
    note: str = ""
    annotator: str = ""

    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    label_schema_version: str = LABEL_SCHEMA_VERSION
    schema_version: str = ANNOTATION_SCHEMA_VERSION
    #: Values from an older sidecar with no home in the current model (movement
    #: phase, severity, affected joints, old review status, an ``uncertain``
    #: verdict). Kept verbatim so nothing is destroyed.
    legacy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source = _enum(self.source, SegmentSource, SegmentSource.MANUAL)
        self.status = _enum(self.status, SegmentStatus, SegmentStatus.ACTIVE)
        self.correctness = Correctness.parse(self.correctness)
        self.start_frame = int(self.start_frame)
        self.end_frame = int(self.end_frame)
        if self.end_frame < self.start_frame:
            raise ValidationError(
                f"Hareket aralığı geçersiz: bitiş karesi ({self.end_frame}) "
                f"başlangıçtan ({self.start_frame}) küçük.",
                field="end_frame",
                code="sample_reversed",
            )
        if self.start_frame < 0:
            raise ValidationError(
                "Hareket aralığı negatif kareden başlayamaz.",
                field="start_frame",
                code="sample_negative",
            )

    @classmethod
    def create(
        cls, take_id: str, start_frame: int, end_frame: int, **kwargs: Any
    ) -> "MovementSample":
        return cls(
            sample_id=new_id("mov"),
            take_id=take_id,
            start_frame=int(start_frame),
            end_frame=int(end_frame),
            **kwargs,
        )

    # ------------------------------------------------------------- geometry
    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    @property
    def is_active(self) -> bool:
        return self.status is SegmentStatus.ACTIVE

    def contains(self, frame: int) -> bool:
        return self.start_frame <= frame <= self.end_frame

    def clamp(self, start: int, end: int) -> tuple[int, int]:
        """Clip a candidate sub-range into this sample, keeping it ordered."""
        low, high = sorted((int(start), int(end)))
        low = max(self.start_frame, min(low, self.end_frame))
        high = max(self.start_frame, min(high, self.end_frame))
        return low, high

    def overlaps(self, other: "MovementSample") -> bool:
        return not (
            self.end_frame < other.start_frame or other.end_frame < self.start_frame
        )

    # --------------------------------------------------------------- labels
    @property
    def is_human_confirmed(self) -> bool:
        """A model suggestion nobody has touched is not ground truth."""
        return self.source is not SegmentSource.MODEL_SUGGESTION or self.revision > 1

    @property
    def error_codes(self) -> tuple[str, ...]:
        """Distinct error classes localised here, in first-seen order."""
        seen: list[str] = []
        for interval in self.error_intervals:
            if interval.error_code and interval.error_code not in seen:
                seen.append(interval.error_code)
        return tuple(seen)

    def interval(self, interval_id: str) -> Optional[ErrorInterval]:
        return next(
            (i for i in self.error_intervals if i.interval_id == interval_id), None
        )

    def sorted_intervals(self) -> list[ErrorInterval]:
        return sorted(
            self.error_intervals,
            key=lambda i: (i.start_frame, i.end_frame, i.error_code),
        )

    def touch(self) -> None:
        self.revision += 1
        self.updated_at = utc_now_iso()

    # ------------------------------------------------------------- transport
    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "label_schema_version": self.label_schema_version,
            "sample_id": self.sample_id,
            "take_id": self.take_id,
            "index": self.index,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "revision": self.revision,
            "source": self.source.value,
            "status": self.status.value,
            "exercise": self.exercise,
            "correctness": self.correctness.value,
            "error_intervals": [i.to_dict() for i in self.sorted_intervals()],
            "note": self.note,
            "annotator": self.annotator,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.legacy:
            payload["legacy"] = dict(self.legacy)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MovementSample":
        """Read a v2 sample, or migrate a pre-2.0 ``RepetitionSegment``.

        Migration never invents a decision: an ``uncertain`` verdict becomes
        ``UNLABELLED`` and the original wording is kept under ``legacy`` so the
        annotator can see what the old file claimed.
        """
        data = dict(payload)
        legacy = dict(data.get("legacy") or {})

        # Pre-2.0 files nested the label inside an "annotation" object.
        annotation = data.get("annotation")
        is_legacy = isinstance(annotation, Mapping)
        label: Mapping[str, Any] = annotation if is_legacy else data

        raw_correctness = label.get("correctness")
        correctness = Correctness.parse(raw_correctness)
        if raw_correctness is not None and not correctness.is_decided:
            text = str(raw_correctness).strip().lower()
            if text and text != Correctness.UNLABELLED.value:
                legacy.setdefault("correctness", text)

        # Fields the redesign removed. Preserved, never re-interpreted.
        dropped_keys = ["movement_phase", "severity", "annotator_confidence",
                        "affected_joints"]
        if is_legacy:
            # Only a v1 document has a review status *inside* the label. In v2
            # the top-level `status` is the sample's own active/excluded state
            # and must not be mistaken for it.
            dropped_keys.append("status")
        for key in dropped_keys:
            value = label.get(key)
            if value not in (None, "", [], {}):
                legacy.setdefault(key, value)

        intervals = [
            ErrorInterval.from_dict(item)
            for item in list(label.get("evidence_intervals") or [])
            + list(label.get("error_intervals") or [])
        ]

        # A pre-2.0 sample carried error classes at movement level with no
        # timing. They cannot become localised intervals without inventing
        # boundaries, so they are recorded as unlocalised classes instead.
        sample_level_errors = [
            str(code) for code in (label.get("error_types") or []) if str(code)
        ]
        if sample_level_errors:
            legacy.setdefault("unlocalised_error_types", sample_level_errors)

        start = int(data["start_frame"])
        end = int(data.get("end_frame", start))
        if end < start:
            legacy.setdefault("reversed_original", [start, end])
            start, end = end, start

        return cls(
            sample_id=str(
                data.get("sample_id") or data.get("segment_id") or new_id("mov")
            ),
            take_id=str(data.get("take_id", "")),
            start_frame=start,
            end_frame=end,
            start_timestamp_ns=data.get("start_timestamp_ns"),
            end_timestamp_ns=data.get("end_timestamp_ns"),
            index=int(data.get("index", 1)),
            revision=int(data.get("revision", 1)),
            source=_enum(data.get("source"), SegmentSource, SegmentSource.MANUAL),
            status=_enum(data.get("status"), SegmentStatus, SegmentStatus.ACTIVE),
            exercise=str(label.get("exercise", "")),
            correctness=correctness,
            error_intervals=intervals,
            note=str(label.get("note", "")),
            annotator=str(label.get("annotator", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            label_schema_version=str(
                label.get("label_schema_version") or LABEL_SCHEMA_VERSION
            ),
            schema_version=str(data.get("schema_version") or ANNOTATION_SCHEMA_VERSION),
            legacy=legacy,
        )


#: Backwards-compatible alias. The class was called ``RepetitionSegment`` before
#: the two-level label redesign; the name survives so older imports keep working.
RepetitionSegment = MovementSample


# ---------------------------------------------------------------------------
# Validation - one rule, shared by the screen and the exporter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampleProblem:
    """One reason a sample is not ready, in a form the UI can render directly."""

    code: str
    message: str
    interval_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "interval_id": self.interval_id,
        }


def evaluate_sample(
    sample: MovementSample, *, known_error_codes: Optional[Sequence[str]] = None
) -> tuple[SampleReadiness, list[SampleProblem]]:
    """Decide whether one sample is export-ready, and say exactly why not.

    This is the single definition of "labelled". The review screen shows its
    verdict and the exporter obeys it, so a sample the user sees as finished is
    precisely a sample that ends up in a release.

    ``known_error_codes`` is the project's error vocabulary. Pass ``None`` to
    skip vocabulary checking (useful while the schema is still being edited).
    """
    problems: list[SampleProblem] = []

    if not sample.is_active:
        return SampleReadiness.EXCLUDED, problems

    # --- structural checks on the intervals themselves ---------------------
    vocabulary = set(known_error_codes) if known_error_codes is not None else None
    for interval in sample.error_intervals:
        if not interval.error_code:
            problems.append(
                SampleProblem(
                    "interval_without_class",
                    "Hata aralığına bir hata türü seçilmedi.",
                    interval.interval_id,
                )
            )
        elif vocabulary is not None and interval.error_code not in vocabulary:
            problems.append(
                SampleProblem(
                    "unknown_error_class",
                    f"'{interval.error_code}' hata türü proje şemasında yok.",
                    interval.interval_id,
                )
            )
        if interval.end_frame < interval.start_frame:
            problems.append(
                SampleProblem(
                    "interval_reversed",
                    "Hata aralığının bitişi başlangıcından önce.",
                    interval.interval_id,
                )
            )
        elif not (
            sample.start_frame <= interval.start_frame
            and interval.end_frame <= sample.end_frame
        ):
            problems.append(
                SampleProblem(
                    "interval_outside_sample",
                    (
                        f"Hata aralığı ({interval.start_frame}-{interval.end_frame}) "
                        f"hareketin dışında ({sample.start_frame}-{sample.end_frame})."
                    ),
                    interval.interval_id,
                )
            )

    if problems:
        return SampleReadiness.INVALID_INTERVAL, problems

    # --- the label itself ---------------------------------------------------
    if not sample.exercise:
        problems.append(
            SampleProblem("no_exercise", "Hareket türü seçilmedi.")
        )
    if not sample.correctness.is_decided:
        problems.append(
            SampleProblem("no_verdict", "Doğru/yanlış kararı verilmedi.")
        )
    if problems:
        return SampleReadiness.UNLABELLED, problems

    if sample.correctness is Correctness.CORRECT and sample.error_intervals:
        problems.append(
            SampleProblem(
                "correct_with_errors",
                (
                    "Hareket doğru işaretlendi fakat "
                    f"{len(sample.error_intervals)} hata aralığı içeriyor."
                ),
            )
        )
        return SampleReadiness.CONTRADICTION, problems

    if sample.correctness is Correctness.INCORRECT and not sample.error_intervals:
        problems.append(
            SampleProblem(
                "incorrect_without_interval",
                "Hatalı hareket için en az bir hata aralığı işaretlenmeli.",
            )
        )
        return SampleReadiness.NEEDS_ERROR_INTERVAL, problems

    return SampleReadiness.READY, problems


def sample_readiness(
    sample: MovementSample, *, known_error_codes: Optional[Sequence[str]] = None
) -> SampleReadiness:
    return evaluate_sample(sample, known_error_codes=known_error_codes)[0]


def is_export_ready(
    sample: MovementSample, *, known_error_codes: Optional[Sequence[str]] = None
) -> bool:
    """The one predicate both the UI and the exporter use."""
    return sample_readiness(sample, known_error_codes=known_error_codes).is_ready


def validate_samples(
    samples: Sequence[MovementSample], *, frame_count: Optional[int] = None
) -> list[dict[str, Any]]:
    """Structural problems across a take's whole set of movement samples.

    Problems are returned rather than raised: the review screen shows all of
    them at once so the user fixes them in one pass.
    """
    problems: list[dict[str, Any]] = []
    active = [s for s in samples if s.is_active]
    ordered = sorted(active, key=lambda s: (s.start_frame, s.end_frame))
    for position, sample in enumerate(ordered):
        if frame_count is not None and sample.end_frame >= frame_count:
            problems.append(
                {
                    "sample_id": sample.sample_id,
                    "issue": "out_of_range",
                    "message": (
                        f"Hareket {sample.index}: bitiş karesi ({sample.end_frame}) "
                        f"kayıt uzunluğunun ({frame_count}) dışında."
                    ),
                }
            )
        if sample.frame_count < 2:
            problems.append(
                {
                    "sample_id": sample.sample_id,
                    "issue": "too_short",
                    "message": f"Hareket {sample.index}: aralık en az 2 kare olmalı.",
                }
            )
        if position + 1 < len(ordered) and sample.overlaps(ordered[position + 1]):
            problems.append(
                {
                    "sample_id": sample.sample_id,
                    "issue": "overlap",
                    "message": (
                        f"Hareket {sample.index} ile "
                        f"{ordered[position + 1].index} çakışıyor."
                    ),
                }
            )
        for interval in sample.error_intervals:
            if not (
                sample.start_frame <= interval.start_frame
                and interval.end_frame <= sample.end_frame
            ):
                problems.append(
                    {
                        "sample_id": sample.sample_id,
                        "issue": "interval_outside_sample",
                        "message": (
                            f"Hareket {sample.index}: bir hata aralığı hareketin "
                            "dışına taşıyor."
                        ),
                    }
                )
    return problems


def renumber_samples(samples: Iterable[MovementSample]) -> list[MovementSample]:
    """Reassign ``index`` in chronological order."""
    ordered = sorted(samples, key=lambda s: (s.start_frame, s.end_frame))
    for position, sample in enumerate(ordered, start=1):
        sample.index = position
    return ordered


#: Legacy aliases kept so older call sites and tests keep working.
validate_segments = validate_samples
renumber_segments = renumber_samples


__all__ = [
    "CaptureProfile",
    "CaptureProtocol",
    "ErrorInterval",
    "MovementSample",
    "Participant",
    "Project",
    "ProtocolTask",
    "RepetitionSegment",
    "SampleProblem",
    "Session",
    "Take",
    "TakeQualityMetrics",
    "evaluate_sample",
    "is_export_ready",
    "renumber_samples",
    "renumber_segments",
    "sample_readiness",
    "validate_samples",
    "validate_segments",
]
