"""Per-signal ``.npy`` files so a version can be read a window at a time.

Processing 1.0.0 wrote one ``arrays.npz``. Compressed archive members cannot be
memory-mapped, so the review screen had to decompress **everything** to look at
one second of a session: measured at 0.73 s and 135 MB resident for a 60-minute
BODY_38 take, against 7.5 ms and 0.27 MB for the same 600-frame window read
from a ``.npy`` memory map.

From 1.1.0 each array is its own uncompressed ``.npy`` beside an ``index.json``
describing them. Runs produced by 1.0.0 are still readable: :class:`ArrayStore`
falls back to the old ``arrays.npz`` and says so through :attr:`is_memmapped`,
so a caller can tell whether a window read is cheap or not instead of guessing.

No Qt, no SDK - this module is part of the offline layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

import numpy as np

from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists

#: Directory holding one ``.npy`` per array, relative to the run directory.
ARRAY_DIRNAME = "arrays"
ARRAY_INDEX_FILE = "index.json"
#: The single-file form written by processing 1.0.0. Read, never written.
LEGACY_ARCHIVE = "arrays.npz"
ARRAY_INDEX_SCHEMA_VERSION = "1.0.0"


def write_arrays(directory: Path, arrays: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """Write every array as its own ``.npy`` plus an index. Returns the index.

    Uncompressed on purpose: the point is a file the reader can map, and
    compression is what made the old form unmappable. The cost is disk, which
    is the cheap resource here - an hour of skeleton arrays is ~135 MB next to
    a raw recording measured in tens of gigabytes.
    """
    target = ensure_dir(Path(directory) / ARRAY_DIRNAME)
    entries: dict[str, Any] = {}
    for key, value in arrays.items():
        array = np.ascontiguousarray(value)
        path = target / f"{key}.npy"
        with open(long_path(path), "wb") as stream:
            np.save(stream, array, allow_pickle=False)
        entries[key] = {
            "file": f"{ARRAY_DIRNAME}/{key}.npy",
            "dtype": str(array.dtype),
            "shape": [int(n) for n in array.shape],
            "bytes": int(array.nbytes),
        }
    index = {
        "schema_version": ARRAY_INDEX_SCHEMA_VERSION,
        "layout": "one uncompressed .npy per array; memory-mappable",
        "arrays": entries,
    }
    write_json(target / ARRAY_INDEX_FILE, index)
    return index


class ArrayStore:
    """Read-only access to one version's arrays, a window at a time.

    ``store["joints"]`` still returns the whole array for callers that want it.
    ``store.window("joints", a, b)`` is the one to reach for in a screen: with
    the 1.1.0 layout it touches only the pages it needs.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._index: Optional[dict[str, Any]] = None
        self._memmaps: dict[str, np.ndarray] = {}
        self._archive: Optional[Any] = None
        self._archive_file: Optional[Any] = None

        index_path = self.directory / ARRAY_DIRNAME / ARRAY_INDEX_FILE
        if path_exists(index_path):
            self._index = dict(read_json(index_path))
        elif not path_exists(self.directory / LEGACY_ARCHIVE):
            raise FileNotFoundError(
                f"Bu sürümde dizi bulunamadı: {self.directory}"
            )

    # ------------------------------------------------------------- metadata
    @property
    def is_memmapped(self) -> bool:
        """False for a 1.0.0 run, where a window read costs a full decompress."""
        return self._index is not None

    @property
    def keys(self) -> tuple[str, ...]:
        if self._index is not None:
            return tuple(self._index["arrays"])
        return tuple(self._open_archive().files)

    def shape(self, key: str) -> tuple[int, ...]:
        if self._index is not None:
            return tuple(self._index["arrays"][key]["shape"])
        return tuple(self._open_archive()[key].shape)

    def dtype(self, key: str) -> np.dtype:
        if self._index is not None:
            return np.dtype(self._index["arrays"][key]["dtype"])
        return self._open_archive()[key].dtype

    @property
    def frames(self) -> int:
        """Length of the time axis, taken from whichever array is present."""
        for key in ("joints", "camera_timestamps_ns", "source_positions"):
            if key in self.keys:
                return int(self.shape(key)[0])
        return 0

    # ---------------------------------------------------------------- access
    def memmap(self, key: str) -> np.ndarray:
        """A read-only memory map of one array (1.1.0), or the loaded array (1.0.0)."""
        cached = self._memmaps.get(key)
        if cached is not None:
            return cached
        if self._index is None:
            value = np.asarray(self._open_archive()[key])
            value.flags.writeable = False
        else:
            entry = self._index["arrays"][key]
            value = np.load(long_path(self.directory / entry["file"]), mmap_mode="r")
        self._memmaps[key] = value
        return value

    def window(self, key: str, start: int, stop: int) -> np.ndarray:
        """An owned copy of ``[start:stop]`` along the time axis.

        Copied rather than handed out as a view so the caller may keep it after
        the store is closed and the map is gone.
        """
        source = self.memmap(key)
        length = len(source)
        low = max(0, min(length, int(start)))
        high = max(low, min(length, int(stop)))
        return np.array(source[low:high])

    def __getitem__(self, key: str) -> np.ndarray:
        return np.array(self.memmap(key))

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def to_dict(self) -> dict[str, np.ndarray]:
        """Every array, fully loaded. Convenient, and as expensive as it sounds."""
        return {key: self[key] for key in self.keys}

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys)

    # ----------------------------------------------------------------- legacy
    def _open_archive(self) -> Any:
        if self._archive is None:
            self._archive_file = open(long_path(self.directory / LEGACY_ARCHIVE), "rb")
            self._archive = np.load(self._archive_file, allow_pickle=False)
        return self._archive

    def close(self) -> None:
        self._memmaps.clear()
        if self._archive is not None:
            self._archive.close()
            self._archive = None
        if self._archive_file is not None:
            self._archive_file.close()
            self._archive_file = None

    def __enter__(self) -> "ArrayStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = [
    "ARRAY_DIRNAME",
    "ARRAY_INDEX_FILE",
    "ARRAY_INDEX_SCHEMA_VERSION",
    "LEGACY_ARCHIVE",
    "ArrayStore",
    "write_arrays",
]
