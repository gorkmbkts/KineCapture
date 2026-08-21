"""Domain model validation, serialisation and skeleton definitions."""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import Correctness, DataOrigin, TrackingState
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.models import BodyPose, CameraInfo, FramePacket
from kinecapture.domain.project import (
    ErrorInterval,
    MovementSample,
    Take,
    evaluate_sample,
    renumber_samples,
    validate_samples,
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


def test_sample_rejects_reversed_range() -> None:
    with pytest.raises(ValidationError) as info:
        MovementSample.create("t", 50, 10)
    assert info.value.code == "sample_reversed"


def test_sample_roundtrip_carries_both_levels() -> None:
    sample = MovementSample.create("take_1", 10, 40)
    sample.exercise = "squat"
    sample.correctness = Correctness.INCORRECT
    sample.error_intervals.append(ErrorInterval.create(15, 22, "knee-valgus"))

    restored = MovementSample.from_dict(sample.to_dict())
    assert restored.sample_id == sample.sample_id
    assert restored.exercise == "squat"
    assert restored.correctness is Correctness.INCORRECT
    assert restored.frame_count == 31
    assert len(restored.error_intervals) == 1
    interval = restored.error_intervals[0]
    assert interval.error_code == "knee-valgus"
    assert (interval.start_frame, interval.end_frame) == (15, 22)
    assert interval.frame_count == 8  # inclusive at both ends


def test_boundaries_are_inclusive_at_both_ends() -> None:
    """The one convention shared by UI, sidecar and export."""
    sample = MovementSample.create("t", 10, 19)
    assert sample.frame_count == 10
    assert sample.contains(10) and sample.contains(19)
    assert not sample.contains(9) and not sample.contains(20)

    interval = ErrorInterval.create(12, 12, "x")
    assert interval.frame_count == 1


def test_sample_clamp_keeps_children_inside() -> None:
    sample = MovementSample.create("t", 10, 20)
    assert sample.clamp(-5, 100) == (10, 20)
    assert sample.clamp(15, 12) == (12, 15)


def test_error_interval_needs_a_class_to_be_well_formed() -> None:
    assert not ErrorInterval.create(1, 5).is_well_formed
    assert ErrorInterval.create(1, 5, "knee-valgus").is_well_formed


def test_validate_samples_finds_overlap_and_range() -> None:
    a = MovementSample.create("t", 0, 20)
    b = MovementSample.create("t", 15, 40)
    renumber_samples([a, b])
    problems = validate_samples([a, b], frame_count=30)
    kinds = {problem["issue"] for problem in problems}
    assert "overlap" in kinds
    assert "out_of_range" in kinds


def test_validate_samples_reports_a_stranded_interval() -> None:
    sample = MovementSample.create("t", 0, 20)
    sample.error_intervals.append(ErrorInterval.create(30, 35, "knee-valgus"))
    problems = validate_samples([sample], frame_count=100)
    assert any(p["issue"] == "interval_outside_sample" for p in problems)


# ------------------------------------------------- legacy label migration


def test_legacy_v1_segment_migrates_without_losing_data() -> None:
    """An old sidecar entry must survive, and must not gain a fake verdict."""
    legacy = {
        "schema_version": "1.0.0",
        "segment_id": "rep_legacy",
        "take_id": "take_1",
        "index": 2,
        "start_frame": 10,
        "end_frame": 60,
        "revision": 4,
        "source": "manual",
        "status": "active",
        "annotation": {
            "exercise": "squat",
            "correctness": "uncertain",
            "error_types": ["knee-valgus", "back-round"],
            "affected_joints": ["left_knee"],
            "movement_phase": "concentric",
            "severity": 2.0,
            "annotator_confidence": 0.8,
            "status": "approved",
            "note": "eski not",
            "evidence_intervals": [
                {
                    "interval_id": "ev_1",
                    "start_frame": 20,
                    "end_frame": 30,
                    "error_type": "knee-valgus",
                    "severity": 1.5,
                }
            ],
        },
    }
    sample = MovementSample.from_dict(legacy)

    assert sample.sample_id == "rep_legacy"
    assert sample.index == 2 and sample.revision == 4
    assert sample.exercise == "squat"
    assert sample.note == "eski not"
    # An undecided verdict must never be promoted into a definite one.
    assert sample.correctness is Correctness.UNLABELLED
    assert sample.legacy["correctness"] == "uncertain"
    # An old evidence interval becomes a real error interval.
    assert len(sample.error_intervals) == 1
    assert sample.error_intervals[0].error_code == "knee-valgus"
    # Sample-level error classes had no timing, so they are not invented into
    # intervals; they are recorded as unlocalised instead.
    assert sample.legacy["unlocalised_error_types"] == ["knee-valgus", "back-round"]
    # Dropped concepts are preserved verbatim.
    assert sample.legacy["movement_phase"] == "concentric"
    assert sample.legacy["severity"] == 2.0
    assert sample.legacy["affected_joints"] == ["left_knee"]
    assert sample.legacy["status"] == "approved"


def test_migrated_sample_round_trips_through_v2() -> None:
    legacy = {
        "segment_id": "rep_x",
        "start_frame": 0,
        "end_frame": 10,
        "annotation": {"exercise": "squat", "correctness": "unknown",
                       "movement_phase": "hold"},
    }
    once = MovementSample.from_dict(legacy)
    twice = MovementSample.from_dict(once.to_dict())
    assert twice.to_dict() == once.to_dict()
    assert twice.legacy["movement_phase"] == "hold"


def test_repetition_segment_alias_still_works() -> None:
    from kinecapture.domain.project import RepetitionSegment

    assert RepetitionSegment is MovementSample


# ------------------------------------------------------ readiness rule


def test_evaluate_sample_covers_every_state() -> None:
    from kinecapture.domain.enums import SampleReadiness, SegmentStatus

    blank = MovementSample.create("t", 0, 20)
    assert evaluate_sample(blank)[0] is SampleReadiness.UNLABELLED

    good = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.CORRECT
    )
    assert evaluate_sample(good)[0] is SampleReadiness.READY

    contradiction = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.CORRECT
    )
    contradiction.error_intervals.append(ErrorInterval.create(2, 5, "k"))
    assert evaluate_sample(contradiction)[0] is SampleReadiness.CONTRADICTION

    pending = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.INCORRECT
    )
    assert evaluate_sample(pending)[0] is SampleReadiness.NEEDS_ERROR_INTERVAL

    stranded = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.INCORRECT
    )
    stranded.error_intervals.append(ErrorInterval.create(50, 60, "k"))
    assert evaluate_sample(stranded)[0] is SampleReadiness.INVALID_INTERVAL

    excluded = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.CORRECT
    )
    excluded.status = SegmentStatus.EXCLUDED
    assert evaluate_sample(excluded)[0] is SampleReadiness.EXCLUDED


def test_unknown_error_class_only_checked_when_vocabulary_given() -> None:
    from kinecapture.domain.enums import SampleReadiness

    sample = MovementSample.create(
        "t", 0, 20, exercise="squat", correctness=Correctness.INCORRECT
    )
    sample.error_intervals.append(ErrorInterval.create(2, 5, "made-up"))
    assert evaluate_sample(sample)[0] is SampleReadiness.READY
    assert evaluate_sample(sample, known_error_codes=["real"])[0] is (
        SampleReadiness.INVALID_INTERVAL
    )


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


def test_label_schema_ships_no_invented_vocabulary() -> None:
    """The ontology is the researcher's to define, not the code's."""
    schema = LabelSchema.default()
    assert schema.exercises == []
    assert schema.error_types == []


def test_label_schema_rejects_duplicates() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Squat")
    with pytest.raises(ValidationError, match="zaten tanımlı"):
        schema.add_exercise("squat")


def test_error_type_duplicates_are_detected_across_spelling() -> None:
    schema = LabelSchema.default()
    first = schema.add_error_type("Diz İçe Çöküyor")
    for variant in ("diz içe çöküyor", "  DİZ  İÇE   ÇÖKÜYOR ", "Diz içe çöküyor"):
        assert schema.match_error_type(variant) is not None
        with pytest.raises(ValidationError) as info:
            schema.add_error_type(variant)
        assert info.value.code == "error_type_duplicate"
        assert schema.ensure_error_type(variant).code == first.code
    assert len(schema.error_types) == 1


def test_error_type_search_ranks_prefix_matches_first() -> None:
    schema = LabelSchema.default()
    schema.add_error_type("Sırt yuvarlanıyor")
    schema.add_error_type("Diz içe çöküyor")
    schema.add_error_type("Aşırı diz öne çıkıyor")
    codes = [o.code for o in schema.search_error_types("diz")]
    assert codes[0] == "diz-ice-cokuyor"
    assert "asiri-diz-one-cikiyor" in codes
    assert "sirt-yuvarlaniyor" not in codes
    # An empty query lists everything.
    assert len(schema.search_error_types("")) == 3


def test_renaming_an_error_type_keeps_its_code() -> None:
    """Annotations and releases reference the code, so it must not move."""
    schema = LabelSchema.default()
    option = schema.add_error_type("Diz içe çöküyor")
    renamed = schema.rename_error_type(option.code, "Diz valgusu")
    assert renamed.code == option.code
    assert renamed.label == "Diz valgusu"
    assert schema.label_for_error(option.code) == "Diz valgusu"


def test_error_type_in_use_cannot_be_removed() -> None:
    schema = LabelSchema.default()
    option = schema.add_error_type("Diz içe çöküyor")
    with pytest.raises(ValidationError) as info:
        schema.remove_error_type(option.code, used_codes=[option.code])
    assert info.value.code == "error_type_in_use"
    schema.remove_error_type(option.code, used_codes=[])
    assert schema.error_types == []


def test_label_mapping_is_stable_and_binary() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Lunge")
    schema.add_exercise("Squat")
    schema.add_error_type("Sırt yuvarlanıyor")
    schema.add_error_type("Diz içe çöküyor")
    mapping = schema.label_mapping()

    # Indices come from sorted codes, so two releases agree on class meaning.
    assert mapping["exercise"]["code_to_index"] == {"lunge": 0, "squat": 1}
    assert mapping["error_types"]["code_to_index"] == {
        "diz-ice-cokuyor": 0,
        "sirt-yuvarlaniyor": 1,
    }
    # The verdict is binary; unlabelled never gets a class index.
    assert mapping["correctness"]["classes"] == ["correct", "incorrect"]
    assert mapping["correctness"]["binary"] is True


def test_schema_reports_unknown_values() -> None:
    schema = LabelSchema.default()
    schema.add_exercise("Squat")
    problems = schema.validate_annotation_values(
        exercise="deadlift", error_types=["nope"]
    )
    issues = {p["issue"] for p in problems}
    assert issues == {"unknown_exercise", "unknown_error_type"}


def test_legacy_schema_blocks_are_preserved() -> None:
    """Movement phase was removed, but an old project file keeps its data."""
    schema = LabelSchema.from_dict(
        {
            "schema_version": "1.0.0",
            "exercises": [{"code": "squat", "label": "Squat"}],
            "movement_phases": [{"code": "hold", "label": "Duraklama"}],
            "severity_scale": [0.0, 3.0],
        }
    )
    assert schema.exercise_codes() == ("squat",)
    assert not hasattr(schema, "movement_phases")
    assert schema.legacy["movement_phases"][0]["code"] == "hold"
    assert schema.legacy["severity_scale"] == [0.0, 3.0]
    assert schema.to_dict()["legacy"]["movement_phases"][0]["code"] == "hold"
