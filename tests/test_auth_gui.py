"""Offscreen tests for the authenticated first-run and coach workflows."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from kinecapture.core.config import AppConfig
from kinecapture.gui.admin import ManageUsersDialog
from kinecapture.gui.auth import RegistrationDialog
from kinecapture.gui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path):
    config = AppConfig(
        dataset_root=tmp_path / "data",
        log_dir=tmp_path / "logs",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    window = MainWindow(config)
    window.resize(1120, 700)
    yield window
    window.close()
    window.deleteLater()


def complete_setup(window: MainWindow):
    fields = window._auth_page._setup_fields
    fields.line("first_name").setText("Sistem")
    fields.line("last_name").setText("Sahibi")
    fields.line("title").setText("Koordinatör")
    fields.line("username").setText("admin")
    fields.password.setText("owner-password")
    fields.password_confirmation.setText("owner-password")
    window._auth_page._create_owner()
    return window.state.current_user


def test_first_run_shows_setup_and_keeps_workspace_gated(window, qapp) -> None:
    assert window.state.identity.needs_initial_setup
    assert window._root_stack.currentWidget() is window._auth_page
    assert window._auth_page._stack.currentWidget() is window._auth_page._setup
    window.navigate("capture")
    # Internal pages may prepare offscreen, but the visible surface remains auth.
    assert window._root_stack.currentWidget() is window._auth_page
    assert not window.grab().isNull()


def test_owner_setup_transitions_to_workspace(window, qapp) -> None:
    user = complete_setup(window)
    qapp.processEvents()
    assert user is not None and user.is_owner
    assert window._root_stack.currentWidget() is window._shell
    assert window._current_key == "projects"
    assert window._auth_page._setup_fields.password.text() == ""


def test_login_password_show_toggle(window) -> None:
    complete_setup(window)
    window.state.logout()
    window._auth_page.refresh_mode()
    password = window._auth_page._password
    assert password.echoMode() == password.EchoMode.Password
    window._auth_page._show_password.setChecked(True)
    assert password.echoMode() == password.EchoMode.Normal


def test_registration_has_field_local_validation(window) -> None:
    owner = complete_setup(window)
    dialog = RegistrationDialog(window.state, actor=owner, parent=window)
    dialog._create()
    assert dialog.fields.rows["first_name"]._error.isVisibleTo(dialog)
    assert dialog.created_user is None
    dialog.close()


def test_self_registration_creates_only_normal_user(window) -> None:
    complete_setup(window)
    dialog = RegistrationDialog(window.state, parent=window)
    dialog.fields.line("first_name").setText("Ayşe")
    dialog.fields.line("last_name").setText("Koç")
    dialog.fields.line("username").setText("ayse")
    dialog.fields.password.setText("coach-password")
    dialog.fields.password_confirmation.setText("coach-password")
    dialog._create()
    assert dialog.created_user is not None
    assert not dialog.created_user.is_owner


def test_owner_management_is_visible_only_to_owner(window) -> None:
    owner = complete_setup(window)
    window._context.refresh()
    assert window._context._manage_users_action.isVisible()
    dialog = ManageUsersDialog(window.state, window)
    assert dialog.windowTitle() == "Kullanıcılar ve Erişimler"
    assert "Sistem Sahibi" in dialog._table.item(0, 0).text()
    dialog.close()

    normal = window.state.identity.create_user(
        owner,
        first_name="Normal",
        last_name="Kullanıcı",
        title="",
        username="normal",
        password="normal-password",
    )
    window.state.logout()
    window.state.activate_user(normal)
    window._context.refresh()
    assert not window._context._manage_users_action.isVisible()


def test_participant_page_contains_only_minimal_flow(window) -> None:
    complete_setup(window)
    page = window._pages["participants"]
    assert page.title == "Katılımcılar"
    for removed in (
        "_height",
        "_mass",
        "_dominant",
        "_operator",
        "_consent",
        "_session_list",
        "_participant_notes",
    ):
        assert not hasattr(page, removed)
    assert page._start.text() == "Kayda Başla"
    assert hasattr(page, "_search")


def test_context_bar_is_user_project_participant_camera_disk(window) -> None:
    complete_setup(window)
    window._context.refresh()
    assert set(window._context._chips) == {
        "project",
        "participant",
        "camera",
        "disk",
    }
    assert "Sistem Sahibi" in window._context._user_button.text()


def test_unauthorized_last_project_is_never_opened(window) -> None:
    owner = complete_setup(window)
    owned = window.state.create_project("Owner only")
    normal = window.state.identity.create_user(
        owner,
        first_name="N",
        last_name="U",
        title="",
        username="normal",
        password="normal-password",
    )
    window.state.logout()
    window.state.config.last_project_path = owned.root
    window.state.activate_user(normal)
    window._authentication_completed(normal)
    assert window.state.workspace is None
    assert window._current_key == "projects"


def test_single_project_auto_opens_but_multiple_projects_require_selection(window) -> None:
    owner = complete_setup(window)
    first = window.state.create_project("First")
    window.state.logout()
    window.state.activate_user(owner)
    window._authentication_completed(owner)
    assert window.state.project.project_id == first.project.project_id
    assert window._current_key == "participants"

    window.state.create_project("Second")
    window.state.logout()
    window.state.activate_user(owner)
    window._authentication_completed(owner)
    assert window.state.workspace is None
    assert window._current_key == "projects"


def test_normal_user_does_not_see_filesystem_project_controls(window) -> None:
    owner = complete_setup(window)
    normal = window.state.identity.create_user(
        owner,
        first_name="N",
        last_name="U",
        title="",
        username="normal",
        password="normal-password",
    )
    window.state.logout()
    window.state.activate_user(normal)
    page = window._pages["projects"]
    page.on_activated()
    assert page.title == "Projeler"
    assert not page._import_button.isVisibleTo(page)
    assert not page._root_button.isVisibleTo(page)


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_auth_and_workspace_paint_at_minimum_size(window, qapp, theme) -> None:
    window.state.set_theme(theme)
    window.resize(window.minimumSize())
    window.show()
    qapp.processEvents()
    assert not window.grab().isNull()
    complete_setup(window)
    qapp.processEvents()
    assert not window.grab().isNull()
