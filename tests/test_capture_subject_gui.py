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
from kinecapture.domain.project import CaptureProfile
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
    from tests.conftest import authenticate_state

    participant = workspace.create_participant()
    # These tests exercise the retained live 3D workflow explicitly.
    config = AppConfig(dataset_root=dataset_root, backend="mock", capture=CaptureProfile.legacy())
    state = AppState(config)
    authenticate_state(state, workspace)
    state.prepare_capture(participant)
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
    from tests.conftest import authenticate_state, paced_backend, record_take

    schema = workspace.label_schema
    if not schema.exercises:
        schema.add_exercise("Squat")
        workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    # Lock onto a person before recording: a take reviewed without a subject
    # association is the *legacy* case, not the normal one, and the review
    # screen must be exercised on a normal take.
    service.start_preview()
    deadline = time.time() + 10
    while time.time() < deadline:
        packet = service.peek_frame()
        if packet is not None and packet.bodies:
            service.select_subject(packet.bodies[0])
            break
        time.sleep(0.01)
    assert service.subject_lock.is_selected, "fixture failed to lock a subject"

    take = record_take(service, workspace, session, frames=40)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    config = AppConfig(dataset_root=dataset_root, backend="mock")
    state = AppState(config)
    authenticate_state(state, workspace)
    page = ReviewPage(state)
    page.on_activated()
    page.resize(1600, 980)
    page.open_take(take)
    qt_app.processEvents()
    return page


# ------------------------------------------- only the selected person is drawn


def _subject_frames(page):
    """Positions where the recorded subject really is present."""
    stream = page._loaded.stream
    return [
        position
        for position in range(stream.frame_count)
        if stream.frame_at(position).subject_body() is not None
    ]


def test_review_draws_the_recorded_subject_and_nobody_else(review_page) -> None:
    """The authority is ``subject_body()``, and there is no second opinion."""
    page = review_page
    stream = page._loaded.stream
    assert stream.has_subject_lock, "fixture must record a locked subject"

    present = _subject_frames(page)
    assert present, "the mock recording should contain the subject somewhere"
    page._seek(present[0])

    frame = stream.frame_at(present[0])
    drawn = page._scene._bodies
    assert len(drawn) == 1
    assert drawn[0].tracking_id == frame.subject_body().tracking_id
    # Any other body in the frame is not drawn at all - not even dimmed.
    others = {b.tracking_id for b in frame.bodies} - {drawn[0].tracking_id}
    assert not (others & {b.tracking_id for b in drawn})


def test_a_frame_without_the_subject_draws_no_skeleton_and_says_so(
    review_page, monkeypatch
) -> None:
    """Absence is reported, never filled in from a neighbouring body."""
    page = review_page
    monkeypatch.setattr(
        type(page._loaded), "review_body_at", lambda self, position: None
    )
    page._seek(3)

    assert page._scene._bodies == ()
    assert "bulunamadı" in page._alert.text()
    # And the last pose is not left frozen on screen from the previous frame.
    assert page._scene.video_view._bodies == ()


def test_the_body_selector_is_gone(review_page) -> None:
    """Choosing "which body" was the bug, not a feature."""
    page = review_page
    assert not hasattr(page, "_body_selector")


def test_coverage_curve_describes_the_drawn_person(review_page) -> None:
    """The timeline and the viewport must not disagree about who was tracked."""
    page = review_page
    curve = page._loaded.subject_coverage_curve()
    assert curve.shape == (page._loaded.frame_count,)
    for position in range(page._loaded.frame_count):
        body = page._loaded.review_body_at(position)
        if body is None:
            assert curve[position] == 0.0
        else:
            assert curve[position] == pytest.approx(body.valid_joint_ratio)


# --------------------------------------------------------- overlay geometry


def test_overlay_uses_the_camera_pixel_space_not_the_proxy_size(qt_app) -> None:
    """The root cause: 2D joints are camera pixels, the picture is a proxy.

    A joint at the centre of the camera image must land at the centre of the
    drawn rectangle whatever size either of them is. Dividing by the proxy's
    width instead put it 1.5x-2x too far right, which is exactly the
    misalignment this fixes.
    """
    from PySide6.QtCore import QRectF

    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((360, 640, 3), dtype=np.uint8))
    view.set_joint_space((960, 540))

    target = QRectF(0, 0, 640, 360)
    centre = view._project_2d((480.0, 270.0), target)
    assert centre is not None
    assert centre.x() == pytest.approx(320.0)
    assert centre.y() == pytest.approx(180.0)

    # Independent of how large it is drawn.
    bigger = view._project_2d((480.0, 270.0), QRectF(0, 0, 1280, 720))
    assert bigger.x() == pytest.approx(640.0)
    assert bigger.y() == pytest.approx(360.0)

    # And the corners map to the corners.
    corner = view._project_2d((960.0, 540.0), target)
    assert corner.x() == pytest.approx(640.0)
    assert corner.y() == pytest.approx(360.0)


def test_without_a_joint_space_the_image_is_the_space(qt_app) -> None:
    """Live capture shows the full camera frame, so the two coincide."""
    from PySide6.QtCore import QRectF

    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((540, 960, 3), dtype=np.uint8))
    view.set_joint_space(None)

    point = view._project_2d((480.0, 270.0), QRectF(0, 0, 960, 540))
    assert point.x() == pytest.approx(480.0)
    assert point.y() == pytest.approx(270.0)


def test_no_2d_and_no_calibration_means_no_overlay(qt_app) -> None:
    """An approximate skeleton is worse than none: it reads as bad tracking."""
    from PySide6.QtCore import QRectF

    from kinecapture.domain.enums import TrackingState
    from kinecapture.domain.models import BodyPose

    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((360, 640, 3), dtype=np.uint8))
    view.set_joint_space((960, 540))

    body = BodyPose(
        tracking_id=1,
        tracking_state=TrackingState.OK,
        body_format="body_38",
        joint_positions_xyz=np.zeros((5, 3), dtype=np.float32),
        joint_confidences=np.ones(5, dtype=np.float32),
    )
    assert body.joint_positions_2d is None
    assert not view.can_overlay([body])
    assert view._body_points(body, QRectF(0, 0, 640, 360)) == [None] * 5


def test_calibration_projection_is_used_when_2d_is_absent(qt_app) -> None:
    """A recorded intrinsics block is a real projection, not a guess."""
    from PySide6.QtCore import QRectF

    view = VideoView(get_theme("dark"))
    view.set_rgb(np.zeros((360, 640, 3), dtype=np.uint8))
    view.set_joint_space(
        (960, 540),
        calibration={
            "fx": 500.0,
            "fy": 500.0,
            "cx": 480.0,
            "cy": 270.0,
            "image_width": 960,
            "image_height": 540,
        },
    )
    # A point straight down the optical axis lands on the principal point.
    point = view._project_with_calibration((0.0, 0.0, 2.0), QRectF(0, 0, 640, 360))
    assert point.x() == pytest.approx(320.0)
    assert point.y() == pytest.approx(180.0)
    # Y is up in the capture frame and down in the image, so they oppose.
    higher = view._project_with_calibration((0.0, 0.5, 2.0), QRectF(0, 0, 640, 360))
    assert higher.y() < point.y()


def test_a_missing_proxy_frame_is_reported_not_substituted(review_page) -> None:
    """Re-showing another moment's picture looks exactly like a tracking bug."""
    page = review_page
    loaded = page._loaded
    if loaded.video is None or not loaded.has_video:
        pytest.skip("this take has no proxy video")
    assert loaded.video_position_for(loaded.video.frame_count) is None


# -------------------------------------------------------- activity retirement


def test_the_activity_mode_no_longer_exists() -> None:
    assert [m.value for m in TimelineMode] == ["movement", "error"]
    assert not hasattr(TimelineMode, "ACTIVITY")


def test_the_timeline_has_no_activity_lane_or_signals(qt_app) -> None:
    timeline = TimelineWidget(get_theme("dark"))
    timeline.set_take(120, fps=30.0)
    assert "activity" not in timeline._lane_rects()
    for name in (
        "set_activity_intervals",
        "set_selected_activity",
        "activity_create_requested",
        "activity_double_clicked",
    ):
        assert not hasattr(timeline, name), f"{name} should be retired"


def test_the_review_page_has_no_activity_authoring(review_page) -> None:
    page = review_page
    for name in (
        "_activity_card",
        "_activity_list",
        "_activity_created",
        "_set_activity_state",
        "_fill_background",
        "_link_activity_to_sample",
    ):
        assert not hasattr(page, name), f"{name} should be retired"


def test_existing_activity_intervals_survive_every_later_save(
    review_page, qt_app
) -> None:
    """Retiring the editor must not delete what people already recorded."""
    from kinecapture.domain.activity import ActivityInterval

    page = review_page
    workspace = page.state.workspace
    take = page._loaded.take
    workspace.save_samples(
        take,
        [],
        activity_intervals=[
            ActivityInterval.create(0, 9, state=ActivityState.BACKGROUND),
            ActivityInterval.create(
                10, 19, state=ActivityState.TARGET_EXERCISE, exercise="squat"
            ),
        ],
    )
    page.open_take(take)
    qt_app.processEvents()
    assert len(page._repo.activity_intervals) == 2

    # A completely unrelated edit, then a save.
    page._create_sample_range(20, 30)
    page._save_now()

    reloaded = workspace.load_activity_intervals(take)
    assert len(reloaded) == 2
    assert reloaded[1].exercise == "squat"


def test_unknown_annotation_blocks_are_preserved(workspace, session) -> None:
    """A block written by another version is carried over, not dropped."""
    from kinecapture.capture.service import CaptureService
    from kinecapture.core.jsonio import read_json_mapping, write_json
    from tests.conftest import paced_backend, record_take

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=20)
    service.shutdown()

    paths = workspace.take_paths(take)
    workspace.save_samples(take, [])
    document = read_json_mapping(paths.segments)
    document["some_future_block"] = {"kept": True}
    write_json(paths.segments, document, overwrite=True)

    workspace.save_samples(take, [])
    assert read_json_mapping(paths.segments)["some_future_block"] == {"kept": True}


# ------------------------------------------------- capture screen information


def test_capture_reference_panels_live_in_a_window_not_a_column(
    capture_page,
) -> None:
    """The two live views own the screen; the panels open on demand."""
    page, _service = capture_page
    assert page._info is not None
    assert not page._info.isVisible()
    # The panels still exist and still update - they just have a home now.
    assert page._health_details is not None
    assert page._task_details is not None
    assert page._subject_details is not None
    assert page._archive_details is not None

    page._toggle_info()
    assert page._info.isVisible()
    page._toggle_info()
    assert not page._info.isVisible()


def test_capture_alert_strip_stays_on_the_main_screen(capture_page) -> None:
    """Critical alerts may never be behind the info window's button."""
    page, _service = capture_page
    page._refresh_alerts()
    # A page with a locked subject and no losses says nothing.
    assert not page._alert_label.isHidden()
    assert not page._confirm_subject_button.isHidden()
    assert not page._clear_subject_button.isHidden()

    page._disk_shortfall = "Disk yetersiz: test"
    page._refresh_alerts()
    assert "Disk yetersiz" in page._alert_label.text()

    page._disk_shortfall = ""
    page._clear_subject()
    page._refresh_alerts()
    assert "seçilmedi" in page._alert_label.text()


@pytest.mark.parametrize("size", [(1120, 700), (1366, 768), (1600, 980)])
@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_capture_and_review_paint_at_every_supported_size(
    capture_page, review_page, size, theme_name
) -> None:
    """Real paint paths, both themes, down to the smallest promised window.

    The check that matters is ``minimumSizeHint``, not ``sizeHint``: a page
    whose minimum exceeds the window is one that will be clipped or will force
    a horizontal scroll, whatever its preferred size happens to be.
    """
    width, height = size
    capture, _service = capture_page
    for page in (capture, review_page):
        page.state.set_theme(theme_name)
        page.resize(width, height)
        page.show()
        QApplication.processEvents()

        image = page.grab()
        assert not image.isNull()
        assert image.width() > 0 and image.height() > 0

        minimum = page.minimumSizeHint()
        assert minimum.width() <= width, (
            f"{type(page).__name__} needs {minimum.width()}px at {width}px wide"
        )
        # A page is laid out inside the window chrome, so it never gets the
        # full height; the margin below is what the app frame actually costs.
        assert minimum.height() <= height - 90, (
            f"{type(page).__name__} needs {minimum.height()}px at {height}px tall"
        )
        page.hide()


def test_dense_rows_wrap_instead_of_clipping(capture_page, review_page) -> None:
    """Every control in a wrapping row is fully inside it at 1120px.

    This is the failure the flow layout exists to prevent: a row of ten
    controls whose last two are drawn past the bottom edge of their own
    container, invisible and unclickable.
    """
    from kinecapture.gui.widgets.flow_layout import FlowContainer

    capture, _service = capture_page
    for page in (capture, review_page):
        page.resize(1120, 700)
        page.show()
        for _ in range(3):
            QApplication.processEvents()
        containers = page.findChildren(FlowContainer)
        assert containers, f"{type(page).__name__} has no wrapping row"
        for container in containers:
            layout = container.layout()
            assert container.height() >= layout.heightForWidth(container.width())
            for index in range(layout.count()):
                item = layout.itemAt(index).widget()
                geometry = item.geometry()
                assert geometry.bottom() <= container.height(), (
                    f"{item.toolTip() or item.text()!r} is clipped vertically"
                )
                assert geometry.right() <= container.width(), (
                    f"{item.toolTip() or item.text()!r} is clipped horizontally"
                )
        page.hide()
