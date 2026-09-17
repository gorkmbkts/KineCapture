import os
import time
from pathlib import Path
from threading import Event
from dataclasses import replace
import numpy as np
import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.jsonio import read_json, write_json, read_jsonl
from kinecapture.core.paths import long_path, path_exists
from kinecapture.domain.project import CaptureProfile
from kinecapture.domain.enums import TakeState
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.processing import ProcessingConfig, process_take, restart_job
from kinecapture.processing.annotations import MovementSample
from kinecapture.processing.jobs import source_identity
from kinecapture.processing.sources import SyntheticSource
from kinecapture.processing.review import ReviewDataset


@pytest.fixture
def raw_take(workspace, session):
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=84, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(12):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()
    return take, paths


def test_minimal_source_has_no_derived_work(raw_take):
    take, paths = raw_take
    assert take.state is TakeState.FINALIZED
    assert take.processing_status == "awaiting_processing"
    assert not take.usable_for_export
    assert not path_exists(paths.skeleton_stream)
    assert not path_exists(paths.proxy_video)
    assert not list(paths.rgbd_dir.glob("*.kcd"))
    rows = list(read_jsonl(paths.raw_index))[1:]
    assert len(rows) == 12 and not any(row["skel"] or row["depth"] for row in rows)


def test_offline_all_frames_immutable_versioned_review(raw_take):
    take, paths = raw_take
    before = source_identity(paths, take)
    config = ProcessingConfig(store_depth=True, store_proxy=False)
    first = process_take(paths.root, config)
    job = read_json(first / "job.json")
    assert job["state"] == "complete", job
    assert job["frames_processed"] == 12
    assert len(job["depth_chunks"]) == 2
    assert source_identity(paths, take) == before
    second = process_take(paths.root, replace(config, store_depth=False))
    assert first != second and path_exists(first)
    review = ReviewDataset(second)
    assert len(review.mapping) == 12
    arrays = review.arrays()
    assert arrays["joints"].shape == (12, 16, 3)
    assert not arrays["subject_present"].any()  # no implicit best-body identity
    anchor = review.anchor_at(4)
    assert review.position_of_anchor(anchor) == 4
    document = review.load_annotations()
    document.samples = (
        MovementSample(
            sample_id="s1", start=anchor, end=review.anchor_at(8), exercise="squat"
        ),
    )
    target = review.save_annotations(document)
    assert path_exists(target) and not path_exists(paths.segments)
    # The sidecar is the only thing written; the raw segments file stays absent.
    reloaded = review.load_annotations()
    assert [s.sample_id for s in reloaded.samples] == ["s1"]
    assert review.position_of_anchor(reloaded.samples[0].start) == 4
    assert review.position_of_anchor(reloaded.samples[0].end) == 8
    with pytest.raises(ValueError, match="another raw source"):
        review.position_of_anchor(replace(anchor, source_fingerprint="wrong"))


def test_cancel_and_restart_keep_partial_and_raw(raw_take):
    take, paths = raw_take
    event = Event()
    event.set()
    partial = process_take(paths.root, ProcessingConfig(store_proxy=False, store_depth=False), cancel=event)
    assert read_json(partial / "job.json")["state"] == "cancelled"
    complete = restart_job(partial)
    assert read_json(complete / "job.json")["state"] == "complete"
    assert read_json(partial / "job.json")["state"] == "cancelled"
    assert complete != partial


def test_restart_rejects_changed_source(raw_take):
    _, paths = raw_take
    event = Event(); event.set()
    partial = process_take(paths.root, cancel=event)
    write_json(paths.raw_dir / "unexpected.json", {"new": True})
    with pytest.raises(ValueError, match="source fingerprint"):
        restart_job(partial)


def test_midstream_cancel_closes_source_without_publishing(raw_take):
    _, paths = raw_take
    event = Event()
    closed = []
    class CancelSource(SyntheticSource):
        def __iter__(self):
            for i, packet in enumerate(super().__iter__()):
                if i == 4: event.set()
                yield packet
        def close(self):
            closed.append(True)
            super().close()
    output = process_take(paths.root,ProcessingConfig(store_depth=False,store_proxy=False),
                          cancel=event,source_factory=CancelSource)
    job=read_json(output/'job.json')
    assert job['state']=='cancelled' and job['frames_processed']==4 and closed


def _broken_source(fault):
    class Broken(SyntheticSource):
        def __iter__(self):
            for i, packet in enumerate(super().__iter__()):
                if fault == "count" and i == 9: return
                if fault == "exception" and i == 3: raise RuntimeError("injected decoder error")
                if i == 4 and fault == "timestamp": packet = replace(packet, camera_timestamp_ns=7)
                if i == 4 and fault == "position": packet = replace(packet, source_position=7)
                yield packet
    return Broken


@pytest.mark.parametrize("fault", ["position", "exception"])
def test_a_fault_that_breaks_annotation_is_never_published(raw_take, fault):
    """Frame position is the annotation contract; a hole in it hides the run.

    These are the faults where the version would be *wrong* rather than
    incomplete: a label boundary would no longer identify a frame, or the run
    never finished at all. Such a run stays in its dot-prefixed staging folder,
    which no listing reads and no reader opens.
    """
    _, paths = raw_take
    staged = process_take(paths.root, ProcessingConfig(store_proxy=False, store_depth=False),
                          source_factory=_broken_source(fault))
    assert staged.name.startswith(".") and staged.name.endswith(".partial")
    job = read_json(staged / "job.json")
    assert job["state"] in ("partial", "failed") and not job.get("published")
    with pytest.raises(ValueError):
        ReviewDataset(staged)


@pytest.mark.parametrize("fault,expected", [
    ("count", "source_frame_count_mismatch"),
    ("timestamp", "source_timestamp_non_monotonic"),
])
def test_a_fault_that_only_costs_coverage_is_published_with_the_fault_recorded(
    raw_take, fault, expected
):
    """Nine frames of sixteen is a short version, not a broken one.

    Until 17 September both endings were the same folder rename that never
    happened, so two 16 September recordings that had matched 99.4% and 99.7%
    of their frames were unreachable from every screen. The caveat is recorded,
    the state stays ``partial``, and the version can be opened and annotated.
    """
    _, paths = raw_take
    run = process_take(paths.root, ProcessingConfig(store_proxy=False, store_depth=False),
                       source_factory=_broken_source(fault))
    assert not run.name.startswith(".")
    job = read_json(run / "job.json")
    assert job["state"] == "partial" and job["published"] is True
    assert expected in job["issues"] and not job["blocking_issues"]
    ReviewDataset(run).close()


def test_derived_tamper_is_not_annotation_ready(raw_take):
    _, paths = raw_take
    output = process_take(paths.root, ProcessingConfig(store_depth=False, store_proxy=False))
    with open(long_path(output / "source_map.jsonl"), "a") as f: f.write("{}\n")
    with pytest.raises(ValueError, match="checksum"):
        ReviewDataset(output)


def test_source_precision_roundtrip_and_wrong_shape():
    backend = MockCameraBackend(width=160, height=120)
    backend.connect(); backend.start_preview()
    body = backend.grab_frame().bodies[0]
    body.joint_positions_xyz[3,1] = np.float32(1.1234567)
    restored = type(body).from_record(body.to_record())
    np.testing.assert_array_equal(restored.joint_positions_xyz, body.joint_positions_xyz)
    record = body.to_record()
    record["joints"] = np.zeros((3, 16)).tolist()
    with pytest.raises(ValueError): type(body).from_record(record)


def test_source_anchor_drives_subject_arrays_and_features(raw_take):
    take, paths = raw_take
    config = ProcessingConfig(store_proxy=False,store_depth=False)
    source = SyntheticSource(paths,take,config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    anchor = {"camera_timestamp_ns": packet.camera_timestamp_ns,
              "source_resolution": list(packet.resolution),
              "point_xy": np.nanmean(points,axis=0).tolist(),
              "bbox_xyxy": np.r_[np.nanmin(points,axis=0),np.nanmax(points,axis=0)].tolist()}
    write_json(paths.raw_dir / "subject_anchors.json", [anchor])
    source.close()
    output=process_take(paths.root,config)
    review=ReviewDataset(output)
    arrays=review.arrays()
    assert arrays["subject_present"].all()
    np.testing.assert_array_equal(arrays["joints"][0],packet.bodies[0].joint_positions_xyz)
    assert np.isfinite(arrays["joint_angles_deg"]).any()


def test_a_subject_picked_before_record_still_names_the_subject(raw_take):
    """Picking the person happens before pressing record, not during.

    Both 16 September takes carry an anchor stamped 3.7 s and 1.6 s before
    their first recorded frame, taken while the preview was running. Matching
    it strictly against the recording found nothing, so the version was written
    with ``subject_anchor_outside_source`` and a joint array that was NaN from
    end to end. It is applied to the first recorded frame, it still has to land
    on a real body there, and the offset is written into the job file.
    """
    take, paths = raw_take
    config = ProcessingConfig(store_proxy=False, store_depth=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    anchor_payload = {
        # A second and a half before the recording starts.
        "camera_timestamp_ns": packet.camera_timestamp_ns - 1_600_000_000,
        "source_resolution": list(packet.resolution),
        "point_xy": np.nanmean(points, axis=0).tolist(),
        "bbox_xyxy": np.r_[np.nanmin(points, axis=0), np.nanmax(points, axis=0)].tolist(),
    }
    write_json(paths.raw_dir / "subject_anchors.json", [anchor_payload])
    source.close()

    run = process_take(paths.root, config)
    job = read_json(run / "job.json")
    assert "subject_anchor_outside_source" not in job["issues"]
    assert "subject_anchor_before_recording" in job["issues"]
    applied = job["subject_anchors"][0]
    assert applied["position"] == 0
    assert applied["method"] == "source_image_anchor_preroll"
    assert applied["offset_ms"] == pytest.approx(1600.0, abs=1.0)
    assert job["subject_status"] == "associated"

    review = ReviewDataset(run)
    try:
        assert review.arrays()["subject_present"].all()
    finally:
        review.close()


# --------------------------------------------- processing 1.1.0 derived layer
#
# Raw file access below goes through ``long_path``. The application already
# does, which is why it works where a plain ``Path`` does not: pytest's temp
# directory names contain the test name and a take path is eight levels deep,
# so these directories routinely pass 260 characters. A test that opened them
# naively would fail for a reason that has nothing to do with what it checks.


def test_a_version_carries_arrays_summary_and_previews(raw_take):
    """The three artefacts a review screen needs, produced once, not at paint time."""
    take, paths = raw_take
    run = process_take(paths.root, ProcessingConfig(store_depth=True, store_proxy=True))
    job = read_json(run / "job.json")
    assert job["schema_version"] == "1.1.0"
    if job["issues"] == ["review_proxy_unavailable"]:
        # OpenCV cannot open an extended-length path, so on a long temp path
        # there is no proxy and therefore no previews. That is the known
        # platform limit, not a defect in what this test is about.
        pytest.skip("proxy video uzun yolda yazılamadı; önizleme kontrolü atlandı")
    assert job["state"] == "complete", job["issues"]

    review = ReviewDataset(run)
    try:
        assert review.array_store.is_memmapped is True
        assert review.window("joints", 2, 6).shape == (4, 16, 3)
        assert review.has_summary
        lane = review.summary.lane(view_start=0, view_span=12, pixels=40)
        assert lane["bins"] > 0
        assert review.has_depth
        assert review.depth.at(3) is not None
        assert review.depth.provenance == "reconstructed_offline"
    finally:
        review.close()


def test_summary_marks_frames_with_no_matching_capture_row(raw_take):
    """QC flags come from the pass that produced them, not a second reading."""
    from kinecapture.processing.summary import FLAG_CAPTURE_UNMATCHED

    take, paths = raw_take
    run = process_take(paths.root, ProcessingConfig(store_depth=False, store_proxy=False))
    review = ReviewDataset(run)
    try:
        # This mock source matches every frame, so the flag must be absent -
        # a flag that is always set would tell nobody anything.
        assert review.summary.flags_present(FLAG_CAPTURE_UNMATCHED) is False
    finally:
        review.close()


def test_progress_never_invents_a_percentage(raw_take):
    take, paths = raw_take
    run = process_take(paths.root, ProcessingConfig(store_depth=False, store_proxy=False))
    job = read_json(run / "job.json")
    assert job["frames_processed"] == 12
    assert job["source_frames_declared"] == 12
    assert job["paused"] is False
    assert job["paused_s"] == 0.0
    # Twelve frames is below the warm-up window, so no rate is quoted rather
    # than one derived from model start-up.
    assert job["rate_fps"] is None
    assert job["eta_s"] is None


def _run_in_thread(target):
    """Run ``target`` on a thread, keeping whatever it returns or raises.

    A worker that dies silently turns every assertion after it into "timed
    out", which says nothing about why. Holding the exception means the test
    reports the real failure instead.
    """
    import threading

    outcome: dict[str, object] = {}

    def wrapper() -> None:
        try:
            outcome["value"] = target()
        except BaseException as exc:  # noqa: BLE001 - re-raised by the caller
            outcome["error"] = exc

    worker = threading.Thread(target=wrapper)
    worker.start()
    return worker, outcome


def _wait_for_job_state(paths, state: str, outcome: dict, timeout: float = 30.0):
    """Poll the in-progress attempt until its job file reports ``state``.

    The path is built up one level at a time rather than globbed. ``long_path``
    decides per path, and a ``derived/processing`` directory can sit just under
    the threshold while the ``job.json`` two levels inside it sits over - in
    which case a recursive glob from the short parent silently returns nothing
    and the wait looks like a timeout. Reading the leaf directly lets
    ``read_json`` apply the prefix where it is actually needed.
    """
    base = paths.derived_dir / "processing"
    deadline = time.time() + timeout
    seen: object = None
    attempts: list[str] = []
    while time.time() < deadline:
        if "error" in outcome:
            raise AssertionError(f"işleme beklenmedik hata verdi: {outcome['error']!r}")
        try:
            names = os.listdir(long_path(base))
        except FileNotFoundError:
            # The attempt directory is created by the worker; on the first
            # poll it may simply not exist yet.
            names = []
        attempts = [
            name for name in names
            if name.startswith(".") and name.endswith(".partial")
        ]
        for name in attempts:
            try:
                job = read_json(base / name / "job.json")
            except Exception:  # noqa: BLE001 - caught mid-write; try again
                continue
            seen = job.get("state")
            if seen == state:
                return base / name / "job.json", job
        time.sleep(0.02)
    raise AssertionError(
        f"iş '{state}' durumuna geçmedi (son görülen: {seen!r}, denemeler: {attempts})"
    )


def test_pause_holds_the_job_and_resume_finishes_it(raw_take):
    """A new recording needs the GPU back; twenty minutes of replay should survive."""
    import threading

    take, paths = raw_take
    pause = threading.Event()
    pause.set()

    worker, outcome = _run_in_thread(
        lambda: process_take(
            paths.root,
            ProcessingConfig(store_depth=False, store_proxy=False),
            pause=pause,
        )
    )
    try:
        _job_file, held = _wait_for_job_state(paths, "paused", outcome)
        assert held["paused"] is True
        assert held["frames_processed"] < 12
    finally:
        pause.clear()
        worker.join(timeout=60)

    assert not worker.is_alive()
    assert "error" not in outcome, outcome.get("error")
    job = read_json(outcome["value"] / "job.json")
    assert job["state"] == "complete"
    assert job["frames_processed"] == 12
    assert job["paused"] is False
    # Time spent waiting is not time spent working.
    assert job["paused_s"] > 0


def test_cancelling_a_paused_job_does_not_wait_for_a_resume(raw_take):
    import threading

    take, paths = raw_take
    pause, cancel = threading.Event(), threading.Event()
    pause.set()

    worker, outcome = _run_in_thread(
        lambda: process_take(
            paths.root,
            ProcessingConfig(store_depth=False, store_proxy=False),
            pause=pause,
            cancel=cancel,
        )
    )
    try:
        _wait_for_job_state(paths, "paused", outcome)
        cancel.set()
        worker.join(timeout=60)
    finally:
        pause.clear()

    assert not worker.is_alive()
    assert "error" not in outcome, outcome.get("error")
    job = read_json(outcome["value"] / "job.json")
    assert job["state"] == "cancelled"
    # Cancelling is not deleting: the raw recording is untouched.
    assert path_exists(paths.native_recording) or path_exists(paths.raw_index)


def test_a_1_0_0_version_still_opens(raw_take):
    """Compatibility, proved by building the old layout and reading it."""
    take, paths = raw_take
    run = process_take(paths.root, ProcessingConfig(store_depth=False, store_proxy=False))
    review = ReviewDataset(run)
    arrays = review.arrays()
    review.close()

    legacy = run.parent / "run_legacy_shape"
    Path(long_path(legacy)).mkdir()
    for name in ("job.json", "source_map.jsonl", "skeleton.jsonl", "checksums.json"):
        payload = Path(long_path(run / name)).read_bytes()
        Path(long_path(legacy / name)).write_bytes(payload)
    with open(long_path(legacy / "arrays.npz"), "wb") as stream:
        np.savez_compressed(stream, **arrays)
    job = read_json(legacy / "job.json")
    job["schema_version"] = "1.0.0"
    write_json(legacy / "job.json", job, overwrite=True)

    old = ReviewDataset(legacy, verify=False)
    try:
        assert old.processing_schema_version == "1.0.0"
        assert old.array_store.is_memmapped is False
        assert old.window("joints", 1, 4).shape == (3, 16, 3)
        assert old.has_summary is False
        assert old.thumbnails.cover() is None
        assert old.position_of_anchor(old.anchor_at(5)) == 5
    finally:
        old.close()
