"""Who a recording belongs to, and which profile it was really taken with.

Two defects from the 15 September audit live here.

*The wrong owner.* A take started with P0002 selected was written under P0001,
because Capture took ``participants[0]`` while the selection lived in the
Projects screen. There is now one selection, held by the session, and these
tests check the file lands where the interface says it will.

*The wrong mode.* "Canlı iskelet" was ticked and the take was written with
``enable_body_tracking=false``, because the mode never reached the backend.
The mode is now part of the profile the camera is built with, and "etkin" is
only claimed once that is true.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.studio.services.capture import (
    LIVE_SKELETON,
    RAW_ONLY,
    mode_of_profile,
    profile_for_mode,
)
from kinecapture.studio.services.messages import Severity
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.capture import CaptureViewModel, RecordingPhase
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from conftest import choose_subject
from kinecapture.studio.viewmodels.tasks import InlineRunner


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    settings = AppConfig()
    settings.dataset_root = tmp_path / "datasets"
    settings.identity_db_path = tmp_path / "identity.sqlite3"
    settings.log_dir = tmp_path / "logs"
    settings.dataset_root.mkdir(parents=True)
    settings.backend = "mock"
    settings.extra["preview_pose_enabled"] = False
    settings.capture.min_free_disk_minutes = 0
    return settings


@pytest.fixture
def session(config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> SessionService:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    service = SessionService.open(config)
    auth = AuthViewModel(service)
    assert auth.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    return service


@pytest.fixture
def projects(session: SessionService) -> ProjectsViewModel:
    viewmodel = ProjectsViewModel(session, InlineRunner())
    viewmodel.reload_projects()
    assert viewmodel.create_project("Squat")
    # Two participants: with only one there is nothing to get wrong.
    assert viewmodel.create_participant()
    assert viewmodel.create_participant()
    return viewmodel


@pytest.fixture
def capture(session: SessionService):
    viewmodel = CaptureViewModel(session)
    yield viewmodel
    viewmodel.disconnect()


def _fold(text: str) -> str:
    """Turkish letters folded, so a test does not depend on casing rules."""
    return text.lower().replace("\u0131", "i").replace("\u0130", "i")


def _codes(projects: ProjectsViewModel) -> dict[str, str]:
    return {row.code: row.participant_id for row in projects.participants.value}


def _record(capture: CaptureViewModel, monkeypatch, *, frames: int = 4):
    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline:
        capture.refresh()
        if capture.metrics.value.connected:
            break
        time.sleep(0.02)
    assert capture.metrics.value.connected
    # Who the recording is of, before it starts. Recording without this is
    # refused now - see ``choose_subject``.
    choose_subject(capture, monkeypatch)
    choose_subject(capture, monkeypatch)
    if not capture.start_recording():
        return None
    deadline = time.time() + 15.0
    while capture.metrics.value.recorded_frames < frames and time.time() < deadline:
        time.sleep(0.02)
        capture.refresh()
    taken = []
    capture.take_finished.subscribe(taken.append)
    capture.stop_recording()
    return taken[0] if taken else None


# ------------------------------------------------------------------- target
def test_the_take_is_written_to_the_selected_participant(
    projects: ProjectsViewModel, capture: CaptureViewModel, session: SessionService
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    assert set(codes) == {"P0001", "P0002"}
    projects.select_participant(codes["P0002"])

    capture.refresh_target()
    assert capture.target.value.participant_code == "P0002"

    take = _record(capture, monkeypatch)
    assert take is not None
    assert take.participant_id == codes["P0002"]

    workspace = session.workspace
    listed = workspace.list_takes(codes["P0002"])
    assert [t.take_id for t in listed] == [take.take_id]
    assert workspace.list_takes(codes["P0001"]) == []


def test_without_a_selection_recording_is_refused(
    projects: ProjectsViewModel, capture: CaptureViewModel, session: SessionService
, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nobody's folder is chosen for them.

    Defaulting to the first participant and announcing it was the previous
    answer, and on 20 September it was not enough: a warning card is read
    afterwards, while the folder name is written the instant recording starts
    and nothing later moves it. Which person a take belongs to is a decision
    somebody makes before the camera rolls.
    """
    session.select_participant("")
    assert session.selected_participant_id == ""
    seen = []
    capture.message.subscribe(seen.append)
    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline and not capture.metrics.value.connected:
        time.sleep(0.02)
        capture.refresh()

    choose_subject(capture, monkeypatch)

    assert capture.start_recording() is False
    refused = [m for m in seen if m.code == "capture_refused"]
    assert refused, "a refusal has to be said, not just returned"
    assert "katilimci" in _fold(refused[-1].headline)
    assert "Projeler" in refused[-1].detail
    # And nothing was created anywhere to make it possible.
    for code in _codes(projects).values():
        assert session.workspace.list_takes(code) == []


def test_the_target_cannot_be_changed_while_a_take_is_open(
    projects: ProjectsViewModel, capture: CaptureViewModel, session: SessionService
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0001"])
    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline and not capture.metrics.value.connected:
        time.sleep(0.02)
        capture.refresh()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    try:
        seen = []
        capture.message.subscribe(seen.append)
        assert capture.choose_target(codes["P0002"]) is False
        assert "target_locked_while_recording" in [m.code for m in seen]
        assert session.selected_participant_id == codes["P0001"]
    finally:
        capture.stop_recording()


def test_opening_another_project_drops_the_participant_selection(
    projects: ProjectsViewModel, session: SessionService
) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0002"])
    assert session.selected_participant_id
    assert projects.create_project("Deadlift")
    assert session.selected_participant_id == ""
    assert session.target().is_set is False


# --------------------------------------------------------------------- mode
def test_the_profile_is_what_defines_a_mode() -> None:
    base = AppConfig().capture
    raw = profile_for_mode(base, RAW_ONLY)
    live = profile_for_mode(base, LIVE_SKELETON)
    assert mode_of_profile(raw) == RAW_ONLY
    assert raw.enable_body_tracking is False and raw.store_skeleton is False
    assert mode_of_profile(live) == LIVE_SKELETON
    assert live.enable_body_tracking is True and live.store_skeleton is True
    # Everything else is untouched: the mode is one decision, not a settings copy.
    assert live.fps == base.fps and live.resolution == base.resolution


def test_choosing_a_mode_while_connected_is_not_called_effective(
    projects: ProjectsViewModel, capture: CaptureViewModel
) -> None:
    assert capture.connect()
    capture.refresh()
    assert capture.active_mode.value == RAW_ONLY

    seen = []
    capture.message.subscribe(seen.append)
    assert capture.set_mode(LIVE_SKELETON)
    assert capture.mode.value == LIVE_SKELETON
    # The camera still has the old profile, and the screen must say so.
    assert capture.active_mode.value == RAW_ONLY
    assert capture.mode_pending.value is True
    assert "mode_needs_reconnect" in [m.code for m in seen]


def test_applying_the_mode_reconnects_and_reaches_the_recorded_take(
    projects: ProjectsViewModel, capture: CaptureViewModel
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0001"])
    assert capture.connect()
    assert capture.set_mode(LIVE_SKELETON)
    assert capture.apply_mode()
    capture.refresh()
    assert capture.active_mode.value == LIVE_SKELETON
    assert capture.mode_pending.value is False
    assert capture.service.active_profile.enable_body_tracking is True

    take = _record(capture, monkeypatch)
    assert take is not None
    # The metadata the take carries is the profile the backend really ran.
    assert take.capture_profile.enable_body_tracking is True
    assert take.capture_profile.store_skeleton is True


def test_the_default_stays_the_minimal_raw_recording(
    projects: ProjectsViewModel, capture: CaptureViewModel
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0001"])
    take = _record(capture, monkeypatch)
    assert take is not None
    assert take.capture_profile.enable_body_tracking is False
    assert take.capture_profile.store_skeleton is False


def test_the_mode_cannot_be_changed_while_recording(
    projects: ProjectsViewModel, capture: CaptureViewModel
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0001"])
    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline and not capture.metrics.value.connected:
        time.sleep(0.02)
        capture.refresh()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    try:
        seen = []
        capture.message.subscribe(seen.append)
        assert capture.set_mode(LIVE_SKELETON) is False
        assert "mode_locked_while_recording" in [m.code for m in seen]
        assert capture.mode.value == RAW_ONLY
    finally:
        capture.stop_recording()


# ---------------------------------------------------------------- stop once
def test_a_second_stop_does_not_finalise_the_take_twice(
    projects: ProjectsViewModel, capture: CaptureViewModel
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0001"])
    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline and not capture.metrics.value.connected:
        time.sleep(0.02)
        capture.refresh()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    finished = []
    capture.take_finished.subscribe(finished.append)
    assert capture.stop_recording() is True
    assert capture.stop_recording() is False
    assert len(finished) == 1


def test_the_status_reading_names_the_phase_and_the_owner(
    projects: ProjectsViewModel, capture: CaptureViewModel
, monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _codes(projects)
    projects.select_participant(codes["P0002"])
    capture.refresh()
    assert capture.status.value.phase is RecordingPhase.IDLE

    assert capture.connect()
    deadline = time.time() + 10.0
    while time.time() < deadline and not capture.metrics.value.connected:
        time.sleep(0.02)
        capture.refresh()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    try:
        capture.refresh()
        status = capture.status.value
        assert status.phase is RecordingPhase.RECORDING
        assert status.is_open is True
        assert "P0002" in status.target_text
    finally:
        capture.stop_recording()
    capture.refresh()
    assert capture.status.value.phase is RecordingPhase.IDLE
    assert capture.status.value.is_open is False
