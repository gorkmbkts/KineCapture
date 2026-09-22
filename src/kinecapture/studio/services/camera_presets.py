"""Named viewpoints, and how the camera travels between them. No Qt.

A preset is a direction, not a position: "ön" means looking at the athlete's
front, whatever the recording's coordinate convention is and wherever the
athlete has walked to. The reference the directions are measured from is
established **once**, from the recording, and does not move afterwards. A
"front" re-derived every frame from the current pose would drift as the person
turned, and every preset would mean something slightly different each time it
was pressed.

The transition is over **time**, not frames: PRESET-02 asks for about 1.5
seconds regardless of how far the camera has to go, so a 20-degree change is a
slow, small move and a 170-degree one is a fast, large one - both finished at
the same moment. It takes the short way round, so 350 degrees to 10 is a
20-degree turn and not a 340-degree one, and eases in and out so it does not
start or stop abruptly.

Nothing here touches a measurement. The camera is a way of looking at the
joints; it never changes one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from .skeleton3d import MAX_ELEVATION, MIN_ELEVATION, OrbitCamera


@dataclass(frozen=True)
class Preset:
    """One named direction, as an offset from the recording's own front."""

    key: str
    label: str
    #: Degrees anticlockwise from the reference front, seen from above.
    azimuth_offset: float
    #: Degrees above the horizon.
    elevation: float
    #: What the button says it does, for a tooltip and a screen reader.
    description: str = ""
    #: What a cramped main strip calls it. Defaults to :attr:`label`.
    short_label: str = ""
    #: Whether the offset is measured from the athlete's own front. False for
    #: the recording's direction, which is a fact about the camera and has to
    #: be given its own angle rather than inheriting the anatomical one.
    anatomical: bool = True


#: The seven directions the design review asked for, plus the recording's own.
#: Order is the order they are offered in.
PRESETS: tuple[Preset, ...] = (
    Preset("front", "Ön", 0.0, 8.0, "Sporcunun önünden"),
    Preset("front_right", "Ön-sağ 45°", -45.0, 8.0, "Önden sağ çapraz", short_label="45°"),
    Preset("right", "Sağ", -90.0, 8.0, "Sporcunun sağından"),
    Preset("back", "Arka", 180.0, 8.0, "Sporcunun arkasından"),
    Preset("left", "Sol", 90.0, 8.0, "Sporcunun solundan"),
    Preset("front_left", "Ön-sol 45°", 45.0, 8.0, "Önden sol çapraz"),
    # Straight down, not "nearly". The 78 degrees this used to be was the
    # pole dodge, and calling that "Üst" was the interface asserting something
    # the view did not show.
    Preset("top", "Üst", 0.0, 90.0, "Tam tepeden"),
    # Measured from the recording's camera, not from the athlete. Its
    # `azimuth_offset` is unused; `absolute_azimuth` on the call is what
    # places it, and with no known convention the button is not offered.
    Preset(
        "camera", "Kayıt yönü", 0.0, 8.0, "Kaydın kendi kamera yönü",
        anatomical=False,
    ),
)

PRESETS_BY_KEY = {preset.key: preset for preset in PRESETS}

#: The five the main panel offers. Eight buttons filled two thirds of a strip
#: whose height is the scarce direction, and five of the eight were pressed
#: rarely enough that being one menu away costs nothing.
PRIMARY_PRESET_KEYS: tuple[str, ...] = (
    "front",
    "right",
    "left",
    "top",
    "front_right",
)

#: The rest. Reachable, in a menu on the same row, in the same order as above.
SECONDARY_PRESET_KEYS: tuple[str, ...] = tuple(
    preset.key for preset in PRESETS if preset.key not in PRIMARY_PRESET_KEYS
)


def preset_label(preset: Preset, *, short: bool = False) -> str:
    return (preset.short_label or preset.label) if short else preset.label

#: How long a transition takes, in seconds. Time, never frames: the same
#: journey must take the same wall-clock time on a fast machine and a slow one.
TRANSITION_SECONDS = 1.5


def shortest_turn(from_azimuth: float, to_azimuth: float) -> float:
    """The signed turn, in radians, taking the short way round.

    350 degrees to 10 degrees is +20, not -340. Without this a preset on the
    far side of the wrap sends the camera the long way round the athlete,
    which reads as the interface having misunderstood the click.
    """
    difference = (float(to_azimuth) - float(from_azimuth)) % (2 * math.pi)
    if difference > math.pi:
        difference -= 2 * math.pi
    return difference


def ease(t: float) -> float:
    """Smooth start, smooth stop. ``t`` and the result are both 0..1."""
    t = min(1.0, max(0.0, float(t)))
    # Smoothstep. Continuous in value and in slope at both ends, which is what
    # stops a transition looking like it was cut off.
    return t * t * (3.0 - 2.0 * t)


@dataclass(frozen=True)
class CameraTransition:
    """A camera journey in progress.

    Sampled by elapsed time. It holds where it started, so a new preset chosen
    mid-flight starts from **where the camera actually is** rather than from
    where the interrupted journey was heading - no queue, no teleport.
    """

    start: OrbitCamera
    target_azimuth: float
    target_elevation: float
    target_distance: float
    target_point: tuple[float, float, float]
    duration: float = TRANSITION_SECONDS

    @classmethod
    def to_camera(
        cls,
        current: OrbitCamera,
        destination: OrbitCamera,
        *,
        duration: float = TRANSITION_SECONDS,
    ) -> "CameraTransition":
        return cls(
            start=current,
            target_azimuth=destination.azimuth,
            target_elevation=destination.elevation,
            target_distance=destination.distance,
            target_point=destination.target,
            duration=max(1e-3, float(duration)),
        )

    def at(self, elapsed: float) -> OrbitCamera:
        """The camera ``elapsed`` seconds in. Clamped at both ends."""
        fraction = ease(float(elapsed) / self.duration)
        turn = shortest_turn(self.start.azimuth, self.target_azimuth)
        azimuth = (self.start.azimuth + turn * fraction) % (2 * math.pi)
        elevation = self.start.elevation + (
            self.target_elevation - self.start.elevation
        ) * fraction
        distance = self.start.distance + (
            self.target_distance - self.start.distance
        ) * fraction
        point = tuple(
            a + (b - a) * fraction
            for a, b in zip(self.start.target, self.target_point)
        )
        return self.start.looking_at(point, distance).__class__(
            azimuth=azimuth,
            elevation=min(MAX_ELEVATION, max(MIN_ELEVATION, elevation)),
            distance=distance,
            target=(float(point[0]), float(point[1]), float(point[2])),
            up_axis=self.start.up_axis,
            fov_deg=self.start.fov_deg,
            near=self.start.near,
            far=self.start.far,
        )

    def finished(self, elapsed: float) -> bool:
        return float(elapsed) >= self.duration


def turn_sense(up_axis: int) -> float:
    """Which way the camera's own azimuth turns, seen from above the athlete.

    ``OrbitCamera`` parameterises the ground plane as the two axes that are
    not "up", taken in ascending index order, with the eye at
    ``(cos a, sin a)``. Whether increasing that angle walks anticlockwise or
    clockwise **as seen from above** depends on whether that ordering is
    right-handed, and it is not the same for every up axis::

        up = x -> (y, z, x)   y x z = +x   right-handed   -> +1
        up = y -> (x, z, y)   x x z = -y   left-handed    -> -1
        up = z -> (x, y, z)   x x y = +z   right-handed   -> +1

    So a preset offset stated once, in the athlete's terms, has to be turned
    into this camera's terms before it is used. Without it the side presets
    mirror: with a y-up recording - which is what the ZED produces - "Sağ"
    stood beside the athlete's *left* shoulder. Nothing looked broken, because
    the view really did move ninety degrees; it moved to the wrong side.

    Returned as the determinant of the basis rather than a table, so it stays
    correct if another coordinate system is added.
    """
    up = int(up_axis) % 3
    a, b = [i for i in (0, 1, 2) if i != up]
    basis = [[0.0] * 3 for _ in range(3)]
    basis[0][a] = basis[1][b] = basis[2][up] = 1.0
    # 3x3 determinant, written out: +1 for a right-handed ordering, -1 for a
    # left-handed one.
    determinant = (
        basis[0][0] * (basis[1][1] * basis[2][2] - basis[1][2] * basis[2][1])
        - basis[0][1] * (basis[1][0] * basis[2][2] - basis[1][2] * basis[2][0])
        + basis[0][2] * (basis[1][0] * basis[2][1] - basis[1][1] * basis[2][0])
    )
    return 1.0 if determinant >= 0 else -1.0


def camera_for_preset(
    preset: Preset,
    current: OrbitCamera,
    *,
    reference_azimuth: float,
    absolute_azimuth: Optional[float] = None,
    target: Optional[Sequence[float]] = None,
    distance: Optional[float] = None,
) -> OrbitCamera:
    """Where ``preset`` puts the camera, measured from a fixed reference.

    ``reference_azimuth`` is the recording's own front, established once. The
    preset is an offset from it, so "ön" stays the same direction for the whole
    session however the athlete moves.

    The offset is stated anticlockwise from above, in the athlete's own terms;
    :func:`turn_sense` converts it into the direction this camera's azimuth
    actually turns for the recording's up axis.
    """
    if preset.anatomical or absolute_azimuth is None:
        offset = math.radians(preset.azimuth_offset) * turn_sense(current.up_axis)
        azimuth = (reference_azimuth + offset) % (2 * math.pi)
    else:
        azimuth = float(absolute_azimuth) % (2 * math.pi)
    elevation = min(
        MAX_ELEVATION, max(MIN_ELEVATION, math.radians(preset.elevation))
    )
    point = tuple(target) if target is not None else current.target
    return current.__class__(
        azimuth=azimuth,
        elevation=elevation,
        distance=float(distance if distance is not None else current.distance),
        target=(float(point[0]), float(point[1]), float(point[2])),
        up_axis=current.up_axis,
        fov_deg=current.fov_deg,
        near=current.near,
        far=current.far,
    )


__all__ = [
    "CameraTransition",
    "turn_sense",
    "PRESETS",
    "PRESETS_BY_KEY",
    "Preset",
    "TRANSITION_SECONDS",
    "camera_for_preset",
    "ease",
    "shortest_turn",
]
