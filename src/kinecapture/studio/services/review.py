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
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from kinecapture.core.jsonio import read_json
from kinecapture.core.paths import path_exists
from kinecapture.processing.annotations import (
    CANONICAL_ANNOTATION_SCHEMA_VERSION,
    AnnotationDocument,
)
from kinecapture.processing.floor import FloorPlane
from kinecapture.processing.review import ReviewDataset
from kinecapture.visualization.skeleton_spec import SkeletonSpec, try_get_skeleton_spec

logger = logging.getLogger(__name__)

#: Array written by the ``tracker_joint_positions_2d`` feature.
JOINTS_2D_KEY = "joint_positions_2d"
JOINT_VALID_KEY = "joint_valid_mask"


class LoadStage(str, Enum):
    """What a version's open is doing, in the words the screen uses.

    These are the *real* steps, in the order they run. The only one with an
    honest percentage is ``VERIFY``, which is measured in bytes and is where
    essentially all of the time goes; the rest report themselves as steps and
    the screen shows an indeterminate bar for them rather than a number
    nothing measured.
    """

    JOB = "job"
    VERIFY = "verify"
    MAP = "map"
    VIDEO = "video"
    SKELETON = "skeleton"
    READY = "ready"


#: Stage -> the sentence the screen shows while it is running.
STAGE_TEXT = {
    LoadStage.JOB: "Kayıt doğrulanıyor",
    LoadStage.VERIFY: "Türetilmiş dosyalar doğrulanıyor",
    LoadStage.MAP: "Kare eşlemesi okunuyor",
    LoadStage.VIDEO: "Video hazırlanıyor",
    LoadStage.SKELETON: "İskelet hazırlanıyor",
    LoadStage.READY: "Hazır",
}


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
        self._floor: Optional[FloorPlane] = None
        self._joints_2d_reason = ""
        self._has_joints_2d: Optional[bool] = None

    # -------------------------------------------------------------- lifecycle
    @classmethod
    def open(
        cls,
        directory: str | Path,
        *,
        verify: bool = True,
        progress: Optional[Callable[[str, int, int], None]] = None,
        cancelled: Optional[Callable[[], bool]] = None,
    ) -> "ReviewSession":
        """Open a version, reporting what it is doing while it does it.

        ``progress`` receives ``(stage, done, total)``. The stages carry real
        work and are named for what the person is waiting on rather than for
        the function running; see :class:`LoadStage`.
        """
        return cls(
            ReviewDataset(
                Path(directory),
                verify=verify,
                progress=progress,
                cancelled=cancelled,
            )
        )

    def prepare_video(self) -> Availability:
        """Open the proxy decoder now rather than on the first frame request.

        Called from the worker during loading so the 130 ms this costs is paid
        before the editor appears, not in the middle of the first repaint.
        """
        return self.video

    def prime(self, frames: int = 300) -> None:
        """Read the first window of joints, so the 3-D view can frame itself.

        Everything here is a read the screen would do anyway on its first
        paint. Doing it on the worker is the difference between an editor that
        appears finished and one that fills in while being looked at.
        """
        self.joints_3d_window(0, min(self.frames, max(1, frames)))
        # Touching this resolves the array store's key list once.
        _ = self.joints_2d_available

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
        points = np.asarray(points[0], dtype=np.float32).copy()
        points[~self._measured_2d(points, position)] = np.nan
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

    def _measured_2d(self, points: np.ndarray, position: int) -> np.ndarray:
        """Which of these pixels the tracker actually measured.

        The ZED reports ``(-1, -1)`` for a joint it could not place in the
        image - a sentinel, not a coordinate. The array stores it verbatim,
        which is right: the raw passthrough is the raw passthrough. What is
        not right is drawing a bone to it. On the 20 September take that put
        four white lines from the athlete's shoulders to just off the
        top-left corner of every frame where a face landmark was hidden.

        Two things are asked. The run's own validity mask, when it has one -
        that is the tracker's answer, not a guess. And the coordinate itself:
        a negative pixel is not a place in an image, whatever produced it.
        """
        finite = np.isfinite(points).all(axis=1)
        inside = (points >= 0).all(axis=1)
        measured = finite & inside
        try:
            mask = self.dataset.window(JOINT_VALID_KEY, position, position + 1)
        except Exception:  # noqa: BLE001 - an older run may not carry one
            return measured
        if mask.size:
            measured &= np.asarray(mask[0], dtype=bool)
        return measured

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

    # ----------------------------------------------------------------- floor
    @property
    def floor(self) -> FloorPlane:
        """The plane this version measured, or a plane that says it did not.

        Read from ``job.json``; the SDK is never started here. A run produced
        before floors were measured has no block at all, and that reads as
        "not attempted" rather than as a floor at zero.
        """
        if self._floor is None:
            self._floor = FloorPlane.from_dict(self._job.get("floor_plane"))
        return self._floor

    # ------------------------------------------------------------ annotations
    def empty_document(self) -> AnnotationDocument:
        """A fresh document bound to *this* version, for when none can be read."""
        return AnnotationDocument(
            schema_version=CANONICAL_ANNOTATION_SCHEMA_VERSION,
            processing_run=self.run_id,
            source_fingerprint=self.source_fingerprint,
        )

    # ---------------------------------------------------------------- subject
    @property
    def subject_status(self) -> str:
        """What processing concluded about who this version is about."""
        return str(self._job.get("subject_status", ""))

    @property
    def has_subject_data(self) -> Availability:
        """Whether this version actually contains one person's movement.

        A run where the tracker never locked onto anybody produces a full set
        of arrays that are entirely NaN. Choosing an athlete in the labelling
        screen cannot repair that: the arrays were written at processing time
        and hold only the *selected* body's joints. The honest answer is that
        the version has to be processed again with the athlete marked, and
        saying that is much better than letting someone label an empty take.
        """
        if self.subject_status == "needs_subject_selection":
            return Availability(
                False,
                "Bu sürüm işlenirken hiçbir kişi seçilmemiş; eklem dizileri boş. "
                "Kaydı, sporcu işaretlenmiş hâlde yeniden işleyin.",
            )
        return Availability(True)

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


__all__ = [
    "Availability",
    "JOINTS_2D_KEY",
    "JOINT_VALID_KEY",
    "LoadStage",
    "STAGE_TEXT",
    "ReviewSession",
]
