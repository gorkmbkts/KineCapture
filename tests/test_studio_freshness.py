"""Lists that are current, and a diagnostics window that says what happened.

Two findings from the 15 September audit.

*An empty project list after signing back in.* The Projects screen had loaded
itself before authentication - which can only produce an empty list - and kept
that as its answer. Creating a throwaway project was the only way to make the
real one reappear.

*Diagnostics stuck on "henüz çalıştırılmadı".* ``collect_diagnostics`` was
called with a positional argument it does not take; the ``TypeError`` was
swallowed and the failure was shown as an idle state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.studio.services.inspectors import diagnostics_sections
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from kinecapture.studio.viewmodels.tasks import InlineRunner


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
    return SessionService.open(config)


def _sign_in(session: SessionService) -> None:
    auth = AuthViewModel(session)
    if session.needs_initial_setup:
        assert auth.create_owner(
            first_name="Ada", last_name="Lovelace", title="",
            username="ada", password="kinecapture1", password_confirm="kinecapture1",
        )
    else:
        assert auth.sign_in("ada", "kinecapture1")


# ------------------------------------------------------------ project lists
def test_a_list_loaded_before_signing_in_is_not_an_answer(
    session: SessionService,
) -> None:
    projects = ProjectsViewModel(session, InlineRunner())
    projects.reload_projects()
    assert projects.projects.value == ()
    # The important part: this is "signed out", not "no projects".
    assert projects.state.value == "signed_out"
    assert projects.loaded_for is None


def test_signing_in_makes_the_existing_project_appear(
    session: SessionService,
) -> None:
    _sign_in(session)
    projects = ProjectsViewModel(session, InlineRunner())
    projects.reload_projects()
    assert projects.create_project("UX Denetimi 14 Eylül")
    project_id = projects.selected_project.value
    assert project_id

    # A fresh application run: everything is rebuilt, and the screen is
    # activated once before authentication finishes.
    session.sign_out()
    reopened = ProjectsViewModel(session, InlineRunner())
    reopened.reload_projects()
    assert reopened.state.value == "signed_out"

    _sign_in(session)
    reopened.reload_projects()
    assert [row.project_id for row in reopened.projects.value] == [project_id]
    assert reopened.state.value == "ready"


def test_an_account_with_no_projects_says_so_and_offers_the_next_step(
    session: SessionService,
) -> None:
    _sign_in(session)
    projects = ProjectsViewModel(session, InlineRunner())
    projects.reload_projects()
    assert projects.state.value == "empty"
    assert "Yeni proje" in projects.summary.value


def test_refresh_reloads_the_whole_screen_not_just_the_open_project(
    session: SessionService,
) -> None:
    _sign_in(session)
    projects = ProjectsViewModel(session, InlineRunner())
    projects.reload_projects()
    assert projects.create_project("Squat")

    # Something else registers a project - another window, another session.
    other = ProjectsViewModel(session, InlineRunner())
    other.reload_projects()
    assert other.create_project("Deadlift")

    assert len(projects.projects.value) == 1
    projects.refresh_all()
    assert len(projects.projects.value) == 2


# -------------------------------------------------------------- diagnostics
def test_a_diagnostics_failure_is_not_shown_as_not_run() -> None:
    idle = diagnostics_sections(None, state="idle")
    failed = diagnostics_sections(None, state="failed", error="TypeError: boom")
    running = diagnostics_sections(None, state="running")

    assert "henüz çalıştırılmadı" in idle[0].rows[0].value
    assert failed[0].rows[0].value == "başarısız"
    assert failed[0].rows[0].level == "error"
    assert "TypeError: boom" in " ".join(row.value for row in failed[0].rows)
    assert running[0].rows[0].value == "çalışıyor"
    # Whatever else changes, these three must never read the same.
    assert len({s[0].rows[0].value for s in (idle, failed, running)}) == 3


def test_collect_diagnostics_is_called_the_way_it_is_declared(
    config: AppConfig,
) -> None:
    """The exact call the shell makes, so a signature change fails here."""
    from kinecapture.core.diagnostics import collect_diagnostics
    from kinecapture.domain.enums import BackendKind

    report = collect_diagnostics(
        dataset_root=config.dataset_root, backend=BackendKind("mock")
    )
    sections = diagnostics_sections(report, state="done")
    assert sections[0].title == "Genel"
    assert sections[1].rows, "a real report has checks in it"
