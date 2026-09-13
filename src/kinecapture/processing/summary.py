"""Pre-computed multi-resolution summary for the timeline.

The old timeline redrew its lanes by walking one pixel column at a time and
asking a full-length array what was inside it - measured at 282-323 ms per
repaint regardless of how long the take was, against a 16 ms budget. The cost
was never the frame count; it was doing per-pixel Python and NumPy work at
paint time.

So the decimation happens once, here, at processing time. Each level halves the
resolution of the one before it, exactly like the min/max pyramid an audio
editor draws a waveform from. A view showing ``span`` frames across ``pixels``
columns picks the level whose bins are about a pixel wide and reads a
contiguous slice - no loop, no allocation per column.

Both ends of a bin are kept: ``min`` and ``max`` for confidence, ``any`` and
``all`` for presence. A single mean would hide the thing the lane exists to
show - one bad frame inside an otherwise good second.

No Qt, no SDK.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists

SUMMARY_SCHEMA_VERSION = "1.0.0"
SUMMARY_DIRNAME = "summary"
SUMMARY_INDEX_FILE = "index.json"

#: Per-frame flags, or-reduced up the pyramid. A bin is flagged when *any*
#: frame in it is, because a QC problem that disappears when you zoom out is
#: worse than useless.
FLAG_CAPTURE_UNMATCHED = 1 << 0
FLAG_INTEGRITY_ISSUE = 1 << 1
FLAG_SUBJECT_AMBIGUOUS = 1 << 2

FLAG_LABELS = {
    FLAG_CAPTURE_UNMATCHED: "capture_unmatched",
    FLAG_INTEGRITY_ISSUE: "integrity_issue",
    FLAG_SUBJECT_AMBIGUOUS: "subject_ambiguous",
}


def _levels_for(frames: int, *, smallest_bins: int = 256) -> tuple[int, ...]:
    """Bin sizes 1, 2, 4, ... until the whole take fits in ``smallest_bins``.

    Stopping there rather than at a single bin keeps the coarsest level useful
    for a full-session overview while the pyramid stays about twice the size of
    its base.
    """
    if frames <= 0:
        return (1,)
    sizes = [1]
    while frames > smallest_bins * sizes[-1]:
        sizes.append(sizes[-1] * 2)
    return tuple(sizes)


def _reduce(values: np.ndarray, bin_size: int, how: str) -> np.ndarray:
    """Reduce ``values`` in blocks of ``bin_size``, padding the last block."""
    count = int(np.ceil(len(values) / bin_size))
    padded_length = count * bin_size
    if how in ("min", "max"):
        pad_value = np.nan
        block = np.full(padded_length, pad_value, dtype=np.float32)
    else:
        block = np.zeros(padded_length, dtype=values.dtype)
    block[: len(values)] = values
    shaped = block.reshape(count, bin_size)
    if how == "min":
        with np.errstate(invalid="ignore"):
            return _nan_reduce(shaped, np.fmin.reduce)
    if how == "max":
        with np.errstate(invalid="ignore"):
            return _nan_reduce(shaped, np.fmax.reduce)
    if how == "any":
        return shaped.any(axis=1).astype(np.uint8)
    if how == "all":
        return shaped.all(axis=1).astype(np.uint8)
    if how == "or":
        return np.bitwise_or.reduce(shaped, axis=1).astype(np.uint8)
    raise ValueError(f"Bilinmeyen indirgeme: {how}")


def _nan_reduce(shaped: np.ndarray, ufunc_reduce: Any) -> np.ndarray:
    """``fmin``/``fmax`` ignore NaN, and an all-NaN bin stays NaN.

    That distinction matters: an all-NaN bin means *not measured*, which is not
    the same as measured-and-zero and must not be painted like it.
    """
    return ufunc_reduce(shaped, axis=1).astype(np.float32)


def build_summary(
    directory: Path,
    *,
    present: np.ndarray,
    confidence: np.ndarray,
    flags: Optional[np.ndarray] = None,
    fps: float = 30.0,
) -> dict[str, Any]:
    """Write the pyramid for one processing run. Returns the index document.

    ``present`` is per-frame subject presence, ``confidence`` the mean joint
    confidence of that frame (NaN where nothing was measured), ``flags`` the
    per-frame QC bitfield.
    """
    frames = int(len(present))
    if len(confidence) != frames:
        raise ValueError("Kapsam ve güven dizileri aynı uzunlukta olmalı")
    flag_values = (
        np.zeros(frames, dtype=np.uint8) if flags is None else np.asarray(flags, np.uint8)
    )
    if len(flag_values) != frames:
        raise ValueError("Bayrak dizisi kare sayısıyla eşleşmiyor")

    present_bool = np.asarray(present).astype(bool)
    confidence_values = np.asarray(confidence, dtype=np.float32)

    target = ensure_dir(Path(directory) / SUMMARY_DIRNAME)
    levels = _levels_for(frames)
    entries: list[dict[str, Any]] = []
    for level, bin_size in enumerate(levels):
        arrays = {
            "confidence_min": _reduce(confidence_values, bin_size, "min"),
            "confidence_max": _reduce(confidence_values, bin_size, "max"),
            "present_any": _reduce(present_bool, bin_size, "any"),
            "present_all": _reduce(present_bool, bin_size, "all"),
            "flags": _reduce(flag_values, bin_size, "or"),
        }
        path = target / f"level_{level:02d}.npz"
        with open(long_path(path), "wb") as stream:
            np.savez(stream, **arrays)
        entries.append(
            {
                "level": level,
                "bin_frames": int(bin_size),
                "bins": int(len(arrays["present_any"])),
                "file": f"{SUMMARY_DIRNAME}/{path.name}",
            }
        )

    index = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "frames": frames,
        "fps": float(fps),
        "signals": ["confidence_min", "confidence_max", "present_any", "present_all", "flags"],
        "flag_bits": {str(bit): name for bit, name in FLAG_LABELS.items()},
        "reduction": "min/max for confidence, any/all for presence, bitwise-or for flags",
        "levels": entries,
    }
    write_json(target / SUMMARY_INDEX_FILE, index)
    return index


class TimelineSummary:
    """Reader for the pyramid. Levels are loaded on first use and kept."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        index_path = self.directory / SUMMARY_DIRNAME / SUMMARY_INDEX_FILE
        if not path_exists(index_path):
            raise FileNotFoundError(f"Zaman çizelgesi özeti yok: {self.directory}")
        self.index = dict(read_json(index_path))
        self.frames = int(self.index["frames"])
        self.fps = float(self.index.get("fps", 30.0))
        self._levels = list(self.index["levels"])
        self._cache: dict[int, dict[str, np.ndarray]] = {}

    @property
    def bin_sizes(self) -> tuple[int, ...]:
        return tuple(int(entry["bin_frames"]) for entry in self._levels)

    def level_for(self, span_frames: float, pixels: int) -> int:
        """The coarsest level that still gives at least one bin per pixel.

        Drawing from a finer level would mean reducing in the paint loop, which
        is the cost this whole file exists to remove.
        """
        if pixels <= 0 or span_frames <= 0:
            return 0
        wanted = span_frames / float(pixels)
        chosen = 0
        for position, size in enumerate(self.bin_sizes):
            if size <= wanted:
                chosen = position
            else:
                break
        return chosen

    def _load(self, level: int) -> dict[str, np.ndarray]:
        cached = self._cache.get(level)
        if cached is not None:
            return cached
        entry = self._levels[level]
        with open(long_path(self.directory / entry["file"]), "rb") as stream:
            with np.load(stream, allow_pickle=False) as archive:
                arrays = {key: archive[key] for key in archive.files}
        self._cache[level] = arrays
        return arrays

    def lane(
        self, view_start: float, view_span: float, pixels: int
    ) -> dict[str, Any]:
        """Everything one repaint of the lanes needs, already decimated.

        Returns the chosen level, the frame each returned bin starts at, and a
        contiguous slice of every signal. The caller draws one rectangle per
        entry and does no arithmetic per pixel.
        """
        level = self.level_for(view_span, pixels)
        bin_size = self.bin_sizes[level]
        arrays = self._load(level)
        total = len(arrays["present_any"])
        first = int(max(0, np.floor(view_start / bin_size)))
        last = int(min(total, np.ceil((view_start + view_span) / bin_size) + 1))
        if last <= first:
            first, last = 0, min(total, 1)
        window = {key: value[first:last] for key, value in arrays.items()}
        return {
            "level": level,
            "bin_frames": bin_size,
            "first_bin": first,
            "start_frame": first * bin_size,
            "bins": last - first,
            **window,
        }

    def flags_present(self, flag: int) -> bool:
        """Whether any frame anywhere carries ``flag`` (read from the coarsest level)."""
        arrays = self._load(len(self._levels) - 1)
        return bool(np.bitwise_and(arrays["flags"], flag).any())


__all__ = [
    "FLAG_CAPTURE_UNMATCHED",
    "FLAG_INTEGRITY_ISSUE",
    "FLAG_LABELS",
    "FLAG_SUBJECT_AMBIGUOUS",
    "SUMMARY_DIRNAME",
    "SUMMARY_SCHEMA_VERSION",
    "TimelineSummary",
    "build_summary",
]
