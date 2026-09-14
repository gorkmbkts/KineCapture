"""The labelling screen's picture: one frame, with the skeleton on it.

Drawn in *source* pixels. The proxy video is a downscale of the camera image,
so the frame is letterboxed into the widget and every joint is placed by the
same mapping - the overlay cannot drift from the picture because both come
from one rectangle.

Three things are deliberately visible rather than implied:

* A joint the tracker did not produce is **not drawn**. An absent joint is not
  the origin, and a skeleton silently pinned to (0, 0) is the most convincing
  wrong picture this screen could show.
* A joint whose confidence is low is drawn hollow, so a coach can see that the
  pose under a label is weak before they trust it.
* When there is no video at all, the reason is written in the middle of the
  viewport instead of a black rectangle that looks like a bug.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.studio.theme import ThemeTokens

#: Below this the joint is drawn hollow. Not a validity threshold - nothing is
#: dropped because of it; it only changes how the joint looks.
WEAK_CONFIDENCE = 0.5


class ReviewViewer(QWidget):
    """One frame of the review proxy with the tracked skeleton over it."""

    clicked = Signal(float, float)  # source-image pixels

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._image: Optional[QImage] = None
        self._buffer: Optional[np.ndarray] = None
        self._source_size: tuple[int, int] = (0, 0)
        self._points: Optional[np.ndarray] = None
        self._confidence: Optional[np.ndarray] = None
        self._bones: tuple[tuple[int, int], ...] = ()
        self._highlight: frozenset[int] = frozenset()
        self._placeholder = "Görüntü yok"
        self._badge = ""
        self._overlay_note = ""
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("İnceleme görüntüsü")

    # ---------------------------------------------------------------- tokens
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    # ----------------------------------------------------------------- state
    def set_placeholder(self, text: str) -> None:
        """What to say when there is no picture. Always a reason, never blank."""
        self._placeholder = text
        self.update()

    def set_badge(self, text: str) -> None:
        """A corner tag - "kırpma önizlemesi", "3 kare geri". Empty hides it."""
        if text != self._badge:
            self._badge = text
            self.update()

    def set_overlay_note(self, text: str) -> None:
        """Why the skeleton is absent, when the frame itself is fine."""
        if text != self._overlay_note:
            self._overlay_note = text
            self.update()

    def set_frame(
        self, rgb: Optional[np.ndarray], source_size: Optional[tuple[int, int]] = None
    ) -> None:
        if rgb is None:
            self._image = None
            self.update()
            return
        height, width = rgb.shape[:2]
        if (
            self._buffer is None
            or self._buffer.shape != (height, width, 3)
            or self._buffer.dtype != np.uint8
        ):
            # One allocation per resolution. The QImage is a view over this
            # buffer, so scrubbing does not allocate a megabyte per frame.
            self._buffer = np.empty((height, width, 3), dtype=np.uint8)
            self._image = QImage(
                self._buffer.data, width, height, width * 3, QImage.Format.Format_RGB888
            )
        np.copyto(self._buffer, rgb, casting="unsafe")
        self._source_size = source_size or (width, height)
        self.update()

    def set_skeleton(
        self,
        points: Optional[np.ndarray],
        bones: Sequence[tuple[int, int]] = (),
        confidence: Optional[np.ndarray] = None,
    ) -> None:
        """``points`` is ``[J, 2]`` in source pixels; NaN where there is none."""
        self._points = None if points is None else np.asarray(points, dtype=np.float32)
        self._confidence = (
            None if confidence is None else np.asarray(confidence, dtype=np.float32)
        )
        self._bones = tuple(bones)
        self.update()

    def set_highlight(self, joints: Sequence[int]) -> None:
        """Joints named by the selected error interval, drawn in the error colour."""
        highlight = frozenset(int(i) for i in joints)
        if highlight != self._highlight:
            self._highlight = highlight
            self.update()

    # ------------------------------------------------------------- geometry
    def _target_rect(self) -> QRectF:
        """Where the frame is drawn: aspect preserved, letterboxed, centred."""
        if self._image is None or self._image.isNull():
            return QRectF(self.rect())
        width, height = self._image.width(), self._image.height()
        if width <= 0 or height <= 0:
            return QRectF(self.rect())
        scale = min(self.width() / width, self.height() / height)
        drawn_w, drawn_h = width * scale, height * scale
        return QRectF(
            (self.width() - drawn_w) / 2,
            (self.height() - drawn_h) / 2,
            drawn_w,
            drawn_h,
        )

    def _to_widget(self, x: float, y: float) -> QPointF:
        rect = self._target_rect()
        source_w, source_h = self._source_size
        return QPointF(
            rect.left() + (x / max(1.0, source_w)) * rect.width(),
            rect.top() + (y / max(1.0, source_h)) * rect.height(),
        )

    def to_source(self, position) -> Optional[tuple[float, float]]:  # noqa: ANN001
        rect = self._target_rect()
        if self._image is None or not rect.contains(QPointF(position)):
            return None
        fraction_x = (position.x() - rect.left()) / max(1.0, rect.width())
        fraction_y = (position.y() - rect.top()) / max(1.0, rect.height())
        source_w, source_h = self._source_size
        return fraction_x * source_w, fraction_y * source_h

    # ---------------------------------------------------------------- events
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() is Qt.MouseButton.LeftButton:
            source = self.to_source(event.position().toPoint())
            if source is not None:
                self.clicked.emit(*source)
        super().mousePressEvent(event)

    # --------------------------------------------------------------- drawing
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        tokens = self._tokens
        painter.fillRect(self.rect(), QColor(tokens.colour("KcSurfaceViewport")))

        if self._image is None or self._image.isNull():
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._placeholder,
            )
            painter.end()
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(self._target_rect(), self._image)
        self._paint_skeleton(painter)
        self._paint_note(painter)
        self._paint_badge(painter)
        painter.end()

    def _paint_skeleton(self, painter: QPainter) -> None:
        points = self._points
        if points is None or points.ndim != 2 or points.shape[1] != 2:
            return
        tokens = self._tokens
        finite = np.isfinite(points).all(axis=1)
        if not finite.any():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bone = QPen(QColor(tokens.colour("KcAccentPrimary")))
        bone.setWidth(2)
        bone.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bone)
        for start, end in self._bones:
            if start >= len(points) or end >= len(points):
                continue
            if not (finite[start] and finite[end]):
                continue
            painter.drawLine(self._to_widget(*points[start]), self._to_widget(*points[end]))

        accent = QColor(tokens.colour("KcAccentPrimary"))
        marked = QColor(tokens.colour("KcStatusRecording"))
        viewport = QColor(tokens.colour("KcSurfaceViewport"))
        confidence = self._confidence
        for index in np.nonzero(finite)[0]:
            highlighted = int(index) in self._highlight
            colour = marked if highlighted else accent
            weak = (
                confidence is not None
                and index < len(confidence)
                and np.isfinite(confidence[index])
                and confidence[index] < WEAK_CONFIDENCE
            )
            radius = 4.0 if highlighted else 3.0
            painter.setPen(QPen(colour, 2 if highlighted else 1))
            painter.setBrush(QBrush(viewport if weak else colour))
            painter.drawEllipse(self._to_widget(*points[index]), radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _paint_note(self, painter: QPainter) -> None:
        if not self._overlay_note:
            return
        tokens = self._tokens
        rect = self._target_rect().adjusted(8, 0, -8, -8)
        painter.setPen(QColor(tokens.colour("KcTextSecondary")))
        font = QFont(painter.font())
        font.setPointSize(max(7, tokens.font_size("KcFontSizeSm")))
        painter.setFont(font)
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                | Qt.TextFlag.TextWordWrap),
            self._overlay_note,
        )

    def _paint_badge(self, painter: QPainter) -> None:
        if not self._badge:
            return
        tokens = self._tokens
        font = QFont(painter.font())
        font.setPointSize(max(7, tokens.font_size("KcFontSizeSm")))
        painter.setFont(font)
        metrics = painter.fontMetrics()
        padding = tokens.metric("KcSpacingSm")
        width = metrics.horizontalAdvance(self._badge) + padding * 2
        height = metrics.height() + padding
        rect = QRectF(self._target_rect().left() + 8, self._target_rect().top() + 8,
                      width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(tokens.colour("KcAccentPrimary"))))
        painter.drawRect(rect)
        painter.setPen(QColor(tokens.colour("KcTextOnAccent")))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._badge)


__all__ = ["ReviewViewer", "WEAK_CONFIDENCE"]
