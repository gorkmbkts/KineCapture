"""The last gate before a label becomes training data.

After a release is written, a model is trained on it and nothing looks at the
labels again. So these tests care about two things above all: that a version
which is not ready is refused *with a reason recorded in the package*, and
that a sample which is written describes exactly the frames the annotator
marked - same boundaries, same classes, same intervals.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import long_path, path_exists
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import CaptureProfile
from kinecapture.export.canonical import (
    CanonicalExportOptions,
    Refusal,
    build_release,
    inspect_version,
)
from kinecapture.processing import ProcessingConfig, process_take
from kinecapture.processing.annotations import JointStatus
from kinecapture.processing.sources import SyntheticSource
from kinecapture.processing.subject_review import Verdict
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.studio.services.annotation_store import AnnotationStore
from kinecapture.studio.services.review import ReviewSession
from kinecapture.studio.services.subject_store import SubjectStore
from kinecapture.processing.subject_review import scan_candidates, scan_unsettled

FRAMES = 40
EXERCISE = "squat"
ERROR_CLASS = "knee_valgus"


@pytest.fixture
def schema() -> LabelSchema:
    schema = LabelSchema.default()
    schema.ensure_exercise("Squat")
    schema.ensure_error_type("Knee valgus")
    return schema


@pytest.fixture
def version(workspace, session) -> Path:
    """A processed version with the athlete marked at capture time."""
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=21, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(paths.raw_dir / "subject_anchors.json", [{
        "camera_timestamp_ns": packet.camera_timestamp_ns,
        "source_resolution": list(packet.resolution),
        "point_xy": np.nanmean(points, axis=0).tolist(),
        "bbox_xyxy": np.r_[np.nanmin(points, axis=0), np.nanmax(points, axis=0)].tolist(),
    }])
    source.close()
    return process_take(paths.root, config)


def label(version: Path, schema: LabelSchema, *, with_error: bool = True) -> dict:
    """Do to a version exactly what the labelling screen does."""
    review = ReviewSession.open(version)
    exercise = schema.exercise_codes()[0]
    error_code = schema.error_type_codes()[0]
    store = AnnotationStore(
        take_dir=review.take_dir,
        document=review.empty_document(),
        annotator="koc",
        resolve=review.dataset.position_of_anchor,
        anchor_at=review.dataset.anchor_at,
        frames=review.frames,
        known_exercises=schema.exercise_codes(),
        known_error_classes=schema.error_type_codes(),
    )
    sample = store.add_movement(5, 20)
    store.label_movement(sample.sample_id, exercise)
    interval_id = ""
    if with_error:
        interval = store.add_error(sample.sample_id, 8, 12)
        interval_id = interval.interval_id
        store.label_error(
            sample.sample_id,
            interval.interval_id,
            error_class=error_code,
            affected_roles=("left_knee",),
            joint_status=JointStatus.SELECTED,
        )
    store.flush()

    frames = review.dataset.stream.frames
    subject = SubjectStore(
        take_dir=review.take_dir,
        document=__import__(
            "kinecapture.processing.subject_review", fromlist=["load_subject_review"]
        ).load_subject_review(review.take_dir, review.run_id, review.source_fingerprint),
        candidates=scan_candidates(frames),
        annotator="koc",
    )
    subject.set_intervals(scan_unsettled(frames, review.dataset.anchor_at))
    subject.choose_athlete(subject.candidates[0].tracker_id)
    if subject.document.unanswered:
        subject.answer_all_remaining(Verdict.SAME_ATHLETE)
    subject.flush()
    out = {
        "sample_id": sample.sample_id,
        "interval_id": interval_id,
        "exercise": exercise,
        "error_class": error_code,
        "run_id": review.run_id,
    }
    review.close()
    return out


# --------------------------------------------------------------- the gates
def test_an_unlabelled_version_is_refused_with_a_reason(version, schema) -> None:
    report, opened = inspect_version(version, schema)
    assert not report.accepted and opened is None
    assert Refusal.ATHLETE_NOT_CHOSEN in report.refusals
    assert Refusal.NO_READY_SAMPLES in report.refusals


def test_a_fully_labelled_version_passes(version, schema) -> None:
    label(version, schema)
    report, opened = inspect_version(version, schema)
    try:
        assert report.accepted, report.refusals
        assert report.refusals == ()
        assert report.annotation_revision > 0
    finally:
        if opened:
            opened["dataset"].close()


def test_a_version_with_no_athlete_never_reaches_the_package(
    version, schema, tmp_path
) -> None:
    label(version, schema)
    # Take the athlete choice back out, as if nobody had answered it.
    from kinecapture.processing.subject_review import (
        load_subject_review,
        save_subject_review,
    )

    review = ReviewSession.open(version)
    document = load_subject_review(review.take_dir, review.run_id, review.source_fingerprint)
    document.athlete_tracker_id = None
    save_subject_review(review.take_dir, document)
    review.close()

    report = build_release([version], tmp_path / "releases", schema)
    assert report.samples == 0
    assert report.refused and Refusal.ATHLETE_NOT_CHOSEN in report.refused[0].refusals


def test_an_unclassified_error_blocks_the_whole_version(version, schema) -> None:
    """Writing the movement without the interval would say "no error here"."""
    review = ReviewSession.open(version)
    store = AnnotationStore(
        take_dir=review.take_dir,
        document=review.empty_document(),
        resolve=review.dataset.position_of_anchor,
        anchor_at=review.dataset.anchor_at,
        frames=review.frames,
        known_exercises=schema.exercise_codes(),
        known_error_classes=schema.error_type_codes(),
    )
    sample = store.add_movement(4, 18)
    store.label_movement(sample.sample_id, schema.exercise_codes()[0])
    store.add_error(sample.sample_id, 6, 9)   # drawn, never classified
    store.flush()
    review.close()

    report, opened = inspect_version(version, schema)
    assert not report.accepted
    assert Refusal.OPEN_ERRORS in report.refusals
    assert opened is None


def test_the_refusal_is_written_into_the_package(version, schema, tmp_path) -> None:
    """"Why is this athlete missing" must be answerable from the release."""
    report = build_release([version], tmp_path / "releases", schema)
    manifest = read_json(report.release_dir / "manifest.json")
    assert manifest["counts"]["versions_refused"] == 1
    refused = manifest["refused_versions"][0]
    assert refused["refusals"]
    assert refused["refusal_text"] and all(refused["refusal_text"])


# ------------------------------------------------------------- the content
def test_a_sample_carries_exactly_the_frames_that_were_marked(
    version, schema, tmp_path
) -> None:
    marked = label(version, schema)
    report = build_release([version], tmp_path / "releases", schema)
    assert report.samples == 1

    entry = read_json(report.release_dir / "samples.json")["samples"][0]
    assert entry["version_positions"] == [5, 20]
    assert entry["frames"] == 16          # inclusive on both ends
    assert entry["exercise"] == marked["exercise"]
    assert entry["correctness"] == "incorrect"   # it carries a classified error

    joints = np.load(
        long_path(report.release_dir / entry["directory"] / "joints.npy")
    )
    assert joints.shape[0] == 16


def test_the_sample_arrays_are_the_versions_own_frames(
    version, schema, tmp_path
) -> None:
    """Sliced, not recomputed: the numbers must be identical."""
    label(version, schema)
    report = build_release([version], tmp_path / "releases", schema)
    entry = read_json(report.release_dir / "samples.json")["samples"][0]

    review = ReviewSession.open(version)
    try:
        expected = review.dataset.window("joints", 5, 21)
    finally:
        review.close()
    written = np.load(long_path(report.release_dir / entry["directory"] / "joints.npy"))
    np.testing.assert_array_equal(written, expected)


def test_error_intervals_are_relative_to_their_sample_and_inclusive(
    version, schema, tmp_path
) -> None:
    label(version, schema)
    report = build_release([version], tmp_path / "releases", schema)
    entry = read_json(report.release_dir / "samples.json")["samples"][0]

    interval = entry["error_intervals"][0]
    # Drawn at 8..12 inside a movement starting at 5.
    assert interval["relative_start"] == 3
    assert interval["relative_end"] == 7
    assert interval["error_class"] == schema.error_type_codes()[0]
    assert interval["affected_roles"] == ["left_knee"]
    assert interval["joint_status"] == JointStatus.SELECTED.value


def test_the_dense_target_matches_the_interval(version, schema, tmp_path) -> None:
    label(version, schema)
    report = build_release([version], tmp_path / "releases", schema)
    entry = read_json(report.release_dir / "samples.json")["samples"][0]
    dense = np.load(
        long_path(report.release_dir / entry["directory"] / "error_per_frame.npy")
    )
    index = entry["error_intervals"][0]["class_index"]
    assert dense.shape[0] == entry["frames"]
    assert dense[3:8, index].all()          # the marked frames, inclusive
    assert not dense[:3, index].any()
    assert not dense[8:, index].any()


def test_a_correct_movement_carries_no_error_rows(version, schema, tmp_path) -> None:
    label(version, schema, with_error=False)
    report = build_release([version], tmp_path / "releases", schema)
    entry = read_json(report.release_dir / "samples.json")["samples"][0]
    assert entry["correctness"] == "correct"
    assert entry["error_intervals"] == []
    dense = np.load(
        long_path(report.release_dir / entry["directory"] / "error_per_frame.npy")
    )
    assert not dense.any()


# ------------------------------------------------------------ the manifest
def test_the_package_names_what_produced_it(version, schema, tmp_path) -> None:
    marked = label(version, schema)
    report = build_release([version], tmp_path / "releases", schema, operator="koc")
    manifest = read_json(report.release_dir / "manifest.json")

    assert manifest["operator"] == "koc"
    assert manifest["annotation_schema_version"]
    assert manifest["subject_schema_version"]
    entry = read_json(report.release_dir / "samples.json")["samples"][0]
    assert entry["run_id"] == marked["run_id"]
    assert entry["annotation_revision"] > 0
    assert entry["subject_revision"] > 0
    assert entry["source_fingerprint"]


def test_class_indices_come_from_the_manifest_and_are_stable(
    version, schema, tmp_path
) -> None:
    label(version, schema)
    first = build_release([version], tmp_path / "r1", schema)
    second = build_release([version], tmp_path / "r2", schema)
    a = read_json(first.release_dir / "manifest.json")
    b = read_json(second.release_dir / "manifest.json")
    assert a["label_mapping"]["exercise"]["code_to_index"] == b["label_mapping"]["exercise"]["code_to_index"]
    assert a["content_fingerprint"] == b["content_fingerprint"]


def test_an_excluded_movement_is_not_written(version, schema, tmp_path) -> None:
    marked = label(version, schema)
    review = ReviewSession.open(version)
    from kinecapture.processing.annotations import load_annotations

    document = load_annotations(review.take_dir, review.run_id, review.source_fingerprint)
    store = AnnotationStore(
        take_dir=review.take_dir,
        document=document,
        resolve=review.dataset.position_of_anchor,
        anchor_at=review.dataset.anchor_at,
        frames=review.frames,
        known_exercises=schema.exercise_codes(),
        known_error_classes=schema.error_type_codes(),
    )
    store.set_excluded(marked["sample_id"], True)
    store.flush()
    review.close()

    report = build_release([version], tmp_path / "releases", schema)
    assert report.samples == 0
    assert Refusal.NO_READY_SAMPLES in report.refused[0].refusals


# -------------------------------------------------------------- atomicity
def test_a_failed_build_leaves_no_release_behind(version, schema, tmp_path, monkeypatch) -> None:
    label(version, schema)
    releases = tmp_path / "releases"

    import kinecapture.export.canonical as canonical

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk doldu")

    monkeypatch.setattr(canonical, "_manifest", boom)
    with pytest.raises(RuntimeError):
        build_release([version], releases, schema)

    leftovers = [p for p in Path(long_path(releases)).iterdir()] if path_exists(releases) else []
    assert leftovers == [], f"yarım kalan sürüm: {leftovers}"
