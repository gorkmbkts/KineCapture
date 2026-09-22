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
from kinecapture.domain.project import CaptureProfile, Participant, Session  # noqa: E402

setup_logging("WARNING", None)


@pytest.fixture(scope="session", autouse=True)
def isolated_session_state(tmp_path_factory):
    """Module-scoped GUI fixtures run BEFORE function-scoped isolation.

    Keep a second outer boundary so their setup and teardown can never write
    real preferences/identity data. Individual tests still get their own path.
    """
    root = tmp_path_factory.mktemp("session_state")
    with pytest.MonkeyPatch.context() as patch:
        for module in ("kinecapture.core.config", "kinecapture.gui.pages.settings"):
            patch.setattr(f"{module}.USER_STATE_PATH", root / "user_state.yaml", raising=False)
        patch.setattr("kinecapture.core.config.USER_STATE_DIR", root, raising=False)
        patch.setenv("LOCALAPPDATA", str(root / "local_app_data"))
        yield root


@pytest.fixture(autouse=True)
def isolated_user_state(tmp_path, monkeypatch, isolated_session_state):
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


def enter_the_workspace(window, app=None, *, participant: bool = True):
    """Get a signed-in window past the project and participant gates.

    From 20 September every screen but Projeler needs a project open in this
    session, and Yakalama additionally needs the participant whose folder a
    take would be written to. A test that is about a layout, a toast or a
    loading state still has to pass through the same door the product puts
    everybody through, so this opens it - explicitly, which is the point of
    the gate.

    The workspace is attached to the session directly rather than through the
    Projeler screen: creating a project there also starts an index rescan, and
    a rescan landing in the middle of a layout test replaces rows the test had
    just put on screen. The tests that are *about* the gate use the real
    screen; these only need the door open.

    Returns the workspace.
    """
    import time

    session = window.viewmodel.session
    workspace = ProjectWorkspace.create(session.config.dataset_root, "Test Projesi")
    session.workspace = workspace
    if participant:
        session.selected_participant_id = workspace.create_participant().participant_id
    if app is not None:
        # Let the screens finish reading the (empty) new project before the
        # test puts anything of its own on them. A scan landing afterwards
        # would replace the test's rows with the project's none.
        deadline = time.time() + 2.0
        while time.time() < deadline:
            app.processEvents()
    return workspace


def show_page_directly(window, key: str, app=None):
    """Put a page on screen without a project, for tests about the page itself.

    From 20 September ``navigate`` refuses every screen but Projeler until a
    project is open. A test about how a list renders is not a test about that
    rule, and giving it a real project makes the screen load the project's own
    (empty) rows over the ones the test just put there. Setting the observable
    the shell is bound to shows the page and skips the rule, which is exactly
    what such a test wants and nothing more.
    """
    window.viewmodel.active_page.set(key)
    if app is not None:
        app.processEvents()
    return window.page(key)


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
        capture_profile=CaptureProfile.legacy(),
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


class _SolePersonPreview:
    """The light pose preview with exactly one person, in a known box.

    Enough for the one thing most capture tests need from it: something for
    the operator's click to land on.
    """

    class _Person:
        def __init__(self, box) -> None:
            import numpy as np

            self.bbox = np.asarray(box, dtype=np.float32).reshape(2, 2)
            self.points = np.zeros((33, 2), dtype=np.float32)
            self.confidence = np.ones(33, dtype=np.float32)

    def __init__(self, packet) -> None:  # noqa: ANN001 - FramePacket
        self.packet = packet
        self.people = (self._Person([[10, 10], [200, 400]]),)

    def anchor(self, x: float, y: float) -> dict:
        from kinecapture.preview.pose import PosePreview

        return PosePreview.anchor(self, x, y)  # the real rule, not a copy


def choose_subject(capture, monkeypatch, *, point=(60.0, 120.0)) -> None:
    """Pick the person in the frame, the way an operator now has to.

    Recording without a selection is refused: the joint arrays are written at
    processing time from the body that was marked, so a take with nobody
    marked comes back NaN from end to end. Two real ZED recordings were lost
    to that on 17 September, which is why the refusal exists and why every
    test that records has to answer the question first.
    """
    import time as _time

    deadline = _time.time() + 10.0
    packet = capture.service.latest_frame()
    while packet is None and _time.time() < deadline:
        _time.sleep(0.02)
        packet = capture.service.latest_frame()
    assert packet is not None, "no preview frame to pick a subject from"
    monkeypatch.setattr(
        capture.service, "pose_preview", lambda: _SolePersonPreview(packet)
    )
    assert capture.select_subject(*point)
