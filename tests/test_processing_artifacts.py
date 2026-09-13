"""The derived artefacts a review screen needs, and the promise that old runs
still open.

Processing 1.1.0 changes what a version looks like on disk. The tests that
matter most here are the ones proving that change did not strand anything: a
1.0.0 run, with its single ``arrays.npz`` and no summary or previews, must
still open and answer every question the new API asks of it.

No Qt and no SDK: everything below runs on arrays written by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from kinecapture.processing.arrays import ArrayStore, write_arrays
from kinecapture.processing.depth import DepthReader
from kinecapture.processing.summary import (
    FLAG_CAPTURE_UNMATCHED,
    FLAG_INTEGRITY_ISSUE,
    TimelineSummary,
    build_summary,
)
from kinecapture.processing.thumbnails import (
    ThumbnailIndex,
    build_thumbnails,
    planned_positions,
)
from kinecapture.recording.rgbd_archive import (
    DEPTH_MAGIC,
    DepthCodec,
    encode_depth_chunk,
    read_chunk_header,
    write_chunk,
)


# --------------------------------------------------------------------- arrays


@pytest.fixture
def arrays() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(7)
    frames = 300
    return {
        "joints": rng.standard_normal((frames, 16, 3)).astype(np.float32),
        "confidences": rng.random((frames, 16)).astype(np.float32),
        "camera_timestamps_ns": np.arange(frames, dtype=np.int64) * 33_333_333,
        "subject_present": (np.arange(frames) % 7 != 0),
    }


def test_arrays_round_trip(tmp_path: Path, arrays) -> None:
    write_arrays(tmp_path, arrays)
    with ArrayStore(tmp_path) as store:
        assert set(store.keys) == set(arrays)
        for key, expected in arrays.items():
            np.testing.assert_array_equal(store[key], expected)


def test_arrays_are_memory_mapped(tmp_path: Path, arrays) -> None:
    """The whole point: a window read must not materialise the session."""
    write_arrays(tmp_path, arrays)
    with ArrayStore(tmp_path) as store:
        assert store.is_memmapped is True
        mapped = store.memmap("joints")
        assert isinstance(mapped, np.memmap)


def test_window_returns_an_owned_copy(tmp_path: Path, arrays) -> None:
    """The caller may keep a window after the store is closed."""
    write_arrays(tmp_path, arrays)
    store = ArrayStore(tmp_path)
    window = store.window("joints", 10, 20)
    store.close()
    assert window.shape == (10, 16, 3)
    np.testing.assert_array_equal(window, arrays["joints"][10:20])


def test_window_clamps_instead_of_raising(tmp_path: Path, arrays) -> None:
    """A timeline asks for the range it is showing, which can run off the end."""
    write_arrays(tmp_path, arrays)
    with ArrayStore(tmp_path) as store:
        assert store.window("joints", -50, 5).shape[0] == 5
        assert store.window("joints", 290, 400).shape[0] == 10
        assert store.window("joints", 500, 600).shape[0] == 0


def test_frames_is_the_time_axis(tmp_path: Path, arrays) -> None:
    write_arrays(tmp_path, arrays)
    with ArrayStore(tmp_path) as store:
        assert store.frames == 300


def test_a_1_0_0_run_still_opens(tmp_path: Path, arrays) -> None:
    """The compatibility promise: an old version loses nothing."""
    with open(tmp_path / "arrays.npz", "wb") as stream:
        np.savez_compressed(stream, **arrays)
    with ArrayStore(tmp_path) as store:
        # Honest about the cost rather than pretending the window is cheap.
        assert store.is_memmapped is False
        assert set(store.keys) == set(arrays)
        np.testing.assert_array_equal(store.window("joints", 3, 8), arrays["joints"][3:8])
        assert store.frames == 300


def test_a_directory_with_no_arrays_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ArrayStore(tmp_path)


# -------------------------------------------------------------------- summary


@pytest.fixture
def signals():
    frames = 1000
    present = np.ones(frames, dtype=bool)
    present[400:410] = False
    confidence = np.full(frames, 0.9, dtype=np.float32)
    confidence[123] = 0.1
    confidence[400:410] = np.nan
    flags = np.zeros(frames, dtype=np.uint8)
    flags[777] = FLAG_INTEGRITY_ISSUE
    flags[10] = FLAG_CAPTURE_UNMATCHED
    return present, confidence, flags


def test_summary_levels_halve(tmp_path: Path, signals) -> None:
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags, fps=30.0)
    summary = TimelineSummary(tmp_path)
    assert summary.frames == 1000
    assert summary.bin_sizes[0] == 1
    assert list(summary.bin_sizes) == sorted(summary.bin_sizes)
    for previous, size in zip(summary.bin_sizes, summary.bin_sizes[1:]):
        assert size == previous * 2


def test_a_single_bad_frame_survives_every_zoom_level(tmp_path: Path, signals) -> None:
    """The reason min and max are both kept.

    A mean would average one 0.1 frame into a second of 0.9 and the lane would
    show nothing - which is exactly the frame the annotator is looking for.
    """
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    for level in range(len(summary.bin_sizes)):
        arrays = summary._load(level)
        assert np.nanmin(arrays["confidence_min"]) == pytest.approx(0.1, abs=1e-6)


def test_a_qc_flag_survives_every_zoom_level(tmp_path: Path, signals) -> None:
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    assert summary.flags_present(FLAG_INTEGRITY_ISSUE)
    assert summary.flags_present(FLAG_CAPTURE_UNMATCHED)
    assert not summary.flags_present(1 << 7)


def test_absence_stays_distinguishable_from_zero(tmp_path: Path, signals) -> None:
    """An unmeasured bin is NaN, not 0.0. They mean different things."""
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    arrays = summary._load(0)
    assert np.isnan(arrays["confidence_min"][405])
    assert arrays["present_any"][405] == 0
    assert arrays["present_all"][399] == 1


def test_level_is_chosen_so_bins_are_about_a_pixel(tmp_path: Path, signals) -> None:
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    # 1000 frames across 1000 pixels: one frame per pixel, finest level.
    assert summary.level_for(1000, 1000) == 0
    # The same 1000 frames across 100 pixels: ten frames per bin.
    coarse = summary.level_for(1000, 100)
    assert summary.bin_sizes[coarse] <= 10


def test_lane_returns_a_contiguous_slice(tmp_path: Path, signals) -> None:
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    lane = summary.lane(view_start=200, view_span=100, pixels=100)
    assert lane["bins"] > 0
    assert lane["start_frame"] <= 200
    assert len(lane["confidence_min"]) == lane["bins"]
    assert len(lane["present_any"]) == lane["bins"]


def test_lane_never_reads_the_whole_take(tmp_path: Path, signals) -> None:
    """What buys the repaint budget: the slice is the view, not the session."""
    present, confidence, flags = signals
    build_summary(tmp_path, present=present, confidence=confidence, flags=flags)
    summary = TimelineSummary(tmp_path)
    lane = summary.lane(view_start=100, view_span=50, pixels=50)
    assert lane["bins"] < 60


def test_summary_rejects_mismatched_lengths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_summary(tmp_path, present=np.ones(10, bool), confidence=np.ones(9, np.float32))


# ----------------------------------------------------------------- thumbnails


def test_planned_positions_always_include_the_ends_and_middle() -> None:
    positions = planned_positions(1000, count=5)
    assert 0 in positions
    assert 999 in positions
    assert 500 in positions
    assert positions == sorted(set(positions))


def test_planned_positions_handle_tiny_takes() -> None:
    assert planned_positions(0) == []
    assert planned_positions(1) == [0]
    assert all(0 <= p < 3 for p in planned_positions(3))


def test_missing_video_is_reported_not_crashed(tmp_path: Path) -> None:
    index = build_thumbnails(tmp_path, tmp_path / "nope.mp4", frames=100)
    assert index["entries"] == []
    assert "üretilmedi" in index["unavailable_reason"]
    assert ThumbnailIndex(tmp_path).cover() is None


def test_thumbnails_are_written_and_readable(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    video = tmp_path / "proxy.mp4"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (160, 90)
    )
    if not writer.isOpened():  # pragma: no cover - depends on local codecs
        pytest.skip("mp4v kodlayıcı yok")
    for index in range(60):
        frame = np.full((90, 160, 3), index * 4 % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    document = build_thumbnails(tmp_path, video, frames=60, count=5, width=64)
    assert document["unavailable_reason"] == ""
    assert document["entries"]

    index = ThumbnailIndex(tmp_path)
    assert 0 in index.positions
    assert index.cover() is not None
    assert index.cover().is_file()
    image = cv2.imread(str(index.cover()))
    assert image is not None
    assert image.shape[1] == 64
    # Nearest, not exact: the library asks for "around here", not a frame id.
    assert index.nearest(10_000) is not None


# ---------------------------------------------------------------------- depth


def _write_depth(directory: Path, blocks: list[tuple[list[int], np.ndarray]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for order, (positions, frames) in enumerate(blocks):
        header, payload = encode_depth_chunk(frames, DepthCodec.FLOAT32_LOSSLESS)
        header.update(positions=positions, stream="depth", chunk_index=order)
        write_chunk(directory / f"depth_{order:06d}.kcd", DEPTH_MAGIC, header, payload)


def test_depth_reader_indexes_by_position(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    first = rng.standard_normal((4, 6, 8)).astype(np.float32)
    second = rng.standard_normal((4, 6, 8)).astype(np.float32)
    _write_depth(tmp_path, [([0, 1, 2, 3], first), ([4, 5, 6, 7], second)])

    reader = DepthReader(tmp_path)
    assert reader.is_available
    assert reader.positions == (0, 1, 2, 3, 4, 5, 6, 7)
    assert reader.shape == (6, 8)
    np.testing.assert_array_equal(reader.at(5), second[1])
    assert reader.at(99) is None
    assert reader.nearest_position(99) == 7
    assert reader.provenance == "reconstructed_offline"


def test_depth_reader_keeps_non_finite_pixels(tmp_path: Path) -> None:
    """Unmeasured stays unmeasured; filling it in would invent a measurement."""
    block = np.full((2, 4, 4), np.nan, dtype=np.float32)
    block[0, 0, 0] = 1.5
    _write_depth(tmp_path, [([0, 1], block)])
    frame = DepthReader(tmp_path).at(0)
    assert frame[0, 0] == pytest.approx(1.5)
    assert np.isnan(frame[1, 1])


def test_empty_directory_is_not_an_error(tmp_path: Path) -> None:
    reader = DepthReader(tmp_path)
    assert reader.is_available is False
    assert reader.at(0) is None
    assert reader.nearest_position(0) is None


def test_header_only_read_does_not_touch_the_payload(tmp_path: Path) -> None:
    """Indexing must not decompress the recording it is indexing."""
    frames = np.zeros((3, 4, 4), dtype=np.float32)
    _write_depth(tmp_path, [([9, 10, 11], frames)])
    header = read_chunk_header(tmp_path / "depth_000000.kcd", DEPTH_MAGIC)
    assert header["positions"] == [9, 10, 11]
    assert header["count"] == 3
