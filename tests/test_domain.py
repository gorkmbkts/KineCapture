"""Domain model validation, serialisation and skeleton definitions."""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import Correctness, DataOrigin, TrackingState
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.models import BodyPose, CameraInfo, FramePacket
from kinecapture.domain.project import (
    RepetitionSegment,
    Take,
    renumber_segments,
    validate_segments,
)
from kinecapture.visualization.mapping import ZED34_TO_REHAB24_V0
from kinecapture.visualization.skeleton_spec import (
    MOCK_SKELETON,
    REHAB24_6_MOCAP,
    ZED_BODY_18,
    ZED_BODY_34,
    ZED_BODY_38,
    get_skeleton_spec,
)


def make_body(num_joints: int = 16, **kwargs) -> BodyPose:
    return BodyPose(
        tracking_id=1,
        tracking_state=TrackingState.OK,
        body_format="mock_16",
        joint_positions_xyz=np.zeros((num_joints, 3), dtype=np.float32),
        joint_confidences=np.ones(num_joints, dtype=np.float32),
        **kwargs,
    )


# ---------------------------------------------------------------- BodyPose


def test_body_pose_rejects_wrong_joint_shape() -> None:
    with pytest.raises(ValidationError, match="joint_positions_xyz"):
        BodyPose(
            tracking_id=1,
            tracking_state=TrackingState.OK,
            body_format="x",
            joint_positions_xyz=np.zeros((16, 2), dtype=np.float32),
            joint_confidences=np.ones(16, dtype=np.float32),
        )


def test_body_pose_rejects_mismatched_confidences() -> None:
    with pytest.raises(ValidationError, match="joint_confidences"):
        BodyPose(
            tracking_id=1,
            tracking_state=TrackingState.OK,
            body_format="x",
            joint_positions_xyz=np.zeros((16, 3), dtype=np.float32),
            joint_confidences=np.ones(8, dtype=np.float32),
        )


def test_body_pose_coerces_dtype() -> None:
    body = BodyPose(
        tracking_id=1,
        tracking_state="ok",
        body_format="x",
        joint_positions_xyz=np.zeros((4, 3), dtype=np.float64),
        joint_confidences=np.ones(4, dtype=np.float64),
    )
    assert body.joint_positions_xyz.dtype == np.float32
    assert body.joint_confidences.dtype == np.float32
    assert body.tracking_state is TrackingState.OK


def test_body_pose_preserves_missing_joints() -> None:
    """A joint the tracker lost must stay lost, not become a plausible number."""
    joints = np.zeros((16, 3), dtype=np.float32)
    joints[3] = np.nan
    body = make_body()
    body.joint_positions_xyz = joints
    body.__post_init__()
    assert not body.valid_joint_mask[3]
    assert body.valid_joint_ratio == pytest.approx(15 / 16)


def test_body_pose_record_roundtrip_keeps_nan() -> None:
    joints = np.arange(48, dtype=np.float32).reshape(16, 3) / 100.0
    joints[5] = np.nan
    confidences = np.linspace(0.0, 1.0, 16, dtype=np.float32)
    body = BodyPose(
        tracking_id=7,
        tracking_state=TrackingState.SEARCHING,
        body_format="mock_16",
        joint_positions_xyz=joints,
        joint_confidences=confidences,
        root_position=np.array([1.0, 2.0, 3.0], dtype=np.float32),
    )
    restored = BodyPose.from_record(body.to_record())
    assert restored.tracking_id == 7
    assert restored.tracking_state is TrackingState.SEARCHING
    assert np.isnan(restored.joint_positions_xyz[5]).all()
    finite = np.isfinite(joints).all(axis=1)
    np.testing.assert_allclose(
        restored.joint_positions_xyz[finite], joints[finite], atol=1e-5
    )
    np.testing.assert_allclose(restored.root_position, body.root_position, atol=1e-5)


def test_mean_confidence_ignores_nan() -> None:
    body = make_body(4)
    body.joint_confidences = np.array([0.5, np.nan, 1.0, np.nan], dtype=np.float32)
    assert body.mean_confidence() == pytest.approx(0.75)


# -------------------------------------------------------------- FramePacket


def test_frame_packet_validates_color_shape() -> None:
    with pytest.raises(ValidationError, match="color_frame"):
        FramePacket(
            frame_index=0,
            host_timestamp_ns=0,
            camera_timestamp_ns=0,
            color_frame=np.zeros((4, 4), dtype=np.uint8),
        )


def test_frame_packet_validates_depth_resolution() -> None:
    with pytest.raises(ValidationError) as info:
        FramePacket(
            frame_index=0,
            host_timestamp_ns=0,
            camera_timestamp_ns=0,
            color_frame=np.zeros((8, 8, 3), dtype=np.uint8),
            depth_frame=np.zeros((4, 4), dtype=np.float32),
        )
    assert info.value.code == "depth_resolution_mismatch"


def test_frame_packet_rejects_negative_index() -> None:
    with pytest.raises(ValidationError, match="frame_index"):
        FramePacket(
            frame_index=-1,
            host_timestamp_ns=0,
            camera_timestamp_ns=0,
            color_frame=np.zeros((4, 4, 3), dtype=np.uint8),
        )


def test_primary_body_prefers_pinned_id() -> None:
    good = make_body()
    good.tracking_id = 2
    other = make_body()
    other.tracking_id = 5
    packet = FramePacket(
        frame_index=0,
        host_timestamp_ns=0,
        camera_timestamp_ns=0,
        color_frame=np.zeros((4, 4, 3), dtype=np.uint8),
        bodies=(good, other),
    )
    assert packet.primary_body(5).tracking_id == 5
    assert packet.primary_body(99) is not None  # falls back rather than failing


# ------------------------------------------------------------- CameraInfo


def test_camera_info_roundtrip() -> None:
    info = CameraInfo(
        backend="zed",
        model="ZED 2i",
        origin=DataOrigin.REAL,
        serial_number="31844341",
        resolution=(1280, 720),
        target_fps=30.0,
        body_format="zed_body_34",
    )
    restored = CameraInfo.from_dict(info.to_dict())
    assert restored == info
    assert not restored.is_synthetic


def test_synthetic_camera_is_marked() -> None:
    info = CameraInfo(backend="mock", model="Sentetik", origin=DataOrigin.SYNTHETIC)
    assert info.is_synthetic
    assert "Sentetik" in info.display_name


# ---------------------------------------------------------- skeleton specs


@pytest.mark.parametrize(
    "spec,count",
    [(ZED_BODY_18, 18), (ZED_BODY_34, 34), (ZED_BODY_38, 38), (MOCK_SKELETON, 16)],
)
def test_skeleton_specs_are_consistent(spec, count) -> None:
    assert spec.num_joints == count
    assert len(set(spec.joint_names)) == count
    for a, b in spec.edges:
        assert 0 <= a < count and 0 <= b < count


def test_zed_body_34_known_landmarks() -> None:
    """Spot-check indices that were read from the local SDK."""
    assert ZED_BODY_34.index_of("pelvis") == 0
    assert ZED_BODY_34.index_of("neck") == 3
    assert ZED_BODY_34.index_of("left_shoulder") == 5
    assert ZED_BODY_34.index_of("right_ankle") == 24
    assert ZED_BODY_34.index_of("head") == 26
    assert ZED_BODY_34.index_of("right_heel") == 33


def test_skeleton_spec_roundtrip() -> None:
    from kinecapture.visualization.skeleton_spec import SkeletonSpec

    restored = SkeletonSpec.from_dict(ZED_BODY_34.to_dict())
    assert restored.joint_names == ZED_BODY_34.joint_names
    assert restored.edges == ZED_BODY_34.edges


def test_side_classification() -> None:
    assert ZED_BODY_34.side_of(ZED_BODY_34.index_of("left_knee")) == "left"
    assert ZED_BODY_34.side_of(ZED_BODY_34.index_of("right_knee")) == "right"
    assert ZED_BODY_34.side_of(ZED_BODY_34.index_of("pelvis")) == "center"


def test_unknown_skeleton_raises_with_hint() -> None:
    with pytest.raises(KeyError, match="Kayıtlı biçimler"):
        get_skeleton_spec("nonexistent")


# ------------------------------------------------------------- joint mapping


def test_rehab24_mapping_is_partial_and_says_so() -> None:
    mapping = ZED34_TO_REHAB24_V0
    assert mapping.status == "partial"
    assert mapping.mapped_count == 23
    assert mapping.target_spec.num_joints == 26
    assert set(mapping.unmapped_target_joints) == {
        "Head_end",
        "LeftToeBase_end",
        "RightToeBase_end",
    }
    # Every unmapped joint carries a stated reason, so the manifest can explain
    # itself rather than just showing a hole.
    for joint in mapping.unmapped_target_joints:
        assert mapping.unmapped_reason[joint]


def test_mapping_fills_unmapped_with_nan_not_guesses() -> None:
    joints = np.arange(34 * 3, dtype=np.float32).reshape(34, 3)
    mapped = ZED34_TO_REHAB24_V0.apply(joints)
    assert mapped.shape == (26, 3)
    target = REHAB24_6_MOCAP
    assert np.isnan(mapped[target.index_of("Head_end")]).all()
    assert np.isnan(mapped[target.index_of("LeftToeBase_end")]).all()
    # A mapped joint copies its source verbatim - no transformation applied.
    np.testing.assert_array_equal(
        mapped[target.index_of("Hips")], joints[ZED_BODY_34.index_of("pelvis")]
    )
    np.testing.assert_array_equal(
        mapped[target.index_of("LeftLeg")], joints[ZED_BODY_34.index_of("left_knee")]
    )


def test_mapping_handles_sequences() -> None:
    joints = np.zeros((5, 34, 3), dtype=np.float32)
    mapped = ZED34_TO_REHAB24_V0.apply(joints)
    assert mapped.shape == (5, 26, 3)
    confidences = np.ones((5, 34), dtype=np.float32)
    assert ZED34_TO_REHAB24_V0.apply_confidence(confidences).shape == (5, 26)


def test_mapping_rejects_wrong_joint_count() -> None:
    with pytest.raises(ValidationError) as info:
        ZED34_TO_REHAB24_V0.apply(np.zeros((18, 3), dtype=np.float32))
    assert info.value.code == "mapping_joint_count_mismatch"


# ------------------------------------------------------------ project types


def test_segment_rejects_reversed_range() -> None:
    with pytest.raises(ValidationError) as info:
        RepetitionSegment.create("t", 50, 10)
    assert info.value.code == "segment_reversed"


def test_segment_roundtrip() -> None:
    segment = RepetitionSegment.create("take_1", 10, 40)
    segment.annotation.exercise = "squat"
    segment.annotation.correctness = Correctness.INCORRECT
    restored = RepetitionSegment.from_dict(segment.to_dict())
    assert restored.segment_id == segment.segment_id
    assert restored.annotation.exercise == "squat"
    assert restored.annotation.correctness is Correctness.INCORRECT
    assert restored.frame_count == 31


def test_validate_segments_finds_overlap_and_range() -> None:
    a = RepetitionSegment.create("t", 0, 20)
    b = RepetitionSegment.create("t", 15, 40)
    renumber_segments([a, b])
    problems = validate_segments([a, b], frame_count=30)
    kinds = {problem["issue"] for problem in problems}
    assert "overlap" in kinds
    assert "out_of_range" in kinds


def test_take_export_eligibility() -> None:
    from kinecapture.domain.enums import TakeQuality, TakeState

    take = Take.create("s", "p", "prj")
    assert not take.usable_for_export  # still recording
    take.state = TakeState.FINALIZED
    take.quality = TakeQuality.GOOD
    assert take.usable_for_export
    take.quality = TakeQuality.EXCLUDED
    assert not take.usable_for_export


def test_take_roundtrip_preserves_provenance() -> None:
    from kinecapture.domain.enums import TakeState

    take = Take.create("s", "p", "prj")
    take.camera_info = CameraInfo(backend="zed", model="ZED 2i", serial_number="1")
    take.skeleton_format = "zed_body_34"
    take.state = TakeState.FINALIZED
    take.metrics.frames_written = 120
    restored = Take.from_dict(take.to_dict())
    assert restored.camera_info.serial_number == "1"
    assert restored.skeleton_format == "zed_body_34"
    assert restored.state is TakeState.FINALIZED
    assert restored.metrics.frames_written == 120


# --------------------------------------------------------------- labels


def test_label_schema_ships_no_invented_error_types() -> None:
    """The error ontology is the researcher's to define, not the code's."""
    schema = LabelSchema.default()
    assert schema.exercises == []
    assert schema.error_types == []
    assert schema.movement_phases  # structural, safe to default


def test_label_schema_rejects_duplicates() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Squat")
    with pytest.raises(ValidationError, match="zaten tanımlı"):
        schema.add_exercise("squat")


def test_label_mapping_is_stable() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Lunge")
    schema.add_exercise("Squat")
    mapping = schema.label_mapping()
    # Indices come from sorted codes, so two releases agree on class meaning.
    assert mapping["exercise"]["code_to_index"] == {"lunge": 0, "squat": 1}
    assert set(mapping["correctness"]["classes"]) == {
        "correct",
        "incorrect",
        "uncertain",
        "unknown",
    }


def test_schema_reports_unknown_values() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Squat")
    problems = schema.validate_annotation_values(
        exercise="deadlift", error_types=[]
    )
    assert problems and problems[0]["issue"] == "unknown_exercise"
