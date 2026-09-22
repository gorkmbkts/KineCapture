"""The labelling screen as a user meets it.

These drive the real widgets: draw on the timeline, trim an edge, press a
number key. What they check is that the picture, the timeline and the stored
label never disagree - the screen is the only place a coach can see what they
labelled, so a view that shows one thing while the document holds another is
the same failure as a wrong label.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.annotations import JointStatus, Readiness  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.viewmodels.navigation import destination  # noqa: E402
from kinecapture.studio.viewmodels.review import ReviewViewModel  # noqa: E402
from kinecapture.studio.views.pages.review import ReviewPage  # noqa: E402
from kinecapture.studio.views.timeline import Tool  # noqa: E402

FRAMES = 24


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def processed(workspace, session) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=7, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(
        paths.raw_dir / "subject_anchors.json",
        [{
            "camera_timestamp_ns": packet.camera_timestamp_ns,
            "source_resolution": list(packet.resolution),
            "point_xy": np.nanmean(points, axis=0).tolist(),
            "bbox_xyxy": np.r_[
                np.nanmin(points, axis=0), np.nanmax(points, axis=0)
            ].tolist(),
        }],
    )
    source.close()
    return process_take(paths.root, config)


@pytest.fixture
def page(qapp, workspace, processed: Path):
    tokens = load_tokens("dark")
    widget = ReviewPage(destination("review"), tokens)
    viewmodel = ReviewViewModel(SessionService(config=None, identity=None, workspace=workspace))
    widget.attach(viewmodel)
    viewmodel.open_version(str(processed))
    widget._after_open()
    widget.resize(1280, 800)
    yield widget
    widget.close()


def drag(timeline, start_x: int, end_x: int, y: int) -> None:
    """A left-button drag across the timeline, as a mouse would deliver it."""
    def event(kind, x):  # noqa: ANN001
        local = QPointF(x, y)
        return QMouseEvent(
            kind,
            local,
            local,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    timeline.mousePressEvent(event(QMouseEvent.Type.MouseButtonPress, start_x))
    timeline.mouseMoveEvent(event(QMouseEvent.Type.MouseMove, (start_x + end_x) // 2))
    timeline.mouseMoveEvent(event(QMouseEvent.Type.MouseMove, end_x))
    timeline.mouseReleaseEvent(event(QMouseEvent.Type.MouseButtonRelease, end_x))


def movement_lane_y(timeline) -> int:
    return int(timeline._lane_rects()["movements"].center().y())


def test_the_screen_opens_on_a_real_version(page) -> None:
    assert page.viewmodel.review is not None
    assert page.viewmodel.frames.value == FRAMES
    assert page.timeline._frames == FRAMES


def test_drawing_on_the_timeline_creates_exactly_one_movement(page) -> None:
    page._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    drag(page.timeline, 200, 500, movement_lane_y(page.timeline))

    rows = page.viewmodel.movements.value
    assert len(rows) == 1
    assert rows[0].start < rows[0].end
    # What the screen shows and what the document holds are the same
    # interval. The repeated movement list is gone - it sat above every
    # editor showing what the timeline already shows - so the timeline's own
    # boxes and the editor are what is asked.
    boxes = [i for i in page.timeline.intervals if i.lane == "movements"]
    assert len(boxes) == 1
    assert boxes[0].start == rows[0].start


def test_a_number_key_labels_the_selected_movement(page) -> None:
    viewmodel = page.viewmodel
    viewmodel.create_exercise("Squat")
    sample_id = viewmodel.add_movement(2, 10)
    viewmodel.select_movement(sample_id)

    page._quick_class(0)
    row = viewmodel.movement_row(sample_id)
    assert row.exercise == viewmodel.exercise_options.value[0][0]
    assert row.readiness is Readiness.READY


def test_trimming_previews_the_frame_without_moving_the_playhead(page) -> None:
    viewmodel = page.viewmodel
    viewmodel.add_movement(4, 16)
    viewmodel.seek(2)

    page._edit_started()
    page._preview_frame(15)
    assert page.viewer._badge  # the picture says it is showing something else
    assert viewmodel.position.value == 2  # ...and the playhead did not move

    page._edit_finished()
    assert not page.viewer._badge
    assert viewmodel.position.value == 2


def test_an_error_needs_a_movement_and_says_so(page) -> None:
    seen = []
    page.viewmodel.message.subscribe(seen.append)
    page.viewmodel.select_movement("")
    assert page.viewmodel.add_error(3, 6) is None
    assert seen


def test_selecting_an_error_highlights_the_joints_it_names(page) -> None:
    viewmodel = page.viewmodel
    viewmodel.create_exercise("Squat")
    viewmodel.create_error_class("Diz içe")
    sample_id = viewmodel.add_movement(2, 20)
    viewmodel.label_movement(sample_id, viewmodel.exercise_options.value[0][0])
    interval_id = viewmodel.add_error(5, 9, sample_id)

    role = next((r for r, i in page._roles.items() if i is not None), None)
    if role is None:
        pytest.skip("bu iskelet için eşlenmiş rol yok")
    assert viewmodel.label_error(
        interval_id,
        error_class=viewmodel.error_options.value[0][0],
        roles=(role,),
        joint_status=JointStatus.SELECTED,
    )
    viewmodel.select_error(interval_id)
    assert page._roles[role] in page.viewer._highlight


def test_the_timeline_and_the_list_stay_one_selection(page) -> None:
    viewmodel = page.viewmodel
    first = viewmodel.add_movement(1, 5)
    second = viewmodel.add_movement(8, 14)

    viewmodel.select_movement(second)
    assert page.timeline.selected == second
    assert page.editor_bar.mode == "movement"
    assert page.editor_bar.movement_start.value() == 8

    viewmodel.select_movement(first)
    assert page.timeline.selected == first


def test_undo_puts_the_screen_back(page) -> None:
    viewmodel = page.viewmodel
    viewmodel.add_movement(3, 9)
    assert len([i for i in page.timeline.intervals if i.lane == "movements"]) == 1
    viewmodel.undo()
    assert [i for i in page.timeline.intervals if i.lane == "movements"] == []
    assert not viewmodel.movements.value


def test_leaving_the_page_writes_the_labels(page) -> None:
    viewmodel = page.viewmodel
    viewmodel.add_movement(2, 7)
    page.page_deactivated()
    assert not viewmodel.store.is_dirty
    assert viewmodel.review.dataset.annotation_file
