"""Playback, repetition segmentation and annotation editing."""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import (
    AnnotationStatus,
    Correctness,
    SegmentSource,
    SegmentStatus,
)
from kinecapture.playback.take_reader import load_take
from tests.conftest import paced_backend, record_take


@pytest.fixture
def recorded(workspace, session):
    """A finished 40-frame synthetic take, loaded and ready to annotate."""
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=40, exercise="squat")
    service.shutdown()
    loaded = load_take(workspace, take)
    yield workspace, take, loaded
    loaded.close()


@pytest.fixture
def repository(recorded) -> AnnotationRepository:
    workspace, take, loaded = recorded
    return AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count, annotator="pytest"
    )


# ---------------------------------------------------------------- playback


def test_take_loads_with_stream_and_video(recorded) -> None:
    _workspace, take, loaded = recorded
    assert loaded.frame_count >= 40
    assert loaded.stream.skeleton_format == "mock_16"
    assert loaded.spec is not None and loaded.spec.num_joints == 16
    assert loaded.stream.tracking_ids == (1,)
    assert loaded.has_video


def test_duration_comes_from_camera_timestamps(recorded) -> None:
    """Elapsed time must not be reconstructed as index / fps."""
    _workspace, _take, loaded = recorded
    stream = loaded.stream
    assert stream.duration_s > 0
    first = stream.frames[0].camera_timestamp_ns
    last = stream.frames[-1].camera_timestamp_ns
    assert stream.duration_s == pytest.approx((last - first) / 1e9, rel=1e-6)


def test_joint_array_shape_and_dtype(recorded) -> None:
    _workspace, _take, loaded = recorded
    array = loaded.stream.joint_array(1, start=0, end=9)
    assert array.shape == (10, 16, 3)
    assert array.dtype == np.float32


def test_missing_body_frames_become_nan_not_interpolated(workspace, session) -> None:
    backend = paced_backend(width=64, height=48, tracking_loss_every=15)
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=45)
    service.shutdown()

    loaded = load_take(workspace, take, with_video=False)
    array = loaded.stream.joint_array(1)
    assert np.isnan(array).any(), "tracking gap was filled in instead of preserved"
    assert np.isfinite(array).any()


def test_video_position_is_clamped_not_drifted(recorded) -> None:
    _workspace, _take, loaded = recorded
    assert loaded.video_position_for(0) == 0
    assert loaded.video_position_for(10**6) < loaded.video.frame_count


def test_coverage_curve_matches_frame_count(recorded) -> None:
    _workspace, _take, loaded = recorded
    curve = loaded.stream.coverage_curve(1)
    assert curve.shape == (loaded.frame_count,)
    assert float(curve.max()) <= 1.0


# ------------------------------------------------------------- segmentation


def test_create_and_persist_segment(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    segment = repository.create_segment(2, 20)
    assert repository.is_dirty
    repository.save()
    assert not repository.is_dirty

    reloaded = workspace.load_segments(take)
    assert len(reloaded) == 1
    assert reloaded[0].segment_id == segment.segment_id
    assert reloaded[0].source is SegmentSource.MANUAL


def test_bounds_are_clamped_to_the_take(recorded, repository) -> None:
    _workspace, _take, loaded = recorded
    segment = repository.create_segment(-50, loaded.frame_count + 500)
    assert segment.start_frame >= 0
    assert segment.end_frame < loaded.frame_count


def test_reversed_range_is_normalised(repository) -> None:
    segment = repository.create_segment(30, 10)
    assert segment.start_frame == 10
    assert segment.end_frame == 30


def test_split_produces_two_and_inherits_labels(repository) -> None:
    segment = repository.create_segment(0, 30)
    repository.annotate(
        segment.segment_id, exercise="squat", correctness=Correctness.CORRECT
    )
    first, second = repository.split(segment.segment_id, 15)
    assert first.end_frame == 14 and second.start_frame == 15
    assert len(repository.segments) == 2
    # A boundary correction is not a statement that the labels were wrong.
    assert second.annotation.exercise == "squat"
    assert second.annotation.correctness is Correctness.CORRECT


def test_split_outside_range_is_refused(repository) -> None:
    segment = repository.create_segment(10, 20)
    with pytest.raises(ValidationError) as info:
        repository.split(segment.segment_id, 30)
    assert info.value.code == "split_out_of_range"


def test_merge_spans_both(repository) -> None:
    first = repository.create_segment(0, 10)
    second = repository.create_segment(12, 25)
    merged = repository.merge(first.segment_id, second.segment_id)
    assert merged.start_frame == 0 and merged.end_frame == 25
    assert len(repository.segments) == 1


def test_exclude_and_restore(repository) -> None:
    segment = repository.create_segment(0, 10)
    repository.set_status(segment.segment_id, SegmentStatus.EXCLUDED)
    assert not repository.find(segment.segment_id).is_active
    assert repository.active_segments == ()
    repository.set_status(segment.segment_id, SegmentStatus.ACTIVE)
    assert repository.find(segment.segment_id).is_active


def test_delete_removes_curation_only(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    segment = repository.create_segment(0, 10)
    repository.save()
    repository.delete(segment.segment_id)
    repository.save()
    assert workspace.load_segments(take) == []
    # The captured frames are untouched.
    assert workspace.take_paths(take).skeleton_stream.is_file()


def test_segments_are_renumbered_chronologically(repository) -> None:
    later = repository.create_segment(30, 38)
    earlier = repository.create_segment(0, 10)
    assert repository.find(earlier.segment_id).index == 1
    assert repository.find(later.segment_id).index == 2


def test_overlap_is_reported_not_silently_accepted(repository) -> None:
    repository.create_segment(0, 20)
    repository.create_segment(10, 30)
    problems = repository.validation_problems()
    assert any(problem["issue"] == "overlap" for problem in problems)


def test_segments_from_markers_are_tagged_as_such(repository) -> None:
    created = repository.create_from_markers([0, 15, 30], final_frame=38)
    assert len(created) == 2
    assert all(s.source is SegmentSource.OPERATOR_MARKER for s in created)


# -------------------------------------------------------------- annotation


def test_annotate_sets_only_given_fields(repository) -> None:
    segment = repository.create_segment(0, 10)
    repository.annotate(segment.segment_id, exercise="squat")
    repository.annotate(segment.segment_id, note="ilk deneme")
    annotation = repository.find(segment.segment_id).annotation
    assert annotation.exercise == "squat"
    assert annotation.note == "ilk deneme"
    assert annotation.annotator == "pytest"


def test_is_labelled_requires_a_real_decision(repository) -> None:
    segment = repository.create_segment(0, 10)
    assert not segment.annotation.is_labelled
    repository.annotate(segment.segment_id, exercise="squat")
    assert not repository.find(segment.segment_id).annotation.is_labelled
    repository.annotate(segment.segment_id, correctness=Correctness.CORRECT)
    assert repository.find(segment.segment_id).annotation.is_labelled


def test_copy_previous_annotation(repository) -> None:
    first = repository.create_segment(0, 10)
    second = repository.create_segment(12, 22)
    repository.annotate(
        first.segment_id,
        exercise="squat",
        correctness=Correctness.INCORRECT,
        error_types=["knee_valgus"],
    )
    repository.copy_annotation_from(first.segment_id, second.segment_id)
    annotation = repository.find(second.segment_id).annotation
    assert annotation.exercise == "squat"
    assert annotation.correctness is Correctness.INCORRECT
    assert annotation.error_types == ("knee_valgus",)


def test_apply_to_all_skips_excluded(repository) -> None:
    first = repository.create_segment(0, 10)
    second = repository.create_segment(12, 22)
    repository.set_status(second.segment_id, SegmentStatus.EXCLUDED)
    changed = repository.apply_to_all(
        exercise="squat", correctness=Correctness.CORRECT
    )
    assert changed == 1
    assert repository.find(first.segment_id).annotation.exercise == "squat"
    assert repository.find(second.segment_id).annotation.exercise == ""


def test_apply_to_all_with_no_arguments_changes_nothing(repository) -> None:
    repository.create_segment(0, 10)
    assert repository.apply_to_all() == 0


# ------------------------------------------------------------ undo / redo


def test_undo_and_redo(repository) -> None:
    repository.create_segment(0, 10)
    assert len(repository.segments) == 1
    repository.create_segment(12, 22)
    assert len(repository.segments) == 2

    assert repository.undo()
    assert len(repository.segments) == 1
    assert repository.redo()
    assert len(repository.segments) == 2


def test_undo_restores_annotation_values(repository) -> None:
    segment = repository.create_segment(0, 10)
    repository.annotate(segment.segment_id, exercise="squat")
    repository.annotate(segment.segment_id, exercise="lunge")
    repository.undo()
    assert repository.find(segment.segment_id).annotation.exercise == "squat"


def test_undo_on_empty_history_is_false(repository) -> None:
    assert not repository.undo()
    assert not repository.redo()


def test_new_edit_clears_redo(repository) -> None:
    repository.create_segment(0, 10)
    repository.undo()
    assert repository.can_redo
    repository.create_segment(20, 30)
    assert not repository.can_redo


# ---------------------------------------------------------------- autosave


def test_save_if_dirty_only_writes_when_needed(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    assert not repository.save_if_dirty()  # nothing changed yet
    repository.create_segment(0, 10)
    assert repository.save_if_dirty()
    assert not repository.save_if_dirty()
    assert workspace.take_paths(take).segments.is_file()


def test_status_survives_a_reload(recorded, repository) -> None:
    workspace, take, loaded = recorded
    segment = repository.create_segment(0, 10)
    repository.annotate(
        segment.segment_id,
        exercise="squat",
        correctness=Correctness.CORRECT,
        status=AnnotationStatus.APPROVED,
    )
    repository.save()

    fresh = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    assert len(fresh.segments) == 1
    assert fresh.segments[0].annotation.status is AnnotationStatus.APPROVED
    assert fresh.labelled_count == 1
