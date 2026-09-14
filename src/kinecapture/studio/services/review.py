"""One opened processing version, ready to be labelled.

Wraps :class:`~kinecapture.processing.review.ReviewDataset` with what a screen
needs and nothing more: a frame, the skeleton at that frame, the bones that
join it, and the anchors that make a label mean something.

Two things are deliberate here.

*Windows, not sessions.* Nothing loads the whole take. Frames come from the
proxy one at a time and joints come out of memory-mapped arrays a slice at a
time, so a sixty-minute version costs about what a one-minute version costs.

*Absent stays absent.* 2D joints exist only if the run computed them, depth
only if it stored it, video only if the proxy was written. Each is reported as
missing with the reason, and nothing is substituted for it - an overlay drawn
from guessed pixels would be a lie told on top of real video.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture.core.jsonio import read_json
from kinecapture.core.paths import path_exists
from kinecapture.processing.annotations import (
    CANONICAL_ANNOTATION_SCHEMA_VERSION,
    AnnotationDocument,
)
from kinecapture.processing.review import ReviewDataset
from kinecapture.visualization.skeleton_spec import SkeletonSpec, try_get_skeleton_spec

logger = logging.getLogger(__name__)

#: Array written by the ``tracker_joint_positions_2d`` feature.
JOINTS_2D_KEY = "joint_positions_2d"


@dataclass(frozen=True)
class Availability:
    """Whether one optional input is usable, and why not when it is not."""

    available: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.available


class ReviewSession:
    """A version held open for labelling."""

    def __init__(self, dataset: ReviewDataset) -> None:
        self.dataset = dataset
        self._job = dataset.job
        self._spec: Optional[SkeletonSpec] = None
        self._video_checked = False
        self._joints_2d_reason = ""
        self._has_joints_2d: Optional[bool] = None

    # -------------------------------------------------------------- lifecycle
    @classmethod
    def open(cls, directory: str | Path, *, verify: bool = True) -> "ReviewSession":
        return cls(ReviewDataset(Path(directory), verify=verify))

    def close(self) -> None:
        self.dataset.close()

    # ------------------------------------------------------------- identity
    @property
    def run_id(self) -> str:
        return self.dataset.run_id

    @property
    def take_dir(self) -> Path:
        return self.dataset.take_dir

    @property
    def frames(self) -> int:
        return self.dataset.frames

    @property
    def source_fingerprint(self) -> str:
        return self.dataset.source_fingerprint

    @property
    def fps(self) -> float:
        """The version's own frame rate; 30 only when the run never recorded one."""
        camera = self._job.get("processing_camera") or {}
        for value in (camera.get("target_fps"), camera.get("fps")):
            try:
                rate = float(value)
            except (TypeError, ValueError):
                continue
            if rate > 0:
                return rate
        return 30.0

    @property
    def source_size(self) -> Optional[tuple[int, int]]:
        """The pixel space 2D joints live in, or ``None`` if unrecorded."""
        camera = self._job.get("processing_camera") or {}
        size = camera.get("resolution") or ()
        if len(size) == 2 and int(size[0]) > 0 and int(size[1]) > 0:
            return int(size[0]), int(size[1])
        return None

    @property
    def skeleton(self) -> Optional[SkeletonSpec]:
        """The joint order and bones this version was written with."""
        if self._spec is None:
            path = self.dataset.directory / "skeleton_spec.json"
            if path_exists(path):
                try:
                    self._spec = SkeletonSpec.from_dict(read_json(path))
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("İskelet tanımı okunamadı: %s", exc)
            if self._spec is None:
                name = self._job.get("skeleton_format") or ""
                self._spec = try_get_skeleton_spec(str(name)) if name else None
        return self._spec

    @property
    def bones(self) -> tuple[tuple[int, int], ...]:
        spec = self.skeleton
        return spec.edges if spec is not None else ()

    # ----------------------------------------------------------------- video
    @property
    def video(self) -> Availability:
        reader = self._reader()
        if reader is None:
            return Availability(False, "Bu sürümde inceleme videosu yok.")
        if not reader.is_available:
            return Availability(False, reader.unavailable_reason or "Video açılamadı.")
        return Availability(True)

    def _reader(self):  # noqa: ANN202
        if not self._video_checked:
            self._video_checked = True
            try:
                self.dataset.open_video()
            except (OSError, ValueError) as exc:
                logger.warning("Proxy video açılamadı: %s", exc)
        return self.dataset.video

    def frame(self, position: int) -> Optional[np.ndarray]:
        """One proxy frame as RGB ``uint8``, or ``None`` when there is no video."""
        reader = self._reader()
        if reader is None or not reader.is_available:
            return None
        if not 0 <= position < self.frames:
            return None
        return reader.read_at(position)

    # ---------------------------------------------------------------- joints
    @property
    def joints_2d_available(self) -> Availability:
        if self._has_joints_2d is None:
            try:
                keys = self.dataset.array_store.keys
            except (FileNotFoundError, OSError, KeyError) as exc:
                self._has_joints_2d = False
                self._joints_2d_reason = f"Diziler okunamadı: {exc}"
            else:
                self._has_joints_2d = JOINTS_2D_KEY in keys
                if not self._has_joints_2d:
                    self._joints_2d_reason = (
                        "Bu sürüm 2B eklem noktalarını hesaplamamış "
                        "('2B eklem noktaları' özelliği kapalıydı)."
                    )
                elif self.source_size is None:
                    self._joints_2d_reason = (
                        "Kaynak görüntü boyutu kayıtlı değil; 2B noktalar "
                        "videoya oturtulamaz."
                    )
                    self._has_joints_2d = False
        return Availability(bool(self._has_joints_2d), self._joints_2d_reason)

    def joints_2d(
        self, position: int, *, frame_size: Optional[tuple[int, int]] = None
    ) -> Optional[np.ndarray]:
        """2D joints for one frame, in the pixels of ``frame_size``.

        ``frame_size`` is the size of the image they will be drawn on - the
        proxy is a downscale of the camera image, so the tracker's pixels are
        rescaled by the ratio between the two. Without a recorded source size
        this returns ``None`` rather than assuming they already match.
        """
        if not self.joints_2d_available:
            return None
        if not 0 <= position < self.frames:
            return None
        points = self.dataset.window(JOINTS_2D_KEY, position, position + 1)
        if points.size == 0:
            return None
        points = np.asarray(points[0], dtype=np.float32)
        if frame_size is None:
            return points
        source = self.source_size
        if source is None:
            return None
        width, height = frame_size
        scale_x = float(width) / float(source[0])
        scale_y = float(height) / float(source[1])
        scaled = points.copy()
        scaled[:, 0] *= scale_x
        scaled[:, 1] *= scale_y
        return scaled

    def joints_3d(self, position: int) -> Optional[np.ndarray]:
        """``[J, 3]`` for one frame. NaN where the tracker had nothing."""
        if not 0 <= position < self.frames:
            return None
        try:
            window = self.dataset.window("joints", position, position + 1)
        except (FileNotFoundError, KeyError, OSError):
            return None
        return np.asarray(window[0], dtype=np.float32) if window.size else None

    def joints_3d_window(self, start: int, stop: int) -> Optional[np.ndarray]:
        try:
            return self.dataset.window("joints", start, stop)
        except (FileNotFoundError, KeyError, OSError):
            return None

    def confidence(self, position: int) -> Optional[np.ndarray]:
        try:
            window = self.dataset.window("confidences", position, position + 1)
        except (FileNotFoundError, KeyError, OSError):
            return None
        return np.asarray(window[0], dtype=np.float32) if window.size else None

    def subject_present(self, position: int) -> Optional[bool]:
        """Whether the chosen person was tracked in this frame; ``None`` if unknown."""
        try:
            window = self.dataset.window("subject_present", position, position + 1)
        except (FileNotFoundError, KeyError, OSError):
            return None
        return bool(window[0]) if window.size else None

    # -------------------------------------------------------------- timeline
    @property
    def has_summary(self) -> bool:
        return self.dataset.has_summary

    @property
    def summary(self):  # noqa: ANN201 - TimelineSummary
        return self.dataset.summary

    @property
    def thumbnails(self):  # noqa: ANN201 - ThumbnailIndex
        return self.dataset.thumbnails

    # ------------------------------------------------------------ annotations
    def empty_document(self) -> AnnotationDocument:
        """A fresh document bound to *this* version, for when none can be read."""
        return AnnotationDocument(
            schema_version=CANONICAL_ANNOTATION_SCHEMA_VERSION,
            processing_run=self.run_id,
            source_fingerprint=self.source_fingerprint,
        )

    # ------------------------------------------------------------------ misc
    @property
    def issues(self) -> tuple[str, ...]:
        return tuple(self._job.get("issues") or ())

    @property
    def job(self) -> dict[str, Any]:
        return dict(self._job)

    def __enter__(self) -> "ReviewSession":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


__all__ = ["Availability", "JOINTS_2D_KEY", "ReviewSession"]
