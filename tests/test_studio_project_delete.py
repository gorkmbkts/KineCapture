"""Deleting a project from the Studio, for real.

The dangerous half is ``kinecapture.dataset.deletion``, which has its own
tests. What is checked here is the part the Studio owns: that the action
exists at all (it did not, so a test project could be made and never removed),
that it goes through the guarded service rather than around it, that the open
project is let go before its folder disappears, and that a refusal is reported
instead of attempted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.viewmodels.auth import AuthViewModel  # noqa: E402
from kinecapture.studio.viewmodels.projects import ProjectsViewModel  # noqa: E402
from kinecapture.studio.viewmodels.tasks import InlineRunner  # noqa: E402


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    settings = AppConfig()
    settings.dataset_root = tmp_path / "datasets"
    settings.identity_db_path = tmp_path / "identity.sqlite3"
    settings.log_dir = tmp_path / "logs"
    settings.dataset_root.mkdir(parents=True)
    settings.backend = "mock"
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
    return viewmodel


def _make(projects: ProjectsViewModel, name: str) -> str:
    assert projects.create_project(name)
    row = next(r for r in projects.projects.value if r.name == name)
    return row.project_id


# --------------------------------------------------------------- preflight
def test_a_deletion_can_be_inspected_before_it_is_agreed_to(projects) -> None:
    """A confirmation that cannot say what will be erased is not consent."""
    project_id = _make(projects, "Silinecek")
    report = projects.deletion_preflight(project_id)
    assert report is not None
    assert report.ok is True
    assert report.resolved is not None
    assert report.resolved.exists()
    # Inspecting changes nothing.
    assert [r.project_id for r in projects.projects.value] == [project_id]


def test_the_preflight_refuses_a_target_that_is_not_a_project(
    projects, session, monkeypatch
) -> None:
    """The guard lives in the deletion service; this checks we ask it."""
    project_id = _make(projects, "Sahte")
    # Point the record at the dataset root itself - never a single project.
    root = Path(session.config.dataset_root)
    monkeypatch.setattr(
        session.identity,
        "authorize_project_deletion",
        lambda _actor, _pid: type(
            "Record", (), {"path": str(root), "name": "Sahte"}
        )(),
    )
    report = projects.deletion_preflight(project_id)
    assert report is not None
    assert report.ok is False
    assert report.reason


# ----------------------------------------------------------------- deleting
def test_deleting_removes_the_folder_and_the_record(projects, session) -> None:
    keep = _make(projects, "Kalacak")
    doomed = _make(projects, "Silinecek")
    folder = Path(
        next(r for r in projects.projects.value if r.project_id == doomed).path
    )
    assert folder.is_dir()

    seen = []
    projects.message.subscribe(seen.append)
    assert projects.delete_project(doomed) is True

    assert not folder.exists(), "the folder is still on disk"
    assert [r.project_id for r in projects.projects.value] == [keep]
    assert projects.deleting.value is False
    assert any(m.code == "project_deleted" for m in seen)


def test_deleting_the_open_project_lets_go_of_it_first(projects, session) -> None:
    """Otherwise the session holds a workspace whose folder has gone."""
    _keep = _make(projects, "Kalacak")
    doomed = _make(projects, "Açık olan")
    projects.open_project(doomed)
    assert session.workspace is not None
    assert projects.selected_project.value == doomed

    assert projects.delete_project(doomed) is True
    assert projects.selected_project.value != doomed
    # Whatever is open now, it is not the deleted one.
    if session.access is not None:
        assert session.access.project_id != doomed


def test_the_last_project_can_be_deleted_too(projects) -> None:
    only = _make(projects, "Tek proje")
    assert projects.delete_project(only) is True
    assert projects.projects.value == ()
    assert projects.state.value == "empty"


def test_a_failure_is_reported_and_the_list_is_rebuilt(
    projects, session, monkeypatch
) -> None:
    from kinecapture.core.errors import StorageError

    project_id = _make(projects, "Kilitli")
    seen = []
    projects.message.subscribe(seen.append)

    def boom(*_args, **_kwargs):
        raise StorageError("Klasör kullanımda.", code="delete_locked")

    monkeypatch.setattr(
        "kinecapture.dataset.deletion.ProjectDeletionService.delete", boom
    )
    assert projects.delete_project(project_id) is True
    assert projects.deleting.value is False, "the actions must not stay held"
    assert seen and seen[-1].severity.value == "error"
    # Nothing was removed, so it is still listed.
    assert [r.project_id for r in projects.projects.value] == [project_id]


def test_deleting_needs_somebody_signed_in(config, monkeypatch) -> None:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    service = SessionService.open(config)
    viewmodel = ProjectsViewModel(service, InlineRunner())
    assert viewmodel.delete_project("prj_whatever") is False
    assert viewmodel.deletion_preflight("prj_whatever") is None
