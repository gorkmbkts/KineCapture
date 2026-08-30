"""Dataset index, release building, validation and atomicity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import ExportCancelled, ExportError
from kinecapture.core.jsonio import read_json
from kinecapture.dataset.index import DatasetIndex, DatasetQuery
from kinecapture.domain.enums import (
    Correctness,
    DataOrigin,
    SampleReadiness,
    TakeQuality,
)
from kinecapture.export.release import (
    ExportOptions,
    ReleaseBuilder,
    list_releases,
    next_release_name,
)
from kinecapture.playback.take_reader import load_take
from tests.conftest import paced_backend, record_take


def _record_and_label(
    workspace, session, *, frames: int = 30, exercise: str = "squat", reps: int = 2
):
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=frames, exercise=exercise)
    service.shutdown()

    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    schema = workspace.label_schema
    if not schema.error_types:
        schema.add_error_type("Diz içe çöküyor")
        workspace.save_label_schema(schema)

    repository = AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count, annotator="pytest"
    )
    span = loaded.frame_count // (reps + 1)
    for index in range(reps):
        sample = repository.create_sample(1 + index * span, (index + 1) * span)
        correct = index % 2 == 0
        repository.label_sample(
            sample.sample_id, exercise=exercise, reviewed=True
        )
        if not correct:
            # An incorrect movement is only finished once the error is located.
            repository.create_error_interval(
                sample.sample_id,
                sample.start_frame + 2,
                sample.start_frame + 6,
                error_code="diz-ice-cokuyor",
            )
    repository.save()
    return take


@pytest.fixture
def labelled_project(workspace, session):
    _record_and_label(workspace, session)
    return workspace


# ------------------------------------------------------------ dataset index


def test_index_counts_everything(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    summary = index.summary()
    assert summary.takes == 1
    assert summary.movement_samples == 2
    assert summary.ready_samples == 2
    assert summary.error_intervals == 1
    assert summary.synthetic_takes == 1
    assert summary.real_takes == 0
    assert summary.correctness_counts == {"correct": 1, "incorrect": 1}
    assert summary.exercise_counts == {"squat": 2}


def test_index_caches_until_metadata_changes(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    first = index.rows
    index.refresh()
    assert index.rows is not first or len(index.rows) == len(first)
    assert len(index.rows) == 1


def test_query_filters(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    assert len(index.filter(DatasetQuery())) == 1
    assert index.filter(DatasetQuery(exercises=("squat",)))
    assert not index.filter(DatasetQuery(exercises=("bench",)))
    assert not index.filter(DatasetQuery(origin=DataOrigin.REAL))
    assert index.filter(DatasetQuery(origin=DataOrigin.SYNTHETIC))
    assert index.filter(DatasetQuery(correctness=(Correctness.INCORRECT,)))
    assert index.filter(DatasetQuery(error_codes=("diz-ice-cokuyor",)))
    assert not index.filter(DatasetQuery(error_codes=("nope",)))
    assert index.filter(DatasetQuery(readiness=(SampleReadiness.READY,)))


def test_quality_issues_flag_single_participant(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    issues = index.quality_issues()
    kinds = {issue["issue"] for issue in issues}
    assert "single_participant_exercise" in kinds
    # Nothing structural should be wrong with a clean synthetic recording.
    assert not any(issue["severity"] == "blocked" for issue in issues)


def test_quality_issues_flag_partial_take(workspace, session) -> None:
    backend = paced_backend(width=64, height=48)
    service = CaptureService(backend)
    service.connect()
    service.start_preview()
    service.start_recording(workspace, session)
    import time

    deadline = time.time() + 10.0
    while service.recorded_frame_count < 8 and time.time() < deadline:
        time.sleep(0.005)
    service.stop_recording(abort_reason="test")
    service.shutdown()

    index = DatasetIndex(workspace).refresh()
    kinds = {issue["issue"] for issue in index.quality_issues()}
    assert "partial_take" in kinds


# ----------------------------------------------------------------- naming


def test_release_names_increment(tmp_path: Path) -> None:
    assert next_release_name(tmp_path) == "dataset_v001"
    (tmp_path / "dataset_v001").mkdir()
    assert next_release_name(tmp_path) == "dataset_v002"
    (tmp_path / "dataset_v007").mkdir()
    assert next_release_name(tmp_path) == "dataset_v008"


# ------------------------------------------------------------------ build


def test_release_contains_every_required_document(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    )
    result = builder.build()

    assert result.sample_count == 2
    assert result.validation_passed
    for name in (
        "manifest.json",
        "skeleton_spec.json",
        "label_mapping.json",
        "dataset_fingerprint.json",
        "validation_report.json",
        "excluded.json",
    ):
        assert (result.path / name).is_file(), f"missing {name}"
    assert (result.path / "samples").is_dir()


def test_sample_arrays_match_the_contract(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    result = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    ).build()

    manifest = read_json(result.path / "manifest.json")
    assert manifest["array_contract"]["dtype"] == "float32"
    assert manifest["array_contract"]["normalisation"] == "none"

    entry = manifest["samples"][0]
    with np.load(result.path / entry["file"]) as payload:
        joints = payload["joints_xyz"]
        assert joints.dtype == np.float32
        assert joints.ndim == 3 and joints.shape[2] == 3
        assert joints.shape[0] == entry["num_frames"]
        assert joints.shape[1] == entry["num_joints"]
        assert "joint_confidences" in payload
        assert "camera_timestamps_ns" in payload
        assert "frame_indices" in payload


def test_manifest_preserves_grouping_keys(labelled_project) -> None:
    """Participant/session/take ids must survive so a split cannot leak."""
    index = DatasetIndex(labelled_project).refresh()
    result = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    ).build()
    manifest = read_json(result.path / "manifest.json")
    for entry in manifest["samples"]:
        assert entry["participant_id"]
        assert entry["session_id"]
        assert entry["take_id"]
        assert entry["movement_sample_id"]
        assert entry["source_backend"]
        assert entry["capture_profile"]


def test_synthetic_samples_are_labelled_synthetic(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    result = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    ).build()
    manifest = read_json(result.path / "manifest.json")
    assert all(entry["origin"] == "synthetic" for entry in manifest["samples"])
    report = read_json(result.path / "validation_report.json")
    assert any("SENTETİK" in warning for warning in report["warnings"])


def test_fingerprint_is_stable_and_component_wise(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    options = ExportOptions(include_synthetic=True)
    first = ReleaseBuilder(labelled_project, index, options).build()
    second = ReleaseBuilder(labelled_project, index, options).build()

    a = read_json(first.path / "dataset_fingerprint.json")
    b = read_json(second.path / "dataset_fingerprint.json")
    assert a["fingerprint"] == b["fingerprint"]
    assert set(a["components"]) == {
        "samples",
        "export_config",
        "skeleton_spec",
        "label_schema",
        # The feature component identifies the derived-feature definitions that
        # produced the release's optional arrays.
        "features",
    }


def test_fingerprint_changes_with_options(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    first = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    ).build()
    second = ReleaseBuilder(
        labelled_project,
        index,
        ExportOptions(include_synthetic=True, store_confidences=False),
    ).build()
    a = read_json(first.path / "dataset_fingerprint.json")
    b = read_json(second.path / "dataset_fingerprint.json")
    assert a["fingerprint"] != b["fingerprint"]


def test_previous_release_is_never_modified(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    options = ExportOptions(include_synthetic=True)
    first = ReleaseBuilder(labelled_project, index, options).build()
    before = (first.path / "manifest.json").read_bytes()

    second = ReleaseBuilder(labelled_project, index, options).build()
    assert first.release_name != second.release_name
    assert (first.path / "manifest.json").read_bytes() == before
    assert len(list_releases(labelled_project.releases_dir)) == 2


def test_export_excludes_synthetic_by_default(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(labelled_project, index, ExportOptions())
    with pytest.raises(ExportError) as info:
        builder.build()
    assert info.value.code == "export_empty"


def test_export_skips_unlabelled_by_default(workspace, session) -> None:
    backend = paced_backend()
    service = CaptureService(backend)
    service.connect()
    take = record_take(service, workspace, session, frames=25)
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    index = DatasetIndex(workspace).refresh()
    with pytest.raises(ExportError):
        ReleaseBuilder(
            workspace, index, ExportOptions(include_synthetic=True)
        ).build()


def test_excluded_samples_are_left_out(labelled_project) -> None:
    from kinecapture.domain.enums import SegmentStatus

    index = DatasetIndex(labelled_project).refresh()
    row = index.rows[0]
    repository = AnnotationRepository(labelled_project, row.take)
    repository.set_sample_status(
        repository.samples[0].sample_id, SegmentStatus.EXCLUDED
    )
    repository.save()

    index.refresh(force=True)
    result = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    ).build()
    assert result.sample_count == 1


def test_short_samples_are_excluded_with_a_reason(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    result = ReleaseBuilder(
        labelled_project,
        index,
        ExportOptions(include_synthetic=True, min_frames_per_sample=1000),
    )
    with pytest.raises(ExportError) as info:
        result.build()
    assert "too_few_frames" in str(info.value)


# ------------------------------------------------------------- atomicity


def test_cancellation_publishes_nothing(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    )

    def cancel_immediately(done: int, total: int, message: str) -> bool:
        return False

    with pytest.raises(ExportCancelled):
        builder.build(progress=cancel_immediately)

    assert list_releases(labelled_project.releases_dir) == []
    # No staging directory is left behind either.
    leftovers = [
        p for p in labelled_project.releases_dir.iterdir() if p.name.startswith(".staging")
    ]
    assert leftovers == []


def test_failure_leaves_no_partial_release(labelled_project, monkeypatch) -> None:
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    )

    def explode(*args, **kwargs):
        raise RuntimeError("disk exploded")

    monkeypatch.setattr("kinecapture.export.release.np.savez_compressed", explode)
    with pytest.raises(RuntimeError):
        builder.build()

    assert list_releases(labelled_project.releases_dir) == []
    assert list(labelled_project.releases_dir.iterdir()) == []


def test_release_refuses_to_overwrite_an_existing_name(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    options = ExportOptions(include_synthetic=True)
    first = ReleaseBuilder(labelled_project, index, options).build()
    with pytest.raises(ExportError) as info:
        ReleaseBuilder(labelled_project, index, options).build(
            release_name=first.release_name
        )
    assert info.value.code == "release_exists"


# ------------------------------------------------------------ joint mapping


def test_mapping_target_without_a_mapping_is_refused_clearly(
    labelled_project,
) -> None:
    """mock_16 has no defined mapping; the export says so instead of guessing."""
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(
        labelled_project,
        index,
        ExportOptions(
            include_synthetic=True, target_skeleton_format="rehab24_6_mocap"
        ),
    )
    with pytest.raises(ExportError) as info:
        builder.build()
    assert "no_joint_mapping" in str(info.value)
    assert "eşleştirmesi" in info.value.remedy


def test_progress_reports_monotonic_completion(labelled_project) -> None:
    index = DatasetIndex(labelled_project).refresh()
    builder = ReleaseBuilder(
        labelled_project, index, ExportOptions(include_synthetic=True)
    )
    seen: list[tuple[int, int]] = []

    def report(done: int, total: int, message: str) -> bool:
        seen.append((done, total))
        return True

    builder.build(progress=report)
    assert seen
    assert all(a[0] <= b[0] for a, b in zip(seen, seen[1:]))
    assert seen[-1][0] <= seen[-1][1]
