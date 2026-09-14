"""The labelling timeline.

Written to feel like a video editor and to repaint inside 16 ms on an hour-long
session. Those two goals are the same goal: an editor feels good because
nothing lags behind the mouse.

How the budget is met
---------------------

*Nothing is computed per pixel at paint time.* The lanes are drawn from the
multi-resolution summary built during processing (F3), which already holds
min/max per bin at every zoom level. Picking a level and slicing it is one
array operation; the old timeline walked a column at a time and cost 292 ms.

*Static layers are cached in a pixmap.* Ruler, lane grounds and the summary
lanes only change when the view range, the size or the theme changes. Moving
the playhead - which happens on every frame of playback - repaints the cached
image plus two thin overlays.

*The intervals are drawn, not widgeted.* One ``paintEvent``, no child widgets,
so a take with three hundred movements costs three hundred rectangles rather
than three hundred objects.

Interaction it owns
-------------------

Drag to scrub. Ctrl+wheel to zoom with the playhead pinned - the frame under
the cursor stays put, which is what makes zooming feel like a camera rather
than a jump. Middle-drag to pan. Drag an interval's edge to trim, with the
frame under the edge shown live while the mouse is down and **one** write when
it is released: the repository hears about a drag once, not sixty times, so
one drag is one undo step.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Sequence

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.processing.summary import (
    FLAG_CAPTURE_UNMATCHED,
    FLAG_INTEGRITY_ISSUE,
    FLAG_SUBJECT_AMBIGUOUS,
)
from kinecapture.studio.theme import ThemeTokens

#: Left gutter holding the lane names. Fixed, so the labels never move while
#: the content scrolls under them.
GUTTER = 96

#: Lane heights, top to bottom.
_RULER_H = 22
_LANE_H = {
    "video": 16,
    "confidence": 30,
    "qc": 12,
    "subject": 12,
    "movements": 34,
    "errors": 28,
}
_LANE_GAP = 3

#: The smallest span the view may zoom to. Below a few frames the ruler stops
#: meaning anything and dragging becomes unusable.
_MIN_SPAN = 6.0

#: A drag shorter than this is a click, and keeps the old scrub behaviour.
_DRAG_THRESHOLD_PX = 4


class Tool(str, Enum):
    """What a drag on empty space does."""

    SCRUB = "scrub"
    DRAW_MOVEMENT = "draw_movement"
    DRAW_ERROR = "draw_error"


class _Grab(str, Enum):
    NONE = "none"
    SCRUB = "scrub"
    PAN = "pan"
    DRAW = "draw"
    MOVE = "move"
    TRIM_START = "trim_start"
    TRIM_END = "trim_end"


@dataclass
class Interval:
    """One drawable band. The timeline knows nothing about labels."""

    key: str
    start: int
    end: int
    lane: str                 # "movements" | "errors"
    text: str = ""
    status: str = "neutral"   # neutral | ready | warning | error
    parent: str = ""          # owning movement, for an error interval


@dataclass
class _Drag:
    grab: _Grab
    key: str = ""
    origin_x: float = 0.0
    origin_frame: float = 0.0
    origin_view: float = 0.0
    start: int = 0
    end: int = 0
    anchor: int = 0
    moved: bool = False


class TimelineView(QWidget):
    """The multi-lane timeline. Emits intent; it never edits anything itself."""

    position_changed = Signal(int)
    #: While a trim is in progress: the frame under the edge being dragged.
    preview_position = Signal(int)
    edit_started = Signal()
    edit_cancelled = Signal()
    #: (key, start, end) - one signal per completed drag, so one undo step.
    interval_changed = Signal(str, int, int)
    interval_drawn = Signal(str, int, int)   # lane, start, end
    selection_changed = Signal(str)
    interval_activated = Signal(str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._frames = 0
        self._fps = 30.0
        self._position = 0
        self._view_start = 0.0
        self._view_span = 1.0
        self._intervals: list[Interval] = []
        self._selected = ""
        self._tool = Tool.SCRUB
        self._active_movement = ""
        self._drag: Optional[_Drag] = None
        self._snap = True

        #: Callable returning decimated lane data for a view range, or None.
        self.lane_source: Optional[Callable[[float, float, int], dict[str, Any]]] = None
        self._static: Optional[QPixmap] = None
        self._static_key: tuple = ()

        self.setMinimumHeight(
            _RULER_H + sum(_LANE_H.values()) + _LANE_GAP * (len(_LANE_H) + 1)
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Zaman çizelgesi")

    # ------------------------------------------------------------------ data
    def set_take(self, frames: int, fps: float) -> None:
        self._frames = max(0, int(frames))
        self._fps = fps if fps > 0 else 30.0
        self._view_start = 0.0
        self._view_span = float(max(1, self._frames))
        self._position = 0
        self._invalidate()

    def set_intervals(self, intervals: Sequence[Interval]) -> None:
        self._intervals = list(intervals)
        self._invalidate()

    def set_position(self, position: int) -> None:
        clamped = max(0, min(self._frames - 1, int(position)))
        if clamped == self._position:
            return
        self._position = clamped
        # Only the overlay moves; the cached layers are untouched. This is the
        # path that runs on every frame of playback.
        self.update()

    def set_selected(self, key: str) -> None:
        if key != self._selected:
            self._selected = key
            self.update()

    def set_active_movement(self, key: str) -> None:
        """Which movement an error interval would be drawn into."""
        if key != self._active_movement:
            self._active_movement = key
            self._invalidate()

    def set_tool(self, tool: Tool) -> None:
        self._tool = tool
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if tool is not Tool.SCRUB
            else Qt.CursorShape.ArrowCursor
        )

    def set_snap(self, enabled: bool) -> None:
        self._snap = bool(enabled)

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._invalidate()

    # --------------------------------------------------------------- reading
    @property
    def position(self) -> int:
        return self._position

    @property
    def tool(self) -> Tool:
        return self._tool

    @property
    def view_range(self) -> tuple[float, float]:
        return self._view_start, self._view_span

    @property
    def selected(self) -> str:
        return self._selected

    # ----------------------------------------------------------------- zoom
    def zoom(self, factor: float, *, at_frame: Optional[float] = None) -> None:
        """Zoom about ``at_frame``, keeping that frame under the same pixel.

        Anchoring is what makes zoom feel like moving a camera. Without it the
        view jumps and the annotator has to find their place again.
        """
        if self._frames <= 0:
            return
        anchor = self._position if at_frame is None else at_frame
        span = max(_MIN_SPAN, min(float(self._frames), self._view_span * factor))
        fraction = (
            (anchor - self._view_start) / self._view_span if self._view_span else 0.5
        )
        start = anchor - fraction * span
        self._set_view(start, span)

    def zoom_to(self, start: int, end: int, *, padding: float = 0.12) -> None:
        first, last = (start, end) if start <= end else (end, start)
        span = max(_MIN_SPAN, (last - first + 1) * (1.0 + padding * 2))
        self._set_view(first - span * padding, span)

    def zoom_all(self) -> None:
        self._set_view(0.0, float(max(1, self._frames)))

    def _set_view(self, start: float, span: float) -> None:
        span = max(_MIN_SPAN, min(float(max(1, self._frames)), span))
        start = max(0.0, min(float(self._frames) - span, start))
        if (start, span) == (self._view_start, self._view_span):
            return
        self._view_start, self._view_span = start, span
        self._invalidate()

    # ------------------------------------------------------------- geometry
    def _plot_width(self) -> float:
        return max(1.0, float(self.width() - GUTTER))

    def _frame_to_x(self, frame: float) -> float:
        return GUTTER + (frame - self._view_start) / self._view_span * self._plot_width()

    def _x_to_frame(self, x: float) -> float:
        return self._view_start + (x - GUTTER) / self._plot_width() * self._view_span

    def _frame_at(self, x: float) -> int:
        frame = int(round(self._x_to_frame(x)))
        return max(0, min(self._frames - 1, frame))

    def _lane_rects(self) -> dict[str, QRectF]:
        rects: dict[str, QRectF] = {}
        y = float(_LANE_GAP)
        rects["ruler"] = QRectF(0, y, self.width(), _RULER_H)
        y += _RULER_H + _LANE_GAP
        for name, height in _LANE_H.items():
            rects[name] = QRectF(0, y, self.width(), height)
            y += height + _LANE_GAP
        return rects

    @staticmethod
    def _plot(rect: QRectF) -> QRectF:
        return QRectF(GUTTER, rect.top(), rect.width() - GUTTER, rect.height())

    # -------------------------------------------------------------- painting
    def _invalidate(self) -> None:
        self._static = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._invalidate()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        if self._frames <= 0:
            painter.fillRect(self.rect(), QColor(self._tokens.colour("KcSurfaceBase")))
            painter.setPen(QColor(self._tokens.colour("KcTextMuted")))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Zaman çizelgesi boş"
            )
            painter.end()
            return

        key = (
            self.width(),
            self.height(),
            round(self._view_start, 3),
            round(self._view_span, 3),
            self._tokens.name,
            len(self._intervals),
            self._active_movement,
            id(self.lane_source),
        )
        if self._static is None or self._static_key != key:
            self._static = self._render_static()
            self._static_key = key
        painter.drawPixmap(0, 0, self._static)

        # Only these two move with the mouse.
        self._paint_selection(painter)
        self._paint_playhead(painter)
        self._paint_drag(painter)
        painter.end()

    def _render_static(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QColor(self._tokens.colour("KcSurfaceBase")))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        lanes = self._lane_rects()
        self._paint_ruler(painter, lanes["ruler"])
        self._paint_summary_lanes(painter, lanes)
        self._paint_intervals(painter, lanes)
        self._paint_gutter(painter, lanes)
        painter.end()
        return pixmap

    def _paint_gutter(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        tokens = self._tokens
        painter.fillRect(
            QRectF(0, 0, GUTTER, self.height()),
            QColor(tokens.colour("KcSurfaceRaised")),
        )
        painter.setPen(QPen(QColor(tokens.colour("KcBorderSubtle"))))
        painter.drawLine(QPointF(GUTTER, 0), QPointF(GUTTER, self.height()))
        font = painter.font()
        font.setPointSize(max(7, tokens.font_size("KcFontSizeXs")))
        painter.setFont(font)
        painter.setPen(QColor(tokens.colour("KcTextMuted")))
        captions = {
            "video": "Video",
            "confidence": "Güven",
            "qc": "QC",
            "subject": "Kişi",
            "movements": "Hareket",
            "errors": "Hata",
        }
        for name, caption in captions.items():
            rect = lanes[name]
            painter.drawText(
                QRectF(6, rect.top(), GUTTER - 12, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                caption,
            )

    def _paint_ruler(self, painter: QPainter, lane: QRectF) -> None:
        tokens = self._tokens
        font = painter.font()
        font.setPointSize(max(7, tokens.font_size("KcFontSizeXs")))
        painter.setFont(font)
        seconds_per_px = self._view_span / self._fps / self._plot_width()
        step = _nice_step(seconds_per_px * 90.0)
        step_frames = max(1.0, step * self._fps)
        tick = int(self._view_start // step_frames) * step_frames
        while tick <= self._view_start + self._view_span:
            x = self._frame_to_x(tick)
            if GUTTER <= x <= self.width():
                painter.setPen(QPen(QColor(tokens.colour("KcBorderStrong"))))
                painter.drawLine(
                    QPointF(x, lane.bottom() - 5), QPointF(x, lane.bottom())
                )
                painter.setPen(QColor(tokens.colour("KcTextMuted")))
                painter.drawText(QPointF(x + 3, lane.top() + 11), _timecode(tick, self._fps))
            tick += step_frames

    def _paint_summary_lanes(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        """Draw the four data lanes as four images, built with NumPy.

        The obvious implementation - one ``fillRect`` per bin per lane - was
        measured at 25-33 ms for a full hour-long view, because a 1600-pixel
        lane is about 1700 bins and four lanes is nearly seven thousand calls
        from Python into Qt. Building each lane as an array and blitting it
        once is four calls, and the arithmetic happens in NumPy where it costs
        almost nothing.
        """
        tokens = self._tokens
        for name in ("video", "confidence", "qc", "subject"):
            painter.fillRect(
                self._plot(lanes[name]), QColor(tokens.colour("KcSurfaceViewport"))
            )
        if self.lane_source is None:
            return
        width = int(self._plot_width())
        if width <= 0:
            return
        data = self.lane_source(self._view_start, self._view_span, width)
        if not data or not data.get("bins"):
            return

        # One bin index per pixel column, computed once and reused by every lane.
        bin_frames = float(data["bin_frames"])
        first_bin = int(data["first_bin"])
        count = int(data["bins"])
        columns = np.arange(width, dtype=np.float64)
        frames = self._view_start + columns / width * self._view_span
        index = np.floor(frames / bin_frames).astype(np.int64) - first_bin
        inside = (index >= 0) & (index < count)
        index = np.clip(index, 0, max(0, count - 1))

        present_any = np.asarray(data["present_any"])[index] & inside
        present_all = np.asarray(data["present_all"])[index].astype(bool) & inside
        conf_min = np.asarray(data["confidence_min"], dtype=np.float32)[index]
        conf_max = np.asarray(data["confidence_max"], dtype=np.float32)[index]
        flags = np.asarray(data["flags"])[index] * inside

        self._blit_solid(
            painter, lanes["video"], width, inside,
            tokens.colour("KcAccentMuted"), tokens.colour("KcSurfaceViewport"),
        )
        self._blit_subject(painter, lanes["subject"], width, present_any, present_all)
        self._blit_confidence(painter, lanes["confidence"], width, conf_min, conf_max)
        self._blit_flags(painter, lanes["qc"], width, flags)

    # -- lane images ---------------------------------------------------------
    @staticmethod
    def _rgba(colour: str) -> tuple[int, int, int, int]:
        value = QColor(colour)
        return value.red(), value.green(), value.blue(), value.alpha()

    def _blit(self, painter: QPainter, rect: QRectF, image_array: np.ndarray) -> None:
        height, width = image_array.shape[:2]
        image = QImage(
            image_array.data, width, height, width * 4, QImage.Format.Format_RGBA8888
        )
        # The array must outlive the draw: QImage does not copy.
        painter.drawImage(QRectF(GUTTER, rect.top(), width, rect.height()), image)

    def _blit_solid(
        self,
        painter: QPainter,
        rect: QRectF,
        width: int,
        mask: np.ndarray,
        on_colour: str,
        off_colour: str,
    ) -> None:
        height = max(1, int(rect.height()))
        buffer = np.empty((height, width, 4), dtype=np.uint8)
        buffer[:, :] = self._rgba(off_colour)
        buffer[:, mask] = self._rgba(on_colour)
        self._blit(painter, rect, buffer)

    def _blit_subject(
        self,
        painter: QPainter,
        rect: QRectF,
        width: int,
        present_any: np.ndarray,
        present_all: np.ndarray,
    ) -> None:
        """Three states, not two: every frame, some frames, no frames.

        A bin where the subject appears in half the frames is neither present
        nor absent, and painting it as either would hide a tracking gap.
        """
        tokens = self._tokens
        height = max(1, int(rect.height()))
        buffer = np.empty((height, width, 4), dtype=np.uint8)
        buffer[:, :] = self._rgba(tokens.colour("KcSurfaceViewport"))
        partial = present_any & ~present_all
        buffer[:, partial] = self._rgba(tokens.colour("KcStatusWarning"))
        buffer[:, present_all] = self._rgba(tokens.colour("KcStatusLive"))
        self._blit(painter, rect, buffer)

    def _blit_confidence(
        self,
        painter: QPainter,
        rect: QRectF,
        width: int,
        low: np.ndarray,
        high: np.ndarray,
    ) -> None:
        """A min/max band per column, like an audio waveform.

        Both ends are kept because a single bad frame inside an otherwise good
        second is exactly what the annotator is hunting for, and a mean would
        erase it.
        """
        tokens = self._tokens
        height = max(1, int(rect.height()))
        buffer = np.empty((height, width, 4), dtype=np.uint8)
        buffer[:, :] = self._rgba(tokens.colour("KcSurfaceViewport"))

        measured = np.isfinite(low) & np.isfinite(high)
        # Unmeasured is its own colour. Not zero confidence - nothing was
        # measured there at all, and the two must not look the same.
        buffer[:, ~measured] = self._rgba(tokens.colour("KcSurfaceControl"))

        scale = height - 1
        top = np.clip(((1.0 - np.nan_to_num(high, nan=0.0)) * scale), 0, scale).astype(np.int32)
        bottom = np.clip(((1.0 - np.nan_to_num(low, nan=0.0)) * scale), 0, scale).astype(np.int32)
        rows = np.arange(height, dtype=np.int32)[:, None]
        band = (rows >= top[None, :]) & (rows <= bottom[None, :]) & measured[None, :]
        buffer[band] = self._rgba(tokens.colour("KcAccentPrimary"))
        self._blit(painter, rect, buffer)

    def _blit_flags(
        self, painter: QPainter, rect: QRectF, width: int, flags: np.ndarray
    ) -> None:
        tokens = self._tokens
        height = max(1, int(rect.height()))
        buffer = np.empty((height, width, 4), dtype=np.uint8)
        buffer[:, :] = self._rgba(tokens.colour("KcSurfaceViewport"))
        serious = (flags & (FLAG_CAPTURE_UNMATCHED | FLAG_INTEGRITY_ISSUE)) != 0
        ambiguous = (flags & FLAG_SUBJECT_AMBIGUOUS) != 0
        buffer[:, ambiguous] = self._rgba(tokens.colour("KcStatusWarning"))
        buffer[:, serious] = self._rgba(tokens.colour("KcStatusRecording"))
        self._blit(painter, rect, buffer)

    def _paint_intervals(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        tokens = self._tokens
        for name in ("movements", "errors"):
            painter.fillRect(
                self._plot(lanes[name]), QColor(tokens.colour("KcSurfaceViewport"))
            )
        font = painter.font()
        font.setPointSize(max(7, tokens.font_size("KcFontSizeXs")))
        painter.setFont(font)
        metrics = QFontMetrics(font)

        fills = {
            "neutral": tokens.colour("KcSurfaceControlActive"),
            "ready": tokens.colour("KcStatusLiveMuted"),
            "warning": tokens.colour("KcStatusWarningMuted"),
            "error": tokens.colour("KcStatusRecordingMuted"),
        }
        edges = {
            "neutral": tokens.colour("KcBorderStrong"),
            "ready": tokens.colour("KcStatusLive"),
            "warning": tokens.colour("KcStatusWarning"),
            "error": tokens.colour("KcStatusRecording"),
        }

        for interval in self._intervals:
            lane = lanes.get(interval.lane)
            if lane is None:
                continue
            if interval.end < self._view_start or interval.start > self._view_start + self._view_span:
                continue
            left = max(GUTTER, self._frame_to_x(interval.start))
            right = min(float(self.width()), self._frame_to_x(interval.end + 1))
            if right <= left:
                right = left + 1.0
            rect = QRectF(left, lane.top() + 2, right - left, lane.height() - 4)
            dimmed = (
                interval.lane == "errors"
                and self._active_movement
                and interval.parent != self._active_movement
            )
            fill = QColor(fills.get(interval.status, fills["neutral"]))
            if dimmed:
                fill.setAlpha(70)
            painter.fillRect(rect, fill)
            pen = QPen(QColor(edges.get(interval.status, edges["neutral"])))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(rect)
            if interval.text and rect.width() > 26:
                painter.setPen(QColor(tokens.colour("KcTextPrimary")))
                painter.drawText(
                    rect.adjusted(4, 0, -4, 0),
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    metrics.elidedText(
                        interval.text, Qt.TextElideMode.ElideRight, int(rect.width()) - 8
                    ),
                )

    def _paint_selection(self, painter: QPainter) -> None:
        if not self._selected:
            return
        interval = self._interval(self._selected)
        if interval is None:
            return
        lane = self._lane_rects().get(interval.lane)
        if lane is None:
            return
        left = max(GUTTER, self._frame_to_x(interval.start))
        right = min(float(self.width()), self._frame_to_x(interval.end + 1))
        pen = QPen(QColor(self._tokens.colour("KcAccentPrimary")))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(left, lane.top() + 1, max(2.0, right - left), lane.height() - 2))

    def _paint_playhead(self, painter: QPainter) -> None:
        x = self._frame_to_x(self._position)
        if not (GUTTER <= x <= self.width()):
            return
        pen = QPen(QColor(self._tokens.colour("KcStatusRecording")))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

    def _paint_drag(self, painter: QPainter) -> None:
        drag = self._drag
        if drag is None or drag.grab not in (_Grab.DRAW, _Grab.TRIM_START, _Grab.TRIM_END, _Grab.MOVE):
            return
        left = max(GUTTER, self._frame_to_x(min(drag.start, drag.end)))
        right = min(float(self.width()), self._frame_to_x(max(drag.start, drag.end) + 1))
        pen = QPen(QColor(self._tokens.colour("KcFocusRing")))
        pen.setWidth(1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(left, 0, max(2.0, right - left), self.height()))

    # ----------------------------------------------------------------- input
    def _interval(self, key: str) -> Optional[Interval]:
        return next((i for i in self._intervals if i.key == key), None)

    def _hit(self, point: QPoint) -> tuple[Optional[Interval], _Grab]:
        lanes = self._lane_rects()
        for interval in reversed(self._intervals):
            lane = lanes.get(interval.lane)
            if lane is None or not (lane.top() <= point.y() <= lane.bottom()):
                continue
            left = self._frame_to_x(interval.start)
            right = self._frame_to_x(interval.end + 1)
            if not (left - 5 <= point.x() <= right + 5):
                continue
            if abs(point.x() - left) <= 5:
                return interval, _Grab.TRIM_START
            if abs(point.x() - right) <= 5:
                return interval, _Grab.TRIM_END
            return interval, _Grab.MOVE
        return None, _Grab.NONE

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        point = event.position().toPoint()
        if point.x() < GUTTER:
            return
        frame = self._frame_at(point.x())

        if event.button() is Qt.MouseButton.MiddleButton:
            self._drag = _Drag(
                grab=_Grab.PAN,
                origin_x=point.x(),
                origin_view=self._view_start,
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if event.button() is not Qt.MouseButton.LeftButton:
            return

        interval, grab = self._hit(point)
        if interval is not None and grab in (_Grab.TRIM_START, _Grab.TRIM_END, _Grab.MOVE):
            self.set_selected(interval.key)
            self.selection_changed.emit(interval.key)
            if grab is _Grab.MOVE and self._tool is Tool.SCRUB:
                # Clicking the body of an interval selects and scrubs; only the
                # edges trim. Moving a whole interval by accident would be easy
                # and expensive to notice.
                self._drag = None
                self._scrub_to(frame)
                return
            self._drag = _Drag(
                grab=grab,
                key=interval.key,
                origin_x=point.x(),
                origin_frame=frame,
                start=interval.start,
                end=interval.end,
                anchor=interval.end if grab is _Grab.TRIM_START else interval.start,
            )
            self.edit_started.emit()
            return

        if self._tool in (Tool.DRAW_MOVEMENT, Tool.DRAW_ERROR):
            self._drag = _Drag(
                grab=_Grab.DRAW, origin_x=point.x(), origin_frame=frame,
                start=frame, end=frame, anchor=frame,
            )
            self.edit_started.emit()
            return

        self.set_selected("")
        self.selection_changed.emit("")
        self._drag = _Drag(grab=_Grab.SCRUB, origin_x=point.x(), origin_frame=frame)
        self._scrub_to(frame)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        point = event.position().toPoint()
        drag = self._drag
        if drag is None:
            self._update_cursor(point)
            return
        if abs(point.x() - drag.origin_x) > _DRAG_THRESHOLD_PX:
            drag.moved = True

        if drag.grab is _Grab.PAN:
            delta = (point.x() - drag.origin_x) / self._plot_width() * self._view_span
            self._set_view(drag.origin_view - delta, self._view_span)
            return

        frame = self._snapped(self._frame_at(point.x()))
        if drag.grab is _Grab.SCRUB:
            self._scrub_to(frame)
            return
        if drag.grab is _Grab.DRAW:
            drag.start, drag.end = min(drag.anchor, frame), max(drag.anchor, frame)
            # The frame under the moving edge, so the annotator can see what
            # they are about to capture instead of guessing from a rectangle.
            self.preview_position.emit(frame)
            self.update()
            return
        if drag.grab is _Grab.TRIM_START:
            drag.start = min(frame, drag.anchor)
            drag.end = drag.anchor
            self.preview_position.emit(drag.start)
            self.update()
            return
        if drag.grab is _Grab.TRIM_END:
            drag.start = drag.anchor
            drag.end = max(frame, drag.anchor)
            self.preview_position.emit(drag.end)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        drag, self._drag = self._drag, None
        self.setCursor(
            Qt.CursorShape.CrossCursor
            if self._tool is not Tool.SCRUB
            else Qt.CursorShape.ArrowCursor
        )
        if drag is None:
            return
        if drag.grab in (_Grab.PAN, _Grab.SCRUB):
            self.update()
            return
        if not drag.moved:
            # Too short to be a drag. Nothing is written, and the edit that was
            # announced is taken back so the playhead returns where it was.
            self.edit_cancelled.emit()
            self.update()
            return
        if drag.grab is _Grab.DRAW:
            lane = "movements" if self._tool is Tool.DRAW_MOVEMENT else "errors"
            self.interval_drawn.emit(lane, drag.start, drag.end)
        else:
            self.interval_changed.emit(drag.key, drag.start, drag.end)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt naming
        interval, _grab = self._hit(event.position().toPoint())
        if interval is not None:
            self.set_selected(interval.key)
            self.interval_activated.emit(interval.key)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt naming
        delta = event.angleDelta().y()
        if not delta:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            at = self._x_to_frame(event.position().x())
            self.zoom(0.8 if delta > 0 else 1.25, at_frame=at)
            event.accept()
            return
        step = self._view_span * 0.15 * (-1 if delta > 0 else 1)
        self._set_view(self._view_start + step, self._view_span)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt naming
        key = event.key()
        if key == Qt.Key.Key_Comma:
            self._scrub_to(self._position - 1)
        elif key == Qt.Key.Key_Period:
            self._scrub_to(self._position + 1)
        elif key == Qt.Key.Key_Home:
            self._scrub_to(0)
        elif key == Qt.Key.Key_End:
            self._scrub_to(self._frames - 1)
        elif key == Qt.Key.Key_Escape and self._drag is not None:
            self._drag = None
            self.edit_cancelled.emit()
            self.update()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def focusOutEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        if self._drag is not None and self._drag.grab not in (_Grab.SCRUB, _Grab.PAN):
            # A drag that loses focus is abandoned, not committed: the mouse is
            # somewhere else and the annotator did not finish the gesture.
            self._drag = None
            self.edit_cancelled.emit()
            self.update()
        super().focusOutEvent(event)

    # ------------------------------------------------------------- internals
    def _update_cursor(self, point: QPoint) -> None:
        if point.x() < GUTTER:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        _interval, grab = self._hit(point)
        if grab in (_Grab.TRIM_START, _Grab.TRIM_END):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif self._tool is not Tool.SCRUB:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _scrub_to(self, frame: int) -> None:
        clamped = max(0, min(self._frames - 1, int(frame)))
        if clamped == self._position:
            return
        self._position = clamped
        self.update()
        self.position_changed.emit(clamped)

    def _snapped(self, frame: int) -> int:
        """Snap to a second boundary or an interval edge when one is close."""
        if not self._snap:
            return frame
        tolerance = max(1, int(self._view_span / self._plot_width() * 6))
        best, distance = frame, tolerance + 1
        second = int(round(frame / self._fps) * self._fps)
        if abs(second - frame) < distance:
            best, distance = second, abs(second - frame)
        for interval in self._intervals:
            for edge in (interval.start, interval.end):
                if abs(edge - frame) < distance:
                    best, distance = edge, abs(edge - frame)
        return max(0, min(self._frames - 1, best))


def _nice_step(seconds: float) -> float:
    """A round number of seconds close to ``seconds``."""
    for candidate in (
        0.04, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600
    ):
        if candidate >= seconds:
            return float(candidate)
    return 3600.0


def _timecode(frame: float, fps: float) -> str:
    total = frame / max(1.0, fps)
    minutes, seconds = divmod(total, 60)
    return f"{int(minutes):02d}:{seconds:04.1f}"


__all__ = ["GUTTER", "Interval", "TimelineView", "Tool"]
