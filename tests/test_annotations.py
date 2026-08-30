"""Playback, movement-sample segmentation, error intervals and labelling.

The label model is two-level: a take holds movement samples, each movement
sample holds zero or more error intervals inside its own bounds. These tests
pin the behaviour that keeps the two levels consistent and the user's work
recoverable.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import (
    Correctness,
    SampleReadiness,
    SegmentSource,
    SegmentStatus,
)
from kinecapture.playback.take_reader import load_take
from tests.conftest import paced_backend, record_take


@pytest.fixture
def recorded(workspace, session):
    """A finished 40-frame synthetic take, loaded and ready to annotate."""
    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=40, exercise="squat")
    service.shutdown()
    loaded = load_take(workspace, take)
    yield workspace, take, loaded
    loaded.close()


@pytest.fixture
def repository(recorded) -> AnnotationRepository:
    workspace, take, loaded = recorded
    schema = workspace.label_schema
    schema.add_exercise("Squat")
    schema.add_error_type("Diz içe çöküyor")
    schema.add_error_type("Sırt yuvarlanıyor")
    workspace.save_label_schema(schema)
    return AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count, annotator="pytest"
    )


def label(repository, sample, correctness=Correctness.CORRECT):
    repository.label_sample(
        sample.sample_id, exercise="squat", correctness=correctness
    )
    return repository.find(sample.sample_id)


# ---------------------------------------------------------------- playback


def test_take_loads_with_stream_and_video(recorded) -> None:
    _workspace, _take, loaded = recorded
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
    service = CaptureService(paced_backend(width=64, height=48, tracking_loss_every=15))
    service.connect()
    take = record_take(service, workspace, session, frames=45)
    service.shutdown()

    loaded = load_take(workspace, take, with_video=False)
    array = loaded.stream.joint_array(1)
    assert np.isnan(array).any(), "tracking gap was filled in instead of preserved"
    assert np.isfinite(array).any()


def test_video_position_reports_absence_instead_of_clamping(recorded) -> None:
    """A position past the proxy has *no* colour frame, and must say so.

    Clamping to the last frame was worse than useless: it paired the current
    pose with a picture from another moment, which is indistinguishable on
    screen from a tracking failure.
    """
    _workspace, _take, loaded = recorded
    assert loaded.video_position_for(0) == 0
    assert loaded.video_position_for(10**6) is None
    assert loaded.video_position_for(-1) is None
    last = loaded.video.frame_count - 1
    assert loaded.video_position_for(last) == last
    assert loaded.video_position_for(loaded.video.frame_count) is None


# ---------------------------------------------------- movement samples


def test_multiple_samples_in_one_take_persist(recorded, repository) -> None:
    workspace, take, loaded = recorded
    first = repository.create_sample(2, 12)
    second = repository.create_sample(15, 25)
    third = repository.create_sample(28, 36)
    label(repository, first)
    label(repository, second)
    label(repository, third)
    repository.save()

    reloaded = workspace.load_samples(take)
    assert len(reloaded) == 3
    assert [s.index for s in reloaded] == [1, 2, 3]
    assert {s.exercise for s in reloaded} == {"squat"}
    assert all(s.source is SegmentSource.MANUAL for s in reloaded)


def test_bounds_are_clamped_to_the_take(recorded, repository) -> None:
    _workspace, _take, loaded = recorded
    sample = repository.create_sample(-50, loaded.frame_count + 500)
    assert sample.start_frame >= 0
    assert sample.end_frame < loaded.frame_count


def test_reversed_range_is_normalised(repository) -> None:
    sample = repository.create_sample(30, 10)
    assert sample.start_frame == 10
    assert sample.end_frame == 30


def test_samples_are_renumbered_chronologically(repository) -> None:
    later = repository.create_sample(30, 38)
    earlier = repository.create_sample(0, 10)
    assert repository.find(earlier.sample_id).index == 1
    assert repository.find(later.sample_id).index == 2


def test_overlap_between_samples_is_reported(repository) -> None:
    repository.create_sample(0, 20)
    repository.create_sample(10, 30)
    problems = repository.validation_problems()
    assert any(problem["issue"] == "overlap" for problem in problems)


def test_exclude_and_restore(repository) -> None:
    sample = repository.create_sample(0, 10)
    repository.set_sample_status(sample.sample_id, SegmentStatus.EXCLUDED)
    assert repository.readiness(repository.find(sample.sample_id)) is (
        SampleReadiness.EXCLUDED
    )
    assert repository.active_samples == ()
    repository.set_sample_status(sample.sample_id, SegmentStatus.ACTIVE)
    assert repository.find(sample.sample_id).is_active


def test_delete_removes_curation_only(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    sample = repository.create_sample(0, 10)
    repository.save()
    repository.delete_sample(sample.sample_id)
    repository.save()
    assert workspace.load_samples(take) == []
    assert workspace.take_paths(take).skeleton_stream.is_file()


def test_samples_from_markers_are_tagged_as_such(repository) -> None:
    created = repository.create_samples_from_markers([0, 15, 30], final_frame=38)
    assert len(created) == 2
    assert all(s.source is SegmentSource.OPERATOR_MARKER for s in created)


# ------------------------------------------------------- labels (level 1)


def test_readiness_requires_exercise_and_verdict(repository) -> None:
    sample = repository.create_sample(0, 20)
    assert repository.readiness(sample) is SampleReadiness.UNLABELLED

    repository.label_sample(sample.sample_id, exercise="squat")
    assert repository.readiness(repository.find(sample.sample_id)) is (
        SampleReadiness.UNLABELLED
    )

    repository.label_sample(sample.sample_id, correctness=Correctness.CORRECT)
    assert repository.readiness(repository.find(sample.sample_id)).is_ready


def test_correctness_is_binary(repository) -> None:
    """There is no third movement class the user can pick."""
    assert [c.value for c in Correctness if c.is_decided] == ["correct", "incorrect"]
    sample = label(repository, repository.create_sample(0, 20))
    assert sample.correctness.is_decided


def test_copy_label_does_not_copy_error_intervals(repository) -> None:
    """Timings belong to their own movement; pasting them would invent data."""
    source = repository.create_sample(0, 15)
    target = repository.create_sample(18, 33)
    label(repository, source, Correctness.INCORRECT)
    repository.create_error_interval(
        source.sample_id, 2, 8, error_code="diz-ice-cokuyor"
    )

    repository.copy_label_from(source.sample_id, target.sample_id)
    copied = repository.find(target.sample_id)
    assert copied.exercise == "squat"
    assert copied.correctness is Correctness.INCORRECT
    assert copied.error_intervals == []
    # ... which correctly leaves it not-yet-ready.
    assert repository.readiness(copied) is SampleReadiness.NEEDS_ERROR_INTERVAL


def test_apply_to_all_skips_excluded(repository) -> None:
    first = repository.create_sample(0, 10)
    second = repository.create_sample(12, 22)
    repository.set_sample_status(second.sample_id, SegmentStatus.EXCLUDED)
    changed = repository.apply_to_all(
        exercise="squat", correctness=Correctness.CORRECT
    )
    assert changed == 1
    assert repository.find(first.sample_id).exercise == "squat"
    assert repository.find(second.sample_id).exercise == ""


# ------------------------------------------------- error intervals (level 2)


def test_single_error_interval_makes_an_incorrect_sample_ready(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    assert repository.readiness(sample) is SampleReadiness.NEEDS_ERROR_INTERVAL

    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    assert repository.readiness(repository.find(sample.sample_id)).is_ready


def test_multiple_repeated_and_overlapping_intervals(repository) -> None:
    sample = label(repository, repository.create_sample(0, 36), Correctness.INCORRECT)
    first = repository.create_error_interval(
        sample.sample_id, 2, 12, error_code="diz-ice-cokuyor"
    )
    overlapping = repository.create_error_interval(
        sample.sample_id, 8, 20, error_code="sirt-yuvarlaniyor"
    )
    repeated = repository.create_error_interval(
        sample.sample_id, 25, 34, error_code="diz-ice-cokuyor"
    )

    sample = repository.find(sample.sample_id)
    assert len(sample.error_intervals) == 3
    # Different classes at the same time are expressed as an overlap.
    assert first.overlaps(overlapping)
    # The same class may legitimately recur later in the movement.
    assert repeated.error_code == first.error_code
    assert sample.error_codes == ("diz-ice-cokuyor", "sirt-yuvarlaniyor")
    assert repository.readiness(sample).is_ready

    at_ten = repository.intervals_at_frame(sample.sample_id, 10)
    assert {i.error_code for i in at_ten} == {"diz-ice-cokuyor", "sirt-yuvarlaniyor"}


def test_interval_is_clamped_into_its_parent(repository) -> None:
    sample = repository.create_sample(10, 30)
    interval = repository.create_error_interval(
        sample.sample_id, -100, 15, error_code="diz-ice-cokuyor"
    )
    assert interval.start_frame >= sample.start_frame
    assert interval.end_frame <= sample.end_frame

    moved = repository.update_error_interval_bounds(
        sample.sample_id, interval.interval_id, 5, 999
    )
    assert moved.start_frame >= sample.start_frame
    assert moved.end_frame <= sample.end_frame


def test_interval_without_class_blocks_readiness(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    interval = repository.create_error_interval(sample.sample_id, 5, 15)
    assert repository.readiness(repository.find(sample.sample_id)) is (
        SampleReadiness.INVALID_INTERVAL
    )

    repository.set_error_interval_class(
        sample.sample_id, interval.interval_id, "diz-ice-cokuyor"
    )
    assert repository.readiness(repository.find(sample.sample_id)).is_ready


def test_unknown_error_class_blocks_readiness(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="not-in-schema"
    )
    assert repository.readiness(repository.find(sample.sample_id)) is (
        SampleReadiness.INVALID_INTERVAL
    )


def test_interval_edit_and_delete(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    interval = repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    repository.update_error_interval_bounds(
        sample.sample_id, interval.interval_id, 7, 20
    )
    moved = repository.find(sample.sample_id).error_intervals[0]
    assert (moved.start_frame, moved.end_frame) == (7, 20)

    repository.set_error_interval_class(
        sample.sample_id, interval.interval_id, "sirt-yuvarlaniyor"
    )
    assert repository.find(sample.sample_id).error_intervals[0].error_code == (
        "sirt-yuvarlaniyor"
    )

    repository.delete_error_interval(sample.sample_id, interval.interval_id)
    assert repository.find(sample.sample_id).error_intervals == []


def test_interval_survives_a_save_reload(recorded, repository) -> None:
    workspace, take, loaded = recorded
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor", start_timestamp_ns=42
    )
    repository.save()

    fresh = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    reloaded = fresh.samples[0]
    assert len(reloaded.error_intervals) == 1
    interval = reloaded.error_intervals[0]
    assert interval.error_code == "diz-ice-cokuyor"
    assert (interval.start_frame, interval.end_frame) == (5, 15)
    assert interval.start_timestamp_ns == 42
    assert fresh.readiness(reloaded).is_ready


# --------------------------------------------- consistency between levels


def test_correct_sample_with_error_intervals_is_a_contradiction(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.CORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    readiness, problems = (
        repository.readiness(repository.find(sample.sample_id)),
        repository.problems(repository.find(sample.sample_id)),
    )
    assert readiness is SampleReadiness.CONTRADICTION
    assert any(p.code == "correct_with_errors" for p in problems)


def test_incorrect_without_interval_is_workable_but_not_ready(repository) -> None:
    """The user may keep working on it; it just is not finished."""
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    readiness = repository.readiness(sample)
    assert readiness is SampleReadiness.NEEDS_ERROR_INTERVAL
    assert not readiness.is_ready
    assert repository.ready_count == 0


def test_ready_count_matches_the_export_rule(repository) -> None:
    """The screen's "labelled" and the exporter's "eligible" are one rule."""
    from kinecapture.domain.project import is_export_ready

    good = label(repository, repository.create_sample(0, 10))
    pending = label(
        repository, repository.create_sample(12, 22), Correctness.INCORRECT
    )
    codes = repository.known_error_codes

    assert is_export_ready(repository.find(good.sample_id), known_error_codes=codes)
    assert not is_export_ready(
        repository.find(pending.sample_id), known_error_codes=codes
    )
    assert repository.ready_count == 1
    assert repository.labelled_count == repository.ready_count


# ------------------------------------- parent bounds change safely


def test_narrowing_a_sample_clamps_and_reports(repository) -> None:
    sample = label(repository, repository.create_sample(0, 36), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 2, 20, error_code="diz-ice-cokuyor"
    )
    repository.create_error_interval(
        sample.sample_id, 30, 35, error_code="sirt-yuvarlaniyor"
    )

    report = repository.update_sample_bounds(sample.sample_id, 10, 25)
    assert len(report.clamped) == 1  # the 2-20 one was trimmed to 10-20
    assert len(report.removed) == 1  # the 30-35 one fell outside entirely
    assert not report.is_lossless
    assert "Ctrl+Z" in report.message()

    survivors = repository.find(sample.sample_id).error_intervals
    assert len(survivors) == 1
    assert survivors[0].start_frame >= 10 and survivors[0].end_frame <= 25


def test_narrowing_is_undoable(repository) -> None:
    sample = label(repository, repository.create_sample(0, 36), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 30, 35, error_code="diz-ice-cokuyor"
    )
    repository.update_sample_bounds(sample.sample_id, 0, 20)
    assert repository.find(sample.sample_id).error_intervals == []

    assert repository.undo()
    restored = repository.find(sample.sample_id)
    assert len(restored.error_intervals) == 1
    assert restored.end_frame == 36


def test_widening_keeps_every_interval(repository) -> None:
    sample = label(repository, repository.create_sample(10, 20), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 12, 18, error_code="diz-ice-cokuyor"
    )
    report = repository.update_sample_bounds(sample.sample_id, 5, 30)
    assert report.is_lossless
    assert not report.changed_anything
    assert len(repository.find(sample.sample_id).error_intervals) == 1


# ------------------------------------------------------- split and merge


def test_split_distributes_intervals_and_divides_the_straddler(repository) -> None:
    sample = label(repository, repository.create_sample(0, 36), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 2, 8, error_code="diz-ice-cokuyor"
    )
    repository.create_error_interval(
        sample.sample_id, 14, 26, error_code="sirt-yuvarlaniyor"
    )  # straddles a cut at 20
    repository.create_error_interval(
        sample.sample_id, 30, 34, error_code="diz-ice-cokuyor"
    )

    head, tail = repository.split_sample(sample.sample_id, 20)
    assert head.end_frame == 19 and tail.start_frame == 20
    # Nothing was lost: the straddling interval became two halves.
    assert len(head.error_intervals) + len(tail.error_intervals) == 4
    assert all(
        head.start_frame <= i.start_frame and i.end_frame <= head.end_frame
        for i in head.error_intervals
    )
    assert all(
        tail.start_frame <= i.start_frame and i.end_frame <= tail.end_frame
        for i in tail.error_intervals
    )
    # A boundary correction is not a statement that the labels were wrong.
    assert tail.exercise == "squat"
    assert tail.correctness is Correctness.INCORRECT


def test_split_outside_range_is_refused(repository) -> None:
    sample = repository.create_sample(10, 20)
    with pytest.raises(ValidationError) as info:
        repository.split_sample(sample.sample_id, 30)
    assert info.value.code == "split_out_of_range"


def test_merge_keeps_intervals_and_records_conflicting_labels(repository) -> None:
    first = label(repository, repository.create_sample(0, 15), Correctness.INCORRECT)
    repository.create_error_interval(
        first.sample_id, 3, 9, error_code="diz-ice-cokuyor"
    )
    second = repository.create_sample(18, 33)
    repository.label_sample(
        second.sample_id, exercise="lunge", correctness=Correctness.CORRECT
    )

    report = repository.merge_samples(first.sample_id, second.sample_id)
    assert report.had_conflict
    assert report.dropped_exercise == "lunge"
    assert report.dropped_correctness == "correct"
    assert "silinmedi" in report.message()

    merged = repository.find(first.sample_id)
    assert (merged.start_frame, merged.end_frame) == (0, 33)
    assert len(merged.error_intervals) == 1
    # The losing label is preserved rather than dropped on the floor.
    history = merged.legacy["merged_from"]
    assert history[0]["exercise"] == "lunge"
    assert history[0]["correctness"] == "correct"


def test_merge_without_conflict_reports_cleanly(repository) -> None:
    first = label(repository, repository.create_sample(0, 15))
    second = repository.create_sample(18, 33)
    report = repository.merge_samples(first.sample_id, second.sample_id)
    assert not report.had_conflict
    assert "birleştirildi" in report.message()


# ----------------------------------------- error classes during labelling


def test_new_error_class_is_created_and_persisted(recorded, repository) -> None:
    workspace, _take, _loaded = recorded
    option = repository.ensure_error_class("Kalça geride kalıyor")
    assert option.code in workspace.label_schema.error_type_codes()

    # Persisted to the project file, so a restart still sees it.
    reopened = type(workspace).open(workspace.root)
    assert option.code in reopened.label_schema.error_type_codes()


def test_creating_a_near_duplicate_class_reuses_the_existing_one(repository) -> None:
    first = repository.ensure_error_class("Diz İçe Çöküyor")
    before = len(repository.workspace.label_schema.error_types)
    for variant in ("diz içe çöküyor", "  DİZ  İÇE   ÇÖKÜYOR ", "Diz içe çöküyor"):
        again = repository.ensure_error_class(variant)
        assert again.code == first.code
    assert len(repository.workspace.label_schema.error_types) == before


def test_new_class_can_be_assigned_immediately(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    interval = repository.create_error_interval(sample.sample_id, 5, 15)
    _updated, option = repository.assign_new_error_class(
        sample.sample_id, interval.interval_id, "Topuk kalkıyor"
    )
    assert repository.find(sample.sample_id).error_intervals[0].error_code == (
        option.code
    )
    assert repository.readiness(repository.find(sample.sample_id)).is_ready


def test_empty_class_name_is_refused(repository) -> None:
    with pytest.raises(ValidationError) as info:
        repository.ensure_error_class("   ")
    assert info.value.code == "error_type_name_empty"


def test_undo_reverts_the_assignment_not_the_vocabulary(repository) -> None:
    """Undo is about this take's labels; the class list is project config."""
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    interval = repository.create_error_interval(sample.sample_id, 5, 15)
    _updated, option = repository.assign_new_error_class(
        sample.sample_id, interval.interval_id, "Topuk kalkıyor"
    )

    assert repository.undo()
    assert repository.find(sample.sample_id).error_intervals[0].error_code == ""
    # The class stays defined - a picker that "adds to the list" should not
    # un-add it because the annotator changed their mind about one interval.
    assert option.code in repository.workspace.label_schema.error_type_codes()


def test_used_error_codes_reports_what_this_take_references(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    assert repository.used_error_codes() == {"diz-ice-cokuyor"}


# ------------------------------------------------------------ undo / redo


def test_undo_and_redo_across_both_levels(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    assert len(repository.find(sample.sample_id).error_intervals) == 1

    assert repository.undo()
    assert repository.find(sample.sample_id).error_intervals == []
    assert repository.redo()
    assert len(repository.find(sample.sample_id).error_intervals) == 1


def test_undo_restores_label_values(repository) -> None:
    sample = repository.create_sample(0, 10)
    repository.label_sample(sample.sample_id, exercise="squat")
    repository.label_sample(sample.sample_id, exercise="lunge")
    repository.undo()
    assert repository.find(sample.sample_id).exercise == "squat"


def test_new_edit_clears_redo(repository) -> None:
    repository.create_sample(0, 10)
    repository.undo()
    assert repository.can_redo
    repository.create_sample(20, 30)
    assert not repository.can_redo


def test_undo_on_empty_history_is_false(repository) -> None:
    assert not repository.undo()
    assert not repository.redo()


# ---------------------------------------------------------------- autosave


def test_save_if_dirty_only_writes_when_needed(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    assert not repository.save_if_dirty()
    repository.create_sample(0, 10)
    assert repository.save_if_dirty()
    assert not repository.save_if_dirty()
    assert workspace.take_paths(take).segments.is_file()


def test_interval_edits_mark_the_repository_dirty(repository) -> None:
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.save()
    assert not repository.is_dirty
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    assert repository.is_dirty


def test_labelling_never_touches_take_metadata(recorded, repository) -> None:
    workspace, take, _loaded = recorded
    before = workspace.take_paths(take).metadata.read_bytes()
    sample = label(repository, repository.create_sample(0, 30), Correctness.INCORRECT)
    repository.create_error_interval(
        sample.sample_id, 5, 15, error_code="diz-ice-cokuyor"
    )
    repository.save()
    assert workspace.take_paths(take).metadata.read_bytes() == before
