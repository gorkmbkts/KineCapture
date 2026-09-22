"""Which way the athlete is facing, and why the camera cannot answer it.

The bug this file is written against is quiet and expensive: "Ön" was the
*virtual camera's* own azimuth at the moment a version opened - 35 degrees by
default, or whatever angle somebody had dragged the view to last time. Every
preset is an offset from that reference, so all eight of them were wrong
together and consistently, which is exactly the way a wrong answer survives:
press "Sağ" and the view does move ninety degrees, just not to the athlete's
right.

The facing is a cross product, so two things decide its sign and both are
checked here: which axis is up, and whether the basis is left- or
right-handed. Getting the handedness wrong puts the front camera behind the
athlete and swaps left with right - a mistake that would be invisible on a
symmetric test pose, which is why every pose here is asymmetric.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kinecapture.studio.services.camera_presets import PRESETS, camera_for_preset
from kinecapture.studio.services.skeleton3d import (
    FACING_HIPS,
    FACING_SHOULDERS,
    FACING_UNKNOWN,
    MIN_SPAN_M,
    OrbitCamera,
    facing_azimuth,
    is_left_handed,
)

#: Joint order used by the poses below.
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, HEAD = 0, 1, 2, 3, 4


def pose(facing: str, *, up_axis: int = 1) -> np.ndarray:
    """A body facing one of the four compass directions of its own space.

    Built from the anatomy, not from an angle: the shoulders are placed where
    they would be for somebody standing and facing that way, and the test then
    asks the code to recover the direction.
    """
    a, b = [i for i in (0, 1, 2) if i != up_axis]
    forward = np.zeros(3, dtype=np.float64)
    which, sign = facing[1], 1.0 if facing[0] == "+" else -1.0
    forward[a if which == "a" else b] = sign

    up = np.zeros(3, dtype=np.float64)
    up[up_axis] = 1.0
    # Where the left shoulder goes, in three dimensions rather than as a flat
    # quarter turn: left = up x forward. A first attempt rotated within the
    # (a, b) plane and passed for y-up while failing for z-up, because
    # (x, z, y) is left-handed while (x, y, z) is right-handed - the very
    # asymmetry the implementation handles by doing the cross product in 3-D.
    left = np.cross(up, forward)

    joints = np.full((5, 3), np.nan, dtype=np.float64)

    def place(index: int, side: float, height: float) -> None:
        joints[index, :] = left * side
        joints[index, up_axis] = height

    place(L_SHOULDER, 0.20, 1.40)
    place(R_SHOULDER, -0.20, 1.40)
    place(L_HIP, 0.12, 0.95)
    place(R_HIP, -0.12, 0.95)
    place(HEAD, 0.0, 1.70)
    return joints


def resolved(joints, **kwargs):  # noqa: ANN001, ANN201
    return facing_azimuth(
        joints,
        left_shoulder=L_SHOULDER,
        right_shoulder=R_SHOULDER,
        left_hip=L_HIP,
        right_hip=R_HIP,
        **kwargs,
    )


# ------------------------------------------------------- the geometry itself


@pytest.mark.parametrize(
    "facing,expected_degrees",
    [("+a", 0.0), ("+b", 90.0), ("-a", 180.0), ("-b", 270.0)],
)
def test_the_facing_comes_back_as_the_angle_it_was_built_from(
    facing, expected_degrees
) -> None:
    angle, source = resolved(pose(facing))
    assert source == FACING_SHOULDERS
    assert math.degrees(angle) == pytest.approx(expected_degrees, abs=0.5)


def test_the_answer_is_an_orbit_azimuth_the_camera_understands() -> None:
    """Not just a number: the camera placed at it has to end up in front.

    This is the assertion the old code could never have passed, because it
    handed the camera its own angle back and the check would have been
    trivially true whatever the athlete was doing.
    """
    joints = pose("+b")            # facing +z with y up
    angle, _source = resolved(joints)
    camera = OrbitCamera(azimuth=angle, elevation=0.0, distance=3.0, target=(0.0, 1.2, 0.0))
    eye = camera.eye
    # The athlete faces +z, so a camera in front of them stands at +z.
    assert eye[2] > 2.0
    assert abs(eye[0]) < 0.2


@pytest.mark.parametrize("up_axis", [1, 2])
def test_the_side_presets_stand_on_the_side_they_are_named_after(up_axis) -> None:
    """The reference alone is not enough: the offsets have to match it.

    This is the assertion that caught the swap. With the front derived from
    the body, "Sağ" was landing beside the athlete's *left* shoulder - a
    quarter turn in the wrong direction, invisible on a symmetric pose and
    invisible again while the reference itself was arbitrary.
    """
    joints = pose("+b", up_axis=up_axis)
    front, _source = resolved(joints, up_axis=up_axis)
    target = tuple(float(x) for x in np.nan_to_num(joints[HEAD]))

    for key, shoulder in (("right", R_SHOULDER), ("left", L_SHOULDER)):
        preset = next(p for p in PRESETS if p.key == key)
        camera = camera_for_preset(
            preset,
            OrbitCamera(up_axis=up_axis, distance=3.0, target=target),
            reference_azimuth=front,
        )
        # Standing beside that shoulder means the camera and the shoulder are
        # on the same side of the body's midline.
        offset = camera.eye - np.asarray(target, dtype=np.float64)
        side = joints[shoulder] - joints[HEAD]
        assert float(np.dot(offset, side)) > 0, f"{key} @ up={up_axis}"


def test_a_z_up_recording_is_handled_by_the_same_formula() -> None:
    joints = pose("+b", up_axis=2)
    angle, source = resolved(joints, up_axis=2)
    assert source == FACING_SHOULDERS
    assert math.degrees(angle) == pytest.approx(90.0, abs=0.5)


def test_a_left_handed_basis_flips_the_facing_by_half_a_turn() -> None:
    """The cross product's sign follows the basis. Unflagged, the front
    camera stands behind the athlete."""
    joints = pose("+b")
    right, _s = resolved(joints)
    left, _s2 = resolved(joints, left_handed=True)
    difference = abs((left - right) % (2 * math.pi) - math.pi)
    assert difference < 1e-6


def test_the_handedness_is_read_from_the_recordings_own_declaration() -> None:
    assert is_left_handed("left_handed_y_up")
    assert is_left_handed("LEFT_HANDED_Z_UP")
    assert not is_left_handed("right_handed_y_up")
    assert not is_left_handed("")


# ------------------------------------------------------------- what it refuses


def test_a_window_is_averaged_rather_than_read_frame_by_frame() -> None:
    """Per frame the answer follows the tracker's noise and the scene wobbles."""
    base = pose("+b")
    rng = np.random.default_rng(3)
    window = np.stack(
        [base + rng.normal(scale=0.01, size=base.shape) for _ in range(40)]
    )
    angle, source = resolved(window)
    assert source == FACING_SHOULDERS
    assert math.degrees(angle) == pytest.approx(90.0, abs=3.0)


def test_nan_frames_are_skipped_never_filled() -> None:
    base = pose("+b")
    window = np.stack([base, np.full_like(base, np.nan), base])
    angle, source = resolved(window)
    assert source == FACING_SHOULDERS
    assert math.degrees(angle) == pytest.approx(90.0, abs=0.5)


def test_shoulders_are_preferred_but_hips_are_a_real_fallback() -> None:
    joints = pose("+b")
    joints[L_SHOULDER, :] = np.nan
    joints[R_SHOULDER, :] = np.nan
    angle, source = resolved(joints)
    assert source == FACING_HIPS
    assert math.degrees(angle) == pytest.approx(90.0, abs=0.5)


def test_a_body_with_no_sides_says_it_does_not_know(
) -> None:
    """Neither guessed nor defaulted: the caller has to be able to say so."""
    joints = pose("+b")
    joints[[L_SHOULDER, R_SHOULDER, L_HIP, R_HIP], :] = np.nan
    angle, source = resolved(joints)
    assert angle is None
    assert source == FACING_UNKNOWN


def test_two_shoulders_on_top_of_each_other_are_refused() -> None:
    """Exactly edge-on, or a frame where the tracker collapsed both sides
    onto one point. A difference of nothing points nowhere, and normalising
    it would return whatever the floating-point noise happened to be."""
    joints = pose("+b")
    joints[L_SHOULDER, 0] = joints[R_SHOULDER, 0] = 0.0
    joints[L_SHOULDER, 2] = joints[R_SHOULDER, 2] = 0.0
    joints[L_HIP, :] = np.nan
    joints[R_HIP, :] = np.nan
    angle, source = resolved(joints)
    assert angle is None
    assert source == FACING_UNKNOWN


def test_a_shoulder_line_that_is_almost_vertical_is_refused() -> None:
    """Somebody lying down, or a bad frame. It says nothing about which way
    they face while standing, and the ground-plane part is what is used."""
    joints = pose("+b")
    joints[L_SHOULDER] = [0.0, 1.6, 0.0]
    joints[R_SHOULDER] = [0.0, 1.2, 0.0]
    joints[L_HIP, :] = np.nan
    joints[R_HIP, :] = np.nan
    angle, source = resolved(joints)
    assert angle is None
    assert source == FACING_UNKNOWN


def test_the_span_threshold_is_a_real_distance_not_a_ratio() -> None:
    """A tenth of a shoulder width is still a shoulder width at a distance."""
    assert 0.0 < MIN_SPAN_M < 0.2


def test_nothing_at_all_is_unknown_rather_than_zero() -> None:
    assert facing_azimuth(None) == (None, FACING_UNKNOWN)
    assert facing_azimuth(np.zeros((0, 3))) == (None, FACING_UNKNOWN)
