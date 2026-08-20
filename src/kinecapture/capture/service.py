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

import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture.camera.base import AvailabilityResult, CameraBackend
from kinecapture.core.errors import CameraError, KineCaptureError
from kinecapture.core.logging import get_logger
from kinecapture.core.state_machine import CaptureStateMachine, InvalidStateTransition
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import CaptureState, TakeState
from kinecapture.domain.models import CameraInfo, CaptureStatistics, FramePacket
from kinecapture.domain.project import Session, Take
from kinecapture.recording.take_writer import TakeWriter
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


class CaptureService:
    """Coordinates one camera backend, its threads, and the active recording."""

    def __init__(
        self,
        backend: CameraBackend,
        *,
        state_machine: Optional[CaptureStateMachine] = None,
        recording_queue_size: int = DEFAULT_RECORDING_QUEUE_SIZE,
    ) -> None:
        if recording_queue_size < 1:
            raise ValueError("recording_queue_size must be >= 1")
        self._backend = backend
        self._state = state_machine or CaptureStateMachine()
        self._statistics = CaptureStatistics()
        self._stats_lock = threading.Lock()

        self._preview_slot: Optional[FramePacket] = None
        self._preview_lock = threading.Lock()

        self._recording_queue: "queue.Queue[Any]" = queue.Queue(
            maxsize=recording_queue_size
        )
        self._acquisition_thread: Optional[threading.Thread] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._writer: Optional[TakeWriter] = None
        self._writer_guard = threading.Lock()
        self._active_take: Optional[Take] = None
        self._active_body_id: Optional[int] = None

        self._frame_listeners: list[FrameListener] = []
        self._error_listeners: list[ErrorListener] = []
        self._take_listeners: list[TakeListener] = []

        self._camera_info: Optional[CameraInfo] = None
        self._shutdown = False
        self._last_error: Optional[KineCaptureError] = None
        self._acquisition_times: list[float] = []

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
        if self.state not in (CaptureState.PREVIEWING, CaptureState.RECORDING):
            return
        if self.is_recording:
            self.stop_recording()

        self._state.transition(CaptureState.STOPPING)
        self._stop_event.set()
        thread, self._acquisition_thread = self._acquisition_thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_S)
            if thread.is_alive():
                logger.error("Yakalama thread'i zamanında durmadı.")

        try:
            self._backend.stop_preview()
        except Exception as exc:  # stopping must not raise at the caller
            logger.warning("Önizleme durdurulurken hata: %s", exc)
        with self._preview_lock:
            self._preview_slot = None
        self._state.transition(CaptureState.READY)
        logger.info("Önizleme durduruldu (%s)", self._backend.name)

    def disconnect(self) -> None:
        """Release the device. Idempotent."""
        if self.state in (CaptureState.PREVIEWING, CaptureState.RECORDING):
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
        self._shutdown = True
        try:
            if self.is_recording:
                self.stop_recording(abort_reason="uygulama kapatıldı")
            self.disconnect()
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
    def start_recording(
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

        spec = self._backend.skeleton_spec()
        extra: dict[str, Any] = {}
        if capture_mode is not None:
            extra["capture_mode"] = capture_mode

        take, paths = workspace.prepare_take(
            session,
            exercise=exercise,
            notes=notes,
            protocol_task_id=protocol_task_id,
            origin=self._backend.origin,
            camera_info=self._camera_info,
            skeleton_format=spec.name if spec else "",
            **extra,
        )

        writer = TakeWriter(workspace, take, paths)

        if (
            take.capture_profile.store_native_recording
            and self._backend.supports_native_recording()
        ):
            try:
                self._backend.start_native_recording(paths.native_recording)
            except KineCaptureError as exc:
                # Native recording is the immutable raw copy; failing to start it
                # is a real problem, so recording does not begin at all.
                writer.close_streams()
                take.state = TakeState.FAILED
                take.notes = f"{take.notes}\n[Native kayıt başlatılamadı: {exc}]".strip()
                workspace.save_take(take)
                self._fail(exc)
                raise

        with self._writer_guard:
            self._writer = writer
            self._active_take = take

        self._drain_recording_queue()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="kinecapture-writer", daemon=True
        )
        self._writer_thread.start()
        self._state.transition(CaptureState.RECORDING)
        logger.info("Kayıt başladı: %s", take.take_id)
        return take

    def stop_recording(self, *, abort_reason: str = "") -> Optional[Take]:
        """Stop recording and finalise the take. Idempotent."""
        if self._writer is None:
            return None
        if self.state is CaptureState.RECORDING:
            self._state.transition(CaptureState.STOPPING)

        try:
            self._backend.stop_native_recording()
        except Exception as exc:
            logger.warning("Native kayıt durdurulurken hata: %s", exc)

        # Tell the writer thread to finish what is already queued, then stop.
        self._recording_queue.put(_SHUTDOWN)
        thread, self._writer_thread = self._writer_thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_S)
            if thread.is_alive():
                logger.error("Yazıcı thread'i zamanında durmadı.")

        with self._writer_guard:
            writer, self._writer = self._writer, None
        if writer is None:
            return None

        take = writer.abort(abort_reason) if abort_reason else writer.finalize()
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
            try:
                packet = self._backend.grab_frame()
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

            self._note_acquisition(packet)
            self._publish_preview(packet)

            if self._writer is not None:
                self._enqueue_for_recording(packet)

            for listener in list(self._frame_listeners):
                try:
                    listener(packet)
                except Exception:
                    logger.exception("Kare dinleyicisi hata verdi")
        logger.debug("Yakalama thread'i durdu.")

    def _writer_loop(self) -> None:
        """Drain the recording queue onto disk."""
        logger.debug("Yazıcı thread'i başladı.")
        while True:
            item = self._recording_queue.get()
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
                    self._fail(exc)
                    break
                except Exception as exc:
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
        with self._preview_lock:
            if self._preview_slot is not None:
                with self._stats_lock:
                    self._statistics.preview_frames_dropped += 1
            self._preview_slot = packet

    def _note_acquisition(self, packet: FramePacket) -> None:
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

    def _drain_recording_queue(self) -> None:
        while True:
            try:
                self._recording_queue.get_nowait()
            except queue.Empty:
                return
            else:
                self._recording_queue.task_done()

    # ------------------------------------------------------------------ error
    def _fail(self, error: KineCaptureError) -> None:
        """Move to ERROR and notify listeners with a structured error."""
        logger.error("Yakalama hatası [%s]: %s", error.code, error.message)
        self._last_error = error
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
