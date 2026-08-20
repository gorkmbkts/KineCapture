"""Mock backend determinism, the state machine, and the capture service."""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.camera import create_backend
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import CameraNotConnectedError
from kinecapture.core.state_machine import (
    ALLOWED_TRANSITIONS,
    CaptureStateMachine,
    InvalidStateTransition,
)
from kinecapture.domain.enums import BackendKind, CaptureState, DataOrigin


# --------------------------------------------------------------- factories


def test_backend_factory_accepts_string_and_enum() -> None:
    """Qt hands enum item data back as a plain string; both must work."""
    assert isinstance(create_backend("mock"), MockCameraBackend)
    assert isinstance(create_backend(BackendKind.MOCK), MockCameraBackend)


def test_backend_factory_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Bilinmeyen backend"):
        create_backend("webcam")


# ------------------------------------------------------------ mock backend


def test_mock_is_always_available(mock_backend: MockCameraBackend) -> None:
    result = mock_backend.is_available()
    assert result.available and result.code == "ok"
    assert result.details["synthetic"] is True


def test_mock_frames_are_deterministic() -> None:
    """Same seed, same geometry, byte-identical frames and joints."""

    def capture(count: int) -> list:
        backend = MockCameraBackend(width=64, height=48, fps=30, seed=99)
        backend.connect()
        backend.start_preview()
        frames = [backend.grab_frame() for _ in range(count)]
        backend.disconnect()
        return frames

    first, second = capture(5), capture(5)
    for a, b in zip(first, second):
        np.testing.assert_array_equal(a.color_frame, b.color_frame)
        np.testing.assert_array_equal(
            a.bodies[0].joint_positions_xyz, b.bodies[0].joint_positions_xyz
        )
        assert a.camera_timestamp_ns == b.camera_timestamp_ns


def test_different_seeds_differ() -> None:
    def first_frame(seed: int):
        backend = MockCameraBackend(width=64, height=48, seed=seed)
        backend.connect()
        backend.start_preview()
        frame = backend.grab_frame()
        backend.disconnect()
        return frame

    assert not np.array_equal(
        first_frame(1).color_frame, first_frame(2).color_frame
    )


def test_mock_marks_every_frame_synthetic(mock_backend: MockCameraBackend) -> None:
    info = mock_backend.connect()
    assert info.origin is DataOrigin.SYNTHETIC
    mock_backend.start_preview()
    packet = mock_backend.grab_frame()
    assert packet.is_synthetic
    assert packet.origin is DataOrigin.SYNTHETIC


def test_mock_produces_depth_with_invalid_regions() -> None:
    backend = MockCameraBackend(width=64, height=48, enable_depth=True)
    backend.connect()
    backend.start_preview()
    packet = backend.grab_frame()
    backend.disconnect()
    assert packet.depth_frame is not None
    # A real sensor always has pixels without depth; the mock must too, so
    # downstream code is exercised against NaN.
    assert np.isnan(packet.depth_frame).any()
    assert np.isfinite(packet.depth_frame).any()


def test_mock_multi_body_scenario() -> None:
    backend = MockCameraBackend(width=64, height=48, num_bodies=3)
    backend.connect()
    backend.start_preview()
    packet = backend.grab_frame()
    backend.disconnect()
    assert len(packet.bodies) == 3
    assert {b.tracking_id for b in packet.bodies} == {1, 2, 3}
    assert backend.capabilities().multi_body


def test_mock_tracking_loss_scenario() -> None:
    backend = MockCameraBackend(width=64, height=48, tracking_loss_every=20)
    backend.connect()
    backend.start_preview()
    frames = [backend.grab_frame() for _ in range(40)]
    backend.disconnect()
    empty = [f for f in frames if not f.bodies]
    assert empty, "scripted tracking loss produced no empty frames"
    assert len(empty) < len(frames), "backend lost the body permanently"


def test_mock_low_confidence_scenario_blanks_joints() -> None:
    backend = MockCameraBackend(width=64, height=48, low_confidence_every=30)
    backend.connect()
    backend.start_preview()
    frames = [backend.grab_frame() for _ in range(20)]
    backend.disconnect()
    degraded = [
        f for f in frames if f.bodies and f.bodies[0].valid_joint_ratio < 1.0
    ]
    assert degraded, "low-confidence scenario never degraded a joint"
    body = degraded[0].bodies[0]
    assert float(body.joint_confidences.min()) < 0.4


def test_mock_grab_requires_connection(mock_backend: MockCameraBackend) -> None:
    with pytest.raises(CameraNotConnectedError):
        mock_backend.grab_frame()


def test_mock_grab_returns_none_when_not_previewing(
    mock_backend: MockCameraBackend,
) -> None:
    mock_backend.connect()
    assert mock_backend.grab_frame() is None


def test_mock_disconnect_is_idempotent(mock_backend: MockCameraBackend) -> None:
    mock_backend.connect()
    mock_backend.disconnect()
    mock_backend.disconnect()  # must not raise


def test_mock_does_not_support_native_recording(
    mock_backend: MockCameraBackend, tmp_path
) -> None:
    """A backend that cannot record natively says so instead of pretending."""
    assert not mock_backend.supports_native_recording()
    assert mock_backend.start_native_recording(tmp_path / "x.svo2") is False


# ------------------------------------------------------------ state machine


def test_state_machine_default_state() -> None:
    assert CaptureStateMachine().state is CaptureState.DISCONNECTED


def test_valid_transition_path() -> None:
    machine = CaptureStateMachine()
    for target in (
        CaptureState.READY,
        CaptureState.PREVIEWING,
        CaptureState.RECORDING,
        CaptureState.STOPPING,
        CaptureState.READY,
    ):
        machine.transition(target)
    assert machine.state is CaptureState.READY


def test_invalid_transition_raises() -> None:
    machine = CaptureStateMachine()
    with pytest.raises(InvalidStateTransition):
        machine.transition(CaptureState.RECORDING)


def test_error_is_reachable_and_recovers_through_disconnected() -> None:
    machine = CaptureStateMachine()
    machine.transition(CaptureState.ERROR)
    assert machine.allowed_targets() == frozenset({CaptureState.DISCONNECTED})
    machine.transition(CaptureState.DISCONNECTED)
    assert machine.state is CaptureState.DISCONNECTED


def test_every_state_has_a_transition_table() -> None:
    for state in CaptureState:
        assert state in ALLOWED_TRANSITIONS


def test_listeners_receive_previous_and_current() -> None:
    machine = CaptureStateMachine()
    seen: list[tuple[CaptureState, CaptureState]] = []
    machine.add_listener(lambda previous, current: seen.append((previous, current)))
    machine.transition(CaptureState.READY)
    assert seen == [(CaptureState.DISCONNECTED, CaptureState.READY)]


def test_force_bypasses_the_graph_for_recovery() -> None:
    machine = CaptureStateMachine()
    machine.force(CaptureState.RECORDING)
    assert machine.state is CaptureState.RECORDING


# --------------------------------------------------------- capture service


def test_service_connect_and_disconnect(mock_backend: MockCameraBackend) -> None:
    service = CaptureService(mock_backend)
    info = service.connect()
    assert service.state is CaptureState.READY
    assert info.is_synthetic
    service.disconnect()
    assert service.state is CaptureState.DISCONNECTED


def test_service_preview_lifecycle(mock_backend: MockCameraBackend) -> None:
    service = CaptureService(mock_backend)
    service.connect()
    service.start_preview()
    assert service.state is CaptureState.PREVIEWING
    service.start_preview()  # idempotent
    assert service.state is CaptureState.PREVIEWING
    service.stop_preview()
    assert service.state is CaptureState.READY
    service.stop_preview()  # idempotent
    service.shutdown()


def test_service_delivers_frames(mock_backend: MockCameraBackend) -> None:
    import time

    service = CaptureService(mock_backend)
    service.connect()
    service.start_preview()
    deadline = time.time() + 5.0
    packet = None
    while packet is None and time.time() < deadline:
        packet = service.latest_frame()
        time.sleep(0.005)
    service.shutdown()
    assert packet is not None, "acquisition thread delivered no frames"
    assert service.statistics.frames_acquired > 0


def test_preview_slot_is_latest_wins(mock_backend: MockCameraBackend) -> None:
    """A slow consumer skips preview frames and they are counted as preview drops."""
    import time

    service = CaptureService(mock_backend)
    service.connect()
    service.start_preview()
    time.sleep(0.25)  # let the acquisition thread outrun the (absent) consumer
    service.stop_preview()
    stats = service.statistics
    service.shutdown()
    assert stats.frames_acquired > 1
    assert stats.preview_frames_dropped > 0
    # Preview throttling is not capture loss and must never be reported as such.
    assert stats.recording_frames_dropped == 0
    assert not stats.has_capture_loss


def test_service_shutdown_is_idempotent(mock_backend: MockCameraBackend) -> None:
    service = CaptureService(mock_backend)
    service.connect()
    service.start_preview()
    service.shutdown()
    service.shutdown()
    assert service.state is CaptureState.DISCONNECTED


def test_recording_requires_preview(
    mock_backend: MockCameraBackend, workspace, session
) -> None:
    service = CaptureService(mock_backend)
    service.connect()
    with pytest.raises(InvalidStateTransition):
        service.start_recording(workspace, session)
    service.shutdown()


def test_stop_recording_without_recording_returns_none(
    mock_backend: MockCameraBackend,
) -> None:
    service = CaptureService(mock_backend)
    service.connect()
    assert service.stop_recording() is None
    service.shutdown()


def test_active_body_change_is_recorded_not_silent(
    mock_backend: MockCameraBackend, workspace, session
) -> None:
    from tests.conftest import paced_backend

    backend = paced_backend(width=64, height=48, num_bodies=2)
    service = CaptureService(backend)
    service.connect()
    service.start_preview()
    take = service.start_recording(workspace, session)
    service.set_active_body_id(1)
    import time

    deadline = time.time() + 10.0
    while service.recorded_frame_count < 10 and time.time() < deadline:
        time.sleep(0.005)
    service.set_active_body_id(2)  # a real switch
    while service.recorded_frame_count < 20 and time.time() < deadline:
        time.sleep(0.005)
    take = service.stop_recording()
    service.shutdown()
    assert take is not None
    assert take.body_id_events, "identity switch was not recorded"
    assert take.body_id_events[0]["previous_id"] == 1
    assert take.body_id_events[0]["new_id"] == 2
