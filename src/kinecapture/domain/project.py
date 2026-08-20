"""Persistent dataset entities: Project, Participant, Session, Take, Repetition.

These are the documents that live on disk. Every one of them:

* carries a stable identifier that is never derived from mutable metadata;
* carries the schema version it was written with;
* round-trips losslessly through ``to_dict`` / ``from_dict``;
* contains no personal information in any field that becomes a file name.

Raw capture metadata and human curation are deliberately separate objects.
:class:`Take` describes what the camera produced; :class:`RepetitionSegment`
and :class:`AnnotationRecord` describe what a person decided about it, and live
in a separate sidecar file so that editing a label never rewrites a take.
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
    AnnotationStatus,
    CaptureMode,
    ConsentStatus,
    Correctness,
    DataOrigin,
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
    store_depth_frames: bool = False
    proxy_video_width: int = 640

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

    @property
    def has_capture_loss(self) -> bool:
        return self.frames_dropped_recording > 0 or self.missing_frame_indices > 0

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
# Repetition + annotation
# ---------------------------------------------------------------------------


@dataclass
class EvidenceInterval:
    """A sub-interval of a repetition where a specific error is visible.

    The ontology of ``error_type`` is defined by the project's label schema, not
    by this class. Nothing here invents error categories.
    """

    interval_id: str
    start_frame: int
    end_frame: int
    error_type: str = ""
    affected_joints: tuple[str, ...] = ()
    severity: Optional[float] = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.end_frame < self.start_frame:
            raise ValidationError(
                f"Kanıt aralığı geçersiz: bitiş ({self.end_frame}) < "
                f"başlangıç ({self.start_frame})",
                field="end_frame",
                code="interval_reversed",
            )
        self.affected_joints = tuple(self.affected_joints)

    @classmethod
    def create(cls, start_frame: int, end_frame: int, **kwargs: Any) -> "EvidenceInterval":
        return cls(
            interval_id=new_id("ev"),
            start_frame=start_frame,
            end_frame=end_frame,
            **kwargs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "error_type": self.error_type,
            "affected_joints": list(self.affected_joints),
            "severity": self.severity,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceInterval":
        return cls(
            interval_id=str(payload.get("interval_id") or new_id("ev")),
            start_frame=int(payload["start_frame"]),
            end_frame=int(payload["end_frame"]),
            error_type=str(payload.get("error_type", "")),
            affected_joints=tuple(payload.get("affected_joints") or ()),
            severity=payload.get("severity"),
            note=str(payload.get("note", "")),
        )


@dataclass
class AnnotationRecord:
    """The human judgement attached to one repetition.

    ``source`` distinguishes a person's decision from a model's suggestion, and
    a model suggestion never counts as ground truth: the dataset export only
    accepts records whose ``status`` a human has moved past ``DRAFT``.
    """

    exercise: str = ""
    correctness: Correctness = Correctness.UNKNOWN
    error_types: tuple[str, ...] = ()
    affected_joints: tuple[str, ...] = ()
    movement_phase: str = ""
    evidence_intervals: list[EvidenceInterval] = field(default_factory=list)
    severity: Optional[float] = None
    annotator_confidence: Optional[float] = None
    note: str = ""
    status: AnnotationStatus = AnnotationStatus.DRAFT
    annotator: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    label_schema_version: str = LABEL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.correctness = _enum(self.correctness, Correctness, Correctness.UNKNOWN)
        self.status = _enum(self.status, AnnotationStatus, AnnotationStatus.DRAFT)
        self.error_types = tuple(self.error_types)
        self.affected_joints = tuple(self.affected_joints)

    @property
    def is_labelled(self) -> bool:
        """True once the annotation carries a real decision, not just a stub."""
        return bool(self.exercise) and self.correctness is not Correctness.UNKNOWN

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label_schema_version": self.label_schema_version,
            "exercise": self.exercise,
            "correctness": self.correctness.value,
            "error_types": list(self.error_types),
            "affected_joints": list(self.affected_joints),
            "movement_phase": self.movement_phase,
            "evidence_intervals": [i.to_dict() for i in self.evidence_intervals],
            "severity": self.severity,
            "annotator_confidence": self.annotator_confidence,
            "note": self.note,
            "status": self.status.value,
            "annotator": self.annotator,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AnnotationRecord":
        return cls(
            exercise=str(payload.get("exercise", "")),
            correctness=_enum(
                payload.get("correctness"), Correctness, Correctness.UNKNOWN
            ),
            error_types=tuple(payload.get("error_types") or ()),
            affected_joints=tuple(payload.get("affected_joints") or ()),
            movement_phase=str(payload.get("movement_phase", "")),
            evidence_intervals=[
                EvidenceInterval.from_dict(i)
                for i in payload.get("evidence_intervals") or []
            ],
            severity=payload.get("severity"),
            annotator_confidence=payload.get("annotator_confidence"),
            note=str(payload.get("note", "")),
            status=_enum(payload.get("status"), AnnotationStatus, AnnotationStatus.DRAFT),
            annotator=str(payload.get("annotator", "")),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            label_schema_version=str(
                payload.get("label_schema_version") or LABEL_SCHEMA_VERSION
            ),
        )


@dataclass
class RepetitionSegment:
    """A frame interval of a take that contains one repetition.

    Coordinate system
    -----------------
    ``start_frame`` and ``end_frame`` are **positions in the take's recorded
    pose stream** - 0-based indices into ``skeleton.jsonl``'s frame records,
    inclusive on both ends. They are *not* the camera's own frame numbers,
    which can skip when a frame is dropped.

    That choice keeps the timeline, the player and the exporter working in one
    unambiguous space. The camera's identity for those frames is not lost: each
    segment also stores ``start_timestamp_ns`` / ``end_timestamp_ns``, and an
    exported sample carries the per-frame ``frame_indices`` and
    ``camera_timestamps_ns`` arrays alongside the poses.
    """

    segment_id: str
    take_id: str
    start_frame: int
    end_frame: int
    start_timestamp_ns: Optional[int] = None
    end_timestamp_ns: Optional[int] = None
    index: int = 1
    revision: int = 1
    source: SegmentSource = SegmentSource.MANUAL
    status: SegmentStatus = SegmentStatus.ACTIVE
    annotation: AnnotationRecord = field(default_factory=AnnotationRecord)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    schema_version: str = ANNOTATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.source = _enum(self.source, SegmentSource, SegmentSource.MANUAL)
        self.status = _enum(self.status, SegmentStatus, SegmentStatus.ACTIVE)
        if self.end_frame < self.start_frame:
            raise ValidationError(
                f"Tekrar aralığı geçersiz: bitiş karesi ({self.end_frame}) "
                f"başlangıçtan ({self.start_frame}) küçük.",
                field="end_frame",
                code="segment_reversed",
            )
        if self.start_frame < 0:
            raise ValidationError(
                "Tekrar aralığı negatif kareden başlayamaz.",
                field="start_frame",
                code="segment_negative",
            )

    @classmethod
    def create(
        cls, take_id: str, start_frame: int, end_frame: int, **kwargs: Any
    ) -> "RepetitionSegment":
        return cls(
            segment_id=new_id("rep"),
            take_id=take_id,
            start_frame=start_frame,
            end_frame=end_frame,
            **kwargs,
        )

    @property
    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    @property
    def is_active(self) -> bool:
        return self.status is SegmentStatus.ACTIVE

    @property
    def is_human_confirmed(self) -> bool:
        """A model suggestion nobody has touched is not ground truth."""
        return self.source is not SegmentSource.MODEL_SUGGESTION or self.revision > 1

    def overlaps(self, other: "RepetitionSegment") -> bool:
        return not (
            self.end_frame < other.start_frame or other.end_frame < self.start_frame
        )

    def touch(self) -> None:
        self.revision += 1
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
            "take_id": self.take_id,
            "index": self.index,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "revision": self.revision,
            "source": self.source.value,
            "status": self.status.value,
            "annotation": self.annotation.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RepetitionSegment":
        return cls(
            segment_id=str(payload.get("segment_id") or new_id("rep")),
            take_id=str(payload.get("take_id", "")),
            start_frame=int(payload["start_frame"]),
            end_frame=int(payload["end_frame"]),
            start_timestamp_ns=payload.get("start_timestamp_ns"),
            end_timestamp_ns=payload.get("end_timestamp_ns"),
            index=int(payload.get("index", 1)),
            revision=int(payload.get("revision", 1)),
            source=_enum(payload.get("source"), SegmentSource, SegmentSource.MANUAL),
            status=_enum(payload.get("status"), SegmentStatus, SegmentStatus.ACTIVE),
            annotation=AnnotationRecord.from_dict(payload.get("annotation") or {}),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or utc_now_iso()),
            schema_version=str(
                payload.get("schema_version") or ANNOTATION_SCHEMA_VERSION
            ),
        )


def validate_segments(
    segments: Sequence[RepetitionSegment], *, frame_count: Optional[int] = None
) -> list[dict[str, Any]]:
    """Return every structural problem in a set of repetition intervals.

    Problems are returned rather than raised: the review screen shows all of
    them at once so the user can fix them in one pass instead of one dialog at
    a time.
    """
    problems: list[dict[str, Any]] = []
    active = [s for s in segments if s.is_active]
    ordered = sorted(active, key=lambda s: (s.start_frame, s.end_frame))
    for index, segment in enumerate(ordered):
        if frame_count is not None and segment.end_frame >= frame_count:
            problems.append(
                {
                    "segment_id": segment.segment_id,
                    "issue": "out_of_range",
                    "message": (
                        f"Tekrar {segment.index}: bitiş karesi ({segment.end_frame}) "
                        f"kayıt uzunluğunun ({frame_count}) dışında."
                    ),
                }
            )
        if segment.frame_count < 2:
            problems.append(
                {
                    "segment_id": segment.segment_id,
                    "issue": "too_short",
                    "message": f"Tekrar {segment.index}: aralık en az 2 kare olmalı.",
                }
            )
        if index + 1 < len(ordered) and segment.overlaps(ordered[index + 1]):
            problems.append(
                {
                    "segment_id": segment.segment_id,
                    "issue": "overlap",
                    "message": (
                        f"Tekrar {segment.index} ile "
                        f"{ordered[index + 1].index} çakışıyor."
                    ),
                }
            )
    return problems


def renumber_segments(segments: Iterable[RepetitionSegment]) -> list[RepetitionSegment]:
    """Reassign ``index`` in chronological order, keeping excluded ones in place."""
    ordered = sorted(segments, key=lambda s: (s.start_frame, s.end_frame))
    for position, segment in enumerate(ordered, start=1):
        segment.index = position
    return ordered


__all__ = [
    "AnnotationRecord",
    "CaptureProfile",
    "CaptureProtocol",
    "EvidenceInterval",
    "Participant",
    "Project",
    "ProtocolTask",
    "RepetitionSegment",
    "Session",
    "Take",
    "TakeQualityMetrics",
    "renumber_segments",
    "validate_segments",
]
