"""The floor plane, found once during offline processing.

A skeleton alone in space has no horizon. Without a floor there is no way to
tell a lean from a camera angle, and no way to say whether a jump left the
ground - so the labelling screen draws one. The question this module answers
is *which* floor: the one the sensor measured, or a line drawn under the
lowest foot.

Those are different claims and this project keeps them apart.

* ``detected`` - the ZED SDK's own plane, from depth. A measurement.
* ``visual_reference`` - the grid the viewer draws when there is no plane,
  placed under the athlete so the scene has a horizon. A drawing aid, and
  labelled as one wherever it is shown.
* ``not_found`` - detection ran and did not succeed, with the reason kept.

Detection happens **offline, once**, while the version is being produced, and
what is stored is a plane equation and the reference it is expressed in - not
a point cloud and not a mesh. The labelling screen never runs the SDK: it
reads four numbers.

Verified on this machine, 19 September 2026: ``find_floor_plane`` returned
``SUCCESS`` on the first frame of ``take_20260917T220755_c97c`` in 0.28 s, with
a ``HORIZONTAL`` plane whose height at the athlete's feet agreed with the
lowest measured foot position to within 2 cm.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

#: Schema of the ``floor_plane`` block written into a processing run.
#: 1.0.0 carries the plane equation, the normal, a point on the plane, the
#: reference space and how it was found. Additive to ``job.json``: a reader
#: that does not know about it is unaffected, and a run produced before this
#: existed simply has no block, which reads as "nothing was measured".
FLOOR_SCHEMA_VERSION = "1.0.0"

#: What a stored floor is allowed to claim.
DETECTED = "detected"
NOT_FOUND = "not_found"
NOT_ATTEMPTED = "not_attempted"

#: The space a plane is expressed in. A plane in camera space is only a world
#: floor while the camera is still; a moving recording needs the per-frame
#: poses as well, and without them the plane must not be presented as one.
CAMERA_SPACE = "camera_at_detection_frame"


@dataclass(frozen=True)
class FloorPlane:
    """One measured floor, and everything needed to read it back honestly."""

    status: str = NOT_ATTEMPTED
    #: ``(a, b, c, d)`` of ``ax + by + cz + d = 0``, in ``reference_space``.
    equation: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    #: Unit normal. Points away from the floor, i.e. towards the athlete.
    normal: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: A point on the plane, which is what a viewer needs to place a grid.
    point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: Which frame of the *source* it was found on, so it can be checked.
    source_position: Optional[int] = None
    #: The recording's own convention, copied so a reader never has to guess.
    coordinate_system: str = ""
    length_unit: str = ""
    reference_space: str = CAMERA_SPACE
    #: True when the camera moved during the recording. A plane found in
    #: camera space is then not a world floor, and saying so is the point.
    camera_moved: Optional[bool] = None
    #: Why, when it did not work. Empty on success.
    reason: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_measured(self) -> bool:
        return self.status == DETECTED

    def height_at(self, x: float, z: float, up_axis: int = 1) -> Optional[float]:
        """Where the plane sits above ``(x, z)``, or ``None``.

        Returns ``None`` for a plane that was never measured, and for one
        whose normal has no component along the up axis - a wall is a plane
        too, and solving it for a height would produce a number with no
        meaning.
        """
        if not self.is_measured:
            return None
        a, b, c, d = self.equation
        coefficients = (a, b, c)
        along_up = coefficients[up_axis]
        if abs(along_up) < 1e-6:
            return None
        others = [i for i in (0, 1, 2) if i != up_axis]
        values = {others[0]: float(x), others[1]: float(z)}
        total = d + sum(coefficients[i] * values[i] for i in others)
        return -total / along_up

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FLOOR_SCHEMA_VERSION,
            "status": self.status,
            "equation": [float(v) for v in self.equation],
            "normal": [float(v) for v in self.normal],
            "point": [float(v) for v in self.point],
            "source_position": self.source_position,
            "coordinate_system": self.coordinate_system,
            "length_unit": self.length_unit,
            "reference_space": self.reference_space,
            "camera_moved": self.camera_moved,
            "reason": self.reason,
            "extra": dict(self.extra),
            "note": (
                "ax + by + cz + d = 0 in reference_space. A plane in "
                "camera space is a world floor only while the camera is "
                "still; with a moving camera the per-frame poses are needed "
                "and this must not be presented as a world plane."
            ),
        }

    @classmethod
    def from_dict(cls, payload: Optional[Mapping[str, Any]]) -> "FloorPlane":
        """Read a stored block. A missing or damaged one is *not attempted*.

        Never an exception and never a guess: a run produced before this
        existed has no block, and that is a fact about the run rather than an
        error in reading it.
        """
        if not payload:
            return cls()
        try:
            equation = tuple(float(v) for v in payload.get("equation") or ())
            normal = tuple(float(v) for v in payload.get("normal") or ())
            point = tuple(float(v) for v in payload.get("point") or ())
            if len(equation) != 4 or len(normal) != 3 or len(point) != 3:
                raise ValueError("shape")
            position = payload.get("source_position")
            return cls(
                status=str(payload.get("status", NOT_ATTEMPTED)),
                equation=equation,  # type: ignore[arg-type]
                normal=normal,  # type: ignore[arg-type]
                point=point,  # type: ignore[arg-type]
                source_position=None if position is None else int(position),
                coordinate_system=str(payload.get("coordinate_system", "")),
                length_unit=str(payload.get("length_unit", "")),
                reference_space=str(payload.get("reference_space", CAMERA_SPACE)),
                camera_moved=payload.get("camera_moved"),
                reason=str(payload.get("reason", "")),
                extra=dict(payload.get("extra") or {}),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Zemin düzlemi bloğu okunamadı: %s", exc)
            return cls(status=NOT_ATTEMPTED, reason=f"okunamadı: {exc}")


def detect_floor(backend: Any, *, attempts: int = 1) -> FloorPlane:
    """Ask the camera for its floor plane. Never raises into a caller.

    Called from the offline pipeline with an already-connected ZED backend
    whose positional tracking is running - the SDK requires a tracking state
    of ``OK`` before it will answer, which is why this is not a static call.

    A backend that is not a ZED, or an SDK that declines, returns a plane that
    says so. Processing a recording must never fail because a viewing aid
    could not be computed.
    """
    try:
        camera = getattr(backend, "_camera", None)
    except Exception as exc:  # noqa: BLE001 - see docstring
        # ``getattr`` with a default only swallows AttributeError. A property
        # that raises anything else would otherwise fail a version that is
        # complete apart from a viewing aid.
        logger.info("Zemin düzlemi için kamera okunamadı: %s", exc)
        return FloorPlane(status=NOT_ATTEMPTED, reason=f"kamera okunamadı: {exc}")
    if camera is None:
        return FloorPlane(status=NOT_ATTEMPTED, reason="Bu kaynak ZED değil.")
    try:
        import pyzed.sl as sl
    except ImportError as exc:  # pragma: no cover - the pipeline imports it
        return FloorPlane(status=NOT_ATTEMPTED, reason=f"pyzed yok: {exc}")

    info = getattr(backend, "_info", None)
    extra = getattr(info, "extra", {}) if info is not None else {}
    profile = (extra or {}).get("effective_capture_profile") or {}
    plane = sl.Plane()
    transform = sl.Transform()
    last = ""
    for _ in range(max(1, int(attempts))):
        try:
            pose = sl.Pose()
            state = camera.get_position(pose)
            if state != sl.POSITIONAL_TRACKING_STATE.OK:
                last = f"konum takibi hazır değil: {state}"
                continue
            status = camera.find_floor_plane(plane, transform)
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.info("Zemin düzlemi aranamadı: %s", exc)
            return FloorPlane(status=NOT_FOUND, reason=str(exc))
        if status != sl.ERROR_CODE.SUCCESS:
            last = str(status)
            continue
        equation = [float(v) for v in plane.get_plane_equation()]
        normal = [float(v) for v in plane.get_normal()]
        centre = [float(v) for v in plane.get_center()]
        return FloorPlane(
            status=DETECTED,
            equation=(equation[0], equation[1], equation[2], equation[3]),
            normal=(normal[0], normal[1], normal[2]),
            point=(centre[0], centre[1], centre[2]),
            source_position=_svo_position(camera),
            coordinate_system=str(profile.get("coordinate_system", "")).lower(),
            length_unit=str(profile.get("length_unit", "")).lower(),
            reference_space=CAMERA_SPACE,
            extra={
                "plane_type": str(plane.type),
                "extents": [float(v) for v in plane.get_extents()],
                "sdk_version": (extra or {}).get("sdk_version", ""),
            },
        )
    return FloorPlane(
        status=NOT_FOUND,
        reason=last or "Zemin düzlemi bulunamadı.",
        coordinate_system=str(profile.get("coordinate_system", "")).lower(),
        length_unit=str(profile.get("length_unit", "")).lower(),
    )


def _svo_position(camera: Any) -> Optional[int]:
    try:
        return int(camera.get_svo_position())
    except Exception:  # noqa: BLE001 - a live camera has no SVO position
        return None


def camera_moved(poses: Sequence[Sequence[float]], tolerance: float = 0.02) -> bool:
    """Whether the camera translated by more than ``tolerance`` at any point.

    Used to decide whether a plane found in camera space may be described as a
    world floor. With no poses recorded the answer is unknown, and the caller
    is expected to store ``None`` rather than ``False``.
    """
    if not poses:
        return False
    first = poses[0]
    for pose in poses[1:]:
        if any(abs(float(a) - float(b)) > tolerance for a, b in zip(pose, first)):
            return True
    return False


__all__ = [
    "CAMERA_SPACE",
    "DETECTED",
    "FLOOR_SCHEMA_VERSION",
    "FloorPlane",
    "NOT_ATTEMPTED",
    "NOT_FOUND",
    "camera_moved",
    "detect_floor",
]
