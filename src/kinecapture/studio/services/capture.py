"""The Studio's view of a live capture: connect, preview, record, stop.

Wraps :class:`~kinecapture.capture.service.CaptureService` behind value objects
so a screen never holds a backend, a writer or a thread.

Two distinctions this file exists to keep visible, because collapsing either
one would make the interface lie:

* **A dropped preview frame is not a dropped recorded frame.** The first is the
  interface keeping up; the second is data that will never exist. They are
  counted separately and reported separately.
* **The light preview pose is not the skeleton.** It is a CPU 2-D estimate for
  checking framing, with no metric depth and no participant identity. The
  metric skeleton is computed offline, afterwards, from the raw recording.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture.core.config import AppConfig
from kinecapture.core.diagnostics import estimate_recording_minutes
from kinecapture.core.errors import KineCaptureError
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import BackendKind
from kinecapture.domain.project import CaptureProfile, Session, Take

logger = logging.getLogger(__name__)

#: What the preview overlay is, said once so no screen has to phrase it itself.
PREVIEW_POSE_DISCLAIMER = (
    "Bu kaplama kadrajı kontrol etmek içindir: CPU'da çalışan hafif bir 2B "
    "tahmindir. Metrik iskelet değildir ve katılımcı kimliği taşımaz; gerçek "
    "iskelet kayıttan sonra ham veriden hesaplanır."
)


@dataclass(frozen=True)
class CaptureMetrics:
    """One reading of the capture path. Refreshed a few times a second."""

    state: str = "disconnected"
    acquisition_fps: float = 0.0
    preview_fps: float = 0.0
    frames_acquired: int = 0
    #: Frames that were written. The number that matters.
    recorded_frames: int = 0
    #: Frames that should have been written and were not. Never merged with
    #: the preview count.
    recording_dropped: int = 0
    #: Preview frames skipped to keep the interface responsive. Not data loss.
    preview_dropped: int = 0
    backend_dropped: int = 0
    elapsed_s: float = 0.0
    bytes_written: int = 0
    free_bytes: int = 0
    recording: bool = False
    connected: bool = False

    @property
    def has_recording_loss(self) -> bool:
        return self.recording_dropped > 0 or self.backend_dropped > 0

    @property
    def free_minutes(self) -> float:
        return estimate_recording_minutes(self.free_bytes) if self.free_bytes else 0.0

    @property
    def elapsed_text(self) -> str:
        minutes, seconds = divmod(int(self.elapsed_s), 60)
        return f"{minutes:02d}:{seconds:02d}"


@dataclass(frozen=True)
class SubjectAnchor:
    """An operator's choice of person, bound to the frame they were looking at.

    Carries the camera timestamp and the source resolution, not a screen
    coordinate: the offline pass has to find the same person in the same frame,
    and a point in display pixels means nothing to it.
    """

    camera_timestamp_ns: int
    source_position: Optional[int]
    point_xy: tuple[float, float]
    bbox_xyxy: tuple[float, float, float, float]
    source_resolution: tuple[int, int]

    @classmethod
    def from_dict(cls, payload: dict) -> "SubjectAnchor":
        box = list(payload["bbox_xyxy"])
        return cls(
            camera_timestamp_ns=int(payload["camera_timestamp_ns"]),
            source_position=payload.get("source_position"),
            point_xy=(float(payload["point_xy"][0]), float(payload["point_xy"][1])),
            bbox_xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
            source_resolution=tuple(int(v) for v in payload["source_resolution"]),  # type: ignore[arg-type]
        )


@dataclass
class CaptureService:
    """Opens the camera, runs the preview, records, and reports honestly."""

    config: AppConfig
    _service: Optional[Any] = field(default=None, repr=False)
    _pose_factory: Optional[Callable[[], Any]] = field(default=None, repr=False)
    _pose_error: str = ""
    last_take: Optional[Take] = None

    # ------------------------------------------------------------- lifecycle
    @property
    def service(self) -> Optional[Any]:
        return self._service

    @property
    def is_connected(self) -> bool:
        return self._service is not None and self._service.camera_info is not None

    @property
    def is_recording(self) -> bool:
        return bool(self._service and self._service.is_recording)

    @property
    def pose_unavailable_reason(self) -> str:
        return self._pose_error

    def profile(self) -> CaptureProfile:
        return self.config.capture

    def connect(self, *, backend: Optional[str] = None) -> Any:
        """Open the camera and start the preview. Returns the camera info."""
        from kinecapture.capture.service import CaptureService as LiveCaptureService

        if self._service is not None:
            self.disconnect()
        kind = BackendKind(backend or getattr(self.config.backend, "value", self.config.backend))
        camera = self._build_backend(kind)
        processor = self._build_pose_processor()
        self._service = LiveCaptureService(camera, preview_processor=processor)
        info = self._service.connect()
        self._service.start_preview()
        return info

    def _build_backend(self, kind: BackendKind):  # noqa: ANN202 - CameraBackend
        profile = self.profile()
        if kind is BackendKind.MOCK:
            from kinecapture.camera.mock import MockCameraBackend

            mock = self.config.mock
            return MockCameraBackend(
                width=640,
                height=360,
                fps=profile.fps,
                seed=getattr(mock, "seed", 7),
                num_bodies=getattr(mock, "num_bodies", 1),
                profile=profile,
                # Paced, because this is standing in for a camera. Free-running
                # it produces frames several times faster than any real device
                # and overflows the writer queue, which then looks like a
                # recording fault in an interface that is working perfectly.
                real_time=True,
            )
        from kinecapture.camera.zed import ZedCameraBackend

        return ZedCameraBackend(profile)

    def _build_pose_processor(self) -> Optional[Callable]:
        """The light preview pose, if its models are present.

        Missing models are not an error: capture is the thing that matters and
        it does not need them. The screen says the overlay is unavailable and
        why, instead of failing to open the camera.
        """
        if not self.config.extra.get("preview_pose_enabled", True):
            self._pose_error = "Ayarlardan kapatıldı."
            return None
        if self._pose_factory is not None:
            try:
                return self._pose_factory()
            except Exception as exc:  # noqa: BLE001 - see docstring
                self._pose_error = str(exc)
                return None
        try:
            from kinecapture.preview.pose import CpuPosePreview

            directory = Path(
                self.config.extra.get(
                    "preview_model_dir", Path.home() / ".cache" / "kinecapture" / "models"
                )
            )
            processor = CpuPosePreview(directory)
        except Exception as exc:  # noqa: BLE001 - see docstring
            self._pose_error = (
                "Hafif poz modelleri bulunamadı. Kayıt bundan etkilenmez; "
                "kaplama gösterilmez."
            )
            logger.info("Hafif poz önizlemesi kullanılamıyor: %s", exc)
            return None
        self._pose_error = ""
        return processor

    def disconnect(self) -> None:
        if self._service is None:
            return
        try:
            self._service.shutdown()
        except KineCaptureError:
            logger.exception("Kamera kapatılırken hata")
        finally:
            self._service = None

    # --------------------------------------------------------------- preview
    def latest_frame(self):  # noqa: ANN201 - FramePacket
        return self._service.latest_frame() if self._service else None

    def pose_preview(self):  # noqa: ANN201 - PosePreview
        return getattr(self._service, "pose_preview", None) if self._service else None

    # -------------------------------------------------------------- subject
    def anchor_from_click(self, x: float, y: float) -> SubjectAnchor:
        """Turn a click on the *displayed* frame into a stored anchor.

        Resolved against the preview that was on screen, never a newly grabbed
        one: by the time a new frame arrives the person has moved, and at the
        edge of two overlapping people that is enough to pick the wrong one.
        """
        preview = self.pose_preview()
        if preview is None:
            raise ValueError(
                "Kişi seçimi için hafif poz kaplaması gerekli; şu an kullanılamıyor."
            )
        payload = preview.anchor(x, y)
        if self._service is not None:
            self._service.set_subject_anchor(payload)
        return SubjectAnchor.from_dict(payload)

    def clear_subject(self) -> None:
        if self._service is not None:
            self._service._subject_anchor = None  # noqa: SLF001 - no public clear yet

    @property
    def subject_anchor(self) -> Optional[SubjectAnchor]:
        raw = getattr(self._service, "_subject_anchor", None) if self._service else None
        return SubjectAnchor.from_dict(raw) if raw else None

    # ------------------------------------------------------------- recording
    def start_recording(
        self, workspace: ProjectWorkspace, session: Session, **kwargs: Any
    ) -> Take:
        if self._service is None:
            raise KineCaptureError("Önce kameraya bağlanın.", code="camera_not_connected")
        take = self._service.start_recording(workspace, session, **kwargs)
        self.last_take = take
        return take

    def stop_recording(self) -> Optional[Take]:
        if self._service is None:
            return None
        take = self._service.stop_recording()
        if take is not None:
            self.last_take = take
        return take

    def add_marker(self, label: str = "operator") -> Optional[dict]:
        return self._service.add_marker(label) if self._service else None

    # --------------------------------------------------------------- metrics
    def metrics(self) -> CaptureMetrics:
        service = self._service
        if service is None:
            return CaptureMetrics()
        stats = service.statistics
        free = self._free_bytes()
        return CaptureMetrics(
            state=service.state.value,
            acquisition_fps=float(stats.acquisition_fps),
            preview_fps=float(stats.preview_fps),
            frames_acquired=int(stats.frames_acquired),
            recorded_frames=int(stats.recorded_frames_written),
            recording_dropped=int(stats.recording_frames_dropped),
            preview_dropped=int(stats.preview_frames_dropped),
            backend_dropped=int(stats.backend_dropped_frames),
            elapsed_s=float(service.recording_elapsed_s),
            free_bytes=free,
            recording=bool(service.is_recording),
            connected=service.camera_info is not None,
        )

    def _free_bytes(self) -> int:
        import shutil

        root = Path(self.config.dataset_root)
        for candidate in (root, *root.parents):
            try:
                return int(shutil.disk_usage(str(candidate)).free)
            except OSError:
                continue
        return 0


__all__ = [
    "PREVIEW_POSE_DISCLAIMER",
    "CaptureMetrics",
    "CaptureService",
    "SubjectAnchor",
]
