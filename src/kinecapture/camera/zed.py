"""Stereolabs ZED camera backend.

Verified against the SDK installed on the development machine
(ZED SDK 5.4.1 / ``pyzed`` 5.4 / CPython 3.11, ZED 2i serial 31844341). Every
SDK call below was exercised against that hardware before being written; no API
here is reproduced from memory.

Two rules shape this module:

* **``pyzed`` is never imported at module level.** It is imported inside
  :func:`_import_sl`, so the whole application - GUI, tests, export - runs on a
  machine with no ZED SDK at all.
* **Nothing is faked.** When a capability is missing the backend says so through
  :meth:`capabilities` and :meth:`is_available`; it never fabricates a frame, a
  body or a depth map to make the UI look complete.

First-run note: the SDK optimises its depth and body-tracking neural models the
first time a given configuration is opened, which takes minutes and is a
one-time cost per model. That is surfaced as a warning by the diagnostics rather
than looking like a hang.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture.camera.base import (
    AvailabilityResult,
    BackendCapabilities,
    CameraBackend,
)
from kinecapture.core.errors import CameraError, CameraNotConnectedError
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import ensure_dir, path_exists
from kinecapture.domain.arrays import owned_snapshot
from kinecapture.domain.enums import (
    BodyActionState,
    CaptureStatus,
    DataOrigin,
    HealthLevel,
    TrackingState,
)
from kinecapture.domain.models import BodyPose, CameraInfo, FramePacket
from kinecapture.domain.project import CaptureProfile
from kinecapture.visualization.skeleton_spec import (
    SkeletonSpec,
    spec_for_zed_body_format,
)

logger = get_logger(__name__)

#: Cached import result so a missing SDK is diagnosed once, not per call.
_sl_module: Any = None
_sl_import_error: Optional[str] = None
_sl_lock = threading.Lock()


def _import_sl() -> Any:
    """Import ``pyzed.sl`` lazily. Returns ``None`` when unavailable."""
    global _sl_module, _sl_import_error
    with _sl_lock:
        if _sl_module is not None or _sl_import_error is not None:
            return _sl_module
        try:
            import pyzed.sl as sl  # noqa: PLC0415 - deliberate lazy import
        except Exception as exc:  # ImportError, or a DLL load failure on Windows
            _sl_import_error = f"{type(exc).__name__}: {exc}"
            logger.info("pyzed kullanılamıyor: %s", _sl_import_error)
            return None
        _sl_module = sl
        return _sl_module


def pyzed_import_error() -> Optional[str]:
    """The reason ``pyzed`` could not be imported, or ``None``."""
    _import_sl()
    return _sl_import_error


def is_pyzed_available() -> bool:
    return _import_sl() is not None


def sdk_version() -> Optional[str]:
    sl = _import_sl()
    if sl is None:
        return None
    try:
        return str(sl.Camera.get_sdk_version())
    except Exception:  # pragma: no cover - depends on a broken SDK install
        return None


def list_devices() -> list[dict[str, Any]]:
    """Enumerate attached ZED cameras. Never raises; returns ``[]`` on failure."""
    sl = _import_sl()
    if sl is None:
        return []
    try:
        devices = sl.Camera.get_device_list()
    except Exception as exc:  # pragma: no cover - driver dependent
        logger.warning("ZED cihaz listesi alınamadı: %s", exc)
        return []
    result: list[dict[str, Any]] = []
    for device in devices:
        result.append(
            {
                "serial_number": str(getattr(device, "serial_number", "")),
                "model": str(getattr(device, "camera_model", "")),
                "state": str(getattr(device, "camera_state", "")),
                "id": int(getattr(device, "id", -1)),
            }
        )
    return result


#: Our :class:`TrackingState` is defined independently of the SDK enum; this is
#: the explicit mapping between the two, not an assumed identity.
_TRACKING_STATE_NAMES = {
    "OK": TrackingState.OK,
    "SEARCHING": TrackingState.SEARCHING,
    "OFF": TrackingState.OFF,
    "TERMINATE": TrackingState.TERMINATE,
}


class ZedCameraBackend(CameraBackend):
    """Live ZED capture: colour, depth, body tracking and native SVO2 recording."""

    name = "zed"
    origin = DataOrigin.REAL

    def __init__(self, profile: Optional[CaptureProfile] = None) -> None:
        self._profile = profile or CaptureProfile()
        self._camera: Any = None
        self._info: Optional[CameraInfo] = None
        self._spec: Optional[SkeletonSpec] = None
        self._previewing = False
        self._frame_index = 0
        self._last_rgb_time = float("-inf")
        self._recording = False
        self._recording_path: Optional[Path] = None
        self._body_tracking_enabled = False
        self._depth_enabled = False
        self._open_lock = threading.RLock()

        # SDK scratch buffers, allocated once per connection.
        self._mat_color: Any = None
        self._mat_depth: Any = None
        self._bodies: Any = None
        self._runtime: Any = None
        self._body_runtime: Any = None

    # ---------------------------------------------------------------- probe
    def is_available(self) -> AvailabilityResult:
        sl = _import_sl()
        if sl is None:
            return AvailabilityResult(
                available=False,
                code="pyzed_missing",
                message="ZED Python modülü (pyzed) bu ortamda bulunamadı.",
                remedy=(
                    "ZED SDK kurulumundaki get_python_api.py betiğini KineSynth "
                    "environment'ı içinde çalıştırın."
                ),
                level=HealthLevel.BLOCKED,
                details={"import_error": _sl_import_error},
            )
        devices = list_devices()
        if not devices:
            return AvailabilityResult(
                available=False,
                code="no_camera_detected",
                message="ZED SDK yüklü fakat bağlı kamera bulunamadı.",
                remedy="Kamerayı USB 3.0 portuna takıp uygulamayı yenileyin.",
                level=HealthLevel.BLOCKED,
                details={"sdk_version": sdk_version()},
            )
        available = [d for d in devices if d["state"].upper().endswith("AVAILABLE")]
        if not available:
            return AvailabilityResult(
                available=False,
                code="camera_busy",
                message="ZED kamera bulundu fakat başka bir uygulama tarafından kullanılıyor.",
                remedy="Kamerayı kullanan diğer uygulamaları kapatın.",
                level=HealthLevel.BLOCKED,
                details={"devices": devices},
            )
        first = available[0]
        return AvailabilityResult.ok(
            f"ZED kamera hazır: {first['model']} (S/N {first['serial_number']}).",
            details={
                "sdk_version": sdk_version(),
                "devices": devices,
                "selected_serial": first["serial_number"],
            },
        )

    def capabilities(self) -> BackendCapabilities:
        if _import_sl() is None:
            return BackendCapabilities(
                color=False,
                depth=False,
                body_tracking=False,
                native_recording=False,
                multi_body=False,
                device_enumeration=False,
            )
        return BackendCapabilities(
            color=True,
            depth=True,
            body_tracking=True,
            native_recording=True,
            multi_body=True,
            device_enumeration=True,
        )

    def diagnostics(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": self.name,
            "pyzed_available": is_pyzed_available(),
            "pyzed_import_error": _sl_import_error,
            "sdk_version": sdk_version(),
            "devices": list_devices(),
            "connected": self._camera is not None,
            "requested_resolution": self._profile.resolution,
            "requested_fps": self._profile.fps,
            "requested_depth_mode": self._profile.depth_mode,
            "requested_body_format": self._profile.body_format,
        }
        if self._camera is not None:
            try:
                info["sdk_current_fps"] = round(float(self._camera.get_current_fps()), 2)
                info["sdk_frame_dropped_count"] = int(
                    self._camera.get_frame_dropped_count()
                )
            except Exception:  # pragma: no cover - device state dependent
                pass
        return info

    # ------------------------------------------------------------ lifecycle
    def _enum(self, sl: Any, enum_name: str, member: str, field: str) -> Any:
        """Resolve ``sl.<enum_name>.<member>`` with an actionable error."""
        enum_cls = getattr(sl, enum_name, None)
        value = getattr(enum_cls, member, None) if enum_cls is not None else None
        if value is None:
            valid = (
                ", ".join(n for n in dir(enum_cls) if not n.startswith("_"))
                if enum_cls is not None
                else "-"
            )
            raise CameraError(
                f"Bu ZED SDK sürümü '{member}' değerini desteklemiyor ({field}).",
                code="unsupported_sdk_value",
                remedy=f"Geçerli değerler: {valid}",
                details={"enum": enum_name, "member": member},
            )
        return value

    def connect(self) -> CameraInfo:
        """Open the camera with the configured profile and report what it gave."""
        with self._open_lock:
            if self._camera is not None and self._info is not None:
                return self._info

            sl = _import_sl()
            if sl is None:
                raise CameraError(
                    "ZED Python modülü (pyzed) bulunamadı.",
                    code="pyzed_missing",
                    remedy="ZED SDK'nın get_python_api.py betiğini çalıştırın.",
                )

            profile = self._profile
            init = sl.InitParameters()
            init.camera_resolution = self._enum(
                sl, "RESOLUTION", profile.resolution, "resolution"
            )
            init.camera_fps = int(profile.fps)
            init.depth_mode = (
                self._enum(sl, "DEPTH_MODE", profile.depth_mode, "depth_mode")
                if profile.computes_depth
                else self._enum(sl, "DEPTH_MODE", "NONE", "depth_mode")
            )
            init.coordinate_units = self._enum(
                sl, "UNIT", profile.length_unit, "length_unit"
            )
            init.coordinate_system = self._enum(
                sl, "COORDINATE_SYSTEM", profile.coordinate_system, "coordinate_system"
            )
            init.sdk_verbose = 0

            camera = sl.Camera()
            started = time.perf_counter()
            status = camera.open(init)
            if status != sl.ERROR_CODE.SUCCESS:
                camera.close()
                raise CameraError(
                    f"ZED kamera açılamadı: {status}",
                    code=f"zed_open_{str(status).lower()}",
                    remedy=(
                        "Kablo bağlantısını, USB 3.0 portunu ve kamerayı kullanan "
                        "diğer uygulamaları kontrol edin."
                    ),
                    details={"error_code": str(status)},
                )
            logger.info("ZED kamera açıldı (%.1f s)", time.perf_counter() - started)

            try:
                self._configure_modules(sl, camera, profile)
                self._info = self._build_camera_info(sl, camera, profile)
            except BaseException:
                camera.close()
                raise

            self._camera = camera
            self._depth_enabled = profile.retrieves_depth
            self._frame_index = 0
            self._mat_color = sl.Mat()
            self._mat_depth = sl.Mat()
            self._bodies = sl.Bodies()
            self._runtime = sl.RuntimeParameters()
            self._runtime.enable_depth = profile.computes_depth
            return self._info

    def _configure_modules(self, sl: Any, camera: Any, profile: CaptureProfile) -> None:
        """Enable positional tracking and body tracking, if requested."""
        self._body_tracking_enabled = False
        self._spec = None
        if not profile.computes_body:
            return

        # Body tracking requires positional tracking; enabling it here rather
        # than relying on an implicit default keeps the failure attributable.
        status = camera.enable_positional_tracking(sl.PositionalTrackingParameters())
        if status != sl.ERROR_CODE.SUCCESS:
            raise CameraError(
                f"Konumsal takip başlatılamadı: {status}",
                code="zed_positional_tracking_failed",
                remedy="Kamerayı sabit tutup yeniden deneyin.",
                details={"error_code": str(status)},
            )

        params = sl.BodyTrackingParameters()
        params.enable_tracking = True
        params.enable_body_fitting = bool(profile.enable_body_fitting)
        params.detection_model = self._enum(
            sl, "BODY_TRACKING_MODEL", profile.body_tracking_model, "body_tracking_model"
        )
        params.body_format = self._enum(
            sl, "BODY_FORMAT", profile.body_format, "body_format"
        )

        started = time.perf_counter()
        status = camera.enable_body_tracking(params)
        if status != sl.ERROR_CODE.SUCCESS:
            camera.disable_positional_tracking()
            raise CameraError(
                f"Vücut takibi başlatılamadı: {status}",
                code="zed_body_tracking_failed",
                remedy=(
                    "GPU belleğini ve NVIDIA sürücüsünü kontrol edin. İlk çalıştırmada "
                    "SDK sinir ağı modellerini optimize eder ve bu birkaç dakika sürer."
                ),
                details={"error_code": str(status)},
            )
        logger.info("Vücut takibi etkin (%.1f s)", time.perf_counter() - started)

        self._body_runtime = sl.BodyTrackingRuntimeParameters()
        self._body_runtime.detection_confidence_threshold = int(
            profile.detection_confidence
        )
        self._spec = spec_for_zed_body_format(profile.body_format)
        self._body_tracking_enabled = True

    @staticmethod
    def _left_camera_calibration(configuration: Any) -> Optional[dict[str, Any]]:
        """Intrinsics of the left camera, or ``None`` when unavailable.

        2D keypoints are pixel coordinates and are meaningless without the
        image size and intrinsics they were produced against, so this is read
        once per connection and stored in the take's provenance. Every value is
        read from the device; nothing is derived or assumed.
        """
        calibration = getattr(configuration, "calibration_parameters", None)
        left = getattr(calibration, "left_cam", None) if calibration else None
        if left is None:
            return None
        try:
            size = left.image_size
            block: dict[str, Any] = {
                "camera": "left",
                "fx": float(left.fx),
                "fy": float(left.fy),
                "cx": float(left.cx),
                "cy": float(left.cy),
                "image_width": int(size.width),
                "image_height": int(size.height),
                "distortion": [float(v) for v in np.ravel(left.disto).tolist()],
                "distortion_model": str(
                    getattr(left, "lens_distortion_model", "unspecified")
                ),
                "note": (
                    "2D eklem noktaları bu görüntü boyutu ve iç parametrelerle "
                    "birlikte anlamlıdır."
                ),
            }
        except Exception as exc:  # pragma: no cover - depends on device state
            logger.warning("Kamera kalibrasyonu okunamadı: %s", exc)
            return None
        return block

    def _build_camera_info(
        self, sl: Any, camera: Any, profile: CaptureProfile
    ) -> CameraInfo:
        """Describe the device from what it reported, not from the request."""
        information = camera.get_camera_information()
        configuration = information.camera_configuration
        resolution = (
            int(configuration.resolution.width),
            int(configuration.resolution.height),
        )
        calibration = self._left_camera_calibration(configuration)
        return CameraInfo(
            backend=self.name,
            model=str(information.camera_model),
            origin=DataOrigin.REAL,
            serial_number=str(information.serial_number),
            firmware_version=str(getattr(configuration, "firmware_version", "")),
            sdk_version=sdk_version(),
            resolution=resolution,
            target_fps=float(configuration.fps),
            coordinate_system=profile.coordinate_system.lower(),
            length_unit=profile.length_unit.lower(),
            body_format=self._spec.name if self._spec else None,
            depth_available=profile.retrieves_depth,
            body_tracking_available=self._body_tracking_enabled,
            extra={
                "requested_resolution": profile.resolution,
                "requested_fps": profile.fps,
                "depth_mode": profile.depth_mode if profile.computes_depth else "NONE",
                "depth_computed": profile.computes_depth,
                "depth_retrieved": profile.retrieves_depth,
                "frame_index_semantics": "successful_grab_ordinal",
                "body_tracking_model": profile.body_tracking_model,
                "body_fitting": profile.enable_body_fitting,
                "input_type": str(information.input_type),
                "left_camera_calibration": calibration,
                "quaternion_order": "xyzw",
            },
        )

    def start_preview(self) -> None:
        if self._camera is None:
            raise CameraNotConnectedError(
                "ZED kamera önizleme öncesi bağlanmalıdır.",
                remedy="Önce Bağlan düğmesini kullanın.",
            )
        self._previewing = True

    def stop_preview(self) -> None:
        self._previewing = False

    def disconnect(self) -> None:
        """Release the device. Idempotent and safe during shutdown."""
        with self._open_lock:
            self._previewing = False
            camera = self._camera
            if camera is None:
                self._info = None
                return
            for action in (
                self.stop_native_recording,
                lambda: camera.disable_body_tracking()
                if self._body_tracking_enabled
                else None,
                lambda: camera.disable_positional_tracking()
                if self._body_tracking_enabled
                else None,
                camera.close,
            ):
                try:
                    action()
                except Exception as exc:  # shutdown must never raise
                    logger.warning("ZED kapatma sırasında hata: %s", exc)
            self._info = None
            self._camera = None
            self._spec = None
            self._body_tracking_enabled = False
            self._mat_color = None
            self._mat_depth = None
            self._bodies = None
            logger.info("ZED kamera kapatıldı.")

    def get_camera_info(self) -> Optional[CameraInfo]:
        return self._info

    def skeleton_spec(self) -> Optional[SkeletonSpec]:
        return self._spec

    # ---------------------------------------------------------------- frames
    def grab_frame(self) -> Optional[FramePacket]:
        """Grab one frame with colour, optional depth and detected bodies."""
        camera = self._camera
        if camera is None:
            raise CameraNotConnectedError("ZED kamera bağlı değil.")
        if not self._previewing:
            return None

        sl = _import_sl()
        if sl is None:  # pragma: no cover - cannot happen once connected
            raise CameraError("pyzed kullanılamıyor.", code="pyzed_missing")

        status = camera.grab(self._runtime)
        if status != sl.ERROR_CODE.SUCCESS:
            if status == sl.ERROR_CODE.CAMERA_NOT_DETECTED:
                raise CameraError(
                    "Kamera bağlantısı koptu.",
                    code="zed_camera_disconnected",
                    remedy="USB bağlantısını kontrol edip yeniden bağlanın.",
                    details={"error_code": str(status)},
                )
            # A transient grab failure is normal (corrupted frame, warm-up); it
            # is reported as "no frame this tick", not as data.
            logger.debug("ZED grab başarısız: %s", status)
            return None

        color = None
        profile = self._profile
        now = time.perf_counter()
        full_rgb = profile.requires_full_rgb
        preview_due = profile.preview_enabled and now - self._last_rgb_time >= 1 / profile.preview_fps
        if full_rgb or preview_due:
            if full_rgb:
                status = camera.retrieve_image(self._mat_color, sl.VIEW.LEFT)
            else:
                width, height = self._info.resolution
                scaled_width = min(width, profile.preview_width)
                resolution = sl.Resolution(scaled_width, max(1, round(height * scaled_width / width)))
                status = camera.retrieve_image(self._mat_color, sl.VIEW.LEFT, sl.MEM.CPU, resolution)
            self._check_retrieval(sl, status, "rgb")
            color_bgra = self._mat_color.get_data()
            color = np.ascontiguousarray(color_bgra[:, :, :3][:, :, ::-1])
            color.setflags(write=False)
            self._last_rgb_time = now

        depth = None
        if self._depth_enabled:
            self._check_retrieval(
                sl, camera.retrieve_measure(self._mat_depth, sl.MEASURE.DEPTH), "depth"
            )
            depth = owned_snapshot(self._mat_depth.get_data(), np.float32)

        bodies = self._retrieve_bodies(sl, camera)

        image_timestamp = camera.get_timestamp(sl.TIME_REFERENCE.IMAGE)
        index = self._frame_index
        self._frame_index += 1

        return FramePacket(
            frame_index=index,
            host_timestamp_ns=time.time_ns(),
            camera_timestamp_ns=int(image_timestamp.get_nanoseconds()),
            color_frame=color,
            depth_frame=depth,
            bodies=bodies,
            capture_status=CaptureStatus.OK,
            origin=DataOrigin.REAL,
            backend_dropped_frames=int(camera.get_frame_dropped_count()),
            source_resolution=self._info.resolution,
        )

    @staticmethod
    def _optional_array(
        body: Any, attribute: str, shape: tuple[int, ...]
    ) -> Optional[np.ndarray]:
        """Read one optional SDK array, or ``None`` if it is absent or wrong.

        Some body formats simply do not produce some of these arrays (body
        fitting outputs are empty for ``BODY_18``, for instance). A field that
        is missing, empty or the wrong shape becomes ``None`` - never a
        reshaped or padded value, which would silently re-index joints.
        """
        raw = getattr(body, attribute, None)
        if raw is None:
            return None
        array = np.asarray(raw, dtype=np.float32)
        if array.shape != shape:
            return None
        return owned_snapshot(array, np.float32)

    @staticmethod
    def _check_retrieval(sl: Any, status: Any, product: str) -> None:
        if status != sl.ERROR_CODE.SUCCESS:
            raise CameraError(
                f"ZED {product} verisi alınamadı: {status}",
                code="zed_retrieval_failed",
                details={"product": product, "error_code": str(status)},
            )

    def _retrieve_bodies(self, sl: Any, camera: Any) -> tuple[BodyPose, ...]:
        if not self._body_tracking_enabled or self._spec is None:
            return ()
        self._check_retrieval(
            sl, camera.retrieve_bodies(self._bodies, self._body_runtime), "bodies"
        )
        expected_joints = self._spec.num_joints
        poses: list[BodyPose] = []
        for body in self._bodies.body_list:
            joints = np.asarray(body.keypoint, dtype=np.float32)
            if joints.shape != (expected_joints, 3):
                # Never silently reshape: a mismatch means the configured body
                # format and the delivered data disagree, which would corrupt
                # every downstream joint index.
                logger.error(
                    "Beklenmeyen eklem sayısı: %s (beklenen %s eklem, format %s)",
                    joints.shape,
                    expected_joints,
                    self._spec.name,
                )
                continue
            confidences = np.asarray(body.keypoint_confidence, dtype=np.float32)
            if confidences.shape != (expected_joints,):
                confidences = np.full(expected_joints, np.nan, dtype=np.float32)
            else:
                # The SDK reports confidence on a 0..100 scale; the domain model
                # uses 0..1. NaN marks a joint the tracker could not see.
                confidences = confidences / 100.0

            per_joint = (expected_joints,)
            poses.append(
                BodyPose(
                    tracking_id=int(body.id),
                    tracking_state=self._map_tracking_state(body.tracking_state),
                    body_format=self._spec.name,
                    joint_positions_xyz=owned_snapshot(joints, np.float32),
                    joint_confidences=owned_snapshot(confidences, np.float32),
                    # Quaternion component order is xyzw, verified against this
                    # SDK: sl.Rotation for +90 deg about Y yields
                    # [0, 0.7071, 0, 0.7071].
                    joint_orientations=self._optional_array(
                        body, "local_orientation_per_joint", (*per_joint, 4)
                    ),
                    root_position=self._optional_array(body, "position", (3,)),
                    root_orientation=self._optional_array(
                        body, "global_root_orientation", (4,)
                    ),
                    body_confidence=float(body.confidence),
                    joint_positions_2d=self._optional_array(
                        body, "keypoint_2d", (*per_joint, 2)
                    ),
                    # Six values per joint, stored in the SDK's own element
                    # order. This project has not verified which order that is,
                    # so it is never interpreted as a named 3x3 covariance.
                    joint_position_covariances=self._optional_array(
                        body, "keypoints_covariance", (*per_joint, 6)
                    ),
                    local_joint_positions_xyz=self._optional_array(
                        body, "local_position_per_joint", (*per_joint, 3)
                    ),
                    tracker_root_velocity_xyz=self._optional_array(
                        body, "velocity", (3,)
                    ),
                    root_position_covariance=self._optional_array(
                        body, "position_covariance", (6,)
                    ),
                    action_state=BodyActionState.parse(
                        getattr(getattr(body, "action_state", None), "name", None)
                    ),
                )
            )
        return tuple(poses)

    @staticmethod
    def _map_tracking_state(raw: Any) -> TrackingState:
        name = str(getattr(raw, "name", raw)).upper().rsplit(".", 1)[-1]
        return _TRACKING_STATE_NAMES.get(name, TrackingState.OFF)

    # ------------------------------------------------------ native recording
    def start_native_recording(self, path: Path) -> bool:
        """Start immutable SVO2 using the requested, explicitly named codec."""
        camera = self._camera
        if camera is None:
            raise CameraNotConnectedError("ZED kamera bağlı değil.")
        if self._recording:
            return True

        sl = _import_sl()
        if sl is None:  # pragma: no cover
            return False

        path = Path(path)
        if path_exists(path):
            raise CameraError("Ham kayıt hedefi zaten var.", code="raw_source_exists")
        ensure_dir(path.parent)
        params = sl.RecordingParameters()
        params.video_filename = str(path)
        codec = self._profile.native_compression.upper()
        try:
            params.compression_mode = getattr(sl.SVO_COMPRESSION_MODE, codec)
        except AttributeError as exc:
            raise CameraError(
                f"Desteklenmeyen SVO codec: {codec}", code="zed_codec_invalid"
            ) from exc
        status = camera.enable_recording(params)
        if status != sl.ERROR_CODE.SUCCESS:
            raise CameraError(
                f"ZED native kaydı başlatılamadı: {status}",
                code="zed_recording_failed",
                remedy="Disk alanını ve hedef klasörün yazma iznini kontrol edin.",
                details={"error_code": str(status), "path": str(path)},
            )
        self._recording = True
        self._recording_path = path
        self._recording_codec = codec
        logger.info("SVO2 kaydı başladı: %s", path.name)
        return True

    def stop_native_recording(self) -> None:
        camera = self._camera
        if camera is None or not self._recording:
            self._recording = False
            return
        try:
            camera.disable_recording()
        finally:
            self._recording = False
            logger.info("SVO2 kaydı durduruldu.")

    def native_recording_stats(self) -> dict[str, Any]:
        camera = self._camera
        if camera is None or not self._recording:
            return {}
        try:
            status = camera.get_recording_status()
        except Exception:  # pragma: no cover - device dependent
            return {}
        return {
            "active": bool(getattr(status, "status", False)),
            "frames_ingested": int(getattr(status, "number_frames_ingested", 0)),
            "frames_encoded": int(getattr(status, "number_frames_encoded", 0)),
            "average_compression_ratio": float(
                getattr(status, "average_compression_ratio", 0.0)
            ),
            "path": str(self._recording_path) if self._recording_path else None,
        }


__all__ = [
    "ZedCameraBackend",
    "is_pyzed_available",
    "list_devices",
    "pyzed_import_error",
    "sdk_version",
]
