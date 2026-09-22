"""Opening a version the way the application really opens one.

The 15 September audit found the labelling screen showing a video title, a
first frame and an empty timeline at the same time: the screen prepared itself
from a ``QTimer.singleShot(0)`` fired next to the load request, while the load
itself ran on a worker thread and finished much later. Drawing on that empty
timeline produced a 0-0 movement.

Everything here therefore goes through a **real** ``TaskRunner`` that defers,
and never calls ``_after_open`` by hand. A test that calls it directly is a
test that cannot see this defect.
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
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.viewmodels.navigation import destination  # noqa: E402
from kinecapture.studio.viewmodels.review import ReviewViewModel  # noqa: E402
from kinecapture.studio.views.pages.review import ReviewPage  # noqa: E402
from kinecapture.studio.views.timeline import Tool  # noqa: E402

FRAMES = 24


class DeferredRunner:
    """A ``TaskRunner`` that answers only when the test says so.

    Stands in for ``QtTaskRunner`` without needing a thread: the point is that
    ``run`` returns before ``on_done`` is called, which is the single property
    the old code assumed away.
    """

    def __init__(self) -> None:
        self.pending: list[tuple] = []

    def run(self, work, on_done, on_error=None) -> None:  # noqa: ANN001
        self.pending.append((work, on_done, on_error))

    @property
    def outstanding(self) -> int:
        return len(self.pending)

    def settle(self, count: int = 0) -> int:
        """Complete ``count`` queued tasks (all of them when 0)."""
        done = 0
        while self.pending and (count == 0 or done < count):
            work, on_done, on_error = self.pending.pop(0)
            try:
                result = work()
            except BaseException as exc:  # noqa: BLE001 - mirrors the Qt runner
                if on_error is None:
                    raise
                on_error(exc)
            else:
                on_done(result)
            done += 1
        return done


def _build_version(workspace, session, *, seed: int = 7) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=seed, profile=profile)
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


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def version_a(workspace, session) -> Path:
    return _build_version(workspace, session, seed=7)


@pytest.fixture
def version_b(workspace, session) -> Path:
    return _build_version(workspace, session, seed=11)


class _Shell:
    """Only what ``page_activated`` reads off the window."""

    pending_review = None


@pytest.fixture
def page(qapp, workspace):
    runner = DeferredRunner()
    widget = ReviewPage(destination("review"), load_tokens("dark"))
    viewmodel = ReviewViewModel(
        SessionService(config=None, identity=None, workspace=workspace), runner=runner
    )
    widget.attach(viewmodel)
    widget.resize(1280, 800)
    widget.runner = runner
    yield widget
    widget.close()


def _open(page, directory: Path) -> None:
    """Ask for a version exactly as the library-to-labelling handover does."""
    page.viewmodel.open_version(str(directory))


def drag(timeline, start_x: int, end_x: int, y: int) -> None:
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


# ------------------------------------------------------- the defect itself
def test_timeline_stays_empty_until_the_load_finishes(page, version_a) -> None:
    _open(page, version_a)
    assert page.timeline._frames == 0
    assert page.viewmodel.busy.value is True


def test_the_timeline_has_the_real_frame_range_once_loaded(page, version_a) -> None:
    _open(page, version_a)
    page.runner.settle()
    assert page.viewmodel.frames.value == FRAMES
    assert page.timeline._frames == FRAMES
    start, span = page.timeline.view_range
    assert (start, span) == (0.0, float(FRAMES))


def test_a_drag_before_the_data_arrives_creates_nothing(page, version_a) -> None:
    _open(page, version_a)
    page.timeline.resize(900, page.timeline.height())
    page._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    lane_y = int(page.timeline._lane_rects()["movements"].center().y())
    drag(page.timeline, 200, 500, lane_y)
    page.runner.settle()
    assert page.viewmodel.movements.value == ()


def test_the_same_drag_after_loading_marks_the_dragged_range(page, version_a) -> None:
    _open(page, version_a)
    page.runner.settle()
    page.timeline.resize(900, page.timeline.height())
    page._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    lane_y = int(page.timeline._lane_rects()["movements"].center().y())
    left, right = 300, 600
    drag(page.timeline, left, right, lane_y)

    rows = page.viewmodel.movements.value
    assert len(rows) == 1
    row = rows[0]
    assert row.end > row.start, "a dragged movement must span more than one frame"
    assert row.start == page.timeline._frame_at(left)
    assert row.end == page.timeline._frame_at(right)


# --------------------------------------------------------------- stale loads
def test_a_slow_first_open_cannot_overwrite_the_second(page, version_a, version_b) -> None:
    """A is asked for, then B before A answers. The screen must end up on B.

    Since 19 September A also *stops* rather than running to completion: the
    open polls a cancellation flag between files, so asking for B does not
    leave a second version being hashed in the background. Whether A ends by
    being cancelled or by being discarded, the screen is on B either way, and
    both endings are checked here.
    """
    from kinecapture.processing.review import Cancelled

    _open(page, version_a)
    _open(page, version_b)
    assert page.runner.outstanding == 2
    # A answers last, which is the ordering that used to win.
    work_a, done_a, _err_a = page.runner.pending.pop(0)
    page.runner.settle()
    try:
        done_a(work_a())
    except Cancelled:
        # A noticed it had been superseded and stopped. Nothing to deliver.
        pass

    assert page.viewmodel.directory == str(version_b)
    assert page.viewmodel.review is not None
    assert Path(page.viewmodel.review.dataset.directory) == version_b


def test_leaving_and_returning_keeps_the_open_version(page, version_a) -> None:
    _open(page, version_a)
    page.runner.settle()
    page.page_deactivated()
    shell = _Shell()
    page.window = lambda: shell  # type: ignore[method-assign]
    page.page_activated()
    assert page.viewmodel.frames.value == FRAMES
    assert page.timeline._frames == FRAMES


def test_a_failed_open_offers_a_retry_and_disables_editing(page, tmp_path) -> None:
    _open(page, tmp_path / "there-is-no-run-here")
    page.runner.settle()
    assert page.viewmodel.review is None
    assert page.viewmodel.open_error.value
    # The way out lives on the preparation surface now, with the reason for
    # the failure beside it, rather than on a transport row the editor is not
    # showing.
    assert page.surface.currentWidget() is page.loading
    assert page.loading.retry_button.isVisibleTo(page.loading)
    assert page._editing_enabled is False
    assert page.timeline.tool is Tool.SCRUB
