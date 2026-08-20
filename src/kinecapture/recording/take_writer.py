"""Take writer: turns a stream of frames into a durable, recoverable take.

What gets written
-----------------
``derived/skeleton.jsonl``
    One JSON record per frame: frame index, host and camera timestamps, and
    every detected body. Append-safe and flushed per frame, so an interrupted
    recording keeps everything written up to the moment it stopped. This is the
    authoritative pose record.

``derived/proxy.mp4``
    A reduced-width colour proxy used for scrubbing during review. It is a
    *convenience* copy, never the raw record.

``raw/capture.svo2``
    The ZED SDK's own recording, written by the SDK itself. Immutable, and
    sufficient to regenerate colour and depth at full fidelity, which is why
    depth frames are not stored a second time by default.

Finalisation
------------
Finalising is staged: streams are closed and flushed, metrics are computed from
what was actually written, checksums are taken, and only then is ``take.json``
rewritten with ``state=FINALIZED``. A take that never reaches that point stays
``PARTIAL`` and is offered for recovery at start-up instead of being mistaken
for a complete recording.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture import SKELETON_STREAM_SCHEMA_VERSION
from kinecapture.core.errors import StorageError
from kinecapture.core.fingerprint import checksum_manifest
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.jsonio import JsonlWriter, write_json
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import (
    ensure_dir,
    is_too_long_for_external_tools,
    path_exists,
    safe_external_path,
)
from kinecapture.dataset.workspace import ProjectWorkspace, TakePaths
from kinecapture.domain.enums import TakeState
from kinecapture.domain.models import FramePacket
from kinecapture.domain.project import Take, TakeQualityMetrics

logger = get_logger(__name__)


class _QualityAccumulator:
    """Running quality statistics, computed while frames stream past.

    Kept incremental on purpose: a five-minute take must not require a second
    pass over the data, and the numbers must be available the instant recording
    stops so the operator can decide whether to re-shoot.
    """

    def __init__(self) -> None:
        self.frames = 0
        self.frames_with_body = 0
        self.frames_with_multiple_bodies = 0
        self.confidence_sum = 0.0
        self.confidence_count = 0
        self.valid_ratio_sum = 0.0
        self.valid_ratio_count = 0
        self.body_ids: set[int] = set()
        self.body_id_changes = 0
        self.first_camera_ts: Optional[int] = None
        self.last_camera_ts: Optional[int] = None
        self.first_frame_index: Optional[int] = None
        self.last_frame_index: Optional[int] = None
        self.max_gap_ms = 0.0
        self._previous_camera_ts: Optional[int] = None
        self._active_body_id: Optional[int] = None

    def add(self, packet: FramePacket, active_body_id: Optional[int]) -> None:
        self.frames += 1
        if self.first_frame_index is None:
            self.first_frame_index = packet.frame_index
        self.last_frame_index = packet.frame_index

        camera_ts = packet.camera_timestamp_ns
        if camera_ts:
            if self.first_camera_ts is None:
                self.first_camera_ts = camera_ts
            self.last_camera_ts = camera_ts
            if self._previous_camera_ts is not None:
                gap_ms = (camera_ts - self._previous_camera_ts) / 1e6
                self.max_gap_ms = max(self.max_gap_ms, gap_ms)
            self._previous_camera_ts = camera_ts

        if packet.bodies:
            self.frames_with_body += 1
            if len(packet.bodies) > 1:
                self.frames_with_multiple_bodies += 1
            for body in packet.bodies:
                self.body_ids.add(body.tracking_id)
                confidence = body.mean_confidence()
                if np.isfinite(confidence):
                    self.confidence_sum += confidence
                    self.confidence_count += 1
                self.valid_ratio_sum += body.valid_joint_ratio
                self.valid_ratio_count += 1

        if active_body_id is not None:
            if self._active_body_id is not None and active_body_id != self._active_body_id:
                self.body_id_changes += 1
            self._active_body_id = active_body_id

    def metrics(
        self, *, target_fps: float, frames_written: int, dropped: int, backend_dropped: int
    ) -> TakeQualityMetrics:
        duration = 0.0
        if self.first_camera_ts is not None and self.last_camera_ts is not None:
            duration = max(0.0, (self.last_camera_ts - self.first_camera_ts) / 1e9)

        expected_span = 0
        if self.first_frame_index is not None and self.last_frame_index is not None:
            expected_span = self.last_frame_index - self.first_frame_index + 1
        missing = max(0, expected_span - self.frames)

        measured_fps = (self.frames - 1) / duration if duration > 0 and self.frames > 1 else 0.0
        return TakeQualityMetrics(
            duration_s=duration,
            target_fps=target_fps,
            measured_fps=measured_fps,
            frames_written=frames_written,
            frames_dropped_recording=dropped,
            backend_dropped_frames=backend_dropped,
            missing_frame_indices=missing,
            frames_with_body=self.frames_with_body,
            frames_with_multiple_bodies=self.frames_with_multiple_bodies,
            tracking_coverage=(
                self.frames_with_body / self.frames if self.frames else 0.0
            ),
            mean_joint_confidence=(
                self.confidence_sum / self.confidence_count
                if self.confidence_count
                else float("nan")
            ),
            mean_valid_joint_ratio=(
                self.valid_ratio_sum / self.valid_ratio_count
                if self.valid_ratio_count
                else float("nan")
            ),
            body_id_changes=self.body_id_changes,
            distinct_body_ids=len(self.body_ids),
            max_frame_gap_ms=self.max_gap_ms,
        )


class ProxyVideoWriter:
    """Reduced-resolution MP4 for review scrubbing.

    OpenCV is an optional runtime concern: if it is missing or the codec cannot
    be opened, recording continues without a proxy and the take records why.
    Losing the ability to scrub is a degraded review experience; losing the
    skeleton stream would be data loss, and the two are not traded off.
    """

    def __init__(self, path: Path, fps: float, target_width: int) -> None:
        self.path = Path(path)
        self.fps = float(fps) if fps > 0 else 30.0
        self.target_width = int(target_width)
        self._writer: Any = None
        self._size: Optional[tuple[int, int]] = None
        self._frames = 0
        self.unavailable_reason: str = ""

    @property
    def frames_written(self) -> int:
        return self._frames

    @property
    def is_open(self) -> bool:
        return self._writer is not None

    def _open(self, width: int, height: int) -> None:
        try:
            import cv2  # noqa: PLC0415 - optional at runtime
        except ImportError as exc:
            self.unavailable_reason = f"opencv-python bulunamadı: {exc}"
            logger.warning("Proxy video yazılamıyor: %s", self.unavailable_reason)
            return

        if is_too_long_for_external_tools(self.path):
            # OpenCV cannot open an extended-length path. The proxy is a review
            # convenience, so it degrades here instead of failing the recording.
            self.unavailable_reason = (
                "Hedef yol Windows uzunluk sinirini asiyor; proxy video atlandi."
            )
            logger.warning("Proxy video yazilamiyor: %s", self.unavailable_reason)
            return

        scale = min(1.0, self.target_width / max(1, width))
        # Even dimensions: most MP4 encoders reject odd ones.
        out_w = max(2, int(round(width * scale)) // 2 * 2)
        out_h = max(2, int(round(height * scale)) // 2 * 2)
        ensure_dir(self.path.parent)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            safe_external_path(self.path), fourcc, self.fps, (out_w, out_h)
        )
        if not writer.isOpened():
            self.unavailable_reason = "MP4 kodlayıcı açılamadı (mp4v)."
            logger.warning("Proxy video yazılamıyor: %s", self.unavailable_reason)
            return
        self._writer = writer
        self._size = (out_w, out_h)

    def write(self, rgb: np.ndarray) -> None:
        if self._writer is None:
            if self.unavailable_reason:
                return
            self._open(int(rgb.shape[1]), int(rgb.shape[0]))
            if self._writer is None:
                return
        import cv2  # noqa: PLC0415 - already proven importable above

        assert self._size is not None
        frame = rgb
        if (frame.shape[1], frame.shape[0]) != self._size:
            frame = cv2.resize(frame, self._size, interpolation=cv2.INTER_AREA)
        self._writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        self._frames += 1

    def close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            try:
                writer.release()
            except Exception as exc:  # pragma: no cover - codec dependent
                logger.warning("Proxy video kapatılırken hata: %s", exc)


class TakeWriter:
    """Owns every file belonging to one in-progress take.

    Instances are used from the recording worker thread only. The public
    counters are read by the GUI, so they are guarded by a lock.
    """

    def __init__(
        self,
        workspace: ProjectWorkspace,
        take: Take,
        paths: TakePaths,
        *,
        write_proxy_video: bool = True,
    ) -> None:
        self.workspace = workspace
        self.take = take
        self.paths = paths
        self._lock = threading.Lock()
        self._skeleton: Optional[JsonlWriter] = None
        self._proxy: Optional[ProxyVideoWriter] = None
        self._accumulator = _QualityAccumulator()
        self._frames_written = 0
        self._frames_dropped = 0
        self._backend_dropped = 0
        self._closed = False
        self._started_monotonic = time.perf_counter()
        self._write_proxy = write_proxy_video
        self._first_frame_index: Optional[int] = None

        paths.ensure_dirs()
        self._skeleton = JsonlWriter(paths.skeleton_stream)
        self._skeleton.write(self._stream_header())
        if write_proxy_video:
            self._proxy = ProxyVideoWriter(
                paths.proxy_video,
                fps=float(take.capture_profile.fps),
                target_width=int(take.capture_profile.proxy_video_width),
            )

    # ------------------------------------------------------------- counters
    @property
    def frames_written(self) -> int:
        with self._lock:
            return self._frames_written

    @property
    def frames_dropped(self) -> int:
        with self._lock:
            return self._frames_dropped

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self._started_monotonic

    def note_dropped(self, count: int = 1) -> None:
        """Record frames the recording queue could not accept.

        This is capture loss, reported separately from preview throttling, and
        it is never rolled into a single "dropped frames" number.
        """
        with self._lock:
            self._frames_dropped += count

    # --------------------------------------------------------------- header
    def _stream_header(self) -> dict[str, Any]:
        """First line of the skeleton stream: enough to read it standalone."""
        camera = self.take.camera_info
        return {
            "record": "header",
            "schema_version": SKELETON_STREAM_SCHEMA_VERSION,
            "take_id": self.take.take_id,
            "session_id": self.take.session_id,
            "participant_id": self.take.participant_id,
            "origin": self.take.origin.value,
            "skeleton_format": self.take.skeleton_format,
            "coordinate_system": camera.coordinate_system if camera else "unspecified",
            "length_unit": camera.length_unit if camera else "unspecified",
            "target_fps": self.take.capture_profile.fps,
            "started_at": self.take.started_at,
        }

    # ---------------------------------------------------------------- write
    def write_frame(self, packet: FramePacket, active_body_id: Optional[int] = None) -> None:
        """Persist one frame. Called on the writer thread only."""
        if self._closed:
            raise StorageError(
                "Kapatılmış kayda yazılamaz.", code="take_writer_closed"
            )
        if self._first_frame_index is None:
            self._first_frame_index = packet.frame_index

        record = {
            "record": "frame",
            "i": packet.frame_index,
            "host_ns": packet.host_timestamp_ns,
            "cam_ns": packet.camera_timestamp_ns,
            "bodies": [body.to_record() for body in packet.bodies],
        }
        if active_body_id is not None:
            record["active_id"] = int(active_body_id)
        assert self._skeleton is not None
        self._skeleton.write(record)

        if self._proxy is not None:
            self._proxy.write(packet.color_frame)

        self._accumulator.add(packet, active_body_id)
        with self._lock:
            self._frames_written += 1
            self._backend_dropped = max(
                self._backend_dropped, int(packet.backend_dropped_frames)
            )

    def record_marker(self, frame_index: int, label: str = "") -> dict[str, Any]:
        """Store an operator marker as both a stream record and take metadata."""
        marker = {
            "frame_index": int(frame_index),
            "label": label,
            "created_at": utc_now_iso(),
        }
        if self._skeleton is not None and not self._closed:
            self._skeleton.write({"record": "marker", **marker})
        self.take.markers.append(marker)
        return marker

    def record_body_id_change(
        self, frame_index: int, previous_id: Optional[int], new_id: Optional[int]
    ) -> None:
        """Note that the followed identity changed - never done silently."""
        event = {
            "frame_index": int(frame_index),
            "previous_id": previous_id,
            "new_id": new_id,
            "at": utc_now_iso(),
        }
        self.take.body_id_events.append(event)
        if self._skeleton is not None and not self._closed:
            self._skeleton.write({"record": "body_id_change", **event})

    # ------------------------------------------------------------- finalise
    def close_streams(self) -> None:
        """Flush and close every stream. Idempotent; never raises."""
        if self._closed:
            return
        self._closed = True
        if self._skeleton is not None:
            try:
                self._skeleton.close()
            except Exception as exc:  # pragma: no cover - shutdown path
                logger.warning("İskelet akışı kapatılırken hata: %s", exc)
        if self._proxy is not None:
            self._proxy.close()

    def finalize(self, *, state: TakeState = TakeState.FINALIZED) -> Take:
        """Close streams, compute metrics, write checksums, publish ``take.json``.

        Returns the updated take. If anything below fails the take is left in a
        state that says so, rather than being marked complete.
        """
        self.close_streams()

        take = self.take
        metrics = self._accumulator.metrics(
            target_fps=float(take.capture_profile.fps),
            frames_written=self._frames_written,
            dropped=self._frames_dropped,
            backend_dropped=self._backend_dropped,
        )
        take.metrics = metrics
        take.ended_at = utc_now_iso()
        take.state = state

        files: dict[str, str] = {}
        if path_exists(self.paths.skeleton_stream):
            files["skeleton_stream"] = f"derived/{self.paths.skeleton_stream.name}"
        if self._proxy is not None and path_exists(self.paths.proxy_video):
            files["proxy_video"] = f"derived/{self.paths.proxy_video.name}"
        elif self._proxy is not None and self._proxy.unavailable_reason:
            take.notes = (
                f"{take.notes}\n[Proxy video yazılamadı: "
                f"{self._proxy.unavailable_reason}]"
            ).strip()
        if path_exists(self.paths.native_recording):
            files["native_recording"] = f"raw/{self.paths.native_recording.name}"
        take.files = files

        write_json(
            self.paths.quality,
            {
                "take_id": take.take_id,
                "computed_at": utc_now_iso(),
                "metrics": metrics.to_dict(),
                "proxy_video_frames": self._proxy.frames_written if self._proxy else 0,
                "proxy_video_unavailable_reason": (
                    self._proxy.unavailable_reason if self._proxy else "disabled"
                ),
            },
            overwrite=True,
        )

        # take.json is written *before* checksums so the manifest can cover it.
        self.workspace.save_take(take)
        write_json(
            self.paths.checksums,
            checksum_manifest(self.paths.checksum_targets()),
            overwrite=True,
        )
        logger.info(
            "Kayıt tamamlandı: %s (%d kare, %.1f s, %.1f FPS)",
            take.take_id,
            metrics.frames_written,
            metrics.duration_s,
            metrics.measured_fps,
        )
        return take

    def abort(self, reason: str = "") -> Take:
        """Stop writing and mark the take ``PARTIAL`` without losing what exists."""
        logger.warning("Kayıt yarıda kaldı (%s): %s", self.take.take_id, reason)
        if reason:
            self.take.notes = f"{self.take.notes}\n[Yarım kaldı: {reason}]".strip()
        return self.finalize(state=TakeState.PARTIAL)


__all__ = ["ProxyVideoWriter", "TakeWriter"]
