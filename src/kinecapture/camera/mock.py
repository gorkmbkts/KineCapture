"""Deterministic synthetic camera backend.

This is the reference backend for development without hardware and for the
automated tests - not a toy demo. Everything the ZED backend can drive
(recording, playback, segmentation, annotation, export) must work here too.

Determinism guarantees, relied on by the tests:

* two backends built with the same seed and geometry produce byte-identical
  colour frames and bit-identical joint arrays for the same frame index;
* ``grab_frame`` never sleeps unless explicitly asked to pace itself, so tests
  run at full speed instead of in real time;
* the scripted degradations (tracking loss, low confidence, dropped frames) are
  a function of the frame index alone, so a failure is always reproducible.

Every frame is stamped ``DataOrigin.SYNTHETIC``, which propagates into take
metadata, the GUI and any exported release.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Optional

import numpy as np

from kinecapture.camera.base import (
    AvailabilityResult,
    BackendCapabilities,
    CameraBackend,
)
from kinecapture.core.errors import CameraNotConnectedError
from kinecapture.domain.enums import (
    BodyActionState,
    CaptureStatus,
    DataOrigin,
    TrackingState,
)
from kinecapture.domain.models import BodyPose, CameraInfo, FramePacket
from kinecapture.visualization.skeleton_spec import MOCK_SKELETON, SkeletonSpec

#: Neutral rest pose in metres, in the same right-handed Y-up convention the
#: ZED backend is configured with, so display code needs no special cases.
_REST_POSE: dict[str, tuple[float, float, float]] = {
    "pelvis": (0.00, 0.95, 2.50),
    "chest_spine": (0.00, 1.25, 2.50),
    "neck": (0.00, 1.48, 2.50),
    "head": (0.00, 1.63, 2.50),
    "left_shoulder": (0.19, 1.43, 2.50),
    "left_elbow": (0.25, 1.18, 2.50),
    "left_wrist": (0.27, 0.94, 2.50),
    "right_shoulder": (-0.19, 1.43, 2.50),
    "right_elbow": (-0.25, 1.18, 2.50),
    "right_wrist": (-0.27, 0.94, 2.50),
    "left_hip": (0.11, 0.93, 2.50),
    "left_knee": (0.12, 0.52, 2.50),
    "left_ankle": (0.12, 0.08, 2.50),
    "right_hip": (-0.11, 0.93, 2.50),
    "right_knee": (-0.12, 0.52, 2.50),
    "right_ankle": (-0.12, 0.08, 2.50),
}


class MockCameraBackend(CameraBackend):
    """Synthetic RGB (and optional depth) plus one or more moving skeletons."""

    name = "mock"
    origin = DataOrigin.SYNTHETIC

    def __init__(
        self,
        width: int = 960,
        height: int = 540,
        fps: float = 30.0,
        seed: int = 1234,
        num_bodies: int = 1,
        enable_depth: bool = True,
        tracking_loss_every: int = 0,
        low_confidence_every: int = 0,
        skeleton: SkeletonSpec = MOCK_SKELETON,
        real_time: bool = False,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("mock frame size must be positive")
        if fps <= 0:
            raise ValueError("fps must be > 0")
        if num_bodies < 1:
            raise ValueError("num_bodies must be >= 1")
        self._width = int(width)
        self._height = int(height)
        self._fps = float(fps)
        self._seed = int(seed)
        self._num_bodies = int(num_bodies)
        self._enable_depth = bool(enable_depth)
        self._tracking_loss_every = int(tracking_loss_every)
        self._low_confidence_every = int(low_confidence_every)
        self._skeleton = skeleton
        #: When True, ``grab_frame`` paces itself to the target FPS so the GUI
        #: preview looks like a real camera. Tests leave it False.
        self._real_time = bool(real_time)

        self._connected = False
        self._previewing = False
        self._frame_index = 0
        self._info: Optional[CameraInfo] = None
        self._next_frame_time: Optional[float] = None
        self._backend_drops = 0
        self._native_recording_path: Optional[Path] = None
        self._background = self._render_background()

    # ---------------------------------------------------------------- probe
    def is_available(self) -> AvailabilityResult:
        return AvailabilityResult.ok(
            "Sentetik backend her zaman kullanılabilir (donanım gerekmez).",
            details={
                "seed": self._seed,
                "resolution": [self._width, self._height],
                "num_bodies": self._num_bodies,
                "synthetic": True,
            },
        )

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            color=True,
            depth=self._enable_depth,
            body_tracking=True,
            native_recording=False,
            multi_body=self._num_bodies > 1,
            device_enumeration=False,
        )

    def diagnostics(self) -> dict[str, object]:
        return {
            "backend": self.name,
            "origin": self.origin.value,
            "seed": self._seed,
            "resolution": f"{self._width}x{self._height}",
            "target_fps": self._fps,
            "num_bodies": self._num_bodies,
            "skeleton_format": self._skeleton.name,
            "scripted_tracking_loss_every": self._tracking_loss_every,
            "scripted_low_confidence_every": self._low_confidence_every,
        }

    # ------------------------------------------------------------ lifecycle
    def connect(self) -> CameraInfo:
        self._connected = True
        self._frame_index = 0
        self._backend_drops = 0
        self._info = CameraInfo(
            backend=self.name,
            model="Sentetik Kamera",
            origin=DataOrigin.SYNTHETIC,
            serial_number=f"MOCK-{self._seed:06d}",
            sdk_version=None,
            resolution=(self._width, self._height),
            target_fps=self._fps,
            coordinate_system="right_handed_y_up",
            length_unit="meter",
            body_format=self._skeleton.name,
            depth_available=self._enable_depth,
            body_tracking_available=True,
            extra={"deterministic": True, "seed": self._seed, "synthetic": True},
        )
        return self._info

    def start_preview(self) -> None:
        if not self._connected:
            raise CameraNotConnectedError(
                "Sentetik kamera önizleme öncesi bağlanmalıdır.",
                remedy="Önce Bağlan düğmesini kullanın.",
            )
        self._previewing = True
        self._next_frame_time = time.perf_counter() if self._real_time else None

    def stop_preview(self) -> None:
        self._previewing = False
        self._next_frame_time = None

    def disconnect(self) -> None:
        self._previewing = False
        self._connected = False
        self._info = None
        self._next_frame_time = None
        self._native_recording_path = None

    def get_camera_info(self) -> Optional[CameraInfo]:
        return self._info

    def skeleton_spec(self) -> Optional[SkeletonSpec]:
        return self._skeleton

    # ---------------------------------------------------------------- frames
    def grab_frame(self) -> Optional[FramePacket]:
        """Produce the next synthetic frame."""
        if not self._connected:
            raise CameraNotConnectedError("Sentetik kamera bağlı değil.")
        if not self._previewing:
            return None

        if self._real_time and self._next_frame_time is not None:
            interval = 1.0 / self._fps
            now = time.perf_counter()
            wait = self._next_frame_time - now
            if wait > 0:
                time.sleep(min(wait, interval))
            # Never accumulate a backlog: if we fell behind, resync and count it
            # as a backend drop instead of pretending it did not happen.
            self._next_frame_time += interval
            if self._next_frame_time < now:
                skipped = int((now - self._next_frame_time) / interval) + 1
                self._backend_drops += skipped
                self._next_frame_time = now + interval

        index = self._frame_index
        self._frame_index += 1

        bodies = tuple(
            body
            for slot in range(self._num_bodies)
            if (body := self._render_body(index, slot)) is not None
        )
        color = self._render_color(index, bodies)
        depth = self._render_depth(index) if self._enable_depth else None
        camera_timestamp_ns = int(index * (1_000_000_000 / self._fps))

        return FramePacket(
            frame_index=index,
            host_timestamp_ns=time.time_ns(),
            camera_timestamp_ns=camera_timestamp_ns,
            color_frame=color,
            depth_frame=depth,
            bodies=bodies,
            capture_status=CaptureStatus.OK,
            origin=DataOrigin.SYNTHETIC,
            backend_dropped_frames=self._backend_drops,
        )

    @property
    def skeleton(self) -> SkeletonSpec:
        return self._skeleton

    @property
    def frame_index(self) -> int:
        return self._frame_index

    # --------------------------------------------------------------- helpers
    def _render_background(self) -> np.ndarray:
        """A static studio-ish backdrop, computed once per backend instance.

        The seed shifts the backdrop's tint and adds a fixed noise field, so two
        backends with different seeds are visibly distinguishable while each one
        stays byte-for-byte reproducible.
        """
        h, w = self._height, self._width
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        vignette = 1.0 - 0.35 * (xs**2)

        rng = np.random.default_rng(self._seed)
        tint = rng.uniform(-0.03, 0.03, size=3).astype(np.float32)
        grain = rng.uniform(0.0, 0.02, size=(h, w)).astype(np.float32)

        frame = np.zeros((h, w, 3), dtype=np.float32)
        frame[..., 0] = (0.10 + 0.10 * ys) * vignette + tint[0]
        frame[..., 1] = (0.12 + 0.12 * ys) * vignette + tint[1]
        frame[..., 2] = (0.16 + 0.16 * ys) * vignette + tint[2]
        frame += grain[..., None]

        floor = int(h * 0.78)
        frame[floor:, :, :] *= 0.55
        for step in range(1, 9):  # floor grid, purely so motion is readable
            row = floor + int((h - floor) * (step / 9.0) ** 1.6)
            if row < h:
                frame[row : row + 1, :, :] += 0.05
        return np.clip(frame, 0.0, 1.0)

    def _render_color(self, index: int, bodies: tuple[BodyPose, ...]) -> np.ndarray:
        """Backdrop, a moving timing bar, and the projected skeletons."""
        frame = self._background.copy()
        h, w = self._height, self._width

        # A one-second sweep so a dropped or duplicated frame is visible by eye.
        phase = (index % max(1, int(self._fps))) / max(1.0, self._fps)
        bar_x = int(phase * (w - 1))
        bar_w = max(2, w // 160)
        frame[: max(4, h // 60), bar_x : bar_x + bar_w, :] = 1.0

        for body in bodies:
            self._draw_body(frame, body)

        return (np.clip(frame, 0.0, 1.0) * 255.0).astype(np.uint8)

    def _project(self, point: np.ndarray) -> Optional[tuple[int, int]]:
        """Pinhole projection of a metre-space point onto the synthetic image."""
        x, y, z = float(point[0]), float(point[1]), float(point[2])
        if not np.isfinite([x, y, z]).all() or z <= 0.05:
            return None
        focal = self._width * 0.75
        u = int(self._width * 0.5 + focal * x / z)
        v = int(self._height * 0.80 - focal * y / z)
        if 0 <= u < self._width and 0 <= v < self._height:
            return u, v
        return None

    def _draw_body(self, frame: np.ndarray, body: BodyPose) -> None:
        spec = self._skeleton
        points = [self._project(body.joint_positions_xyz[i]) for i in range(spec.num_joints)]
        tint = np.array([0.35, 0.85, 0.95], dtype=np.float32)
        for a, b in spec.edges:
            pa, pb = points[a], points[b]
            if pa is None or pb is None:
                continue
            self._draw_line(frame, pa, pb, tint * 0.85, thickness=2)
        for index, point in enumerate(points):
            if point is None:
                continue
            confidence = float(body.joint_confidences[index])
            weight = 1.0 if not np.isfinite(confidence) else max(0.25, confidence)
            self._draw_dot(frame, point, tint * weight, radius=3)

    @staticmethod
    def _draw_line(
        frame: np.ndarray,
        start: tuple[int, int],
        end: tuple[int, int],
        color: np.ndarray,
        thickness: int = 1,
    ) -> None:
        x0, y0 = start
        x1, y1 = end
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(steps + 1):
            t = step / steps
            x = int(round(x0 + (x1 - x0) * t))
            y = int(round(y0 + (y1 - y0) * t))
            MockCameraBackend._draw_dot(frame, (x, y), color, radius=thickness)

    @staticmethod
    def _draw_dot(
        frame: np.ndarray, point: tuple[int, int], color: np.ndarray, radius: int = 2
    ) -> None:
        h, w = frame.shape[:2]
        x, y = point
        x0, x1 = max(0, x - radius), min(w, x + radius + 1)
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        if x0 >= x1 or y0 >= y1:
            return
        frame[y0:y1, x0:x1, :] = color

    def _render_depth(self, index: int) -> np.ndarray:
        """Synthetic depth in metres, with an invalid band so NaN handling is tested."""
        h, w = self._height, self._width
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
        xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        depth = 2.2 + 1.6 * ys + 0.25 * np.abs(xs)
        depth = depth + 0.05 * math.sin(2.0 * math.pi * (index % 60) / 60.0)
        depth = np.broadcast_to(depth, (h, w)).astype(np.float32).copy()
        # A real sensor always has pixels with no depth; mimic that so downstream
        # code never assumes a fully finite depth map.
        depth[: max(1, h // 12), :] = np.nan
        return depth

    def _pose_positions(self, index: int, slot: int) -> np.ndarray:
        """The analytic joint positions of one scripted body, without dropouts.

        Kept separate from :meth:`_render_body` so the same closed-form motion
        can be evaluated at a neighbouring frame - which is how the synthetic
        root velocity below is obtained, rather than by inventing a number.
        """
        spec = self._skeleton
        t = index / self._fps
        rate = 0.25 + 0.05 * slot
        swing = math.sin(2.0 * math.pi * rate * t)
        crouch = 0.22 * (1.0 - math.cos(2.0 * math.pi * rate * t)) / 2.0
        lateral = 0.55 * slot
        depth_offset = 0.35 * slot

        joints = np.zeros((spec.num_joints, 3), dtype=np.float32)
        for i, joint_name in enumerate(spec.joint_names):
            x, y, z = _REST_POSE[joint_name]
            x += lateral
            z += depth_offset
            if joint_name.endswith(("_wrist", "_elbow")):
                z += 0.14 * swing
                y += 0.06 * swing
            if not joint_name.endswith("_ankle"):
                y -= crouch
            if joint_name.endswith("_knee"):
                z += 0.10 * crouch
            joints[i] = (x, y, z)
        return joints

    def _parent_relative(self, joints: np.ndarray) -> np.ndarray:
        """Parent-relative joint positions, mirroring an SDK fitting output.

        Genuinely derived from this backend's own skeleton topology, so it is a
        real property of the synthetic body rather than a stand-in for a
        measurement. The root has no parent and stays at the origin.
        """
        spec = self._skeleton
        parents = {child: parent for parent, child in spec.edges}
        local = np.zeros_like(joints)
        for i in range(spec.num_joints):
            parent = parents.get(i)
            if parent is None:
                continue
            local[i] = joints[i] - joints[parent]
        return local

    def _render_body(self, index: int, slot: int) -> Optional[BodyPose]:
        """One scripted skeleton. Returns ``None`` during a scripted dropout."""
        spec = self._skeleton
        tracking_id = 1 + slot

        if self._tracking_loss_every > 0 and index > 0:
            # Lose the body for 10 consecutive frames on every cycle.
            if index % self._tracking_loss_every < 10:
                return None

        joints = self._pose_positions(index, slot)
        confidences = np.full(spec.num_joints, 0.94, dtype=np.float32)
        confidences -= 0.05 * float(slot)

        if self._low_confidence_every > 0 and index % self._low_confidence_every < 15:
            # Wrists and ankles degrade first on a real tracker; mirror that, and
            # blank the coordinates entirely so NaN handling is exercised.
            for name in ("left_wrist", "right_wrist", "left_ankle", "right_ankle"):
                joint_index = spec.find(name)
                if joint_index is None:
                    continue
                confidences[joint_index] = 0.15
                joints[joint_index] = np.nan

        state = TrackingState.OK
        if self._tracking_loss_every > 0 and index % self._tracking_loss_every < 18:
            state = TrackingState.SEARCHING

        root_index = spec.root_index
        root = joints[root_index]

        # ---- optional tracker-like fields -------------------------------
        # Only fields this backend can honestly derive from its own motion
        # model are filled. The rest stay NaN, which is what a tracker that
        # does not produce them looks like - and it keeps the NaN paths
        # exercised end to end instead of only in unit tests.
        previous = self._pose_positions(max(0, index - 1), slot)[root_index]
        following = self._pose_positions(index + 1, slot)[root_index]
        span = 2.0 if index > 0 else 1.0
        root_velocity = ((following - previous) * (self._fps / span)).astype(np.float32)

        points_2d = np.full((spec.num_joints, 2), np.nan, dtype=np.float32)
        for i in range(spec.num_joints):
            projected = self._project(joints[i])
            if projected is not None:
                points_2d[i] = projected

        nan_quat = np.full((spec.num_joints, 4), np.nan, dtype=np.float32)
        return BodyPose(
            tracking_id=tracking_id,
            tracking_state=state,
            body_format=spec.name,
            joint_positions_xyz=joints,
            joint_confidences=confidences,
            # No orientation model here: NaN says "not measured" rather than
            # letting an identity quaternion pass for one.
            joint_orientations=nan_quat,
            root_position=None if not np.isfinite(root).all() else root.copy(),
            root_orientation=np.full(4, np.nan, dtype=np.float32),
            body_confidence=float(np.nanmean(confidences) * 100.0),
            joint_positions_2d=points_2d,
            joint_position_covariances=np.full(
                (spec.num_joints, 6), np.nan, dtype=np.float32
            ),
            local_joint_positions_xyz=self._parent_relative(joints),
            tracker_root_velocity_xyz=root_velocity,
            root_position_covariance=np.full(6, np.nan, dtype=np.float32),
            action_state=(
                BodyActionState.MOVING
                if float(np.linalg.norm(root_velocity)) > 0.02
                else BodyActionState.IDLE
            ),
        )


__all__ = ["MockCameraBackend"]
