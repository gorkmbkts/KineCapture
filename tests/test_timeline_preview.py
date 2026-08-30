"""Video-editor style trim preview on the timeline.

Dragging an interval edge, or drawing a new one, should show the frame under
the moving endpoint - and then leave the playhead exactly where it was. The old
behaviour drove the normal seek path, so every drag both stuttered the viewer
and dumped the playhead wherever the mouse happened to come up, while writing
one repository mutation, one undo snapshot and one autosave per mouse move.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.capture.service import CaptureService  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.domain.enums import TakeQuality  # noqa: E402
from kinecapture.gui.theme import get_theme  # noqa: E402
from kinecapture.gui.widgets.scene_view import SceneMode  # noqa: E402
from kinecapture.gui.widgets.timeline import TimelineMode, TimelineWidget  # noqa: E402
from kinecapture.playback.take_reader import load_take  # noqa: E402
from tests.conftest import paced_backend, record_take  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _event(kind, x: float, y: float) -> QMouseEvent:
    point = QPointF(x, y)
    return QMouseEvent(
        kind,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


class Recorder:
    """Collects everything a timeline says during one gesture."""

    def __init__(self, timeline: TimelineWidget) -> None:
        self.started = 0
        self.previews: list[int] = []
        self.finished = 0
        self.cancelled = 0
        self.sample_bounds: list[tuple[str, int, int]] = []
        self.interval_bounds: list[tuple[str, int, int]] = []
        self.sample_creates: list[tuple[int, int]] = []
        self.interval_creates: list[tuple[int, int]] = []
        self.positions: list[int] = []

        timeline.edit_started.connect(lambda: setattr(self, "started", self.started + 1))
        timeline.preview_position_changed.connect(self.previews.append)
        timeline.edit_finished.connect(
            lambda: setattr(self, "finished", self.finished + 1)
        )
        timeline.edit_cancelled.connect(
            lambda: setattr(self, "cancelled", self.cancelled + 1)
        )
        timeline.sample_bounds_changed.connect(
            lambda i, s, e: self.sample_bounds.append((i, s, e))
        )
        timeline.interval_bounds_changed.connect(
            lambda i, s, e: self.interval_bounds.append((i, s, e))
        )
        timeline.sample_create_requested.connect(
            lambda s, e: self.sample_creates.append((s, e))
        )
        timeline.interval_create_requested.connect(
            lambda s, e: self.interval_creates.append((s, e))
        )
        timeline.position_changed.connect(self.positions.append)


def drag(timeline, lane_key, from_frame, to_frame, *, release=True, steps=4):
    """Press, move in steps and (optionally) release across a lane."""
    lane = timeline._lane_rects()[lane_key]
    y = lane.center().y()
    timeline.mousePressEvent(
        _event(QMouseEvent.Type.MouseButtonPress, timeline._frame_to_x(from_frame), y)
    )
    for step in range(1, steps + 1):
        frame = from_frame + (to_frame - from_frame) * step / steps
        timeline.mouseMoveEvent(
            _event(QMouseEvent.Type.MouseMove, timeline._frame_to_x(frame), y)
        )
    if release:
        timeline.mouseReleaseEvent(
            _event(
                QMouseEvent.Type.MouseButtonRelease,
                timeline._frame_to_x(to_frame),
                y,
            )
        )


@pytest.fixture
def timeline(qapp, workspace, session):
    from kinecapture.annotations.repository import AnnotationRepository

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=80)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    repo = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    sample = repo.create_sample(10, 50)
    repo.label_sample(sample.sample_id, exercise="squat", reviewed=True)
    interval = repo.create_error_interval(
        sample.sample_id, 20, 30, error_code="diz-ice-cokuyor"
    )

    widget = TimelineWidget(get_theme("dark"))
    widget.set_take(loaded.frame_count, fps=30.0)
    widget.set_samples(repo.samples)
    widget.resize(1000, 260)
    widget.show()
    qapp.processEvents()
    yield widget, repo, sample, interval
    widget.hide()


# ------------------------------------------------------- the six drag kinds


def test_resizing_a_movement_previews_the_moving_edge(timeline) -> None:
    widget, _repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    drag(widget, "movements", sample.start_frame, sample.start_frame + 8)

    assert log.started == 1
    assert log.previews, "the dragged edge must be previewed"
    assert log.previews[-1] == pytest.approx(sample.start_frame + 8, abs=1)
    # Exactly one commit for the whole gesture.
    assert len(log.sample_bounds) == 1
    assert log.finished == 1
    identifier, start, end = log.sample_bounds[0]
    assert identifier == sample.sample_id
    assert start == pytest.approx(sample.start_frame + 8, abs=1)
    assert end == sample.end_frame


def test_resizing_the_end_of_a_movement_previews_the_end(timeline) -> None:
    widget, _repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    # The right handle is the edge *after* the last frame, which is where
    # ``_range_rect`` puts it.
    drag(widget, "movements", sample.end_frame + 1, sample.end_frame - 6)

    assert log.previews[-1] == pytest.approx(sample.end_frame - 6, abs=1)
    assert len(log.sample_bounds) == 1
    _identifier, start, end = log.sample_bounds[0]
    assert start == sample.start_frame
    assert end == pytest.approx(sample.end_frame - 6, abs=1)


def test_creating_a_movement_previews_the_moving_end_and_commits_once(
    timeline,
) -> None:
    widget, _repo, _sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    log = Recorder(widget)

    drag(widget, "movements", 60, 74)

    assert log.started == 1
    assert log.previews, "a create drag previews too, not only a resize"
    assert log.previews[-1] == pytest.approx(74, abs=1)
    assert len(log.sample_creates) == 1
    assert log.finished == 1


def test_resizing_and_creating_an_error_interval_previews(timeline) -> None:
    widget, _repo, sample, interval = timeline
    widget.set_mode(TimelineMode.ERROR)
    widget.set_selected_sample(sample.sample_id)
    widget.set_selected_interval(interval.interval_id)
    log = Recorder(widget)

    drag(widget, "errors", interval.start_frame, interval.start_frame + 4)
    assert log.previews
    assert len(log.interval_bounds) == 1

    log2 = Recorder(widget)
    drag(widget, "errors", 38, 46)
    assert log2.previews
    assert len(log2.interval_creates) == 1


def test_an_error_preview_is_clamped_to_its_parent_movement(timeline) -> None:
    """What the preview shows is what the commit will produce."""
    widget, _repo, sample, interval = timeline
    widget.set_mode(TimelineMode.ERROR)
    widget.set_selected_sample(sample.sample_id)
    widget.set_selected_interval(interval.interval_id)
    log = Recorder(widget)

    # Drag the start far below the movement's own start.
    drag(widget, "errors", interval.start_frame, sample.start_frame - 30)

    assert all(frame >= sample.start_frame for frame in log.previews), (
        "the preview must obey the same clamp as the final bounds"
    )
    _identifier, start, _end = log.interval_bounds[0]
    assert start >= sample.start_frame


def test_moving_a_whole_band_still_commits_once(timeline) -> None:
    widget, _repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    middle = (sample.start_frame + sample.end_frame) // 2
    drag(widget, "movements", middle, middle + 5)

    assert len(log.sample_bounds) == 1
    _identifier, start, end = log.sample_bounds[0]
    assert end - start == sample.end_frame - sample.start_frame, (
        "a move keeps the span"
    )


# --------------------------------------------------------- no write storms


def test_a_drag_writes_to_the_repository_exactly_once(timeline) -> None:
    """One gesture, one mutation, one undo step, one autosave."""
    widget, repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)

    original_start = sample.start_frame
    changes: list[int] = []
    repo.add_change_listener(lambda: changes.append(1))
    widget.sample_bounds_changed.connect(
        lambda i, s, e: repo.update_sample_bounds(i, s, e)
    )

    drag(widget, "movements", original_start, original_start + 9, steps=12)

    assert len(changes) == 1, f"{len(changes)} writes for one drag"
    assert repo.find(sample.sample_id).start_frame != original_start
    repo.undo()
    restored = repo.find(sample.sample_id)
    assert restored.start_frame == original_start, (
        "one Ctrl+Z must undo the whole drag"
    )


def test_the_band_follows_the_cursor_before_anything_is_written(timeline) -> None:
    """The tentative bounds are what gets drawn, or the band would sit still."""
    widget, repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)

    original_start = sample.start_frame
    changes: list[int] = []
    repo.add_change_listener(lambda: changes.append(1))

    drag(widget, "movements", original_start, original_start + 10, release=False)

    drawn = widget._drawn_bounds(sample.sample_id, original_start, sample.end_frame)
    assert drawn[0] == pytest.approx(original_start + 10, abs=1)
    # ... and the repository has not heard a word about it.
    assert repo.find(sample.sample_id).start_frame == original_start
    assert changes == []

    widget.cancel_drag()


# ------------------------------------------------------------- cancelling


def test_escape_abandons_the_edit_and_writes_nothing(timeline) -> None:
    widget, repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    original_start = sample.start_frame
    changes: list[int] = []
    repo.add_change_listener(lambda: changes.append(1))

    drag(widget, "movements", original_start, original_start + 12, release=False)
    widget.cancel_drag()

    assert log.cancelled == 1
    assert log.finished == 0
    assert log.sample_bounds == []
    assert repo.find(sample.sample_id).start_frame == original_start
    assert changes == []
    # The band snaps back to its stored bounds.
    assert widget._drawn_bounds(
        sample.sample_id, original_start, sample.end_frame
    ) == (original_start, sample.end_frame)


def test_losing_focus_mid_drag_abandons_it(timeline) -> None:
    widget, repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    drag(widget, "movements", sample.start_frame, sample.start_frame + 7, release=False)
    widget.clearFocus()

    assert log.sample_bounds == []
    assert repo.find(sample.sample_id).start_frame == sample.start_frame


def test_a_drag_that_changes_nothing_commits_nothing(timeline) -> None:
    widget, _repo, sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    widget.set_selected_sample(sample.sample_id)
    log = Recorder(widget)

    drag(widget, "movements", sample.start_frame, sample.start_frame)

    assert log.sample_bounds == []
    assert log.finished == 0
    assert log.cancelled == 1


def test_a_short_click_still_scrubs(timeline) -> None:
    """Clicking an empty lane must keep moving the playhead, as it always did."""
    widget, _repo, _sample, _interval = timeline
    widget.set_mode(TimelineMode.MOVEMENT)
    log = Recorder(widget)

    drag(widget, "movements", 64, 64, steps=1)

    assert log.sample_creates == []
    assert log.positions, "a click is a scrub"
    assert log.positions[-1] == pytest.approx(64, abs=1)


# ------------------------------------------------- integration with review


@pytest.fixture
def review_page(qapp, workspace, session, dataset_root, isolated_user_state):
    from kinecapture.gui.pages.review import ReviewPage
    from kinecapture.gui.state import AppState
    from tests.conftest import authenticate_state

    schema = workspace.label_schema
    if not schema.exercises:
        schema.add_exercise("Squat")
        workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=80)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    state = AppState(AppConfig(dataset_root=dataset_root, backend="mock"))
    authenticate_state(state, workspace)
    page = ReviewPage(state)
    page.on_activated()
    page.resize(1366, 768)
    page.open_take(take)
    page._create_sample_range(10, 50)
    qapp.processEvents()
    return page


def test_the_playhead_comes_back_to_where_the_drag_started(review_page, qapp) -> None:
    page = review_page
    page._seek(35)
    assert page._position == 35

    page._edit_started()
    page._preview_position(12)
    qapp.processEvents()
    # The preview did not move the playhead, only what is on screen.
    assert page._position == 35

    page._preview_position(14)
    page._edit_finished()
    qapp.processEvents()

    assert page._position == 35, (
        "the playhead returns to where it was, not to the released frame"
    )
    assert not page._playing, "an edit must not start playback"


def test_the_preview_reaches_every_scene_mode(review_page, qapp) -> None:
    page = review_page
    page._seek(30)
    for mode in SceneMode:
        page._set_scene_mode(mode)
        page._edit_started()
        page._preview_position(8)
        qapp.processEvents()
        assert page._position == 30
        assert "ÖNİZLEME" in page._position_label.text()
        page._edit_finished()
        qapp.processEvents()
        assert page._position == 30
        assert "ÖNİZLEME" not in page._position_label.text()


def test_playback_is_paused_by_a_drag_and_not_resumed(review_page, qapp) -> None:
    """A running timer would fight the preview for the viewer."""
    page = review_page
    page._seek(20)
    page._play()
    assert page._playing

    page._edit_started()
    assert not page._playing, "the drag pauses playback"
    page._preview_position(40)
    qapp.processEvents()
    assert page._position == 20

    page._edit_finished()
    assert not page._playing, "and does not start it again"
    assert page._position == 20


def test_a_take_without_a_proxy_video_still_previews_the_skeleton(
    review_page, qapp
) -> None:
    page = review_page
    page._scene.set_video_available(False, "Proxy video yok.")
    page._set_scene_mode(SceneMode.SKELETON)
    page._seek(25)

    page._edit_started()
    page._preview_position(9)
    qapp.processEvents()

    assert not page._scene.grab().isNull()
    page._edit_finished()
    assert page._position == 25
