from pathlib import Path
from threading import Event
from dataclasses import replace
import numpy as np
import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.jsonio import read_json, write_json, read_jsonl
from kinecapture.core.paths import long_path
from kinecapture.domain.project import CaptureProfile
from kinecapture.domain.enums import TakeState
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.processing import ProcessingConfig, process_take, restart_job
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
    assert not paths.skeleton_stream.exists()
    assert not paths.proxy_video.exists()
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
    assert first != second and first.exists()
    review = ReviewDataset(second)
    assert len(review.mapping) == 12
    arrays = review.arrays()
    assert arrays["joints"].shape == (12, 16, 3)
    assert not arrays["subject_present"].any()  # no implicit best-body identity
    anchor = review.anchor_at(4)
    assert review.position_of_anchor(anchor) == 4
    target = review.save_annotations([{"exercise": "squat", "start": anchor, "end": review.anchor_at(8)}])
    assert target.exists() and not paths.segments.exists()
    with pytest.raises(ValueError, match="another raw source"):
        review.position_of_anchor({**anchor, "source_fingerprint": "wrong"})


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


@pytest.mark.parametrize("fault", ["count", "timestamp", "position", "exception"])
def test_fault_never_publishes_complete(raw_take, fault):
    _, paths = raw_take
    class Broken(SyntheticSource):
        def __iter__(self):
            for i, packet in enumerate(super().__iter__()):
                if fault == "count" and i == 9: return
                if fault == "exception" and i == 3: raise RuntimeError("injected decoder error")
                if i == 4 and fault == "timestamp": packet = replace(packet, camera_timestamp_ns=7)
                if i == 4 and fault == "position": packet = replace(packet, source_position=7)
                yield packet
    partial = process_take(paths.root, ProcessingConfig(store_proxy=False, store_depth=False), source_factory=Broken)
    assert read_json(partial / "job.json")["state"] in ("partial", "failed")
    with pytest.raises(ValueError, match="complete"):
        ReviewDataset(partial)


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
