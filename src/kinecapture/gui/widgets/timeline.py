"""Layered timeline for review, movement segmentation and error localisation.

Two editing modes, one widget
-----------------------------
The same timeline does two different jobs, and confusing them would corrupt
labels, so the mode is explicit and always visible:

``MOVEMENT``
    Draw and adjust movement samples across the whole take. The error lane is
    drawn but dimmed and inert.

``ERROR``
    Draw and adjust error intervals *inside the selected movement*. Everything
    outside that movement is masked, the movement lane is inert, and the drawn
    range is clamped to the parent - an error interval can never be created
    outside the movement it belongs to.

Lanes, top to bottom:

```text
  ruler          frame numbers and seconds
  availability   where pose data actually exists (gaps stay visible)
  confidence     per-frame tracking coverage
  markers        operator markers dropped during capture
  movements      movement samples (level 1)
  errors         error intervals of the selected movement (level 2)
```

Boundary convention: positions are 0-based stream indices, inclusive at both
ends. A range covering frames 10..19 is drawn from the left edge of frame 10 to
the right edge of frame 19, so a one-frame range is visibly one frame wide.

The widget owns no data. It renders what it is given and emits intent signals;
the page decides what those mean, so undo/redo and autosave stay in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from kinecapture.domain.enums import Correctness, SegmentSource
from kinecapture.domain.project import ErrorInterval, MovementSample
from kinecapture.gui.theme import Theme

#: Lane heights in logical pixels.
_RULER_H = 18
_AVAILABILITY_H = 8
_CONFIDENCE_H = 18
_MARKER_H = 10
_MOVEMENT_H = 34
_ERROR_H = 32
_ACTIVITY_H = 26
_GAP = 3

#: How close to an edge counts as grabbing the handle rather than the body.
_HANDLE_PX = 6

#: Below this many frames a drag is treated as a click, not an interval draw.
_MIN_DRAG_FRAMES = 2

#: Width of the left gutter holding the lane captions. The plot starts after
#: it, so a range beginning at frame 0 can never sit under its own lane label.
_GUTTER = 58

#: Distinct hues for error classes. Chosen to stay apart in both themes; the
#: class name is always drawn too, so colour is never the only signal.
_ERROR_PALETTE = (
    "#e0567a", "#f0913c", "#c678dd", "#3fb6c9",
    "#d4a72c", "#7f9cf5", "#e06c75", "#56b6a2",
)


class TimelineMode(str, Enum):
    """Which layer of labels the timeline is editing.

    The first two are the two levels of the repetition model. The third is the
    activity strip, which describes the whole take rather than a repetition
    inside it - a different question, so a different mode rather than a
    different colour in the same lane.
    """

    MOVEMENT = "movement"
    ERROR = "error"
    ACTIVITY = "activity"

    @property
    def label(self) -> str:
        return {
            TimelineMode.MOVEMENT: "Hareket aralıkları",
            TimelineMode.ERROR: "Hata aralıkları",
            TimelineMode.ACTIVITY: "Aktivite durumları",
        }[self]


@dataclass
class _Drag:
    """State of an in-progress mouse interaction."""

    kind: str  # playhead | move | resize-start | resize-end | create | pan
    lane: str = "movement"  # movement | error
    target_id: str = ""
    anchor_frame: int = 0
    grab_offset: int = 0
    original_start: int = 0
    original_end: int = 0
    pan_origin: float = 0.0
    view_origin: float = 0.0


def error_class_colour(code: str) -> str:
    """A stable colour for an error class, derived from its code.

    Deterministic so the same class keeps the same colour across takes and
    sessions without storing a palette anywhere.
    """
    if not code:
        return "#8b93a1"
    digest = sum((index + 1) * ord(char) for index, char in enumerate(code))
    return _ERROR_PALETTE[digest % len(_ERROR_PALETTE)]


class TimelineWidget(QWidget):
    """Interactive multi-layer timeline with movement and error edit modes."""

    position_changed = Signal(int)
    mode_changed = Signal(str)

    sample_selected = Signal(str)
    sample_bounds_changed = Signal(str, int, int)
    sample_create_requested = Signal(int, int)
    sample_double_clicked = Signal(str)

    activity_selected = Signal(str)
    activity_bounds_changed = Signal(str, int, int)
    activity_create_requested = Signal(int, int)
    activity_double_clicked = Signal(str)

    interval_selected = Signal(str)
    interval_bounds_changed = Signal(str, int, int)
    interval_create_requested = Signal(int, int)
    interval_double_clicked = Signal(str)

    loop_range_changed = Signal(object)

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._frame_count = 0
        self._fps = 30.0
        self._position = 0
        self._mode = TimelineMode.MOVEMENT

        self._samples: list[MovementSample] = []
        self._selected_sample_id: Optional[str] = None
        self._activity: list[Any] = []
        self._selected_activity_id = ""
        self._selected_interval_id: Optional[str] = None
        self._error_labels: dict[str, str] = {}

        self._markers: list[int] = []
        self._coverage: Optional[np.ndarray] = None
        self._availability: Optional[np.ndarray] = None
        self._gap_positions: tuple[int, ...] = ()
        self._loop_range: Optional[tuple[int, int]] = None
        self._editable = True

        self._view_start = 0.0
        self._view_span = 1.0
        self._drag: Optional[_Drag] = None
        self._hover_id: Optional[str] = None

        self.setMinimumHeight(
            _RULER_H
            + _AVAILABILITY_H
            + _CONFIDENCE_H
            + _MARKER_H
            + _MOVEMENT_H
            + _ERROR_H
            + _ACTIVITY_H
            + 7 * _GAP
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ----------------------------------------------------------------- mode
    @property
    def mode(self) -> TimelineMode:
        return self._mode

    def set_mode(self, mode: TimelineMode | str) -> None:
        resolved = TimelineMode(mode)
        if resolved is self._mode:
            return
        self._mode = resolved
        self._drag = None
        self.update()
        self.mode_changed.emit(resolved.value)

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
        self._coverage = (
            None if coverage is None else np.asarray(coverage, dtype=np.float32)
        )
        self._availability = None if self._coverage is None else (self._coverage > 0.0)
        self._gap_positions = tuple(int(g) for g in gaps)
        self._view_start = 0.0
        self._view_span = float(max(1, self._frame_count))
        self._position = 0
        self.update()

    def set_samples(self, samples: Sequence[MovementSample]) -> None:
        self._samples = list(samples)
        ids = {s.sample_id for s in self._samples}
        if self._selected_sample_id and self._selected_sample_id not in ids:
            self._selected_sample_id = None
            self._selected_interval_id = None
        self.update()

    def set_error_labels(self, labels: dict[str, str]) -> None:
        """Display names for error classes, used for the in-bar captions."""
        self._error_labels = dict(labels)
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

    # ------------------------------------------------------------ selection
    def set_selected_sample(self, sample_id: Optional[str]) -> None:
        if sample_id == self._selected_sample_id:
            return
        self._selected_sample_id = sample_id
        self._selected_interval_id = None
        self.update()

    @property
    def selected_sample_id(self) -> Optional[str]:
        return self._selected_sample_id

    def set_selected_interval(self, interval_id: Optional[str]) -> None:
        self._selected_interval_id = interval_id
        self.update()

    @property
    def selected_interval_id(self) -> Optional[str]:
        return self._selected_interval_id

    def selected_sample(self) -> Optional[MovementSample]:
        return next(
            (s for s in self._samples if s.sample_id == self._selected_sample_id), None
        )

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
        rects["movements"] = QRectF(0, y, width, _MOVEMENT_H)
        y += _MOVEMENT_H + _GAP
        rects["errors"] = QRectF(0, y, width, _ERROR_H)
        y += _ERROR_H + _GAP
        rects["activity"] = QRectF(0, y, width, _ACTIVITY_H)
        return rects

    @property
    def _plot_width(self) -> float:
        return max(1.0, float(self.width() - _GUTTER))

    def _frame_to_x(self, frame: float) -> float:
        """Left edge of ``frame``. Frame N spans ``[x(N), x(N+1))``."""
        if self._view_span <= 0:
            return float(_GUTTER)
        return _GUTTER + (frame - self._view_start) / self._view_span * self._plot_width

    def _x_to_frame(self, x: float) -> int:
        if self.width() <= _GUTTER:
            return 0
        frame = self._view_start + ((x - _GUTTER) / self._plot_width) * self._view_span
        return int(np.clip(int(np.floor(frame)), 0, max(0, self._frame_count - 1)))

    def _caption_rect(self, lane: QRectF) -> QRectF:
        return QRectF(4, lane.top(), _GUTTER - 8, lane.height())

    def _plot_rect(self, lane: QRectF) -> QRectF:
        return QRectF(_GUTTER, lane.top(), self._plot_width, lane.height())

    def _range_rect(self, start: int, end: int, lane: QRectF, inset: float = 2.0) -> QRectF:
        """Rect covering an inclusive ``[start, end]`` range."""
        left = self._frame_to_x(start)
        right = self._frame_to_x(end + 1)
        return QRectF(
            left, lane.top() + inset, max(2.0, right - left), lane.height() - 2 * inset
        )

    def _sample_at(self, point: QPointF) -> Optional[tuple[MovementSample, str]]:
        lane = self._lane_rects()["movements"]
        if not (lane.top() <= point.y() <= lane.bottom()):
            return None
        ordered = sorted(
            self._samples, key=lambda s: s.sample_id != (self._selected_sample_id or "")
        )
        for sample in ordered:
            rect = self._range_rect(sample.start_frame, sample.end_frame, lane)
            if not rect.adjusted(-_HANDLE_PX, 0, _HANDLE_PX, 0).contains(point):
                continue
            if abs(point.x() - rect.left()) <= _HANDLE_PX:
                return sample, "resize-start"
            if abs(point.x() - rect.right()) <= _HANDLE_PX:
                return sample, "resize-end"
            return sample, "move"
        return None

    def _interval_rows(self) -> list[list[ErrorInterval]]:
        """Pack the selected sample's intervals into non-overlapping rows.

        Overlapping intervals get their own row so both stay readable, which is
        the whole point of allowing two error classes at the same moment.
        """
        sample = self.selected_sample()
        if sample is None:
            return []
        rows: list[list[ErrorInterval]] = []
        for interval in sample.sorted_intervals():
            for row in rows:
                if all(not interval.overlaps(other) for other in row):
                    row.append(interval)
                    break
            else:
                rows.append([interval])
        return rows

    def _interval_lane_rect(self, row: int, rows: int, lane: QRectF) -> QRectF:
        rows = max(1, rows)
        height = lane.height() / rows
        return QRectF(lane.left(), lane.top() + row * height, lane.width(), height)

    def _interval_at(self, point: QPointF) -> Optional[tuple[ErrorInterval, str]]:
        lane = self._lane_rects()["errors"]
        if not (lane.top() <= point.y() <= lane.bottom()):
            return None
        rows = self._interval_rows()
        for row_index, row in enumerate(rows):
            row_rect = self._interval_lane_rect(row_index, len(rows), lane)
            if not (row_rect.top() <= point.y() <= row_rect.bottom()):
                continue
            for interval in row:
                rect = self._range_rect(
                    interval.start_frame, interval.end_frame, row_rect, inset=1.5
                )
                if not rect.adjusted(-_HANDLE_PX, 0, _HANDLE_PX, 0).contains(point):
                    continue
                if abs(point.x() - rect.left()) <= _HANDLE_PX:
                    return interval, "resize-start"
                if abs(point.x() - rect.right()) <= _HANDLE_PX:
                    return interval, "resize-end"
                return interval, "move"
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

        if self._editable and self._mode is TimelineMode.ERROR:
            handled = self._press_error_mode(point, lanes, frame)
            if handled:
                return
        elif self._editable and self._mode is TimelineMode.MOVEMENT:
            handled = self._press_movement_mode(point, lanes, frame)
            if handled:
                return
        elif self._editable and self._mode is TimelineMode.ACTIVITY:
            handled = self._press_activity_mode(point, lanes, frame)
            if handled:
                return

        self._drag = _Drag(kind="playhead")
        self.set_position(frame)
        self.position_changed.emit(self._position)

    def _press_movement_mode(self, point: QPointF, lanes, frame: int) -> bool:
        hit = self._sample_at(point)
        if hit is not None:
            sample, kind = hit
            self._selected_sample_id = sample.sample_id
            self.sample_selected.emit(sample.sample_id)
            self._drag = _Drag(
                kind=kind,
                lane="movement",
                target_id=sample.sample_id,
                grab_offset=frame - sample.start_frame,
                original_start=sample.start_frame,
                original_end=sample.end_frame,
            )
            self.update()
            return True
        if lanes["movements"].contains(point):
            self._drag = _Drag(kind="create", lane="movement", anchor_frame=frame)
            self.update()
            return True
        return False

    def _press_error_mode(self, point: QPointF, lanes, frame: int) -> bool:
        sample = self.selected_sample()
        hit = self._interval_at(point)
        if hit is not None:
            interval, kind = hit
            self._selected_interval_id = interval.interval_id
            self.interval_selected.emit(interval.interval_id)
            self._drag = _Drag(
                kind=kind,
                lane="error",
                target_id=interval.interval_id,
                grab_offset=frame - interval.start_frame,
                original_start=interval.start_frame,
                original_end=interval.end_frame,
            )
            self.update()
            return True
        if lanes["errors"].contains(point) and sample is not None:
            # Anchoring is clamped to the parent, so a drag that starts outside
            # the movement still produces a valid interval inside it.
            anchor = int(np.clip(frame, sample.start_frame, sample.end_frame))
            self._drag = _Drag(kind="create", lane="error", anchor_frame=anchor)
            self.update()
            return True
        # Clicking a movement while in error mode selects it, so the user can
        # switch target without leaving the mode.
        movement_hit = self._sample_at(point)
        if movement_hit is not None:
            self._selected_sample_id = movement_hit[0].sample_id
            self._selected_interval_id = None
            self.sample_selected.emit(movement_hit[0].sample_id)
            self.update()
            return True
        return False

    def _press_activity_mode(self, point: QPointF, lanes, frame: int) -> bool:
        """Select an existing activity band, or start drawing a new one."""
        if not lanes["activity"].contains(point):
            return False
        existing = self._activity_at(frame)
        if existing is not None:
            self._selected_activity_id = existing.interval_id
            self.activity_selected.emit(existing.interval_id)
            self.update()
            return True
        self._drag = _Drag(kind="create", lane="activity", anchor_frame=frame)
        self.update()
        return True

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        point = QPointF(event.position())
        frame = self._x_to_frame(point.x())

        if self._drag is None:
            self._update_hover(point, frame, event)
            return

        drag = self._drag
        if drag.kind == "pan":
            delta_frames = (
                (drag.pan_origin - point.x()) / self._plot_width * self._view_span
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
        else:
            self._drag_existing(drag, frame)
        self.update()

    def _drag_existing(self, drag: _Drag, frame: int) -> None:
        if drag.lane == "movement":
            limit_low, limit_high = 0, max(0, self._frame_count - 1)
            signal = self.sample_bounds_changed
        else:
            sample = self.selected_sample()
            if sample is None:
                return
            limit_low, limit_high = sample.start_frame, sample.end_frame
            signal = self.interval_bounds_changed

        if drag.kind == "move":
            span = drag.original_end - drag.original_start
            start = int(
                np.clip(frame - drag.grab_offset, limit_low, limit_high - span)
            )
            signal.emit(drag.target_id, start, start + span)
        elif drag.kind == "resize-start":
            start = int(np.clip(frame, limit_low, drag.original_end - 1))
            signal.emit(drag.target_id, start, drag.original_end)
        elif drag.kind == "resize-end":
            end = int(np.clip(frame, drag.original_start + 1, limit_high))
            signal.emit(drag.target_id, drag.original_start, end)

    def _update_hover(self, point: QPointF, frame: int, event: QMouseEvent) -> None:
        hit = (
            self._interval_at(point)
            if self._mode is TimelineMode.ERROR
            else self._sample_at(point)
        )
        if hit is None and self._mode is TimelineMode.ERROR:
            hit = self._sample_at(point)
        if hit is not None:
            target, kind = hit
            self._hover_id = getattr(target, "interval_id", None) or getattr(
                target, "sample_id", None
            )
            self.setCursor(
                Qt.CursorShape.SizeHorCursor
                if kind.startswith("resize")
                else Qt.CursorShape.SizeAllCursor
            )
        else:
            self._hover_id = None
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if self._frame_count:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"Kare {frame}  ·  {frame / self._fps:.2f} s",
                self,
            )
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        drag, self._drag = self._drag, None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if drag is None:
            return
        if drag.kind == "create":
            frame = self._x_to_frame(QPointF(event.position()).x())
            if drag.lane == "error":
                sample = self.selected_sample()
                if sample is not None:
                    frame = int(
                        np.clip(frame, sample.start_frame, sample.end_frame)
                    )
            start, end = sorted((drag.anchor_frame, frame))
            if end - start >= _MIN_DRAG_FRAMES:
                if drag.lane == "error":
                    self.interval_create_requested.emit(start, end)
                elif drag.lane == "activity":
                    self.activity_create_requested.emit(start, end)
                else:
                    self.sample_create_requested.emit(start, end)
            else:
                # Too short to be a range: treat it as a scrub instead.
                self.set_position(frame)
                self.position_changed.emit(self._position)
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        point = QPointF(event.position())
        if self._mode is TimelineMode.ACTIVITY:
            frame = self._x_to_frame(point.x())
            existing = self._activity_at(frame)
            if existing is not None:
                self.activity_double_clicked.emit(existing.interval_id)
                return
        if self._mode is TimelineMode.ERROR:
            hit = self._interval_at(point)
            if hit is not None:
                self.interval_double_clicked.emit(hit[0].interval_id)
                return
        hit = self._sample_at(point)
        if hit is not None:
            self.sample_double_clicked.emit(hit[0].sample_id)

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
                    anchor - ratio * new_span, 0.0, max(0.0, self._frame_count - new_span)
                )
            )
            self._view_span = new_span
        self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover_id = None
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
        self._paint_samples(painter, lanes["movements"])
        self._paint_error_lane(painter, lanes["errors"])
        self._paint_activity_lane(painter, lanes["activity"])
        self._paint_pending_create(painter, lanes)
        self._paint_playhead(painter)
        painter.end()

    def _paint_loop(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        if self._loop_range is None:
            return
        start, end = self._loop_range
        left = self._frame_to_x(start)
        right = self._frame_to_x(end + 1)
        colour = QColor(self._theme.accent)
        colour.setAlpha(26)
        painter.fillRect(QRectF(left, 0, max(1.0, right - left), self.height()), colour)

    def _paint_ruler(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        font = painter.font()
        font.setPointSize(max(7, theme.font_size_sm - 2))
        painter.setFont(font)

        target_px = 90.0
        frames_per_tick = max(1.0, self._view_span * target_px / max(1, self.width()))
        step_seconds = _nice_step(frames_per_tick / self._fps)
        step_frames = max(1.0, step_seconds * self._fps)

        tick = int(self._view_start // step_frames) * step_frames
        while tick <= self._view_start + self._view_span:
            x = self._frame_to_x(tick)
            if _GUTTER <= x <= self.width():
                painter.setPen(QPen(QColor(theme.border_strong)))
                painter.drawLine(
                    QPointF(x, lane.bottom() - 5), QPointF(x, lane.bottom())
                )
                painter.setPen(QColor(theme.text_muted))
                painter.drawText(
                    QPointF(x + 3, lane.top() + 11),
                    f"{tick / self._fps:.1f}s · {int(tick)}",
                )
            tick += step_frames

    def _paint_availability(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(self._plot_rect(lane), QColor(theme.bg_base))
        if self._availability is None:
            painter.fillRect(self._plot_rect(lane), QColor(theme.skeleton_dim))
            return
        for x in range(_GUTTER, max(_GUTTER + 1, int(self.width()))):
            f0 = self._x_to_frame(x)
            f1 = self._x_to_frame(x + 1)
            if f0 >= len(self._availability):
                break
            hi = min(len(self._availability), max(f0 + 1, f1))
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
            if _GUTTER <= x <= self.width():
                pen = QPen(QColor(theme.danger))
                pen.setWidthF(1.5)
                painter.setPen(pen)
                painter.drawLine(
                    QPointF(x, lane.top() - 2), QPointF(x, lane.bottom() + 2)
                )

    def _paint_confidence(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(self._plot_rect(lane), QColor(theme.bg_base))
        if self._coverage is None or self._coverage.size == 0:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                lane.adjusted(6, 0, 0, 0),
                Qt.AlignmentFlag.AlignVCenter,
                "Takip kapsamı verisi yok",
            )
            return
        pen = QPen(QColor(theme.accent))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        previous: Optional[QPointF] = None
        for x in range(_GUTTER, max(_GUTTER + 1, int(self.width())), 2):
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
            if not (_GUTTER <= x <= self.width()):
                continue
            painter.setBrush(QColor(theme.warning))
            painter.setPen(Qt.PenStyle.NoPen)
            top = lane.top() + 1
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, lane.bottom() - 1),
                        QPointF(x - 4, top),
                        QPointF(x + 4, top),
                    ]
                )
            )

    def _paint_samples(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(self._plot_rect(lane), QColor(theme.bg_base))
        dim = self._mode is TimelineMode.ERROR

        painter.setPen(QColor(theme.text_muted))
        painter.drawText(
            self._caption_rect(lane),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "HAREKET",
        )

        for sample in self._samples:
            rect = self._range_rect(sample.start_frame, sample.end_frame, lane)
            if rect.right() < 0 or rect.left() > self.width():
                continue
            selected = sample.sample_id == self._selected_sample_id
            hovered = sample.sample_id == self._hover_id

            base = QColor(self._sample_colour(sample))
            fill = QColor(base)
            fill.setAlpha(140 if selected else 70)
            if not sample.is_active:
                fill.setAlpha(30)
            if dim and not selected:
                fill.setAlpha(max(18, fill.alpha() // 3))
            painter.setBrush(fill)

            pen = QPen(base)
            pen.setWidthF(2.4 if selected else 1.0)
            if not sample.is_active:
                pen.setStyle(Qt.PenStyle.DashLine)
            elif sample.source is SegmentSource.MODEL_SUGGESTION:
                # A model suggestion stays dashed until a human touches it.
                pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, theme.radius_sm, theme.radius_sm)

            if (selected or hovered) and not dim:
                painter.setBrush(QColor(theme.text_primary))
                painter.setPen(Qt.PenStyle.NoPen)
                for x in (rect.left(), rect.right()):
                    painter.drawRoundedRect(
                        QRectF(x - 2, rect.top() + 3, 4, rect.height() - 6), 2, 2
                    )

            if rect.width() > 30:
                painter.setPen(
                    QColor(theme.text_primary if not dim or selected else theme.text_muted)
                )
                label = f"{sample.index}"
                if sample.exercise and rect.width() > 100:
                    label = f"{sample.index} · {sample.exercise}"
                if sample.error_intervals and rect.width() > 150:
                    label += f" · {len(sample.error_intervals)} hata"
                if not sample.is_active:
                    label += " (dışlandı)"
                painter.drawText(
                    rect.adjusted(6, 0, -6, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )


    # ------------------------------------------------------- activity lane
    #: One colour per activity state. Never the only cue: every band is also
    #: labelled, and unlabelled time is drawn as a hatched gap rather than as
    #: another colour, because it is not another class.
    _ACTIVITY_COLOURS: dict[str, str] = {
        "background": "#64748b",
        "transition": "#a78bfa",
        "target_exercise": "#22c55e",
        "other_activity": "#f59e0b",
    }

    def set_activity_intervals(
        self, intervals: Sequence[Any], selected_id: str = ""
    ) -> None:
        """Show the activity strip. Purely display; the repository owns it."""
        self._activity = list(intervals)
        self._selected_activity_id = selected_id
        self.update()

    def set_selected_activity(self, interval_id: str) -> None:
        self._selected_activity_id = interval_id
        self.update()

    def _paint_activity_lane(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.setPen(QColor(theme.text_muted))
        painter.drawText(
            self._caption_rect(lane),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "AKTİVİTE",
        )
        plot = self._plot_rect(lane)
        painter.fillRect(plot, QColor(theme.bg_base))

        if not self._activity:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                plot,
                Qt.AlignmentFlag.AlignCenter,
                "Aktivite etiketi yok"
                if self._mode is not TimelineMode.ACTIVITY
                else "Sürükleyerek aktivite aralığı çizin",
            )
            return

        # Unlabelled stretches first, so a labelled band always paints over
        # them and the eye reads the gaps as gaps.
        self._paint_unlabelled_gaps(painter, plot)

        for interval in self._activity:
            left = self._frame_to_x(interval.start_frame)
            right = self._frame_to_x(interval.end_frame + 1)
            if right < plot.left() or left > plot.right():
                continue
            box = QRectF(
                max(left, plot.left()),
                plot.top() + 2,
                max(2.0, min(right, plot.right()) - max(left, plot.left())),
                plot.height() - 4,
            )
            colour = QColor(
                self._ACTIVITY_COLOURS.get(interval.state.value, theme.text_muted)
            )
            is_selected = interval.interval_id == self._selected_activity_id
            fill = QColor(colour)
            fill.setAlpha(200 if is_selected else 130)
            painter.setBrush(fill)
            pen = QPen(colour)
            pen.setWidthF(2.0 if is_selected else 1.0)
            painter.setPen(pen)
            painter.drawRoundedRect(box, 3, 3)

            text = interval.state.label
            if interval.exercise:
                text += f" · {interval.exercise}"
            if box.width() > 46:
                painter.setPen(QColor(theme.text_primary))
                font = painter.font()
                font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
                painter.save()
                painter.setFont(font)
                painter.drawText(
                    box.adjusted(4, 0, -4, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )
                painter.restore()

    def _paint_unlabelled_gaps(self, painter: QPainter, plot: QRectF) -> None:
        """Draw what nobody has labelled, as an absence rather than a class."""
        covered = sorted(
            (i.start_frame, i.end_frame) for i in self._activity if i.end_frame >= i.start_frame
        )
        cursor = 0
        gaps: list[tuple[int, int]] = []
        for start, end in covered:
            if start > cursor:
                gaps.append((cursor, start - 1))
            cursor = max(cursor, end + 1)
        if cursor < self._frame_count:
            gaps.append((cursor, self._frame_count - 1))

        colour = QColor(self._theme.text_muted)
        colour.setAlpha(48)
        brush = QBrush(colour, Qt.BrushStyle.BDiagPattern)
        painter.setPen(Qt.PenStyle.NoPen)
        for low, high in gaps:
            left = self._frame_to_x(low)
            right = self._frame_to_x(high + 1)
            if right < plot.left() or left > plot.right():
                continue
            painter.fillRect(
                QRectF(
                    max(left, plot.left()),
                    plot.top() + 2,
                    max(1.0, min(right, plot.right()) - max(left, plot.left())),
                    plot.height() - 4,
                ),
                brush,
            )

    def _activity_at(self, frame: int) -> Optional[Any]:
        for interval in self._activity:
            if interval.start_frame <= frame <= interval.end_frame:
                return interval
        return None

    def _paint_error_lane(self, painter: QPainter, lane: QRectF) -> None:
        theme = self._theme
        painter.fillRect(self._plot_rect(lane), QColor(theme.bg_base))
        active = self._mode is TimelineMode.ERROR
        sample = self.selected_sample()

        painter.setPen(QColor(theme.text_muted if not active else theme.accent))
        painter.drawText(
            self._caption_rect(lane),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "HATA",
        )

        if sample is None:
            painter.setPen(QColor(theme.text_muted))
            painter.drawText(
                lane,
                Qt.AlignmentFlag.AlignCenter,
                "Hata aralığı için önce bir hareket seçin",
            )
            return

        # Everything outside the selected movement is not editable here, and is
        # masked so the user can see the boundary they are working inside.
        mask = QColor(theme.bg_sunken)
        mask.setAlpha(190 if active else 110)
        left_edge = self._frame_to_x(sample.start_frame)
        right_edge = self._frame_to_x(sample.end_frame + 1)
        painter.fillRect(
            QRectF(_GUTTER, lane.top(), max(0.0, left_edge - _GUTTER), lane.height()),
            mask,
        )
        painter.fillRect(
            QRectF(right_edge, lane.top(), max(0.0, self.width() - right_edge),
                   lane.height()),
            mask,
        )
        boundary = QPen(QColor(theme.accent if active else theme.border_strong))
        boundary.setWidthF(1.2)
        boundary.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(boundary)
        painter.drawLine(
            QPointF(left_edge, lane.top()), QPointF(left_edge, lane.bottom())
        )
        painter.drawLine(
            QPointF(right_edge, lane.top()), QPointF(right_edge, lane.bottom())
        )

        rows = self._interval_rows()
        if not rows:
            painter.setPen(QColor(theme.text_muted))
            hint = (
                "Bu hareket için hata aralığı yok — sürükleyerek ekleyin"
                if active
                else "Hata aralığı yok"
            )
            painter.drawText(
                QRectF(left_edge, lane.top(), max(10.0, right_edge - left_edge),
                       lane.height()),
                Qt.AlignmentFlag.AlignCenter,
                hint,
            )
            return

        for row_index, row in enumerate(rows):
            row_rect = self._interval_lane_rect(row_index, len(rows), lane)
            for interval in row:
                self._paint_interval(painter, interval, row_rect, active)

    def _paint_interval(
        self, painter: QPainter, interval: ErrorInterval, lane: QRectF, active: bool
    ) -> None:
        theme = self._theme
        rect = self._range_rect(interval.start_frame, interval.end_frame, lane, inset=1.5)
        if rect.right() < 0 or rect.left() > self.width():
            return
        selected = interval.interval_id == self._selected_interval_id
        base = QColor(error_class_colour(interval.error_code))
        if not interval.error_code:
            base = QColor(theme.warning)

        fill = QColor(base)
        fill.setAlpha(170 if selected else 110)
        if not active:
            fill.setAlpha(60)
        painter.setBrush(fill)

        pen = QPen(base)
        pen.setWidthF(2.2 if selected else 1.0)
        if not interval.error_code:
            # An interval with no class is unfinished, and says so.
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, theme.radius_sm, theme.radius_sm)

        if selected and active:
            painter.setBrush(QColor(theme.text_primary))
            painter.setPen(Qt.PenStyle.NoPen)
            for x in (rect.left(), rect.right()):
                painter.drawRoundedRect(
                    QRectF(x - 2, rect.top() + 2, 4, rect.height() - 4), 2, 2
                )

        if rect.width() > 26:
            name = self._error_labels.get(
                interval.error_code, interval.error_code
            ) or "sınıf yok"
            painter.setPen(QColor("#0d1117") if active else QColor(theme.text_muted))
            painter.drawText(
                rect.adjusted(5, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name,
            )

    def _paint_pending_create(self, painter: QPainter, lanes: dict[str, QRectF]) -> None:
        if self._drag is None or self._drag.kind != "create":
            return
        current = self._x_to_frame(self.mapFromGlobal(self.cursor().pos()).x())
        lane_key = {"error": "errors", "activity": "activity"}.get(
            self._drag.lane, "movements"
        )
        lane = lanes[lane_key]
        if self._drag.lane == "error":
            sample = self.selected_sample()
            if sample is not None:
                current = int(np.clip(current, sample.start_frame, sample.end_frame))
        start, end = sorted((self._drag.anchor_frame, current))
        rect = self._range_rect(start, end, lane)

        colour = QColor(
            self._theme.warning if self._drag.lane == "error" else self._theme.accent
        )
        fill = QColor(colour)
        fill.setAlpha(60)
        painter.setBrush(fill)
        pen = QPen(colour)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, self._theme.radius_sm, self._theme.radius_sm)

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
            QPolygonF([QPointF(x, 9), QPointF(x - 5, 0), QPointF(x + 5, 0)])
        )

    def _sample_colour(self, sample: MovementSample) -> str:
        theme = self._theme
        if not sample.is_active:
            return theme.text_muted
        return {
            Correctness.CORRECT: theme.success,
            Correctness.INCORRECT: theme.warning,
            Correctness.UNLABELLED: theme.accent,
        }[sample.correctness]


def _nice_step(raw_seconds: float) -> float:
    """Round a tick interval up to a human-friendly value."""
    for candidate in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0):
        if raw_seconds <= candidate:
            return candidate
    return 600.0


__all__ = ["TimelineMode", "TimelineWidget", "error_class_colour"]
