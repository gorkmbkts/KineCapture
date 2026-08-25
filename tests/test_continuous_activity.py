"""Labelling and exporting a whole take, not just its repetitions.

The distinction these tests defend is the one the whole continuous layer rests
on: **unlabelled time is not background**. A model that learns otherwise learns
the annotator's attention span. Everything else here - overlap rules, the
sample link, the frame-level targets - exists to keep that distinction true all
the way from the timeline to the ``.npz``.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.core.errors import ValidationError
from kinecapture.core.jsonio import read_json
from kinecapture.dataset.index import DatasetIndex
from kinecapture.domain.activity import (
    ActivityInterval,
    ActivityState,
    ContinuousReadiness,
    UNLABELLED_CODE,
    evaluate_continuous,
    find_overlaps,
    measure_coverage,
    unlabelled_gaps,
)
from kinecapture.domain.enums import Correctness, TakeQuality
from kinecapture.export import continuous as continuous_contract
from kinecapture.export.release import ExportOptions, ReleaseBuilder
from kinecapture.playback.take_reader import load_take
from tests.test_export import _record_and_label


@pytest.fixture
def take_and_repo(workspace, session):
    take = _record_and_label(workspace, session, frames=60, reps=1)
    loaded = load_take(workspace, take, with_video=False)
    repository = AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count, annotator="pytest"
    )
    return workspace, take, repository, loaded.frame_count


# ------------------------------------------------------------- the domain


def test_state_codes_are_fixed_and_unlabelled_is_not_one_of_them() -> None:
    codes = {state.code for state in ActivityState}
    assert codes == {0, 1, 2, 3}
    assert UNLABELLED_CODE not in codes
    assert UNLABELLED_CODE == -1

    mapping = continuous_contract.array_contract(store_error_arrays=True)["activity"]
    assert mapping["unlabelled_code"] == UNLABELLED_CODE
    assert "background sayılmaz" in mapping["unlabelled_note"]


def test_only_a_target_exercise_interval_may_carry_an_exercise() -> None:
    good = ActivityInterval.create(
        0, 9, state=ActivityState.TARGET_EXERCISE, exercise="squat"
    )
    assert good.problems() == []

    missing = ActivityInterval.create(0, 9, state=ActivityState.TARGET_EXERCISE)
    assert any("egzersiz türü" in issue for issue in missing.problems())

    stray = ActivityInterval.create(0, 9, state=ActivityState.BACKGROUND)
    stray.exercise = "squat"
    assert any("Yalnız hedef egzersiz" in issue for issue in stray.problems())


def test_coverage_counts_gaps_without_filling_them() -> None:
    intervals = [
        ActivityInterval.create(0, 9, state=ActivityState.BACKGROUND),
        ActivityInterval.create(20, 29, state=ActivityState.OTHER_ACTIVITY),
    ]
    coverage = measure_coverage(intervals, 40)
    assert coverage.labelled_frames == 20
    assert coverage.unlabelled_frames == 20
    assert coverage.per_state["background"] == 10
    assert unlabelled_gaps(intervals, 40) == [(10, 19), (30, 39)]


def test_overlapping_states_are_a_contradiction() -> None:
    intervals = [
        ActivityInterval.create(0, 20, state=ActivityState.BACKGROUND),
        ActivityInterval.create(15, 30, state=ActivityState.OTHER_ACTIVITY),
    ]
    assert find_overlaps(intervals)
    readiness, _coverage = evaluate_continuous(intervals, 40)
    assert readiness is ContinuousReadiness.OVERLAPPING


def test_full_coverage_is_only_required_when_asked() -> None:
    intervals = [ActivityInterval.create(0, 9, state=ActivityState.BACKGROUND)]
    assert evaluate_continuous(intervals, 40)[0] is ContinuousReadiness.READY
    assert (
        evaluate_continuous(intervals, 40, require_full_coverage=True)[0]
        is ContinuousReadiness.PARTIAL_COVERAGE
    )


# ------------------------------------------------------- the repository


def test_activity_crud_round_trips_through_the_sidecar(take_and_repo) -> None:
    workspace, take, repository, frames = take_and_repo
    repository.create_activity_interval(0, 9, state=ActivityState.BACKGROUND)
    repository.create_activity_interval(10, 14, state=ActivityState.TRANSITION)
    repository.create_activity_interval(
        15, 34, state=ActivityState.TARGET_EXERCISE, exercise="squat"
    )
    repository.save()

    reopened = AnnotationRepository(workspace, take, frame_count=frames)
    states = [i.state for i in reopened.activity_intervals]
    assert states == [
        ActivityState.BACKGROUND,
        ActivityState.TRANSITION,
        ActivityState.TARGET_EXERCISE,
    ]
    assert reopened.activity_intervals[2].exercise == "squat"
    # The movement samples came back untouched alongside them.
    assert len(reopened.samples) == len(repository.samples)


def test_an_older_sidecar_opens_without_being_rewritten(take_and_repo) -> None:
    workspace, take, repository, frames = take_and_repo
    repository.save()
    path = workspace.take_paths(take).segments
    before = path.read_bytes()

    document = read_json(path)
    assert "activity_intervals" not in document  # nothing was labelled yet

    reopened = AnnotationRepository(workspace, take, frame_count=frames)
    assert reopened.activity_intervals == ()
    assert path.read_bytes() == before


def test_overlapping_creation_is_trimmed_or_refused(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    repository.create_activity_interval(10, 19, state=ActivityState.BACKGROUND)

    trimmed = repository.create_activity_interval(
        15, 29, state=ActivityState.OTHER_ACTIVITY
    )
    assert (trimmed.start_frame, trimmed.end_frame) == (20, 29)

    with pytest.raises(ValidationError) as excinfo:
        repository.create_activity_interval(12, 16, state=ActivityState.TRANSITION)
    assert excinfo.value.code == "activity_span_occupied"


def test_moving_an_interval_onto_a_neighbour_is_refused(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    first = repository.create_activity_interval(0, 9, state=ActivityState.BACKGROUND)
    repository.create_activity_interval(10, 19, state=ActivityState.TRANSITION)
    with pytest.raises(ValidationError) as excinfo:
        repository.update_activity_bounds(first.interval_id, 0, 15)
    assert excinfo.value.code == "activity_overlap"


def test_unlabelled_time_never_becomes_background_by_itself(take_and_repo) -> None:
    _workspace, _take, repository, frames = take_and_repo
    repository.create_activity_interval(0, 9, state=ActivityState.BACKGROUND)

    with pytest.raises(ValidationError) as excinfo:
        repository.fill_gaps_with_background()
    assert excinfo.value.code == "background_fill_needs_confirmation"
    assert repository.activity_coverage().unlabelled_frames == frames - 10

    created = repository.fill_gaps_with_background(confirmed=True)
    assert created
    assert repository.activity_coverage().is_complete
    # And it only touched the gaps, not the existing label.
    assert all(i.state is ActivityState.BACKGROUND for i in created)


def test_a_linked_interval_follows_its_movement_sample(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    sample = repository.samples[0]
    interval = repository.create_activity_interval(
        sample.start_frame,
        sample.end_frame,
        state=ActivityState.TARGET_EXERCISE,
        exercise="squat",
    )
    repository.link_activity_to_sample(interval.interval_id, sample.sample_id)

    repository.update_sample_bounds(
        sample.sample_id, sample.start_frame + 3, sample.end_frame - 2
    )
    linked = repository.find_activity(interval.interval_id)
    moved = repository.find(sample.sample_id)
    assert (linked.start_frame, linked.end_frame) == (
        moved.start_frame,
        moved.end_frame,
    )

    # The link makes the sample the single source of that boundary.
    with pytest.raises(ValidationError) as excinfo:
        repository.update_activity_bounds(interval.interval_id, 0, 5)
    assert excinfo.value.code == "activity_bounds_linked"


def test_activity_edits_participate_in_undo(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    interval = repository.create_activity_interval(
        0, 9, state=ActivityState.BACKGROUND
    )
    assert len(repository.activity_intervals) == 1
    repository.set_activity_state(interval.interval_id, ActivityState.TRANSITION)
    assert repository.find_activity(interval.interval_id).state is (
        ActivityState.TRANSITION
    )

    assert repository.undo()
    assert repository.find_activity(interval.interval_id).state is (
        ActivityState.BACKGROUND
    )
    assert repository.undo()
    assert repository.activity_intervals == ()
    assert repository.redo()
    assert len(repository.activity_intervals) == 1


def test_undo_keeps_both_layers_in_step(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    before_samples = len(repository.samples)
    repository.create_activity_interval(0, 9, state=ActivityState.BACKGROUND)
    repository.create_sample(40, 49)
    assert len(repository.samples) == before_samples + 1

    repository.undo()  # undoes the sample, not the activity interval
    assert len(repository.samples) == before_samples
    assert len(repository.activity_intervals) == 1


def test_creating_activity_from_samples_mirrors_their_bounds(take_and_repo) -> None:
    _workspace, _take, repository, _frames = take_and_repo
    created = repository.activity_from_samples()
    assert created
    for interval in created:
        sample = repository.find(interval.linked_sample_id)
        assert (interval.start_frame, interval.end_frame) == (
            sample.start_frame,
            sample.end_frame,
        )
        assert interval.state is ActivityState.TARGET_EXERCISE


# --------------------------------------------------------------- export


def _label_timeline(repository, frames: int, *, with_exercise: bool = True):
    """A realistic strip: some waiting, a transition, the exercise, then a gap.

    The exercise stretch is linked to the movement sample, so its bounds are
    the sample's, and the surrounding labels are placed around it rather than
    over it - activity states are mutually exclusive.
    """
    sample = repository.samples[0]
    if with_exercise:
        interval = repository.create_activity_interval(
            sample.start_frame,
            sample.end_frame,
            state=ActivityState.TARGET_EXERCISE,
            exercise="squat",
        )
        repository.link_activity_to_sample(interval.interval_id, sample.sample_id)
    after = sample.end_frame + 1
    repository.create_activity_interval(
        after, after + 3, state=ActivityState.TRANSITION
    )
    repository.create_activity_interval(
        after + 4, after + 13, state=ActivityState.BACKGROUND
    )
    repository.create_activity_interval(
        frames - 5, frames - 1, state=ActivityState.OTHER_ACTIVITY
    )
    repository.save()


def _build(workspace, **options):
    index = DatasetIndex(workspace).refresh(force=True)
    settings = ExportOptions(include_synthetic=True, **options)
    return ReleaseBuilder(workspace, index, settings).build()


def test_default_export_still_produces_only_movement_samples(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace)

    assert result.continuous_count == 0
    assert result.sample_count >= 1
    assert not (result.path / "continuous").exists()
    assert not (result.path / "activity_spec.json").exists()
    manifest = read_json(result.path / "manifest.json")
    assert manifest["dataset_modes"]["continuous_activity"] is False


def test_continuous_export_writes_one_example_per_take(take_and_repo) -> None:
    workspace, take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)

    assert result.continuous_count == 1
    assert result.validation_passed
    manifest = read_json(result.path / "manifest.json")
    entry = manifest["continuous_samples"][0]
    assert entry["num_frames"] == frames
    assert entry["split_group_id"] == take.take_id

    payload = np.load(result.path / entry["file"])
    assert payload["joints_xyz"].shape[0] == frames
    for key in (
        "activity_state_code",
        "activity_label_mask",
        "exercise_active",
        "exercise_start_target",
        "exercise_end_target",
        "subject_present_mask",
        "error_label_mask",
        "correctness_code",
    ):
        assert payload[key].shape[0] == frames


def test_unlabelled_frames_stay_out_of_every_class(take_and_repo) -> None:
    """The single most damaging thing this contract could get wrong."""
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)
    manifest = read_json(result.path / "manifest.json")
    payload = np.load(result.path / manifest["continuous_samples"][0]["file"])

    codes = payload["activity_state_code"]
    mask = payload["activity_label_mask"]
    assert codes.dtype == np.int16
    assert np.all(codes[~mask] == UNLABELLED_CODE)
    assert np.all(codes[mask] != UNLABELLED_CODE)
    assert (~mask).any(), "this fixture is supposed to leave a gap"
    # Background is a real class with its own code; the gap is not it.
    assert (codes == ActivityState.BACKGROUND.code).any()


def test_start_and_end_targets_match_the_interval_bounds(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)
    manifest = read_json(result.path / "manifest.json")
    entry = manifest["continuous_samples"][0]
    payload = np.load(result.path / entry["file"])

    exercises = [
        item
        for item in entry["activity_intervals"]
        if item["state"] == ActivityState.TARGET_EXERCISE.value
    ]
    assert exercises
    starts = np.flatnonzero(payload["exercise_start_target"]).tolist()
    ends = np.flatnonzero(payload["exercise_end_target"]).tolist()
    assert starts == [item["start_position"] for item in exercises]
    assert ends == [item["end_position"] for item in exercises]
    assert payload["exercise_active"][starts[0] : ends[0] + 1].all()


def test_a_one_frame_exercise_sets_start_and_end_together() -> None:
    targets = continuous_contract.build_targets(
        frames=10,
        intervals=[
            ActivityInterval.create(
                4, 4, state=ActivityState.TARGET_EXERCISE, exercise="squat"
            )
        ],
        samples=[],
        exercise_index={"squat": 0},
        error_index={},
    )
    assert targets.exercise_start_target[4] == 1
    assert targets.exercise_end_target[4] == 1
    assert targets.exercise_active.sum() == 1


def test_error_labels_apply_only_where_a_judgement_exists(take_and_repo) -> None:
    """"No error here" and "nobody was asked" must stay distinguishable."""
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)
    manifest = read_json(result.path / "manifest.json")
    payload = np.load(result.path / manifest["continuous_samples"][0]["file"])

    sample = repository.samples[0]
    mask = payload["error_label_mask"]
    assert mask[sample.start_frame : sample.end_frame + 1].all()
    assert not mask[: sample.start_frame].any()

    correctness = payload["correctness_code"]
    assert (correctness[~mask] == continuous_contract.CORRECTNESS_NOT_APPLICABLE).all()
    assert set(np.unique(correctness[mask]).tolist()) <= {0, 1}


def test_a_take_with_no_exercise_at_all_is_a_valid_negative(
    workspace, session
) -> None:
    """A recording of somebody just standing around is exactly what is needed."""
    take = _record_and_label(workspace, session, frames=40, reps=1)
    loaded = load_take(workspace, take, with_video=False)
    repository = AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count
    )
    # Discard the repetitions entirely and label the whole take as background.
    for sample in list(repository.samples):
        repository.delete_sample(sample.sample_id)
    repository.create_activity_interval(
        0, loaded.frame_count - 1, state=ActivityState.BACKGROUND
    )
    repository.save()

    result = _build(
        workspace, export_movement_samples=False, export_continuous=True
    )
    assert result.continuous_count == 1
    assert result.sample_count == 0
    assert result.validation_passed

    manifest = read_json(result.path / "manifest.json")
    entry = manifest["continuous_samples"][0]
    assert entry["activity_summary"]["has_target_exercise"] is False
    payload = np.load(result.path / entry["file"])
    assert not payload["exercise_active"].any()
    assert payload["activity_label_mask"].all()


def test_both_datasets_can_be_published_side_by_side(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_movement_samples=True, export_continuous=True)

    assert result.sample_count >= 1
    assert result.continuous_count == 1
    manifest = read_json(result.path / "manifest.json")
    assert manifest["dataset_modes"]["movement_samples"] is True
    assert manifest["dataset_modes"]["continuous_activity"] is True
    # Two separate contracts, two separate directories.
    assert (result.path / "samples").is_dir()
    assert (result.path / "continuous").is_dir()
    spec = read_json(result.path / "activity_spec.json")
    assert spec["contract"]["arrays"]["activity_state_code"]
    assert spec["split_grouping"]


def test_a_take_with_no_activity_labels_is_excluded_with_a_reason(
    take_and_repo,
) -> None:
    workspace, _take, _repository, _frames = take_and_repo
    result = _build(workspace, export_continuous=True)
    excluded = read_json(result.path / "excluded.json")
    reasons = {item["reason"] for item in excluded["items"]}
    assert "continuous_not_annotated" in reasons


def test_requiring_full_coverage_blocks_a_partial_timeline(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)  # deliberately leaves a gap

    result = _build(workspace, export_continuous=True)
    assert result.continuous_count == 1

    strict = _build(
        workspace, export_continuous=True, require_full_activity_coverage=True
    )
    assert strict.continuous_count == 0
    excluded = read_json(strict.path / "excluded.json")
    assert any(
        item["reason"] == "continuous_partial_coverage" for item in excluded["items"]
    )


def test_the_raw_archive_is_referenced_not_copied(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)
    manifest = read_json(result.path / "manifest.json")
    source = manifest["continuous_samples"][0]["raw_source"]

    assert source["copied_into_release"] is False
    assert source["rgbd_archive"] == "raw/rgbd/"
    assert source["checksums"]
    # No gigabytes of depth were duplicated into the release.
    assert not (result.path / "raw").exists()


def test_fingerprint_moves_when_the_activity_timeline_changes(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    first = read_json(
        _build(workspace, export_continuous=True).path / "dataset_fingerprint.json"
    )["fingerprint"]

    interval = [
        i
        for i in repository.activity_intervals
        if i.state is ActivityState.BACKGROUND
    ][0]
    repository.set_activity_state(interval.interval_id, ActivityState.OTHER_ACTIVITY)
    repository.save()

    second = read_json(
        _build(workspace, export_continuous=True).path / "dataset_fingerprint.json"
    )["fingerprint"]
    assert first != second


def test_selecting_no_dataset_mode_is_refused() -> None:
    from kinecapture.core.errors import ExportError

    with pytest.raises(ExportError) as excinfo:
        ExportOptions(export_movement_samples=False, export_continuous=False)
    assert excinfo.value.code == "no_dataset_mode"


def test_features_run_on_a_continuous_example_too(take_and_repo) -> None:
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(
        workspace,
        export_continuous=True,
        feature_ids=("joint_velocity", "joint_angles", "validity_masks"),
    )
    manifest = read_json(result.path / "manifest.json")
    payload = np.load(result.path / manifest["continuous_samples"][0]["file"])
    assert payload["joint_velocity_xyz"].shape[0] == frames
    assert payload["joint_angles_rad"].shape[0] == frames
    assert payload["joint_valid_mask"].shape[0] == frames


def test_derivatives_do_not_cross_a_subject_absent_gap() -> None:
    """A velocity computed across "the person was not there" would be fiction."""
    from kinecapture.features.compute import FeatureContext, compute_features
    from kinecapture.visualization.skeleton_spec import MOCK_SKELETON

    frames = 9
    joints = np.zeros((frames, MOCK_SKELETON.num_joints, 3), dtype=np.float32)
    joints[:, :, 0] = np.arange(frames, dtype=np.float32)[:, None] * 0.01
    joints[4] = np.nan  # subject absent for one frame
    timestamps = (np.arange(frames, dtype=np.int64) * 33_333_333)

    context = FeatureContext(
        spec=MOCK_SKELETON,
        joints=joints,
        timestamps_ns=timestamps,
        frame_indices=np.arange(frames, dtype=np.int64),
        target_fps=30.0,
    )
    result = compute_features(context, ["joint_velocity"])
    mask = result.arrays["joint_velocity_valid_mask"]
    # The absent frame has no velocity of its own, and neither neighbour may
    # differentiate across it.
    assert not mask[3].any()
    assert not mask[4].any()
    assert not mask[5].any()
    assert np.isnan(result.arrays["joint_velocity_xyz"][4]).all()
    # Frames well away from the hole are unaffected.
    assert mask[1].all() and mask[7].all()


def test_a_pre_lock_take_is_marked_legacy_not_passed_off_as_locked(
    take_and_repo,
) -> None:
    """An old recording has no authoritative subject, and the release says so."""
    workspace, _take, repository, frames = take_and_repo
    _label_timeline(repository, frames)
    result = _build(workspace, export_continuous=True)
    manifest = read_json(result.path / "manifest.json")
    subject = manifest["continuous_samples"][0]["subject"]

    assert subject["has_association"] is False
    assert subject["legacy_active_body"] is True
    assert "uydurulmamıştır" in subject["legacy_note"]

    report = read_json(result.path / "validation_report.json")
    assert any("kişi kilidinden ÖNCE" in warning for warning in report["warnings"])
    # The pose is still real - it just is not an authoritative association.
    payload = np.load(result.path / manifest["continuous_samples"][0]["file"])
    assert np.isfinite(payload["joints_xyz"]).any()
    assert payload["subject_present_mask"].any()


def test_a_locked_take_exports_the_locked_subject(workspace, session) -> None:
    """With a lock, the pose is the chosen person's and is marked as such."""
    import time

    from kinecapture.capture.service import CaptureService
    from tests.conftest import paced_backend

    service = CaptureService(paced_backend())
    service.connect()
    service.start_preview()
    deadline = time.time() + 10
    packet = service.peek_frame()
    while (packet is None or not packet.bodies) and time.time() < deadline:
        time.sleep(0.01)
        packet = service.peek_frame()
    service.select_subject(packet.bodies[0])

    take = service.start_recording(workspace, session, exercise="squat")
    deadline = time.time() + 15
    while service.recorded_frame_count < 30 and time.time() < deadline:
        time.sleep(0.005)
    take = service.stop_recording()
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    frames = take.metrics.frames_written
    repository = AnnotationRepository(workspace, take, frame_count=frames)
    repository.create_activity_interval(
        0, frames - 1, state=ActivityState.BACKGROUND
    )
    repository.save()

    result = _build(
        workspace, export_movement_samples=False, export_continuous=True
    )
    manifest = read_json(result.path / "manifest.json")
    subject = manifest["continuous_samples"][0]["subject"]
    assert subject["has_association"] is True
    assert subject.get("legacy_active_body") is False
    assert subject["coverage"] == pytest.approx(1.0)
    assert subject["distinct_tracking_ids"]

    payload = np.load(result.path / manifest["continuous_samples"][0]["file"])
    assert payload["subject_present_mask"].all()
    assert (payload["subject_source_tracking_id"] >= 0).all()
