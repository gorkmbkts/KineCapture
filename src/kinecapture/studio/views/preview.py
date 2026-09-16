"""The live preview: one image, one overlay, one click target.

Two things this widget is careful about.

**Buffers.** A frame arrives fifteen times a second at 640 pixels wide. The
conversion reuses a pre-allocated array and wraps it in a ``QImage`` without
copying, instead of allocating a new one per frame and leaving the collector to
deal with it.

**Coordinates.** A click has to come back in *source* pixels, not the pixels of
the letterboxed, scaled thing on screen. The offline pass has to find the same
person in the same frame, and a display coordinate means nothing to it.

Painted with ``QPainter`` and no rounding, no shadow, no frame effect: this is
a scientific image, and pixel truth comes before decoration.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.studio.theme import ThemeTokens


class PreviewView(QWidget):
    """Shows the latest frame, draws the light pose on it, reports clicks."""

    clicked = Signal(float, float)  # source-image pixels

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._image: Optional[QImage] = None
        self._buffer: Optional[np.ndarray] = None
        self._source_size: tuple[int, int] = (0, 0)
        self._people: tuple = ()
        self._bones: tuple = ()
        self._recording = False
        self._placeholder = "Kamera bağlı değil"
        # Mirroring is a *display* choice for somebody standing in front of
        # their own camera. It never touches the recording, and a click is
        # un-mirrored before it becomes a source coordinate.
        self._mirrored = False
        self._guides = False
        self._countdown = 0
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Canlı önizleme")

    # ---------------------------------------------------------------- tokens
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_recording(self, recording: bool) -> None:
        """A thin red border while recording - one of three places it is said."""
        if recording != self._recording:
            self._recording = recording
            self.update()

    def set_mirrored(self, mirrored: bool) -> None:
        """Flip the picture left-to-right for somebody facing their own camera.

        The raw recording is untouched: this is the same image, drawn the
        other way round, and :meth:`to_source` undoes it so a click still
        lands on the person the operator pointed at.
        """
        if mirrored != self._mirrored:
            self._mirrored = bool(mirrored)
            self.update()

    def set_guides(self, shown: bool) -> None:
        """Thirds and a head/feet margin, to frame a shot without a second person."""
        if shown != self._guides:
            self._guides = bool(shown)
            self.update()

    def set_countdown(self, seconds: int) -> None:
        """Seconds left before recording starts. 0 hides it."""
        seconds = max(0, int(seconds))
        if seconds != self._countdown:
            self._countdown = seconds
            self.update()

    @property
    def mirrored(self) -> bool:
        return self._mirrored

    # ----------------------------------------------------------------- frame
    def set_frame(self, rgb: Optional[np.ndarray], source_size: tuple[int, int]) -> None:
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
            # Allocated once per resolution, then written into. The QImage
            # below is a view over this buffer and never owns pixels.
            self._buffer = np.empty((height, width, 3), dtype=np.uint8)
            self._image = QImage(
                self._buffer.data, width, height, width * 3, QImage.Format.Format_RGB888
            )
        np.copyto(self._buffer, rgb, casting="unsafe")
        self._source_size = source_size or (width, height)
        self.update()

    def set_people(self, people: tuple, bones: tuple) -> None:
        self._people = people
        self._bones = bones
        self.update()

    # ------------------------------------------------------------- geometry
    def _target_rect(self) -> QRectF:
        """Where the image is drawn: aspect preserved, letterboxed, centred."""
        if self._image is None or self._image.isNull():
            return QRectF(self.rect())
        width, height = self._image.width(), self._image.height()
        if width <= 0 or height <= 0:
            return QRectF(self.rect())
        scale = min(self.width() / width, self.height() / height)
        drawn_w, drawn_h = width * scale, height * scale
        return QRectF(
            (self.width() - drawn_w) / 2, (self.height() - drawn_h) / 2, drawn_w, drawn_h
        )

    def to_source(self, position: QPoint) -> Optional[tuple[float, float]]:
        """Widget pixels -> source-image pixels, or ``None`` outside the image."""
        rect = self._target_rect()
        if self._image is None or not rect.contains(QPointF(position)):
            return None
        fraction_x = (position.x() - rect.left()) / max(1.0, rect.width())
        fraction_y = (position.y() - rect.top()) / max(1.0, rect.height())
        if self._mirrored:
            # Undo the flip: the anchor is stored in *source* pixels, and a
            # mirrored click that was not undone would pick the wrong person
            # in any frame with more than one.
            fraction_x = 1.0 - fraction_x
        source_w, source_h = self._source_size
        return fraction_x * source_w, fraction_y * source_h

    def _to_widget(self, x: float, y: float) -> QPointF:
        rect = self._target_rect()
        source_w, source_h = self._source_size
        fraction_x = x / max(1.0, source_w)
        if self._mirrored:
            fraction_x = 1.0 - fraction_x
        return QPointF(
            rect.left() + fraction_x * rect.width(),
            rect.top() + (y / max(1.0, source_h)) * rect.height(),
        )

    # ---------------------------------------------------------------- events
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        if event.button() is Qt.MouseButton.LeftButton:
            source = self.to_source(event.position().toPoint())
            if source is not None:
                self.clicked.emit(*source)
        super().mousePressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        tokens = self._tokens
        painter.fillRect(self.rect(), QColor(tokens.colour("KcSurfaceViewport")))

        if self._image is None or self._image.isNull():
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            painter.end()
            return

        rect = self._target_rect()
        if self._mirrored:
            painter.save()
            painter.translate(rect.center())
            painter.scale(-1.0, 1.0)
            painter.translate(-rect.center())
            painter.drawImage(rect, self._image)
            painter.restore()
        else:
            painter.drawImage(rect, self._image)
        self._paint_people(painter)
        if self._guides:
            self._paint_guides(painter, rect)
        if self._countdown:
            self._paint_countdown(painter, rect)
        if self._recording:
            pen = QPen(QColor(tokens.colour("KcStatusRecording")))
            pen.setWidth(tokens.metric("KcSpacingXs"))
            painter.setPen(pen)
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.end()

    def _paint_guides(self, painter: QPainter, rect: QRectF) -> None:
        """Thirds, plus the margin a whole body needs at the top and bottom.

        A framing aid and nothing more: it makes no claim about whether a head
        or a foot is actually in shot, because nothing here has measured that.
        """
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        line = QColor(tokens.colour("KcTextOnAccent"))
        line.setAlpha(70)
        pen = QPen(line)
        pen.setWidth(1)
        painter.setPen(pen)
        for index in (1, 2):
            x = rect.left() + rect.width() * index / 3.0
            y = rect.top() + rect.height() * index / 3.0
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        margin = QColor(tokens.colour("KcStatusWarning"))
        margin.setAlpha(110)
        pen = QPen(margin)
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        for fraction in (0.08, 0.92):
            y = rect.top() + rect.height() * fraction
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _paint_countdown(self, painter: QPainter, rect: QRectF) -> None:
        """The number, big enough to read from where the athlete is standing."""
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = painter.font()
        font.setPointSize(max(48, int(rect.height() / 5)))
        font.setBold(True)
        painter.setFont(font)
        shadow = QColor(tokens.colour("KcSurfaceViewport"))
        shadow.setAlpha(150)
        painter.fillRect(rect, shadow)
        painter.setPen(QColor(tokens.colour("KcStatusRecording")))
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignCenter), str(self._countdown)
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _paint_people(self, painter: QPainter) -> None:
        if not self._people:
            return
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bone_pen = QPen(QColor(tokens.colour("KcAccentPrimary")))
        bone_pen.setWidth(2)
        box_pen = QPen(QColor(tokens.colour("KcStatusLive")))
        box_pen.setWidth(1)
        for person in self._people:
            points = np.asarray(person.points, dtype=np.float32)
            painter.setPen(bone_pen)
            for start, end in self._bones:
                if start >= len(points) or end >= len(points):
                    continue
                a, b = points[start], points[end]
                if not (np.isfinite(a).all() and np.isfinite(b).all()):
                    continue
                painter.drawLine(self._to_widget(*a), self._to_widget(*b))
            box = np.asarray(person.bbox, dtype=np.float32).reshape(2, 2)
            painter.setPen(box_pen)
            top_left = self._to_widget(*box[0])
            bottom_right = self._to_widget(*box[1])
            painter.drawRect(QRectF(top_left, bottom_right))


__all__ = ["PreviewView"]
