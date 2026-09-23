"""The 3D skeleton, drawn with OpenGL.

A thin renderer over :mod:`kinecapture.studio.services.skeleton3d` and
:mod:`kinecapture.studio.services.skeleton_palette`, which own every number
worth testing. This file owns the GL context and nothing else.

Three things are deliberate.

**The scene is not rebuilt per frame.** The floor is uploaded once. The pose
buffers are allocated at the skeleton's maximum size and then written into, so
scrubbing a take costs a buffer write rather than a new scene.

**Joints are spheres, bones are ribbons.** The joints were ``GL_POINTS`` and
the bones ``GL_LINES`` with ``glLineWidth``, and both were wrong for the same
reason: OpenGL only requires a driver to support a line width of 1.0 and a
square point, so what a reader saw was a flat dot and a staircase. A point is
now shaded as a sphere in the fragment shader - one quad per joint, no mesh,
no vertex cost - and a bone is two triangles that turn to face the camera.

Neither relies on multisampling, because on this machine there is none:
``setSamples(4)`` is *requested* and the driver grants 0, measured from the
live context rather than assumed from the request. The sphere gets its edge
from ``discard`` and the ribbon fades its own last pixel.

**Colour belongs to the athlete, not the screen.** Every joint and bone takes
its colour from the skeleton's own anatomical role table, so the right arm is
amber whether the camera is in front of the person or behind them. A joint
whose role the format does not declare is neutral and is *named* unknown.

Only PySide6's own GL classes are used. PyOpenGL is installed here but its
accelerator is compiled against an older numpy and raises on the first array
it is handed; Qt's buffers and shader program have no such coupling.

If OpenGL cannot start - a remote session, a driver that refuses the context -
the widget says so in the viewport. Labelling does not depend on this view, so
a missing 3D view is a message, never a crash.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Sequence

import numpy as np
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QMatrix4x4,
    QMouseEvent,
    QPainter,
    QSurfaceFormat,
    QWheelEvent,
)
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from kinecapture.studio.services.camera_presets import (
    PRESETS_BY_KEY,
    CameraTransition,
    Preset,
    camera_for_preset,
)
from kinecapture.studio.services.skeleton3d import (
    DEFAULT_UP_AXIS,
    OrbitCamera,
    bone_ribbons,
    body_target,
    feet_pivot,
    frame_subject,
    ground_grid,
    joint_points,
    pick_joint,
    project_points,
)
from kinecapture.studio.services.skeleton_palette import (
    bone_tokens,
    joint_labels,
    joint_tokens,
)
from kinecapture.studio.theme import ThemeTokens

logger = logging.getLogger(__name__)

GL_LINES = 0x0001
GL_TRIANGLES = 0x0004
GL_POINTS = 0x0000
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_VERTEX_PROGRAM_POINT_SIZE = 0x8642
GL_MULTISAMPLE = 0x809D
GL_SAMPLES = 0x80A9
#: Point sprites. On a *core* profile ``gl_PointCoord`` is always defined; on
#: a compatibility profile - which is what Qt gives us here, measured as
#: OpenGL 4.6 Compatibility - it is undefined until this is enabled, and the
#: sphere shader then discards every fragment. Measured on 19 September: with
#: it off the joints drew exactly 0 pixels while the same points through the
#: flat shader drew 10482.
GL_POINT_SPRITE = 0x8861

#: How close to a joint's drawn centre a click has to land, in pixels. Wide
#: enough to hit without aiming, narrow enough that two joints a hand's width
#: apart on screen are two targets.
PICK_RADIUS_PX = 14

#: Height of the band that says joint picking is on.
PICKING_STRIP_H = 30

#: How often the camera repaints during a preset transition. Stopped the
#: moment the transition ends - an animation timer left running is a screen
#: nobody is looking at being redrawn sixty times a second.
TRANSITION_INTERVAL_MS = 16

_VERTEX_SHADER = """
#version 120
attribute vec3 position;
attribute vec3 colour_in;
attribute float edge_in;
uniform mat4 mvp;
uniform float point_size;
varying vec3 colour_out;
varying float edge_out;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
    gl_PointSize = point_size;
    colour_out = colour_in;
    edge_out = edge_in;
}
"""

#: One quad per joint, shaded as a sphere. The normal is reconstructed from
#: the point's own coordinates, so there is no mesh and no extra vertex work -
#: a joint costs one vertex whatever it looks like. ``discard`` outside the
#: circle is what makes the square a disc, and the depth written from the
#: reconstructed normal is what lets a near joint occlude a far one correctly.
_SPHERE_FRAGMENT = """
#version 120
uniform vec4 colour;
uniform float use_vertex_colour;
uniform float ring;
varying vec3 colour_out;
void main() {
    vec2 from_centre = gl_PointCoord * 2.0 - 1.0;
    float radius = dot(from_centre, from_centre);
    if (radius > 1.0) {
        discard;
    }
    vec3 normal = vec3(from_centre, sqrt(max(0.0, 1.0 - radius)));
    // One fixed light, over the viewer's shoulder. Enough to read a sphere
    // as a sphere; not a lighting model anybody should reason about.
    float lit = 0.45 + 0.55 * max(0.0, dot(normal, normalize(vec3(0.3, 0.5, 1.0))));
    vec3 base = mix(colour.rgb, colour_out, use_vertex_colour);
    vec3 shaded = base * lit;
    if (ring > 0.5 && radius > 0.62) {
        // The selection ring: a bright rim that leaves the anatomical colour
        // in the middle, so a selected joint still says which limb it is on.
        shaded = mix(shaded, vec3(1.0), 0.75);
    }
    gl_FragColor = vec4(shaded, colour.a);
}
"""

#: Bones fade their own edges rather than relying on multisampling.
#: Measured on this machine: ``QSurfaceFormat.setSamples(4)`` is *requested*
#: and the driver grants 0. Asking again would not change that, so the smooth
#: edge is computed here, where nothing can decline it. ``edge_out`` runs
#: -1..+1 across the ribbon, and ``fwidth`` is how wide one pixel is in that
#: coordinate - so the fade is exactly one pixel at any zoom.
_FLAT_FRAGMENT = """
#version 120
#extension GL_OES_standard_derivatives : enable
uniform vec4 colour;
uniform float use_vertex_colour;
uniform float soften;
varying vec3 colour_out;
varying float edge_out;
void main() {
    vec3 base = mix(colour.rgb, colour_out, use_vertex_colour);
    float alpha = colour.a;
    if (soften > 0.5) {
        float distance_from_edge = 1.0 - abs(edge_out);
        float pixel = fwidth(edge_out);
        alpha *= smoothstep(0.0, max(pixel, 1e-5), distance_from_edge);
    }
    gl_FragColor = vec4(base, alpha);
}
"""


class _Mesh:
    """One vertex buffer, allocated once and written into afterwards."""

    def __init__(self) -> None:
        self.buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.capacity = 0
        self.count = 0

    def create(self) -> None:
        self.buffer.create()
        self.buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)

    #: Floats per vertex: position (3), colour (3), across-ribbon (1).
    STRIDE = 7

    def upload(
        self,
        vertices: np.ndarray,
        colours: Optional[np.ndarray] = None,
        across: Optional[np.ndarray] = None,
    ) -> None:
        """Position, colour and across-ribbon coordinate, interleaved."""
        data = np.ascontiguousarray(vertices, dtype=np.float32).reshape(-1, 3)
        self.count = len(data)
        if self.count == 0:
            return
        payload = np.zeros((self.count, self.STRIDE), dtype=np.float32)
        payload[:, :3] = data
        if colours is not None:
            payload[:, 3:6] = np.ascontiguousarray(
                colours, dtype=np.float32
            ).reshape(-1, 3)
        if across is not None:
            payload[:, 6] = np.ascontiguousarray(across, dtype=np.float32).ravel()
        raw = np.ascontiguousarray(payload).tobytes()
        self.buffer.bind()
        if len(raw) > self.capacity:
            # Grows, never shrinks: a take's skeleton has a fixed joint count,
            # so this settles after the first frame.
            self.buffer.allocate(raw, len(raw))
            self.capacity = len(raw)
        else:
            self.buffer.write(0, raw, len(raw))
        self.buffer.release()

    def destroy(self) -> None:
        if self.buffer.isCreated():
            self.buffer.destroy()


def _rgb(colour: str) -> tuple[float, float, float]:
    value = QColor(colour)
    return value.redF(), value.greenF(), value.blueF()


class Skeleton3DView(QOpenGLWidget):
    """Orbit view of one frame's pose, in the recording's own coordinates."""

    camera_changed = Signal()
    #: A joint was double-clicked while joint-picking is on. Carries the index.
    joint_picked = Signal(int)
    #: The joint under the pointer, or -1. Drives the hover readout.
    joint_hovered = Signal(int)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.camera = OrbitCamera()
        self._bones: tuple[tuple[int, int], ...] = ()
        self._joints: Optional[np.ndarray] = None
        self._spec = None
        self._joint_colours: Optional[np.ndarray] = None
        self._bone_colours: Optional[np.ndarray] = None
        self._labels: tuple[str, ...] = ()
        self._highlight: frozenset[int] = frozenset()
        self._selected: frozenset[int] = frozenset()
        self._hovered = -1
        self._grid_data = ground_grid(DEFAULT_UP_AXIS)
        #: The floor mesh is uploaded once and only re-uploaded when the plane
        #: it represents moves - which is when a version opens, not per frame.
        self._grid_dirty = True
        self._floor_height: Optional[float] = None
        #: Where the grid sits when nothing measured a floor. Kept apart from
        #: ``_floor_height`` so "detected" and "visual reference" are never
        #: the same value read two ways.
        self._reference_floor: Optional[float] = None
        self._program: Optional[QOpenGLShaderProgram] = None
        self._flat: Optional[QOpenGLShaderProgram] = None
        self._grid = _Mesh()
        self._bone_mesh = _Mesh()
        self._joint_mesh = _Mesh()
        self._marked_mesh = _Mesh()
        self._dirty = True
        self._unavailable = ""
        self._note = ""
        self._last_pos: Optional[QPoint] = None
        self._drag_button: Optional[Qt.MouseButton] = None
        self._drag_distance = 0.0
        #: The vertical axis the plain left drag turns around, and the point
        #: the camera looks at. Different concepts, kept apart on purpose.
        self._pivot: Optional[tuple[float, float, float]] = None
        self._body: Optional[tuple[float, float, float]] = None
        #: The recording's own front, set once. Presets are offsets from it.
        self._reference_azimuth = 0.0
        #: Where the recording's own camera stood, as an orbit azimuth, or
        #: ``None`` when the coordinate convention is not known. Kept apart
        #: from the anatomical reference on purpose: a recording made from the
        #: side has a camera direction and no claim about the athlete's front.
        self._recording_azimuth: Optional[float] = None
        #: Joint-picking is off unless a class is being defined. A double
        #: click during ordinary labelling must not change a class's joints.
        self._picking = False
        #: What to say over the scene while picking. Empty when not picking.
        self._picking_note = ""
        self._build_overlay()
        self._transition: Optional[CameraTransition] = None
        self._transition_started = 0.0
        self._reduce_motion = False
        self._previous_camera: Optional[OrbitCamera] = None
        self._saved_camera: Optional[OrbitCamera] = None
        self._show_floor = True
        self._samples = 0
        #: Frame-time samples, for the performance report. Bounded.
        self._frame_times: list[float] = []

        self._timer = QTimer(self)
        self._timer.setInterval(TRANSITION_INTERVAL_MS)
        self._timer.timeout.connect(self._advance_transition)

        self.setMinimumSize(220, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("3B iskelet görünümü")

    # ---------------------------------------------------------------- state
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._rebuild_palette()
        self._dirty = True
        self.update()

    def set_skeleton_spec(
        self, bones: Sequence[tuple[int, int]], up_axis: int, spec=None  # noqa: ANN001
    ) -> None:
        """The topology, the up axis, and - when given - the role table.

        The spec is what makes the colours anatomical. Without it every joint
        is neutral, which is the honest answer rather than a guess from index
        positions that mean different things in different formats.
        """
        self._bones = tuple(bones)
        self._spec = spec
        self._labels = joint_labels(spec)
        self._grid_data = ground_grid(
            up_axis, height=self._floor_height or 0.0, centre=self._pivot
        )
        self._grid_dirty = True
        if up_axis != self.camera.up_axis:
            self.camera = OrbitCamera(up_axis=up_axis)
        self._rebuild_palette()
        self._dirty = True
        self.update()

    def _rebuild_palette(self) -> None:
        """Resolve the anatomy's colours once per spec or theme, not per frame."""
        spec = self._spec
        if spec is None:
            self._joint_colours = None
            self._bone_colours = None
            return
        tokens = self._tokens
        self._joint_colours = np.asarray(
            [_rgb(tokens.colour(token)) for token in joint_tokens(spec)],
            dtype=np.float32,
        )
        self._bone_colours = np.asarray(
            [_rgb(tokens.colour(token)) for token in bone_tokens(spec, self._bones)],
            dtype=np.float32,
        )

    def set_joints(self, joints: Optional[np.ndarray]) -> None:
        """The pose for the current frame, ``[J, 3]``, NaN where unknown."""
        self._joints = None if joints is None else np.asarray(joints, dtype=np.float32)
        self._dirty = True
        self.update()

    def set_highlight(self, joints: Sequence[int]) -> None:
        highlight = frozenset(int(i) for i in joints)
        if highlight != self._highlight:
            self._highlight = highlight
            self._dirty = True
            self.update()

    def set_selected_joints(self, joints: Sequence[int]) -> None:
        """Joints chosen while a fault class is being defined."""
        selected = frozenset(int(i) for i in joints)
        if selected != self._selected:
            self._selected = selected
            self._dirty = True
            self.update()

    @property
    def picking_note(self) -> str:
        return self._picking_note

    def set_picking_note(self, text: str) -> None:
        """What the annotator is being asked to do, drawn over the scene.

        R-03 asks for an explicit "eklem seç" state. A hint in a panel below
        is not that: the instruction belongs where the pointing happens.
        """
        if text == self._picking_note:
            return
        self._picking_note = text
        self._show_overlay()

    def set_picking(self, enabled: bool) -> None:
        """Turn joint picking on, for the duration of defining a class.

        JOINT-03: outside that, a double click is not allowed to change any
        class's joints, so the mode is explicit rather than always live.
        """
        self._picking = bool(enabled)
        if not self._picking:
            self._picking_note = ""
        self._show_overlay()
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._picking
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    @property
    def is_picking(self) -> bool:
        return self._picking

    def set_note(self, text: str) -> None:
        """Shown in the corner - usually why there is no pose on this frame."""
        if text != self._note:
            self._note = text
            self._show_overlay()

    def set_floor_height(self, height: Optional[float]) -> None:
        """Where the ground is, in the recording's own units.

        ``None`` means nothing measured one, and the grid is drawn at the
        origin plane and described as a visual reference rather than as a
        detected floor.
        """
        self._floor_height = None if height is None else float(height)
        self._grid_data = ground_grid(
            self.camera.up_axis,
            height=self._floor_height or 0.0,
            centre=self._pivot,
        )
        self._grid_dirty = True
        self._dirty = True
        self.update()

    @property
    def floor_source(self) -> str:
        """``detected`` | ``visual_reference`` | ``none``.

        FLOOR-04 keeps these three apart. A grid drawn at the lowest the feet
        reached is a viewing aid; it is not the plane the SDK measured, and
        the interface must not let the two be confused.
        """
        if self._floor_height is not None:
            return "detected"
        if self._reference_floor is not None:
            return "visual_reference"
        return "none"

    @property
    def floor_height(self) -> Optional[float]:
        """The height the grid is drawn at, whatever its source."""
        if self._floor_height is not None:
            return self._floor_height
        return self._reference_floor

    def set_floor_visible(self, shown: bool) -> None:
        self._show_floor = bool(shown)
        self.update()

    @property
    def floor_visible(self) -> bool:
        return self._show_floor

    @property
    def is_available(self) -> bool:
        return not self._unavailable

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable

    @property
    def samples(self) -> int:
        """Multisample count the context really gave us, not the one asked for."""
        return self._samples

    def set_camera(self, camera: OrbitCamera) -> None:
        self.camera = camera
        self.update()

    # ------------------------------------------------------- stable targets
    def set_references(
        self,
        window: Optional[np.ndarray],
        *,
        left_ankle: Optional[int] = None,
        right_ankle: Optional[int] = None,
        hips: Sequence[Optional[int]] = (),
    ) -> None:
        """Establish the pivot and the look-at point, once, from a window.

        CAM-04. Both are computed over a span of frames rather than one, so a
        jump does not move the axis the viewer walks around and a shift of
        weight does not make the whole scene wobble. When the joints needed
        are missing, the previous values are kept - a viewing decision, not a
        measurement being filled in.
        """
        pivot = feet_pivot(
            window,
            left_ankle,
            right_ankle,
            up_axis=self.camera.up_axis,
            floor_height=self._floor_height,
        )
        if pivot is not None:
            self._pivot = pivot
            if self._floor_height is None:
                # No measured floor for this version. The grid is drawn at the
                # lowest the feet reached over the reference window, which is
                # a *visual reference* and is described as one - see
                # :attr:`floor_source`. It is emphatically not a claim that
                # the floor was detected, and because it is fixed once it does
                # not rise when the athlete jumps.
                self._reference_floor = float(pivot[self.camera.up_axis])
            # Under the athlete whichever way the height was found. A measured
            # floor says how *high* the grid is and nothing about where; that
            # still comes from the feet. Centring used to happen only without
            # a measured floor, so a version with one kept the grid on the
            # recording's origin - the camera, measured 3.03 m from the
            # athlete on 22 September against a 3 m half-width - and the
            # athlete stood on its edge. A second version opened in the same
            # view kept the first one's centre instead.
            self._grid_data = ground_grid(
                self.camera.up_axis, height=self.floor_height, centre=pivot
            )
            self._grid_dirty = True
        body = body_target(window, hips)
        if body is not None:
            self._body = body
            self.camera = self.camera.with_target(body)
            self.camera_changed.emit()
        self.update()

    def set_recording_azimuth(self, azimuth: Optional[float]) -> None:
        """The source camera's own direction. Not the athlete's front."""
        self._recording_azimuth = None if azimuth is None else float(azimuth)

    @property
    def recording_azimuth(self) -> float:
        """The recorded viewpoint, or the current reference if unknown."""
        if self._recording_azimuth is None:
            return self._reference_azimuth
        return self._recording_azimuth

    @property
    def has_recording_direction(self) -> bool:
        return self._recording_azimuth is not None

    def set_reference_azimuth(self, azimuth: float) -> None:
        """The recording's own front. Presets are measured from it, once."""
        self._reference_azimuth = float(azimuth)

    def use_current_view_as_front(self) -> None:
        """PRESET-01: let the annotator say which way "ön" is."""
        self._reference_azimuth = self.camera.azimuth
        self.update()

    @property
    def reference_azimuth(self) -> float:
        return self._reference_azimuth

    def frame_on(self, joints: Optional[np.ndarray]) -> bool:
        """Point the camera at the subject. Once per version, not per frame."""
        framing = frame_subject(joints, self.camera.up_axis)
        if framing is None:
            return False
        target, distance = framing
        self.camera = self.camera.looking_at(target, distance)
        self._body = tuple(float(v) for v in target)
        self.camera_changed.emit()
        self.update()
        return True

    def reset_view(self) -> None:
        self.camera = OrbitCamera(
            up_axis=self.camera.up_axis,
            target=self._body or self.camera.target,
            distance=self.camera.distance,
        )
        self.camera_changed.emit()
        self.update()

    def centre_on_body(self) -> None:
        """CAM-03: one step back to the subject when the view has wandered."""
        if self._body is not None:
            self.camera = self.camera.with_target(self._body)
        self.camera_changed.emit()
        self.update()

    # -------------------------------------------------------- preset travel
    def set_reduce_motion(self, reduced: bool) -> None:
        """PRESET-03: arrive at once instead of travelling."""
        self._reduce_motion = bool(reduced)

    @property
    def reduce_motion(self) -> bool:
        return self._reduce_motion

    def go_to_preset(self, key: str) -> bool:
        preset = PRESETS_BY_KEY.get(key)
        if preset is None:
            return False
        destination = camera_for_preset(
            preset,
            self.camera,
            reference_azimuth=self._reference_azimuth,
            absolute_azimuth=self._recording_azimuth,
            target=self._body,
        )
        return self.travel_to(destination)

    def travel_to(self, destination: OrbitCamera) -> bool:
        """Move to ``destination``, smoothly unless motion is reduced.

        A transition already running is replaced rather than queued, and the
        new one starts from where the camera *is* - so pressing two presets in
        a row is a change of mind, not two journeys back to back.
        """
        self._previous_camera = self.camera
        if self._reduce_motion:
            self._stop_transition()
            self.camera = destination
            self.camera_changed.emit()
            self.update()
            return True
        self._transition = CameraTransition.to_camera(self.camera, destination)
        self._transition_started = time.perf_counter()
        if not self._timer.isActive():
            self._timer.start()
        return True

    def return_to_previous_view(self) -> bool:
        """PANEL-02: back to where the camera was before the last preset."""
        if self._previous_camera is None:
            return False
        return self.travel_to(self._previous_camera)

    def save_view(self) -> None:
        self._saved_camera = self.camera

    def restore_saved_view(self) -> bool:
        if self._saved_camera is None:
            return False
        return self.travel_to(self._saved_camera)

    @property
    def is_travelling(self) -> bool:
        return self._transition is not None

    def _advance_transition(self) -> None:
        transition = self._transition
        if transition is None:
            self._stop_transition()
            return
        elapsed = time.perf_counter() - self._transition_started
        self.camera = transition.at(elapsed)
        self.camera_changed.emit()
        self.update()
        if transition.finished(elapsed):
            self._stop_transition()

    def _stop_transition(self) -> None:
        self._transition = None
        if self._timer.isActive():
            # PERF-02: the timer stops the moment the journey ends. An
            # animation timer left running repaints a scene nothing is moving.
            self._timer.stop()

    # ------------------------------------------------------------------ GL
    def initializeGL(self) -> None:  # noqa: N802 - Qt naming
        try:
            self._program = self._build_program(_SPHERE_FRAGMENT)
            self._flat = self._build_program(_FLAT_FRAGMENT)
            for mesh in (self._grid, self._bone_mesh, self._joint_mesh, self._marked_mesh):
                mesh.create()
            self._grid.upload(self._grid_data.reshape(-1, 3))
            self._grid_dirty = False
            # What the driver actually gave us, which is not always what the
            # format asked for. Reported rather than assumed.
            context = self.context()
            self._samples = context.format().samples() if context else 0
            self._dirty = True
        except Exception as exc:  # noqa: BLE001 - any GL failure becomes a message
            logger.warning("3B görünüm başlatılamadı: %s", exc)
            self._program = None
            self._flat = None
            self._unavailable = (
                "3B görünüm bu makinede açılamadı.\n"
                "Etiketleme etkilenmez: video, 2B iskelet ve zaman çizelgesi çalışır."
            )

            self._show_overlay()
    def _build_program(self, fragment: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER
        ):
            raise RuntimeError(program.log() or "köşe gölgelendiricisi derlenmedi")
        if not program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, fragment
        ):
            raise RuntimeError(program.log() or "parça gölgelendiricisi derlenmedi")
        if not program.link():
            raise RuntimeError(program.log() or "gölgelendirici bağlanamadı")
        return program

    def _rebuild(self) -> None:
        tokens = self._tokens
        # Scaled with the camera's distance so a bone keeps roughly the same
        # apparent thickness whether the view is close in or pulled back.
        width = tokens.metric("KcBoneWidth") / 1000.0 * max(1.0, self.camera.distance)
        vertices, bone_index, across = bone_ribbons(
            self._joints, self._bones, self.camera.eye, width
        )
        if self._bone_colours is not None and len(bone_index):
            inside = bone_index < len(self._bone_colours)
            tint = np.zeros((len(bone_index), 3), dtype=np.float32)
            tint[inside] = self._bone_colours[bone_index[inside]]
            self._bone_mesh.upload(vertices, tint, across)
        else:
            self._bone_mesh.upload(vertices, None, across)

        points, indices = joint_points(self._joints)
        if len(points):
            marked = np.isin(indices, list(self._selected | self._highlight))
            plain_colours = self._colours_for(indices[~marked])
            self._joint_mesh.upload(points[~marked], plain_colours)
            self._marked_mesh.upload(points[marked], self._colours_for(indices[marked]))
        else:
            self._joint_mesh.upload(points, None)
            self._marked_mesh.upload(np.zeros((0, 3), dtype=np.float32), None)
        self._dirty = False

    def _colours_for(self, indices: np.ndarray) -> Optional[np.ndarray]:
        table = self._joint_colours
        if table is None or not len(indices):
            return None
        inside = indices < len(table)
        out = np.zeros((len(indices), 3), dtype=np.float32)
        out[inside] = table[indices[inside]]
        if (~inside).any():
            out[~inside] = _rgb(self._tokens.colour("KcAnatomyUnknown"))
        return out

    def paintGL(self) -> None:  # noqa: N802 - Qt naming
        started = time.perf_counter()
        functions = self.context().functions() if self.context() else None
        if functions is None:
            return
        tokens = self._tokens
        background = QColor(tokens.colour("KcSurfaceViewport"))
        functions.glClearColor(
            background.redF(), background.greenF(), background.blueF(), 1.0
        )
        functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._program is None or self._flat is None:
            return
        if self._grid_dirty:
            self._grid.upload(self._grid_data.reshape(-1, 3))
            self._grid_dirty = False
        if self._dirty:
            self._rebuild()

        functions.glEnable(GL_DEPTH_TEST)
        functions.glEnable(GL_BLEND)
        functions.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        functions.glEnable(GL_VERTEX_PROGRAM_POINT_SIZE)
        functions.glEnable(GL_POINT_SPRITE)
        functions.glEnable(GL_MULTISAMPLE)

        matrix = QMatrix4x4(*[float(v) for v in self._matrix().flatten()])

        if self._show_floor:
            self._draw(
                functions, self._flat, self._grid, GL_LINES,
                tokens.colour("KcFloorGrid"), matrix,
            )
        # Bones first: the joints sit on top of the ends, which is what makes
        # a limb read as jointed rather than as a chain of separate sticks.
        self._draw(
            functions, self._flat, self._bone_mesh, GL_TRIANGLES,
            tokens.colour("KcAnatomyUnknown"), matrix,
            vertex_colour=True, soften=True,
        )
        node = float(tokens.metric("KcJointNodeSize"))
        selected = float(tokens.metric("KcJointNodeSelectedSize"))
        self._draw(
            functions, self._program, self._joint_mesh, GL_POINTS,
            tokens.colour("KcAnatomyUnknown"), matrix,
            point_size=node * self.devicePixelRatioF(), vertex_colour=True,
        )
        self._draw(
            functions, self._program, self._marked_mesh, GL_POINTS,
            tokens.colour("KcSkeletonSelection"), matrix,
            point_size=selected * self.devicePixelRatioF(),
            vertex_colour=True, ring=True,
        )
        elapsed = time.perf_counter() - started
        self._frame_times.append(elapsed)
        if len(self._frame_times) > 240:
            del self._frame_times[:120]


    @property
    def frame_times(self) -> tuple[float, ...]:
        """Recent paint durations in seconds. For the performance report."""
        return tuple(self._frame_times)

    def _matrix(self) -> np.ndarray:
        aspect = self.width() / max(1, self.height())
        return self.camera.matrix(aspect)

    def _draw(
        self,
        functions,  # noqa: ANN001 - QOpenGLFunctions
        program: QOpenGLShaderProgram,
        mesh: _Mesh,
        mode: int,
        colour: str,
        matrix: QMatrix4x4,
        *,
        point_size: float = 1.0,
        vertex_colour: bool = False,
        ring: bool = False,
        soften: bool = False,
    ) -> None:
        if mesh.count == 0:
            return
        rgba = QColor(colour)
        program.bind()
        program.setUniformValue(program.uniformLocation("mvp"), matrix)
        program.setUniformValue1f(
            program.uniformLocation("point_size"), float(point_size)
        )
        program.setUniformValue1f(
            program.uniformLocation("use_vertex_colour"), 1.0 if vertex_colour else 0.0
        )
        if program is self._program:
            program.setUniformValue1f(
                program.uniformLocation("ring"), 1.0 if ring else 0.0
            )
        else:
            program.setUniformValue1f(
                program.uniformLocation("soften"), 1.0 if soften else 0.0
            )
        program.setUniformValue(
            program.uniformLocation("colour"),
            float(rgba.redF()), float(rgba.greenF()), float(rgba.blueF()), 1.0,
        )
        position = program.attributeLocation("position")
        tint = program.attributeLocation("colour_in")
        edge = program.attributeLocation("edge_in")
        mesh.buffer.bind()
        stride = _Mesh.STRIDE * 4
        program.enableAttributeArray(position)
        program.setAttributeBuffer(position, GL_FLOAT, 0, 3, stride)
        if tint >= 0:
            program.enableAttributeArray(tint)
            program.setAttributeBuffer(tint, GL_FLOAT, 3 * 4, 3, stride)
        if edge >= 0:
            program.enableAttributeArray(edge)
            program.setAttributeBuffer(edge, GL_FLOAT, 6 * 4, 1, stride)
        functions.glDrawArrays(mode, 0, mesh.count)
        program.disableAttributeArray(position)
        if tint >= 0:
            program.disableAttributeArray(tint)
        if edge >= 0:
            program.disableAttributeArray(edge)
        mesh.buffer.release()
        program.release()

    def _build_overlay(self) -> None:
        """Three labels over the viewport: the mode, the note, the hover."""
        self._picking_label = QLabel(self)
        self._picking_label.setProperty("kcRole", "pickingBanner")
        self._picking_label.setWordWrap(False)
        self._picking_label.setAccessibleName("Eklem seçimi durumu")
        self._picking_label.hide()

        self._note_label = QLabel(self)
        self._note_label.setProperty("kcRole", "viewportNote")
        self._note_label.setWordWrap(True)
        self._note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._note_label.hide()

        self._hover_label = QLabel(self)
        self._hover_label.setProperty("kcRole", "viewportHover")
        self._hover_label.hide()
        self._restyle_overlay()

    def _restyle_overlay(self) -> None:
        tokens = self._tokens
        self._picking_label.setStyleSheet(
            f"background: {tokens.colour('KcContextFault')};"
            f" color: {tokens.colour('KcTextOnAccent')};"
            f" padding: 6px 10px;"
        )
        self._note_label.setStyleSheet(
            f"background: {tokens.colour('KcSurfaceViewport')};"
            f" color: {tokens.colour('KcTextMuted')}; padding: 10px;"
        )
        self._hover_label.setStyleSheet(
            f"color: {tokens.colour('KcTextPrimary')};"
            f" background: {tokens.colour('KcSurfaceSunken')};"
            f" padding: 2px 6px;"
        )

    def _layout_overlay(self) -> None:
        """Where each label sits. Called whenever the widget resizes."""
        width, height = self.width(), self.height()
        self._picking_label.setGeometry(0, 0, width, PICKING_STRIP_H)
        top = PICKING_STRIP_H if self._picking_label.isVisible() else 0
        if self._unavailable:
            self._note_label.setGeometry(0, 0, width, height)
        else:
            self._note_label.setGeometry(
                8, max(0, height - 48), max(0, width - 16), 40
            )
        self._hover_label.adjustSize()
        self._hover_label.move(8, top + 8)

    def _show_overlay(self) -> None:
        """Reflect the current state. One place decides what is on screen."""
        self._picking_label.setText(self._picking_note)
        self._picking_label.setVisible(bool(self._picking_note))
        text = self._unavailable or self._note
        self._note_label.setText(text)
        self._note_label.setVisible(bool(text))
        hint = self._hover_text()
        self._hover_label.setText(hint)
        self._hover_label.setVisible(bool(hint))
        self._layout_overlay()
        self._picking_label.raise_()
        self._hover_label.raise_()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._layout_overlay()

    def _paint_overlay_unused(self) -> None:
        """Whatever has to be readable over the scene.

        Called from the end of `paintGL`, while the widget's own framebuffer
        is the current target. A `QPainter` opened in `paintEvent` instead
        draws into a surface that is never shown - which is why every one of
        these notes was invisible until this was measured.
        """
        hint = self._hover_text()
        if not (self._unavailable or self._note or hint or self._picking_note):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        if self._unavailable:
            painter.fillRect(self.rect(), QColor(tokens.colour("KcSurfaceViewport")))
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._unavailable,
            )
            painter.end()
            return
        if self._picking_note:
            # A band across the top, in the fault colour, so the mode is
            # unmistakable while it is on. Somebody who double-clicks the
            # skeleton has to be able to see *why* that does something now
            # and did not a moment ago.
            strip = QRectF(0, 0, self.width(), PICKING_STRIP_H)
            painter.fillRect(strip, QColor(tokens.colour("KcContextFault")))
            painter.setPen(QColor(tokens.colour("KcTextOnAccent")))
            painter.drawText(
                strip.adjusted(10, 0, -10, 0),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                self._picking_note,
            )
        if hint:
            painter.setPen(QColor(tokens.colour("KcTextPrimary")))
            painter.drawText(
                self.rect().adjusted(
                    8, PICKING_STRIP_H + 8 if self._picking_note else 8, -8, -8
                ),
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft),
                hint,
            )
        if self._note:
            painter.setPen(QColor(tokens.colour("KcTextSecondary")))
            painter.drawText(
                self.rect().adjusted(8, 8, -8, -8),
                int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                    | Qt.TextFlag.TextWordWrap),
                self._note,
            )
        painter.end()

    def _hover_text(self) -> str:
        if self._hovered < 0 or self._hovered >= len(self._labels):
            return ""
        return self._labels[self._hovered]

    # -------------------------------------------------------------- picking
    def projected_joints(self) -> np.ndarray:
        """Every joint's position on this widget, in its own pixels."""
        return project_points(
            self._joints, self._matrix(), self.width(), self.height()
        )

    def joint_at(self, x: float, y: float) -> Optional[int]:
        """Which joint a point on the widget means, or ``None``.

        The radius is in **logical** pixels, the same units as the projection
        and as the pointer. It used to be multiplied by the device pixel
        ratio, which made the tolerance grow with the scaling while the node
        drawn on screen stayed the same size on the page - at 150% a click 21
        logical pixels from a joint still marked it, well outside anything
        that looked like a target.
        """
        return pick_joint(self.projected_joints(), x, y, PICK_RADIUS_PX)

    # -------------------------------------------------------------- input
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        self._last_pos = event.position()
        self._drag_button = event.button()
        self._drag_distance = 0.0
        # Any deliberate input takes the camera back at once. A transition
        # that kept running under the hand would fight it.
        self._stop_transition()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        position = event.position()
        if self._last_pos is None:
            self._update_hover(position)
            return
        delta = position - self._last_pos
        self._last_pos = position
        self._drag_distance += abs(delta.x()) + abs(delta.y())
        buttons = event.buttons()
        if buttons & Qt.MouseButton.LeftButton:
            # CAM-01. Horizontal only: the viewer walks around a vertical axis
            # through the point between the feet, and the height of the camera
            # does not change because the hand drifted up.
            if self._pivot is not None:
                self.camera = self.camera.with_target(self._pivot)
            self.camera = self.camera.turn(-delta.x() * 0.01)
            if self._body is not None:
                self.camera = self.camera.with_target(self._body)
        elif buttons & Qt.MouseButton.MiddleButton:
            # CAM-02. Above and below, around the body's own centre.
            if self._body is not None:
                self.camera = self.camera.with_target(self._body)
            self.camera = self.camera.inspect(-delta.x() * 0.01, delta.y() * 0.01)
        elif buttons & Qt.MouseButton.RightButton:
            self.camera = self.camera.pan(delta.x(), delta.y())
        else:
            self._update_hover(position)
            return
        self.camera_changed.emit()
        self._dirty = True
        self.update()

    def _update_hover(self, position) -> None:  # noqa: ANN001
        found = self.joint_at(position.x(), position.y())
        index = -1 if found is None else int(found)
        if index != self._hovered:
            self._hovered = index
            self.joint_hovered.emit(index)
            self._show_overlay()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802, ARG002
        self._last_pos = None
        self._drag_button = None

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Pick a joint - but only while a class is being defined.

        JOINT-02: a drag that turned into a double click must not select. The
        distance the pointer travelled since the press is what separates the
        two, so turning the camera cannot mark a joint by accident.
        """
        if not self._picking or event.button() is not Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        if self._drag_distance > 6.0:
            return
        position = event.position()
        found = self.joint_at(position.x(), position.y())
        if found is None:
            # Empty space picks nothing. It does not invent the nearest joint.
            return
        self.joint_picked.emit(int(found))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt naming
        steps = event.angleDelta().y() / 120.0
        if steps:
            self._stop_transition()
            self.camera = self.camera.zoom(0.88 ** steps)
            self.camera_changed.emit()
            self._dirty = True
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        if self._hovered != -1:
            self._hovered = -1
            self.joint_hovered.emit(-1)
            self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        if event.key() == Qt.Key.Key_R:
            self.reset_view()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        # PERF-02: a view nobody is looking at does not animate.
        self._stop_transition()
        super().hideEvent(event)


def default_surface_format() -> QSurfaceFormat:
    """A depth buffer, which the scene needs and the default format lacks.

    Multisampling is *asked* for here; whether the driver grants it is read
    back from the live context (:attr:`Skeleton3DView.samples`) rather than
    assumed from this request.
    """
    fmt = QSurfaceFormat.defaultFormat()
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    return fmt


__all__ = [
    "PICKING_STRIP_H",
    "PICK_RADIUS_PX",
    "Skeleton3DView",
    "default_surface_format",
]
