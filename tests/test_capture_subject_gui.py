"""Clicking a person, and the screens that show what that did.

A selection the user cannot see is as dangerous as no selection at all, so
these tests construct the real widgets, send real mouse events, and check what
the screen ends up saying - offscreen, in both themes, and at the 1366x768
minimum the project promises to stay usable at.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from kinecapture.core.config import AppConfig
from kinecapture.domain.activity import ActivityState
from kinecapture.domain.enums import ConsentStatus, TakeQuality
from kinecapture.gui.pages.capture import CapturePage
from kinecapture.gui.pages.review import ReviewPage
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import get_theme
from kinecapture.gui.widgets.timeline import TimelineMode, TimelineWidget
from kinecapture.gui.widgets.video_view import VideoView


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _mouse_event(kind, x: float, y: float) -> QMouseEvent:
    """The non-deprecated overload, which also wants a global position."""
    point = QPointF(x, y)
    return QMouseEvent(
        kind,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _click(widget, x: float, y: float) -> None:
    widget.mousePressEvent(
        _mouse_event(QMouseEvent.Type.MouseButtonPress, x, y)
    )


# ------------------------------------------------------------ VideoView


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_click_maps_to_the_right_source_pixel_through_the_letterbox(
    qt_app, theme_name
) -> None:
    """A click must land on the same pixel at any window size or aspect."""
    view = VideoView(get_theme(theme_name))
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    view.set_rgb(image)

    for width, height in ((640, 480), (900, 300), (301, 777)):
        view.resize(width, height)
        target = view._letterbox()
        # A point one quarter across and one third down the *image*.
        expected = (160 * 0.25, 120 / 3)
        wx = target.left() + expected[0] * target.width() / 160
        wy = target.top() + expected[1] * target.height() / 120
        got = view.widget_to_image(wx, wy)
        assert got is not None
        assert got[0] == pytest.approx(expected[0], abs=0.5)
        assert got[1] == pytest.approx(expected[1], abs=0.5)


def test_a_click_on_the_letterbox_bar_is_a_click_on_nothing(qt_app) -> None:
    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((100, 100, 3), dtype=np.uint8))
    view.resize(600, 200)  # wide window, bars on the left and right
    target = view._letterbox()
    assert view.widget_to_image(target.left() - 10, 100) is None

    received: list[tuple[float, float]] = []
    view.clicked.connect(lambda x, y: received.append((x, y)))
    _click(view, target.left() - 10, 100)
    assert received == []
    _click(view, target.center().x(), target.center().y())
    assert len(received) == 1


def test_the_click_signal_carries_coordinates_not_just_a_notification(qt_app):
    """The page has to know *where*; guessing from the widget would be a bug."""
    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((100, 200, 3), dtype=np.uint8))
    view.resize(400, 200)
    received: list[tuple[float, float]] = []
    view.clicked.connect(lambda x, y: received.append((x, y)))

    target = view._letterbox()
    _click(view, target.left() + target.width() * 0.75, target.top() + 10)
    assert len(received) == 1
    assert received[0][0] == pytest.approx(150.0, abs=2.0)


# --------------------------------------------------------- capture page


@pytest.fixture
def capture_page(qt_app, workspace, dataset_root, isolated_user_state):
    participant = workspace.create_participant()
    session = workspace.create_session(
        participant.participant_id, consent=ConsentStatus.GRANTED
    )
    config = AppConfig(dataset_root=dataset_root, backend="mock")
    state = AppState(config)
    state.open_project(workspace.root)
    state.set_participant(participant)
    state.set_session(session)
    page = CapturePage(state)
    page.on_activated()
    page.resize(1400, 900)

    service = state.ensure_capture_service()
    service.connect()
    service.start_preview()
    deadline = time.time() + 10
    while time.time() < deadline:
        qt_app.processEvents()
        page._pull_frame()
        if page._last_packet is not None and page._last_packet.bodies:
            break
        time.sleep(0.01)
    yield page, service
    service.shutdown()


def _click_on_body(page, body) -> None:
    points = body.joint_positions_2d
    visible = points[np.isfinite(points).all(axis=1)]
    image_point = visible[0]
    page._video.resize(800, 600)
    target = page._video._letterbox()
    image = page._video._image
    wx = target.left() + float(image_point[0]) * target.width() / image.width()
    wy = target.top() + float(image_point[1]) * target.height() / image.height()
    _click(page._video, wx, wy)


def test_clicking_a_person_locks_onto_them(capture_page) -> None:
    page, service = capture_page
    assert page._last_packet is not None and page._last_packet.bodies
    body = page._last_packet.bodies[0]

    assert not service.subject_lock.is_selected
    _click_on_body(page, body)

    lock = service.subject_lock
    assert lock.is_selected
    assert lock.tracking_id == body.tracking_id
    assert lock.state.value == "locked"
    rows = {key.text(): value.text() for key, value in page._subject_details._rows}
    assert rows["Eşlenen tracker ID"] == str(body.tracking_id)
    assert rows["Mantıksal kimlik"].startswith("subj_")


def test_clicking_empty_space_leaves_the_selection_alone(capture_page) -> None:
    page, service = capture_page
    body = page._last_packet.bodies[0]
    _click_on_body(page, body)
    original = service.subject_lock.tracking_id

    target = page._video._letterbox()
    _click(page._video, target.left() + 1, target.top() + 1)
    assert service.subject_lock.tracking_id == original


def test_the_archive_card_shows_a_real_cost_and_capacity(capture_page) -> None:
    page, _service = capture_page
    page._refresh_archive_card()
    rows = {key.text(): value.text() for key, value in page._archive_details._rows}
    assert "GB / dakika" in rows["Tahmini boyut"]
    assert rows["Derinlik arşivi"].startswith("kayıpsız")
    assert "dakika" in rows["Kayıt süresi kapasitesi"]


def test_the_capture_page_paints_with_a_locked_subject(capture_page) -> None:
    page, _service = capture_page
    _click_on_body(page, page._last_packet.bodies[0])
    page._redraw_last_frame()
    assert not page.grab().isNull()
    page.resize(1366, 768)
    assert not page.grab().isNull()


# ---------------------------------------------------------- review page


@pytest.fixture
def review_page(qt_app, workspace, session, dataset_root, isolated_user_state):
    from kinecapture.capture.service import CaptureService
    from tests.conftest import paced_backend, record_take

    schema = workspace.label_schema
    if not schema.exercises:
        schema.add_exercise("Squat")
        workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=40)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    config = AppConfig(dataset_root=dataset_root, backend="mock")
    state = AppState(config)
    state.open_project(workspace.root)
    page = ReviewPage(state)
    page.on_activated()
    page.resize(1600, 980)
    page.open_take(take)
    qt_app.processEvents()
    return page


def test_activity_mode_is_a_first_class_mode(review_page) -> None:
    page = review_page
    page._set_timeline_mode(TimelineMode.ACTIVITY)
    assert page._timeline.mode is TimelineMode.ACTIVITY
    assert "AKTİVİTE" in page._mode_hint.text()
    # And it says the thing that must never be forgotten.
    assert "SAYILMAZ" in page._mode_hint.text()
    assert not page._activity_detail.isHidden()


def test_drawing_and_classifying_an_activity_band(review_page) -> None:
    page = review_page
    page._set_timeline_mode(TimelineMode.ACTIVITY)
    page._activity_created(0, 9)
    assert len(page._repo.activity_intervals) == 1
    page._set_activity_state(ActivityState.TRANSITION)
    assert page._repo.activity_intervals[0].state is ActivityState.TRANSITION

    page._activity_created(10, 24)
    page._set_activity_state(ActivityState.TARGET_EXERCISE)
    target = page._repo.activity_intervals[1]
    assert target.state is ActivityState.TARGET_EXERCISE
    assert target.exercise  # a target band always carries an exercise


def test_the_screen_reports_unlabelled_time_as_unlabelled(review_page) -> None:
    page = review_page
    page._set_timeline_mode(TimelineMode.ACTIVITY)
    page._activity_created(0, 9)
    page._set_activity_state(ActivityState.BACKGROUND)
    page._refresh_activity_list()

    hint = page._activity_hint.text()
    assert "Etiketlenmemiş" in hint
    assert "arka plan sayılmaz" in hint
    coverage = page._repo.activity_coverage()
    assert coverage.unlabelled_frames == page._loaded.frame_count - 10


def test_filling_gaps_requires_confirmation_from_the_domain(review_page) -> None:
    from kinecapture.core.errors import ValidationError

    page = review_page
    page._activity_created(0, 9)
    with pytest.raises(ValidationError):
        page._repo.fill_gaps_with_background()


@pytest.mark.parametrize("size", [(1600, 980), (1366, 768)])
def test_the_review_page_paints_in_activity_mode(review_page, size) -> None:
    page = review_page
    page._set_timeline_mode(TimelineMode.ACTIVITY)
    page._activity_created(0, 9)
    page._set_activity_state(ActivityState.BACKGROUND)
    page.resize(*size)
    assert not page.grab().isNull()


# ------------------------------------------------------------- timeline


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_the_activity_lane_paints_bands_and_gaps(qt_app, theme_name) -> None:
    from kinecapture.domain.activity import ActivityInterval

    timeline = TimelineWidget(get_theme(theme_name))
    timeline.set_take(120, fps=30.0)
    timeline.set_mode(TimelineMode.ACTIVITY)
    timeline.set_activity_intervals(
        [
            ActivityInterval.create(0, 29, state=ActivityState.BACKGROUND),
            ActivityInterval.create(
                40, 79, state=ActivityState.TARGET_EXERCISE, exercise="squat"
            ),
            # 30..39 and 80..119 are deliberately left unlabelled.
        ]
    )
    timeline.resize(900, 260)
    assert not timeline.grab().isNull()

    timeline.set_activity_intervals([])
    assert not timeline.grab().isNull()


def test_dragging_in_the_activity_lane_requests_a_new_band(qt_app) -> None:
    timeline = TimelineWidget(get_theme("dark"))
    timeline.set_take(100, fps=30.0)
    timeline.set_mode(TimelineMode.ACTIVITY)
    timeline.resize(900, 260)
    timeline.show()

    requests: list[tuple[int, int]] = []
    timeline.activity_create_requested.connect(
        lambda start, end: requests.append((start, end))
    )

    lane = timeline._lane_rects()["activity"]
    start_x = timeline._frame_to_x(10)
    end_x = timeline._frame_to_x(40)
    _click(timeline, start_x, lane.center().y())
    timeline.mouseReleaseEvent(
        _mouse_event(
            QMouseEvent.Type.MouseButtonRelease, end_x, lane.center().y()
        )
    )

    assert requests
    start, end = requests[0]
    assert start == pytest.approx(10, abs=1)
    assert end == pytest.approx(40, abs=1)
