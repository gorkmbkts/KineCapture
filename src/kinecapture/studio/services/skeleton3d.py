"""The geometry behind the 3D skeleton view. No Qt, no OpenGL.

Everything here is arithmetic on arrays: where the camera is, what it looks
at, and which line segments make up a pose. The widget that draws it owns a
GL context and nothing else, so the part that can be wrong in a way a person
would notice is the part that can be tested without a screen.

Two rules carry over from the rest of the labelling screen:

* **A joint the tracker did not produce is not a point at the origin.** Bones
  with a missing end are dropped, not drawn to (0, 0, 0), which would show a
  limb collapsing into the floor every time tracking dropped a frame.
* **The up axis is read, not assumed.** The recording says which convention
  it used; a viewer that always assumed Y-up would lay a Z-up capture on its
  side and make every judgement about depth or lean wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Optional, Sequence

import numpy as np

#: Coordinate systems this viewer knows how to orient, and which array index
#: points away from the floor in each.
UP_AXIS = {
    "right_handed_y_up": 1,
    "left_handed_y_up": 1,
    "right_handed_z_up": 2,
    "left_handed_z_up": 2,
    "right_handed_z_up_x_fwd": 2,
}
DEFAULT_UP_AXIS = 1

#: Limits on the orbit. Elevation stops just short of the poles because the
#: view direction and the up vector become parallel there and the camera flips.
MIN_ELEVATION = -math.pi / 2 + 0.01
MAX_ELEVATION = math.pi / 2 - 0.01
MIN_DISTANCE = 0.15
MAX_DISTANCE = 60.0


def up_axis_for(coordinate_system: str) -> int:
    """Which component is "up" for a recording's coordinate system."""
    return UP_AXIS.get((coordinate_system or "").strip().lower(), DEFAULT_UP_AXIS)


@dataclass(frozen=True)
class OrbitCamera:
    """Where the viewer stands. Persistent: the angle survives scrubbing.

    Angles rather than a free matrix, because the useful thing is "walk around
    the athlete", and an orbit cannot get into a state a person cannot get out
    of - no accumulated drift, no upside down.
    """

    azimuth: float = math.radians(35.0)
    elevation: float = math.radians(15.0)
    distance: float = 3.2
    target: tuple[float, float, float] = (0.0, 1.0, 0.0)
    up_axis: int = DEFAULT_UP_AXIS
    fov_deg: float = 45.0
    near: float = 0.05
    far: float = 200.0

    # ------------------------------------------------------------ movement
    def orbit(self, d_azimuth: float, d_elevation: float) -> "OrbitCamera":
        return replace(
            self,
            azimuth=(self.azimuth + d_azimuth) % (2 * math.pi),
            elevation=min(MAX_ELEVATION, max(MIN_ELEVATION, self.elevation + d_elevation)),
        )

    def zoom(self, factor: float) -> "OrbitCamera":
        return replace(
            self,
            distance=min(MAX_DISTANCE, max(MIN_DISTANCE, self.distance * float(factor))),
        )

    def pan(self, dx: float, dy: float) -> "OrbitCamera":
        """Slide the target across the screen plane, scaled by distance.

        Scaled so a drag moves the picture by the same amount however far away
        the camera is; panning that crawls when zoomed out feels broken.
        """
        right, up = self._screen_axes()
        step = self.distance * 0.0025
        target = np.asarray(self.target, dtype=np.float64)
        target = target + right * (-dx * step) + up * (dy * step)
        return replace(self, target=(float(target[0]), float(target[1]), float(target[2])))

    def looking_at(self, target: Sequence[float], distance: float) -> "OrbitCamera":
        return replace(
            self,
            target=(float(target[0]), float(target[1]), float(target[2])),
            distance=min(MAX_DISTANCE, max(MIN_DISTANCE, float(distance))),
        )

    # ------------------------------------------------------------ geometry
    @property
    def up(self) -> np.ndarray:
        vector = np.zeros(3, dtype=np.float64)
        vector[self.up_axis] = 1.0
        return vector

    @property
    def eye(self) -> np.ndarray:
        """Camera position, from the orbit angles around the target."""
        # Two axes span the ground plane; the third is up. Naming them this way
        # keeps one formula for every supported coordinate system.
        up = self.up_axis
        a, b = [i for i in (0, 1, 2) if i != up]
        offset = np.zeros(3, dtype=np.float64)
        horizontal = self.distance * math.cos(self.elevation)
        offset[a] = horizontal * math.cos(self.azimuth)
        offset[b] = horizontal * math.sin(self.azimuth)
        offset[up] = self.distance * math.sin(self.elevation)
        return np.asarray(self.target, dtype=np.float64) + offset

    def _screen_axes(self) -> tuple[np.ndarray, np.ndarray]:
        forward = np.asarray(self.target, dtype=np.float64) - self.eye
        forward = _normalise(forward)
        right = _normalise(np.cross(forward, self.up))
        return right, _normalise(np.cross(right, forward))

    def view_matrix(self) -> np.ndarray:
        """Column-major 4x4, ready for OpenGL."""
        eye = self.eye
        forward = _normalise(np.asarray(self.target, dtype=np.float64) - eye)
        right = _normalise(np.cross(forward, self.up))
        true_up = np.cross(right, forward)

        matrix = np.eye(4, dtype=np.float32)
        matrix[0, :3] = right
        matrix[1, :3] = true_up
        matrix[2, :3] = -forward
        matrix[0, 3] = -float(np.dot(right, eye))
        matrix[1, 3] = -float(np.dot(true_up, eye))
        matrix[2, 3] = float(np.dot(forward, eye))
        return matrix

    def projection_matrix(self, aspect: float) -> np.ndarray:
        aspect = max(1e-3, float(aspect))
        f = 1.0 / math.tan(math.radians(self.fov_deg) / 2.0)
        matrix = np.zeros((4, 4), dtype=np.float32)
        matrix[0, 0] = f / aspect
        matrix[1, 1] = f
        matrix[2, 2] = (self.far + self.near) / (self.near - self.far)
        matrix[2, 3] = (2.0 * self.far * self.near) / (self.near - self.far)
        matrix[3, 2] = -1.0
        return matrix

    def matrix(self, aspect: float) -> np.ndarray:
        return self.projection_matrix(aspect) @ self.view_matrix()

    # ------------------------------------------------------------- storage
    def to_dict(self) -> dict[str, float]:
        return {
            "azimuth": self.azimuth,
            "elevation": self.elevation,
            "distance": self.distance,
            "target": list(self.target),
            "up_axis": self.up_axis,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "OrbitCamera":
        target = payload.get("target") or (0.0, 1.0, 0.0)
        return cls(
            azimuth=float(payload.get("azimuth", math.radians(35.0))),
            elevation=float(payload.get("elevation", math.radians(15.0))),
            distance=float(payload.get("distance", 3.2)),
            target=(float(target[0]), float(target[1]), float(target[2])),
            up_axis=int(payload.get("up_axis", DEFAULT_UP_AXIS)),
        )


def _normalise(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector / length if length > 1e-9 else np.array([0.0, 0.0, 1.0])


def frame_subject(
    joints: Optional[np.ndarray], up_axis: int = DEFAULT_UP_AXIS
) -> Optional[tuple[tuple[float, float, float], float]]:
    """Where to point the camera so the whole person fits, or ``None``.

    ``joints`` may be one frame ``[J, 3]`` or a window ``[T, J, 3]``; a window
    is better, because framing on a single frame makes the view jump whenever
    the athlete moves. NaN is ignored rather than dragging the box to zero.
    """
    if joints is None:
        return None
    points = np.asarray(joints, dtype=np.float64).reshape(-1, 3)
    finite = points[np.isfinite(points).all(axis=1)]
    if finite.size == 0:
        return None
    low = finite.min(axis=0)
    high = finite.max(axis=0)
    centre = (low + high) / 2.0
    extent = float(np.max(high - low))
    # A little over twice the subject's size: the person fills the frame with
    # enough room that a raised arm does not leave it.
    distance = max(MIN_DISTANCE, min(MAX_DISTANCE, extent * 2.2 + 0.5))
    return (float(centre[0]), float(centre[1]), float(centre[2])), distance


def bone_segments(
    joints: Optional[np.ndarray], bones: Sequence[tuple[int, int]]
) -> np.ndarray:
    """``[N, 2, 3]`` line endpoints for the bones that are actually known.

    A bone with a missing end is left out. Drawing it to the origin would be
    the 3D version of the lie this project refuses everywhere else.
    """
    if joints is None or not len(bones):
        return np.zeros((0, 2, 3), dtype=np.float32)
    points = np.asarray(joints, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        return np.zeros((0, 2, 3), dtype=np.float32)
    valid = np.isfinite(points).all(axis=1)
    pairs = np.asarray(bones, dtype=np.int64).reshape(-1, 2)
    inside = (pairs >= 0).all(axis=1) & (pairs < len(points)).all(axis=1)
    pairs = pairs[inside]
    if pairs.size == 0:
        return np.zeros((0, 2, 3), dtype=np.float32)
    usable = valid[pairs[:, 0]] & valid[pairs[:, 1]]
    pairs = pairs[usable]
    if pairs.size == 0:
        return np.zeros((0, 2, 3), dtype=np.float32)
    return np.stack((points[pairs[:, 0]], points[pairs[:, 1]]), axis=1)


def joint_points(joints: Optional[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """The joints that exist, and their indices in the original array."""
    if joints is None:
        return np.zeros((0, 3), dtype=np.float32), np.zeros(0, dtype=np.int64)
    points = np.asarray(joints, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        return np.zeros((0, 3), dtype=np.float32), np.zeros(0, dtype=np.int64)
    valid = np.isfinite(points).all(axis=1)
    return points[valid], np.nonzero(valid)[0]


def ground_grid(
    up_axis: int = DEFAULT_UP_AXIS,
    *,
    half_extent: float = 3.0,
    step: float = 0.5,
    height: float = 0.0,
) -> np.ndarray:
    """``[N, 2, 3]`` line endpoints for a floor grid.

    Without a floor there is no way to tell a lean from a camera angle: a
    skeleton alone in space has no scale and no horizon.
    """
    ticks = np.arange(-half_extent, half_extent + step * 0.5, step, dtype=np.float32)
    a, b = [i for i in (0, 1, 2) if i != up_axis]
    lines = np.zeros((len(ticks) * 2, 2, 3), dtype=np.float32)
    for index, value in enumerate(ticks):
        first = lines[index]
        first[0, a] = value
        first[1, a] = value
        first[0, b] = -half_extent
        first[1, b] = half_extent
        second = lines[len(ticks) + index]
        second[0, b] = value
        second[1, b] = value
        second[0, a] = -half_extent
        second[1, a] = half_extent
    lines[:, :, up_axis] = height
    return lines


__all__ = [
    "DEFAULT_UP_AXIS",
    "MAX_DISTANCE",
    "MIN_DISTANCE",
    "OrbitCamera",
    "UP_AXIS",
    "bone_segments",
    "frame_subject",
    "ground_grid",
    "joint_points",
    "up_axis_for",
]
