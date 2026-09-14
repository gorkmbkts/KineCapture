"""The 3D view's geometry, and the widget when a GL context can be had.

The arithmetic is tested without a screen: where the camera ends up, which
bones survive a dropped joint, which way is up. Those are the things that
would be wrong in a way a coach would notice - a skeleton lying on its side,
or a limb reaching down to the origin every time tracking blinked.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kinecapture.studio.services.skeleton3d import (
    DEFAULT_UP_AXIS,
    MAX_DISTANCE,
    MIN_DISTANCE,
    OrbitCamera,
    bone_segments,
    frame_subject,
    ground_grid,
    joint_points,
    up_axis_for,
)

BONES = ((0, 1), (1, 2), (2, 3))


def pose(missing: tuple[int, ...] = ()) -> np.ndarray:
    # No joint sits at the origin on purpose: that is what a dropped joint
    # would collapse to, so the tests below can tell the two apart.
    points = np.array(
        [[0.1, 0.2, -0.1], [0.1, 1.0, -0.1], [0.3, 1.5, 0.0], [0.6, 1.8, 0.1]],
        dtype=np.float32,
    )
    for index in missing:
        points[index] = np.nan
    return points


# ------------------------------------------------------------------ up axis
def test_the_up_axis_is_read_from_the_recording() -> None:
    assert up_axis_for("right_handed_y_up") == 1
    assert up_axis_for("right_handed_z_up") == 2
    # An unknown convention falls back, and the fallback is stated, not silent.
    assert up_axis_for("something_else") == DEFAULT_UP_AXIS
    assert up_axis_for("") == DEFAULT_UP_AXIS


def test_a_z_up_capture_is_not_laid_on_its_side() -> None:
    camera = OrbitCamera(up_axis=2, target=(0.0, 0.0, 1.0), elevation=0.0)
    assert camera.up.tolist() == [0.0, 0.0, 1.0]
    # At zero elevation the camera sits at the subject's height, whichever
    # axis "height" happens to be.
    assert camera.eye[2] == pytest.approx(1.0)


# ------------------------------------------------------------------- camera
def test_orbiting_never_flips_the_camera_over() -> None:
    camera = OrbitCamera()
    for _ in range(200):
        camera = camera.orbit(0.0, 0.5)
    assert camera.elevation < math.pi / 2
    assert camera.up[camera.up_axis] == 1.0


def test_zoom_is_bounded_at_both_ends() -> None:
    camera = OrbitCamera()
    for _ in range(100):
        camera = camera.zoom(0.5)
    assert camera.distance == pytest.approx(MIN_DISTANCE)
    for _ in range(100):
        camera = camera.zoom(2.0)
    assert camera.distance == pytest.approx(MAX_DISTANCE)


def test_the_camera_stays_the_set_distance_from_what_it_looks_at() -> None:
    camera = OrbitCamera(target=(1.0, 1.2, -0.5), distance=2.5)
    offset = camera.eye - np.asarray(camera.target)
    assert float(np.linalg.norm(offset)) == pytest.approx(2.5, abs=1e-5)


def test_the_target_projects_to_the_middle_of_the_screen() -> None:
    """If this drifts, the subject creeps out of frame as the camera moves."""
    camera = OrbitCamera(target=(0.4, 1.1, -0.2), distance=3.0)
    point = np.array([*camera.target, 1.0], dtype=np.float64)
    clip = camera.matrix(16 / 9) @ point
    assert clip[3] > 0  # in front of the camera, not behind it
    assert clip[0] / clip[3] == pytest.approx(0.0, abs=1e-5)
    assert clip[1] / clip[3] == pytest.approx(0.0, abs=1e-5)


def test_panning_moves_the_view_the_same_way_at_any_zoom() -> None:
    near = OrbitCamera(distance=1.0).pan(100.0, 0.0)
    far = OrbitCamera(distance=10.0).pan(100.0, 0.0)
    near_shift = np.linalg.norm(np.asarray(near.target) - np.array([0.0, 1.0, 0.0]))
    far_shift = np.linalg.norm(np.asarray(far.target) - np.array([0.0, 1.0, 0.0]))
    assert far_shift > near_shift  # scaled by distance, so the picture keeps up


def test_the_camera_survives_a_round_trip_through_storage() -> None:
    camera = OrbitCamera(azimuth=1.1, elevation=-0.3, distance=4.2,
                         target=(0.5, 0.9, -1.0), up_axis=2)
    restored = OrbitCamera.from_dict(camera.to_dict())
    assert restored.azimuth == pytest.approx(camera.azimuth)
    assert restored.elevation == pytest.approx(camera.elevation)
    assert restored.distance == pytest.approx(camera.distance)
    assert restored.target == camera.target
    assert restored.up_axis == 2


# ------------------------------------------------------------------ framing
def test_framing_puts_the_whole_person_in_view() -> None:
    framing = frame_subject(pose())
    assert framing is not None
    target, distance = framing
    assert target[1] == pytest.approx(1.0, abs=1e-6)  # mid-height of the pose
    assert MIN_DISTANCE <= distance <= MAX_DISTANCE


def test_framing_ignores_joints_the_tracker_never_produced() -> None:
    """A NaN dragged into the box would pull the camera towards the origin."""
    assert frame_subject(pose(missing=(3,))) != frame_subject(pose())
    with_nan = frame_subject(pose(missing=(3,)))
    without = frame_subject(pose()[:3])
    assert with_nan is not None and without is not None
    assert with_nan[0] == pytest.approx(without[0])


def test_framing_a_window_is_allowed() -> None:
    window = np.stack([pose(), pose() + 0.5])
    framing = frame_subject(window)
    assert framing is not None and framing[0][1] > frame_subject(pose())[0][1]


def test_nothing_to_frame_is_reported_not_guessed() -> None:
    assert frame_subject(None) is None
    assert frame_subject(np.full((4, 3), np.nan, dtype=np.float32)) is None


# -------------------------------------------------------------------- bones
def test_a_bone_with_a_missing_end_is_dropped_not_drawn_to_the_origin() -> None:
    full = bone_segments(pose(), BONES)
    assert len(full) == 3

    partial = bone_segments(pose(missing=(2,)), BONES)
    assert len(partial) == 1  # only 0-1 survives; 1-2 and 2-3 touch the gap
    assert np.isfinite(partial).all()
    assert not (partial == 0.0).all(axis=2).any()


def test_an_out_of_range_bone_is_ignored() -> None:
    assert len(bone_segments(pose(), ((0, 99), (0, 1)))) == 1


def test_no_joints_means_no_geometry_not_a_crash() -> None:
    assert bone_segments(None, BONES).shape == (0, 2, 3)
    assert joint_points(None)[0].shape == (0, 3)


def test_joint_points_report_which_joints_they_are() -> None:
    points, indices = joint_points(pose(missing=(1,)))
    assert len(points) == 3
    assert indices.tolist() == [0, 2, 3]
    assert np.isfinite(points).all()


# --------------------------------------------------------------------- grid
def test_the_floor_lies_flat_on_the_up_axis() -> None:
    for axis in (1, 2):
        grid = ground_grid(axis)
        assert len(grid) > 0
        assert np.allclose(grid[:, :, axis], 0.0)
        others = [i for i in (0, 1, 2) if i != axis]
        assert grid[:, :, others].min() < 0 < grid[:, :, others].max()


# ------------------------------------------------------------------- widget
def test_the_widget_draws_a_real_pose_or_says_why_it_cannot() -> None:
    """A GL context may not exist here; that is a message, never a crash."""
    pytest.importorskip("PySide6.QtOpenGLWidgets")
    import os

    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        pytest.skip("offscreen platformunda GL bağlamı güvenilir değil")

    from PySide6.QtWidgets import QApplication

    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.views.skeleton3d import Skeleton3DView

    app = QApplication.instance() or QApplication([])
    view = Skeleton3DView(load_tokens("dark"))
    try:
        view.set_skeleton_spec(BONES, 1)
        view.set_joints(pose(missing=(2,)))
        view.resize(320, 240)
        view.show()
        app.processEvents()
        if not view.is_available:
            assert view.unavailable_reason
            return
        view._rebuild()
        assert view._bone_mesh.count == 2   # one surviving bone, two ends
        assert view._joint_mesh.count == 3  # the joint that is NaN is not sent
    finally:
        view.close()
