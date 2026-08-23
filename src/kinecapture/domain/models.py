"""Live-capture data models.

Design rules (MEMORY.md sections 4 and 7):

* Raw data and display-only transforms are kept apart. Nothing in this module
  re-centres, rescales or re-orients coordinates.
* NumPy array shapes and dtypes are validated at construction time so a
  malformed packet fails where it is produced, not three layers later.
* Models are backend independent: no ``pyzed`` and no Qt types here.
* Non-finite joint coordinates are *preserved*, not repaired. A joint the
  tracker could not see must stay visibly absent rather than becoming a
  plausible-looking number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Optional

import numpy as np

from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import (
    BodyActionState,
    CaptureStatus,
    DataOrigin,
    TrackingState,
)


@dataclass(frozen=True)
class CameraInfo:
    """Static description of the capture device.

    Every field that ends up in a take's provenance block comes from here, so
    it must describe what the device *actually* reported rather than what the
    configuration asked for.
    """

    backend: str
    model: str
    origin: DataOrigin = DataOrigin.REAL
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    sdk_version: Optional[str] = None
    resolution: tuple[int, int] = (0, 0)
    target_fps: float = 0.0
    coordinate_system: str = "unspecified"
    length_unit: str = "unspecified"
    body_format: Optional[str] = None
    depth_available: bool = False
    body_tracking_available: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_synthetic(self) -> bool:
        return self.origin is DataOrigin.SYNTHETIC

    @property
    def display_name(self) -> str:
        suffix = " (Sentetik)" if self.is_synthetic else ""
        return f"{self.model}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "origin": self.origin.value,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "sdk_version": self.sdk_version,
            "resolution": list(self.resolution),
            "target_fps": self.target_fps,
            "coordinate_system": self.coordinate_system,
            "length_unit": self.length_unit,
            "body_format": self.body_format,
            "depth_available": self.depth_available,
            "body_tracking_available": self.body_tracking_available,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CameraInfo":
        data = dict(payload)
        resolution = data.get("resolution") or [0, 0]
        return cls(
            backend=str(data.get("backend", "unknown")),
            model=str(data.get("model", "unknown")),
            origin=DataOrigin(data.get("origin", DataOrigin.REAL.value)),
            serial_number=data.get("serial_number"),
            firmware_version=data.get("firmware_version"),
            sdk_version=data.get("sdk_version"),
            resolution=(int(resolution[0]), int(resolution[1])),
            target_fps=float(data.get("target_fps") or 0.0),
            coordinate_system=str(data.get("coordinate_system", "unspecified")),
            length_unit=str(data.get("length_unit", "unspecified")),
            body_format=data.get("body_format"),
            depth_available=bool(data.get("depth_available", False)),
            body_tracking_available=bool(data.get("body_tracking_available", False)),
            extra=dict(data.get("extra") or {}),
        )


@dataclass
class BodyPose:
    """One detected person in one frame.

    Required shapes:
        ``joint_positions_xyz``  float32 ``[J, 3]``  - raw source coordinates
        ``joint_confidences``    float32 ``[J]``     - 0..1, NaN when unknown

    Optional tracker outputs. Every one of them is genuinely optional: a body
    format or an SDK version that does not produce a field leaves it ``None``
    rather than carrying a plausible-looking substitute.

        ``joint_orientations``           float32 ``[J, 4]`` - **xyzw** order,
            parent-relative ("local") joint rotations
        ``joint_positions_2d``           float32 ``[J, 2]`` - image pixels in
            the left camera's image, valid only together with the resolution
            and intrinsics recorded in the take's camera provenance
        ``joint_position_covariances``   float32 ``[J, 6]`` - per-joint 3D
            position covariance in the tracker's **native element order**,
            stored verbatim because that order is not documented in a form
            this project has verified
        ``local_joint_positions_xyz``    float32 ``[J, 3]`` - parent-relative
            joint positions from the SDK's body fitting
        ``root_position``                float32 ``[3]``
        ``root_orientation``             float32 ``[4]``    - **xyzw**, global
        ``tracker_root_velocity_xyz``    float32 ``[3]``    - the tracker's own
            root velocity, in length unit per second. Kept separate from any
            velocity this application derives from coordinates.
        ``root_position_covariance``     float32 ``[6]``    - native order
        ``action_state``                 tracker motion state, never a clinical
            or biomechanical judgement

    ``body_format`` records which skeleton definition the joint order belongs
    to (``"zed_body_34"``, ``"mock_16"``, ...). It must travel with the data:
    the joint order is meaningless without it.
    """

    tracking_id: int
    tracking_state: TrackingState
    body_format: str
    joint_positions_xyz: np.ndarray
    joint_confidences: np.ndarray
    joint_orientations: Optional[np.ndarray] = None
    root_position: Optional[np.ndarray] = None
    root_orientation: Optional[np.ndarray] = None
    body_confidence: float = float("nan")
    joint_positions_2d: Optional[np.ndarray] = None
    joint_position_covariances: Optional[np.ndarray] = None
    local_joint_positions_xyz: Optional[np.ndarray] = None
    tracker_root_velocity_xyz: Optional[np.ndarray] = None
    root_position_covariance: Optional[np.ndarray] = None
    action_state: BodyActionState = BodyActionState.UNKNOWN

    #: Optional per-joint arrays: attribute name -> trailing dimension.
    _PER_JOINT_OPTIONAL: ClassVar[tuple[tuple[str, int], ...]] = (
        ("joint_orientations", 4),
        ("joint_positions_2d", 2),
        ("joint_position_covariances", 6),
        ("local_joint_positions_xyz", 3),
    )
    #: Optional per-body vectors: attribute name -> length.
    _PER_BODY_OPTIONAL: ClassVar[tuple[tuple[str, int], ...]] = (
        ("root_position", 3),
        ("root_orientation", 4),
        ("tracker_root_velocity_xyz", 3),
        ("root_position_covariance", 6),
    )

    def __post_init__(self) -> None:
        pos = np.asarray(self.joint_positions_xyz, dtype=np.float32)
        if pos.ndim != 2 or pos.shape[1] != 3:
            raise ValidationError(
                f"joint_positions_xyz [J, 3] olmalı, gelen: {pos.shape}",
                field="joint_positions_xyz",
                code="joint_shape_invalid",
            )
        if pos.shape[0] == 0:
            raise ValidationError(
                "Bir iskelet en az bir eklem içermelidir.",
                field="joint_positions_xyz",
                code="joint_count_zero",
            )
        self.joint_positions_xyz = pos
        joints = pos.shape[0]

        conf = np.asarray(self.joint_confidences, dtype=np.float32)
        if conf.shape != (joints,):
            raise ValidationError(
                f"joint_confidences [{joints}] olmalı, gelen: {conf.shape}",
                field="joint_confidences",
                code="confidence_shape_invalid",
            )
        self.joint_confidences = conf

        for name, width in self._PER_JOINT_OPTIONAL:
            self._coerce(name, (joints, width))
        for name, width in self._PER_BODY_OPTIONAL:
            self._coerce(name, (width,))

        if isinstance(self.tracking_state, str):
            self.tracking_state = TrackingState(self.tracking_state)
        self.action_state = BodyActionState.parse(self.action_state)

    def _coerce(self, name: str, shape: tuple[int, ...]) -> None:
        """Validate one optional array in place, or leave it ``None``.

        A wrong shape is an error, not something to reshape around: silently
        reinterpreting a tracker array would re-index every joint in it.
        """
        value = getattr(self, name)
        if value is None:
            return
        array = np.asarray(value, dtype=np.float32)
        if array.shape != shape:
            raise ValidationError(
                f"{name} {list(shape)} olmalı, gelen: {array.shape}",
                field=name,
                code=f"{name}_shape_invalid",
            )
        setattr(self, name, array)

    @property
    def num_joints(self) -> int:
        return int(self.joint_positions_xyz.shape[0])

    @property
    def valid_joint_mask(self) -> np.ndarray:
        """Boolean ``[J]`` mask of joints with fully finite coordinates."""
        return np.isfinite(self.joint_positions_xyz).all(axis=1)

    @property
    def valid_joint_ratio(self) -> float:
        """Fraction of joints with usable coordinates (0..1)."""
        return float(self.valid_joint_mask.mean())

    def mean_confidence(self) -> float:
        """Mean of the finite confidences, or NaN when none are known."""
        finite = self.joint_confidences[np.isfinite(self.joint_confidences)]
        return float(finite.mean()) if finite.size else float("nan")

    def available_fields(self) -> tuple[str, ...]:
        """Names of the optional tracker fields this body actually carries."""
        names = [
            name
            for name, _ in (*self._PER_JOINT_OPTIONAL, *self._PER_BODY_OPTIONAL)
            if getattr(self, name) is not None
        ]
        if self.action_state is not BodyActionState.UNKNOWN:
            names.append("action_state")
        return tuple(sorted(names))

    def to_record(self) -> dict[str, Any]:
        """Compact JSON projection used by the per-frame skeleton sidecar.

        Coordinates are rounded to millimetre-scale precision (5 decimals in
        metres) purely to keep the sidecar small; that is a storage decision on
        already-raw values, not a normalisation of them. Non-finite values
        become ``null`` so a missing joint stays missing after a round trip.

        Optional fields are written only when present, so a take recorded
        without them is exactly as small as it was before they existed.
        """

        def _clean(values: np.ndarray, decimals: int) -> list[Any]:
            rounded = np.round(values.astype(np.float64), decimals)
            return [None if not np.isfinite(v) else float(v) for v in rounded.ravel()]

        def _rows(values: np.ndarray, decimals: int) -> list[list[Any]]:
            return [_clean(values[i], decimals) for i in range(values.shape[0])]

        record: dict[str, Any] = {
            "id": int(self.tracking_id),
            "state": self.tracking_state.value,
            "format": self.body_format,
            "joints": _rows(self.joint_positions_xyz, 5),
            "conf": _clean(self.joint_confidences, 4),
        }
        if np.isfinite(self.body_confidence):
            record["body_conf"] = round(float(self.body_confidence), 3)
        if self.root_position is not None:
            record["root"] = _clean(self.root_position, 5)
        if self.joint_orientations is not None:
            record["quat"] = _rows(self.joint_orientations, 5)
        if self.root_orientation is not None:
            record["rquat"] = _clean(self.root_orientation, 5)
        if self.tracker_root_velocity_xyz is not None:
            record["rvel"] = _clean(self.tracker_root_velocity_xyz, 5)
        if self.root_position_covariance is not None:
            record["rcov"] = _clean(self.root_position_covariance, 7)
        if self.joint_positions_2d is not None:
            record["kp2d"] = _rows(self.joint_positions_2d, 2)
        if self.joint_position_covariances is not None:
            record["kpcov"] = _rows(self.joint_position_covariances, 7)
        if self.local_joint_positions_xyz is not None:
            record["ljoints"] = _rows(self.local_joint_positions_xyz, 5)
        if self.action_state is not BodyActionState.UNKNOWN:
            record["action"] = self.action_state.value
        return record

    @classmethod
    def from_record(cls, payload: Mapping[str, Any]) -> "BodyPose":
        """Inverse of :meth:`to_record`. ``null`` becomes NaN again.

        A record written by an older version simply has fewer keys; nothing is
        migrated and nothing is invented for the fields it never carried.
        """

        def _to_array(values: Any, shape: tuple[int, ...]) -> np.ndarray:
            flat = [np.nan if v is None else float(v) for v in np.ravel(values).tolist()]
            return np.asarray(flat, dtype=np.float32).reshape(shape)

        def _optional(key: str, shape: tuple[int, ...]) -> Optional[np.ndarray]:
            raw = payload.get(key)
            if raw is None:
                return None
            try:
                return _to_array(raw, shape)
            except ValueError:
                # A record whose stored shape disagrees with the joint count is
                # unusable; dropping the field keeps the rest of the frame.
                return None

        joints = payload.get("joints") or []
        num_joints = len(joints)
        positions = _to_array(joints, (num_joints, 3))
        confidences = _to_array(payload.get("conf") or [], (num_joints,))
        return cls(
            tracking_id=int(payload.get("id", 0)),
            tracking_state=TrackingState(payload.get("state", TrackingState.OK.value)),
            body_format=str(payload.get("format", "unknown")),
            joint_positions_xyz=positions,
            joint_confidences=confidences,
            joint_orientations=_optional("quat", (num_joints, 4)),
            root_position=_optional("root", (3,)),
            root_orientation=_optional("rquat", (4,)),
            body_confidence=float(payload.get("body_conf", float("nan"))),
            joint_positions_2d=_optional("kp2d", (num_joints, 2)),
            joint_position_covariances=_optional("kpcov", (num_joints, 6)),
            local_joint_positions_xyz=_optional("ljoints", (num_joints, 3)),
            tracker_root_velocity_xyz=_optional("rvel", (3,)),
            root_position_covariance=_optional("rcov", (6,)),
            action_state=BodyActionState.parse(payload.get("action")),
        )


@dataclass
class FramePacket:
    """Everything one captured frame carries through the pipeline.

    Shapes:
        ``color_frame`` uint8 ``[H, W, 3]`` in RGB order
        ``depth_frame`` float32 ``[H, W]`` in the camera's length unit
        (optional; non-finite entries mark pixels with no depth)
    """

    frame_index: int
    host_timestamp_ns: int
    camera_timestamp_ns: int
    color_frame: np.ndarray
    depth_frame: Optional[np.ndarray] = None
    bodies: tuple[BodyPose, ...] = ()
    capture_status: CaptureStatus = CaptureStatus.OK
    origin: DataOrigin = DataOrigin.REAL
    backend_dropped_frames: int = 0
    take_id: Optional[str] = None
    session_id: Optional[str] = None

    def __post_init__(self) -> None:
        color = np.asarray(self.color_frame)
        if color.ndim != 3 or color.shape[2] != 3:
            raise ValidationError(
                f"color_frame [H, W, 3] olmalı, gelen: {color.shape}",
                field="color_frame",
                code="color_shape_invalid",
            )
        if color.dtype != np.uint8:
            color = color.astype(np.uint8)
        self.color_frame = color

        if self.depth_frame is not None:
            depth = np.asarray(self.depth_frame, dtype=np.float32)
            if depth.ndim != 2:
                raise ValidationError(
                    f"depth_frame [H, W] olmalı, gelen: {depth.shape}",
                    field="depth_frame",
                    code="depth_shape_invalid",
                )
            if depth.shape != color.shape[:2]:
                raise ValidationError(
                    "depth_frame çözünürlüğü color_frame ile uyuşmuyor: "
                    f"{depth.shape} != {color.shape[:2]}",
                    field="depth_frame",
                    code="depth_resolution_mismatch",
                )
            self.depth_frame = depth

        if self.frame_index < 0:
            raise ValidationError(
                f"frame_index negatif olamaz: {self.frame_index}",
                field="frame_index",
                code="frame_index_invalid",
            )
        self.bodies = tuple(self.bodies)

    @property
    def resolution(self) -> tuple[int, int]:
        """``(width, height)`` of the colour image."""
        return int(self.color_frame.shape[1]), int(self.color_frame.shape[0])

    @property
    def is_synthetic(self) -> bool:
        return self.origin is DataOrigin.SYNTHETIC

    def body_by_id(self, tracking_id: int) -> Optional[BodyPose]:
        for body in self.bodies:
            if body.tracking_id == tracking_id:
                return body
        return None

    def primary_body(self, preferred_id: Optional[int] = None) -> Optional[BodyPose]:
        """The body the UI should follow.

        ``preferred_id`` wins when it is still present. Otherwise the body with
        the most usable joints is chosen - and the caller is expected to record
        that the active identity changed rather than switching silently.
        """
        if preferred_id is not None:
            match = self.body_by_id(preferred_id)
            if match is not None:
                return match
        if not self.bodies:
            return None
        return max(self.bodies, key=lambda b: (b.valid_joint_ratio, -b.tracking_id))


@dataclass
class CaptureStatistics:
    """Observable health of the live capture path.

    Preview and capture are counted separately on purpose: dropping a preview
    frame to keep the GUI responsive is acceptable, losing a recorded frame is
    not, and one number cannot honestly represent both.
    """

    frames_acquired: int = 0
    preview_frames_delivered: int = 0
    preview_frames_dropped: int = 0
    recorded_frames_written: int = 0
    recording_frames_dropped: int = 0
    backend_dropped_frames: int = 0
    acquisition_fps: float = 0.0
    preview_fps: float = 0.0
    last_latency_ms: float = 0.0

    def reset(self) -> None:
        for name, value in self.__class__().__dict__.items():
            setattr(self, name, value)

    @property
    def has_capture_loss(self) -> bool:
        """True when data that should have been recorded was not."""
        return self.recording_frames_dropped > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frames_acquired": self.frames_acquired,
            "preview_frames_delivered": self.preview_frames_delivered,
            "preview_frames_dropped": self.preview_frames_dropped,
            "recorded_frames_written": self.recorded_frames_written,
            "recording_frames_dropped": self.recording_frames_dropped,
            "backend_dropped_frames": self.backend_dropped_frames,
            "acquisition_fps": round(self.acquisition_fps, 2),
            "preview_fps": round(self.preview_fps, 2),
            "last_latency_ms": round(self.last_latency_ms, 2),
        }


__all__ = [
    "BodyPose",
    "CameraInfo",
    "CaptureStatistics",
    "FramePacket",
]
