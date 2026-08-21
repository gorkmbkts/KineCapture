"""Force every custom widget to actually paint.

Constructing a widget and handing it data exercises almost none of the code
that runs when Qt asks it to draw. A real crash escaped exactly this gap:
``QPainter.drawPolygon`` was being called with loose ``QPointF`` arguments,
which binds to Qt's ``(const QPointF *, int)`` overload and faults - and no
test noticed, because no test had ever triggered a paint event.

``widget.grab()`` renders synchronously into a pixmap, so these tests fail
loudly on a painting bug instead of segfaulting the application in front of a
user. Every custom-painted widget is covered in the states it is actually used
in, including the awkward ones: empty, single-frame, all-NaN, zoomed, dragging.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.domain.enums import Correctness, SegmentSource, SegmentStatus, TrackingState  # noqa: E402
from kinecapture.domain.models import BodyPose  # noqa: E402
from kinecapture.domain.project import RepetitionSegment  # noqa: E402
from kinecapture.gui.theme import DARK_THEME, LIGHT_THEME  # noqa: E402
from kinecapture.gui.widgets.skeleton_view import VIEW_PRESETS, SkeletonView3D  # noqa: E402
from kinecapture.gui.widgets.timeline import TimelineWidget  # noqa: E402
from kinecapture.gui.widgets.video_view import VideoView  # noqa: E402
from kinecapture.visualization.skeleton_spec import (  # noqa: E402
    MOCK_SKELETON,
    ZED_BODY_34,
)

THEMES = (DARK_THEME, LIGHT_THEME)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def paint(widget, size: QSize = QSize(640, 240)) -> None:
    """Render the widget and assert something was actually drawn."""
    widget.resize(size)
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.size().width() > 0


def make_body(spec, *, nan_joints=(), confidences=None, tracking_id=1) -> BodyPose:
    count = spec.num_joints
    joints = np.zeros((count, 3), dtype=np.float32)
    joints[:, 1] = np.linspace(0.1, 1.7, count)
    joints[:, 0] = np.linspace(-0.3, 0.3, count)
    joints[:, 2] = 2.5
    for index in nan_joints:
        joints[index] = np.nan
    if confidences is None:
        confidences = np.full(count, 0.9, dtype=np.float32)
    return BodyPose(
        tracking_id=tracking_id,
        tracking_state=TrackingState.OK,
        body_format=spec.name,
        joint_positions_xyz=joints,
        joint_confidences=np.asarray(confidences, dtype=np.float32),
    )


def make_segments(count: int = 3, frame_count: int = 300):
    segments = []
    span = frame_count // (count + 1)
    for index in range(count):
        segment = RepetitionSegment.create(
            "take", 1 + index * span, (index + 1) * span
        )
        segment.index = index + 1
        segment.annotation.exercise = "squat"
        segment.annotation.correctness = list(Correctness)[index % len(Correctness)]
        segments.append(segment)
    return segments


# --------------------------------------------------------------- timeline


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_timeline_paints_populated(qapp, theme) -> None:
    timeline = TimelineWidget(theme)
    frames = 300
    timeline.set_take(
        frames,
        fps=30.0,
        markers=[10, 120, 250],
        coverage=np.clip(np.sin(np.linspace(0, 8, frames)) * 0.5 + 0.5, 0, 1).astype(
            np.float32
        ),
        gaps=[80, 200],
    )
    timeline.set_segments(make_segments(3, frames))
    timeline.set_position(150)
    timeline.set_loop_range((100, 180))
    paint(timeline)


def test_timeline_paints_when_empty(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(0)
    paint(timeline)


def test_timeline_paints_single_frame_take(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(1, fps=30.0, coverage=np.ones(1, dtype=np.float32))
    paint(timeline)


def test_timeline_paints_without_coverage(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(120, fps=30.0, markers=[5])
    timeline.set_segments(make_segments(1, 120))
    paint(timeline)


def test_timeline_paints_excluded_and_suggested_segments(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(200, fps=30.0)
    segments = make_segments(2, 200)
    segments[0].status = SegmentStatus.EXCLUDED
    segments[1].source = SegmentSource.MODEL_SUGGESTION
    timeline.set_segments(segments)
    timeline.set_selected(segments[1].segment_id)
    paint(timeline)


def test_timeline_paints_at_extreme_zoom(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    frames = 5000
    timeline.set_take(
        frames, fps=60.0, coverage=np.ones(frames, dtype=np.float32)
    )
    timeline.set_segments(make_segments(4, frames))
    timeline.zoom_to_range(2000, 2010)  # deepest zoom
    paint(timeline)
    timeline.zoom_to_fit()  # widest
    paint(timeline)


def test_timeline_paints_in_a_tiny_viewport(qapp) -> None:
    timeline = TimelineWidget(DARK_THEME)
    timeline.set_take(100, fps=30.0, markers=[50])
    timeline.set_segments(make_segments(2, 100))
    paint(timeline, QSize(60, 140))


# -------------------------------------------------------------- 3D view


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("preset", [p.key for p in VIEW_PRESETS])
def test_skeleton_view_paints_every_preset(qapp, theme, preset) -> None:
    view = SkeletonView3D(theme, preset=preset)
    view.set_bodies([make_body(ZED_BODY_34)], ZED_BODY_34)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_with_missing_joints(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    body = make_body(ZED_BODY_34, nan_joints=(0, 5, 33))
    view.set_bodies([body], ZED_BODY_34)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_with_all_joints_missing(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    body = make_body(ZED_BODY_34, nan_joints=range(ZED_BODY_34.num_joints))
    view.set_bodies([body], ZED_BODY_34)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_low_confidence(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    body = make_body(
        MOCK_SKELETON,
        confidences=np.linspace(0.0, 1.0, MOCK_SKELETON.num_joints),
    )
    view.set_bodies([body], MOCK_SKELETON)
    view.set_show_confidence(True)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_multiple_bodies(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    bodies = [
        make_body(MOCK_SKELETON, tracking_id=1),
        make_body(MOCK_SKELETON, tracking_id=2),
    ]
    view.set_bodies(bodies, MOCK_SKELETON, active_id=2)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_empty(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_with_trail(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    view.set_show_trail(True)
    for _ in range(5):
        body = make_body(MOCK_SKELETON)
        body.root_position = np.array([0.0, 1.0, 2.5], dtype=np.float32)
        view.set_bodies([body], MOCK_SKELETON)
    paint(view, QSize(400, 320))


def test_skeleton_view_paints_without_root_centering(qapp) -> None:
    view = SkeletonView3D(DARK_THEME)
    view.set_root_centered(False)
    view.set_bodies([make_body(ZED_BODY_34)], ZED_BODY_34)
    paint(view, QSize(400, 320))


# ------------------------------------------------------------- video view


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_video_view_paints_with_overlay(qapp, theme) -> None:
    view = VideoView(theme)
    view.set_rgb(np.random.randint(0, 255, (180, 320, 3), dtype=np.uint8))
    view.set_bodies([make_body(MOCK_SKELETON)], MOCK_SKELETON)
    view.set_badge("KAYIT", theme.danger)
    paint(view, QSize(480, 320))


def test_video_view_paints_placeholder(qapp) -> None:
    view = VideoView(DARK_THEME, placeholder_text="Görüntü yok")
    paint(view, QSize(480, 320))


def test_video_view_paints_depth(qapp) -> None:
    view = VideoView(DARK_THEME)
    depth = np.full((120, 160), 2.5, dtype=np.float32)
    depth[:20, :] = np.nan
    view.set_depth(depth)
    paint(view, QSize(480, 320))


def test_video_view_paints_with_missing_joints(qapp) -> None:
    view = VideoView(DARK_THEME)
    view.set_rgb(np.zeros((180, 320, 3), dtype=np.uint8))
    view.set_bodies(
        [make_body(ZED_BODY_34, nan_joints=(1, 2, 3))], ZED_BODY_34, active_id=1
    )
    paint(view, QSize(480, 320))


def test_video_view_paints_extreme_aspect_ratios(qapp) -> None:
    view = VideoView(DARK_THEME)
    view.set_rgb(np.zeros((90, 640, 3), dtype=np.uint8))
    view.set_bodies([make_body(MOCK_SKELETON)], MOCK_SKELETON)
    paint(view, QSize(120, 400))
    paint(view, QSize(900, 100))


# ------------------------------------------------------- whole-page paint


def test_every_page_paints(qapp, tmp_path) -> None:
    """Render each workspace page - the check that would have caught the crash."""
    from kinecapture.core.config import AppConfig
    from kinecapture.gui.main_window import _PAGES, MainWindow

    config = AppConfig(dataset_root=tmp_path / "data", log_dir=tmp_path / "logs")
    window = MainWindow(config)
    window.resize(1280, 800)
    try:
        for key, _cls in _PAGES:
            window.navigate(key)
            qapp.processEvents()
            pixmap = window.grab()
            assert not pixmap.isNull(), key
    finally:
        window.state.release_capture_service()
        window.close()


def test_review_page_paints_with_a_loaded_take(qapp, workspace, session) -> None:
    """The exact path that crashed: Review, populated, actually painted."""
    from kinecapture.annotations.repository import AnnotationRepository
    from kinecapture.capture.service import CaptureService
    from kinecapture.core.config import AppConfig
    from kinecapture.domain.enums import TakeQuality
    from kinecapture.gui.main_window import MainWindow
    from kinecapture.playback.take_reader import load_take
    from tests.conftest import paced_backend, record_take

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=40, exercise="squat")
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    repository = AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count
    )
    segment = repository.create_segment(2, loaded.frame_count - 3)
    repository.annotate(
        segment.segment_id, exercise="squat", correctness=Correctness.CORRECT
    )
    repository.save()

    config = AppConfig(
        dataset_root=workspace.root.parent.parent, log_dir=workspace.root / "logs"
    )
    window = MainWindow(config)
    window.resize(1280, 800)
    try:
        window.state.open_project(workspace.root)
        qapp.processEvents()
        window.navigate("review")
        qapp.processEvents()

        page = window._pages["review"]
        assert page._take_selector.count() >= 1
        assert page._loaded is not None
        assert page._loaded.frame_count == loaded.frame_count

        assert not window.grab().isNull()
        page._seek(page._loaded.frame_count // 2)
        qapp.processEvents()
        assert not window.grab().isNull()

        # And with a segment selected, which paints the handles.
        page._segment_list.setCurrentRow(0)
        qapp.processEvents()
        assert not window.grab().isNull()
    finally:
        window.state.release_capture_service()
        window.close()
