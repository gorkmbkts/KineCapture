"""SDK-free reader for a pinned processing version and canonical annotations.

Opens **one** completed version: its skeleton stream, arrays, timeline summary,
preview images, review proxy and reconstructed depth, plus the canonical
annotation sidecar bound to that version's source.

Imports neither Qt nor ``pyzed``. That is checked by a test, because it is what
lets a screen open a version while a recording is running, and what lets the
next front end reuse this file unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture.core.jsonio import read_json, read_jsonl, write_json
from kinecapture.core.paths import long_path, ensure_dir, path_exists
from kinecapture.core.fingerprint import verify_checksum_manifest
from kinecapture.playback.take_reader import load_skeleton_stream, ProxyVideoReader

from .arrays import ArrayStore
from .depth import DepthReader, has_depth
from .summary import TimelineSummary
from .thumbnails import ThumbnailIndex

CANONICAL_ANNOTATION_SCHEMA_VERSION = "1.0.0"


class ReviewDataset:
    def __init__(self, directory: Path, *, verify: bool = True):
        self.directory = Path(directory)
        self.job = read_json(self.directory / "job.json")
        if self.job["state"] != "complete":
            raise ValueError("Only a complete processing version can be annotated")
        if verify and verify_checksum_manifest(read_json(self.directory / "checksums.json"), self.directory):
            raise ValueError("Derived checksum verification failed")
        self.mapping = [r for r in read_jsonl(self.directory / "source_map.jsonl", strict=True) if r.get("record") == "frame"]
        # Position lookup built once. The linear scan it replaces cost a pass
        # over the whole map per annotation boundary, which is two per interval.
        self._by_anchor = {
            (int(row["source_position"]), int(row["cam_ns"])): index
            for index, row in enumerate(self.mapping)
        }
        self.stream = load_skeleton_stream(self.directory / "skeleton.jsonl")
        self.video: Optional[ProxyVideoReader] = None
        self._arrays: Optional[ArrayStore] = None
        self._summary: Optional[TimelineSummary] = None
        self._thumbnails: Optional[ThumbnailIndex] = None
        self._depth: Optional[DepthReader] = None

    # ----------------------------------------------------------------- basics
    @property
    def run_id(self) -> str:
        return str(self.job["run_id"])

    @property
    def frames(self) -> int:
        return len(self.mapping)

    @property
    def processing_schema_version(self) -> str:
        return str(self.job.get("schema_version", "1.0.0"))

    def open_video(self) -> ProxyVideoReader:
        if self.video is None:
            self.video = ProxyVideoReader(self.directory / "proxy.mp4")
        return self.video

    # ----------------------------------------------------------------- arrays
    @property
    def array_store(self) -> ArrayStore:
        """Lazy: a screen that only scrubs video never opens the arrays."""
        if self._arrays is None:
            self._arrays = ArrayStore(self.directory)
        return self._arrays

    def arrays(self) -> dict[str, np.ndarray]:
        """Every array, fully loaded.

        Kept for callers that genuinely want the whole session (export, a
        one-off analysis). A screen showing part of a take should use
        :meth:`window` instead - for an hour-long BODY_38 take this is 135 MB
        and that one is under a megabyte.
        """
        return self.array_store.to_dict()

    def window(self, key: str, start: int, stop: int) -> np.ndarray:
        """``[start:stop]`` of one array along the time axis."""
        return self.array_store.window(key, start, stop)

    # ---------------------------------------------------------------- summary
    @property
    def has_summary(self) -> bool:
        return path_exists(self.directory / "summary" / "index.json")

    @property
    def summary(self) -> TimelineSummary:
        """Pre-decimated timeline lanes. Raises on a 1.0.0 run, which has none."""
        if self._summary is None:
            self._summary = TimelineSummary(self.directory)
        return self._summary

    # ------------------------------------------------------------- thumbnails
    @property
    def thumbnails(self) -> ThumbnailIndex:
        if self._thumbnails is None:
            self._thumbnails = ThumbnailIndex(self.directory)
        return self._thumbnails

    # ------------------------------------------------------------------ depth
    @property
    def has_depth(self) -> bool:
        return has_depth(self.directory / "depth")

    @property
    def depth(self) -> DepthReader:
        """Offline-reconstructed depth, indexed by source position.

        Never the depth measured while recording: replaying an SVO does not
        return the same values, so this carries ``reconstructed_offline``
        provenance and must be presented as such.
        """
        if self._depth is None:
            self._depth = DepthReader(self.directory / "depth")
        return self._depth

    # ---------------------------------------------------------------- anchors
    def anchor_at(self, position: int) -> dict:
        if not 0 <= position < len(self.mapping):
            raise IndexError("Preview position outside source map")
        row = self.mapping[position]
        return {"source_fingerprint": self.job["source"]["fingerprint"],
                "source_position": row["source_position"], "camera_timestamp_ns": row["cam_ns"]}

    def position_of_anchor(self, anchor: dict) -> int:
        if anchor["source_fingerprint"] != self.job["source"]["fingerprint"]:
            raise ValueError("Annotation belongs to another raw source")
        key = (int(anchor["source_position"]), int(anchor["camera_timestamp_ns"]))
        position = self._by_anchor.get(key)
        if position is None:
            raise ValueError("Canonical annotation boundary is not uniquely mapped")
        return position

    def save_annotations(self, samples: list[dict]) -> Path:
        """New sidecar contract; legacy segments.json is never migrated implicitly."""
        for sample in samples:
            start, end = (self.position_of_anchor(sample[k]) for k in ("start", "end"))
            if start > end:
                raise ValueError("Annotation interval is reversed")
            for interval in sample.get("errors", []):
                a, b = (self.position_of_anchor(interval[k]) for k in ("start", "end"))
                if not start <= a <= b <= end:
                    raise ValueError("Error interval is outside its movement sample")
        directory = ensure_dir(Path(self.job["take_dir"]) / "annotations" / "processing")
        target = directory / (self.job["run_id"] + ".json")
        write_json(target, {"schema_version": CANONICAL_ANNOTATION_SCHEMA_VERSION,
                           "contract": "canonical_source_boundaries_inclusive",
                           "processing_run": self.job["run_id"], "samples": samples}, overwrite=True)
        return target

    def close(self):
        if self.video:
            self.video.close()
            self.video = None
        if self._arrays is not None:
            self._arrays.close()
            self._arrays = None
        if self._depth is not None:
            self._depth.close()
            self._depth = None

    def __enter__(self) -> "ReviewDataset":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = ["CANONICAL_ANNOTATION_SCHEMA_VERSION", "ReviewDataset"]
