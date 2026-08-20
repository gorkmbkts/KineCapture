"""Layered timeline for review, segmentation and labelling.

Layers, top to bottom:

```text
  ruler            frame numbers and seconds
  availability     where pose data actually exists (gaps stay visible)
  confidence       per-frame tracking coverage
  markers          operator markers dropped during capture
  repetitions      draggable repetition intervals
```

Interaction:

* click or drag the playhead to scrub;
* drag a repetition body to move it, drag an edge handle to resize;
* drag on empty space in the repetition lane to create a new interval;
* wheel to zoom around the cursor, shift+wheel or middle-drag to pan.

The widget owns no data. It renders what it is given and emits intent signals;
the page decides what those mean, so undo/redo and autosave stay in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from kinecapture.domain.enums import Correctness, SegmentSource
from kinecapture.domain.project import RepetitionSegment
from kinecapture.gui.theme import Theme

#: Lane heights in logical pixels.
_RULER_H = 20
_AVAILABILITY_H = 10
_CONFIDENCE_H = 26
_MARKER_H = 12
_REPETITION_H = 42
_GAP = 4

#: How close to an edge counts as grabbing the handle rather than the body.
_HANDLE_PX = 6

#: Below this many frames a drag is treated as a click, not an interval draw.
_MIN_DRAG_FRAMES = 2


@dataclass
class _Drag:
    """State of an in-progress mouse interaction."""

    kind: str  # "playhead" | "move" | "resize-start" | "resize-end" | "create" | "pan"
    segment_id: str = ""
    anchor_frame: int = 0
    grab_offset: int = 0
    original_start: int = 0
    original_end: int = 0
    pan_origin: float = 0.0
    view_origin: float = 0.0


class TimelineWidget(QWidget):
    """Interactive multi-layer timeline."""

    position_changed = Signal(int)
    segment_selected = Signal(str)
    segment_bounds_changed = Signal(str, int, int)
    segment_create_requested = Signal(int, int)
    segment_double_clicked = Signal(str)
    loop_range_changed = Signal(object)

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._frame_count = 0
        self._fps = 30.0
        self._position = 0
        self._segments: list[RepetitionSegment] = []
        self._selected_id: Optional[str] = None
        self._markers: list[int] = []
        self._coverage: Optional[np.ndarray] = None
        self._availability: Optional[np.ndarray] = None
        self._gap_positions: tuple[int, ...] = ()
        self._loop_range: Optional[tuple[int, int]] = None
        self._editable = True

        self._view_start = 0.0
        self._view_span = 1.0
        self._drag: Optional[_Drag] = None
        self._hover_segment: Optional[str] = None

        self.setMinimumHeight(
            _RULER_H + _AVAILABILITY_H + _CONFIDENCE_H + _MARKER_H + _REPETITION_H + 5 * _GAP
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ----------------------------------------------------------------- data
    def set_take(
        self,
        frame_count: int,
        *,
        fps: float = 30.0,
        markers: Sequence[int] = (),
        coverage: Optional[np.ndarray] = None,
        gaps: Sequence[int] = (),
    ) -> None:
        self._frame_count = max(0, int(frame_count))
        self._fps = fps if fps > 0 else 30.0
        self._markers = sorted(int(m) for m in markers)
        self._coverage = None if coverage is None else np.asarray(coverage, dtype=np.float32)
        self._availability = (
            None if self._coverage is None else (self._coverage > 0.0)
        )
        self._gap_positions = tuple(int(g) for g in gaps)
        self._view_start = 0.0
        self._view_span = float(max(1, self._frame_count))
        self._position = 0
        self.update()

    def set_segments(self, segments: Sequence[RepetitionSegment]) -> None:
        self._segments = list(segments)
        if self._selected_id and not any(
            s.segment_id == self._selected_id for s in self._segments
        ):
            self._selected_id = None
        self.update()

    def set_position(self, position: int) -> None:
        clamped = int(np.clip(position, 0, max(0, self._frame_count - 1)))
        if clamped == self._position:
            return
        self._position = clamped
        self._ensure_visible(clamped)
        self.update()

    @property
    def position(self) -> int:
        return self._position

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def set_selected(self, segment_id: Optional[str]) -> None:
        self._selected_id = segment_id
        self.update()

    @property
    def selected_id(self) -> Optional[str]:
        return self._selected_id

    def set_loop_range(self, loop: Optional[tuple[int, int]]) -> None:
        self._loop_range = loop
        self.update()

    @property
    def loop_range(self) -> Optional[tuple[int, int]]:
        return self._loop_range

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.update()

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    # ----------------------------------------------------------------- zoom
    def zoom_to_fit(self) -> None:
        self._view_start = 0.0
        self._view_span = float(max(1, self._frame_count))
        self.update()

    def zoom_to_range(self, start: int, end: int, *, padding: float = 0.15) -> None:
        span = max(_MIN_DRAG_FRAMES, end - start + 1)
        pad = span * padding
        self._view_span = float(np.clip(span + 2 * pad, 4.0, max(4, self._frame_count)))
        self._view_start = float(
            np.clip(start - pad, 0.0, max(0.0, self._frame_count - self._view_span))
        )
        self.update()

    def _ensure_visible(self, frame: int) -> None:
        if frame < self._view_start:
            self._view_start = float(max(0, frame - self._view_span * 0.1))
        elif frame > self._view_start + self._view_span:
            self._view_start = float(
                min(
                    max(0.0, self._frame_count - self._view_span),
                    frame - self._view_span * 0.9,
                )
            )

    # ------------------------------------------------------------ geometry
    def _lane_rects(self) -> dict[str, QRectF]:
        width = float(self.width())
        y = 0.0
        rects: dict[str, QRectF] = {}
        rects["ruler"] = QRectF(0, y, width, _RULER_H)
        y += _RULER_H + _GAP
        rects["availability"] = QRectF(0, y, width, _AVAILABILITY_H)
        y += _AVAILABILITY_H + _GAP
        rects["confidence"] = QRectF(0, y, width, _CONFIDENCE_H)
        y += _CONFIDENCE_H + _GAP
        rects["markers"] = QRectF(0, y, width, _MARKER_H)
        y += _MARKER_H + _GAP
        rects["repetitions"] = QRectF(0, y, width, _REPETITION_H)
        return rects

    def _frame_to_x(self, frame: float) -> float:
        if self._view_span <= 0:
            return 0.0
        return (frame - self._view_start) / self._view_span * self.width()

    def _x_to_frame(self, x: float) -> int:
        if self.width() <= 0:
            return 0
        frame = self._view_start + (x / self.width()) * self._view_span
        return int(np.clip(round(frame), 0, max(0, self._frame_count - 1)))

    def _segment_rect(self, segment: RepetitionSegment, lane: QRectF) -> QRectF:
        left = self._frame_to_x(segment.start_frame)
        right = self._frame_to_x(segment.end_frame + 1)
        return QRectF(left, lane.top() + 2, max(2.0, right - left), lane.height() - 4)

    def _segment_at(self, point: QPointF) -> Optional[tuple[RepetitionSegment, str]]:
        """The segment under ``point`` and which part of it: body or a handle."""
        lane = self._lane_rects()["repetitions"]
        if not lane.contains(QPointF(lane.center().x(), point.y())):
            return None
        # Selected first so an overlapping pair stays grabbable.
        ordered = sorted(
            self._segments, key=lambda s: s.segment_id != (self._selected_id or "")
        )
        for segment in ordered:
            rect = self._segment_rect(segment, lane)
            if not rect.adjusted(-_HANDLE_PX, 0, _HANDLE_PX, 0).contains(point):
                continue
            if abs(point.x() - rect.left()) <= _HANDLE_PX:
                return segment, "resize-start"
            if abs(point.x() - rect.right()) <= _HANDLE_PX:
                return segment, "resize-end"
            return segment, "move"
        return None

    # -------------------------------------------------------------- events
    def mousePressEvent(self, event: QMouseEvent) -> None:
        point = QPointF(event.position())
        lanes = self._lane_rects()
        frame = self._x_to_frame(point.x())

        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag = _Drag(
                kind="pan", pan_origin=point.x(), view_origin=self._view_start
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        hit = self._segment_at(point) if self._editable else None
        if hit is not None:
            segment, kind = hit
            self._selected_id = segment.segment_id
            self.segment_selected.emit(segment.segment_id)
            self._drag = _Drag(
                kind=kind,
                segment_id=segment.segment_id,
                grab_offset=frame - segment.start_frame,
                original_start=segment.start_frame,
                original_end=segment.end_frame,
            )
            self.update()
            return

        if self._editable and lanes["repetitions"].contains(point):
            self._drag = _Drag(kind="create", anchor_frame=frame)
            self.update()
            return

        self._drag = _Drag(kind="playhead")
        self.set_position(frame)
        self.position_changed.emit(self._position)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = QPointF(event.position())
        frame = self._x_to_frame(point.x())

        if self._drag is None:
            hit = self._segment_at(point)
            self._hover_segment = hit[0].segment_id if hit else None
            if hit:
                _, kind = hit
                self.setCursor(
                    Qt.CursorShape.SizeHorCursor
                    if kind.startswith("resize")
                    else Qt.CursorShape.SizeAllCursor
                )
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            if self._frame_count:
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"Kare {frame}  ·  {frame / self._fps:.2f} s",
                    self,
                )
            self.update()
            return

        drag = self._drag
        if drag.kind == "pan":
            delta_frames = (
                (drag.pan_origin - point.x()) / max(1, self.width()) * self._view_span
            )
            self._view_start = float(
                np.clip(
                    drag.view_origin + delta_frames,
                    0.0,
                    max(0.0, self._frame_count - self._view_span),
                )
            )
        elif drag.kind == "playhead":
            self.set_position(frame)
            self.position_changed.emit(self._position)
        elif drag.kind == "create":
            self.update()
        elif drag.kind == "move":
            span = drag.original_end - drag.original_start
            start = int(
                np.clip(frame - drag.grab_offset, 0, max(0, self._frame_count - 1 - span))
            )
            self.segment_bounds_changed.emit(drag.segment_id, start, start + span)
        elif drag.kind == "resize-start":
            start = min(frame, drag.original_end - 1)
            self.segment_bounds_changed.emit(
                drag.segment_id, max(0, start), drag.original_end
            )
        elif drag.kind == "resize-end":
            end = max(frame, drag.original_start + 1)
            self.segment_bounds_changed.emit(
                drag.segment_id,
                drag.original_start,
                min(end, max(0, self._frame_count - 1)),
            )
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        drag, self._drag = self._drag, None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if drag is None:
            return
        if drag.kind == "create":
            frame = self._x_to_frame(QPointF(event.position()).x())
            start, end = sorted((drag.anchor_frame, frame))
            if end - start >= _MIN_DRAG_FRAMES:
                self.segment_create_requested.emit(start, end)
            else:
                # Too short to be an interval: treat it as a scrub instead.
                self.set_position(frame)
                self.position_changed.emit(self._position)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        hit = self._segment_at(QPointF(event.position()))
        if hit is not None:
            self.segment_double_clicked.emit(hit[0].segment_id)

    def wheelEvent(self, event: QWheelEvent) -> None:
        steps = event.angleDelta().y() / 120.0
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._view_start = float(
                np.clip(
                    self._view_start - steps * self._view_span * 0.15,
                    0.0,
                    max(0.0, self._frame_count - self._view_span),
                )
            )
        else:
            # Zoom about the cursor so the frame under it stays put.
            anchor = self._x_to_frame(event.position().x())
            factor = 0.85**steps
            new_span = float(
                np.clip(self._view_span * factor, 4.0, max(4, self._frame_count))
            )
            ratio = (anchor - self._view_start) / max(1e-6, self._view_span)
            self._view_start = float(
                np.clip(
                    anchor - ratio * new_span,
                    0.0,
                    max(0.0, self._frame_count - new_span),
                )
            )
            self._view_span = new_span
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover_segment = None
        self.update()

    # --------------------------------------------------------------- paint
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = self._theme
        painter.fillRect(self.rect(), QColor(theme.bg_sunken))

        if self._frame_count <= 0:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Zaman çizelgesi boş"
            )
            painter.end()
            return

        lanes = self._lane_rects()
        self._paint_loop(painter, lanes)
        self._paint_ruler(painter, lanes["ruler"])
        self._paint_availability(painter, lanes["availability"])
        self._paint_confidence(painter, lanes["confidence"])
        self._paint_markers(painter, lanes["markers"])
        self._paint_segments(painter, lanes["repetitions"])
        self._paint_pending_create(painter, lanes["repetitions"])
        self._paint_playhead(painter)
        painter.end()

    def _paint_loop(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        if self._loop_range is None:
            return
        start, end = self._loop_range
        left = self._frame_to_x(start)
        right = self._frame_to_x(end + 1)
        colour = QColor(self._theme.accent)
        colour.setAlpha(28)
        painter.fillRect(
            QRectF(left, 0, max(1.0, right - left), self.height()), colour
        )

    def _paint_ruler(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.setPen(QColor(theme.text_muted))
        font = painter.font()
        font.setPointSize(max(7, theme.font_size_sm - 2))
        painter.setFont(font)

        # Tick spacing chosen so labels never collide at any zoom level.
        target_px = 90.0
        frames_per_tick = max(1.0, self._view_span * target_px / max(1, self.width()))
        step_seconds = _nice_step(frames_per_tick / self._fps)
        step_frames = max(1.0, step_seconds * self._fps)

        first = int(self._view_start // step_frames) * step_frames
        tick = first
        while tick <= self._view_start + self._view_span:
            x = self._frame_to_x(tick)
            if 0 <= x <= self.width():
                pen = QPen(QColor(theme.border_strong))
                painter.setPen(pen)
                painter.drawLine(QPointF(x, lane.bottom() - 5), QPointF(x, lane.bottom()))
                painter.setPen(QColor(theme.text_muted))
                seconds = tick / self._fps
                painter.drawText(
                    QPointF(x + 3, lane.top() + 11), f"{seconds:.1f}s · {int(tick)}"
                )
            tick += step_frames

    def _paint_availability(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(lane, QColor(theme.bg_base))
        if self._availability is None:
            painter.fillRect(lane, QColor(theme.skeleton_dim))
            return
        # Per-pixel column reduction: any missing frame in the column shows.
        width = max(1, int(self.width()))
        for x in range(width):
            f0 = self._x_to_frame(x)
            f1 = self._x_to_frame(x + 1)
            hi = min(len(self._availability), max(f0 + 1, f1))
            if f0 >= len(self._availability):
                break
            window = self._availability[f0:hi]
            if window.size == 0:
                continue
            ratio = float(window.mean())
            colour = QColor(theme.success if ratio >= 0.999 else theme.warning)
            if ratio <= 0.001:
                colour = QColor(theme.danger)
            painter.fillRect(QRectF(x, lane.top(), 1, lane.height()), colour)

        for gap in self._gap_positions:
            x = self._frame_to_x(gap)
            if 0 <= x <= self.width():
                pen = QPen(QColor(theme.danger))
                pen.setWidthF(1.5)
                painter.setPen(pen)
                painter.drawLine(
                    QPointF(x, lane.top() - 2), QPointF(x, lane.bottom() + 2)
                )

    def _paint_confidence(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(lane, QColor(theme.bg_base))
        if self._coverage is None or self._coverage.size == 0:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                lane.adjusted(6, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter,
                "Takip kapsamı verisi yok",
            )
            return
        width = max(1, int(self.width()))
        pen = QPen(QColor(theme.accent))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        previous: Optional[QPointF] = None
        for x in range(0, width, 2):
            frame = self._x_to_frame(x)
            if frame >= len(self._coverage):
                break
            value = float(self._coverage[frame])
            point = QPointF(x, lane.bottom() - value * (lane.height() - 3))
            if previous is not None:
                painter.drawLine(previous, point)
            previous = point

    def _paint_markers(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        for marker in self._markers:
            x = self._frame_to_x(marker)
            if not (0 <= x <= self.width()):
                continue
            painter.setBrush(QColor(theme.warning))
            painter.setPen(Qt.PenStyle.NoPen)
            top = lane.top() + 1
            painter.drawPolygon(
                QPointF(x, lane.bottom() - 1),
                QPointF(x - 4, top),
                QPointF(x + 4, top),
            )

    def _paint_segments(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(lane, QColor(theme.bg_base))
        for segment in self._segments:
            rect = self._segment_rect(segment, lane)
            if rect.right() < 0 or rect.left() > self.width():
                continue
            selected = segment.segment_id == self._selected_id
            hovered = segment.segment_id == self._hover_segment

            fill = QColor(self._segment_colour(segment))
            fill.setAlpha(70 if not selected else 130)
            if not segment.is_active:
                fill.setAlpha(35)
            painter.setBrush(fill)

            pen = QPen(QColor(self._segment_colour(segment)))
            pen.setWidthF(2.0 if selected else 1.0)
            if not segment.is_active:
                pen.setStyle(Qt.PenStyle.DashLine)
            elif segment.source is SegmentSource.MODEL_SUGGESTION:
                # A model suggestion is drawn dashed until a human touches it.
                pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, theme.radius_sm, theme.radius_sm)

            if selected or hovered:
                handle = QColor(theme.text_primary)
                painter.setBrush(handle)
                painter.setPen(Qt.PenStyle.NoPen)
                for x in (rect.left(), rect.right()):
                    painter.drawRoundedRect(
                        QRectF(x - 2, rect.top() + 3, 4, rect.height() - 6), 2, 2
                    )

            if rect.width() > 34:
                painter.setPen(QColor(theme.text_primary))
                label = str(segment.index)
                if segment.annotation.exercise and rect.width() > 110:
                    label = f"{segment.index} · {segment.annotation.exercise}"
                if not segment.is_active:
                    label += " (dışlandı)"
                painter.drawText(
                    rect.adjusted(6, 0, -6, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )

    def _paint_pending_create(self, painter: QPainter, lane: QRectF) -> None:
        if self._drag is None or self._drag.kind != "create":
            return
        current = self._x_to_frame(self.mapFromGlobal(self.cursor().pos()).x())
        start, end = sorted((self._drag.anchor_frame, current))
        left, right = self._frame_to_x(start), self._frame_to_x(end + 1)
        colour = QColor(self._theme.accent)
        colour.setAlpha(60)
        painter.setBrush(colour)
        pen = QPen(QColor(self._theme.accent))
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(
            QRectF(left, lane.top() + 2, max(2.0, right - left), lane.height() - 4),
            self._theme.radius_sm,
            self._theme.radius_sm,
        )

    def _paint_playhead(self, painter: QPainter) -> None:
        x = self._frame_to_x(self._position)
        if not (-2 <= x <= self.width() + 2):
            return
        theme = self._theme
        pen = QPen(QColor(theme.text_primary))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.setBrush(QColor(theme.text_primary))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPointF(x, 9), QPointF(x - 5, 0), QPointF(x + 5, 0)
        )

    def _segment_colour(self, segment: RepetitionSegment) -> str:
        theme = self._theme
        if not segment.is_active:
            return theme.text_muted
        return {
            Correctness.CORRECT: theme.success,
            Correctness.INCORRECT: theme.warning,
            Correctness.UNCERTAIN: theme.info,
            Correctness.UNKNOWN: theme.accent,
        }[segment.annotation.correctness]


def _nice_step(raw_seconds: float) -> float:
    """Round a tick interval up to a human-friendly value."""
    for candidate in (
        0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0
    ):
        if raw_seconds <= candidate:
            return candidate
    return 600.0


__all__ = ["TimelineWidget"]
