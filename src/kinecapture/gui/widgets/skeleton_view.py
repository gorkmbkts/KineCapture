"""Rotatable 3D skeleton view.

Implemented with ``QPainter`` and an explicit perspective projection rather than
a plotting library or an OpenGL widget. For a stick figure of a few dozen joints
that is fast enough, has no extra dependency, behaves identically under Windows
display scaling, and - importantly - keeps the projection maths visible and
testable instead of hidden inside a framework.

**Display transforms never touch stored data.** Root centring, the axis flips
and the zoom below exist only to produce screen coordinates. The arrays handed
to this widget are the raw capture values and are never modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.domain.models import BodyPose
from kinecapture.gui.theme import Theme
from kinecapture.visualization.skeleton_spec import SkeletonSpec

LOW_CONFIDENCE = 0.4


@dataclass(frozen=True)
class ViewPreset:
    """A named camera orientation."""

    key: str
    label: str
    yaw_deg: float
    pitch_deg: float


VIEW_PRESETS: tuple[ViewPreset, ...] = (
    ViewPreset("front", "Önden", 0.0, 0.0),
    ViewPreset("side", "Yandan", 90.0, 0.0),
    ViewPreset("perspective", "Perspektif", 35.0, 18.0),
    ViewPreset("top", "Üstten", 0.0, 82.0),
)


class SkeletonView3D(QWidget):
    """Orbit-able 3D stick figure with a ground grid.

    Mouse: drag to orbit, wheel to zoom, double-click to reset.
    """

    view_changed = Signal(str)

    def __init__(
        self,
        theme: Theme,
        *,
        preset: str = "perspective",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._spec: Optional[SkeletonSpec] = None
        self._bodies: tuple[BodyPose, ...] = ()
        self._active_id: Optional[int] = None
        self._trail: list[np.ndarray] = []
        self._show_trail = False
        self._root_centered = True
        self._show_confidence = True
        self._placeholder = "İskelet verisi yok"

        current = next((p for p in VIEW_PRESETS if p.key == preset), VIEW_PRESETS[2])
        self._preset_key = current.key
        self._yaw = math.radians(current.yaw_deg)
        self._pitch = math.radians(current.pitch_deg)
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._drag_origin: Optional[QPointF] = None
        self._drag_button: Optional[Qt.MouseButton] = None

        # A floor, not a target: both views carry the layout stretch and
        # take every pixel the controls around them do not need. The floor
        # only decides what happens in a 1120x700 window, where a slightly
        # shorter picture beats a clipped timeline.
        self.setMinimumSize(240, 120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ----------------------------------------------------------------- data
    def set_bodies(
        self,
        bodies: Sequence[BodyPose],
        spec: Optional[SkeletonSpec],
        *,
        active_id: Optional[int] = None,
    ) -> None:
        self._bodies = tuple(bodies)
        self._spec = spec
        self._active_id = active_id
        if self._show_trail:
            body = self._primary_body()
            if body is not None and body.root_position is not None:
                self._trail.append(body.root_position.copy())
                if len(self._trail) > 120:
                    del self._trail[0]
        self.update()

    def clear(self) -> None:
        self._bodies = ()
        self._trail.clear()
        self.update()

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder = text
        self.update()

    # -------------------------------------------------------------- options
    def set_preset(self, key: str) -> None:
        preset = next((p for p in VIEW_PRESETS if p.key == key), None)
        if preset is None:
            return
        self._preset_key = preset.key
        self._yaw = math.radians(preset.yaw_deg)
        self._pitch = math.radians(preset.pitch_deg)
        self._pan = QPointF(0.0, 0.0)
        self.view_changed.emit(preset.key)
        self.update()

    @property
    def preset_key(self) -> str:
        return self._preset_key

    def set_root_centered(self, enabled: bool) -> None:
        """Centre the figure on its root. Display only - data is untouched."""
        self._root_centered = enabled
        self.update()

    def set_show_confidence(self, enabled: bool) -> None:
        self._show_confidence = enabled
        self.update()

    def set_show_trail(self, enabled: bool) -> None:
        self._show_trail = enabled
        if not enabled:
            self._trail.clear()
        self.update()

    def reset_view(self) -> None:
        self.set_preset(self._preset_key)
        self._zoom = 1.0

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    # ---------------------------------------------------------- interaction
    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = QPointF(event.position())
        self._drag_button = event.button()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        delta = QPointF(event.position()) - self._drag_origin
        self._drag_origin = QPointF(event.position())
        if self._drag_button == Qt.MouseButton.RightButton:
            self._pan += delta
        else:
            self._yaw += delta.x() * 0.01
            # Clamped so the figure can never flip upside down mid-drag.
            self._pitch = max(
                -math.pi / 2 + 0.05,
                min(math.pi / 2 - 0.05, self._pitch + delta.y() * 0.01),
            )
            self._preset_key = "free"
            self.view_changed.emit("free")
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        self._drag_button = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.reset_view()

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        self._zoom = float(np.clip(self._zoom * (1.12**steps), 0.25, 6.0))
        self.update()

    # --------------------------------------------------------------- render
    def _primary_body(self) -> Optional[BodyPose]:
        if not self._bodies:
            return None
        if self._active_id is not None:
            for body in self._bodies:
                if body.tracking_id == self._active_id:
                    return body
        return max(self._bodies, key=lambda b: b.valid_joint_ratio)

    def _origin(self) -> np.ndarray:
        """The point the view is centred on. Display-only."""
        if not self._root_centered:
            return np.zeros(3, dtype=np.float32)
        body = self._primary_body()
        if body is None:
            return np.zeros(3, dtype=np.float32)
        if body.root_position is not None and np.isfinite(body.root_position).all():
            return body.root_position.astype(np.float32)
        valid = body.joint_positions_xyz[body.valid_joint_mask]
        if valid.size == 0:
            return np.zeros(3, dtype=np.float32)
        return valid.mean(axis=0).astype(np.float32)

    def _project(self, point: np.ndarray, origin: np.ndarray) -> Optional[QPointF]:
        """World metres -> widget pixels, through yaw/pitch and perspective."""
        if not np.isfinite(point).all():
            return None
        local = point.astype(np.float64) - origin.astype(np.float64)
        x, y, z = float(local[0]), float(local[1]), float(local[2])

        cos_yaw, sin_yaw = math.cos(self._yaw), math.sin(self._yaw)
        xr = x * cos_yaw + z * sin_yaw
        zr = -x * sin_yaw + z * cos_yaw

        cos_pitch, sin_pitch = math.cos(self._pitch), math.sin(self._pitch)
        yr = y * cos_pitch - zr * sin_pitch
        zr = y * sin_pitch + zr * cos_pitch

        # Camera sits 3.2 m back; that plus the clamp keeps a person in frame at
        # the ranges a ZED 2i is typically used at.
        depth = zr + 3.2
        if depth <= 0.15:
            return None
        scale = min(self.width(), self.height()) * 0.55 * self._zoom
        u = self.width() / 2.0 + self._pan.x() + scale * xr / depth
        v = self.height() / 2.0 + self._pan.y() - scale * yr / depth
        return QPointF(u, v)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = self._theme
        painter.fillRect(self.rect(), QColor(theme.bg_sunken))

        origin = self._origin()
        self._paint_grid(painter, origin)

        if self._spec is None or not self._bodies:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder
            )
            painter.end()
            return

        if self._show_trail and len(self._trail) > 1:
            self._paint_trail(painter, origin)

        # Painter's algorithm: furthest body first so the near one wins overlaps.
        ordered = sorted(
            self._bodies,
            key=lambda b: -self._body_depth(b),
        )
        for body in ordered:
            self._paint_body(painter, body, origin)

        self._paint_axes(painter, origin)
        painter.end()

    def _body_depth(self, body: BodyPose) -> float:
        valid = body.joint_positions_xyz[body.valid_joint_mask]
        return float(valid[:, 2].mean()) if valid.size else 0.0

    def _paint_grid(self, painter: QPainter, origin: np.ndarray) -> None:
        """A 4x4 m floor grid at y=0, so scale and orientation are readable."""
        theme = self._theme
        pen = QPen(QColor(theme.grid))
        pen.setWidthF(1.0)
        painter.setPen(pen)

        floor_y = -origin[1] if self._root_centered else 0.0
        extent, step = 2.0, 0.5
        ticks = np.arange(-extent, extent + step / 2, step)
        base_z = origin[2] if self._root_centered else 2.5

        for tick in ticks:
            row_a = self._project(
                np.array([origin[0] - extent, origin[1] + floor_y, base_z + tick]),
                origin,
            )
            row_b = self._project(
                np.array([origin[0] + extent, origin[1] + floor_y, base_z + tick]),
                origin,
            )
            if row_a and row_b:
                painter.drawLine(row_a, row_b)
            col_a = self._project(
                np.array([origin[0] + tick, origin[1] + floor_y, base_z - extent]),
                origin,
            )
            col_b = self._project(
                np.array([origin[0] + tick, origin[1] + floor_y, base_z + extent]),
                origin,
            )
            if col_a and col_b:
                painter.drawLine(col_a, col_b)

    def _paint_axes(self, painter: QPainter, origin: np.ndarray) -> None:
        """A small corner gnomon so the orientation is never ambiguous."""
        theme = self._theme
        painter.save()
        size = 34
        cx, cy = self.width() - size - 18, self.height() - size - 18
        axes = (
            (np.array([1.0, 0.0, 0.0]), theme.skeleton_right, "X"),
            (np.array([0.0, 1.0, 0.0]), theme.success, "Y"),
            (np.array([0.0, 0.0, 1.0]), theme.skeleton_left, "Z"),
        )
        cos_yaw, sin_yaw = math.cos(self._yaw), math.sin(self._yaw)
        cos_pitch, sin_pitch = math.cos(self._pitch), math.sin(self._pitch)
        for vector, colour, label in axes:
            x, y, z = vector
            xr = x * cos_yaw + z * sin_yaw
            zr = -x * sin_yaw + z * cos_yaw
            yr = y * cos_pitch - zr * sin_pitch
            end = QPointF(cx + size * xr, cy - size * yr)
            pen = QPen(QColor(colour))
            pen.setWidthF(1.8)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx, cy), end)
            painter.drawText(end + QPointF(3, 3), label)
        painter.restore()

    def _paint_trail(self, painter: QPainter, origin: np.ndarray) -> None:
        theme = self._theme
        points = [self._project(p, origin) for p in self._trail]
        for index in range(1, len(points)):
            a, b = points[index - 1], points[index]
            if a is None or b is None:
                continue
            colour = QColor(theme.accent)
            colour.setAlpha(int(30 + 170 * index / len(points)))
            pen = QPen(colour)
            pen.setWidthF(1.4)
            painter.setPen(pen)
            painter.drawLine(a, b)

    def _paint_body(
        self, painter: QPainter, body: BodyPose, origin: np.ndarray
    ) -> None:
        spec = self._spec
        assert spec is not None
        if body.num_joints != spec.num_joints:
            return
        is_active = self._active_id is None or body.tracking_id == self._active_id
        points = [
            self._project(body.joint_positions_xyz[i], origin)
            for i in range(spec.num_joints)
        ]

        for a, b in spec.edges:
            pa, pb = points[a], points[b]
            if pa is None or pb is None:
                continue  # never bridge a missing joint
            confidence = min(
                float(body.joint_confidences[a]), float(body.joint_confidences[b])
            )
            colour = QColor(self._side_colour(spec.side_of(a) if spec.side_of(a) != "center" else spec.side_of(b)))
            colour.setAlpha(self._alpha(confidence, is_active))
            pen = QPen(colour)
            pen.setWidthF(3.0 if is_active else 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(pa, pb)

        for index, point in enumerate(points):
            if point is None:
                continue
            confidence = float(body.joint_confidences[index])
            colour = QColor(self._side_colour(spec.side_of(index)))
            colour.setAlpha(self._alpha(confidence, is_active))
            painter.setBrush(colour)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = 4.0 if is_active else 2.6
            if (
                self._show_confidence
                and np.isfinite(confidence)
                and confidence < LOW_CONFIDENCE
            ):
                # A low-confidence joint gets a hollow ring so it is obviously
                # different from a confident one, not merely dimmer.
                painter.setBrush(Qt.BrushStyle.NoBrush)
                ring = QPen(colour)
                ring.setWidthF(1.4)
                painter.setPen(ring)
            painter.drawEllipse(point, radius, radius)

        # Joints the tracker lost are reported as a count, never invented.
        missing = int((~body.valid_joint_mask).sum())
        if missing and is_active:
            painter.setPen(QColor(self._theme.warning))
            painter.drawText(
                10,
                self.height() - 12,
                f"{missing} eklem görülemiyor",
            )

    def _side_colour(self, side: str) -> str:
        return {
            "left": self._theme.skeleton_left,
            "right": self._theme.skeleton_right,
            "center": self._theme.skeleton_center,
        }[side]

    def _alpha(self, confidence: float, is_active: bool) -> int:
        base = 255 if is_active else 110
        if not self._show_confidence or not np.isfinite(confidence):
            return base
        if confidence >= LOW_CONFIDENCE:
            return base
        return int(base * (0.35 + 0.65 * max(0.0, confidence) / LOW_CONFIDENCE))


__all__ = ["LOW_CONFIDENCE", "VIEW_PRESETS", "SkeletonView3D", "ViewPreset"]
