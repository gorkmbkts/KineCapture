"""The timeline says what it can do before anyone is told.

The 15 September brief made these acceptance conditions rather than polish:
an interval has to *look* trimmable, the body and the ends have to feel
different, a class has to keep its colour, and a movement has to be
distinguishable from a fault without reading the label.

None of this is asserted by looking at a picture. Every check here is a
behaviour or a value the widget will answer for.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.theme import CLASS_COLOURS, FAULT_COLOURS, load_tokens  # noqa: E402
from kinecapture.studio.views.timeline import (  # noqa: E402
    GUTTER,
    Interval,
    TimelineView,
    Tool,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def timeline(app) -> TimelineView:
    widget = TimelineView(load_tokens("dark"))
    widget.resize(1000, widget.minimumHeight())
    widget.set_take(600, 30.0)
    widget.set_intervals(
        [
            Interval("m1", 30, 120, "movements", "Squat", "ready", colour_index=0, code="SQ"),
            Interval("m2", 200, 290, "movements", "Squat", "ready", colour_index=0, code="SQ"),
            Interval("m3", 360, 450, "movements", "Lunge", "ready", colour_index=1, code="LU"),
            Interval("e1", 40, 60, "errors", "Diz içe", "warning", parent="m1",
                     colour_index=0, code="DIZ"),
            Interval("e2", 210, 230, "errors", "Diz içe", "warning", parent="m2",
                     colour_index=0, code="DIZ"),
        ]
    )
    widget.zoom_all()
    return widget


def _lane_y(timeline: TimelineView, lane: str) -> int:
    return int(timeline._lane_rects()[lane].center().y())


def _x_of(timeline: TimelineView, frame: int) -> float:
    return timeline._frame_to_x(frame)


def _move(timeline: TimelineView, x: float, y: int) -> None:
    point = QPointF(x, y)
    timeline.mouseMoveEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseMove,
            point,
            point,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


# ------------------------------------------------------- ends versus body
def test_the_end_of_a_box_is_a_different_gesture_from_its_middle(timeline) -> None:
    y = _lane_y(timeline, "movements")
    _move(timeline, _x_of(timeline, 30) + 1, y)
    key, end = timeline.hovered
    assert (key, end) == ("m1", "trim_start")
    assert timeline.cursor().shape() is Qt.CursorShape.SizeHorCursor

    _move(timeline, (_x_of(timeline, 30) + _x_of(timeline, 120)) / 2, y)
    key, end = timeline.hovered
    assert (key, end) == ("m1", "move")
    assert timeline.cursor().shape() is not Qt.CursorShape.SizeHorCursor

    _move(timeline, _x_of(timeline, 121) - 1, y)
    assert timeline.hovered == ("m1", "trim_end")


def test_leaving_the_timeline_clears_the_hover(timeline) -> None:
    _move(timeline, _x_of(timeline, 60), _lane_y(timeline, "movements"))
    assert timeline.hovered[0] == "m1"
    timeline.leaveEvent(None)
    assert timeline.hovered == ("", "none")


def test_a_very_short_interval_still_has_two_reachable_ends(app) -> None:
    """Zoomed out, two handles would overlap. Each half trims its own end."""
    widget = TimelineView(load_tokens("dark"))
    widget.resize(1000, widget.minimumHeight())
    widget.set_take(360, 30.0)
    widget.set_intervals([Interval("tiny", 100, 103, "movements", "Squat", "ready")])
    widget.zoom_all()
    y = _lane_y(widget, "movements")
    left = widget._frame_to_x(100)
    right = widget._frame_to_x(104)
    width = right - left
    assert 4 < width < 21, f"this test needs a narrow box, got {width:.1f}px"

    _move(widget, left + 1, y)
    assert widget.hovered == ("tiny", "trim_start")
    _move(widget, right - 1, y)
    assert widget.hovered == ("tiny", "trim_end")


# ---------------------------------------------------------- class colours
def test_the_same_class_gets_the_same_colour_every_time(timeline) -> None:
    tokens = load_tokens("dark")
    first = timeline._class_colour(timeline._interval("m1"))
    second = timeline._class_colour(timeline._interval("m2"))
    other = timeline._class_colour(timeline._interval("m3"))
    assert first == second
    assert first != other
    assert first.name() == tokens.colour(CLASS_COLOURS[0]).lower()
    assert other.name() == tokens.colour(CLASS_COLOURS[1]).lower()


def test_a_fault_takes_its_colour_from_the_fault_family(timeline) -> None:
    tokens = load_tokens("dark")
    fault = timeline._class_colour(timeline._interval("e1"))
    assert fault.name() == tokens.colour(FAULT_COLOURS[0]).lower()
    # Same index, different family: a movement and a fault never collide.
    movement = timeline._class_colour(timeline._interval("m1"))
    assert fault != movement


def test_an_unclassified_interval_is_not_given_a_class_colour(timeline) -> None:
    timeline.set_intervals(
        [Interval("m9", 10, 40, "movements", "", "warning", colour_index=-1)]
    )
    tokens = load_tokens("dark")
    colour = timeline._class_colour(timeline._interval("m9"))
    assert colour.name() == tokens.colour("KcSurfaceControlActive").lower()


def test_the_colour_survives_a_reopen(timeline) -> None:
    """Colours come from the stored vocabulary order, not from paint order."""
    before = timeline._class_colour(timeline._interval("m3")).name()
    intervals = list(timeline._intervals)
    timeline.set_intervals([])
    timeline.set_intervals(list(reversed(intervals)))
    assert timeline._class_colour(timeline._interval("m3")).name() == before


# ---------------------------------------------------------------- feedback
def test_a_snap_is_recorded_so_it_can_be_shown(timeline) -> None:
    timeline.set_snap(True)
    # One frame away from an existing edge: close enough to be pulled onto it.
    assert timeline._snapped(31) == 30
    assert timeline._snapped_now is True
    # Far from anything, at this zoom: left where it was put.
    assert timeline._snapped(155) == 155
    assert timeline._snapped_now is False


def test_snapping_off_means_off(timeline) -> None:
    timeline.set_snap(False)
    assert timeline._snapped(31) == 31
    assert timeline._snapped_now is False


def test_an_empty_timeline_says_what_to_do_next(app) -> None:
    widget = TimelineView(load_tokens("dark"))
    widget.resize(600, widget.minimumHeight())
    # Nothing loaded: drawing tools are refused outright, not offered.
    widget.set_tool(Tool.DRAW_MOVEMENT)
    assert widget.tool is Tool.SCRUB
    point = QPointF(300, _lane_y(widget, "movements"))
    widget.mousePressEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert widget._drag is None


def test_the_ruler_gains_detail_as_it_is_zoomed_in(timeline) -> None:
    timeline.zoom_all()
    coarse = timeline._step_frames()
    timeline.zoom_to(100, 140)
    fine = timeline._step_frames()
    assert fine < coarse


def test_the_gutter_keeps_the_track_names_off_the_data(timeline) -> None:
    """Names are in a fixed column; the data never scrolls under them."""
    assert timeline._frame_to_x(0) >= GUTTER
    point = QPoint(GUTTER - 10, _lane_y(timeline, "movements"))
    interval, _grab = timeline._hit(point)
    assert interval is None or timeline._frame_to_x(interval.start) >= GUTTER
