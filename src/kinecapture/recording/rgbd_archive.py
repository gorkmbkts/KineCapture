"""The raw RGB-D archive: the part of a take that can never be recomputed.

Why this module exists at all
----------------------------
It was measured on this machine, with this SDK, that **replaying an SVO2 does
not reproduce the depth that was measured live**. Re-opening a freshly written
``capture.svo2`` and retrieving ``MEASURE.DEPTH`` at the same positions gives a
map that differs from the live one by metres in places, and whose invalid-pixel
mask is not even the same. SVO2 stores the *stereo images*; depth is a neural
reconstruction performed at read time, and it depends on the depth mode, the
SDK version and the GPU.

So an SVO2 alone is not an archive of what the camera measured. If the depth
that the skeleton was derived from is to survive, it has to be written down.
That is what this module does.

What it costs, measured rather than guessed
-------------------------------------------
720p float32 depth is 3.69 MB per frame - 6.6 GB/min raw. On real ZED depth:

===============================================  =========  ==========
scheme                                            MB/min     lossless
===============================================  =========  ==========
byteshuffle + zlib-1                                 3534    yes
temporal XOR + byteshuffle + zlib-1                  3286    yes
uint16 at 1/4000 m + byteshuffle + zlib-1            1612    no (0.13 mm)
===============================================  =========  ==========

Lossless compresses badly because the data really is that fine-grained: a
single frame carried 196010 distinct values in a 200000-pixel sample, with a
median spacing of 9 micrometres. There is no free win here, so the default
keeps the measurement intact and the cost is shown to the user before
recording rather than being solved by throwing data away.

Encoding one frame costs ~68 ms on one core, so a single thread sustains only
~15 fps. ``zlib`` releases the GIL, and three worker threads measured 38 fps,
which is why chunks are compressed on a small pool.

Layout on disk
--------------
``raw/rgbd/depth_000000.kcd``
    A chunk of consecutive depth frames, self-describing and independently
    decodable. A chunk lost to a power cut costs that chunk, not the take.
``raw/rgbd/color_000000.kcc``
    The same for colour, used only when the backend has no native recording
    (the synthetic backend, or a ZED whose SVO2 failed to start).
``raw/rgbd/index.jsonl``
    One line per recorded frame, mapping the recording-local position to the
    camera frame number, both timestamps, and which streams actually got it.

Chunk files start with a magic line and a JSON header, so a reader never has to
guess a shape, a dtype, a scale or a compression scheme.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import zlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator, Optional

import numpy as np

from kinecapture.core.errors import StorageError
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.domain.arrays import retain_snapshot

logger = get_logger(__name__)

#: First line of every chunk file. The version is part of the contract.
DEPTH_MAGIC = b"KCRGBD-DEPTH-1"
COLOR_MAGIC = b"KCRGBD-COLOR-1"

#: Frames per chunk. Half a second at 30 fps: small enough that a lost chunk is
#: a small loss, large enough that per-chunk overhead stays negligible.
DEFAULT_CHUNK_FRAMES = 15

#: Compression workers. Three measured 38 fps on 720p depth, above the 30 fps
#: the camera delivers.
DEFAULT_WORKERS = 3

#: How long a producer waits for a slot before calling the frame lost.
_ENQUEUE_TIMEOUT_S = 0.5
_CLOSE_TIMEOUT_S = 30.0


class DepthCodec(str, Enum):
    """How a depth chunk is stored.

    ``FLOAT32_LOSSLESS`` keeps the measurement bit for bit, NaN included.
    ``UINT16_QUANTISED`` is offered because lossless depth costs 3.5 GB/min and
    some studies cannot afford that - but it is *labelled* lossy everywhere,
    carries its scale and its invalid sentinel in the chunk header, and clips
    beyond its range instead of wrapping.
    """

    FLOAT32_LOSSLESS = "float32_byteshuffle_zlib"
    UINT16_QUANTISED = "uint16_scaled_byteshuffle_zlib"

    @property
    def is_lossless(self) -> bool:
        return self is DepthCodec.FLOAT32_LOSSLESS

    @property
    def label(self) -> str:
        return {
            DepthCodec.FLOAT32_LOSSLESS: "float32 kayıpsız",
            DepthCodec.UINT16_QUANTISED: "uint16 nicemlenmiş (kayıplı)",
        }[self]

    @property
    def megabytes_per_minute_720p(self) -> float:
        """Measured on real ZED depth at 720p/30, for the disk estimate."""
        return {
            DepthCodec.FLOAT32_LOSSLESS: 3534.0,
            DepthCodec.UINT16_QUANTISED: 1612.0,
        }[self]


#: Steps per metre for the quantised codec. 1/4000 m is 0.25 mm; measured
#: worst-case error on real depth was 0.126 mm, and 0.12% of pixels sat beyond
#: the 16.38 m the 16-bit range reaches and were clipped.
QUANTISED_SCALE = 4000.0
#: Reserved code for "no depth here". Never a real distance.
QUANTISED_INVALID = 0


def _shuffle(array: np.ndarray) -> bytes:
    """Group byte 0 of every value, then byte 1, and so on.

    Float32 depth is nearly constant in its exponent bits and noisy in its low
    mantissa bits. Interleaved, a generic compressor sees noise everywhere;
    de-interleaved, the high-order planes become long runs. Measured: 1.29x
    without, 1.88x with.
    """
    raw = np.ascontiguousarray(array).view(np.uint8).reshape(-1, array.dtype.itemsize)
    return raw.transpose(1, 0).tobytes()


def _unshuffle(payload: bytes, count: int, dtype: Any) -> np.ndarray:
    width = np.dtype(dtype).itemsize
    planes = np.frombuffer(payload, dtype=np.uint8).reshape(width, count)
    return planes.transpose(1, 0).copy().view(dtype).reshape(-1)


def encode_depth_chunk(
    frames: np.ndarray, codec: DepthCodec
) -> tuple[dict[str, Any], bytes]:
    """Compress ``[N, H, W] float32`` metres into a header and a payload."""
    block = np.ascontiguousarray(frames, dtype=np.float32)
    header: dict[str, Any] = {
        "codec": codec.value,
        "lossless": codec.is_lossless,
        "count": int(block.shape[0]),
        "height": int(block.shape[1]),
        "width": int(block.shape[2]),
        "unit": "meter",
        "byteshuffle": True,
        "compression": "zlib",
        "compression_level": 1,
    }
    if codec is DepthCodec.FLOAT32_LOSSLESS:
        header["dtype"] = "float32"
        header["invalid"] = "nan"
        payload = zlib.compress(_shuffle(block), 1)
    else:
        finite = np.isfinite(block)
        quantised = np.where(
            finite,
            np.clip(np.rint(block * QUANTISED_SCALE), 1, 65535),
            QUANTISED_INVALID,
        ).astype(np.uint16)
        header["dtype"] = "uint16"
        header["scale_per_meter"] = QUANTISED_SCALE
        header["invalid_value"] = QUANTISED_INVALID
        header["quantisation_step_m"] = 1.0 / QUANTISED_SCALE
        header["max_representable_m"] = 65535.0 / QUANTISED_SCALE
        header["clipped_pixels"] = int(
            (finite & (block * QUANTISED_SCALE > 65535)).sum()
        )
        payload = zlib.compress(_shuffle(quantised), 1)
    return header, payload


def decode_depth_chunk(header: dict[str, Any], payload: bytes) -> np.ndarray:
    """Inverse of :func:`encode_depth_chunk`, back to ``[N, H, W]`` metres."""
    count = int(header["count"])
    height, width = int(header["height"]), int(header["width"])
    total = count * height * width
    raw = zlib.decompress(payload)
    if header["dtype"] == "float32":
        values = _unshuffle(raw, total, np.float32)
        return values.reshape(count, height, width)
    values = _unshuffle(raw, total, np.uint16).reshape(count, height, width)
    scale = float(header["scale_per_meter"])
    invalid = int(header.get("invalid_value", QUANTISED_INVALID))
    result = values.astype(np.float32) / np.float32(scale)
    result[values == invalid] = np.nan
    return result


def encode_color_chunk(frames: np.ndarray) -> tuple[dict[str, Any], bytes]:
    """Compress ``[N, H, W, 3] uint8`` RGB losslessly.

    PNG is used when OpenCV is available because it is a well-understood
    lossless image codec that any consumer can read; otherwise the raw bytes
    are byte-shuffled and deflated, which is slower to read but needs nothing
    beyond the standard library.
    """
    block = np.ascontiguousarray(frames, dtype=np.uint8)
    header: dict[str, Any] = {
        "count": int(block.shape[0]),
        "height": int(block.shape[1]),
        "width": int(block.shape[2]),
        "channels": int(block.shape[3]),
        "dtype": "uint8",
        "colour_order": "rgb",
        "lossless": True,
    }
    try:
        import cv2  # noqa: PLC0415 - optional at runtime
    except ImportError:
        header["codec"] = "raw_byteshuffle_zlib"
        header["compression"] = "zlib"
        return header, zlib.compress(_shuffle(block.reshape(-1)), 1)

    parts: list[bytes] = []
    sizes: list[int] = []
    for index in range(block.shape[0]):
        bgr = block[index][:, :, ::-1]
        ok, encoded = cv2.imencode(".png", bgr, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if not ok:  # pragma: no cover - codec dependent
            header["codec"] = "raw_byteshuffle_zlib"
            header["compression"] = "zlib"
            return header, zlib.compress(_shuffle(block.reshape(-1)), 1)
        data = encoded.tobytes()
        parts.append(data)
        sizes.append(len(data))
    header["codec"] = "png_sequence"
    header["frame_sizes"] = sizes
    return header, b"".join(parts)


def decode_color_chunk(header: dict[str, Any], payload: bytes) -> np.ndarray:
    count = int(header["count"])
    height, width = int(header["height"]), int(header["width"])
    channels = int(header.get("channels", 3))
    if header["codec"] == "png_sequence":
        import cv2  # noqa: PLC0415 - written by a build that had it

        result = np.zeros((count, height, width, channels), dtype=np.uint8)
        offset = 0
        for index, size in enumerate(header["frame_sizes"]):
            buffer = np.frombuffer(payload[offset : offset + size], dtype=np.uint8)
            bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            result[index] = bgr[:, :, ::-1]
            offset += size
        return result
    total = count * height * width * channels
    values = _unshuffle(zlib.decompress(payload), total, np.uint8)
    return values.reshape(count, height, width, channels)


def write_chunk(path: Path, magic: bytes, header: dict[str, Any], payload: bytes) -> None:
    """Write one self-describing chunk file.

    Not atomic on purpose: a chunk is an append-only artefact of a recording in
    progress, and a half-written one has to be *detectable*, which it is - the
    header states how many bytes the payload should be. Metadata that must be
    atomic goes through ``jsonio`` instead.
    """
    body = json.dumps(header, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ensure_dir(path.parent)
    with open(long_path(path), "wb") as stream:
        stream.write(magic + b"\n")
        stream.write(str(len(body)).encode("ascii") + b"\n")
        stream.write(body)
        stream.write(b"\n")
        stream.write(str(len(payload)).encode("ascii") + b"\n")
        stream.write(payload)
        stream.flush()


def read_chunk(path: Path, expected_magic: bytes) -> tuple[dict[str, Any], bytes]:
    """Read one chunk, refusing a truncated or foreign file."""
    with open(long_path(path), "rb") as stream:
        magic = stream.readline().strip()
        if magic != expected_magic:
            raise StorageError(
                f"Beklenmeyen chunk biçimi: {path.name}",
                code="rgbd_chunk_magic_mismatch",
                details={"path": str(path), "magic": magic.decode("latin-1")},
            )
        header_length = int(stream.readline().strip())
        header = json.loads(stream.read(header_length).decode("utf-8"))
        stream.readline()
        payload_length = int(stream.readline().strip())
        payload = stream.read(payload_length)
    if len(payload) != payload_length:
        raise StorageError(
            f"Chunk yarım kalmış: {path.name} "
            f"({len(payload)}/{payload_length} bayt)",
            code="rgbd_chunk_truncated",
            remedy="Bu chunk kurtarılamaz; kaydın geri kalanı okunabilir.",
            details={"path": str(path)},
        )
    return header, payload


@dataclass
class StreamStats:
    """What actually happened to one raw stream."""

    frames_offered: int = 0
    frames_written: int = 0
    frames_dropped: int = 0
    chunks_written: int = 0
    bytes_written: int = 0
    failure: str = ""

    @property
    def has_loss(self) -> bool:
        return self.frames_dropped > 0 or bool(self.failure)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frames_offered": self.frames_offered,
            "frames_written": self.frames_written,
            "frames_dropped": self.frames_dropped,
            "chunks_written": self.chunks_written,
            "bytes_written": self.bytes_written,
            "failure": self.failure,
        }


class _ChunkPool:
    """A tiny bounded worker pool that compresses and writes chunks.

    Bounded on purpose: an unbounded queue would hide a disk that cannot keep
    up by silently growing in RAM until the machine died. When the bound is
    reached the producer waits briefly and then counts the frames lost, which
    is a fact the take carries rather than a surprise.
    """

    def __init__(self, workers: int, capacity: int) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=max(1, capacity))
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._errors: list[str] = []
        self._threads = [
            threading.Thread(target=self._run, name=f"kc-rgbd-{index}", daemon=True)
            for index in range(max(1, workers))
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, job) -> bool:  # type: ignore[no-untyped-def]
        if self._stopping.is_set():
            raise StorageError("Chunk kuyruğu kapatılıyor.", code="chunk_pool_closed")
        try:
            self._queue.put(job, timeout=_ENQUEUE_TIMEOUT_S)
        except queue.Full:
            return False
        return True

    def _run(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=0.05)
            except queue.Empty:
                if self._stopping.is_set():
                    return
                continue
            try:
                try:
                    job()
                except Exception as exc:  # a writer failure must be visible
                    with self._lock:
                        self._errors.append(f"{type(exc).__name__}: {exc}")
                    logger.error("RGB-D chunk yazımı başarısız: %s", exc)
            finally:
                self._queue.task_done()

    def close(self) -> list[str]:
        self._stopping.set()
        deadline = time.monotonic() + _CLOSE_TIMEOUT_S
        for thread in self._threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        if any(thread.is_alive() for thread in self._threads):
            raise StorageError(
                "Depth/renk yazıcıları henüz durmadı; arşiv tamamlanmış sayılmadı.",
                code="archive_close_pending",
            )
        with self._lock:
            return list(self._errors)


class RgbdArchiveWriter:
    """Persists the exact colour and depth a recording measured.

    Colour is required for the synthetic backend and otherwise optional.
    Measured live depth is an explicitly selected product; a reconstruction
    made later from stereo source belongs to a separate processing version.
    """

    def __init__(
        self,
        directory: Path,
        *,
        depth_codec: DepthCodec = DepthCodec.FLOAT32_LOSSLESS,
        store_color: bool = False,
        chunk_frames: int = DEFAULT_CHUNK_FRAMES,
        workers: int = DEFAULT_WORKERS,
        max_pending_chunks: int = 4,
    ) -> None:
        self.directory = Path(directory)
        self.depth_codec = depth_codec
        self.store_color = bool(store_color)
        self.chunk_frames = max(1, int(chunk_frames))
        self.depth = StreamStats()
        self.color = StreamStats()

        ensure_dir(self.directory)
        self._pool = _ChunkPool(workers, max_pending_chunks)
        self._lock = threading.Lock()
        self._depth_buffer: list[np.ndarray] = []
        self._depth_positions: list[int] = []
        self._color_buffer: list[np.ndarray] = []
        self._color_positions: list[int] = []
        self._depth_chunk_index = 0
        self._color_chunk_index = 0
        self._chunk_records: list[dict[str, Any]] = []
        self._closed = False

    # ------------------------------------------------------------- writing
    def add_frame(
        self,
        position: int,
        color: Optional[np.ndarray],
        depth: Optional[np.ndarray],
    ) -> tuple[bool, bool]:
        """Offer one frame's raw payloads. Returns ``(colour ok, depth ok)``."""
        if self._closed:
            raise StorageError(
                "Kapatılmış RGB-D arşivine yazılamaz.", code="rgbd_writer_closed"
            )
        depth_ok = True
        color_ok = True

        if depth is not None:
            self.depth.frames_offered += 1
            self._depth_buffer.append(retain_snapshot(depth, np.float32))
            self._depth_positions.append(int(position))
            if len(self._depth_buffer) >= self.chunk_frames:
                depth_ok = self._flush_depth()

        if self.store_color and color is not None:
            self.color.frames_offered += 1
            self._color_buffer.append(retain_snapshot(color, np.uint8))
            self._color_positions.append(int(position))
            if len(self._color_buffer) >= self.chunk_frames:
                color_ok = self._flush_color()
        return color_ok, depth_ok

    def _flush_depth(self) -> bool:
        if not self._depth_buffer:
            return True
        block = np.stack(self._depth_buffer)
        positions = list(self._depth_positions)
        index = self._depth_chunk_index
        self._depth_buffer = []
        self._depth_positions = []
        self._depth_chunk_index += 1

        path = self.directory / f"depth_{index:06d}.kcd"

        def job() -> None:
            header, payload = encode_depth_chunk(block, self.depth_codec)
            header["chunk_index"] = index
            header["stream"] = "depth"
            header["first_position"] = positions[0]
            header["positions"] = positions
            write_chunk(path, DEPTH_MAGIC, header, payload)
            with self._lock:
                self.depth.frames_written += len(positions)
                self.depth.chunks_written += 1
                self.depth.bytes_written += Path(long_path(path)).stat().st_size
                self._chunk_records.append(
                    {
                        "stream": "depth",
                        "chunk_index": index,
                        "file": f"rgbd/{path.name}",
                        "frames": len(positions),
                        "first_position": positions[0],
                        "last_position": positions[-1],
                    }
                )

        if not self._pool.submit(job):
            self.depth.frames_dropped += len(positions)
            logger.error(
                "Derinlik chunk kuyruğu doldu; %d kare kaybedildi.", len(positions)
            )
            return False
        return True

    def _flush_color(self) -> bool:
        if not self._color_buffer:
            return True
        block = np.stack(self._color_buffer)
        positions = list(self._color_positions)
        index = self._color_chunk_index
        self._color_buffer = []
        self._color_positions = []
        self._color_chunk_index += 1

        path = self.directory / f"color_{index:06d}.kcc"

        def job() -> None:
            header, payload = encode_color_chunk(block)
            header["chunk_index"] = index
            header["stream"] = "color"
            header["first_position"] = positions[0]
            header["positions"] = positions
            write_chunk(path, COLOR_MAGIC, header, payload)
            with self._lock:
                self.color.frames_written += len(positions)
                self.color.chunks_written += 1
                self.color.bytes_written += Path(long_path(path)).stat().st_size
                self._chunk_records.append(
                    {
                        "stream": "color",
                        "chunk_index": index,
                        "file": f"rgbd/{path.name}",
                        "frames": len(positions),
                        "first_position": positions[0],
                        "last_position": positions[-1],
                    }
                )

        if not self._pool.submit(job):
            self.color.frames_dropped += len(positions)
            logger.error(
                "Renk chunk kuyruğu doldu; %d kare kaybedildi.", len(positions)
            )
            return False
        return True

    # ------------------------------------------------------------ shutdown
    def close(self) -> list[dict[str, Any]]:
        """Flush the partial chunks, stop the pool, return the chunk table."""
        if self._closed:
            return list(self._chunk_records)
        self._flush_depth()
        self._flush_color()
        errors = self._pool.close()
        self._closed = True
        if errors:
            message = "; ".join(errors[:3])
            self.depth.failure = self.depth.failure or message
            if self.store_color:
                self.color.failure = self.color.failure or message
        return sorted(
            self._chunk_records, key=lambda item: (item["stream"], item["chunk_index"])
        )

    @property
    def has_loss(self) -> bool:
        return self.depth.has_loss or (self.store_color and self.color.has_loss)


class RgbdArchiveReader:
    """Reads back an archive without touching it.

    Deliberately lazy: a five-minute depth archive is tens of gigabytes, so
    frames are decoded a chunk at a time and only when asked for.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def _chunks(self, prefix: str, suffix: str) -> list[Path]:
        directory = Path(long_path(self.directory))
        if not directory.is_dir():
            return []
        return sorted(directory.glob(f"{prefix}_*{suffix}"))

    def depth_chunks(self) -> list[Path]:
        return self._chunks("depth", ".kcd")

    def color_chunks(self) -> list[Path]:
        return self._chunks("color", ".kcc")

    def iter_depth(self) -> Iterator[tuple[int, np.ndarray]]:
        """``(recording position, [H, W] float32 metres)`` for every frame."""
        for path in self.depth_chunks():
            header, payload = read_chunk(path, DEPTH_MAGIC)
            block = decode_depth_chunk(header, payload)
            for offset, position in enumerate(header["positions"]):
                yield int(position), block[offset]

    def iter_color(self) -> Iterator[tuple[int, np.ndarray]]:
        for path in self.color_chunks():
            header, payload = read_chunk(path, COLOR_MAGIC)
            block = decode_color_chunk(header, payload)
            for offset, position in enumerate(header["positions"]):
                yield int(position), block[offset]

    def depth_at(self, position: int) -> Optional[np.ndarray]:
        for path in self.depth_chunks():
            header, payload = read_chunk(path, DEPTH_MAGIC)
            positions = list(header["positions"])
            if position in positions:
                block = decode_depth_chunk(header, payload)
                return block[positions.index(position)]
        return None

    def color_at(self, position: int) -> Optional[np.ndarray]:
        for path in self.color_chunks():
            header, payload = read_chunk(path, COLOR_MAGIC)
            positions = list(header["positions"])
            if position in positions:
                block = decode_color_chunk(header, payload)
                return block[positions.index(position)]
        return None

    def verify(self) -> list[dict[str, Any]]:
        """Re-read every chunk header, reporting the ones that do not survive."""
        problems: list[dict[str, Any]] = []
        for path, magic in (
            *((p, DEPTH_MAGIC) for p in self.depth_chunks()),
            *((p, COLOR_MAGIC) for p in self.color_chunks()),
        ):
            try:
                read_chunk(path, magic)
            except StorageError as exc:
                problems.append(
                    {"file": path.name, "issue": exc.code, "message": exc.message}
                )
        return problems

    def positions(self) -> dict[str, list[int]]:
        """Which recording positions each stream actually holds."""
        result: dict[str, list[int]] = {"depth": [], "color": []}
        for path in self.depth_chunks():
            header, _payload = read_chunk(path, DEPTH_MAGIC)
            result["depth"].extend(int(p) for p in header["positions"])
        for path in self.color_chunks():
            header, _payload = read_chunk(path, COLOR_MAGIC)
            result["color"].extend(int(p) for p in header["positions"])
        result["depth"].sort()
        result["color"].sort()
        return result


def estimate_bytes_per_second(
    *,
    width: int,
    height: int,
    fps: float,
    depth_codec: DepthCodec,
    store_color: bool,
    native_recording: bool,
    native_megabytes_per_minute: float = 96.3,
) -> dict[str, float]:
    """Estimated raw-archive cost, from the measured 720p figures.

    The depth figure was measured on this camera; other resolutions are scaled
    by pixel count, which is an approximation and is labelled as one.
    """
    pixels = max(1, int(width) * int(height))
    reference = 1280 * 720
    scale = (pixels / reference) * (max(1.0, float(fps)) / 30.0)
    depth_per_minute = depth_codec.megabytes_per_minute_720p * scale
    color_per_minute = 0.0
    if store_color:
        # PNG on real colour measured close to 1 MB per 720p frame.
        color_per_minute = 1.0 * 30.0 * 60.0 * scale
    native_per_minute = native_megabytes_per_minute * scale if native_recording else 0.0
    total = depth_per_minute + color_per_minute + native_per_minute
    return {
        "depth_mb_per_minute": depth_per_minute,
        "color_mb_per_minute": color_per_minute,
        "native_mb_per_minute": native_per_minute,
        "total_mb_per_minute": total,
        "total_bytes_per_second": total * 1e6 / 60.0,
    }


__all__ = [
    "COLOR_MAGIC",
    "DEFAULT_CHUNK_FRAMES",
    "DEFAULT_WORKERS",
    "DEPTH_MAGIC",
    "DepthCodec",
    "QUANTISED_INVALID",
    "QUANTISED_SCALE",
    "RgbdArchiveReader",
    "RgbdArchiveWriter",
    "StreamStats",
    "decode_color_chunk",
    "decode_depth_chunk",
    "encode_color_chunk",
    "encode_depth_chunk",
    "estimate_bytes_per_second",
    "read_chunk",
    "write_chunk",
]
