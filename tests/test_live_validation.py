"""Operator controls must never auto-record or abandon an active writer."""
import time
import numpy as np
from PySide6.QtWidgets import QApplication

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.domain.project import CaptureProfile
from kinecapture.preview.pose import PosePreview
from kinecapture.tools.live_validation import ValidationWindow, SwitchablePose
from kinecapture.core.jsonio import read_json


def wait_until(app, predicate, timeout=8):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate(): return
        time.sleep(.01)
    raise AssertionError("UI state did not finish")


def test_manual_countdown_stop_and_multiple_takes(tmp_path):
    app=QApplication.instance() or QApplication([])
    model=lambda packet: PosePreview(packet, ())
    processor=SwitchablePose(None,model=model)
    backend=MockCameraBackend(width=96,height=72,fps=60,real_time=True,profile=CaptureProfile())
    window=ValidationWindow(tmp_path,processor=processor,backend=backend,countdown_seconds=5,max_seconds=2)
    window.show()
    try:
        wait_until(app,lambda: window.mode=="ready")
        assert window.service.active_take is None
        window.start_button.click()
        assert window.mode=="countdown"
        window.stop_button.click()
        assert window.mode=="ready" and window.service.active_take is None
        window.countdown.setValue(0)
        window.start_button.click()
        wait_until(app,lambda: window.service.recorded_frame_count>=5)
        assert not window.case.isEnabled()
        window.stop_button.click()
        wait_until(app,lambda: window.mode=="ready")
        assert len(window.takes)==1 and window.takes[0]["state"]=="finalized"
        window.case.setCurrentIndex(1)
        window.start_button.click()
        wait_until(app,lambda: window.service.recorded_frame_count>=5)
        window.finish_button.click()
        wait_until(app,lambda: window.closed_cleanly)
        assert len(window.takes)==2 and window.takes[1]["state"]=="finalized"
        assert window.takes[0]["take_id"]!=window.takes[1]["take_id"]
        saved=read_json(window.workspace.root/"validation.json")
        assert saved["closed_cleanly"] and len(saved["takes"])==2
    finally:
        if not window.closed_cleanly:
            window.finish()
            wait_until(app,lambda: window.closed_cleanly)
