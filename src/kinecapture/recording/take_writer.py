"""Durable capture writer with explicitly selected products.

Minimum real capture stores immutable SVO2 stereo source, a per-grab timestamp
index, calibration/provenance and integrity telemetry. The default codec is
H264_LOSSLESS; acceptance by the SDK is not proof of decoded file coverage.

Live skeleton, proxy, separate colour and measured depth archives are optional.
The synthetic backend retains colour chunks and deterministic generator
provenance. Offline processing produces separately versioned derived results.

Stream closure and payload checksums precede the final take.json commit. Failed
or interrupted closure never publishes a complete take. Mutable human curation
is excluded from immutable payload checksums.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture import (
    RAW_ARCHIVE_SCHEMA_VERSION,
    SKELETON_STREAM_SCHEMA_VERSION,
)
from kinecapture.capture.subject_lock import FrameAssociation, SubjectLock
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
    long_path,
)
from kinecapture.dataset.workspace import ProjectWorkspace, TakePaths
from kinecapture.domain.enums import TakeState
from kinecapture.domain.models import FramePacket
from kinecapture.domain.project import Take, TakeQualityMetrics
from kinecapture.recording.rgbd_archive import (
    DepthCodec,
    RgbdArchiveReader,
    RgbdArchiveWriter,
)

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
        self.frames_with_other_people = 0
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
                self.frames_with_other_people += 1
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
            frames_with_other_people=self.frames_with_other_people,
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
        write_proxy_video: Optional[bool] = None,
        subject_lock: Optional[SubjectLock] = None,
        archive_color: bool = False,
        native_recording_active: bool = False,
        backend_drop_baseline: int = 0,
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
        self._backend_drop_baseline = backend_drop_baseline
        self._integrity_issues: set[str] = set()
        self._recording_status: Optional[dict[str, Any]] = None
        self._previous_timestamp: Optional[int] = None
        self._timestamp_gaps = 0
        #: Frames the SDK told us it did not write into the SVO, and frames on
        #: which it repeated the previous camera timestamp. Counted rather than
        #: flagged: "2 of 524" and "all of them" are not the same recording,
        #: and a boolean cannot tell them apart.
        self._native_unwritten = 0
        self._timestamp_repeats = 0
        self._gap_sum = self._gap_squared_sum = 0.0
        self._closed = False
        self._started_monotonic = time.perf_counter()
        self._write_proxy = write_proxy_video
        self._first_frame_index: Optional[int] = None
        self.subject_lock = subject_lock
        self._native_recording_active = bool(native_recording_active)
        self._chunk_table: list[dict[str, Any]] = []
        self._external_raw_failure = ""
        self.subject_anchors: list[dict] = []
        take.processing_status = "live" if take.capture_profile.store_skeleton else "awaiting_processing"
        workspace.save_take(take)

        paths.ensure_dirs()
        if take.capture_profile.store_skeleton:
            self._skeleton = JsonlWriter(paths.skeleton_stream)
            self._skeleton.write(self._stream_header())
        if take.capture_profile.store_proxy and write_proxy_video is not False:
            self._proxy = ProxyVideoWriter(
                paths.proxy_video,
                fps=float(take.capture_profile.fps),
                target_width=int(take.capture_profile.proxy_video_width),
            )

        # --- the immutable raw archive --------------------------------
        # Colour is archived here only when nothing else is keeping it: a ZED
        # already writes its stereo images to the SVO2 and replay was verified
        # to return them, so a second copy would double the cost for nothing.
        profile = take.capture_profile
        self._archive: Optional[RgbdArchiveWriter] = None
        archive_color = bool(archive_color or profile.store_color)
        self._archive_color = archive_color
        self._raw_index: Optional[JsonlWriter] = None
        if profile.archives_depth or archive_color:
            codec = (
                DepthCodec.UINT16_QUANTISED
                if str(profile.depth_archive).lower().startswith("uint16")
                else DepthCodec.FLOAT32_LOSSLESS
            )
            self._archive = RgbdArchiveWriter(
                paths.rgbd_dir,
                depth_codec=codec,
                store_color=archive_color,
            )
        self._raw_index = JsonlWriter(paths.raw_index)
        self._raw_index.write(self._raw_index_header())

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
            "subject_id": (
                self.subject_lock.subject_id if self.subject_lock else None
            ),
        }

    def _raw_index_header(self) -> dict[str, Any]:
        """First line of the raw index: the synchronisation contract itself.

        Two numbers in this project are easy to confuse and must never be: the
        *position* is where a frame sits in this recording's own sequence and is
        what annotation bounds refer to; the *camera frame index* is the
        backend successful-grab ordinal, not a physical camera counter. Both are here,
        in every record, precisely so nothing downstream has to infer one from
        the other.
        """
        camera = self.take.camera_info
        return {
            "record": "header",
            "schema_version": RAW_ARCHIVE_SCHEMA_VERSION,
            "take_id": self.take.take_id,
            "origin": self.take.origin.value,
            "coordinate_system": camera.coordinate_system if camera else "unspecified",
            "length_unit": camera.length_unit if camera else "unspecified",
            "target_fps": self.take.capture_profile.fps,
            "fields": {
                "p": "recording-local position, 0-based, the annotation contract",
                "i": "camera frame index as reported by the backend",
                "host_ns": "host clock when the frame was received",
                "cam_ns": "camera timestamp of the image",
                "color": "colour archived in this take's own rgbd chunks",
                "depth": "depth archived in this take's own rgbd chunks",
                "skel": "a pose record was written for this position",
                "native": "the backend's own recording was running",
                "subj": "authoritative selected-subject association",
            },
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
        position = self._frames_written

        # --- authoritative subject association --------------------------
        # Decided here, once, while the frame is in hand. Downstream code
        # reads this answer instead of re-deriving one, which is how "which
        # skeleton is the participant?" stops having two possible answers.
        association: Optional[FrameAssociation] = None
        if self._skeleton is not None and self.subject_lock is not None and self.subject_lock.is_selected:
            association = self.subject_lock.update(
                packet.bodies,
                frame_index=packet.frame_index,
                timestamp_ns=packet.camera_timestamp_ns,
            )
            active_body_id = association.tracking_id

        record = {
            "record": "frame",
            "i": packet.frame_index,
            "p": position,
            "host_ns": packet.host_timestamp_ns,
            "cam_ns": packet.camera_timestamp_ns,
            "bodies": [body.to_record() for body in packet.bodies] if self._skeleton else [],
            "source_position": packet.source_position,
            "integrity_issues": list(packet.integrity_issues),
        }
        if active_body_id is not None:
            record["active_id"] = int(active_body_id)
        if association is not None:
            record["subject"] = association.to_record()
        if self._skeleton is not None:
            self._skeleton.write(record)

        if self._proxy is not None:
            if packet.color_frame is None:
                raise StorageError("Proxy için RGB karesi eksik.", code="rgb_missing")
            self._proxy.write(packet.color_frame)

        # --- the immutable raw archive ---------------------------------
        color_ok = depth_ok = True
        if self._archive is not None:
            if self._archive_color and packet.color_frame is None:
                raise StorageError("Ham renk karesi eksik.", code="raw_color_missing")
            if self.take.capture_profile.archives_depth and packet.depth_frame is None:
                raise StorageError("İstenen derinlik karesi eksik.", code="raw_depth_missing")
            color_ok, depth_ok = self._archive.add_frame(
                position,
                packet.color_frame if self._archive_color else None,
                packet.depth_frame if self.take.capture_profile.archives_depth else None,
            )

        if self._raw_index is not None:
            index_record: dict[str, Any] = {
                "record": "frame",
                "p": position,
                "i": packet.frame_index,
                "host_ns": packet.host_timestamp_ns,
                "cam_ns": packet.camera_timestamp_ns,
                "skel": self._skeleton is not None,
                "source_position": packet.source_position,
                "integrity_issues": list(packet.integrity_issues),
                "color": bool(self._archive_color and color_ok),
                "depth": bool(
                    packet.depth_frame is not None
                    and self.take.capture_profile.archives_depth
                    and self._archive is not None
                    and depth_ok
                ),
                "native": self._native_recording_active,
                "status": packet.capture_status.value,
            }
            if association is not None:
                index_record["subj"] = association.to_record()
            self._raw_index.write(index_record)

        self._accumulator.add(packet, active_body_id)
        self._integrity_issues.update(packet.integrity_issues)
        if packet.recording_status is not None:
            self._recording_status = dict(packet.recording_status)
            if packet.recording_status.get("status") is False:
                self._native_unwritten += 1
                self._integrity_issues.add("native_recording_status_failed")
        ts = packet.camera_timestamp_ns
        if ts < 0 or (ts == 0 and packet.origin.value != "synthetic"):
            self._integrity_issues.add("camera_timestamp_missing")
        if self._previous_timestamp is not None:
            gap = (ts - self._previous_timestamp) / 1e6
            self._gap_sum += gap
            self._gap_squared_sum += gap * gap
            if gap < 0:
                self._integrity_issues.add("camera_timestamp_non_monotonic")
            elif gap == 0:
                # The ZED gave two consecutive frames the same timestamp once
                # in 524 frames and twice in 1648 on 16 September. Time did not
                # go backwards and no frame was lost; calling it
                # "non-monotonic" demoted two intact recordings.
                self._timestamp_repeats += 1
                self._integrity_issues.add("camera_timestamp_repeated")
            if gap > 1500 / self.take.capture_profile.fps:
                self._timestamp_gaps += 1
        self._previous_timestamp = ts
        with self._lock:
            self._frames_written += 1
            self._backend_dropped = max(
                self._backend_dropped, max(0, int(packet.backend_dropped_frames) - self._backend_drop_baseline)
            )

    def _raw_source_loss(self) -> str:
        """Why the immutable source is incomplete, or an empty string.

        A sentence rather than a list of codes, because this is what ends up in
        the take's notes and in front of the operator.
        """
        reasons: list[str] = []
        if self._frames_written == 0:
            reasons.append("hiç kare yazılmadı")
        if self._frames_dropped:
            reasons.append(f"{self._frames_dropped} kare yazma kuyruğunda kayboldu")
        if self._backend_dropped:
            reasons.append(f"kamera {self._backend_dropped} kareyi düşürdü")
        if self._native_unwritten:
            reasons.append(
                f"SDK {self._native_unwritten} karenin SVO'ya yazılmadığını bildirdi"
            )
        if "camera_timestamp_missing" in self._integrity_issues:
            reasons.append("bazı karelerde kamera zaman damgası yok")
        if "camera_timestamp_non_monotonic" in self._integrity_issues:
            reasons.append("kamera zaman damgası geriye gitti")
        return " · ".join(reasons)

    def _integrity_summary(self) -> str:
        """What was measured that is worth saying but is not missing data."""
        notes: list[str] = []
        if self._timestamp_repeats:
            notes.append(
                f"kamera {self._timestamp_repeats} karede önceki zaman damgasını "
                "tekrarladı"
            )
        if self._timestamp_gaps:
            notes.append(f"{self._timestamp_gaps} karede beklenenden büyük aralık")
        rest = sorted(self._integrity_issues - {"camera_timestamp_repeated"})
        if rest:
            notes.append(", ".join(rest))
        return " · ".join(notes) or "kayıt bütünlüğü notları var"

    def note_raw_failure(self, reason: str) -> None:
        """Record that the immutable source is not trustworthy.

        Called for problems the archive writer itself cannot see - a native
        recorder that would not stop cleanly, for instance. It is what stops
        such a take being finalised as complete.
        """
        self._external_raw_failure = self._external_raw_failure or reason
        logger.error("Ham kayıt sorunu: %s", reason)

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
        """Close all writers; a timeout must not permit premature publication."""
        if self._closed:
            return
        if self._skeleton is not None:
            try:
                self._skeleton.close()
            except Exception as exc:  # pragma: no cover - shutdown path
                self.note_raw_failure(f"İskelet akışı kapatılamadı: {exc}")
        if self._proxy is not None:
            self._proxy.close()
        if self._archive is not None:
            try:
                self._chunk_table = self._archive.close()
            except Exception as exc:  # pragma: no cover - shutdown path
                logger.error("RGB-D arşivi kapatılırken hata: %s", exc)
                self._archive.depth.failure = f"{type(exc).__name__}: {exc}"
                raise
        if self._raw_index is not None:
            try:
                self._raw_index.close()
            except Exception as exc:  # pragma: no cover - shutdown path
                self.note_raw_failure(f"Ham indeks kapatılamadı: {exc}")
        self._closed = True

    def finalize(self, *, state: TakeState = TakeState.FINALIZED) -> Take:
        """Close streams, compute metrics, write checksums, publish ``take.json``.

        Returns the updated take. If anything below fails the take is left in a
        state that says so, rather than being marked complete.
        """
        self.close_streams()
        if self._native_recording_active and (
            not path_exists(self.paths.native_recording)
            or Path(long_path(self.paths.native_recording)).stat().st_size == 0
        ):
            self.note_raw_failure("SDK başladı dedi ancak kapatılmış SVO2 kaynağı eksik/boş.")

        take = self.take
        metrics = self._accumulator.metrics(
            target_fps=float(take.capture_profile.fps),
            frames_written=self._frames_written,
            dropped=self._frames_dropped,
            backend_dropped=self._backend_dropped,
        )
        self._apply_archive_metrics(metrics)
        take.metrics = metrics
        take.ended_at = utc_now_iso()

        # A take whose immutable source is incomplete is not a finished take.
        # It keeps every byte it did manage to write - nothing is deleted - but
        # it says PARTIAL, so it can never be mistaken for a reprocessable
        # recording later. Missing frames and merely imperfect ones are both
        # written down and answered differently: only frames that are actually
        # absent decide the state. Until 17 September the two were one test
        # (``or self._integrity_issues``), so a camera that stamped one
        # microsecond twice demoted a take whose 524 frames were all on disk,
        # under a note about an RGB-D archive that had been switched off on
        # purpose.
        lost = self._raw_source_loss()
        if lost:
            self.note_raw_failure(lost)
            metrics.raw_archive_failure = self._external_raw_failure
        elif self._integrity_issues:
            note = self._integrity_summary()
            take.notes = f"{take.notes}\n[Kayıt notu: {note}]".strip()
            logger.warning("Kayıt notlarla tamamlandı: %s", note)
        if state is TakeState.FINALIZED and metrics.has_raw_archive_loss:
            state = TakeState.PARTIAL
            reason = metrics.raw_archive_failure or (
                f"renk {metrics.color_frames_dropped}, derinlik "
                f"{metrics.depth_frames_dropped} kare arşivlenemedi"
            )
            # The archive wording only applies when the archive is what was
            # lost. It used to be printed over every kind of loss.
            label = (
                "Ham RGB-D arşivi eksik"
                if (metrics.color_frames_dropped or metrics.depth_frames_dropped)
                else "Ham kaynak eksik"
            )
            take.notes = f"{take.notes}\n[{label}: {reason}]".strip()
            logger.error("%s, kayıt PARTIAL: %s", label, reason)
        take.state = state
        take.processing_status = "live" if self._skeleton is not None else "awaiting_processing"

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
        if path_exists(self.paths.raw_index):
            files["raw_index"] = "raw/rgbd/index.jsonl"
        if self._archive is not None:
            files["rgbd_archive"] = "raw/rgbd/"
        take.files = files

        write_json(
            self.paths.raw_manifest, self._raw_manifest(metrics), overwrite=True
        )

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

        # take.json is the final commit, and remains mutable for human curation.
        # It must not invalidate the immutable payload checksums on every note.
        write_json(
            self.paths.checksums,
            checksum_manifest({
                key: path for key, path in self.paths.checksum_targets().items()
                if key != "take.json"
            }),
            overwrite=True,
        )
        self.workspace.save_take(take)
        logger.info(
            "Kayıt tamamlandı: %s (%d kare, %.1f s, %.1f FPS)",
            take.take_id,
            metrics.frames_written,
            metrics.duration_s,
            metrics.measured_fps,
        )
        return take

    # ------------------------------------------------------- raw archive
    def _apply_archive_metrics(self, metrics: TakeQualityMetrics) -> None:
        """Fold the per-stream archive counters into the take's quality."""
        if self._external_raw_failure:
            metrics.raw_archive_failure = self._external_raw_failure
        if self._archive is not None:
            metrics.depth_frames_archived = self._archive.depth.frames_written
            metrics.depth_frames_dropped = self._archive.depth.frames_dropped
            metrics.color_frames_archived = self._archive.color.frames_written
            metrics.color_frames_dropped = self._archive.color.frames_dropped
            metrics.raw_archive_failure = (
                self._archive.depth.failure
                or self._archive.color.failure
                or self._external_raw_failure
            )
        lock = self.subject_lock
        if lock is not None and lock.is_selected:
            counters = lock.counters
            metrics.subject_locked_frames = counters["locked_frames"]
            metrics.subject_lost_frames = counters["lost_frames"]
            metrics.subject_ambiguous_frames = counters["ambiguous_frames"]
            metrics.subject_reassociations = counters["reassociations"]
            metrics.subject_manual_confirmations = counters["manual_confirmations"]

    def _raw_manifest(self, metrics: TakeQualityMetrics) -> dict[str, Any]:
        """Describe the raw archive well enough to reprocess it years later."""
        take = self.take
        camera = take.camera_info
        profile = take.capture_profile
        archive = self._archive
        reader = RgbdArchiveReader(self.paths.rgbd_dir)
        stored = reader.positions() if archive is not None else {"depth": [], "color": []}

        native_present = path_exists(self.paths.native_recording)
        return {
            "schema_version": RAW_ARCHIVE_SCHEMA_VERSION,
            "take_id": take.take_id,
            "created_at": utc_now_iso(),
            "origin": take.origin.value,
            "frames_recorded": self._frames_written,
            "capture_profile": profile.to_dict(),
            "camera_info": camera.to_dict() if camera else None,
            "integrity": {
                "issues": sorted(self._integrity_issues),
                "queue_frames_lost": self._frames_dropped,
                "backend_drop_delta": self._backend_dropped,
                "backend_drop_baseline": self._backend_drop_baseline,
                "timestamp_gaps_over_1_5_intervals": self._timestamp_gaps,
                "timestamp_repeats": self._timestamp_repeats,
                "native_frames_unwritten": self._native_unwritten,
                "timestamp_gap_max_ms": metrics.max_frame_gap_ms,
                "timestamp_gap_std_ms": (max(0.0, self._gap_squared_sum / max(1, self._frames_written - 1) - (self._gap_sum / max(1, self._frames_written - 1)) ** 2) ** 0.5),
                "last_sdk_recording_status": self._recording_status,
                "source_frame_mapping": "pending_offline_timestamp_reconciliation",
            },
            "synchronisation": {
                "index_file": "raw/rgbd/index.jsonl",
                "position": (
                    "0 tabanlı, bu kaydın kendi sırası. Etiket sınırları ve "
                    "derived/skeleton.jsonl bu konumu kullanır."
                ),
                "camera_frame_index": (
                    "Backend successful-grab ordinal; fiziksel kamera sayacı değildir."
                ),
                "camera_timestamp_ns": (
                    "Görüntünün kamera zaman damgası. SVO2 içine mikrosaniye "
                    "çözünürlüğünde yazılır: yeniden oynatmada son üç hane "
                    "sıfırlanmış olarak geri gelir (ölçülen fark 300 ns)."
                ),
                "note": (
                    "Akış konumu ile kamera kare numarası birbirinin yerine "
                    "kullanılamaz."
                ),
            },
            "native_recording": {
                "present": native_present,
                "file": "raw/capture.svo2" if native_present else None,
                "format": "svo2" if native_present else None,
                "compression_mode": profile.native_compression,
                "lossless": str(profile.native_compression).upper().endswith("LOSSLESS"),
                "stores": "stereo görüntüler ve sensör verisi",
                "does_not_store": (
                    "Final metrik derinlik ve iskelet. Bunlar kayıtlı stereo kaynak, SDK ve işleme parametrelerinden sürümlü olarak yeniden hesaplanır."
                ),
                "replay_verified": (
                    "Bu take için henüz doğrulanmadı; offline işleme kaynak kapsamını kontrol eder."
                ),
            },
            "rgbd_archive": {
                "directory": "raw/rgbd/",
                "depth": {
                    "enabled": archive is not None and profile.archives_depth,
                    "codec": archive.depth_codec.value if archive else None,
                    "lossless": archive.depth_codec.is_lossless if archive else None,
                    "dtype": "float32",
                    "unit": "meter",
                    "invalid": "nan",
                    "frames": metrics.depth_frames_archived,
                    "dropped": metrics.depth_frames_dropped,
                    "chunks": archive.depth.chunks_written if archive else 0,
                    "bytes": archive.depth.bytes_written if archive else 0,
                    "positions_stored": len(stored["depth"]),
                },
                "color": {
                    "enabled": bool(self._archive_color),
                    "frames": metrics.color_frames_archived,
                    "dropped": metrics.color_frames_dropped,
                    "chunks": archive.color.chunks_written if archive else 0,
                    "bytes": archive.color.bytes_written if archive else 0,
                    "positions_stored": len(stored["color"]),
                    "source_of_truth": (
                        "raw/rgbd/color_*.kcc"
                        if self._archive_color
                        else "raw/capture.svo2"
                    ),
                },
                "chunks": list(getattr(self, "_chunk_table", [])),
                "recovery": (
                    "Her chunk kendi başlığıyla bağımsız okunur; yarım kalan "
                    "chunk okurken tespit edilir ve yalnız o chunk kaybolur."
                ),
            },
            "capture_provenance": {
                "camera_model": camera.model if camera else None,
                "serial_number": camera.serial_number if camera else None,
                "sdk_version": camera.sdk_version if camera else None,
                "resolution": list(camera.resolution) if camera else None,
                "target_fps": profile.fps,
                "depth_mode": profile.depth_mode,
                "coordinate_system": camera.coordinate_system if camera else None,
                "length_unit": camera.length_unit if camera else None,
                "body_format": take.skeleton_format,
                "calibration": (
                    (camera.extra or {}).get("left_camera_calibration")
                    if camera
                    else None
                ),
            },
            "subject": (
                self.subject_lock.provenance()
                if self.subject_lock is not None and self.subject_lock.is_selected
                else {"selected": False}
            ),
            "immutability": (
                "Bu dizin etiketleme veya export sırasında değiştirilmez. "
                "Türetilen her şey derived/ veya releases/ altına yazılır."
            ),
        }

    def abort(self, reason: str = "") -> Take:
        """Stop writing and mark the take ``PARTIAL`` without losing what exists."""
        logger.warning("Kayıt yarıda kaldı (%s): %s", self.take.take_id, reason)
        if reason:
            self.take.notes = f"{self.take.notes}\n[Yarım kaldı: {reason}]".strip()
        return self.finalize(state=TakeState.PARTIAL)


__all__ = ["ProxyVideoWriter", "TakeWriter"]
