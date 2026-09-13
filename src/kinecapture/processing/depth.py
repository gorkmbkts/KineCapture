"""Indexed, cached access to a processed version's depth frames.

``RgbdArchiveReader.depth_at`` re-reads and decompresses chunks until it finds
the frame, which is the right trade for a one-off extraction and the wrong one
for a 3-D view being scrubbed: every frame pays for every chunk before it.

Here the chunk **headers** are read once to build a position index, and the one
decoded chunk is kept. Stepping through a take then decompresses each chunk once
instead of once per frame inside it.

The depth this reads is reconstructed offline from the immutable SVO, never the
depth measured during capture - a distinction the SDK itself forces, since
replaying a recording does not give back the same depth values. Callers are
told through :attr:`provenance` so nothing can present it as a capture-time
measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from kinecapture.core.paths import long_path, path_exists
from kinecapture.recording.rgbd_archive import (
    DEPTH_MAGIC,
    decode_depth_chunk,
    read_chunk,
    read_chunk_header,
)

#: What this depth is, stated once so no screen has to guess.
PROVENANCE = "reconstructed_offline"


class DepthReader:
    """Random access to ``depth/*.kcd`` with one chunk held in memory."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._index: dict[int, tuple[Path, int]] = {}
        self._cached_path: Optional[Path] = None
        self._cached_block: Optional[np.ndarray] = None
        self._height = 0
        self._width = 0
        self._build_index()

    def _chunk_files(self) -> list[Path]:
        directory = Path(long_path(self.directory))
        if not directory.is_dir():
            return []
        return sorted(directory.glob("depth_*.kcd"))

    def _build_index(self) -> None:
        for path in self._chunk_files():
            header = read_chunk_header(path, DEPTH_MAGIC)
            self._height = int(header.get("height", self._height))
            self._width = int(header.get("width", self._width))
            for offset, position in enumerate(header.get("positions", [])):
                self._index[int(position)] = (path, offset)

    @property
    def is_available(self) -> bool:
        return bool(self._index)

    @property
    def provenance(self) -> str:
        return PROVENANCE

    @property
    def shape(self) -> tuple[int, int]:
        return (self._height, self._width)

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(sorted(self._index))

    def at(self, position: int) -> Optional[np.ndarray]:
        """``[H, W] float32`` metres for ``position``, or ``None`` if not stored.

        Non-finite pixels mean *not measured* and are left that way; filling
        them with a nearby value would invent a measurement.
        """
        entry = self._index.get(int(position))
        if entry is None:
            return None
        path, offset = entry
        if self._cached_path != path or self._cached_block is None:
            header, payload = read_chunk(path, DEPTH_MAGIC)
            self._cached_block = decode_depth_chunk(header, payload)
            self._cached_path = path
        return self._cached_block[offset]

    def nearest_position(self, position: int) -> Optional[int]:
        if not self._index:
            return None
        return min(self._index, key=lambda value: abs(value - int(position)))

    def close(self) -> None:
        self._cached_block = None
        self._cached_path = None

    def __enter__(self) -> "DepthReader":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def has_depth(directory: Path) -> bool:
    directory = Path(directory)
    return path_exists(directory) and bool(list(Path(long_path(directory)).glob("depth_*.kcd")))


__all__ = ["PROVENANCE", "DepthReader", "has_depth"]
