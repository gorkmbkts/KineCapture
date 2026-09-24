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
from typing import Any, Callable, Optional

import numpy as np

from kinecapture.core.jsonio import read_json, read_jsonl
from kinecapture.core.paths import long_path, path_exists
from kinecapture.core.fingerprint import verify_checksum_manifest
from kinecapture.playback.take_reader import load_skeleton_stream, ProxyVideoReader

from .annotations import (
    CANONICAL_ANNOTATION_SCHEMA_VERSION,
    Anchor,
    AnnotationDocument,
    annotation_path,
    load_annotations,
    save_annotations,
)
from .arrays import ArrayStore
from .depth import DepthReader, has_depth
from .summary import TimelineSummary
from .thumbnails import ThumbnailIndex


class Cancelled(RuntimeError):
    """The caller asked for this open to stop; nothing here is half-applied."""


def run_take_dir(directory: Path, job: Any) -> Path:
    """The take a processing version belongs to - where it is *now*.

    ``job.json`` records, as an absolute path, the take directory the version
    was produced in. A project that has since been copied or moved - to another
    disk, to another computer - still carries that old path, and following it
    read labels from, and wrote labels into, a project that was no longer this
    one (release gate, 23 September 2026). A version published in place sits at
    ``<take>/derived/processing/<run>``, so its take is the folder three levels
    up whenever that folder really is a take. Only a version written elsewhere
    with ``--output-root`` falls back to the recorded path.
    """
    directory = Path(directory)
    parent = directory.parent
    if parent.name == "processing" and parent.parent.name == "derived":
        candidate = parent.parent.parent
        if path_exists(candidate / "take.json"):
            return candidate
    return Path(job["take_dir"])


class ReviewDataset:
    def __init__(
        self,
        directory: Path,
        *,
        verify: bool = True,
        progress: Optional[Callable[[str, int, int], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ):
        """Open one processing version.

        ``progress`` is called with ``(stage, done, total)`` as the open runs.
        The stages are real work, not a decorative sequence: reading the job
        file, re-hashing every derived file against ``checksums.json``, and
        parsing the source map. The checksum stage is measured in bytes and on
        a 2.7 GB version is 99% of the time, so it is the one that carries a
        percentage; the others report ``total = 0`` and are shown as steps.

        ``cancelled`` is polled inside the checksum walk. A caller that has
        moved to another version stops paying for this one immediately.
        """
        self.directory = Path(directory)
        report = progress or (lambda _stage, _done, _total: None)
        report("job", 0, 0)
        self.job = read_json(self.directory / "job.json")
        # ``partial`` is a version with recorded caveats, and the library
        # lists it with them attached; refusing to open one was how a run that
        # had matched 521 of 524 frames became unreachable. ``running``,
        # ``cancelled`` and ``failed`` are not versions at all.
        if self.job.get("state") not in ("complete", "partial"):
            raise ValueError(
                "Only a complete or partial processing version can be annotated"
            )
        if self.job.get("blocking_issues"):
            raise ValueError(
                "This version did not pass a check that annotation depends on: "
                + ", ".join(self.job["blocking_issues"])
            )
        if verify:
            report("verify", 0, 0)
            problems = verify_checksum_manifest(
                read_json(self.directory / "checksums.json"),
                self.directory,
                progress=lambda done, total: report("verify", done, total),
                cancelled=cancelled,
            )
            if cancelled is not None and cancelled():
                raise Cancelled("Sürüm açma iptal edildi.")
            if problems:
                raise ValueError("Derived checksum verification failed")
        report("map", 0, 0)
        # The source map is kept as two integer arrays rather than as parsed
        # rows. An hour at 60 FPS is 216000 frames; as dicts plus a tuple-keyed
        # index that measured 222 MB, and as arrays it is 3.5 MB. The rows
        # themselves are still available through :attr:`mapping`, re-read on
        # demand for the rare caller that wants the capture columns.
        positions: list[int] = []
        stamps: list[int] = []
        for row in read_jsonl(self.directory / "source_map.jsonl", strict=True):
            if row.get("record") != "frame":
                continue
            positions.append(int(row["source_position"]))
            stamps.append(int(row["cam_ns"]))
        self._positions = np.asarray(positions, dtype=np.int64)
        self._stamps = np.asarray(stamps, dtype=np.int64)
        report("map", 1, 1)
        # Strictly increasing source positions are the normal case and make
        # every anchor unique, so lookup is a binary search over the array. A
        # damaged source that repeats a position falls back to a dictionary
        # which *records* the repeat instead of letting the last row win.
        self._ordered = bool(
            self._positions.size and np.all(np.diff(self._positions) > 0)
        )
        self._by_anchor: Optional[dict[tuple[int, int], int]] = None
        self._ambiguous: frozenset[tuple[int, int]] = frozenset()
        self._stream: Optional[Any] = None
        self.video: Optional[ProxyVideoReader] = None
        self._arrays: Optional[ArrayStore] = None
        self._summary: Optional[TimelineSummary] = None
        self._thumbnails: Optional[ThumbnailIndex] = None
        self._depth: Optional[DepthReader] = None

    # ---------------------------------------------------------------- stream
    @property
    def stream(self):  # noqa: ANN201 - SkeletonStream
        """Every body in every frame, parsed on first use.

        Deliberately lazy. Parsing an hour of ``skeleton.jsonl`` costs seconds
        and hundreds of megabytes, and the labelling screen never needs it: it
        reads windows out of the memory-mapped arrays instead. Only a caller
        that genuinely wants per-body detail (subject selection, audit) pays
        for it.
        """
        if self._stream is None:
            self._stream = load_skeleton_stream(self.directory / "skeleton.jsonl")
        return self._stream

    @property
    def stream_loaded(self) -> bool:
        return self._stream is not None

    # ----------------------------------------------------------------- basics
    @property
    def run_id(self) -> str:
        return str(self.job["run_id"])

    @property
    def frames(self) -> int:
        return int(self._positions.size)

    @property
    def mapping(self) -> list[dict[str, Any]]:
        """The source map rows, re-read from disk.

        Not held in memory: the two columns anchoring needs are kept as arrays,
        and everything else in a row is wanted only by an audit view.
        """
        return [
            row
            for row in read_jsonl(self.directory / "source_map.jsonl", strict=True)
            if row.get("record") == "frame"
        ]

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
    @property
    def source_fingerprint(self) -> str:
        return str(self.job["source"]["fingerprint"])

    @property
    def take_dir(self) -> Path:
        """Where this version's labels live. See :func:`run_take_dir`."""
        return run_take_dir(self.directory, self.job)

    def anchor_at(self, position: int) -> Anchor:
        """The canonical identity of one frame: raw source, position and time."""
        if not 0 <= position < self.frames:
            raise IndexError("Preview position outside source map")
        return Anchor(
            source_fingerprint=self.source_fingerprint,
            source_position=int(self._positions[position]),
            camera_timestamp_ns=int(self._stamps[position]),
        )

    def position_of_anchor(self, anchor) -> int:  # noqa: ANN001 - Anchor or mapping
        """Resolve an anchor **exactly**, or refuse.

        There is no nearest-neighbour fallback and no positional correction. A
        label whose moment cannot be found in this version belongs to a
        different one, and moving it to the closest frame would quietly change
        what a coach said.
        """
        if not isinstance(anchor, Anchor):
            anchor = Anchor.from_dict(anchor)
        if anchor.source_fingerprint != self.source_fingerprint:
            raise ValueError("Annotation belongs to another raw source")
        key = (anchor.source_position, anchor.camera_timestamp_ns)
        if self._ordered:
            index = int(np.searchsorted(self._positions, anchor.source_position))
            if (
                0 <= index < self._positions.size
                and int(self._positions[index]) == anchor.source_position
                and int(self._stamps[index]) == anchor.camera_timestamp_ns
            ):
                return index
            raise ValueError("Canonical annotation boundary is not uniquely mapped")

        if self._by_anchor is None:
            self._build_fallback_index()
        if key in self._ambiguous:
            # Two frames of this version carry the same identity, so there is
            # no single frame this label refers to. Picking either one would be
            # a guess presented as a fact.
            raise ValueError("Canonical annotation boundary is ambiguous in this version")
        position = self._by_anchor.get(key)
        if position is None:
            raise ValueError("Canonical annotation boundary is not uniquely mapped")
        return position

    def _build_fallback_index(self) -> None:
        """Index a source map whose positions are not strictly increasing."""
        index: dict[tuple[int, int], int] = {}
        ambiguous: set[tuple[int, int]] = set()
        for i in range(self._positions.size):
            key = (int(self._positions[i]), int(self._stamps[i]))
            if key in index:
                ambiguous.add(key)
            else:
                index[key] = i
        self._by_anchor = index
        self._ambiguous = frozenset(ambiguous)

    # ------------------------------------------------------------ annotations
    @property
    def annotation_file(self) -> Path:
        return annotation_path(self.take_dir, self.run_id)

    def load_annotations(self) -> AnnotationDocument:
        """This version's labels, or an empty document. Never another version's."""
        return load_annotations(self.take_dir, self.run_id, self.source_fingerprint)

    def save_annotations(self, document: AnnotationDocument) -> Path:
        """Write the canonical sidecar. ``segments.json`` is never touched."""
        document.processing_run = self.run_id
        document.source_fingerprint = self.source_fingerprint
        return save_annotations(self.take_dir, document)

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


__all__ = [
    "CANONICAL_ANNOTATION_SCHEMA_VERSION",
    "Anchor",
    "AnnotationDocument",
    "Cancelled",
    "ReviewDataset",
    "run_take_dir",
]
