import time
from threading import Event
from types import SimpleNamespace
from dataclasses import replace
import numpy as np
import pytest

from kinecapture.domain.project import CaptureProfile
from kinecapture.domain.models import FramePacket
from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.capture.subject_lock import SubjectLock, SubjectLockState
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.core.jsonio import read_json, read_jsonl


def test_new_defaults_and_historical_profile_are_separate():
    profile = CaptureProfile()
    assert profile.fps == 60 and profile.native_compression == "H264_LOSSLESS"
    assert not profile.computes_body and not profile.computes_depth
    assert not profile.requires_full_rgb
    old = {"fps": 30, "enable_depth": True, "enable_body_tracking": True}
    assert CaptureProfile.from_dict(old).store_skeleton
    assert not CaptureProfile.for_new_capture(old).computes_depth


def test_headless_zed_grab_never_retrieves_images_depth_or_body(monkeypatch):
    profile = CaptureProfile(preview_enabled=False)
    backend = ZedCameraBackend(profile)
    sl = SimpleNamespace(ERROR_CODE=SimpleNamespace(SUCCESS=0), TIME_REFERENCE=SimpleNamespace(IMAGE=0))
    monkeypatch.setattr("kinecapture.camera.zed._import_sl", lambda: sl)
    def forbidden(*a, **k): raise AssertionError("disabled product executed")
    backend._camera = SimpleNamespace(grab=lambda runtime: 0,
        get_timestamp=lambda ref: SimpleNamespace(get_nanoseconds=lambda: 123456789),
        get_frame_dropped_count=lambda: 0, retrieve_image=forbidden,
        retrieve_measure=forbidden, retrieve_bodies=forbidden)
    backend._info = SimpleNamespace(resolution=(1280,720))
    backend._previewing = True
    packet = backend.grab_frame()
    assert packet.color_frame is None and packet.depth_frame is None and packet.bodies == ()
    assert packet.resolution == (1280,720)


def test_camera_provenance_returns_actual_resolution_and_calibration(monkeypatch):
    backend = ZedCameraBackend()
    monkeypatch.setattr("kinecapture.camera.zed.sdk_version", lambda: "test-sdk")
    calibration = SimpleNamespace(left_cam=SimpleNamespace(fx=100.,fy=110.,cx=80.,cy=60.,
        image_size=SimpleNamespace(width=160,height=120), disto=np.zeros(5)), right_cam=None)
    config = SimpleNamespace(resolution=SimpleNamespace(width=160,height=120), fps=30., calibration_parameters=calibration)
    camera = SimpleNamespace(get_camera_information=lambda: SimpleNamespace(camera_configuration=config,
        serial_number=123,camera_model="ZED test",input_type="test"))
    info = backend._build_camera_info(None, camera, CaptureProfile())
    assert info.resolution == (160,120) and info.target_fps == 30
    assert info.extra["left_camera_calibration"]["fy"] == 110
    assert info.extra["stereo_calibration"]["calibration_parameters"]["left_cam"]["fx"] == 100


@pytest.mark.parametrize("block_listener", [False, True])
def test_preview_and_listeners_cannot_backpressure_recording(workspace, session, block_listener):
    entered, release = Event(), Event()
    def slow(packet):
        entered.set()
        release.wait(4)
        return packet
    profile = CaptureProfile(min_free_disk_minutes=0)
    backend = MockCameraBackend(width=96,height=72,fps=120,real_time=True,profile=profile)
    service = CaptureService(backend, preview_processor=None if block_listener else slow)
    if block_listener: service.add_frame_listener(slow)
    try:
        service.connect(); service.start_preview(); service.start_recording(workspace, session)
        assert entered.wait(2)
        baseline = service.recorded_frame_count
        deadline = time.monotonic()+2
        while service.recorded_frame_count < baseline+20 and time.monotonic() < deadline:
            time.sleep(.01)
        assert service.recorded_frame_count >= baseline+20
        assert not release.is_set() and service.statistics.recording_frames_dropped == 0
    finally:
        release.set()
        service.shutdown()


def test_same_tracker_id_cannot_override_conflicting_geometry():
    backend = MockCameraBackend(width=160,height=120)
    backend.connect(); backend.start_preview()
    body = backend.grab_frame().bodies[0]
    lock = SubjectLock()
    lock.select(body, frame_index=0,timestamp_ns=1_000_000_000,spec=backend.skeleton)
    stranger = replace(body, root_position=body.root_position+np.array([4,0,0]),
                       joint_positions_xyz=body.joint_positions_xyz+np.array([4,0,0]))
    association = lock.update([stranger],frame_index=1,timestamp_ns=1_033_333_333)
    assert association.state is SubjectLockState.AMBIGUOUS and association.tracking_id is None
    assert lock.update([body],frame_index=2,timestamp_ns=1_066_666_666).tracking_id is None


def test_failed_publication_leaves_recording_recoverable(workspace, session, monkeypatch):
    backend = MockCameraBackend(width=160,height=120)
    info=backend.connect(); backend.start_preview()
    take, paths=workspace.prepare_take(session,origin=backend.origin,camera_info=info)
    writer=TakeWriter(workspace,take,paths,write_proxy_video=False,archive_color=True)
    writer.write_frame(backend.grab_frame())
    def fail(*a,**k): raise OSError("injected checksum failure")
    monkeypatch.setattr("kinecapture.recording.take_writer.checksum_manifest",fail)
    with pytest.raises(OSError): writer.finalize()
    assert read_json(paths.metadata)["state"] == "recording"
    assert len(list(read_jsonl(paths.raw_index))) == 2


def test_missing_native_source_cannot_finalize(workspace,session):
    from kinecapture.domain.enums import TakeState
    backend=MockCameraBackend(width=160,height=120)
    info=backend.connect(); backend.start_preview()
    take,paths=workspace.prepare_take(session,origin=backend.origin,camera_info=info)
    writer=TakeWriter(workspace,take,paths,write_proxy_video=False,native_recording_active=True)
    writer.write_frame(backend.grab_frame())
    assert writer.finalize().state is TakeState.PARTIAL
