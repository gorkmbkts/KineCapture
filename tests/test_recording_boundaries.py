"""Adversarial lifecycle tests: actual worker scheduling, disposable sources."""

import json
import threading
import time

import pytest

from conftest import paced_backend, record_take
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import StorageError
from kinecapture.domain.enums import TakeState
from kinecapture.playback.take_reader import load_skeleton_stream
from kinecapture.recording.take_writer import TakeWriter


def test_native_source_and_sidecar_share_start_stop_boundary(workspace, session):
    backend = paced_backend()
    original_grab = backend.grab_frame
    source_indices = []
    native = False

    def start(path):
        nonlocal native
        path.write_bytes(b"unit-test-source; not an SVO")
        native = True
        return True

    def stop():
        nonlocal native
        native = False

    def grab():
        packet = original_grab()
        if packet is not None and native:
            source_indices.append(packet.frame_index)
        return packet

    backend.supports_native_recording = lambda: True
    backend.start_native_recording = start
    backend.stop_native_recording = stop
    backend.grab_frame = grab
    service = CaptureService(backend)
    try:
        service.connect()
        take = record_take(service, workspace, session, frames=10)
        stream = load_skeleton_stream(workspace.take_paths(take).skeleton_stream)
        assert [frame.frame_index for frame in stream.frames] == source_indices
        assert len(source_indices) >= 10
    finally:
        service.shutdown()


def test_writer_timeout_keeps_streams_owned_until_writer_finishes(
    workspace, session, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    original_write = TakeWriter.write_frame

    def blocked_write(writer, *args):
        entered.set()
        assert release.wait(3)
        return original_write(writer, *args)

    monkeypatch.setattr(TakeWriter, "write_frame", blocked_write)
    service = CaptureService(paced_backend(), recording_queue_size=2)
    try:
        service.connect()
        service.start_preview()
        take = service.start_recording(workspace, session)
        assert entered.wait(2)
        # A bounded close must not close a file under an active writer.
        monkeypatch.setattr("kinecapture.capture.service._JOIN_TIMEOUT_S", 0.05)
        before = time.monotonic()
        with pytest.raises(StorageError) as error:
            service.stop_recording()
        assert error.value.code == "writer_close_pending"
        assert time.monotonic() - before < 1
        assert service._writer is not None and not service._writer._closed
        stored = json.loads(workspace.take_paths(take).metadata.read_text())
        assert stored["state"] == TakeState.RECORDING.value
        release.set()
        service._writer_thread.join(timeout=2)
        service.stop_recording()
        assert service._writer is None
    finally:
        release.set()
        service.shutdown()


def test_native_false_is_not_a_successful_recording(workspace, session):
    backend = paced_backend()
    backend.supports_native_recording = lambda: True
    backend.start_native_recording = lambda path: False
    service = CaptureService(backend)
    try:
        service.connect()
        service.start_preview()
        with pytest.raises(StorageError, match="ham kaydı"):
            service.start_recording(workspace, session)
        assert service._writer is None
    finally:
        service.shutdown()
