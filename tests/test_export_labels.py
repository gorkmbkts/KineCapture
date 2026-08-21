"""The export contract for the two-level label model.

What a future temporal-localisation model consumes must be unambiguous, so
these tests pin the parts a consumer would otherwise have to guess: that the
relative interval bounds really index the exported array, that the per-frame
target agrees with the interval list, that class indices are stable, and that
validation and the fingerprint actually notice when any of it changes.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import ExportError
from kinecapture.core.jsonio import read_json
from kinecapture.dataset.index import DatasetIndex
from kinecapture.domain.enums import Correctness
from kinecapture.domain.enums import TakeQuality
from kinecapture.export.release import ExportOptions, ReleaseBuilder
from kinecapture.playback.take_reader import load_take
from tests.conftest import paced_backend, record_take

CLASS_A = "diz-ice-cokuyor"
CLASS_B = "sirt-yuvarlaniyor"


@pytest.fixture
def project(workspace, session):
    """A take with three movements: correct, incorrect-with-overlaps, correct."""
    schema = workspace.label_schema
    schema.add_exercise("Squat")
    schema.add_error_type("Diz içe çöküyor")
    schema.add_error_type("Sırt yuvarlanıyor")
    workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=120, exercise="squat")
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    n = loaded.frame_count
    repo = AnnotationRepository(workspace, take, frame_count=n, annotator="pytest")

    first = repo.create_sample(2, n // 3)
    repo.label_sample(
        first.sample_id, exercise="squat", correctness=Correctness.CORRECT
    )

    second = repo.create_sample(n // 3 + 4, 2 * n // 3)
    repo.label_sample(
        second.sample_id, exercise="squat", correctness=Correctness.INCORRECT
    )
    base = second.start_frame
    repo.create_error_interval(second.sample_id, base + 3, base + 14, error_code=CLASS_A)
    # Overlaps the first, expressing two errors at the same moment.
    repo.create_error_interval(second.sample_id, base + 10, base + 22, error_code=CLASS_B)
    # The same class again later in the movement.
    repo.create_error_interval(
        second.sample_id, second.end_frame - 9, second.end_frame - 2, error_code=CLASS_A
    )

    third = repo.create_sample(2 * n // 3 + 4, n - 3)
    repo.label_sample(
        third.sample_id, exercise="squat", correctness=Correctness.CORRECT
    )
    repo.save()
    return workspace, take


@pytest.fixture
def release(project):
    workspace, _take = project
    index = DatasetIndex(workspace).refresh()
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()
    return workspace, result


def localised_entry(manifest: dict) -> dict:
    return max(manifest["samples"], key=lambda e: len(e["error_intervals"]))


# --------------------------------------------------------------- structure


def test_each_movement_becomes_one_sample(release) -> None:
    _workspace, result = release
    assert result.sample_count == 3
    assert result.error_interval_count == 3
    assert result.validation_passed


def test_time_dimension_comes_from_the_movement_bounds(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    for entry in manifest["samples"]:
        span = entry["end_position"] - entry["start_position"] + 1
        assert entry["num_frames"] == span, "inclusive bounds must match T"
        with np.load(result.path / entry["file"]) as payload:
            assert payload["joints_xyz"].shape[0] == span


def test_sample_carries_exercise_and_binary_verdict(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    for entry in manifest["samples"]:
        assert entry["exercise"] == "squat"
        assert entry["correctness"] in ("correct", "incorrect")


def test_movement_phase_is_gone_from_the_contract(release) -> None:
    """The redesign removed it; nothing may quietly still emit it."""
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    mapping = read_json(result.path / "label_mapping.json")
    assert "movement_phases" not in mapping
    for entry in manifest["samples"]:
        assert "movement_phase" not in entry
        for interval in entry["error_intervals"]:
            assert "movement_phase" not in interval
    # And the manifest says so explicitly, so a consumer is not left guessing.
    assert "hareket fazı" in manifest["label_contract"]["movement_phase"].lower()


# ------------------------------------------------------- interval geometry


def test_relative_bounds_index_the_exported_array(release) -> None:
    """The whole point: rel bounds must slice joints_xyz correctly."""
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)

    with np.load(result.path / entry["file"]) as payload:
        joints = payload["joints_xyz"]

    for interval in entry["error_intervals"]:
        start, end = interval["relative_start"], interval["relative_end"]
        assert 0 <= start <= end < joints.shape[0]
        # Absolute and relative describe the same span.
        assert interval["start_position"] - entry["start_position"] == start
        assert interval["end_position"] - entry["start_position"] == end
        # Inclusive on both ends.
        assert interval["num_frames"] == end - start + 1
        assert joints[start : end + 1].shape[0] == interval["num_frames"]


def test_intervals_carry_camera_frames_and_timestamps(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)

    with np.load(result.path / entry["file"]) as payload:
        camera_frames = payload["frame_indices"]
        timestamps = payload["camera_timestamps_ns"]

    for interval in entry["error_intervals"]:
        start, end = interval["relative_start"], interval["relative_end"]
        assert interval["start_camera_frame"] == int(camera_frames[start])
        assert interval["end_camera_frame"] == int(camera_frames[end])
        assert interval["start_timestamp_ns"] == int(timestamps[start])
        assert interval["end_timestamp_ns"] == int(timestamps[end])


def test_interval_array_matches_the_manifest(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)

    with np.load(result.path / entry["file"]) as payload:
        stored = payload["error_intervals"]

    assert stored.dtype == np.int32
    assert stored.shape == (len(entry["error_intervals"]), 3)
    for row, interval in zip(stored, entry["error_intervals"]):
        assert int(row[0]) == interval["class_index"]
        assert int(row[1]) == interval["relative_start"]
        assert int(row[2]) == interval["relative_end"]


def test_per_frame_target_agrees_with_the_intervals(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    mapping = read_json(result.path / "label_mapping.json")
    entry = localised_entry(manifest)
    classes = mapping["error_types"]["classes"]

    with np.load(result.path / entry["file"]) as payload:
        target = payload["error_multi_hot"]

    assert target.dtype == np.uint8
    assert target.shape == (entry["num_frames"], len(classes))

    expected = np.zeros_like(target)
    for interval in entry["error_intervals"]:
        column = mapping["error_types"]["code_to_index"][interval["error_code"]]
        expected[interval["relative_start"] : interval["relative_end"] + 1, column] = 1
    np.testing.assert_array_equal(target, expected)


def test_overlapping_classes_light_up_together(release) -> None:
    """Two errors at once is exactly two columns set on the same frame."""
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)
    with np.load(result.path / entry["file"]) as payload:
        target = payload["error_multi_hot"]
    assert (target.sum(axis=1) > 1).any(), "no frame carries two simultaneous classes"


def test_the_same_class_can_repeat_in_one_sample(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)
    codes = [i["error_code"] for i in entry["error_intervals"]]
    assert codes.count(CLASS_A) == 2


def test_correct_samples_carry_no_intervals(release) -> None:
    _workspace, result = release
    manifest = read_json(result.path / "manifest.json")
    for entry in manifest["samples"]:
        if entry["correctness"] == "correct":
            assert entry["error_intervals"] == []
            assert not entry["has_error_localisation"]


# ------------------------------------------------------------ class mapping


def test_error_class_mapping_is_stable_and_documented(release) -> None:
    _workspace, result = release
    mapping = read_json(result.path / "label_mapping.json")
    errors = mapping["error_types"]
    assert errors["classes"] == sorted([CLASS_A, CLASS_B])
    assert errors["code_to_index"] == {
        code: index for index, code in enumerate(sorted([CLASS_A, CLASS_B]))
    }
    assert errors["labels"][CLASS_A] == "Diz içe çöküyor"
    assert "code_to_index" in errors["note"]


def test_a_new_class_does_not_renumber_export_indices_arbitrarily(project) -> None:
    """Indices come from sorted codes, so they are reproducible."""
    workspace, _take = project
    schema = workspace.label_schema
    schema.add_error_type("Zzz son sınıf")
    workspace.save_label_schema(schema)

    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()
    mapping = read_json(result.path / "label_mapping.json")
    # The pre-existing classes keep their relative order.
    codes = mapping["error_types"]["classes"]
    assert codes.index(CLASS_A) < codes.index(CLASS_B) < codes.index("zzz-son-sinif")


# -------------------------------------------------------------- validation


def test_validation_reports_interval_statistics(release) -> None:
    _workspace, result = release
    report = read_json(result.path / "validation_report.json")
    assert report["passed"]
    assert report["error_interval_count"] == 3
    assert report["samples_with_localisation"] == 1
    checks = {c["check"]: c["passed"] for c in report["checks"]}
    assert checks["error_interval_bounds"]
    assert checks["correctness_consistency"]


def _corrupt_sidecar(workspace, take, mutate):
    """Damage a stored label the way a hand-edited sidecar would.

    Goes around the repository deliberately: the repository would refuse, and
    the point is to prove the exporter defends itself against a file it did not
    write.
    """
    repo = AnnotationRepository(workspace, take)
    target = next(s for s in repo.samples if s.error_intervals)
    mutate(target)
    workspace.save_samples(take, repo.samples)
    return target


def test_a_sample_with_a_stranded_interval_is_rejected_whole(project) -> None:
    """Dropping just the bad interval would mislabel the movement.

    If an interval escapes its parent, exporting the sample without it would
    tell a model "no error here" for a span the annotator did mark. So the
    whole sample is withheld, with the reason recorded.
    """
    workspace, take = project

    def strand(sample):
        sample.error_intervals[0].start_frame = sample.end_frame + 50
        sample.error_intervals[0].end_frame = sample.end_frame + 60

    _corrupt_sidecar(workspace, take, strand)

    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()

    excluded = read_json(result.path / "excluded.json")
    entry = next(
        item for item in excluded["items"] if item["reason"] == "sample_invalid_interval"
    )
    assert "dışında" in entry["message"]
    # The clean movements still make it, and the release is valid.
    assert result.sample_count == 2
    assert read_json(result.path / "validation_report.json")["passed"]


def test_a_sample_with_an_unknown_class_is_rejected_whole(project) -> None:
    workspace, take = project

    def reclassify(sample):
        sample.error_intervals[0].error_code = "silinmis-sinif"

    _corrupt_sidecar(workspace, take, reclassify)

    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()
    excluded = read_json(result.path / "excluded.json")
    entry = next(
        item for item in excluded["items"] if item["reason"] == "sample_invalid_interval"
    )
    assert "silinmis-sinif" in entry["message"]
    assert result.sample_count == 2


def test_interval_guards_still_apply_when_unready_is_forced(project) -> None:
    """With include_unready on, per-interval guards are the last line."""
    workspace, take = project

    def strand(sample):
        sample.error_intervals[0].start_frame = sample.end_frame + 50
        sample.error_intervals[0].end_frame = sample.end_frame + 60

    _corrupt_sidecar(workspace, take, strand)

    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace,
        index,
        ExportOptions(include_synthetic=True, include_unready=True),
    ).build()

    excluded = read_json(result.path / "excluded.json")
    reasons = {item["reason"] for item in excluded["items"]}
    assert "interval_outside_sample" in reasons

    # The sample is exported, but only with the intervals that survived.
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)
    assert len(entry["error_intervals"]) == 2
    for interval in entry["error_intervals"]:
        assert 0 <= interval["relative_start"] <= interval["relative_end"]
        assert interval["relative_end"] < entry["num_frames"]


def test_a_take_filtered_out_says_why(project) -> None:
    workspace, _take = project
    index = DatasetIndex(workspace).refresh(force=True)
    # Synthetic takes are off by default, so the only take is filtered out.
    with pytest.raises(ExportError) as info:
        ReleaseBuilder(workspace, index, ExportOptions()).build()
    excluded = info.value.details["excluded"]
    assert any(item["reason"] == "take_synthetic_excluded" for item in excluded)


def test_unready_samples_are_excluded_by_default(workspace, session) -> None:
    """The release contains exactly what the screen calls ready."""
    schema = workspace.label_schema
    schema.add_exercise("Squat")
    workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=40)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    repo = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    pending = repo.create_sample(2, 20)
    # Incorrect but never localised: workable, not finished.
    repo.label_sample(
        pending.sample_id, exercise="squat", correctness=Correctness.INCORRECT
    )
    repo.save()
    assert repo.ready_count == 0

    index = DatasetIndex(workspace).refresh(force=True)
    with pytest.raises(ExportError) as info:
        ReleaseBuilder(
            workspace, index, ExportOptions(include_synthetic=True)
        ).build()
    assert info.value.code == "export_empty"


# ------------------------------------------------------------- fingerprint


def _fingerprint(workspace) -> str:
    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()
    return read_json(result.path / "dataset_fingerprint.json")["fingerprint"]


def test_fingerprint_is_stable_for_identical_content(project) -> None:
    workspace, _take = project
    assert _fingerprint(workspace) == _fingerprint(workspace)


def test_fingerprint_changes_when_an_interval_moves(project) -> None:
    workspace, take = project
    before = _fingerprint(workspace)
    repo = AnnotationRepository(workspace, take)
    target = next(s for s in repo.samples if s.error_intervals)
    interval = target.sorted_intervals()[0]
    repo.update_error_interval_bounds(
        target.sample_id, interval.interval_id,
        interval.start_frame + 1, interval.end_frame,
    )
    repo.save()
    assert _fingerprint(workspace) != before


def test_fingerprint_changes_when_an_interval_is_reclassified(project) -> None:
    workspace, take = project
    before = _fingerprint(workspace)
    repo = AnnotationRepository(workspace, take)
    target = next(s for s in repo.samples if s.error_intervals)
    interval = target.sorted_intervals()[0]
    repo.set_error_interval_class(target.sample_id, interval.interval_id, CLASS_B)
    repo.save()
    assert _fingerprint(workspace) != before


def test_fingerprint_changes_when_an_interval_is_deleted(project) -> None:
    workspace, take = project
    before = _fingerprint(workspace)
    repo = AnnotationRepository(workspace, take)
    target = next(s for s in repo.samples if s.error_intervals)
    repo.delete_error_interval(
        target.sample_id, target.sorted_intervals()[-1].interval_id
    )
    repo.save()
    assert _fingerprint(workspace) != before


def test_fingerprint_changes_when_an_interval_is_added(project) -> None:
    workspace, take = project
    before = _fingerprint(workspace)
    repo = AnnotationRepository(workspace, take)
    target = next(s for s in repo.samples if s.error_intervals)
    repo.create_error_interval(
        target.sample_id,
        target.start_frame + 1,
        target.start_frame + 2,
        error_code=CLASS_B,
    )
    repo.save()
    assert _fingerprint(workspace) != before


def test_target_arrays_can_be_switched_off(project) -> None:
    workspace, _take = project
    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace,
        index,
        ExportOptions(include_synthetic=True, store_error_target_arrays=False),
    ).build()
    manifest = read_json(result.path / "manifest.json")
    entry = localised_entry(manifest)
    with np.load(result.path / entry["file"]) as payload:
        assert "error_multi_hot" not in payload
        # The authoritative interval list is always written.
        assert "error_intervals" in payload
    assert result.validation_passed
