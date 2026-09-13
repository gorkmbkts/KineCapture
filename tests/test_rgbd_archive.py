"""The immutable RGB-D archive: does it really keep what it promises?

The archive exists because replaying an SVO2 was measured not to return the
depth that was recorded. That makes these tests the ones standing between the
project and a dataset whose depth can never be reproduced - so they check the
bytes, not just the file names.
"""

from __future__ import annotations

import json
import time
import zlib
from pathlib import Path

import numpy as np
import pytest

from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import StorageError
from kinecapture.core.jsonio import read_json, read_jsonl
from kinecapture.domain.enums import TakeState
from kinecapture.recording.rgbd_archive import (
    COLOR_MAGIC,
    DEPTH_MAGIC,
    DepthCodec,
    QUANTISED_SCALE,
    RgbdArchiveReader,
    RgbdArchiveWriter,
    decode_depth_chunk,
    encode_depth_chunk,
    estimate_bytes_per_second,
    read_chunk,
    write_chunk,
)
from tests.conftest import paced_backend, record_take


def _depth_frames(count: int, height: int = 32, width: int = 48) -> list[np.ndarray]:
    """Frames shaped like real sensor output: smooth, noisy, partly invalid."""
    rng = np.random.default_rng(11)
    frames = []
    for index in range(count):
        base = np.linspace(0.8, 6.0, height, dtype=np.float32)[:, None]
        frame = (base * np.ones((1, width), np.float32)) + index * 0.01
        frame += rng.normal(0, 0.004, (height, width)).astype(np.float32)
        frame[rng.random((height, width)) < 0.06] = np.nan
        frames.append(frame)
    return frames


# ------------------------------------------------------------------ codec


def test_lossless_depth_survives_bit_for_bit() -> None:
    """Not "close enough": the same float32 bits, NaN pattern included."""
    frames = np.stack(_depth_frames(6))
    header, payload = encode_depth_chunk(frames, DepthCodec.FLOAT32_LOSSLESS)
    restored = decode_depth_chunk(header, payload)

    assert header["lossless"] is True
    assert np.array_equal(restored.view(np.uint32), frames.view(np.uint32))
    assert np.array_equal(np.isnan(restored), np.isnan(frames))


def test_infinities_and_negatives_survive_too() -> None:
    frames = np.zeros((2, 4, 4), dtype=np.float32)
    frames[0, 0, 0] = np.inf
    frames[0, 0, 1] = -np.inf
    frames[0, 1, 0] = np.nan
    frames[1, :, :] = -1.5
    header, payload = encode_depth_chunk(frames, DepthCodec.FLOAT32_LOSSLESS)
    restored = decode_depth_chunk(header, payload)
    assert np.array_equal(restored.view(np.uint32), frames.view(np.uint32))


def test_quantised_codec_declares_exactly_what_it_loses() -> None:
    """A lossy option is allowed - being quiet about it is not."""
    frames = np.stack(_depth_frames(4))
    header, payload = encode_depth_chunk(frames, DepthCodec.UINT16_QUANTISED)
    restored = decode_depth_chunk(header, payload)

    assert header["lossless"] is False
    assert header["scale_per_meter"] == QUANTISED_SCALE
    assert header["quantisation_step_m"] == pytest.approx(1.0 / QUANTISED_SCALE)
    assert "max_representable_m" in header
    assert np.array_equal(np.isnan(restored), np.isnan(frames))

    finite = np.isfinite(frames)
    error = np.abs(restored[finite] - frames[finite])
    assert error.max() <= 1.0 / QUANTISED_SCALE


def test_a_truncated_chunk_is_detected_not_silently_short(tmp_path) -> None:
    frames = np.stack(_depth_frames(4))
    header, payload = encode_depth_chunk(frames, DepthCodec.FLOAT32_LOSSLESS)
    path = tmp_path / "depth_000000.kcd"
    write_chunk(path, DEPTH_MAGIC, header, payload)

    data = path.read_bytes()
    path.write_bytes(data[: len(data) - 64])
    with pytest.raises(StorageError) as excinfo:
        read_chunk(path, DEPTH_MAGIC)
    assert excinfo.value.code == "rgbd_chunk_truncated"


def test_a_foreign_file_is_refused(tmp_path) -> None:
    path = tmp_path / "depth_000000.kcd"
    path.write_bytes(b"not a chunk\n")
    with pytest.raises(StorageError) as excinfo:
        read_chunk(path, DEPTH_MAGIC)
    assert excinfo.value.code == "rgbd_chunk_magic_mismatch"


def test_disk_estimate_scales_with_pixels_and_rate() -> None:
    small = estimate_bytes_per_second(
        width=640,
        height=360,
        fps=30,
        depth_codec=DepthCodec.FLOAT32_LOSSLESS,
        store_color=False,
        native_recording=False,
    )
    large = estimate_bytes_per_second(
        width=1280,
        height=720,
        fps=30,
        depth_codec=DepthCodec.FLOAT32_LOSSLESS,
        store_color=False,
        native_recording=False,
    )
    assert large["depth_mb_per_minute"] == pytest.approx(
        small["depth_mb_per_minute"] * 4, rel=1e-6
    )
    quantised = estimate_bytes_per_second(
        width=1280,
        height=720,
        fps=30,
        depth_codec=DepthCodec.UINT16_QUANTISED,
        store_color=False,
        native_recording=False,
    )
    assert quantised["depth_mb_per_minute"] < large["depth_mb_per_minute"]


# ---------------------------------------------------------------- writer


def test_writer_round_trips_every_frame(tmp_path) -> None:
    frames = _depth_frames(23)
    colours = [
        np.random.default_rng(i).integers(0, 255, (32, 48, 3)).astype(np.uint8)
        for i in range(23)
    ]
    writer = RgbdArchiveWriter(
        tmp_path, store_color=True, chunk_frames=7, workers=2
    )
    for position, (colour, depth) in enumerate(zip(colours, frames)):
        assert writer.add_frame(position, colour, depth) == (True, True)
    chunks = writer.close()

    assert writer.depth.frames_written == 23
    assert writer.depth.frames_dropped == 0
    assert writer.color.frames_written == 23
    # 23 frames in chunks of 7 leaves a short final chunk, which must exist.
    assert writer.depth.chunks_written == 4
    assert len(chunks) == 8

    reader = RgbdArchiveReader(tmp_path)
    restored = dict(reader.iter_depth())
    assert sorted(restored) == list(range(23))
    for position, frame in enumerate(frames):
        assert np.array_equal(
            restored[position].view(np.uint32), frame.view(np.uint32)
        )
    restored_colour = dict(reader.iter_color())
    for position, colour in enumerate(colours):
        assert np.array_equal(restored_colour[position], colour)
    assert reader.verify() == []


def test_reused_mutable_buffers_are_snapshotted_on_offer(tmp_path):
    writer = RgbdArchiveWriter(tmp_path, store_color=True, chunk_frames=3, workers=1)
    depth = np.empty((4, 6), dtype=np.float32)
    color = np.empty((4, 6, 3), dtype=np.uint8)
    for position in range(3):
        depth.fill(position + 0.25)
        color.fill(position + 10)
        writer.add_frame(position, color, depth)
    depth.fill(999)
    color.fill(255)
    writer.close()
    reader = RgbdArchiveReader(tmp_path)
    for position, frame in reader.iter_depth():
        np.testing.assert_array_equal(frame, np.full((4, 6), position + 0.25))
    for position, frame in reader.iter_color():
        np.testing.assert_array_equal(frame, np.full((4, 6, 3), position + 10))


def test_a_half_written_chunk_costs_only_that_chunk(tmp_path) -> None:
    """Recovery, not resilience theatre: the rest of the take stays readable."""
    writer = RgbdArchiveWriter(tmp_path, chunk_frames=5, workers=1)
    for position, depth in enumerate(_depth_frames(20)):
        writer.add_frame(position, None, depth)
    writer.close()

    victim = sorted(tmp_path.glob("depth_*.kcd"))[1]
    data = victim.read_bytes()
    victim.write_bytes(data[: len(data) // 2])

    reader = RgbdArchiveReader(tmp_path)
    problems = reader.verify()
    assert len(problems) == 1
    assert problems[0]["file"] == victim.name

    survived = []
    for path in reader.depth_chunks():
        try:
            header, _payload = read_chunk(path, DEPTH_MAGIC)
        except StorageError:
            continue
        survived.extend(header["positions"])
    # Three of four chunks are intact; only the damaged five frames are gone.
    assert len(survived) == 15


def test_overflow_is_counted_as_loss_rather_than_hidden(tmp_path, monkeypatch) -> None:
    writer = RgbdArchiveWriter(tmp_path, chunk_frames=2, workers=1)
    monkeypatch.setattr(writer._pool, "submit", lambda job: False)
    ok_color, ok_depth = True, True
    for position, depth in enumerate(_depth_frames(4)):
        ok_color, ok_depth = writer.add_frame(position, None, depth)
    writer.close()
    assert ok_depth is False
    assert writer.depth.frames_dropped > 0
    assert writer.has_loss


def test_reader_finds_one_frame_without_decoding_everything(tmp_path) -> None:
    frames = _depth_frames(12)
    writer = RgbdArchiveWriter(tmp_path, chunk_frames=4, workers=1)
    for position, depth in enumerate(frames):
        writer.add_frame(position, None, depth)
    writer.close()

    reader = RgbdArchiveReader(tmp_path)
    assert np.array_equal(
        reader.depth_at(7).view(np.uint32), frames[7].view(np.uint32)
    )
    assert reader.depth_at(99) is None


# ------------------------------------------------------- through a take


@pytest.fixture
def recorded(workspace, session):
    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=25)
    service.shutdown()
    return workspace, take


def test_a_finished_take_carries_a_verifiable_archive(recorded) -> None:
    workspace, take = recorded
    paths = workspace.take_paths(take)

    assert take.state is TakeState.FINALIZED
    assert take.metrics.depth_frames_archived == take.metrics.frames_written
    assert take.metrics.depth_frames_dropped == 0
    assert not take.metrics.has_raw_archive_loss

    reader = RgbdArchiveReader(paths.rgbd_dir)
    assert reader.verify() == []
    stored = reader.positions()
    assert len(stored["depth"]) == take.metrics.frames_written
    # The synthetic backend has no native recording, so colour is archived here.
    assert len(stored["color"]) == take.metrics.frames_written


def test_the_raw_manifest_states_what_svo2_does_not_hold(recorded) -> None:
    workspace, take = recorded
    manifest = read_json(workspace.take_paths(take).raw_manifest)

    assert manifest["schema_version"]
    native = manifest["native_recording"]
    assert "yeniden hesaplanır" in native["does_not_store"]
    assert "Final metrik derinlik ve iskelet" in native["does_not_store"]
    assert native["lossless"] is False  # This fixture explicitly uses legacy H264.
    depth = manifest["rgbd_archive"]["depth"]
    assert depth["lossless"] is True
    assert depth["unit"] == "meter"
    assert depth["invalid"] == "nan"
    assert manifest["synchronisation"]["position"]
    assert manifest["synchronisation"]["camera_frame_index"]


def test_the_sync_index_keeps_position_and_camera_index_apart(recorded) -> None:
    workspace, take = recorded
    paths = workspace.take_paths(take)
    records = [r for r in read_jsonl(paths.raw_index) if r.get("record") == "frame"]

    assert len(records) == take.metrics.frames_written
    positions = [int(r["p"]) for r in records]
    assert positions == list(range(len(records)))
    # The camera's own counter starts wherever the camera was; conflating the
    # two is the bug this index exists to prevent.
    assert all("i" in r and "cam_ns" in r and "host_ns" in r for r in records)
    assert all(r["depth"] and r["skel"] for r in records)


def test_archive_chunks_are_individually_checksummed(recorded) -> None:
    workspace, take = recorded
    paths = workspace.take_paths(take)
    manifest = read_json(paths.checksums)
    chunk_entries = [k for k in manifest["files"] if "rgbd/depth_" in k]
    assert chunk_entries
    assert all(manifest["files"][key]["checksum"] for key in chunk_entries)
    assert "raw/raw_capture_manifest.json" in manifest["files"]


def test_a_tampered_chunk_fails_integrity_verification(recorded) -> None:
    workspace, take = recorded
    paths = workspace.take_paths(take)
    from kinecapture.core.fingerprint import verify_checksum_manifest

    assert verify_checksum_manifest(read_json(paths.checksums), paths.root) == []

    victim = sorted(paths.rgbd_dir.glob("depth_*.kcd"))[0]
    data = bytearray(victim.read_bytes())
    data[-1] ^= 0xFF
    victim.write_bytes(bytes(data))

    problems = verify_checksum_manifest(read_json(paths.checksums), paths.root)
    assert any(p["issue"] == "checksum_mismatch" for p in problems)


def test_a_take_whose_archive_lost_frames_is_not_finalized(
    workspace, session, monkeypatch
) -> None:
    """The whole point: an unreprocessable recording must not look complete."""
    from kinecapture.recording import take_writer as module

    original = module.RgbdArchiveWriter.add_frame

    def lossy(self, position, color, depth):  # type: ignore[no-untyped-def]
        result = original(self, position, color, depth)
        if position == 3:
            self.depth.frames_dropped += 1
            return (result[0], False)
        return result

    monkeypatch.setattr(module.RgbdArchiveWriter, "add_frame", lossy)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=12)
    service.shutdown()

    assert take.metrics.depth_frames_dropped == 1
    assert take.metrics.has_raw_archive_loss
    assert take.state is TakeState.PARTIAL
    assert "Ham RGB-D arşivi eksik" in take.notes
    # Nothing was deleted: what did get written is still there.
    assert RgbdArchiveReader(workspace.take_paths(take).rgbd_dir).depth_chunks()


def test_a_native_recorder_that_will_not_stop_blocks_finalisation(
    workspace, session, monkeypatch
) -> None:
    from kinecapture.camera.mock import MockCameraBackend

    service = CaptureService(paced_backend())
    service.connect()
    service.start_preview()
    take = service.start_recording(workspace, session)
    deadline = time.time() + 10
    while service.recorded_frame_count < 8 and time.time() < deadline:
        time.sleep(0.005)

    def explode() -> None:
        raise RuntimeError("recorder wedged")

    monkeypatch.setattr(
        MockCameraBackend, "stop_native_recording", lambda self: explode()
    )
    take = service.stop_recording()
    service.shutdown()

    assert take.state is TakeState.PARTIAL
    assert "recorder wedged" in take.metrics.raw_archive_failure


def test_an_old_take_without_an_archive_still_reads(recorded) -> None:
    """Reading a pre-archive recording reports the gap; it does not invent one."""
    workspace, take = recorded
    paths = workspace.take_paths(take)
    for path in list(paths.rgbd_dir.iterdir()):
        path.unlink()
    paths.raw_manifest.unlink()

    reader = RgbdArchiveReader(paths.rgbd_dir)
    assert reader.depth_chunks() == []
    assert reader.positions() == {"depth": [], "color": []}
    assert reader.verify() == []

    from kinecapture.playback.take_reader import load_take

    loaded = load_take(workspace, take, with_video=False)
    assert loaded.frame_count == take.metrics.frames_written


def test_disk_precheck_refuses_rather_than_degrading(workspace, session, monkeypatch):
    """Never solve a full disk by quietly lowering the resolution."""
    service = CaptureService(paced_backend())
    service.connect()
    service.start_preview()

    monkeypatch.setattr(
        CaptureService,
        "raw_archive_estimate",
        lambda self, sess=None: {
            "total_mb_per_minute": 3534.0,
            "free_bytes": 1_000_000,
            "free_minutes": 0.02,
            "depth_lossless": True,
            "color_source": "rgbd_chunks",
            "archives_depth": True,
        },
    )
    with pytest.raises(StorageError) as excinfo:
        service.start_recording(workspace, session)
    assert excinfo.value.code == "insufficient_disk_space"
    assert "sessizce düşürülmez" in (excinfo.value.remedy or "")
    service.shutdown()


def test_extraction_tool_verifies_and_extracts_without_touching_raw(
    recorded, tmp_path
) -> None:
    workspace, take = recorded
    paths = workspace.take_paths(take)
    from kinecapture.tools.extract_raw import main

    before = {
        path: path.read_bytes()
        for path in sorted(paths.rgbd_dir.iterdir())
        if path.is_file()
    }
    assert main([str(paths.root), "--verify"]) == 0

    out = tmp_path / "extracted"
    assert main([str(paths.root), "--out", str(out), "--range", "2", "6"]) == 0
    payload = np.load(next(out.glob("*.npz")))
    assert payload["positions"].tolist() == [2, 3, 4, 5, 6]
    assert payload["depth_m"].shape[0] == 5
    assert payload["depth_m"].dtype == np.float32

    manifest = read_json(out / "extraction_manifest.json")
    assert manifest["raw_untouched"] is True
    assert "ölçülen derinlik" in manifest["depth_source"]
    for path, content in before.items():
        assert path.read_bytes() == content
