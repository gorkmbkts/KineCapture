"""The labelling screen, tested for the one thing that must not go wrong.

A wrong label is worse than a missing one: a missing label stops the export,
while a wrong one trains the model on a lie and nothing downstream can tell.
So most of what is checked here is refusal - that a boundary is never moved to
a convenient frame, that a foreign recording's labels are never adopted, that
a half-finished interval never leaves as "no error here".

Qt is not imported. This is the viewmodel and the services under it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.errors import ValidationError
from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import long_path, path_exists
from kinecapture.domain.project import CaptureProfile
from kinecapture.processing import ProcessingConfig, process_take
from kinecapture.processing.sources import SyntheticSource
from kinecapture.processing.annotations import (
    Anchor,
    Correctness,
    JointStatus,
    MovementSample,
    Readiness,
    load_annotations,
)
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.studio.services.annotation_store import AnnotationStore
from kinecapture.studio.services.review import ReviewSession
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.review import ReviewViewModel

FRAMES = 24


@pytest.fixture
def processed(workspace, session) -> Path:
    """A real processed version of a short synthetic take."""
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=11, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    # Anchor the subject, exactly as the capture screen does. Without this no
    # body is selected and every array is NaN, which would make the tests below
    # pass without ever touching real numbers.
    config = ProcessingConfig(store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(
        paths.raw_dir / "subject_anchors.json",
        [{
            "camera_timestamp_ns": packet.camera_timestamp_ns,
            "source_resolution": list(packet.resolution),
            "point_xy": np.nanmean(points, axis=0).tolist(),
            "bbox_xyxy": np.r_[
                np.nanmin(points, axis=0), np.nanmax(points, axis=0)
            ].tolist(),
        }],
    )
    source.close()
    return process_take(paths.root, config)


@pytest.fixture
def studio_session(workspace):
    """The real session type, holding only what the screen actually reads."""
    return SessionService(config=None, identity=None, workspace=workspace)


@pytest.fixture
def opened(processed: Path) -> ReviewSession:
    review = ReviewSession.open(processed)
    yield review
    review.close()


def make_store(review: ReviewSession, **kwargs) -> AnnotationStore:
    defaults = dict(
        take_dir=review.take_dir,
        document=review.empty_document(),
        resolve=review.dataset.position_of_anchor,
        anchor_at=review.dataset.anchor_at,
        frames=review.frames,
        known_exercises=("squat", "deadlift"),
        known_error_classes=("knee_valgus", "back_round"),
    )
    defaults.update(kwargs)
    return AnnotationStore(**defaults)


# --------------------------------------------------------------- the anchors
def test_a_boundary_survives_save_and_reload_on_the_exact_frame(opened) -> None:
    store = make_store(opened)
    store.add_movement(4, 9)
    store.flush()

    document = load_annotations(
        opened.take_dir, opened.run_id, opened.source_fingerprint
    )
    reloaded = make_store(opened, document=document)
    assert reloaded.sample_bounds(document.samples[0].sample_id) == (4, 9)


def test_the_end_frame_is_inside_the_interval(opened) -> None:
    """Inclusive boundaries. Frame 9 belongs to a 4..9 movement."""
    store = make_store(opened)
    sample = store.add_movement(4, 9)
    assert store.sample_at(9) is not None
    assert store.sample_at(9).sample_id == sample.sample_id
    assert store.sample_at(10) is None


def test_labels_from_another_recording_are_refused_not_merged(opened, processed) -> None:
    store = make_store(opened)
    store.add_movement(2, 6)
    store.flush()

    # Read and write through the project's own helpers: these paths are long
    # enough on Windows that plain pathlib silently reports "not found".
    path = opened.dataset.annotation_file
    assert path_exists(path)
    payload = read_json(path)
    payload["source_fingerprint"] = "sha256:" + "0" * 64
    write_json(path, payload, overwrite=True)

    with pytest.raises(ValidationError) as caught:
        load_annotations(opened.take_dir, opened.run_id, opened.source_fingerprint)
    assert caught.value.code == "annotation_source_mismatch"


def test_an_unresolvable_moment_is_never_moved_to_the_nearest_frame(opened) -> None:
    anchor = opened.dataset.anchor_at(5)
    moved = replace(anchor, camera_timestamp_ns=anchor.camera_timestamp_ns + 1)
    with pytest.raises(ValueError):
        opened.dataset.position_of_anchor(moved)


def test_a_label_is_rejected_when_its_moment_left_the_version(opened) -> None:
    """A sample whose anchor is not in this version fails validation as a whole."""
    store = make_store(opened)
    good = opened.dataset.anchor_at(3)
    stray = replace(good, source_position=9999, camera_timestamp_ns=123)
    store.document.samples = (
        MovementSample(sample_id="s1", start=good, end=stray, exercise="squat"),
    )
    problems = store._validate(store.document)
    assert any(p["code"] == "sample_anchor_unresolved" for p in problems)


# ------------------------------------------------------------- the decisions
def test_one_decision_is_one_undo(opened) -> None:
    """Labelling sets class, verdict and timestamp - undo must take all three."""
    store = make_store(opened)
    sample = store.add_movement(1, 5)
    store.label_movement(sample.sample_id, "squat")
    assert store.document.samples[0].exercise == "squat"
    assert store.document.samples[0].reviewed_at

    store.undo()
    assert store.document.samples[0].exercise == ""
    assert not store.document.samples[0].reviewed_at
    assert len(store.document.samples) == 1  # the movement itself is still there


def test_correctness_is_derived_never_chosen(opened) -> None:
    store = make_store(opened)
    sample = store.add_movement(1, 8)
    assert store.document.samples[0].correctness is Correctness.UNREVIEWED

    store.label_movement(sample.sample_id, "squat")
    assert store.document.samples[0].correctness is Correctness.CORRECT

    interval = store.add_error(sample.sample_id, 2, 4)
    store.label_error(
        sample.sample_id,
        interval.interval_id,
        error_class="knee_valgus",
        affected_roles=("left_knee",),
        joint_status=JointStatus.SELECTED,
    )
    assert store.document.samples[0].correctness is Correctness.INCORRECT


def test_an_unclassified_error_blocks_the_whole_movement(opened) -> None:
    """Dropping the interval instead would export the rep as error-free."""
    store = make_store(opened)
    sample = store.add_movement(1, 8)
    store.label_movement(sample.sample_id, "squat")
    store.add_error(sample.sample_id, 2, 4)
    assert store.readiness(sample.sample_id) is Readiness.UNCLASSIFIED_ERROR


def test_an_error_cannot_sit_outside_its_movement(opened) -> None:
    store = make_store(opened)
    sample = store.add_movement(4, 8)
    with pytest.raises((ValidationError, ValueError)):
        store.add_error(sample.sample_id, 9, 12)


def test_shrinking_a_movement_clips_the_errors_inside_it(opened) -> None:
    store = make_store(opened)
    sample = store.add_movement(2, 12)
    interval = store.add_error(sample.sample_id, 6, 11)
    store.set_movement_bounds(sample.sample_id, 2, 8)
    assert store.sample_bounds(sample.sample_id) == (2, 8)
    remaining = store.document.samples[0].errors
    if remaining:
        first, last = store.error_bounds(sample.sample_id, interval.interval_id)
        assert first >= 2 and last <= 8


def test_an_unknown_class_is_refused(opened) -> None:
    store = make_store(opened)
    sample = store.add_movement(1, 5)
    with pytest.raises((ValidationError, ValueError)):
        store.label_movement(sample.sample_id, "not_a_real_exercise")


def test_naming_joints_requires_saying_they_were_chosen(opened) -> None:
    store = make_store(opened)
    sample = store.add_movement(1, 8)
    interval = store.add_error(sample.sample_id, 2, 4)
    with pytest.raises((ValidationError, ValueError)):
        store.label_error(
            sample.sample_id,
            interval.interval_id,
            error_class="knee_valgus",
            affected_roles=("left_knee",),
            joint_status=JointStatus.UNREVIEWED,
        )


def test_a_rejected_edit_leaves_nothing_behind(opened) -> None:
    """All-or-nothing: a refused decision must not consume an undo step."""
    store = make_store(opened)
    sample = store.add_movement(1, 5)
    before = store.document.samples
    depth = len(store._undo)
    with pytest.raises((ValidationError, ValueError)):
        store.label_movement(sample.sample_id, "nonsense")
    assert store.document.samples == before
    assert len(store._undo) == depth


# ------------------------------------------------------------------ the view
def test_the_screen_never_guesses_which_movement_an_error_belongs_to(
    opened, studio_session
) -> None:
    viewmodel = ReviewViewModel(studio_session)
    viewmodel._attach(opened)
    seen = []
    viewmodel.message.subscribe(seen.append)

    assert viewmodel.add_error(2, 4) is None
    assert seen and "hareket" in seen[0].headline.lower()


def test_bulk_labelling_never_overwrites_a_decision(opened, studio_session) -> None:
    viewmodel = ReviewViewModel(studio_session)
    viewmodel._attach(opened)
    viewmodel.store.known_exercises = ("squat", "deadlift")

    first = viewmodel.add_movement(1, 4)
    second = viewmodel.add_movement(6, 9)
    viewmodel.label_movement(first, "deadlift")

    changed = viewmodel.apply_exercise_to_unlabelled("squat")
    assert changed == 1
    assert viewmodel.movement_row(first).exercise == "deadlift"
    assert viewmodel.movement_row(second).exercise == "squat"


def test_rows_report_what_is_missing(opened, studio_session) -> None:
    viewmodel = ReviewViewModel(studio_session)
    viewmodel._attach(opened)
    viewmodel.store.known_exercises = ("squat",)
    sample_id = viewmodel.add_movement(1, 6)

    row = viewmodel.movement_row(sample_id)
    assert row.readiness is Readiness.NO_EXERCISE
    assert row.status == "warning"

    viewmodel.label_movement(sample_id, "squat")
    assert viewmodel.movement_row(sample_id).readiness is Readiness.READY
    assert "1/1" in viewmodel.progress.value


def test_seeking_stays_inside_the_version(opened, studio_session) -> None:
    viewmodel = ReviewViewModel(studio_session)
    viewmodel._attach(opened)
    viewmodel.seek(-5)
    assert viewmodel.position.value == 0
    viewmodel.seek(10_000)
    assert viewmodel.position.value == opened.frames - 1


# --------------------------------------------------------------- the session
def test_two_d_joints_are_reported_missing_rather_than_invented(processed) -> None:
    """A run without the 2D feature must say so, not project 3D into pixels."""
    review = ReviewSession.open(processed)
    try:
        available = review.joints_2d_available
        if not available:
            assert available.reason
            assert review.joints_2d(0, frame_size=(320, 240)) is None
    finally:
        review.close()


def test_two_d_joints_are_scaled_into_the_image_they_are_drawn_on(processed) -> None:
    review = ReviewSession.open(processed)
    try:
        if not review.joints_2d_available:
            pytest.skip(review.joints_2d_available.reason)
        source = review.source_size
        assert source is not None
        native = review.joints_2d(0)
        half = review.joints_2d(0, frame_size=(source[0] // 2, source[1] // 2))
        finite = np.isfinite(native[:, 0]) & np.isfinite(half[:, 0])
        assert finite.any(), "tracker produced no usable 2D joints to scale"
        assert np.allclose(half[finite, 0] * 2.0, native[finite, 0], atol=1e-3)
        assert np.allclose(half[finite, 1] * 2.0, native[finite, 1], atol=1e-3)
    finally:
        review.close()


def test_opening_a_version_does_not_parse_the_skeleton_stream(processed) -> None:
    """The screen reads windows out of arrays; the stream is seconds and MBs."""
    review = ReviewSession.open(processed)
    try:
        assert review.frames > 0
        review.joints_3d(0)
        assert not review.dataset.stream_loaded
    finally:
        review.close()


def test_a_repeated_frame_identity_is_ambiguous_not_last_wins(opened, processed) -> None:
    """A damaged source can repeat a frame identity; then no position is right."""
    from kinecapture.processing.review import ReviewDataset

    path = processed / "source_map.jsonl"
    with open(long_path(path), "r", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    frames = [r for r in rows if r.get("record") == "frame"]
    # Make frame 7 claim to be frame 3: same source position, same camera time.
    frames[7]["source_position"] = frames[3]["source_position"]
    frames[7]["cam_ns"] = frames[3]["cam_ns"]
    body = [rows[0]] + frames
    with open(long_path(path), "w", encoding="utf-8") as stream:
        for row in body:
            stream.write(json.dumps(row) + chr(10))

    dataset = ReviewDataset(processed, verify=False)
    try:
        assert not dataset._ordered
        with pytest.raises(ValueError, match="ambiguous"):
            dataset.position_of_anchor(
                Anchor(
                    source_fingerprint=dataset.source_fingerprint,
                    source_position=int(frames[3]["source_position"]),
                    camera_timestamp_ns=int(frames[3]["cam_ns"]),
                )
            )
    finally:
        dataset.close()


def test_the_source_map_is_not_held_as_parsed_rows(opened) -> None:
    """An hour of frames must not cost hundreds of megabytes to open."""
    assert opened.dataset._positions.dtype == np.int64
    assert opened.dataset._stamps.dtype == np.int64
    assert opened.dataset._by_anchor is None  # the dict is only for damaged maps
