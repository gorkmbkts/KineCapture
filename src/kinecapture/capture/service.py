"""Capture service: the boundary between the GUI and the camera backends.

Threading model
---------------
```text
 acquisition thread          recording queue          writer thread
 backend.grab_frame()  --->  bounded, size N   --->   TakeWriter.write_frame()
        |
        +----------------->  preview slot (latest wins, size 1)
                                    |
                             GUI QTimer polls
```

* The GUI thread never calls the backend and never touches the disk.
* The preview slot holds exactly one frame: when the GUI falls behind, the
  older preview frame is discarded and counted as a *preview* drop. That is
  acceptable and expected.
* The recording queue is bounded too, but overflowing it is **capture loss** and
  is counted separately, reported prominently, and stored in the take's quality
  metrics. The two numbers are never merged.
* ``stop`` and ``shutdown`` are idempotent and join their threads with a
  timeout, so closing the window cannot hang on a wedged device.

This module is Qt-free by design. The Qt adapter lives in
:mod:`kinecapture.capture.qt_bridge`.
"""

from __future__ import annotations

import os
import queue
import threading
import time
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture.camera.base import AvailabilityResult, CameraBackend
from kinecapture.capture.subject_lock import (
    SubjectLock,
    SubjectLockState,
    is_ambiguous_pick,
    pick_body_at_pixel,
)
from kinecapture.core.errors import CameraError, KineCaptureError, StorageError
from kinecapture.core.logging import get_logger
from kinecapture.core.state_machine import CaptureStateMachine, InvalidStateTransition
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import CaptureState, DataOrigin, TakeState
from kinecapture.domain.models import BodyPose, CameraInfo, CaptureStatistics, FramePacket
from kinecapture.domain.project import Session, Take
from kinecapture.recording.rgbd_archive import DepthCodec, estimate_bytes_per_second
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.preview.worker import LatestWorker
from kinecapture.visualization.skeleton_spec import SkeletonSpec

logger = get_logger(__name__)

FrameListener = Callable[[FramePacket], None]
ErrorListener = Callable[[KineCaptureError], None]
TakeListener = Callable[[Take], None]

#: How many frames the recording queue may buffer before overflow becomes
#: capture loss. At 30 fps this is four seconds of slack for a disk hiccup.
DEFAULT_RECORDING_QUEUE_SIZE = 120

#: How long stop/shutdown waits for each worker before giving up on it.
_JOIN_TIMEOUT_S = 5.0

#: Sentinel pushed onto the recording queue to end the writer thread.
_SHUTDOWN = object()


@dataclass(frozen=True)
class RecordingTargetCheck:
    """Whether the next take's raw file can be written where it would go.

    Built from the *prospective* path, before a take directory exists, so a
    refusal never leaves half a take behind and never interrupts the preview.
    """

    #: The longest raw-recording path this session can produce.
    path: Path
    length: int
    #: The backend's own ceiling, or ``None`` when it has none.
    limit: Optional[int]
    #: False for a backend that writes through Python and is not affected.
    needs_native: bool = True

    @property
    def ok(self) -> bool:
        if not self.needs_native or self.limit is None:
            return True
        return self.length <= self.limit

    @property
    def reason(self) -> str:
        if self.ok:
            return ""
        return (
            f"Kayıt hedefi bu kamera için fazla uzun: {self.length} karakter, "
            f"sınır {self.limit}."
        )

    def require(self) -> None:
        """Raise when the target cannot work. Called before anything is made."""
        if self.ok:
            return
        over = self.length - int(self.limit or 0)
        raise StorageError(
            self.reason,
            code="recording_target_path_too_long",
            remedy=(
                f"Veri klasörünü en az {over} karakter daha kısa bir yola alın "
                "(Ayarlar > Veri klasörü). Uygulamanın kendi dosyaları uzun "
                "yolu kullanabiliyor; kameranın kayıt kütüphanesi kullanamıyor."
            ),
            details={
                "path": str(self.path),
                "length": self.length,
                "limit": self.limit,
                "over_by": over,
            },
        )


class CaptureService:
    """Coordinates one camera backend, its threads, and the active recording."""

    def __init__(
        self,
        backend: CameraBackend,
        *,
        state_machine: Optional[CaptureStateMachine] = None,
        recording_queue_size: int = DEFAULT_RECORDING_QUEUE_SIZE,
        preview_processor: Optional[Callable] = None,
    ) -> None:
        if recording_queue_size < 1:
            raise ValueError("recording_queue_size must be >= 1")
        self._backend = backend
        self._state = state_machine or CaptureStateMachine()
        self._statistics = CaptureStatistics()
        self._stats_lock = threading.Lock()

        self._preview_slot: Optional[FramePacket] = None
        self._preview_lock = threading.Lock()
        self._preview_processor = preview_processor
        self._preview_worker: Optional[LatestWorker] = None
        self.pose_preview = None
        self._subject_anchor: Optional[dict] = None

        self._recording_queue: "queue.Queue[Any]" = queue.Queue(
            maxsize=recording_queue_size
        )
        self._acquisition_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._writer_stop = threading.Event()
        self._capture_gate = threading.Lock()
        self._boundary_pending = threading.Event()
        self._boundary_done = threading.Event()
        self._boundary_done.set()
        self._lifecycle_guard = threading.RLock()
        self._recording_accepting = False
        self._native_stop_failure = ""

        self._writer: Optional[TakeWriter] = None
        self._writer_guard = threading.Lock()
        self._active_take: Optional[Take] = None
        self._active_body_id: Optional[int] = None

        self._frame_listeners: list[FrameListener] = []
        self._error_listeners: list[ErrorListener] = []
        #: Starts refused before any frame was written. A counter, not a state:
        #: the camera is still previewing and the next attempt may succeed.
        self._recording_start_failures = 0
        self._take_listeners: list[TakeListener] = []

        self._camera_info: Optional[CameraInfo] = None
        self._shutdown = False
        self._last_error: Optional[KineCaptureError] = None
        self._acquisition_times: list[float] = []
        self.last_recording_status: Optional[dict] = None

        # The lock lives here rather than in the GUI: it is a capture concern,
        # it has to be consulted on the writer thread, and it must survive a
        # page being rebuilt.
        self._subject_lock = SubjectLock()
        self._subject_candidates: list[tuple[BodyPose, float]] = []
        self._last_dataset_root: Optional[Path] = None

    # -------------------------------------------------------------- exposure
    @property
    def backend(self) -> CameraBackend:
        return self._backend

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def state_machine(self) -> CaptureStateMachine:
        return self._state

    @property
    def state(self) -> CaptureState:
        return self._state.state

    @property
    def statistics(self) -> CaptureStatistics:
        return self._statistics

    @property
    def camera_info(self) -> Optional[CameraInfo]:
        return self._camera_info

    @property
    def skeleton_spec(self) -> Optional[SkeletonSpec]:
        return self._backend.skeleton_spec()

    @property
    def active_take(self) -> Optional[Take]:
        return self._active_take

    @property
    def is_recording(self) -> bool:
        return self.state is CaptureState.RECORDING

    @property
    def last_error(self) -> Optional[KineCaptureError]:
        return self._last_error

    @property
    def active_body_id(self) -> Optional[int]:
        return self._active_body_id

    def set_active_body_id(self, tracking_id: Optional[int]) -> None:
        """Pin the identity the UI follows and the writer records."""
        previous, self._active_body_id = self._active_body_id, tracking_id
        writer = self._writer
        # Choosing an identity for the first time is not an identity *change*;
        # only a switch away from an established one is worth recording.
        if writer is not None and previous is not None and previous != tracking_id:
            writer.record_body_id_change(writer.frames_written, previous, tracking_id)

    # --------------------------------------------------------- subject lock
    @property
    def subject_lock(self) -> SubjectLock:
        """The take-local identity of the person being recorded."""
        return self._subject_lock

    @property
    def subject_candidates(self) -> list[tuple[BodyPose, float]]:
        """Bodies near the last click, nearest first, with pixel distances."""
        return list(self._subject_candidates)

    def select_subject_at_pixel(
        self,
        x: float,
        y: float,
        *,
        radius: float = 60.0,
        packet: Optional[FramePacket] = None,
    ) -> tuple[Optional[BodyPose], bool]:
        """Pick the person under an image pixel.

        ``packet`` should be the frame the operator was actually looking at.
        Resolving the click against a newer frame would mean the person had
        already moved, and at the edge of two overlapping bodies that is enough
        to pick the wrong one.

        Returns the chosen body and whether the pick was ambiguous. When two
        people overlap the choice is *not* made here - guessing which of two
        adjacent skeletons was meant is exactly how the wrong person ends up in
        the dataset.
        """
        packet = packet or self.peek_frame()
        if packet is None or not packet.bodies:
            self._subject_candidates = []
            return None, False
        body, candidates = pick_body_at_pixel(
            packet.bodies, x, y, radius=radius, spec=self.skeleton_spec
        )
        self._subject_candidates = candidates
        if body is None:
            return None, False
        if is_ambiguous_pick(candidates):
            return None, True
        self.select_subject(body, packet=packet)
        return body, False

    def select_subject(
        self, body: BodyPose, *, method: str = "click", packet: Optional[FramePacket] = None
    ) -> str:
        """Lock onto a specific detected body."""
        packet = packet if packet is not None else self.peek_frame()
        frame_index = packet.frame_index if packet else 0
        timestamp = packet.camera_timestamp_ns if packet else 0
        subject_id = self._subject_lock.select(
            body,
            frame_index=frame_index,
            timestamp_ns=timestamp,
            method=method,
            spec=self.skeleton_spec,
        )
        self._active_body_id = int(body.tracking_id)
        return subject_id

    def confirm_subject(self, body: BodyPose) -> None:
        """Operator re-confirms the subject after an ambiguous stretch."""
        packet = self.peek_frame()
        self._subject_lock.confirm(
            body,
            frame_index=packet.frame_index if packet else 0,
            timestamp_ns=packet.camera_timestamp_ns if packet else 0,
        )
        self._active_body_id = int(body.tracking_id)

    def clear_subject(self) -> None:
        packet = self.peek_frame()
        self._subject_lock.clear(
            frame_index=packet.frame_index if packet else -1,
            timestamp_ns=packet.camera_timestamp_ns if packet else 0,
        )
        self._active_body_id = None

    # ------------------------------------------------------- raw archive
    def raw_archive_estimate(self, session: Optional[Session] = None) -> dict[str, Any]:
        """What the immutable archive will cost, and whether the disk can take it.

        Answered before recording rather than discovered during it. The figures
        come from measurements on this camera, and the shortfall is reported as
        minutes of recording rather than as bytes, because minutes is what the
        operator is deciding about.
        """
        import shutil

        profile = getattr(self._backend, "_profile", None) or (session.capture_profile if session else None)
        info = self._camera_info
        width, height = (info.resolution if info else (1280, 720)) or (1280, 720)
        fps = float(info.target_fps if info else 30.0) or 30.0
        codec = DepthCodec.FLOAT32_LOSSLESS
        archives_depth = True
        if profile is not None:
            archives_depth = profile.archives_depth
            if str(profile.depth_archive).lower().startswith("uint16"):
                codec = DepthCodec.UINT16_QUANTISED

        native = self._backend.supports_native_recording()
        estimate = estimate_bytes_per_second(
            width=int(width) or 1280,
            height=int(height) or 720,
            fps=fps,
            depth_codec=codec,
            store_color=not native,
            native_recording=native,
            native_megabytes_per_minute={"H264": 96.3, "H264_LOSSLESS": 1100.0, "LOSSLESS": 3000.0}.get(profile.native_compression if profile else "H264", 3000.0),
        )
        if not archives_depth:
            estimate["depth_mb_per_minute"] = 0.0
            estimate["total_mb_per_minute"] = (
                estimate["color_mb_per_minute"] + estimate["native_mb_per_minute"]
            )
            estimate["total_bytes_per_second"] = (
                estimate["total_mb_per_minute"] * 1e6 / 60.0
            )
        free_bytes = 0
        try:
            root = self._last_dataset_root or Path.home()
            free_bytes = shutil.disk_usage(str(root)).free
        except OSError:  # pragma: no cover - platform dependent
            free_bytes = 0
        per_minute = max(1e-6, estimate["total_mb_per_minute"] * 1e6)
        estimate["free_bytes"] = free_bytes
        estimate["free_minutes"] = free_bytes / per_minute
        estimate["depth_codec"] = codec.value
        estimate["depth_lossless"] = codec.is_lossless
        estimate["archives_depth"] = archives_depth
        estimate["color_source"] = "native_svo2" if native else "rgbd_chunks"
        estimate["evidence"] = "historical size estimate scaled by resolution/FPS; not a live throughput guarantee"
        return estimate


    def _guard_disk_space(
        self, workspace: ProjectWorkspace, session: Session
    ) -> None:
        """Refuse to start a recording the disk cannot hold.

        Solving a storage shortfall by quietly lowering the resolution, the
        frame rate or the depth archive would corrupt the dataset's provenance.
        The honest options are: record less, or free space.
        """
        estimate = self.raw_archive_estimate(session)
        required = float(session.capture_profile.min_free_disk_minutes)
        available = float(estimate.get("free_minutes", 0.0))
        if required > 0 and available < required:
            raise StorageError(
                f"Disk alanı yetersiz: ham arşiv dakikada yaklaşık "
                f"{estimate['total_mb_per_minute'] / 1000:.1f} GB yazıyor ve "
                f"boş alan yalnız {available:.1f} dakikaya yetiyor "
                f"(en az {required:.0f} dakika gerekli).",
                code="insufficient_disk_space",
                remedy=(
                    "Yer açın veya Ayarlar'dan derinlik arşivini nicemlenmiş "
                    "profile alın. Çözünürlük ve FPS sessizce düşürülmez."
                ),
                details={
                    "free_bytes": estimate.get("free_bytes"),
                    "mb_per_minute": estimate.get("total_mb_per_minute"),
                    "free_minutes": available,
                },
            )

    def check_recording_target(
        self, workspace: ProjectWorkspace
    ) -> RecordingTargetCheck:
        """Can this project's raw recordings actually be written where they go?

        Answered from the *prospective* deepest path, before the preview is
        disturbed and before a take directory exists. Read-only: nothing is
        created in the dataset to find out. The answer belongs to the project,
        not to one take, so the Capture screen can show it before the operator
        presses record rather than after.
        """
        absolute = os.path.abspath(str(workspace.longest_raw_path()))
        return RecordingTargetCheck(
            path=Path(absolute),
            length=len(absolute),
            limit=self._backend.native_recording_path_limit,
            needs_native=self._backend.supports_native_recording(),
        )

    def check_availability(self) -> AvailabilityResult:
        return self._backend.is_available()

    def add_frame_listener(self, listener: FrameListener) -> None:
        if listener not in self._frame_listeners:
            self._frame_listeners.append(listener)

    def add_error_listener(self, listener: ErrorListener) -> None:
        if listener not in self._error_listeners:
            self._error_listeners.append(listener)

    def add_take_listener(self, listener: TakeListener) -> None:
        if listener not in self._take_listeners:
            self._take_listeners.append(listener)

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> CameraInfo:
        """Connect the backend and move to READY."""
        if self.state is CaptureState.READY and self._camera_info is not None:
            return self._camera_info

        availability = self._backend.is_available()
        if not availability.available:
            error = CameraError(
                availability.message,
                code=availability.code,
                remedy=availability.remedy,
                details=dict(availability.details),
            )
            self._fail(error)
            raise error

        try:
            info = self._backend.connect()
        except KineCaptureError as exc:
            self._fail(exc)
            raise
        except Exception as exc:
            error = CameraError(
                f"Kamera açılamadı: {exc}", code="camera_open_failed"
            )
            self._fail(error)
            raise error from exc

        self._camera_info = info
        self._statistics.reset()
        self._last_error = None
        if self.state is not CaptureState.READY:
            self._state.transition(CaptureState.READY)
        logger.info("Backend bağlandı: %s (%s)", self._backend.name, info.model)
        return info

    def start_preview(self) -> None:
        """Start the acquisition thread. Idempotent while already previewing."""
        if self.state in (CaptureState.PREVIEWING, CaptureState.RECORDING):
            return
        if self.state is not CaptureState.READY:
            raise InvalidStateTransition(self.state, CaptureState.PREVIEWING)

        try:
            self._backend.start_preview()
        except KineCaptureError as exc:
            self._fail(exc)
            raise

        self._stop_event.clear()
        with self._preview_lock:
            self._preview_slot = None
        self._acquisition_times.clear()

        self._acquisition_thread = threading.Thread(
            target=self._acquisition_loop,
            name="kinecapture-acquire",
            daemon=True,
        )
        self._acquisition_thread.start()
        self._state.transition(CaptureState.PREVIEWING)
        logger.info("Önizleme başladı (%s)", self._backend.name)

    def stop_preview(self) -> None:
        """Stop acquisition (and any recording). Safe in any state."""
        if self._writer is not None:
            self.stop_recording()
        if self._acquisition_thread is None:
            return
        if self._state.can_transition(CaptureState.STOPPING):
            self._state.transition(CaptureState.STOPPING)
        self._stop_event.set()
        thread = self._acquisition_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_S)
            if thread.is_alive():
                error = CameraError(
                    "Yakalama işlemi henüz durmadı; kamera handle'ı korunuyor.",
                    code="acquisition_close_pending",
                )
                self._fail(error)
                raise error
        self._acquisition_thread = None
        worker = self._preview_worker
        if worker is not None:
            if not worker.close():
                raise CameraError("Önizleme işçisi henüz durmadı.", code="preview_close_pending")
            self._preview_worker = None

        try:
            self._backend.stop_preview()
        except Exception as exc:  # stopping must not raise at the caller
            logger.warning("Önizleme durdurulurken hata: %s", exc)
        with self._preview_lock:
            self._preview_slot = None
        if self.state is CaptureState.STOPPING:
            self._state.transition(CaptureState.READY)
        logger.info("Önizleme durduruldu (%s)", self._backend.name)

    def disconnect(self) -> None:
        """Release the device. Idempotent."""
        self.stop_preview()
        try:
            self._backend.disconnect()
        except Exception as exc:
            logger.warning("Backend kapatılırken hata: %s", exc)
        finally:
            self._camera_info = None
            if self.state is not CaptureState.DISCONNECTED:
                self._state.force(CaptureState.DISCONNECTED)
            logger.info("Backend ayrıldı (%s)", self._backend.name)

    def shutdown(self) -> None:
        """Final cleanup on exit. Idempotent and never raises.

        An in-progress recording is finalised as PARTIAL rather than abandoned:
        the frames already on disk stay readable and the take says honestly that
        it did not finish.
        """
        if self._shutdown:
            return
        try:
            if self._writer is not None:
                self.stop_recording(abort_reason="uygulama kapatıldı")
            self.disconnect()
            self._shutdown = True
        except Exception as exc:
            logger.warning("Kapanış sırasında hata: %s", exc)

    # -------------------------------------------------------------- preview
    def latest_frame(self) -> Optional[FramePacket]:
        """Take the newest preview frame, if one arrived since the last call."""
        with self._preview_lock:
            packet, self._preview_slot = self._preview_slot, None
        if packet is not None:
            with self._stats_lock:
                self._statistics.preview_frames_delivered += 1
        return packet

    def peek_frame(self) -> Optional[FramePacket]:
        """Look at the newest preview frame without consuming it."""
        with self._preview_lock:
            return self._preview_slot

    # ------------------------------------------------------------- recording
    @contextmanager
    def _capture_boundary(self):
        """No native start/stop may cut through a grab and its queue handoff."""
        # Give control operations priority over the next grab. A plain mutex
        # can starve its waiter when acquisition immediately reacquires it.
        self._boundary_done.clear()
        self._boundary_pending.set()
        if not self._capture_gate.acquire(timeout=_JOIN_TIMEOUT_S):
            self._boundary_pending.clear()
            self._boundary_done.set()
            raise StorageError(
                "Kamera işlemi bitmedi; kayıt sınırı güvenle oluşturulamadı.",
                code="capture_boundary_timeout",
            )
        try:
            yield
        finally:
            self._capture_gate.release()
            self._boundary_pending.clear()
            self._boundary_done.set()

    def start_recording(
        self, workspace: ProjectWorkspace, session: Session, **kwargs: Any
    ) -> Take:
        with self._lifecycle_guard, self._capture_boundary():
            if self._writer is not None:
                raise StorageError(
                    "Önceki kaydın kapanışı bitmedi.", code="recording_close_pending"
                )
            return self._start_recording(workspace, session, **kwargs)

    def _start_recording(
        self,
        workspace: ProjectWorkspace,
        session: Session,
        *,
        exercise: str = "",
        notes: str = "",
        protocol_task_id: Optional[str] = None,
        capture_mode: Any = None,
    ) -> Take:
        """Begin recording into a new take.

        The take directory and its metadata stub exist on disk before the first
        frame is written, so an abrupt power loss still leaves a discoverable,
        recoverable take.
        """
        if self.state is not CaptureState.PREVIEWING:
            raise InvalidStateTransition(self.state, CaptureState.RECORDING)

        self._last_dataset_root = workspace.root
        self._guard_disk_space(workspace, session)
        # Everything knowable about the destination is checked while the
        # preview is still running and before a take directory exists. A
        # refusal here costs the operator a sentence; the same refusal three
        # steps later cost them a frozen picture and a take marked failed.
        self.check_recording_target(workspace).require()

        spec = self._backend.skeleton_spec()
        extra: dict[str, Any] = {}
        if capture_mode is not None:
            extra["capture_mode"] = capture_mode

        take, paths = workspace.prepare_take(
            session,
            operator_user_id=session.operator_user_id,
            exercise=exercise,
            notes=notes,
            protocol_task_id=protocol_task_id,
            origin=self._backend.origin,
            camera_info=self._camera_info,
            skeleton_format=spec.name if spec else "",
            **extra,
        )
        effective_profile = getattr(self._backend, "_profile", session.capture_profile)
        take.capture_profile = deepcopy(effective_profile)
        workspace.save_take(take)

        # A ZED keeps its stereo images in the SVO2, so colour is archived
        # separately only when the backend has no recording of its own.
        native_supported = self._backend.supports_native_recording()
        native_started = False
        if native_supported:
            try:
                native_started = bool(
                    self._backend.start_native_recording(paths.native_recording)
                )
                if not native_started:
                    raise StorageError(
                        "Backend ham kaydı başlatmadı.", code="raw_archive_unavailable"
                    )
            except KineCaptureError as exc:
                # Native recording is part of the immutable raw source; failing
                # to start it is a real problem, so recording does not begin.
                # But nothing has been recorded either: no frame, no writer, no
                # state change. Ending in ERROR here froze the last preview
                # frame and made the camera unusable until it was reconnected,
                # which is what the operator saw on 20 September. The take is
                # still marked failed - it is the audit trail of the attempt -
                # and the preview carries on so the cause can be fixed and the
                # recording tried again without touching the camera.
                take.state = TakeState.FAILED
                take.notes = f"{take.notes}\n[Native kayıt başlatılamadı: {exc}]".strip()
                workspace.save_take(take)
                self._abort_start(exc)
                raise
        elif self._backend.origin is not DataOrigin.SYNTHETIC:
            # A real capture with no immutable source at all cannot be a
            # dataset recording. Refuse rather than produce one that can never
            # be reprocessed.
            error = StorageError(
                "Bu backend değişmez ham kayıt üretemiyor; gerçek kayıt "
                "başlatılmadı.",
                code="raw_archive_unavailable",
                remedy=(
                    "ZED backend'ini kullanın veya açıkça sentetik bir test "
                    "profiliyle çalışın."
                ),
            )
            take.state = TakeState.FAILED
            workspace.save_take(take)
            self._fail(error)
            raise error

        try:
            writer = TakeWriter(
                workspace,
                take,
                paths,
                subject_lock=self._subject_lock,
                archive_color=not native_started,
                native_recording_active=native_started,
                backend_drop_baseline=self._statistics.backend_dropped_frames,
            )
        except Exception as exc:
            if native_started:
                try:
                    self._backend.stop_native_recording()
                except Exception:  # pragma: no cover - shutdown path
                    logger.exception("Native kayıt durdurulamadı")
            error = StorageError(
                f"Ham arşiv başlatılamadı: {exc}",
                code="raw_archive_start_failed",
                remedy="Disk alanını ve yazma iznini kontrol edin.",
            )
            take.state = TakeState.FAILED
            workspace.save_take(take)
            self._fail(error)
            raise error from exc

        with self._writer_guard:
            self._writer = writer
            self._active_take = take
        if self._subject_anchor is not None:
            self.set_subject_anchor(self._subject_anchor)

        self._drain_recording_queue()
        self._writer_stop.clear()
        self._native_stop_failure = ""
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="kinecapture-writer", daemon=True
        )
        self._writer_thread.start()
        self._recording_accepting = True
        self._state.transition(CaptureState.RECORDING)
        logger.info("Kayıt başladı: %s", take.take_id)
        return take

    def stop_recording(self, *, abort_reason: str = "") -> Optional[Take]:
        with self._lifecycle_guard:
            return self._stop_recording(abort_reason=abort_reason)

    def _stop_recording(self, *, abort_reason: str = "") -> Optional[Take]:
        """Stop recording and finalise the take. Idempotent."""
        if self._writer is None:
            return None
        if self.state is CaptureState.RECORDING:
            self._state.transition(CaptureState.STOPPING)

        with self._capture_boundary():
            # Gate includes the grab and enqueue: no stale pre-start packet and
            # no packet captured after native stop can enter this recording.
            self._recording_accepting = False
            try:
                self._backend.stop_native_recording()
            except Exception as exc:
                self._native_stop_failure = f"{type(exc).__name__}: {exc}"
                logger.error("Native kayıt durdurulurken hata: %s", exc)
            self._writer_stop.set()

        # An event, not a sentinel put into a possibly full/dead queue.
        thread = self._writer_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_S)
            if thread.is_alive():
                error = StorageError(
                    "Yazıcı henüz durmadı; kayıt tamamlanmış sayılmadı. Yeniden kapatmayı deneyin.",
                    code="writer_close_pending",
                )
                self._fail(error)
                # Keep ownership: never close streams while a writer uses them.
                raise error

        with self._writer_guard:
            writer = self._writer
        if writer is None:
            return None

        remaining = self._drain_recording_queue()
        if remaining:
            writer.note_dropped(remaining)
            writer.note_raw_failure(f"Yazıcı durduğunda {remaining} kare yazılmamıştı.")
        if self._native_stop_failure:
            writer.note_raw_failure(
                f"Native kayıt düzgün durdurulamadı: {self._native_stop_failure}"
            )
        take = writer.abort(abort_reason) if abort_reason else writer.finalize()
        with self._writer_guard:
            self._writer = None
            self._writer_thread = None
        self._active_take = take

        if self.state is CaptureState.STOPPING:
            # Preview keeps running after a take ends so the operator can shoot
            # again without re-opening the camera.
            self._state.transition(
                CaptureState.PREVIEWING
                if self._acquisition_thread is not None
                and self._acquisition_thread.is_alive()
                else CaptureState.READY
            )

        for listener in list(self._take_listeners):
            try:
                listener(take)
            except Exception:
                logger.exception("Kayıt dinleyicisi hata verdi")
        return take

    def add_marker(self, label: str = "") -> Optional[dict[str, Any]]:
        """Drop an operator marker at the current recording position."""
        writer = self._writer
        if writer is None:
            return None
        return writer.record_marker(writer.frames_written, label)

    @property
    def recording_elapsed_s(self) -> float:
        writer = self._writer
        return writer.elapsed_s if writer is not None else 0.0

    @property
    def recorded_frame_count(self) -> int:
        writer = self._writer
        return writer.frames_written if writer is not None else 0

    # ----------------------------------------------------------- thread loops
    def _acquisition_loop(self) -> None:
        """Pull frames from the backend as fast as it delivers them."""
        logger.debug("Yakalama thread'i başladı.")
        while not self._stop_event.is_set():
            if self._boundary_pending.is_set():
                self._boundary_done.wait(timeout=0.05)
                continue
            try:
                with self._capture_gate:
                    if self._stop_event.is_set():
                        break
                    packet = self._backend.grab_frame()
                    if packet is not None:
                        self._note_acquisition(packet)
                        self._publish_preview(packet)
                        if self._recording_accepting:
                            self._enqueue_for_recording(packet)
            except KineCaptureError as exc:
                self._fail(exc)
                break
            except Exception as exc:
                self._fail(
                    CameraError(
                        f"Kare alınamadı: {exc}", code="frame_grab_failed"
                    )
                )
                break

            if packet is None:
                # No frame this tick. Yield rather than spin.
                time.sleep(0.002)
                continue

        logger.debug("Yakalama thread'i durdu.")

    def _writer_loop(self) -> None:
        """Drain the recording queue onto disk."""
        logger.debug("Yazıcı thread'i başladı.")
        while True:
            try:
                item = self._recording_queue.get(timeout=0.05)
            except queue.Empty:
                if self._writer_stop.is_set():
                    break
                continue
            try:
                if item is _SHUTDOWN:
                    break
                writer = self._writer
                if writer is None:
                    continue
                try:
                    writer.write_frame(item, self._active_body_id)
                    with self._stats_lock:
                        self._statistics.recorded_frames_written += 1
                except KineCaptureError as exc:
                    writer.note_raw_failure(f"Yazıcı hatası: {exc}")
                    self._fail(exc)
                    break
                except Exception as exc:
                    writer.note_raw_failure(f"Yazıcı hatası: {exc}")
                    self._fail(
                        KineCaptureError(
                            f"Kare diske yazılamadı: {exc}",
                            code="frame_write_failed",
                            remedy="Disk alanını kontrol edin.",
                        )
                    )
                    break
            finally:
                self._recording_queue.task_done()
        logger.debug("Yazıcı thread'i durdu.")

    def _enqueue_for_recording(self, packet: FramePacket) -> None:
        """Queue a frame for the writer, counting overflow as capture loss."""
        try:
            self._recording_queue.put_nowait(packet)
        except queue.Full:
            writer = self._writer
            if writer is not None:
                writer.note_dropped()
            with self._stats_lock:
                self._statistics.recording_frames_dropped += 1
            logger.error(
                "Kayıt kuyruğu doldu; kare %d diske yazılamadı.", packet.frame_index
            )

    def _publish_preview(self, packet: FramePacket) -> None:
        """Latest-wins preview slot. Overwriting is a preview drop, not data loss."""
        if packet.color_frame is None:
            return
        profile = getattr(self._backend, "_profile", None)
        if profile is not None and not profile.preview_enabled:
            return
        if self._preview_worker is None:
            self._preview_worker = LatestWorker(self._process_preview, fps=profile.preview_fps if profile else 15.0)
        self._preview_worker.offer(packet)

    def _process_preview(self, packet: FramePacket):
        if self._preview_processor is not None:
            self.pose_preview = self._preview_processor(packet)
        with self._preview_lock:
            if self._preview_slot is not None:
                with self._stats_lock:
                    self._statistics.preview_frames_dropped += 1
            self._preview_slot = packet
        for listener in list(self._frame_listeners):
            try:
                listener(packet)
            except Exception:
                logger.exception("Kare dinleyicisi hata verdi")
        return packet

    def set_subject_anchor(self, anchor: dict) -> None:
        """Store an operator selection on the displayed source image."""
        with self._lifecycle_guard:
            self._set_subject_anchor(anchor)

    def _set_subject_anchor(self, anchor: dict) -> None:
        from kinecapture.core.jsonio import write_json
        if not all(k in anchor for k in ("camera_timestamp_ns", "source_resolution", "point_xy", "bbox_xyxy")):
            raise ValueError("Subject anchor lacks source timestamp/image geometry")
        self._subject_anchor = deepcopy(anchor)
        writer = self._writer
        if writer is not None:
            writer.subject_anchors.append(deepcopy(anchor))
            write_json(writer.paths.raw_dir / "subject_anchors.json", writer.subject_anchors, overwrite=True)

    def _note_acquisition(self, packet: FramePacket) -> None:
        if packet.recording_status is not None:
            self.last_recording_status = packet.recording_status
        now = time.perf_counter()
        self._acquisition_times.append(now)
        # Keep roughly the last two seconds so the number reacts to a stall.
        if len(self._acquisition_times) > 90:
            del self._acquisition_times[:-90]
        with self._stats_lock:
            stats = self._statistics
            stats.frames_acquired += 1
            stats.backend_dropped_frames = max(
                stats.backend_dropped_frames, int(packet.backend_dropped_frames)
            )
            if len(self._acquisition_times) >= 2:
                span = self._acquisition_times[-1] - self._acquisition_times[0]
                if span > 0:
                    stats.acquisition_fps = (len(self._acquisition_times) - 1) / span
                stats.last_latency_ms = (
                    self._acquisition_times[-1] - self._acquisition_times[-2]
                ) * 1000.0

    def _drain_recording_queue(self) -> int:
        count = 0
        while True:
            try:
                self._recording_queue.get_nowait()
            except queue.Empty:
                return count
            else:
                count += 1
                self._recording_queue.task_done()

    # ------------------------------------------------------------------ error
    def _abort_start(self, error: KineCaptureError) -> None:
        """A recording that never began. Report it; keep the preview alive.

        Deliberately not :meth:`_fail`: that sets the stop event and moves to
        ``ERROR``, from which the only way out is ``DISCONNECTED``. Nothing
        about a refused ``enable_recording`` requires the camera to be torn
        down, and tearing it down is what left a dead picture on screen.
        """
        logger.error("Kayıt başlatılamadı [%s]: %s", error.code, error.message)
        self._last_error = error
        self._recording_start_failures += 1
        for listener in list(self._error_listeners):
            try:
                listener(error)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Hata dinleyicisi hata verdi")

    @property
    def recording_start_failures(self) -> int:
        """How many starts were refused since the service was created."""
        return self._recording_start_failures

    def _fail(self, error: KineCaptureError) -> None:
        """Move to ERROR and notify listeners with a structured error."""
        logger.error("Yakalama hatası [%s]: %s", error.code, error.message)
        self._last_error = error
        if self._writer is not None:
            self._writer.note_raw_failure(f"{error.code}: {error.message}")
        self._stop_event.set()
        if self._state.can_transition(CaptureState.ERROR):
            self._state.transition(CaptureState.ERROR)
        for listener in list(self._error_listeners):
            try:
                listener(error)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Hata dinleyicisi hata verdi")


__all__ = [
    "DEFAULT_RECORDING_QUEUE_SIZE",
    "CaptureService",
]
