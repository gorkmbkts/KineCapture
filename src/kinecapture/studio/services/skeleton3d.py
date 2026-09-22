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

#: Limits on the orbit. The poles themselves are reachable: the view keeps a
#: defined orientation there because `OrbitCamera._reference_up` tips its
#: reference over to a ground axis, so straight down is a view rather than a
#: degenerate matrix. A hair under a right angle so the two ground axes never
#: both vanish from the projection.
MIN_ELEVATION = -math.pi / 2 + 1e-4
MAX_ELEVATION = math.pi / 2 - 1e-4
MIN_DISTANCE = 0.15
MAX_DISTANCE = 60.0


#: Coordinate systems whose basis is left-handed. The athlete's facing is a
#: cross product, so its sign flips with the handedness of the basis; getting
#: this wrong puts "Ön" behind the athlete and swaps left with right.
LEFT_HANDED = frozenset({"left_handed_y_up", "left_handed_z_up"})

#: Where a reference front came from. Reported alongside the angle, because
#: "measured from the shoulders" and "assumed" are different claims and a
#: screen that shows one for the other is lying.
FACING_SHOULDERS = "shoulders"
FACING_HIPS = "hips"
FACING_MANUAL = "manual"
FACING_UNKNOWN = "unknown"

#: Below this, the two sides of the body are too close together in the ground
#: plane for their difference to point anywhere: a person seen exactly edge-on
#: by a noisy tracker, or a frame where both shoulders collapsed onto one
#: point. Metres, on the projected span.
MIN_SPAN_M = 0.06


def is_left_handed(coordinate_system: str) -> bool:
    return (coordinate_system or "").strip().lower() in LEFT_HANDED


def facing_azimuth(
    joints: Optional[np.ndarray],
    *,
    up_axis: int = DEFAULT_UP_AXIS,
    left_shoulder: Optional[int] = None,
    right_shoulder: Optional[int] = None,
    left_hip: Optional[int] = None,
    right_hip: Optional[int] = None,
    left_handed: bool = False,
) -> tuple[Optional[float], str]:
    """Which way the athlete is facing, as an orbit azimuth, and from what.

    The camera's own angle is *not* an answer to this question. It says where
    somebody last dragged the view to, which is why a remembered camera could
    silently redefine a different recording's front.

    The body does answer it. A person's facing is perpendicular to the line
    across their shoulders, in the ground plane::

        facing = normalise(cross(left_shoulder - right_shoulder, up))

    Checked against the convention this camera uses: with ``y`` up and a
    right-handed basis, an athlete facing ``+z`` has their left shoulder at
    ``+x``, and ``x x y = +z``. In a left-handed basis the same cross product
    points backwards, so the sign follows ``left_handed``.

    ``joints`` may be one pose ``[J, 3]`` or a window ``[N, J, 3]``; a window
    is averaged, which is what makes the answer stable rather than following
    the tracker's own noise frame by frame. NaN is skipped, never filled.

    Returns ``(azimuth, source)``. The azimuth is ``None`` when the body does
    not say - too few joints, all NaN, or the two sides too close together in
    the ground plane to point anywhere - and the source says which it was, so
    a caller can show an honest "belirsiz" rather than a confident wrong angle.
    """
    if joints is None:
        return None, FACING_UNKNOWN
    array = np.asarray(joints, dtype=np.float64)
    if array.ndim == 2:
        array = array[None, :, :]
    if array.ndim != 3 or array.shape[-1] != 3:
        return None, FACING_UNKNOWN

    up = int(up_axis) % 3
    ground = [i for i in (0, 1, 2) if i != up]

    def span(left: Optional[int], right: Optional[int]) -> Optional[np.ndarray]:
        """Mean left-minus-right vector over the window, or ``None``."""
        if left is None or right is None:
            return None
        count = array.shape[1]
        if not (0 <= int(left) < count and 0 <= int(right) < count):
            return None
        difference = array[:, int(left), :] - array[:, int(right), :]
        usable = difference[np.isfinite(difference).all(axis=1)]
        if usable.size == 0:
            return None
        mean = usable.mean(axis=0)
        # Only the ground-plane part matters: a shoulder line that is mostly
        # vertical - somebody lying down, or a bad frame - says nothing about
        # which way they face while standing.
        flat = np.zeros(3, dtype=np.float64)
        flat[ground[0]] = mean[ground[0]]
        flat[ground[1]] = mean[ground[1]]
        if float(np.hypot(flat[ground[0]], flat[ground[1]])) < MIN_SPAN_M:
            return None
        return flat

    for source, vector in (
        (FACING_SHOULDERS, span(left_shoulder, right_shoulder)),
        (FACING_HIPS, span(left_hip, right_hip)),
    ):
        if vector is None:
            continue
        up_vector = np.zeros(3, dtype=np.float64)
        up_vector[up] = 1.0
        facing = np.cross(vector, up_vector)
        if left_handed:
            facing = -facing
        length = float(np.linalg.norm(facing))
        if length <= 1e-9:
            continue
        facing /= length
        # The same (a, b) parameterisation `OrbitCamera.eye` uses, so the
        # angle can be handed straight to it as a reference.
        a, b = ground
        return float(math.atan2(facing[b], facing[a])) % (2 * math.pi), source

    return None, FACING_UNKNOWN


#: Which way the recording camera looks, per coordinate system, as a unit
#: vector in that system's own axes. The athlete is in front of the lens, so
#: the camera *stands* in the opposite direction from them - which is the
#: direction an orbit camera has to be placed to reproduce the recorded view.
CAMERA_FORWARD = {
    "right_handed_y_up": (0.0, 0.0, -1.0),
    "left_handed_y_up": (0.0, 0.0, 1.0),
    "right_handed_z_up": (0.0, 1.0, 0.0),
    "left_handed_z_up": (0.0, 1.0, 0.0),
    "right_handed_z_up_x_fwd": (1.0, 0.0, 0.0),
}


def recording_azimuth(coordinate_system: str) -> Optional[float]:
    """The orbit azimuth that reproduces the recording's own viewpoint.

    A different question from the athlete's front, and kept a different
    question: a recording made from the side has a perfectly good camera
    direction and no claim at all about which way the person was facing.
    Making one preset an alias of the other would throw that away.

    ``None`` when the coordinate system is not one this knows the convention
    for - the caller then leaves the preset out rather than pointing it
    somewhere invented.
    """
    forward = CAMERA_FORWARD.get((coordinate_system or "").strip().lower())
    if forward is None:
        return None
    up = up_axis_for(coordinate_system)
    a, b = [i for i in (0, 1, 2) if i != up]
    # Standing where the camera is means standing *against* its view direction.
    behind = (-forward[a], -forward[b])
    if abs(behind[0]) < 1e-9 and abs(behind[1]) < 1e-9:
        # A camera looking straight down has no direction in the ground plane.
        return None
    return math.atan2(behind[1], behind[0]) % (2 * math.pi)


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

    def turn(self, d_azimuth: float) -> "OrbitCamera":
        """Walk around the athlete. Height does not change.

        CAM-01: the plain left drag. The viewer circles a vertical axis and
        the athlete stays where they are - the "bullet time" move. Vertical
        mouse movement is deliberately *not* wired to this: a drag that was
        meant to circle should not tip the camera over the subject's head
        because the hand wandered.
        """
        return replace(self, azimuth=(self.azimuth + d_azimuth) % (2 * math.pi))

    def inspect(self, d_azimuth: float, d_elevation: float) -> "OrbitCamera":
        """Look from above or below, around the body's own centre.

        CAM-02: the middle-button drag. Same orbit, but elevation is live and
        the target is the body rather than the point between the feet. The two
        are different concepts and the code keeps them apart: the axis a
        viewer walks around is vertical through the floor, and what the camera
        looks at is the middle of the person.
        """
        return self.orbit(d_azimuth, d_elevation)

    def with_target(self, target: Sequence[float]) -> "OrbitCamera":
        """Look at a different point without moving anything else."""
        return replace(
            self,
            target=(float(target[0]), float(target[1]), float(target[2])),
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

    def _reference_up(self, forward: np.ndarray) -> np.ndarray:
        """An up vector that is not parallel to ``forward``.

        Looking straight down, the world's up *is* the view direction, and
        ``cross(forward, up)`` is the zero vector - the camera has no defined
        roll and the matrix collapses. The usual dodge is to stop short of the
        pole, which is why "Üst" was 78 degrees and not a view from overhead.

        Instead, the reference tips over to a ground axis as the pole is
        approached. The view keeps a defined, continuous orientation all the
        way to straight down, and the preset can be what it says it is.
        """
        up = self.up
        if abs(float(np.dot(forward, up))) < 0.999:
            return up
        # Which way is "up the screen" when looking down: the ground axis the
        # azimuth is measured from, turned to face the same way the camera
        # does. Continuous with the off-pole case, so approaching straight
        # down does not snap.
        a, b = [i for i in (0, 1, 2) if i != self.up_axis]
        horizon = np.zeros(3, dtype=np.float64)
        horizon[a] = math.cos(self.azimuth)
        horizon[b] = math.sin(self.azimuth)
        # Below the athlete the same reference would flip the image over.
        return horizon if self.elevation >= 0.0 else -horizon

    def _screen_axes(self) -> tuple[np.ndarray, np.ndarray]:
        forward = np.asarray(self.target, dtype=np.float64) - self.eye
        forward = _normalise(forward)
        right = _normalise(np.cross(forward, self._reference_up(forward)))
        return right, _normalise(np.cross(right, forward))

    def view_matrix(self) -> np.ndarray:
        """Column-major 4x4, ready for OpenGL."""
        eye = self.eye
        forward = _normalise(np.asarray(self.target, dtype=np.float64) - eye)
        right = _normalise(np.cross(forward, self._reference_up(forward)))
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


def bone_ribbons(
    joints: Optional[np.ndarray],
    bones: Sequence[tuple[int, int]],
    eye: np.ndarray,
    width: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bones as camera-facing quads, and which bone each vertex belongs to.

    ``GL_LINES`` with ``glLineWidth`` is why the bones looked like staircases:
    the specification only requires a driver to support a width of 1.0, so on
    most of them a thick line either stays one pixel or is drawn as an
    unfiltered run of them. A quad is geometry, and geometry is antialiased by
    the same multisampling as everything else in the scene.

    Each bone becomes two triangles in a ribbon that turns to face the camera,
    so it keeps the same apparent thickness whatever angle it is seen from -
    including end-on, where a fixed-orientation ribbon would vanish.

    Returns ``([N*6, 3] vertices, [N*6] bone index, [N*6] across)``. The bone
    index is what lets the caller colour each bone from the anatomy without a
    draw call per bone; ``across`` runs -1..+1 over the ribbon's width and is
    what the shader fades the outermost pixel from, so the edge is smooth
    without depending on a driver granting multisampling.

    A bone with a missing end is left out: drawing it to the origin would be
    the 3-D version of the lie this project refuses everywhere else.
    """
    segments = bone_segments(joints, bones)
    kept = _kept_bone_indices(joints, bones)
    if len(segments) == 0:
        return (
            np.zeros((0, 3), dtype=np.float32),
            np.zeros(0, dtype=np.int64),
            np.zeros(0, dtype=np.float32),
        )

    starts = segments[:, 0, :].astype(np.float64)
    ends = segments[:, 1, :].astype(np.float64)
    along = ends - starts
    # Towards the camera from the middle of each bone, so a ribbon seen
    # end-on still has area.
    to_eye = np.asarray(eye, dtype=np.float64) - (starts + ends) / 2.0
    side = np.cross(along, to_eye)
    lengths = np.linalg.norm(side, axis=1, keepdims=True)
    # A bone pointing straight at the camera has no well-defined side. Any
    # perpendicular will do there, and this one is stable.
    degenerate = (lengths < 1e-9).ravel()
    if degenerate.any():
        fallback = np.cross(along[degenerate], np.array([0.0, 0.0, 1.0]))
        second = np.cross(along[degenerate], np.array([0.0, 1.0, 0.0]))
        flat = np.linalg.norm(fallback, axis=1) < 1e-9
        fallback[flat] = second[flat]
        side[degenerate] = fallback
        lengths = np.linalg.norm(side, axis=1, keepdims=True)
    offset = side / np.maximum(lengths, 1e-9) * (float(width) / 2.0)

    a = starts + offset
    b = starts - offset
    c = ends - offset
    d = ends + offset
    quads = np.stack((a, b, c, a, c, d), axis=1)  # [N, 6, 3]
    # Where each vertex sits across the ribbon: +1 on one side, -1 on the
    # other. The shader fades the last pixel from this, which is what gives a
    # smooth edge on a driver that declined multisampling.
    across = np.tile(
        np.asarray([1.0, -1.0, -1.0, 1.0, -1.0, 1.0], dtype=np.float32),
        len(quads),
    )
    return (
        quads.reshape(-1, 3).astype(np.float32),
        np.repeat(kept, 6).astype(np.int64),
        across,
    )


def _kept_bone_indices(
    joints: Optional[np.ndarray], bones: Sequence[tuple[int, int]]
) -> np.ndarray:
    """Indices into ``bones`` of the bones :func:`bone_segments` keeps."""
    if joints is None or not len(bones):
        return np.zeros(0, dtype=np.int64)
    points = np.asarray(joints, dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        return np.zeros(0, dtype=np.int64)
    valid = np.isfinite(points).all(axis=1)
    pairs = np.asarray(bones, dtype=np.int64).reshape(-1, 2)
    order = np.arange(len(pairs), dtype=np.int64)
    inside = (pairs >= 0).all(axis=1) & (pairs < len(points)).all(axis=1)
    pairs, order = pairs[inside], order[inside]
    if pairs.size == 0:
        return np.zeros(0, dtype=np.int64)
    usable = valid[pairs[:, 0]] & valid[pairs[:, 1]]
    return order[usable]


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
    centre: Optional[Sequence[float]] = None,
) -> np.ndarray:
    """``[N, 2, 3]`` line endpoints for a floor grid.

    Without a floor there is no way to tell a lean from a camera angle: a
    skeleton alone in space has no scale and no horizon.

    ``centre`` puts the grid under the athlete rather than under the origin -
    a recording's origin is the camera, which can be metres away. It is
    applied **once**, from a reference pose: a grid recentred every frame
    would follow the athlete around and stop being a fixed floor, which is
    exactly the behaviour FLOOR-01 rules out.
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
    if centre is not None:
        offset = np.asarray(centre, dtype=np.float32).ravel()
        if offset.size == 3:
            lines[:, :, a] += offset[a]
            lines[:, :, b] += offset[b]
    return lines


def project_points(
    points: Optional[np.ndarray], matrix: np.ndarray, width: int, height: int
) -> np.ndarray:
    """Where ``points`` land on a ``width`` x ``height`` viewport, in pixels.

    ``[N, 3]`` of ``(x, y, depth)``. ``depth`` is the clip-space z divided by
    w, so nearer is smaller, and a point behind the camera comes back with
    ``NaN`` rather than a mirrored position in front of it - picking a joint
    that is behind you is exactly the "wrong joint selected" the design review
    ruled out.

    The y axis is flipped into widget coordinates, so the result can be
    compared with a mouse position directly.
    """
    if points is None:
        return np.zeros((0, 3), dtype=np.float64)
    array = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if array.size == 0:
        return np.zeros((0, 3), dtype=np.float64)
    homogeneous = np.concatenate(
        [array, np.ones((len(array), 1), dtype=np.float64)], axis=1
    )
    clip = homogeneous @ np.asarray(matrix, dtype=np.float64).T
    w = clip[:, 3]
    out = np.full((len(array), 3), np.nan, dtype=np.float64)
    visible = w > 1e-9
    ndc = clip[visible, :3] / w[visible, None]
    out[visible, 0] = (ndc[:, 0] * 0.5 + 0.5) * float(width)
    out[visible, 1] = (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * float(height)
    out[visible, 2] = ndc[:, 2]
    return out


def pick_joint(
    projected: np.ndarray, x: float, y: float, radius: float
) -> Optional[int]:
    """Which joint a click at ``(x, y)`` means, or ``None``.

    The nearest *to the camera* among those under the pointer, not the nearest
    in the plane: when two joints overlap the one in front is the one being
    looked at, and picking the one behind is how the far shoulder gets marked
    instead of the near one.

    Nothing within ``radius`` means nothing was picked. Clicking empty space
    must not invent a joint.
    """
    if projected is None or len(projected) == 0:
        return None
    array = np.asarray(projected, dtype=np.float64)
    finite = np.isfinite(array).all(axis=1)
    if not finite.any():
        return None
    dx = array[:, 0] - float(x)
    dy = array[:, 1] - float(y)
    within = finite & ((dx * dx + dy * dy) <= float(radius) ** 2)
    if not within.any():
        return None
    candidates = np.nonzero(within)[0]
    nearest = candidates[np.argmin(array[candidates, 2])]
    return int(nearest)


def feet_pivot(
    joints: Optional[np.ndarray],
    left_ankle: Optional[int],
    right_ankle: Optional[int],
    up_axis: int = DEFAULT_UP_AXIS,
    floor_height: Optional[float] = None,
) -> Optional[tuple[float, float, float]]:
    """The point the horizontal orbit turns around: between the feet, on the floor.

    ``joints`` may be one frame or a window; a window is better, because a
    pivot recomputed from a single frame follows the ankles' own noise and the
    whole scene wobbles as the person shifts weight.

    Returns ``None`` when neither ankle is known. That is not a failure to
    paper over with the origin - the caller keeps its last good pivot and says
    so, which is a viewing decision rather than a measurement.
    """
    if joints is None:
        return None
    array = np.asarray(joints, dtype=np.float64)
    if array.ndim == 2:
        array = array[None, :, :]
    if array.ndim != 3:
        return None
    indices = [i for i in (left_ankle, right_ankle) if i is not None]
    indices = [i for i in indices if 0 <= i < array.shape[1]]
    if not indices:
        return None
    feet = array[:, indices, :].reshape(-1, 3)
    finite = feet[np.isfinite(feet).all(axis=1)]
    if finite.size == 0:
        return None
    centre = finite.mean(axis=0)
    # On the floor, not at ankle height: the axis a viewer walks around is
    # vertical through the ground, so a jump must not lift it.
    centre[up_axis] = (
        float(floor_height)
        if floor_height is not None
        else float(np.min(finite[:, up_axis]))
    )
    return float(centre[0]), float(centre[1]), float(centre[2])


def body_target(
    joints: Optional[np.ndarray], hips: Sequence[Optional[int]] = ()
) -> Optional[tuple[float, float, float]]:
    """What the camera looks at: the middle of the body.

    The hips when the skeleton declares them, because that is where a person's
    mass is and an orbit around it reads as walking around somebody. Failing
    that, the centre of whatever joints exist - stated as a fallback rather
    than presented as an anatomical claim.
    """
    if joints is None:
        return None
    array = np.asarray(joints, dtype=np.float64)
    if array.ndim == 2:
        array = array[None, :, :]
    if array.ndim != 3:
        return None
    indices = [i for i in hips if i is not None and 0 <= i < array.shape[1]]
    if indices:
        chosen = array[:, indices, :].reshape(-1, 3)
        finite = chosen[np.isfinite(chosen).all(axis=1)]
        if finite.size:
            centre = finite.mean(axis=0)
            return float(centre[0]), float(centre[1]), float(centre[2])
    framing = frame_subject(array)
    return framing[0] if framing is not None else None


__all__ = [
    "DEFAULT_UP_AXIS",
    "body_target",
    "bone_ribbons",
    "feet_pivot",
    "pick_joint",
    "project_points",
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
