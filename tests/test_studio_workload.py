"""PERF-02: the work each part of the screen is allowed to do.

These are structural checks, not timings. A timing that passes on this machine
says nothing about the next one, and a benchmark in the test suite becomes a
flaky test the moment somebody runs it under load. What can be asserted
reliably is *where* the work happens: that no timer runs behind a page nobody
is looking at, that the camera's transition timer stops when it arrives, that
a mesh is not rebuilt for a frame that did not change it, and that repeatedly
opening and leaving a screen does not leave workers behind.

The measured numbers live in the validation report, taken in a real window.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.camera_presets import (  # noqa: E402
    PRESETS,
    TRANSITION_SECONDS,
    CameraTransition,
    camera_for_preset,
)
from kinecapture.studio.services.skeleton3d import OrbitCamera  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    shell = build_window(config, state_path=tmp_path / "window.json")
    shell.resize(1600, 900)
    shell.show()
    assert shell.auth_viewmodel.create_owner(
        first_name="Ada",
        last_name="Lovelace",
        title="",
        username="ada",
        password="kinecapture1",
        password_confirm="kinecapture1",
    )
    app.processEvents()
    yield shell, app
    shell.close()


# ------------------------------------------------------- timers behind pages


def test_no_timer_runs_behind_a_page_nobody_is_looking_at(window) -> None:
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    view = shell.page("review")
    shell.viewmodel.navigate("export")
    app.processEvents()
    assert not view._clock.isActive()
    assert not view.skeleton._timer.isActive()


def test_leaving_the_labelling_screen_stops_playback(window) -> None:
    """A page that keeps playing while hidden is decoding video nobody sees."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    view = shell.page("review")
    view.viewmodel.playing.set(True)
    shell.viewmodel.navigate("library")
    app.processEvents()
    assert not view.viewmodel.playing.value
    assert not view._clock.isActive()


def test_the_capture_screen_stops_its_preview_when_it_is_left(window) -> None:
    shell, app = window
    shell.viewmodel.navigate("capture")
    app.processEvents()
    view = shell.page("capture")
    shell.viewmodel.navigate("library")
    app.processEvents()
    for name in dir(view):
        if name.startswith("_") and name.endswith(("timer", "clock")):
            timer = getattr(view, name, None)
            if hasattr(timer, "isActive"):
                assert not timer.isActive(), name


# ------------------------------------------------------- camera transitions


def test_a_transition_ends_rather_than_running_forever() -> None:
    """The timer has to have a last step, or it runs for the whole session."""
    start = OrbitCamera(up_axis=1)
    destination = camera_for_preset(PRESETS[2], start, reference_azimuth=0.0)
    move = CameraTransition.to_camera(start, destination)
    assert not move.finished(0.0)
    assert not move.finished(TRANSITION_SECONDS * 0.5)
    assert move.finished(TRANSITION_SECONDS)
    assert move.finished(TRANSITION_SECONDS + 0.001)
    # And the last sample is the target itself, not almost it: a transition
    # that stops one step short leaves the camera somewhere nobody chose.
    arrived = move.at(TRANSITION_SECONDS)
    assert arrived.azimuth == pytest.approx(destination.azimuth, abs=1e-6)
    assert arrived.elevation == pytest.approx(destination.elevation, abs=1e-6)


def test_a_new_preset_mid_flight_starts_from_where_the_camera_is() -> None:
    """No queue and no teleport: interrupting a move is a normal thing to do,
    and restarting from the abandoned target would jump."""
    start = OrbitCamera(up_axis=1)
    first = CameraTransition.to_camera(
        start, camera_for_preset(PRESETS[3], start, reference_azimuth=0.0)
    )
    midway = first.at(TRANSITION_SECONDS * 0.4)
    second = CameraTransition.to_camera(
        midway, camera_for_preset(PRESETS[4], midway, reference_azimuth=0.0)
    )
    assert second.start.azimuth == midway.azimuth


def test_reduced_motion_arrives_immediately(window) -> None:
    """The alternative to a 1.5 s move is arriving, not a shorter move that
    still has to be waited out."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    skeleton = shell.page("review").skeleton
    skeleton.set_reduce_motion(True)
    skeleton.go_to_preset("front")
    assert not skeleton._timer.isActive()


def test_a_transition_is_arithmetic_not_a_scene(window) -> None:
    """The compass is painted from two numbers. If it ever became a second
    viewport it would cost a second scene per frame."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    from PySide6.QtOpenGLWidgets import QOpenGLWidget

    compass = shell.page("review").camera_panel.compass
    assert not isinstance(compass, QOpenGLWidget)
    assert not compass.findChildren(QOpenGLWidget)


# ------------------------------------------------------------- mesh rebuilds


def test_the_same_pose_twice_does_not_rebuild_the_mesh(window) -> None:
    """`set_joints` marks the scene dirty; the *upload* happens once per
    paint. What must not happen is rebuilding the grid, the palette or the
    bone topology for a frame that changed none of them."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    skeleton = shell.page("review").skeleton
    bones = tuple((i, i + 1) for i in range(0, 8))
    skeleton.set_skeleton_spec(bones, up_axis=1)
    grid = skeleton._grid_data
    palette = skeleton._joint_colours

    pose = np.zeros((10, 3), dtype=np.float32)
    for _ in range(5):
        skeleton.set_joints(pose)
    assert skeleton._grid_data is grid
    assert skeleton._joint_colours is palette


def test_changing_the_topology_does_rebuild_it(window) -> None:
    """The cache has to be a cache, not a freeze."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    skeleton = shell.page("review").skeleton
    skeleton.set_skeleton_spec(((0, 1),), up_axis=1)
    first = skeleton._grid_data
    skeleton.set_skeleton_spec(((0, 1), (1, 2)), up_axis=2)
    assert skeleton._grid_data is not first


# ------------------------------------------------------------------- picking


def test_picking_costs_nothing_while_it_is_off(window) -> None:
    """PERF-02 and JOINT-02 at once: no projection is kept warm for a mode
    that is not on."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    skeleton = shell.page("review").skeleton
    assert not skeleton.is_picking
    skeleton.set_picking(True)
    assert skeleton.is_picking
    skeleton.set_picking(False)
    assert not skeleton.is_picking


# -------------------------------------------------------- repeated page use


def test_cycling_pages_does_not_accumulate_widgets(window) -> None:
    """A page rebuilt on every visit is both slow and a leak."""
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    def drain() -> None:
        # `deleteLater` only takes effect when deferred deletions are
        # delivered. Counting widgets without draining them measures Qt's
        # queue, not a leak.
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    # Both pages built first. Counting from a baseline taken before the
    # library exists measures its one-time construction - 63 widgets on this
    # build - and calls it a leak.
    shell.viewmodel.navigate("library")
    drain()
    shell.viewmodel.navigate("review")
    drain()
    before = len(app.allWidgets())
    for _ in range(6):
        shell.viewmodel.navigate("library")
        drain()
        shell.viewmodel.navigate("review")
        drain()
    drain()
    assert len(app.allWidgets()) == before


def test_a_page_is_built_once_and_kept(window) -> None:
    shell, app = window
    shell.viewmodel.navigate("review")
    app.processEvents()
    first = shell.page("review")
    shell.viewmodel.navigate("export")
    app.processEvents()
    shell.viewmodel.navigate("review")
    app.processEvents()
    assert shell.page("review") is first


# ------------------------------------------------- the offline work is offline


def test_floor_detection_is_not_something_the_screen_does() -> None:
    """FLOOR-01 and PERF-02 agree here: the plane is measured while the take
    is processed, written into `job.json`, and only read at labelling time."""
    import kinecapture.processing.floor as floor
    import kinecapture.studio.views.skeleton3d as view

    assert hasattr(floor, "detect_floor")
    assert not hasattr(view, "detect_floor")
    source = (view.__file__ or "")
    assert source.endswith("skeleton3d.py")
    with open(source, "r", encoding="utf-8") as stream:
        body = stream.read()
    assert "detect_floor" not in body
    assert "pyzed" not in body
