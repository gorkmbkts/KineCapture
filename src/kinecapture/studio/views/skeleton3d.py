"""The 3D skeleton, drawn with OpenGL.

A thin renderer over :mod:`kinecapture.studio.services.skeleton3d`, which owns
every number worth testing. This file owns the GL context and nothing else.

Two things are deliberate.

**The scene is not rebuilt per frame.** The floor is uploaded once. The pose
buffers are allocated at the skeleton's maximum size and then written into, so
scrubbing a take costs a buffer write rather than a new scene.

**Only PySide6's own GL classes are used.** PyOpenGL is installed here but its
accelerator is compiled against an older numpy and raises on the first array
it is handed; Qt's buffers and shader program have no such coupling, and one
less binding is one less thing to break on another machine.

If OpenGL cannot start - a remote session, a driver that refuses the context -
the widget says so in the viewport. Labelling does not depend on this view, so
a missing 3D view is a message, never a crash.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import Qt, Signal
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
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.studio.services.skeleton3d import (
    DEFAULT_UP_AXIS,
    OrbitCamera,
    bone_segments,
    frame_subject,
    ground_grid,
    joint_points,
)
from kinecapture.studio.theme import ThemeTokens

logger = logging.getLogger(__name__)

GL_LINES = 0x0001
GL_POINTS = 0x0000
GL_FLOAT = 0x1406
GL_DEPTH_TEST = 0x0B71
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_VERTEX_PROGRAM_POINT_SIZE = 0x8642

_VERTEX_SHADER = """
#version 120
attribute vec3 position;
uniform mat4 mvp;
uniform float point_size;
void main() {
    gl_Position = mvp * vec4(position, 1.0);
    gl_PointSize = point_size;
}
"""

_FRAGMENT_SHADER = """
#version 120
uniform vec4 colour;
void main() {
    gl_FragColor = colour;
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

    def upload(self, vertices: np.ndarray) -> None:
        data = np.ascontiguousarray(vertices, dtype=np.float32).reshape(-1, 3)
        self.count = len(data)
        if self.count == 0:
            return
        payload = data.tobytes()
        self.buffer.bind()
        if len(payload) > self.capacity:
            # Grows, never shrinks: a take's skeleton has a fixed joint count,
            # so this settles after the first frame.
            self.buffer.allocate(payload, len(payload))
            self.capacity = len(payload)
        else:
            self.buffer.write(0, payload, len(payload))
        self.buffer.release()

    def destroy(self) -> None:
        if self.buffer.isCreated():
            self.buffer.destroy()


class Skeleton3DView(QOpenGLWidget):
    """Orbit view of one frame's pose, in the recording's own coordinates."""

    camera_changed = Signal()

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.camera = OrbitCamera()
        self._bones: tuple[tuple[int, int], ...] = ()
        self._joints: Optional[np.ndarray] = None
        self._highlight: frozenset[int] = frozenset()
        self._grid_data = ground_grid(DEFAULT_UP_AXIS)
        self._program: Optional[QOpenGLShaderProgram] = None
        self._grid = _Mesh()
        self._bone_mesh = _Mesh()
        self._joint_mesh = _Mesh()
        self._marked_mesh = _Mesh()
        self._dirty = True
        self._unavailable = ""
        self._note = ""
        self._last_pos = None
        self.setMinimumSize(220, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("3B iskelet görünümü")

    # ---------------------------------------------------------------- state
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def set_skeleton_spec(self, bones: Sequence[tuple[int, int]], up_axis: int) -> None:
        self._bones = tuple(bones)
        self._grid_data = ground_grid(up_axis)
        if up_axis != self.camera.up_axis:
            self.camera = OrbitCamera(up_axis=up_axis)
        self._dirty = True
        self.update()

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

    def set_note(self, text: str) -> None:
        """Shown in the corner - usually why there is no pose on this frame."""
        if text != self._note:
            self._note = text
            self.update()

    @property
    def is_available(self) -> bool:
        return not self._unavailable

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable

    def set_camera(self, camera: OrbitCamera) -> None:
        self.camera = camera
        self.update()

    def frame_on(self, joints: Optional[np.ndarray]) -> bool:
        """Point the camera at the subject. Once per version, not per frame."""
        framing = frame_subject(joints, self.camera.up_axis)
        if framing is None:
            return False
        target, distance = framing
        self.camera = self.camera.looking_at(target, distance)
        self.camera_changed.emit()
        self.update()
        return True

    def reset_view(self) -> None:
        self.camera = OrbitCamera(
            up_axis=self.camera.up_axis,
            target=self.camera.target,
            distance=self.camera.distance,
        )
        self.camera_changed.emit()
        self.update()

    # ------------------------------------------------------------------ GL
    def initializeGL(self) -> None:  # noqa: N802 - Qt naming
        try:
            program = QOpenGLShaderProgram(self)
            if not program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Vertex, _VERTEX_SHADER
            ):
                raise RuntimeError(program.log() or "köşe gölgelendiricisi derlenmedi")
            if not program.addShaderFromSourceCode(
                QOpenGLShader.ShaderTypeBit.Fragment, _FRAGMENT_SHADER
            ):
                raise RuntimeError(program.log() or "parça gölgelendiricisi derlenmedi")
            if not program.link():
                raise RuntimeError(program.log() or "gölgelendirici bağlanamadı")
            self._program = program
            for mesh in (self._grid, self._bone_mesh, self._joint_mesh, self._marked_mesh):
                mesh.create()
            self._grid.upload(self._grid_data)
            self._dirty = True
        except Exception as exc:  # noqa: BLE001 - any GL failure becomes a message
            logger.warning("3B görünüm başlatılamadı: %s", exc)
            self._program = None
            self._unavailable = (
                "3B görünüm bu makinede açılamadı.\n"
                "Etiketleme etkilenmez: video, 2B iskelet ve zaman çizelgesi çalışır."
            )

    def _rebuild(self) -> None:
        self._bone_mesh.upload(bone_segments(self._joints, self._bones).reshape(-1, 3))
        points, indices = joint_points(self._joints)
        if len(points) and self._highlight:
            marked = np.isin(indices, list(self._highlight))
            self._joint_mesh.upload(points[~marked])
            self._marked_mesh.upload(points[marked])
        else:
            self._joint_mesh.upload(points)
            self._marked_mesh.upload(np.zeros((0, 3), dtype=np.float32))
        self._dirty = False

    def paintGL(self) -> None:  # noqa: N802 - Qt naming
        functions = self.context().functions() if self.context() else None
        if functions is None:
            return
        tokens = self._tokens
        background = QColor(tokens.colour("KcSurfaceViewport"))
        functions.glClearColor(
            background.redF(), background.greenF(), background.blueF(), 1.0
        )
        functions.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._program is None:
            return
        if self._dirty:
            self._rebuild()

        functions.glEnable(GL_DEPTH_TEST)
        functions.glEnable(GL_BLEND)
        functions.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        functions.glEnable(GL_VERTEX_PROGRAM_POINT_SIZE)

        aspect = self.width() / max(1, self.height())
        matrix = QMatrix4x4(*[float(v) for v in self.camera.matrix(aspect).flatten()])

        self._program.bind()
        self._program.setUniformValue(self._program.uniformLocation("mvp"), matrix)
        position = self._program.attributeLocation("position")

        self._draw(functions, self._grid, GL_LINES,
                   tokens.colour("KcBorderSubtle"), position, width=1.0)
        self._draw(functions, self._bone_mesh, GL_LINES,
                   tokens.colour("KcAccentPrimary"), position, width=2.5)
        self._draw(functions, self._joint_mesh, GL_POINTS,
                   tokens.colour("KcAccentPrimary"), position, point_size=6.0)
        self._draw(functions, self._marked_mesh, GL_POINTS,
                   tokens.colour("KcStatusRecording"), position, point_size=11.0)
        self._program.release()

    def _draw(
        self,
        functions,  # noqa: ANN001 - QOpenGLFunctions
        mesh: _Mesh,
        mode: int,
        colour: str,
        position: int,
        *,
        width: float = 1.0,
        point_size: float = 1.0,
    ) -> None:
        if mesh.count == 0 or self._program is None:
            return
        rgba = QColor(colour)
        self._program.setUniformValue1f(
            self._program.uniformLocation("point_size"), float(point_size)
        )
        self._program.setUniformValue(
            self._program.uniformLocation("colour"),
            float(rgba.redF()), float(rgba.greenF()), float(rgba.blueF()), 1.0,
        )
        functions.glLineWidth(width)
        mesh.buffer.bind()
        self._program.enableAttributeArray(position)
        self._program.setAttributeBuffer(position, GL_FLOAT, 0, 3, 0)
        functions.glDrawArrays(mode, 0, mesh.count)
        self._program.disableAttributeArray(position)
        mesh.buffer.release()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().paintEvent(event)
        if not (self._unavailable or self._note):
            return
        painter = QPainter(self)
        tokens = self._tokens
        if self._unavailable:
            painter.fillRect(self.rect(), QColor(tokens.colour("KcSurfaceViewport")))
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._unavailable,
            )
        else:
            painter.setPen(QColor(tokens.colour("KcTextSecondary")))
            painter.drawText(
                self.rect().adjusted(8, 8, -8, -8),
                int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                    | Qt.TextFlag.TextWordWrap),
                self._note,
            )
        painter.end()

    # -------------------------------------------------------------- input
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        self._last_pos = event.position()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if self._last_pos is None:
            return
        delta = event.position() - self._last_pos
        self._last_pos = event.position()
        buttons = event.buttons()
        if buttons & Qt.MouseButton.LeftButton:
            self.camera = self.camera.orbit(-delta.x() * 0.01, delta.y() * 0.01)
        elif buttons & (Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton):
            self.camera = self.camera.pan(delta.x(), delta.y())
        else:
            return
        self.camera_changed.emit()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802, ARG002
        self._last_pos = None

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt naming
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.camera = self.camera.zoom(0.88 ** steps)
            self.camera_changed.emit()
            self.update()

    def keyPressEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        if event.key() == Qt.Key.Key_R:
            self.reset_view()
        else:
            super().keyPressEvent(event)


def default_surface_format() -> QSurfaceFormat:
    """A depth buffer, which the scene needs and the default format lacks."""
    fmt = QSurfaceFormat.defaultFormat()
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    return fmt


__all__ = ["Skeleton3DView", "default_surface_format"]
