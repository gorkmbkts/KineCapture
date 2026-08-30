"""Reading a recorded take back for review.

Synchronisation policy
----------------------
Playback position is driven by **frame index**, and every frame carries the
camera timestamp it was captured with. Timing is therefore never reconstructed
as ``index / fps``: that assumption silently hides a dropped frame, which is
exactly the failure this application exists to make visible.

:class:`TakeReader` exposes both, so the review timeline can show real elapsed
time while gaps in the frame sequence stay visible as gaps.

Memory policy
-------------
The skeleton stream is small (a five-minute 34-joint take is a few megabytes as
float32) and is loaded fully so scrubbing is instant. Video is *not*: the proxy
MP4 is read frame by frame through OpenCV and seeked on demand.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from kinecapture.core.errors import StorageError
from kinecapture.core.jsonio import read_jsonl
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import (
    is_too_long_for_external_tools,
    long_path,
    path_exists,
    safe_external_path,
)
from kinecapture.dataset.workspace import ProjectWorkspace, TakePaths
from kinecapture.domain.models import BodyPose
from kinecapture.domain.project import Take
from kinecapture.visualization.skeleton_spec import SkeletonSpec, try_get_skeleton_spec

logger = get_logger(__name__)


@dataclass
class SkeletonFrame:
    """One frame of the recorded pose stream.

    ``bodies`` keeps *every* detection, for audit and for future reprocessing.
    ``subject`` is the authoritative answer to "which of them is the person
    this recording is about", written at capture time by the subject lock.
    """

    frame_index: int
    host_timestamp_ns: int
    camera_timestamp_ns: int
    bodies: tuple[BodyPose, ...] = ()
    active_body_id: Optional[int] = None
    position: Optional[int] = None
    subject: Optional[dict[str, Any]] = None

    def body(self, tracking_id: Optional[int]) -> Optional[BodyPose]:
        """The requested body, the recorded active one, or the best available.

        The final fallback makes this convenient for *display*, and unsuitable
        for ground truth: it will happily return a stranger. Dataset code uses
        :meth:`subject_body` instead.
        """
        if tracking_id is not None:
            for body in self.bodies:
                if body.tracking_id == tracking_id:
                    return body
        if self.active_body_id is not None:
            for body in self.bodies:
                if body.tracking_id == self.active_body_id:
                    return body
        if not self.bodies:
            return None
        return max(self.bodies, key=lambda b: b.valid_joint_ratio)

    def subject_body(self) -> Optional[BodyPose]:
        """The locked subject, or ``None``. Never anybody else.

        There is no fallback here on purpose. If the subject was not found in
        this frame, the honest answer is that it was not found - substituting
        the best-tracked body is precisely how another person's movement ends
        up labelled as the participant's.
        """
        if not self.subject:
            return None
        tracker_id = self.subject.get("tracker_id")
        if tracker_id is None:
            return None
        for body in self.bodies:
            if body.tracking_id == int(tracker_id):
                return body
        return None

    @property
    def subject_state(self) -> str:
        return str((self.subject or {}).get("state", "unselected"))

    @property
    def subject_confidence(self) -> float:
        value = (self.subject or {}).get("confidence")
        return float(value) if value is not None else float("nan")


@dataclass
class SkeletonStream:
    """The whole pose stream of one take, plus what the header said about it."""

    header: dict[str, Any] = field(default_factory=dict)
    frames: list[SkeletonFrame] = field(default_factory=list)
    markers: list[dict[str, Any]] = field(default_factory=list)
    body_id_changes: list[dict[str, Any]] = field(default_factory=list)
    truncated: bool = False

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def skeleton_format(self) -> str:
        return str(self.header.get("skeleton_format", ""))

    @property
    def duration_s(self) -> float:
        """Elapsed time from the camera timestamps, not from a frame count."""
        stamps = [f.camera_timestamp_ns for f in self.frames if f.camera_timestamp_ns]
        if len(stamps) < 2:
            return 0.0
        return max(0.0, (stamps[-1] - stamps[0]) / 1e9)

    @property
    def tracking_ids(self) -> tuple[int, ...]:
        ids: set[int] = set()
        for frame in self.frames:
            ids.update(body.tracking_id for body in frame.bodies)
        return tuple(sorted(ids))

    def frame_at(self, position: int) -> Optional[SkeletonFrame]:
        """Frame at a 0-based playback position (not the recorded frame index)."""
        if 0 <= position < len(self.frames):
            return self.frames[position]
        return None

    def position_of_frame_index(self, frame_index: int) -> int:
        """Nearest playback position for a recorded frame index."""
        indices = [f.frame_index for f in self.frames]
        if not indices:
            return 0
        return int(np.clip(np.searchsorted(indices, frame_index), 0, len(indices) - 1))

    def timestamp_gaps(self, *, target_fps: float) -> list[tuple[int, float]]:
        """Positions where the inter-frame gap exceeds 1.5 frame intervals.

        These are the moments where data is genuinely missing. The review
        timeline marks them so a gap is never mistaken for a slow movement.
        """
        if target_fps <= 0 or len(self.frames) < 2:
            return []
        threshold_ms = 1.5 * (1000.0 / target_fps)
        gaps: list[tuple[int, float]] = []
        for position in range(1, len(self.frames)):
            previous = self.frames[position - 1].camera_timestamp_ns
            current = self.frames[position].camera_timestamp_ns
            if not previous or not current:
                continue
            gap_ms = (current - previous) / 1e6
            if gap_ms > threshold_ms:
                gaps.append((position, gap_ms))
        return gaps

    def joint_array(
        self, tracking_id: Optional[int], *, start: int = 0, end: Optional[int] = None
    ) -> np.ndarray:
        """``float32 [T, J, 3]`` for one body over a playback range.

        Frames where the body is absent become all-NaN rows: a gap in tracking
        stays a gap rather than being interpolated away.
        """
        stop = len(self.frames) if end is None else min(end + 1, len(self.frames))
        window = self.frames[start:stop]
        if not window:
            return np.zeros((0, 0, 3), dtype=np.float32)

        num_joints = 0
        for frame in window:
            body = frame.body(tracking_id)
            if body is not None:
                num_joints = body.num_joints
                break
        if num_joints == 0:
            return np.zeros((len(window), 0, 3), dtype=np.float32)

        result = np.full((len(window), num_joints, 3), np.nan, dtype=np.float32)
        for offset, frame in enumerate(window):
            body = frame.body(tracking_id)
            if body is not None and body.num_joints == num_joints:
                result[offset] = body.joint_positions_xyz
        return result

    def confidence_array(
        self, tracking_id: Optional[int], *, start: int = 0, end: Optional[int] = None
    ) -> np.ndarray:
        """``float32 [T, J]`` confidences aligned with :meth:`joint_array`."""
        stop = len(self.frames) if end is None else min(end + 1, len(self.frames))
        window = self.frames[start:stop]
        if not window:
            return np.zeros((0, 0), dtype=np.float32)
        num_joints = 0
        for frame in window:
            body = frame.body(tracking_id)
            if body is not None:
                num_joints = body.num_joints
                break
        result = np.full((len(window), num_joints), np.nan, dtype=np.float32)
        for offset, frame in enumerate(window):
            body = frame.body(tracking_id)
            if body is not None and body.num_joints == num_joints:
                result[offset] = body.joint_confidences
        return result

    def optional_body_array(
        self,
        tracking_id: Optional[int],
        attribute: str,
        *,
        start: int = 0,
        end: Optional[int] = None,
    ) -> Optional[np.ndarray]:
        """One optional tracker array over a playback range, or ``None``.

        Returns ``float32 [T, ...]`` shaped like the per-frame field, with
        all-NaN rows where the body was absent or never carried that field.
        ``None`` means *no* frame in the window carried it at all, which is
        what an older recording looks like - and is reported as an unavailable
        feature rather than as an array of zeros.
        """
        stop = len(self.frames) if end is None else min(end + 1, len(self.frames))
        window = self.frames[start:stop]
        if not window:
            return None

        tail: Optional[tuple[int, ...]] = None
        for frame in window:
            body = frame.body(tracking_id)
            value = getattr(body, attribute, None) if body is not None else None
            if value is not None:
                tail = tuple(int(dimension) for dimension in np.shape(value))
                break
        if tail is None:
            return None

        result = np.full((len(window), *tail), np.nan, dtype=np.float32)
        for offset, frame in enumerate(window):
            body = frame.body(tracking_id)
            value = getattr(body, attribute, None) if body is not None else None
            if value is not None and tuple(np.shape(value)) == tail:
                result[offset] = np.asarray(value, dtype=np.float32)
        return result

    def body_state_arrays(
        self,
        tracking_id: Optional[int],
        *,
        start: int = 0,
        end: Optional[int] = None,
    ) -> dict[str, np.ndarray]:
        """Per-frame presence, tracker confidence, tracking state and action."""
        from kinecapture.domain.enums import BodyActionState  # local: avoids a cycle

        stop = len(self.frames) if end is None else min(end + 1, len(self.frames))
        window = self.frames[start:stop]
        count = len(window)
        present = np.zeros(count, dtype=bool)
        confidence = np.full(count, np.nan, dtype=np.float32)
        tracking = np.zeros(count, dtype=np.uint8)
        action = np.zeros(count, dtype=np.uint8)
        states = {"ok": 1, "searching": 2, "off": 3, "terminate": 4}
        actions = {
            BodyActionState.IDLE.value: 1,
            BodyActionState.MOVING.value: 2,
        }
        for offset, frame in enumerate(window):
            body = frame.body(tracking_id)
            if body is None:
                continue
            present[offset] = True
            confidence[offset] = body.body_confidence
            tracking[offset] = states.get(body.tracking_state.value, 0)
            action[offset] = actions.get(body.action_state.value, 0)
        return {
            "body_present": present,
            "body_confidence": confidence,
            "tracking_state": tracking,
            "action_state": action,
        }

    def optional_field_names(self, tracking_id: Optional[int]) -> tuple[str, ...]:
        """Which optional tracker fields appear anywhere in this stream."""
        found: set[str] = set()
        for frame in self.frames:
            body = frame.body(tracking_id)
            if body is not None:
                found.update(body.available_fields())
        return tuple(sorted(found))

    # ------------------------------------------------------ selected subject
    @property
    def has_subject_lock(self) -> bool:
        """Whether this take recorded an authoritative subject association."""
        return any(frame.subject for frame in self.frames)

    @property
    def subject_id(self) -> str:
        return str(self.header.get("subject_id") or "")

    def subject_arrays(
        self, *, start: int = 0, end: Optional[int] = None, num_joints: int = 0
    ) -> dict[str, np.ndarray]:
        """The selected subject's own timeline over a playback range.

        Frames where the subject was not found give all-NaN coordinates, a
        ``False`` presence flag and the ``-1`` sentinel for the tracker id.
        Nothing is borrowed from another body, and nothing is interpolated.

        A take recorded before the subject lock existed has no association at
        all; that is reported through ``has_association`` rather than being
        approximated from ``active_id``, which was only ever a display hint.
        """
        stop = len(self.frames) if end is None else min(end + 1, len(self.frames))
        window = self.frames[start:stop]
        count = len(window)

        joints = num_joints
        if joints <= 0:
            for frame in window:
                body = frame.subject_body()
                if body is not None:
                    joints = body.num_joints
                    break
        positions = np.full((count, max(joints, 0), 3), np.nan, dtype=np.float32)
        confidences = np.full((count, max(joints, 0)), np.nan, dtype=np.float32)
        present = np.zeros(count, dtype=bool)
        tracker_ids = np.full(count, -1, dtype=np.int64)
        association = np.full(count, np.nan, dtype=np.float32)
        states: list[str] = []

        for offset, frame in enumerate(window):
            states.append(frame.subject_state)
            association[offset] = frame.subject_confidence
            body = frame.subject_body()
            if body is None:
                continue
            present[offset] = True
            tracker_ids[offset] = int(body.tracking_id)
            if joints and body.num_joints == joints:
                positions[offset] = body.joint_positions_xyz
                confidences[offset] = body.joint_confidences
        return {
            "joints_xyz": positions,
            "joint_confidences": confidences,
            "subject_present_mask": present,
            "subject_source_tracking_id": tracker_ids,
            "subject_association_confidence": association,
            "subject_states": np.asarray(states),
            "has_association": np.asarray([self.has_subject_lock]),
        }

    @property
    def dominant_tracking_id(self) -> Optional[int]:
        """The identity seen in the most frames, or ``None`` if nobody was.

        Used **only** for takes recorded before the subject lock existed, where
        there is no recorded answer to "who is the participant". It is a
        heuristic and is labelled as one wherever it reaches the user; it is
        never used to overrule a real lock. This matches the rule the exporter
        applies to the same legacy takes, so the picture on screen and the
        exported array describe the same person.
        """
        counts: dict[int, int] = {}
        for frame in self.frames:
            for body in frame.bodies:
                counts[body.tracking_id] = counts.get(body.tracking_id, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]

    def review_body_at(
        self, position: int, *, fallback_id: Optional[int] = None
    ) -> Optional[BodyPose]:
        """The one body review may draw at ``position``, or ``None``.

        With a subject lock this is the locked person and nobody else, so a
        frame where the subject was not tracked returns ``None`` rather than
        the next best body. Without a lock the caller supplies the legacy
        ``fallback_id`` it has already told the user about.
        """
        frame = self.frame_at(position)
        if frame is None:
            return None
        if self.has_subject_lock:
            return frame.subject_body()
        if fallback_id is None:
            return None
        for body in frame.bodies:
            if body.tracking_id == fallback_id:
                return body
        return None

    def subject_coverage_curve(
        self, *, fallback_id: Optional[int] = None
    ) -> np.ndarray:
        """``float32 [T]`` usable-joint fraction of the *drawn* person only.

        The timeline used to plot :meth:`coverage_curve` with a ``None``
        tracking id, which falls back to the best-tracked body in each frame.
        On a take with a bystander that reads as full coverage during the exact
        stretch where the participant was lost - the timeline claimed good data
        for frames the viewport was drawing as empty. Both now read the same
        body.
        """
        values = np.zeros(len(self.frames), dtype=np.float32)
        for position in range(len(self.frames)):
            body = self.review_body_at(position, fallback_id=fallback_id)
            values[position] = body.valid_joint_ratio if body is not None else 0.0
        return values

    def coverage_curve(self, tracking_id: Optional[int]) -> np.ndarray:
        """``float32 [T]`` fraction of usable joints per frame, for the timeline."""
        values = np.zeros(len(self.frames), dtype=np.float32)
        for position, frame in enumerate(self.frames):
            body = frame.body(tracking_id)
            values[position] = body.valid_joint_ratio if body is not None else 0.0
        return values


def load_skeleton_stream(path: Path) -> SkeletonStream:
    """Read a ``skeleton.jsonl`` sidecar.

    A truncated final line (interrupted recording) is tolerated and reported via
    :attr:`SkeletonStream.truncated` rather than making the file unreadable.
    """
    path = Path(path)
    if not path_exists(path):
        raise StorageError(
            f"İskelet akışı bulunamadı: {path.name}",
            code="skeleton_stream_missing",
            remedy="Kayıt yarım kalmış olabilir; kurtarma ekranını kullanın.",
            details={"path": str(path)},
        )

    stream = SkeletonStream()
    byte_size = os.stat(long_path(path)).st_size
    consumed = 0
    for record in read_jsonl(path):
        consumed += 1
        kind = record.get("record")
        if kind == "header":
            stream.header = dict(record)
        elif kind == "frame":
            bodies = tuple(
                BodyPose.from_record(entry) for entry in record.get("bodies") or []
            )
            stream.frames.append(
                SkeletonFrame(
                    frame_index=int(record.get("i", 0)),
                    host_timestamp_ns=int(record.get("host_ns", 0)),
                    camera_timestamp_ns=int(record.get("cam_ns", 0)),
                    bodies=bodies,
                    active_body_id=record.get("active_id"),
                    position=(
                        int(record["p"]) if record.get("p") is not None else None
                    ),
                    subject=record.get("subject"),
                )
            )
        elif kind == "marker":
            stream.markers.append(dict(record))
        elif kind == "body_id_change":
            stream.body_id_changes.append(dict(record))

    if byte_size and consumed:
        # A file whose last line has no newline terminator was cut off mid-write.
        with open(long_path(path), "rb") as handle:
            handle.seek(max(0, byte_size - 1))
            stream.truncated = handle.read(1) != b"\n"
    return stream


class ProxyVideoReader:
    """Random-access reader over the review proxy video.

    Thread-safe: the GUI thread seeks it while a timer advances playback. All
    access is serialised on one lock because ``cv2.VideoCapture`` is not
    re-entrant.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._capture: Any = None
        self._lock = threading.RLock()
        self._frame_count = 0
        self._position = -1
        self.unavailable_reason = ""
        self._open()

    def _open(self) -> None:
        if not path_exists(self.path):
            self.unavailable_reason = "Proxy video dosyası yok."
            return
        if is_too_long_for_external_tools(self.path):
            # OpenCV cannot open an extended-length path; scrubbing degrades
            # while the pose stream - the actual data - stays fully readable.
            self.unavailable_reason = (
                "Dosya yolu Windows uzunluk sınırını aşıyor; proxy video okunamıyor."
            )
            return
        try:
            import cv2  # noqa: PLC0415 - optional at runtime
        except ImportError as exc:
            self.unavailable_reason = f"opencv-python bulunamadı: {exc}"
            return
        capture = cv2.VideoCapture(safe_external_path(self.path))
        if not capture.isOpened():
            self.unavailable_reason = "Proxy video açılamadı."
            return
        self._capture = capture
        self._frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    @property
    def is_available(self) -> bool:
        return self._capture is not None

    @property
    def frame_count(self) -> int:
        return self._frame_count

    def read_at(self, position: int) -> Optional[np.ndarray]:
        """Return frame ``position`` as contiguous RGB uint8, or ``None``."""
        if self._capture is None:
            return None
        import cv2  # noqa: PLC0415 - proven importable in _open

        with self._lock:
            if position != self._position + 1:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = self._capture.read()
            self._position = position if ok else -1
            if not ok or frame is None:
                return None
            return np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def close(self) -> None:
        with self._lock:
            capture, self._capture = self._capture, None
            if capture is not None:
                capture.release()

    def __enter__(self) -> "ProxyVideoReader":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


@dataclass
class LoadedTake:
    """Everything the review screen needs for one take."""

    take: Take
    paths: TakePaths
    stream: SkeletonStream
    video: Optional[ProxyVideoReader] = None
    spec: Optional[SkeletonSpec] = None

    @property
    def frame_count(self) -> int:
        return self.stream.frame_count

    @property
    def target_fps(self) -> float:
        return float(self.take.capture_profile.fps or 30)

    @property
    def has_video(self) -> bool:
        return self.video is not None and self.video.is_available

    def video_position_for(self, position: int) -> Optional[int]:
        """Map a skeleton position onto a proxy-video frame, or ``None``.

        The proxy is written frame for frame alongside the pose stream inside
        the same loop, so the mapping is the identity. When the proxy is
        shorter - a codec dropped the tail, or the writer was cut off - the
        positions past its end have **no** colour frame.

        This used to clamp to the last available frame. That silently paired
        one person's pose with a different moment's picture, which looks
        exactly like a tracking failure and is impossible to tell apart from
        one. Returning ``None`` lets the caller say "no RGB for this frame",
        which is the truth.
        """
        if self.video is None or self.video.frame_count <= 0:
            return None
        if not 0 <= position < self.video.frame_count:
            return None
        return int(position)

    @property
    def proxy_frame_shortfall(self) -> int:
        """How many pose frames have no colour frame behind them."""
        if self.video is None or self.video.frame_count <= 0:
            return self.frame_count
        return max(0, self.frame_count - self.video.frame_count)

    @property
    def joint_pixel_space(self) -> Optional[tuple[int, int]]:
        """Resolution the recorded ``joint_positions_2d`` are expressed in.

        This is the *camera's* image, which is not the proxy video: the proxy
        is downscaled to ``proxy_video_width``. Overlaying 2D joints without
        this distinction scales every joint by the ratio between the two.
        """
        camera = self.take.camera_info
        if camera is None:
            return None
        width, height = camera.resolution
        return (int(width), int(height)) if width > 0 and height > 0 else None

    @property
    def camera_calibration(self) -> Optional[dict[str, Any]]:
        """Verified left-camera intrinsics, when the take recorded them."""
        camera = self.take.camera_info
        if camera is None:
            return None
        calibration = (camera.extra or {}).get("left_camera_calibration")
        return dict(calibration) if isinstance(calibration, dict) else None

    @property
    def has_subject_lock(self) -> bool:
        return self.stream.has_subject_lock

    @property
    def legacy_tracking_id(self) -> Optional[int]:
        """Who to draw for a take that predates the subject lock."""
        if self.stream.has_subject_lock:
            return None
        return self.stream.dominant_tracking_id

    def review_body_at(self, position: int):  # type: ignore[no-untyped-def]
        """The single body the review screen is allowed to draw."""
        return self.stream.review_body_at(
            position, fallback_id=self.legacy_tracking_id
        )

    def subject_coverage_curve(self):  # type: ignore[no-untyped-def]
        return self.stream.subject_coverage_curve(
            fallback_id=self.legacy_tracking_id
        )

    def close(self) -> None:
        if self.video is not None:
            self.video.close()
            self.video = None


def load_take(
    workspace: ProjectWorkspace, take: Take, *, with_video: bool = True
) -> LoadedTake:
    """Load a take's pose stream and (optionally) open its proxy video."""
    paths = workspace.take_paths(take)
    stream = load_skeleton_stream(paths.skeleton_stream)
    spec = try_get_skeleton_spec(
        take.skeleton_format or stream.skeleton_format
    )
    if spec is None and stream.skeleton_format:
        logger.warning(
            "Kayıt bilinmeyen iskelet biçimi kullanıyor: %s", stream.skeleton_format
        )
    video = ProxyVideoReader(paths.proxy_video) if with_video else None
    if video is not None and not video.is_available:
        logger.info(
            "Proxy video kullanılamıyor (%s): %s", take.take_id, video.unavailable_reason
        )
    return LoadedTake(take=take, paths=paths, stream=stream, video=video, spec=spec)


def recover_partial_take(
    workspace: ProjectWorkspace, take: Take
) -> tuple[Take, int]:
    """Re-derive a partial take's frame count from what is actually on disk.

    Returns the updated take and the number of recoverable frames. Nothing is
    deleted and no frame data is rewritten: only the take's own metadata is
    corrected so it stops claiming to be mid-recording.
    """
    from kinecapture.domain.enums import TakeState  # local: avoids a cycle at import

    paths = workspace.take_paths(take)
    if not path_exists(paths.skeleton_stream):
        take.state = TakeState.FAILED
        take.notes = f"{take.notes}\n[Kurtarma: iskelet akışı bulunamadı]".strip()
        workspace.save_take(take)
        return take, 0

    stream = load_skeleton_stream(paths.skeleton_stream)
    take.metrics.frames_written = stream.frame_count
    take.metrics.duration_s = stream.duration_s
    if stream.frame_count > 1 and stream.duration_s > 0:
        take.metrics.measured_fps = (stream.frame_count - 1) / stream.duration_s
    take.state = TakeState.PARTIAL
    note = f"[Kurtarıldı: {stream.frame_count} kare"
    if stream.truncated:
        note += ", son satır yarım"
    take.notes = f"{take.notes}\n{note}]".strip()
    workspace.save_take(take)
    logger.info(
        "Yarım kayıt kurtarıldı: %s (%d kare)", take.take_id, stream.frame_count
    )
    return take, stream.frame_count


__all__ = [
    "LoadedTake",
    "ProxyVideoReader",
    "SkeletonFrame",
    "SkeletonStream",
    "load_skeleton_stream",
    "load_take",
    "recover_partial_take",
]
