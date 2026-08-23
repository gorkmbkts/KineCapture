"""Feature mathematics, checked against closed-form answers.

These are the tests that decide whether a number in a released dataset means
what its name says. They avoid the camera entirely and build sequences whose
correct answer is known analytically, so a failure points at the maths rather
than at a tracker.

The recurring theme is that *not* computing something is a result too: a gap in
the timestamps, a joint the skeleton does not have and a degenerate segment all
have to produce NaN and a ``False`` mask, never a plausible number.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kinecapture.features.compute import (
    BILATERAL_PAIR_IDS,
    FeatureContext,
    compute_features,
)
from kinecapture.features.definitions import (
    ANGLE_IDS,
    DISTANCE_IDS,
    RATIO_IDS,
)
from kinecapture.features.geometry import bone_table, three_point_angle
from kinecapture.features.registry import (
    FEATURES,
    PRESETS,
    applicability,
    array_keys_for,
    get_feature,
    get_preset,
    match_preset,
    order_features,
)
from kinecapture.features.roles import resolve_roles
from kinecapture.features.summary import SUMMARY_LENGTH, summary_names
from kinecapture.features.temporal import (
    central_difference,
    max_gap_seconds,
    second_difference,
)
from kinecapture.visualization.skeleton_spec import (
    MOCK_SKELETON,
    REHAB24_6_MOCAP,
    ZED_BODY_18,
    ZED_BODY_34,
)

# ---------------------------------------------------------------- helpers


def _rest_pose(spec=MOCK_SKELETON) -> np.ndarray:
    """A neutral, exactly left/right symmetric standing pose."""
    positions = {
        "pelvis": (0.00, 0.95, 2.50),
        "chest_spine": (0.00, 1.25, 2.50),
        "neck": (0.00, 1.48, 2.50),
        "head": (0.00, 1.63, 2.50),
        "left_shoulder": (0.19, 1.43, 2.50),
        "left_elbow": (0.24, 1.18, 2.50),
        "left_wrist": (0.26, 0.94, 2.50),
        "right_shoulder": (-0.19, 1.43, 2.50),
        "right_elbow": (-0.24, 1.18, 2.50),
        "right_wrist": (-0.26, 0.94, 2.50),
        "left_hip": (0.11, 0.93, 2.50),
        "left_knee": (0.11, 0.52, 2.50),
        "left_ankle": (0.11, 0.08, 2.50),
        "right_hip": (-0.11, 0.93, 2.50),
        "right_knee": (-0.11, 0.52, 2.50),
        "right_ankle": (-0.11, 0.08, 2.50),
    }
    return np.asarray(
        [positions[name] for name in spec.joint_names], dtype=np.float32
    )


def _sequence(frames: int, spec=MOCK_SKELETON) -> np.ndarray:
    return np.repeat(_rest_pose(spec)[None, ...], frames, axis=0)


def _timestamps(frames: int, fps: float = 30.0, start_ns: int = 0) -> np.ndarray:
    step = int(round(1e9 / fps))
    return np.asarray(
        [start_ns + index * step for index in range(frames)], dtype=np.int64
    )


def _context(joints, timestamps=None, *, spec=MOCK_SKELETON, fps=30.0, **kwargs):
    joints = np.asarray(joints, dtype=np.float32)
    frames = joints.shape[0]
    if timestamps is None:
        timestamps = _timestamps(frames, fps)
    return FeatureContext(
        spec=spec,
        joints=joints,
        timestamps_ns=np.asarray(timestamps, dtype=np.int64),
        frame_indices=np.arange(frames, dtype=np.int64),
        target_fps=fps,
        **kwargs,
    )


# ------------------------------------------------------------- timestamps


def test_physical_velocity_is_exact_under_irregular_timestamps() -> None:
    """Constant motion, jittery clock: the answer must still be the true speed."""
    stamps = np.asarray([0, 31, 70, 101, 139, 168], dtype=np.int64) * 1_000_000
    seconds = stamps / 1e9
    velocity = np.asarray([0.5, -0.25, 2.0])
    joints = (seconds[:, None, None] * velocity[None, None, :]).astype(np.float32)

    values, mask = central_difference(
        joints, stamps, max_gap_s=max_gap_seconds(30.0)
    )
    assert mask.all()
    np.testing.assert_allclose(
        values[:, 0, :], np.tile(velocity, (values.shape[0], 1)), rtol=1e-5
    )


def test_same_displacement_at_two_frame_rates_gives_different_velocity() -> None:
    """The distinction the whole module exists for.

    The per-frame step is identical in both sequences. The displacement feature
    must therefore agree, and the physical velocity must not - it is twice as
    fast at twice the frame rate.
    """
    step = np.asarray([0.01, 0.0, 0.0], dtype=np.float32)
    frames = 10
    joints = np.cumsum(
        np.repeat(step[None, None, :], frames, axis=0), axis=0
    ).astype(np.float32)

    slow = _context(joints, _timestamps(frames, 30.0))
    fast = _context(joints, _timestamps(frames, 60.0), fps=60.0)

    slow_features = compute_features(slow, ["joint_displacement", "joint_velocity"])
    fast_features = compute_features(fast, ["joint_displacement", "joint_velocity"])

    np.testing.assert_allclose(
        slow_features.arrays["joint_displacement_xyz"][1:],
        fast_features.arrays["joint_displacement_xyz"][1:],
        rtol=1e-6,
    )
    slow_speed = float(slow_features.arrays["joint_speed"][5, 0])
    fast_speed = float(fast_features.arrays["joint_speed"][5, 0])
    assert slow_speed == pytest.approx(0.3, rel=1e-4)
    assert fast_speed == pytest.approx(0.6, rel=1e-4)


def test_first_displacement_frame_is_nan_not_zero() -> None:
    """A zero would tell a model the body was stationary at every sample start."""
    joints = _sequence(5)
    result = compute_features(_context(joints), ["joint_displacement"])
    assert np.isnan(result.arrays["joint_displacement_xyz"][0]).all()
    assert not result.arrays["joint_displacement_valid_mask"][0].any()


def test_derivatives_do_not_bridge_a_tracking_gap() -> None:
    stamps = np.asarray([0, 33, 66, 500, 533, 566], dtype=np.int64) * 1_000_000
    joints = (
        (stamps / 1e9)[:, None, None] * np.asarray([1.0, 0.0, 0.0])[None, None, :]
    ).astype(np.float32)
    values, mask = central_difference(
        joints, stamps, max_gap_s=max_gap_seconds(30.0)
    )
    # Positions 2 and 3 straddle the hole; neither may carry a derivative.
    assert not mask[2].any() and not mask[3].any()
    assert np.isnan(values[2]).all() and np.isnan(values[3]).all()
    assert mask[0].all() and mask[5].all()


def test_constant_acceleration_is_recovered_exactly() -> None:
    stamps = np.asarray([0, 29, 66, 99, 141], dtype=np.int64) * 1_000_000
    seconds = stamps / 1e9
    acceleration = np.asarray([0.0, -9.81, 0.0])
    joints = (
        0.5 * acceleration[None, None, :] * (seconds[:, None, None] ** 2)
    ).astype(np.float64)

    values, mask = second_difference(
        joints, stamps, max_gap_s=max_gap_seconds(30.0)
    )
    interior = values[1:-1, 0, :]
    np.testing.assert_allclose(
        interior, np.tile(acceleration, (interior.shape[0], 1)), rtol=1e-4
    )
    # The ends have no three-point stencil and are not extrapolated.
    assert not mask[0].any() and not mask[-1].any()


def test_non_positive_timestamp_step_is_rejected() -> None:
    stamps = np.asarray([0, 33, 33, 66], dtype=np.int64) * 1_000_000
    joints = _sequence(4)
    _values, mask = central_difference(
        joints, stamps, max_gap_s=max_gap_seconds(30.0)
    )
    assert not mask[1].any() and not mask[2].any()


# ------------------------------------------------------------------ angles


def test_known_right_angle_and_straight_angle() -> None:
    vertex = np.asarray([[0.0, 0.0, 0.0]])
    right = three_point_angle(
        np.asarray([[1.0, 0.0, 0.0]]), vertex, np.asarray([[0.0, 1.0, 0.0]])
    )
    straight = three_point_angle(
        np.asarray([[1.0, 0.0, 0.0]]), vertex, np.asarray([[-1.0, 0.0, 0.0]])
    )
    assert float(right[0]) == pytest.approx(math.pi / 2)
    assert float(straight[0]) == pytest.approx(math.pi)


def test_degenerate_segment_gives_nan_angle() -> None:
    vertex = np.asarray([[0.0, 0.0, 0.0]])
    angle = three_point_angle(vertex, vertex, np.asarray([[0.0, 1.0, 0.0]]))
    assert np.isnan(angle[0])


def test_angle_columns_follow_the_definition_order() -> None:
    joints = _sequence(6)
    result = compute_features(_context(joints), ["joint_angles"])
    values = result.arrays["joint_angles_rad"]
    assert values.shape == (6, len(ANGLE_IDS))
    # A straight, symmetric standing pose: both knees are near full extension.
    left = float(values[0, ANGLE_IDS.index("left_knee_angle")])
    right = float(values[0, ANGLE_IDS.index("right_knee_angle")])
    assert left == pytest.approx(math.pi, abs=0.05)
    assert left == pytest.approx(right, abs=1e-5)


def test_angle_degrees_is_a_separate_array_with_a_declared_unit() -> None:
    joints = _sequence(4)
    result = compute_features(_context(joints), ["joint_angles", "joint_angles_degrees"])
    radians = result.arrays["joint_angles_rad"]
    degrees = result.arrays["joint_angles_deg"]
    np.testing.assert_allclose(np.degrees(radians), degrees, equal_nan=True, rtol=1e-5)


def test_angle_missing_from_a_skeleton_stays_nan_without_disturbing_others() -> None:
    """``mock_16`` has no foot joint, so only the ankle columns go missing."""
    joints = _sequence(5)
    result = compute_features(_context(joints), ["joint_angles"])
    values = result.arrays["joint_angles_rad"]
    for angle_id in ("left_ankle_angle", "right_ankle_angle"):
        assert np.isnan(values[:, ANGLE_IDS.index(angle_id)]).all()
    for angle_id in ("left_knee_angle", "trunk_inclination"):
        assert np.isfinite(values[:, ANGLE_IDS.index(angle_id)]).all()


def test_angular_velocity_of_a_static_pose_is_zero_not_nan() -> None:
    joints = _sequence(8)
    result = compute_features(
        _context(joints), ["joint_angles", "joint_angular_velocity"]
    )
    rates = result.arrays["joint_angular_velocity_rad_s"]
    knee = rates[:, ANGLE_IDS.index("left_knee_angle")]
    assert np.isfinite(knee).all()
    np.testing.assert_allclose(knee, 0.0, atol=1e-5)


# ------------------------------------------------------------ quaternions


def test_quaternion_sign_flips_do_not_manufacture_angular_speed() -> None:
    """``q`` and ``-q`` are the same rotation; the double cover must not leak.

    The sequence below is a steady rotation whose stored quaternions flip sign
    on alternate frames, which is exactly what a tracker does. Differencing
    Euler angles or the raw components would produce a huge spurious spike.
    """
    frames = 9
    joints = _sequence(frames)
    stamps = _timestamps(frames)
    angles = np.linspace(0.0, 0.4, frames)
    quaternions = np.zeros((frames, MOCK_SKELETON.num_joints, 4), dtype=np.float32)
    for index, angle in enumerate(angles):
        sign = -1.0 if index % 2 else 1.0
        quaternions[index, :, 1] = sign * math.sin(angle / 2.0)
        quaternions[index, :, 3] = sign * math.cos(angle / 2.0)

    result = compute_features(
        _context(joints, stamps, raw={"joint_orientations": quaternions}),
        ["quaternion_angular_speed"],
    )
    speeds = result.arrays["quaternion_angular_speed_rad_s"]
    finite = speeds[np.isfinite(speeds)]
    assert finite.size
    # 0.4 rad over 8 frames at 30 Hz is a steady 1.5 rad/s.
    np.testing.assert_allclose(finite, 1.5, rtol=1e-3)


def test_quaternion_angular_speed_is_unavailable_without_orientations() -> None:
    result = compute_features(_context(_sequence(5)), ["quaternion_angular_speed"])
    assert result.availability["quaternion_angular_speed"].value == "absent"
    assert "quaternion" in result.reasons["quaternion_angular_speed"].lower()
    assert np.isnan(result.arrays["quaternion_angular_speed_rad_s"]).all()


def test_non_unit_quaternion_gives_nan_rather_than_a_number() -> None:
    frames = 4
    quaternions = np.zeros((frames, MOCK_SKELETON.num_joints, 4), dtype=np.float32)
    result = compute_features(
        _context(_sequence(frames), raw={"joint_orientations": quaternions}),
        ["quaternion_angular_speed"],
    )
    assert np.isnan(result.arrays["quaternion_angular_speed_rad_s"]).all()


# ----------------------------------------------------------------- bones


def test_bone_arrays_follow_the_skeleton_edge_order() -> None:
    joints = _sequence(3)
    result = compute_features(_context(joints), ["bone_geometry"])
    vectors = result.arrays["bone_vectors_xyz"]
    lengths = result.arrays["bone_lengths"]
    assert vectors.shape == (3, len(MOCK_SKELETON.edges), 3)

    table = bone_table(MOCK_SKELETON)
    for position, (parent, child) in enumerate(MOCK_SKELETON.edges):
        expected = joints[0, child] - joints[0, parent]
        np.testing.assert_allclose(vectors[0, position], expected, atol=1e-6)
        assert table[position]["parent"] == MOCK_SKELETON.joint_names[parent]
        assert table[position]["child"] == MOCK_SKELETON.joint_names[child]
    np.testing.assert_allclose(
        lengths[0], np.linalg.norm(vectors[0], axis=-1), rtol=1e-6
    )


def test_a_missing_joint_invalidates_only_its_own_bones() -> None:
    joints = _sequence(3).copy()
    wrist = MOCK_SKELETON.index_of("left_wrist")
    joints[:, wrist, :] = np.nan

    result = compute_features(
        _context(joints), ["bone_geometry", "joint_angles", "validity_masks"]
    )
    valid = result.arrays["bone_valid_mask"]
    affected = [
        position
        for position, (parent, child) in enumerate(MOCK_SKELETON.edges)
        if wrist in (parent, child)
    ]
    assert affected
    for position in range(len(MOCK_SKELETON.edges)):
        expected = position not in affected
        assert bool(valid[0, position]) is expected

    angles = result.arrays["joint_angles_rad"]
    assert np.isnan(angles[:, ANGLE_IDS.index("left_elbow_angle")]).all()
    assert np.isfinite(angles[:, ANGLE_IDS.index("right_elbow_angle")]).all()
    assert np.isfinite(angles[:, ANGLE_IDS.index("left_knee_angle")]).all()
    assert not result.arrays["joint_valid_mask"][0, wrist]


# -------------------------------------------------------------- symmetry


def test_perfectly_symmetric_pose_has_near_zero_symmetry_features() -> None:
    joints = _sequence(6)
    result = compute_features(
        _context(joints),
        ["body_aligned_positions", "joint_angles", "bilateral_angles", "bilateral_mirror"],
    )
    mirror = result.arrays["bilateral_mirror_distance"]
    finite = mirror[np.isfinite(mirror)]
    assert finite.size
    np.testing.assert_allclose(finite, 0.0, atol=1e-5)

    difference = result.arrays["bilateral_angle_difference_rad"]
    finite_difference = difference[np.isfinite(difference)]
    np.testing.assert_allclose(finite_difference, 0.0, atol=1e-5)


def test_deliberate_asymmetry_shows_up() -> None:
    joints = _sequence(6).copy()
    wrist = MOCK_SKELETON.index_of("left_wrist")
    joints[:, wrist, 0] += 0.10

    result = compute_features(
        _context(joints),
        ["body_aligned_positions", "joint_angles", "bilateral_angles", "bilateral_mirror"],
    )
    column = BILATERAL_PAIR_IDS.index("wrist")
    distance = result.arrays["bilateral_mirror_distance"][0, column]
    assert float(distance) == pytest.approx(0.10, abs=1e-4)

    elbow = result.arrays["bilateral_angle_difference_rad"][0, 0]
    assert abs(float(elbow)) > 1e-3


def test_symmetry_is_measured_in_body_space_not_camera_space() -> None:
    """Rotating the person about the vertical axis must not create asymmetry.

    Computed in camera coordinates, ``left - right`` would change the moment
    the subject turned away from the lens. That confound is precisely what a
    model must not learn as a movement error.
    """
    joints = _sequence(4).copy()
    angle = math.radians(35.0)
    rotation = np.asarray(
        [
            [math.cos(angle), 0.0, math.sin(angle)],
            [0.0, 1.0, 0.0],
            [-math.sin(angle), 0.0, math.cos(angle)],
        ]
    )
    centre = joints[:, MOCK_SKELETON.root_index : MOCK_SKELETON.root_index + 1, :]
    rotated = ((joints - centre) @ rotation.T + centre).astype(np.float32)

    result = compute_features(
        _context(rotated), ["body_aligned_positions", "bilateral_mirror"]
    )
    mirror = result.arrays["bilateral_mirror_distance"]
    finite = mirror[np.isfinite(mirror)]
    assert finite.size
    np.testing.assert_allclose(finite, 0.0, atol=1e-4)


def test_bilateral_pair_missing_from_the_skeleton_stays_nan() -> None:
    joints = _sequence(4)
    result = compute_features(
        _context(joints), ["body_aligned_positions", "bilateral_mirror"]
    )
    mirror = result.arrays["bilateral_mirror_distance"]
    # mock_16 has no heel; that column must be empty rather than borrowed.
    assert np.isnan(mirror[:, BILATERAL_PAIR_IDS.index("heel")]).all()
    assert np.isfinite(mirror[:, BILATERAL_PAIR_IDS.index("knee")]).all()


# ------------------------------------------------- distances and ratios


def test_distances_and_ratios_are_computed_from_the_declared_roles() -> None:
    joints = _sequence(3)
    result = compute_features(_context(joints), ["segment_distances", "segment_ratios"])
    distances = result.arrays["segment_distances"]
    assert distances.shape == (3, len(DISTANCE_IDS))
    hip_width = float(distances[0, DISTANCE_IDS.index("hip_width")])
    assert hip_width == pytest.approx(0.22, abs=1e-4)

    ratios = result.arrays["segment_ratios"]
    assert ratios.shape == (3, len(RATIO_IDS))
    knee_ratio = float(ratios[0, RATIO_IDS.index("knee_over_hip_width")])
    knee_separation = float(distances[0, DISTANCE_IDS.index("knee_separation")])
    assert knee_ratio == pytest.approx(knee_separation / hip_width, rel=1e-5)


def test_ratio_with_a_vanishing_denominator_is_nan() -> None:
    joints = _sequence(3).copy()
    left_hip = MOCK_SKELETON.index_of("left_hip")
    right_hip = MOCK_SKELETON.index_of("right_hip")
    joints[:, left_hip, :] = joints[:, right_hip, :]

    result = compute_features(_context(joints), ["segment_distances", "segment_ratios"])
    ratios = result.arrays["segment_ratios"]
    assert np.isnan(ratios[:, RATIO_IDS.index("knee_over_hip_width")]).all()


def test_joint_centroid_is_not_called_a_centre_of_mass() -> None:
    definition = get_feature("joint_centroid_proxy")
    # The array must not be *named* a centre of mass; the description is
    # allowed - and expected - to say explicitly that it is not one.
    assert all("center_of_mass" not in key and "com" != key for key in definition.array_keys)
    assert "DEĞİLDİR" in definition.description
    assert definition.array_keys == (
        "joint_centroid_proxy_xyz",
        "joint_centroid_valid_mask",
    )
    result = compute_features(_context(_sequence(3)), ["joint_centroid_proxy"])
    centroid = result.arrays["joint_centroid_proxy_xyz"]
    np.testing.assert_allclose(
        centroid[0], np.nanmean(_rest_pose(), axis=0), atol=1e-5
    )


# ---------------------------------------------------------- coordinates


def test_root_centering_never_touches_the_raw_array() -> None:
    joints = _sequence(4)
    original = joints.copy()
    result = compute_features(
        _context(joints), ["canonical_pose", "root_centered_positions"]
    )
    np.testing.assert_array_equal(joints, original)
    np.testing.assert_array_equal(result.arrays["joints_xyz"], original)
    centred = result.arrays["root_centered_xyz"]
    np.testing.assert_allclose(centred[:, MOCK_SKELETON.root_index, :], 0.0, atol=0)


def test_scale_normalisation_needs_a_body_scale() -> None:
    joints = _sequence(4)
    result = compute_features(
        _context(joints), ["body_scale", "scale_normalized_positions"]
    )
    scale = float(result.arrays["body_scale"][0])
    assert scale > 0.5
    normalised = result.arrays["scale_normalized_xyz"]
    centred = joints - joints[:, MOCK_SKELETON.root_index : MOCK_SKELETON.root_index + 1, :]
    np.testing.assert_allclose(normalised, centred / scale, rtol=1e-5)


def test_body_scale_is_nan_when_the_legs_are_missing() -> None:
    joints = _sequence(4).copy()
    for name in ("left_knee", "right_knee", "left_ankle", "right_ankle"):
        joints[:, MOCK_SKELETON.index_of(name), :] = np.nan
    result = compute_features(
        _context(joints), ["body_scale", "scale_normalized_positions"]
    )
    assert np.isnan(result.arrays["body_scale"][0])
    assert result.availability["body_scale"].value == "absent"
    assert np.isnan(result.arrays["scale_normalized_xyz"]).all()


def test_body_frame_is_invalid_without_hips() -> None:
    joints = _sequence(4).copy()
    joints[:, MOCK_SKELETON.index_of("left_hip"), :] = np.nan
    result = compute_features(_context(joints), ["body_aligned_positions"])
    assert not result.arrays["body_frame_valid_mask"].any()
    assert np.isnan(result.arrays["body_aligned_xyz"]).all()


# ------------------------------------------------------------ summary


def test_summary_vector_has_a_fixed_length_and_named_elements() -> None:
    names = summary_names()
    assert len(names) == SUMMARY_LENGTH
    assert len(set(names)) == SUMMARY_LENGTH

    short = compute_features(
        _context(_sequence(5)), order_features(["summary_vector"])
    ).arrays["summary_features"]
    long = compute_features(
        _context(_sequence(40)), order_features(["summary_vector"])
    ).arrays["summary_features"]
    assert short.shape == long.shape == (SUMMARY_LENGTH,)
    assert short.dtype == np.float32


def test_summary_length_is_independent_of_the_skeleton() -> None:
    """Two formats, different joint counts, identical vector width."""
    mock = compute_features(
        _context(_sequence(6)), order_features(["summary_vector"])
    ).arrays["summary_features"]
    zed = compute_features(
        _context(
            np.zeros((6, ZED_BODY_34.num_joints, 3), dtype=np.float32),
            spec=ZED_BODY_34,
        ),
        order_features(["summary_vector"]),
    ).arrays["summary_features"]
    assert mock.shape == zed.shape


def test_summary_elements_that_cannot_be_computed_are_nan() -> None:
    result = compute_features(
        _context(_sequence(6)), order_features(["summary_vector"])
    )
    values = result.arrays["summary_features"]
    names = summary_names()
    # mock_16 has no heel joint at all.
    heel = names.index("joint_left_heel_speed_mean")
    assert np.isnan(values[heel])
    duration = names.index("duration_s")
    assert float(values[duration]) == pytest.approx(5 / 30.0, rel=1e-3)


def test_summary_contains_no_dataset_level_or_label_derived_element() -> None:
    """A leaked feature is worse than a missing one."""
    forbidden = ("template", "class_", "label", "participant", "dataset", "zscore")
    for name in summary_names():
        assert not any(token in name for token in forbidden), name


# ------------------------------------------------------------- registry


def test_registry_order_is_deterministic_and_dependencies_come_first() -> None:
    ordered = order_features(["summary_vector"])
    assert ordered.index("joint_angles") < ordered.index("summary_vector")
    assert ordered.index("body_aligned_positions") < ordered.index("summary_vector")
    assert ordered[0] == "canonical_pose"
    assert order_features(["summary_vector", "summary_vector"]) == ordered


def test_unknown_feature_ids_are_dropped_not_fatal() -> None:
    assert order_features(["nope", "joint_velocity"]) == order_features(
        ["joint_velocity"]
    )


def test_every_feature_has_a_unique_array_key() -> None:
    keys = [key for definition in FEATURES for key in definition.array_keys]
    assert len(keys) == len(set(keys))


def test_every_feature_declares_unit_space_and_missing_policy() -> None:
    for definition in FEATURES:
        assert definition.label and definition.description
        assert definition.missing_policy
        for contract in definition.arrays:
            assert contract.unit and contract.space and contract.dtype
            assert contract.shape.startswith("[")


def test_locked_canonical_feature_cannot_be_deselected() -> None:
    assert "canonical_pose" in order_features([])
    assert get_feature("canonical_pose").locked


def test_presets_resolve_and_round_trip() -> None:
    for preset in PRESETS:
        resolved = order_features(preset.feature_ids)
        assert match_preset(resolved) == preset.preset_id
        assert array_keys_for(resolved)


def test_kinesynth_preset_does_not_imply_physical_velocity() -> None:
    """The existing KineSynth channel is a frame difference, and says so."""
    preset = get_preset("kinesynth_compat")
    assert "joint_displacement" in preset.feature_ids
    assert "joint_velocity" not in preset.feature_ids
    assert "fiziksel hız" in preset.description.lower()
    displacement = get_feature("joint_displacement")
    assert "FİZİKSEL HIZ DEĞİLDİR" in displacement.description


def test_applicability_reports_why_a_feature_is_unavailable() -> None:
    verdict = applicability(get_feature("body_scale"), ZED_BODY_18)
    assert not verdict.supported
    assert "pelvis" in verdict.reason

    mapped = applicability(
        get_feature("tracker_joint_orientations"),
        REHAB24_6_MOCAP,
        mapping_active=True,
    )
    assert not mapped.supported
    assert "eşleştirme" in mapped.reason.lower()

    fine = applicability(get_feature("joint_velocity"), REHAB24_6_MOCAP)
    assert fine.supported


def test_roles_resolve_against_every_registered_skeleton() -> None:
    for spec in (MOCK_SKELETON, ZED_BODY_18, ZED_BODY_34, REHAB24_6_MOCAP):
        roles = resolve_roles(spec)
        for role, index in roles.items():
            assert index is None or 0 <= index < spec.num_joints, (spec.name, role)
    # The three formats that have a pelvis really do resolve it.
    assert resolve_roles(ZED_BODY_34)["pelvis"] == ZED_BODY_34.index_of("pelvis")
    assert resolve_roles(REHAB24_6_MOCAP)["pelvis"] == REHAB24_6_MOCAP.index_of("Hips")
    assert resolve_roles(ZED_BODY_18)["pelvis"] is None


def test_zed34_and_rehab24_agree_on_the_same_movement() -> None:
    """The same physical pose, expressed in two layouts, yields the same knee angle.

    This is the property a joint mapping has to preserve: geometry recomputed
    on the target skeleton must describe the same body, not a differently
    indexed one.
    """
    from kinecapture.visualization.mapping import ZED34_TO_REHAB24_V0

    rng = np.random.default_rng(7)
    native = rng.normal(size=(5, ZED_BODY_34.num_joints, 3)).astype(np.float32)
    mapped = ZED34_TO_REHAB24_V0.apply(native)

    native_angles = compute_features(
        _context(native, spec=ZED_BODY_34), ["joint_angles"]
    ).arrays["joint_angles_rad"]
    mapped_angles = compute_features(
        _context(mapped, spec=REHAB24_6_MOCAP), ["joint_angles"]
    ).arrays["joint_angles_rad"]

    for angle_id in ("left_knee_angle", "right_elbow_angle", "pelvis_tilt"):
        column = ANGLE_IDS.index(angle_id)
        np.testing.assert_allclose(
            native_angles[:, column], mapped_angles[:, column], rtol=1e-5
        )
