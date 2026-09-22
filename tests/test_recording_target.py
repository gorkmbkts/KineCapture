"""Where a recording would be written, checked before anything is disturbed.

On 20 September three recordings failed in a row with ``SVO RECORDING ERROR``
and a message telling the operator to check disk space and permissions. The
disk had 138 GB free and the folder was writable. The real cause was the
length of the target path: 279 characters, against a machine whose
``LongPathsEnabled`` is 0. The application's own writers reach that depth
because they prefix ``\\\\?\\``; the ZED SDK opens the file from the plain
string it is handed and cannot.

Measured at that exact length before these tests were written: a plain
``CreateFileW`` and a plain ``CreateFileA`` both returned ``ERROR_PATH_NOT_FOUND``
while the prefixed call succeeded.

So the question is asked of the *project*, before a take exists and before the
preview is touched, and a start that is refused leaves the camera exactly as it
was.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kinecapture.capture.service import CaptureService, RecordingTargetCheck
from kinecapture.core.errors import StorageError
from kinecapture.core.paths import MAX_PATH
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import CaptureState



def test_the_longest_path_is_known_before_anything_is_recorded(
    workspace: ProjectWorkspace,
) -> None:
    longest = workspace.longest_raw_path()

    assert longest.name == "capture.svo2"
    assert longest.is_relative_to(workspace.root)
    # Fixed-width identifiers all the way down, which is what makes the
    # question answerable at all.
    assert "participants" in longest.parts and "takes" in longest.parts


def test_a_backend_without_a_limit_is_never_refused() -> None:
    check = RecordingTargetCheck(
        path=Path("C:/" + "x" * 400), length=403, limit=None, needs_native=True
    )
    assert check.ok
    check.require()  # does not raise


def test_a_path_over_the_backend_limit_is_refused_with_the_numbers() -> None:
    check = RecordingTargetCheck(
        path=Path("C:/some/long/target/capture.svo2"),
        length=281,
        limit=MAX_PATH,
        needs_native=True,
    )
    assert not check.ok
    with pytest.raises(StorageError) as caught:
        check.require()

    error = caught.value
    assert error.code == "recording_target_path_too_long"
    assert error.details["length"] == 281
    assert error.details["over_by"] == 281 - MAX_PATH
    # The advice has to name the fix, not a generic disk/permission guess.
    assert "Veri klasörünü" in error.remedy
    assert "disk" not in error.remedy.lower()


def test_the_real_20_september_geometry_is_caught(tmp_path: Path) -> None:
    """The scratchpad root that leaked into the user's settings, measured."""
    leaked = (
        r"C:\Users\gorke\AppData\Local\Temp\claude"
        r"\C--Users-gorke-Desktop-KineCapture"
        r"\669f5dfe-dadd-45eb-8c6b-5d3a0a82e402\scratchpad\waste_home\datasets"
        r"\projects\prj_20260920T195851_f700"
    )
    # The deepest file such a project can hold, built the way the layout does.
    deepest = (
        Path(leaked)
        / "participants"
        / "P0001"
        / "sessions"
        / "ses_20260920T195927_ade1"
        / "takes"
        / "take_20260920T195927_0482"
        / "raw"
        / "capture.svo2"
    )
    check = RecordingTargetCheck(
        path=deepest, length=len(str(deepest)), limit=MAX_PATH, needs_native=True
    )
    assert check.length == 279, check.length
    assert not check.ok

    # And the root the user actually works in is comfortably inside it.
    short = (
        Path(r"C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4")
        / "participants/P0001/sessions/ses_20260916T151622_57a9"
        / "takes/take_20260920T195059_c183/raw/capture.svo2"
    )
    assert len(str(short)) <= MAX_PATH


def test_a_refused_start_leaves_the_preview_running(
    capture_service_with_long_target,
) -> None:
    """The camera must not be dead afterwards. It was, until now."""
    service, workspace, session = capture_service_with_long_target
    service.start_preview()
    assert service.state is CaptureState.PREVIEWING

    with pytest.raises(StorageError) as caught:
        service.start_recording(workspace, session)

    assert caught.value.code == "recording_target_path_too_long"
    # Not ERROR, which can only be left through DISCONNECTED.
    assert service.state is CaptureState.PREVIEWING
    assert service.is_recording is False
    # And nothing was created in the dataset for an attempt that never began.
    assert list(workspace.list_takes(session.participant_id, session.session_id)) == []

    service.stop_preview()


def test_the_refusal_can_be_retried_after_the_cause_is_fixed(
    capture_service_with_long_target, monkeypatch
) -> None:
    service, workspace, session = capture_service_with_long_target
    service.start_preview()
    with pytest.raises(StorageError):
        service.start_recording(workspace, session)

    # The operator moves the data folder; here, the limit stops applying.
    monkeypatch.setattr(
        type(service.backend), "native_recording_path_limit", property(lambda _s: None)
    )
    take = service.start_recording(workspace, session)
    assert take is not None
    assert service.is_recording
    service.stop_recording()


@pytest.fixture
def capture_service_with_long_target(workspace, session, mock_backend, monkeypatch):
    """A synthetic camera that claims a path limit its target cannot meet."""
    monkeypatch.setattr(
        type(mock_backend),
        "native_recording_path_limit",
        property(lambda _s: 8),
        raising=False,
    )
    monkeypatch.setattr(
        type(mock_backend), "supports_native_recording", lambda _s: True, raising=False
    )
    # The synthetic camera has no recorder of its own; give it one that always
    # succeeds, so what this file measures is the *check*, not the mock.
    monkeypatch.setattr(
        type(mock_backend), "start_native_recording", lambda _s, _p: True, raising=False
    )
    service = CaptureService(mock_backend)
    service.connect()
    yield service, workspace, session
    service.shutdown()
