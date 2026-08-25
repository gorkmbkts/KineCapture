"""Colour / depth image view with an optional 2D skeleton overlay.

Two things this widget is careful about:

* **Aspect ratio.** The image is letterboxed, never stretched, so a body's
  proportions on screen match reality.
* **Missing joints.** A joint with non-finite coordinates is not drawn at all,
  and a bone with a missing endpoint is not drawn either. Low-confidence joints
  fade rather than disappearing, so the operator can tell "uncertain" from
  "absent" - two very different situations.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.domain.models import BodyPose
from kinecapture.gui.converters import depth_to_qimage, rgb_to_qimage
from kinecapture.gui.theme import Theme
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Below this confidence a joint is drawn faded rather than solid.
LOW_CONFIDENCE = 0.4


class VideoView(QWidget):
    """Displays one frame plus, optionally, the projected skeleton over it."""

    #: Emitted with the click position in **source image pixels**, so the page
    #: can ask the domain layer who was clicked. The widget deliberately does
    #: not decide that itself: picking a person is a capture decision, not a
    #: painting one.
    clicked = Signal(float, float)

    def __init__(
        self,
        theme: Theme,
        *,
        placeholder_text: str = "Görüntü yok",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._image: Optional[QImage] = None
        self._bodies: tuple[BodyPose, ...] = ()
        self._spec: Optional[SkeletonSpec] = None
        self._active_id: Optional[int] = None
        self._overlay_enabled = True
        self._placeholder_text = placeholder_text
        self._highlight_subject = False
        self._badge_text = ""
        self._badge_colour = ""
        #: Intrinsics used to project 3D joints back onto the image. Filled from
        #: the frame's own geometry: an approximation is honest here because the
        #: overlay is a visual aid, and the 3D view is the metric one.
        self._focal_ratio = 0.75

        self.setMinimumSize(240, 160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(False)

    # ----------------------------------------------------------------- data
    def set_rgb(self, rgb: Optional[np.ndarray]) -> None:
        self._image = rgb_to_qimage(rgb) if rgb is not None else None
        self.update()

    def set_depth(self, depth: Optional[np.ndarray]) -> None:
        self._image = (
            depth_to_qimage(depth, self._theme) if depth is not None else None
        )
        self.update()

    def set_image(self, image: Optional[QImage]) -> None:
        self._image = image
        self.update()

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
        self.update()

    def set_overlay_enabled(self, enabled: bool) -> None:
        self._overlay_enabled = enabled
        self.update()

    def set_highlight_subject(self, enabled: bool) -> None:
        """Draw the selection ring. On during capture, off during review."""
        self._highlight_subject = bool(enabled)
        self.update()

    def set_badge(self, text: str, colour: str = "") -> None:
        """Corner badge - used for the RECORDING dot and the synthetic marker."""
        self._badge_text = text
        self._badge_colour = colour or self._theme.text_secondary
        self.update()

    def set_placeholder_text(self, text: str) -> None:
        self._placeholder_text = text
        self.update()

    def clear(self) -> None:
        self._image = None
        self._bodies = ()
        self.update()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def current_pixmap(self) -> Optional[QPixmap]:
        return QPixmap.fromImage(self._image) if self._image else None

    # ---------------------------------------------------------------- paint
    def widget_to_image(self, x: float, y: float) -> Optional[tuple[float, float]]:
        """Turn a widget coordinate into a source-image pixel.

        Accounts for the letterbox and for whatever scale the image is being
        drawn at, so a click lands on the same pixel at any window size or DPI
        setting. Returns ``None`` for a click on the letterbox bars, which is a
        click on nothing rather than on the nearest edge pixel.
        """
        if self._image is None or self._image.isNull():
            return None
        target = self._letterbox()
        if not target.contains(x, y) or target.width() <= 0 or target.height() <= 0:
            return None
        scale_x = self._image.width() / target.width()
        scale_y = self._image.height() / target.height()
        return ((x - target.left()) * scale_x, (y - target.top()) * scale_y)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.position()
            image_point = self.widget_to_image(point.x(), point.y())
            if image_point is not None:
                self.clicked.emit(image_point[0], image_point[1])
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        theme = self._theme

        painter.fillRect(self.rect(), QColor(theme.bg_sunken))

        if self._image is None or self._image.isNull():
            self._paint_placeholder(painter)
            painter.end()
            return

        target = self._letterbox()
        painter.drawImage(target, self._image)

        if self._overlay_enabled and self._spec is not None and self._bodies:
            self._paint_skeletons(painter, target)

        if self._badge_text:
            self._paint_badge(painter)
        painter.end()

    def _letterbox(self) -> QRectF:
        """The largest rect inside the widget with the image's aspect ratio."""
        assert self._image is not None
        widget_w, widget_h = self.width(), self.height()
        image_w, image_h = self._image.width(), self._image.height()
        if image_w <= 0 or image_h <= 0:
            return QRectF(0, 0, widget_w, widget_h)
        scale = min(widget_w / image_w, widget_h / image_h)
        draw_w, draw_h = image_w * scale, image_h * scale
        return QRectF(
            (widget_w - draw_w) / 2.0, (widget_h - draw_h) / 2.0, draw_w, draw_h
        )

    def _paint_placeholder(self, painter: QPainter) -> None:
        theme = self._theme
        pen = QPen(QColor(theme.border_strong))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        inset = self.rect().adjusted(8, 8, -8, -8)
        painter.drawRoundedRect(inset, theme.radius_md, theme.radius_md)
        painter.setPen(QColor(theme.text_muted))
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder_text
        )

    def _paint_badge(self, painter: QPainter) -> None:
        theme = self._theme
        painter.save()
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(self._badge_text)
        height = metrics.height() + 6
        rect = QRectF(10, 10, text_width + 20, height)
        painter.setBrush(QColor(0, 0, 0, 165))
        painter.setPen(QPen(QColor(self._badge_colour), 1))
        painter.drawRoundedRect(rect, theme.radius_sm, theme.radius_sm)
        painter.setPen(QColor(self._badge_colour))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._badge_text)
        painter.restore()

    # ------------------------------------------------------------- skeleton
    def _project(
        self, point: np.ndarray, target: QRectF
    ) -> Optional[QPointF]:
        """Project a metre-space joint onto the displayed image rectangle."""
        x, y, z = float(point[0]), float(point[1]), float(point[2])
        if not np.isfinite((x, y, z)).all() or z <= 0.05:
            return None
        focal = target.width() * self._focal_ratio
        u = target.center().x() + focal * x / z
        v = target.top() + target.height() * 0.80 - focal * y / z
        if not (target.left() - 40 <= u <= target.right() + 40):
            return None
        if not (target.top() - 40 <= v <= target.bottom() + 40):
            return None
        return QPointF(u, v)

    def _project_2d(
        self, point, target: QRectF
    ) -> Optional[QPointF]:
        """Place a tracker-reported image pixel onto the drawn rectangle.

        Exact, unlike :meth:`_project`: these are the camera's own 2D
        keypoints, so the skeleton lands where the person actually is instead
        of where a guessed focal length would put them.
        """
        if self._image is None or self._image.isNull():
            return None
        u, v = float(point[0]), float(point[1])
        if not np.isfinite((u, v)).all():
            return None
        scale_x = target.width() / max(1, self._image.width())
        scale_y = target.height() / max(1, self._image.height())
        x = target.left() + u * scale_x
        y = target.top() + v * scale_y
        if not (target.left() - 40 <= x <= target.right() + 40):
            return None
        if not (target.top() - 40 <= y <= target.bottom() + 40):
            return None
        return QPointF(x, y)

    def _body_points(self, body, target: QRectF) -> list[Optional[QPointF]]:
        """Screen points for one body, exactly when the tracker gave them."""
        count = body.num_joints
        if body.joint_positions_2d is not None:
            return [
                self._project_2d(body.joint_positions_2d[i], target)
                for i in range(count)
            ]
        return [
            self._project(body.joint_positions_xyz[i], target) for i in range(count)
        ]

    def _paint_skeletons(self, painter: QPainter, target: QRectF) -> None:
        spec = self._spec
        assert spec is not None
        theme = self._theme
        scale = max(0.6, min(2.0, target.width() / 640.0))

        for body in self._bodies:
            if body.num_joints != spec.num_joints:
                continue
            is_active = self._active_id is None or body.tracking_id == self._active_id
            points = self._body_points(body, target)
            if is_active and self._active_id is not None and self._highlight_subject:
                self._paint_subject_halo(painter, points, scale)

            for a, b in spec.edges:
                pa, pb = points[a], points[b]
                if pa is None or pb is None:
                    continue  # a bone with a missing end is not drawn at all
                confidence = min(
                    float(body.joint_confidences[a]), float(body.joint_confidences[b])
                )
                colour = QColor(self._bone_colour(spec, a, b))
                colour.setAlpha(self._alpha(confidence, is_active))
                pen = QPen(colour)
                pen.setWidthF(2.6 * scale if is_active else 1.6 * scale)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(pa, pb)

            for index, point in enumerate(points):
                if point is None:
                    continue
                confidence = float(body.joint_confidences[index])
                colour = QColor(self._joint_colour(spec, index))
                colour.setAlpha(self._alpha(confidence, is_active))
                painter.setBrush(colour)
                painter.setPen(Qt.PenStyle.NoPen)
                radius = (3.4 if is_active else 2.2) * scale
                painter.drawEllipse(point, radius, radius)

            head = self._head_anchor(spec, points)
            if head is not None:
                self._paint_body_label(painter, head, body, is_active)

    def _paint_subject_halo(
        self, painter: QPainter, points: list[Optional[QPointF]], scale: float
    ) -> None:
        """Ring the selected person so the choice is visible at a glance."""
        visible = [point for point in points if point is not None]
        if len(visible) < 2:
            return
        xs = [point.x() for point in visible]
        ys = [point.y() for point in visible]
        margin = 14.0 * scale
        box = QRectF(
            min(xs) - margin,
            min(ys) - margin,
            (max(xs) - min(xs)) + 2 * margin,
            (max(ys) - min(ys)) + 2 * margin,
        )
        painter.save()
        pen = QPen(QColor(self._theme.accent))
        pen.setWidthF(2.4 * scale)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 10.0, 10.0)
        painter.restore()

    def _paint_body_label(
        self, painter: QPainter, anchor: QPointF, body: BodyPose, is_active: bool
    ) -> None:
        theme = self._theme
        text = f"ID {body.tracking_id}"
        if not is_active:
            text += " (pasif)"
        painter.save()
        painter.setPen(
            QColor(theme.accent if is_active else theme.text_muted)
        )
        painter.drawText(anchor + QPointF(8, -8), text)
        painter.restore()

    @staticmethod
    def _head_anchor(
        spec: SkeletonSpec, points: Sequence[Optional[QPointF]]
    ) -> Optional[QPointF]:
        for name in ("head", "neck", "nose", "chest_spine", "pelvis"):
            index = spec.find(name)
            if index is not None and points[index] is not None:
                return points[index]
        return next((p for p in points if p is not None), None)

    @staticmethod
    def _alpha(confidence: float, is_active: bool) -> int:
        """Opacity from confidence. Unknown confidence renders as fully solid."""
        base = 255 if is_active else 120
        if not np.isfinite(confidence):
            return base
        if confidence >= LOW_CONFIDENCE:
            return base
        return int(base * (0.3 + 0.7 * max(0.0, confidence) / LOW_CONFIDENCE))

    def _joint_colour(self, spec: SkeletonSpec, index: int) -> str:
        return {
            "left": self._theme.skeleton_left,
            "right": self._theme.skeleton_right,
            "center": self._theme.skeleton_center,
        }[spec.side_of(index)]

    def _bone_colour(self, spec: SkeletonSpec, a: int, b: int) -> str:
        side_a, side_b = spec.side_of(a), spec.side_of(b)
        side = side_a if side_a != "center" else side_b
        return {
            "left": self._theme.skeleton_left,
            "right": self._theme.skeleton_right,
            "center": self._theme.skeleton_center,
        }[side]


__all__ = ["LOW_CONFIDENCE", "VideoView"]
