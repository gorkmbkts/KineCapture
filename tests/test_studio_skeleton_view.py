"""The 3-D view's anatomy, its geometry and its camera. Mostly without Qt.

Everything a person would notice being wrong here is arithmetic: which colour
a limb is, where a joint lands on screen, which joint a click means, which way
the camera turns. Those are tested directly. The renderer is checked only for
the things a renderer can get wrong on its own - that it starts, that it says
so when it cannot, and that it stops animating when nobody is watching.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kinecapture.studio.services.camera_presets import (
    PRESETS,
    PRESETS_BY_KEY,
    TRANSITION_SECONDS,
    CameraTransition,
    camera_for_preset,
    ease,
    shortest_turn,
)
from kinecapture.studio.services.skeleton3d import (
    MAX_ELEVATION,
    MIN_ELEVATION,
    OrbitCamera,
    body_target,
    bone_ribbons,
    feet_pivot,
    pick_joint,
    project_points,
)
from kinecapture.studio.services.skeleton_palette import (
    bone_groups,
    group_for_role,
    joint_groups,
    joint_labels,
    joint_tokens,
)
from kinecapture.visualization.skeleton_spec import (
    ZED_BODY_18,
    ZED_BODY_34,
    get_skeleton_spec,
)


# ------------------------------------------------------------------ SKEL-02


def test_a_role_is_placed_on_the_right_limb() -> None:
    assert group_for_role("right_elbow") == "right_arm"
    assert group_for_role("left_knee") == "left_leg"
    assert group_for_role("right_heel") == "right_leg"
    assert group_for_role("left_clavicle") == "left_arm"
    assert group_for_role("pelvis") == "torso"
    assert group_for_role("neck") == "torso"


def test_an_unmapped_role_is_named_unknown_not_guessed() -> None:
    assert group_for_role("") == "unknown"
    assert group_for_role("left_tail") == "unknown"
    assert group_for_role("right_antenna") == "unknown"


def test_the_colour_follows_the_role_table_not_the_index() -> None:
    """Index 5 is a left shoulder in one format and a right one in another."""
    thirty_four = joint_groups(ZED_BODY_34)
    eighteen = joint_groups(ZED_BODY_18)
    assert thirty_four[ZED_BODY_34.index_of("left_shoulder")] == "left_arm"
    assert thirty_four[ZED_BODY_34.index_of("right_shoulder")] == "right_arm"
    assert eighteen[ZED_BODY_18.index_of("left_shoulder")] == "left_arm"
    assert eighteen[ZED_BODY_18.index_of("right_shoulder")] == "right_arm"
    # The same *position* is a different joint in the two formats, which is
    # exactly why nothing here is keyed on a number. Index 2 is the chest in
    # one and the right shoulder in the other; anything reading the index
    # would paint the torso as an arm on half the recordings in this project.
    assert ZED_BODY_34.joint_names[2] == "chest_spine"
    assert ZED_BODY_18.joint_names[2] == "right_shoulder"
    assert thirty_four[2] == "torso"
    assert eighteen[2] == "right_arm"


@pytest.mark.parametrize("name", ["zed_body_18", "zed_body_34", "zed_body_38"])
def test_every_shipped_format_is_mapped_without_inventing_sides(name: str) -> None:
    spec = get_skeleton_spec(name)
    groups = joint_groups(spec)
    assert len(groups) == spec.num_joints
    for index, group in enumerate(groups):
        joint = spec.joint_names[index]
        if group == "unknown":
            continue
        # A joint named "left_*" is never coloured on the right, and vice
        # versa. This is the mistake that would be invisible until somebody
        # tried to use the labels.
        if joint.startswith("left_"):
            assert group.startswith("left"), joint
        if joint.startswith("right_"):
            assert group.startswith("right"), joint


def test_a_bone_between_the_chest_and_a_shoulder_belongs_to_the_limb() -> None:
    spec = ZED_BODY_34
    edges = [(spec.index_of("chest_spine"), spec.index_of("left_clavicle"))]
    assert bone_groups(spec, edges) == ("left_arm",)


def test_a_bone_touching_an_unmapped_joint_is_neutral() -> None:
    spec = ZED_BODY_34
    thumb = spec.index_of("left_thumb")
    edges = [(spec.index_of("left_wrist"), thumb)]
    assert bone_groups(spec, edges) == ("unknown",)


def test_a_joint_is_labelled_by_its_role_where_there_is_one() -> None:
    labels = joint_labels(ZED_BODY_34)
    assert labels[ZED_BODY_34.index_of("left_knee")] == "left knee"
    # And by the format's own name where there is not - never a bare index.
    thumb = ZED_BODY_34.index_of("left_thumb")
    assert labels[thumb] == "left_thumb"
    assert all(label for label in labels)


def test_the_palette_resolves_to_real_tokens() -> None:
    from kinecapture.studio.theme import load_tokens

    tokens = load_tokens("dark")
    for token in set(joint_tokens(ZED_BODY_34)):
        assert tokens.colour(token).startswith("#")


def test_no_spec_means_no_claim() -> None:
    assert joint_groups(None) == ()
    assert bone_groups(None) == ()
    assert joint_labels(None) == ()


# ------------------------------------------------------------------ SKEL-01


def _pose() -> np.ndarray:
    return np.asarray(
        [
            [0.0, 1.6, 0.0],
            [0.0, 1.2, 0.0],
            [0.3, 1.2, 0.0],
            [np.nan, np.nan, np.nan],
        ],
        dtype=np.float32,
    )


def test_a_bone_is_geometry_not_a_one_pixel_line() -> None:
    """glLineWidth is why they looked like staircases; quads do not."""
    vertices, index, across = bone_ribbons(
        _pose(), [(0, 1), (1, 2)], np.asarray([0.0, 1.4, 4.0]), 0.05
    )
    # Two triangles per bone.
    assert vertices.shape == (12, 3)
    assert list(index) == [0] * 6 + [1] * 6
    # And the across-ribbon coordinate the shader fades its edge from.
    assert set(np.unique(across)) == {-1.0, 1.0}
    assert len(across) == len(vertices)


def test_a_bone_with_a_missing_end_is_left_out() -> None:
    vertices, index, _across = bone_ribbons(
        _pose(), [(0, 1), (1, 3)], np.asarray([0.0, 1.4, 4.0]), 0.05
    )
    assert vertices.shape == (6, 3)
    assert set(index) == {0}
    # And nothing was drawn to the origin instead.
    assert not np.isclose(vertices, 0.0).all(axis=1).any()


def test_a_ribbon_has_area_even_seen_end_on() -> None:
    """A bone pointing at the camera still has to be visible."""
    pose = np.asarray([[0.0, 1.0, 0.0], [0.0, 1.0, 1.0]], dtype=np.float32)
    vertices, _index, _across = bone_ribbons(
        pose, [(0, 1)], np.asarray([0.0, 1.0, 5.0]), 0.05
    )
    assert vertices.shape == (6, 3)
    spread = vertices.max(axis=0) - vertices.min(axis=0)
    assert spread.max() > 0.0
    assert np.isfinite(vertices).all()


def test_a_ribbon_keeps_its_width() -> None:
    pose = np.asarray([[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]], dtype=np.float32)
    for eye in (
        np.asarray([0.5, 1.0, 4.0]),
        np.asarray([4.0, 1.0, 0.5]),
        np.asarray([0.5, 5.0, 0.2]),
    ):
        vertices, _index, _across = bone_ribbons(pose, [(0, 1)], eye, 0.08)
        # The two vertices at one end are the ribbon's width apart.
        assert np.linalg.norm(vertices[0] - vertices[1]) == pytest.approx(
            0.08, abs=1e-5
        )


def test_no_bones_is_not_an_error() -> None:
    vertices, index, across = bone_ribbons(None, [(0, 1)], np.zeros(3), 0.05)
    assert len(vertices) == 0 and len(index) == 0 and len(across) == 0


def test_the_bone_edge_is_softened_without_depending_on_multisampling() -> None:
    """Measured here: setSamples(4) is requested and the driver grants 0.

    So the smooth edge is computed in the shader, where nothing can decline
    it. This checks the mechanism is present rather than re-asking for MSAA.
    """
    from kinecapture.studio.views import skeleton3d as module

    assert "fwidth(edge_out)" in module._FLAT_FRAGMENT
    assert "soften" in module._FLAT_FRAGMENT
    assert "edge_in" in module._VERTEX_SHADER


# ------------------------------------------------------------------ JOINT-02


def test_a_joint_projects_onto_the_widget() -> None:
    camera = OrbitCamera(target=(0.0, 1.0, 0.0), distance=3.0)
    matrix = camera.matrix(1.0)
    projected = project_points(
        np.asarray([[0.0, 1.0, 0.0]], dtype=np.float32), matrix, 400, 400
    )
    assert projected.shape == (1, 3)
    # The point the camera is aimed at lands in the middle of the viewport.
    assert projected[0, 0] == pytest.approx(200.0, abs=1.0)
    assert projected[0, 1] == pytest.approx(200.0, abs=1.0)


def test_a_point_behind_the_camera_is_not_projected_in_front_of_it() -> None:
    camera = OrbitCamera(azimuth=0.0, elevation=0.0, target=(0, 0, 0), distance=2.0)
    matrix = camera.matrix(1.0)
    behind = np.asarray([[10.0, 0.0, 0.0]], dtype=np.float32)
    projected = project_points(behind, matrix, 400, 400)
    assert not np.isfinite(projected[0]).all()


def test_the_nearer_of_two_overlapping_joints_is_the_one_picked() -> None:
    """The far shoulder must not be marked instead of the near one."""
    projected = np.asarray(
        [
            [200.0, 200.0, 0.8],  # far
            [201.0, 201.0, 0.2],  # near
        ]
    )
    assert pick_joint(projected, 200.0, 200.0, 14.0) == 1


def test_clicking_empty_space_picks_nothing() -> None:
    projected = np.asarray([[200.0, 200.0, 0.5]])
    assert pick_joint(projected, 20.0, 20.0, 14.0) is None


def test_an_unprojectable_joint_is_never_picked() -> None:
    projected = np.asarray([[np.nan, np.nan, np.nan]])
    assert pick_joint(projected, 0.0, 0.0, 999.0) is None
    assert pick_joint(np.zeros((0, 3)), 0.0, 0.0, 999.0) is None


# -------------------------------------------------------------------- CAM-04


def test_the_pivot_is_between_the_feet_on_the_floor() -> None:
    window = np.asarray(
        [
            [[-0.2, 0.05, 0.0], [0.2, 0.06, 0.0]],
            [[-0.2, 0.04, 0.0], [0.2, 0.05, 0.0]],
        ],
        dtype=np.float32,
    )
    pivot = feet_pivot(window, 0, 1, up_axis=1)
    assert pivot is not None
    assert pivot[0] == pytest.approx(0.0, abs=1e-5)
    # On the ground, not at ankle height: a jump must not lift the axis.
    assert pivot[1] == pytest.approx(0.04, abs=1e-5)


def test_a_jump_does_not_lift_the_pivot() -> None:
    standing = np.asarray([[[-0.2, 0.05, 0.0], [0.2, 0.05, 0.0]]], dtype=np.float32)
    airborne = np.asarray([[[-0.2, 0.55, 0.0], [0.2, 0.55, 0.0]]], dtype=np.float32)
    window = np.concatenate([standing, airborne], axis=0)
    # Measured over the window, the floor is the lowest the feet ever were.
    assert feet_pivot(window, 0, 1, up_axis=1)[1] == pytest.approx(0.05, abs=1e-5)


def test_a_measured_floor_wins_over_the_lowest_foot() -> None:
    """FLOOR-04: the instantaneous minimum is not a substitute for a floor."""
    window = np.asarray([[[-0.2, 0.30, 0.0], [0.2, 0.31, 0.0]]], dtype=np.float32)
    assert feet_pivot(window, 0, 1, up_axis=1, floor_height=0.0)[1] == 0.0


def test_no_ankles_means_no_pivot_rather_than_the_origin() -> None:
    window = np.full((2, 2, 3), np.nan, dtype=np.float32)
    assert feet_pivot(window, 0, 1) is None
    assert feet_pivot(None, 0, 1) is None
    assert feet_pivot(window, None, None) is None


def test_the_look_at_point_is_the_hips_when_there_are_hips() -> None:
    window = np.asarray(
        [[[0.0, 0.0, 0.0], [-0.1, 0.95, 0.0], [0.1, 0.95, 0.0]]], dtype=np.float32
    )
    target = body_target(window, hips=(1, 2))
    assert target[1] == pytest.approx(0.95, abs=1e-5)


def test_without_hips_the_target_is_an_honest_fallback() -> None:
    window = np.asarray([[[0.0, 0.0, 0.0], [0.0, 2.0, 0.0]]], dtype=np.float32)
    target = body_target(window, hips=())
    assert target is not None
    assert target[1] == pytest.approx(1.0, abs=1e-5)


# -------------------------------------------------------------- CAM-01/02


def test_a_plain_drag_turns_without_changing_the_height() -> None:
    camera = OrbitCamera(elevation=math.radians(12.0))
    turned = camera.turn(math.radians(90.0))
    assert turned.elevation == camera.elevation
    assert turned.azimuth != camera.azimuth


def test_the_middle_drag_looks_from_above_and_below() -> None:
    camera = OrbitCamera(elevation=0.0)
    up = camera.inspect(0.0, 0.5)
    down = camera.inspect(0.0, -0.5)
    assert up.elevation > 0.0 > down.elevation


def test_neither_mode_can_flip_the_camera_over() -> None:
    camera = OrbitCamera()
    for _ in range(50):
        camera = camera.inspect(0.0, 0.5)
    assert camera.elevation <= MAX_ELEVATION
    for _ in range(100):
        camera = camera.inspect(0.0, -0.5)
    assert camera.elevation >= MIN_ELEVATION


def test_the_axis_and_the_look_at_point_stay_different_things() -> None:
    camera = OrbitCamera(target=(0.0, 1.0, 0.0))
    moved = camera.with_target((0.0, 0.0, 0.0))
    assert moved.target == (0.0, 0.0, 0.0)
    assert moved.azimuth == camera.azimuth
    assert moved.elevation == camera.elevation


def test_turning_the_camera_changes_no_measurement() -> None:
    joints = np.asarray([[0.1, 1.2, -0.3]], dtype=np.float32)
    before = joints.copy()
    camera = OrbitCamera()
    for _ in range(20):
        camera = camera.turn(0.2).zoom(1.05).pan(3, -2)
    assert np.array_equal(joints, before)


# ------------------------------------------------------------- PRESET-01/02


def test_the_seven_directions_and_the_recording_are_all_offered() -> None:
    keys = [preset.key for preset in PRESETS]
    for wanted in (
        "front", "back", "left", "right", "top", "front_left", "front_right",
        "camera",
    ):
        assert wanted in keys
    assert all(preset.label and preset.description for preset in PRESETS)


def test_a_preset_is_measured_from_a_fixed_reference() -> None:
    """"Ön" must not be re-interpreted as the athlete turns."""
    camera = OrbitCamera()
    reference = math.radians(30.0)
    front = camera_for_preset(
        PRESETS_BY_KEY["front"], camera, reference_azimuth=reference
    )
    assert front.azimuth == pytest.approx(reference)


def test_a_side_preset_is_a_quarter_turn_and_lands_on_that_side() -> None:
    """A quarter turn is the arithmetic; the side is the requirement.

    This test used to assert only the first half, with the sign the y-up
    camera happens to use - so it passed while "Sağ" stood beside the
    athlete's left shoulder. Where the camera ends up is checked in
    `test_studio_facing.py` against a body whose facing is known; here the
    two are only required to be quarter turns in *opposite* directions.
    """
    camera = OrbitCamera()
    reference = math.radians(30.0)
    angles = {
        key: camera_for_preset(
            PRESETS_BY_KEY[key], camera, reference_azimuth=reference
        ).azimuth
        for key in ("front", "left", "right")
    }
    left = math.degrees(shortest_turn(angles["front"], angles["left"]))
    right = math.degrees(shortest_turn(angles["front"], angles["right"]))
    assert abs(left) == pytest.approx(90.0, abs=1e-6)
    assert abs(right) == pytest.approx(90.0, abs=1e-6)
    assert left == pytest.approx(-right, abs=1e-6)


def test_the_top_preset_is_a_usable_view_from_directly_overhead() -> None:
    """It used to stop 12 degrees short and still be called "Üst".

    The reason was real - at the pole the view direction and the world's up
    are parallel, `cross` returns zero and the matrix collapses - but the
    answer was to name the workaround after the thing it was avoiding. The
    camera now keeps a defined orientation at the pole, so the preset can be
    what it claims.
    """
    camera = camera_for_preset(
        PRESETS_BY_KEY["top"], OrbitCamera(), reference_azimuth=0.0
    )
    assert math.degrees(camera.elevation) == pytest.approx(90.0, abs=0.01)
    matrix = camera.matrix(1.0)
    assert np.isfinite(matrix).all()

    # Looking straight down the body's own axis: the head and the feet land on
    # the same pixel, and the shoulders are apart. A collapsed matrix fails
    # both, and a 78-degree view fails the first.
    joints = np.array(
        [[0.2, 1.4, 0.0], [-0.2, 1.4, 0.0], [0.0, 1.7, 0.0], [0.0, 0.0, 0.0]],
        dtype=np.float32,
    )
    points = project_points(joints, matrix, 500, 500)
    assert float(np.hypot(*(points[2, :2] - points[3, :2]))) < 1.0
    assert float(np.hypot(*(points[0, :2] - points[1, :2]))) > 40.0


def test_the_short_way_round_is_taken() -> None:
    assert math.degrees(
        shortest_turn(math.radians(350), math.radians(10))
    ) == pytest.approx(20.0, abs=1e-6)
    assert math.degrees(
        shortest_turn(math.radians(10), math.radians(350))
    ) == pytest.approx(-20.0, abs=1e-6)
    assert abs(math.degrees(shortest_turn(0.0, math.radians(179)))) <= 180.0


def test_the_journey_is_the_same_length_however_far_it_goes() -> None:
    """PRESET-02: about 1.5 seconds, near or far."""
    near = CameraTransition.to_camera(
        OrbitCamera(azimuth=0.0), OrbitCamera(azimuth=math.radians(20))
    )
    far = CameraTransition.to_camera(
        OrbitCamera(azimuth=0.0), OrbitCamera(azimuth=math.radians(170))
    )
    assert near.duration == far.duration == TRANSITION_SECONDS
    assert near.finished(TRANSITION_SECONDS)
    assert far.finished(TRANSITION_SECONDS)
    assert not near.finished(TRANSITION_SECONDS - 0.01)


def test_the_journey_is_driven_by_time_not_by_frames() -> None:
    transition = CameraTransition.to_camera(
        OrbitCamera(azimuth=0.0), OrbitCamera(azimuth=math.radians(90))
    )
    # Sampled unevenly, as a real timer does, it still lands where it should.
    for elapsed in (0.0, 0.01, 0.9, 1.0, 1.49, TRANSITION_SECONDS, 99.0):
        assert np.isfinite(transition.at(elapsed).azimuth)
    assert math.degrees(transition.at(TRANSITION_SECONDS).azimuth) == pytest.approx(
        90.0, abs=1e-6
    )


def test_a_journey_starts_and_stops_smoothly() -> None:
    assert ease(0.0) == 0.0
    assert ease(1.0) == 1.0
    # Slower at the ends than in the middle: that is what "smooth" means here.
    assert ease(0.1) < 0.1
    assert ease(0.9) > 0.9
    assert ease(-5.0) == 0.0 and ease(5.0) == 1.0


def test_a_three_fifty_to_ten_journey_never_goes_the_long_way() -> None:
    transition = CameraTransition.to_camera(
        OrbitCamera(azimuth=math.radians(350)),
        OrbitCamera(azimuth=math.radians(10)),
    )
    seen = [
        math.degrees(transition.at(t * TRANSITION_SECONDS).azimuth)
        for t in np.linspace(0.0, 1.0, 40)
    ]
    # Every sample is in the 20-degree arc through zero, never out at 180.
    for angle in seen:
        assert angle >= 349.0 or angle <= 11.0, angle


def test_a_new_journey_starts_from_where_the_camera_is() -> None:
    """PRESET-03: no queue, no teleport."""
    first = CameraTransition.to_camera(
        OrbitCamera(azimuth=0.0), OrbitCamera(azimuth=math.radians(180))
    )
    midway = first.at(TRANSITION_SECONDS / 2)
    second = CameraTransition.to_camera(
        midway, OrbitCamera(azimuth=math.radians(45))
    )
    assert second.at(0.0).azimuth == pytest.approx(midway.azimuth)
