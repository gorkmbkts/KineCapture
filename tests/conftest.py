"""Shared fixtures.

Two rules the whole suite depends on:

* **No hardware.** Every test runs against the synthetic backend. A connected
  ZED camera must never be required, and must never be opened.
* **No real time.** Recording tests drive the pipeline with a deterministic
  mock backend that produces frames as fast as it is asked, so a test never
  waits on a wall clock.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest

# Qt must not try to open a window during tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.logging import setup_logging  # noqa: E402
from kinecapture.dataset.workspace import ProjectWorkspace  # noqa: E402
from kinecapture.domain.enums import ConsentStatus  # noqa: E402
from kinecapture.domain.project import Participant, Session  # noqa: E402

setup_logging("WARNING", None)


@pytest.fixture(autouse=True)
def isolated_user_state(tmp_path, monkeypatch):
    """Never let a test write to the real user's settings file.

    ``AppState`` persists preferences whenever the theme or the open project
    changes, which the GUI tests do constantly. Without this redirection those
    writes land in ``~/.kinecapture/user_state.yaml`` and a test's temporary
    dataset root becomes the user's configured one - user data modified by a
    test run, which is exactly what this project promises never to do.
    """
    state_dir = tmp_path / "_user_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "user_state.yaml"
    for module in ("kinecapture.core.config", "kinecapture.gui.pages.settings"):
        monkeypatch.setattr(f"{module}.USER_STATE_PATH", state_path, raising=False)
    monkeypatch.setattr(
        "kinecapture.core.config.USER_STATE_DIR", state_dir, raising=False
    )
    # AppConfig resolves the identity DB from LOCALAPPDATA at construction
    # time. Redirect it too: authentication tests must never create or modify
    # the real per-user database.
    app_data = tmp_path / "_local_app_data"
    monkeypatch.setenv("LOCALAPPDATA", str(app_data))
    yield state_path


def authenticate_state(state, workspace=None, *, open_workspace=True):
    """Create/login an isolated owner and optionally register a workspace."""
    password = "pytest-password"
    if state.identity.needs_initial_setup:
        user = state.identity.create_initial_owner(
            first_name="Py",
            last_name="Test",
            title="",
            username="pytest-owner",
            password=password,
        )
    else:
        user = state.identity.authenticate("pytest-owner", password)
    state.activate_user(user)
    if workspace is not None:
        try:
            state.identity.register_project(user, workspace)
        except Exception as exc:
            if getattr(exc, "code", "") != "project_already_registered":
                raise
        if open_workspace:
            state.open_project(workspace.root)
    return user


@pytest.fixture
def dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "datasets"
    root.mkdir()
    return root


@pytest.fixture
def workspace(dataset_root: Path) -> ProjectWorkspace:
    return ProjectWorkspace.create(dataset_root, "Test Projesi")


@pytest.fixture
def participant(workspace: ProjectWorkspace) -> Participant:
    return workspace.create_participant()


@pytest.fixture
def session(workspace: ProjectWorkspace, participant: Participant) -> Session:
    return workspace.create_session(
        participant.participant_id,
        operator="pytest",
        consent=ConsentStatus.GRANTED,
    )


@pytest.fixture
def mock_backend() -> Iterator[MockCameraBackend]:
    """A small, fast, fully deterministic synthetic camera."""
    backend = MockCameraBackend(
        width=160, height=120, fps=30, seed=42, real_time=False
    )
    yield backend
    backend.disconnect()


def paced_backend(**kwargs) -> MockCameraBackend:
    """A synthetic camera that paces itself to a (fast) frame rate.

    Unpaced, the mock produces frames as fast as the CPU allows, which floods
    the bounded recording queue and manufactures capture loss that has nothing
    to do with what is being tested. Pacing at a high rate keeps recording tests
    quick *and* loss-free, so a dropped frame in a test means a real defect.
    """
    params: dict = {
        "width": 96,
        "height": 72,
        "fps": 120,
        "real_time": True,
        "seed": 42,
    }
    params.update(kwargs)
    return MockCameraBackend(**params)


def record_take(service, workspace, session, *, frames: int = 30, **kwargs):
    """Drive a recording to completion without waiting on real time.

    The service's own threads do the work; this only blocks until the writer
    has actually persisted ``frames`` frames, with a generous ceiling so a
    genuine hang fails the test instead of hanging the suite.
    """
    import time

    service.start_preview()
    take = service.start_recording(workspace, session, **kwargs)
    deadline = time.time() + 20.0
    while service.recorded_frame_count < frames and time.time() < deadline:
        time.sleep(0.005)
    assert service.recorded_frame_count >= frames, (
        f"writer only persisted {service.recorded_frame_count}/{frames} frames"
    )
    return service.stop_recording()
