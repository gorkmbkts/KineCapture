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
from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.studio.theme import ThemeTokens


#: How long a message drawn on the picture stays fully visible, and how long
#: it then takes to disappear. Long enough to read a short sentence from three
#: metres away; short enough that it is gone before the next attempt.
NOTICE_HOLD_MS = 3000
NOTICE_FADE_MS = 600


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
        #: The live framing verdict, and the worst of the last few seconds.
        #: Painted over the picture because the person who needs to read it is
        #: standing in front of the camera, not sitting at the keyboard.
        self._framing = ("", "", "")
        #: A message drawn on the picture for the same reason, which holds for
        #: a few seconds and then fades out by itself.
        self._notice = ("", "")
        self._notice_opacity = 0.0
        self._notice_hold = QTimer(self)
        self._notice_hold.setSingleShot(True)
        self._notice_hold.timeout.connect(self._fade_notice)
        self._notice_fade = QVariantAnimation(self)
        self._notice_fade.setDuration(NOTICE_FADE_MS)
        self._notice_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._notice_fade.valueChanged.connect(self._notice_faded)
        #: The detection the operator picked, in source pixels, or ``None``.
        self._subject_box = None
        #: Where the framing badge was painted this pass, so other overlays
        #: can avoid it. Empty until the first paint.
        self._framing_rect = QRectF()
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

    def show_notice(self, text: str, *, severity: str = "warning") -> None:
        """Put a sentence on the picture, and take it away again.

        Same card as the window's own messages, drawn where the person is
        already looking. It holds for :data:`NOTICE_HOLD_MS` and then fades,
        because somebody three metres from the keyboard cannot dismiss it.
        """
        self._notice = (str(text or ""), str(severity or "warning"))
        self._notice_fade.stop()
        self._notice_opacity = 1.0
        self._notice_hold.start(NOTICE_HOLD_MS)
        self.update()

    def _fade_notice(self) -> None:
        self._notice_fade.stop()
        self._notice_fade.setStartValue(1.0)
        self._notice_fade.setEndValue(0.0)
        self._notice_fade.start()

    def _notice_faded(self, value) -> None:  # noqa: ANN001 - QVariant
        self._notice_opacity = float(value)
        if self._notice_opacity <= 0.0:
            self._notice = ("", "")
        self.update()

    @property
    def notice_text(self) -> str:
        """What is on the picture right now. Empty once it has faded."""
        return self._notice[0] if self._notice_opacity > 0.0 else ""

    def set_subject_box(self, box) -> None:  # noqa: ANN001 - 4-tuple or None
        """Outline the person the operator picked, in source pixels."""
        value = tuple(float(v) for v in box) if box is not None else None
        if value != self._subject_box:
            self._subject_box = value
            self.update()

    def set_framing(self, text: str, state: str, history: str) -> None:
        """Say whether the whole person is in shot, and how the last seconds went."""
        value = (str(text or ""), str(state or ""), str(history or ""))
        if value != self._framing:
            self._framing = value
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
        # The badge goes down first and records where it landed, so the
        # subject tag can step out of its way instead of printing over it.
        self._framing_rect = QRectF()
        if self._framing[0]:
            self._paint_framing(painter, rect)
        if self._subject_box is not None:
            self._paint_subject_box(painter, rect)
        if self._notice[0] and self._notice_opacity > 0.0:
            self._paint_notice(painter, rect)
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

    #: Verdict state -> the token its badge is painted in.
    _FRAMING_COLOURS = {
        "ok": "KcStatusLive",
        "tight": "KcStatusWarning",
        "cut": "KcStatusRecording",
        "crowded": "KcStatusWarning",
        "no_person": "KcTextMuted",
        "no_overlay": "KcTextMuted",
        "no_camera": "KcTextMuted",
    }

    def _paint_framing(self, painter: QPainter, rect: QRectF) -> None:
        """A badge across the top of the picture, sized to be read from 3 m.

        Never mirrored with the image: it is text, and a flipped word is
        unreadable exactly when it matters most.
        """
        text, state, history = self._framing
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = painter.font()
        font.setPointSize(max(13, int(rect.height() / 22)))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        pad = tokens.metric("KcSpacingLg")
        line_height = metrics.height()
        height = line_height + pad * 2
        small_font = QFont(font)
        small_font.setPointSize(max(10, int(font.pointSize() * 0.7)))
        small_font.setBold(False)
        if history:
            height += QFontMetrics(small_font).height()
        width = max(
            metrics.horizontalAdvance(text),
            QFontMetrics(small_font).horizontalAdvance(history) if history else 0,
        ) + pad * 2
        width = min(width, rect.width() - pad * 2)
        badge = QRectF(
            rect.center().x() - width / 2.0, rect.top() + pad, width, height
        )
        self._framing_rect = badge

        background = QColor(tokens.colour("KcSurfaceViewport"))
        background.setAlpha(205)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(
            badge, tokens.metric("KcRadiusRound"), tokens.metric("KcRadiusRound")
        )
        accent = QColor(
            tokens.colour(self._FRAMING_COLOURS.get(state, "KcTextMuted"))
        )
        pen = QPen(accent)
        pen.setWidth(tokens.metric("KcBorderWidthStrong"))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            badge, tokens.metric("KcRadiusRound"), tokens.metric("KcRadiusRound")
        )

        painter.setPen(accent)
        painter.setFont(font)
        top = QRectF(badge.left(), badge.top() + pad, badge.width(), line_height)
        painter.drawText(top, int(Qt.AlignmentFlag.AlignCenter), text)
        if history:
            painter.setPen(QColor(tokens.colour("KcTextSecondary")))
            painter.setFont(small_font)
            below = QRectF(
                badge.left(),
                top.bottom(),
                badge.width(),
                QFontMetrics(small_font).height(),
            )
            painter.drawText(below, int(Qt.AlignmentFlag.AlignCenter), history)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _paint_subject_box(self, painter: QPainter, rect: QRectF) -> None:
        """Outline whoever the operator picked, so the choice is visible.

        "I clicked something" and "the application understood who" are two
        different facts, and until now the screen only ever showed the first.
        """
        assert self._subject_box is not None
        tokens = self._tokens
        x0, y0, x1, y1 = self._subject_box
        box = QRectF(self._to_widget(x0, y0), self._to_widget(x1, y1)).normalized()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(tokens.colour("KcAccentPrimary")))
        pen.setWidth(tokens.metric("KcBorderWidthStrong"))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = tokens.metric("KcRadiusSmall")
        painter.drawRoundedRect(box, radius, radius)

        font = painter.font()
        font.setPointSize(max(9, int(rect.height() / 40)))
        font.setBold(True)
        painter.setFont(font)
        text = "seçilen kişi"
        metrics = painter.fontMetrics()
        pad = tokens.metric("KcSpacingSm")
        # Inside the box, not above it: above put the tag on the same row as
        # the framing badge. And if the badge is there anyway - it is centred,
        # and people stand in the middle of frames - the tag drops below it.
        tag = QRectF(
            box.left() + pad,
            box.top() + pad,
            metrics.horizontalAdvance(text) + pad * 2,
            metrics.height() + pad,
        )
        if tag.intersects(self._framing_rect):
            tag.moveTop(self._framing_rect.bottom() + pad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.colour("KcAccentPrimary")))
        painter.drawRoundedRect(tag, radius, radius)
        painter.setPen(QColor(tokens.colour("KcTextOnAccent")))
        painter.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), text)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    #: Notice severity -> the token its edge is painted in. The same three the
    #: window's own message cards use, so the two read as one system.
    _NOTICE_COLOURS = {
        "info": "KcAccentPrimary",
        "warning": "KcStatusWarning",
        "error": "KcStatusRecording",
    }

    def _paint_notice(self, painter: QPainter, rect: QRectF) -> None:
        """The window's message card, drawn on the picture and fading out."""
        text, severity = self._notice
        tokens = self._tokens
        painter.save()
        painter.setOpacity(self._notice_opacity)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = painter.font()
        font.setPointSize(max(12, int(rect.height() / 26)))
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        pad = tokens.metric("KcSpacingLg")
        width = min(metrics.horizontalAdvance(text) + pad * 3, rect.width() - pad * 2)
        height = metrics.height() + pad * 2
        card = QRectF(
            rect.center().x() - width / 2.0,
            rect.bottom() - height - tokens.metric("KcSpacingXxl"),
            width,
            height,
        )
        radius = tokens.metric("KcRadiusControl")
        background = QColor(tokens.colour("KcSurfaceOverlay"))
        background.setAlpha(238)
        accent = QColor(
            tokens.colour(self._NOTICE_COLOURS.get(severity, "KcStatusWarning"))
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(card, radius, radius)
        pen = QPen(accent)
        pen.setWidth(tokens.metric("KcBorderWidth"))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(card, radius, radius)
        # The coloured edge a message card carries, on the same side.
        painter.fillRect(
            QRectF(card.left(), card.top(), tokens.metric("KcSpacingSm"), card.height()),
            accent,
        )
        painter.setPen(QColor(tokens.colour("KcTextPrimary")))
        painter.drawText(card, int(Qt.AlignmentFlag.AlignCenter), text)
        painter.restore()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

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
