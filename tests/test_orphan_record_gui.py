"""Getting rid of a project whose folder is no longer on disk.

Every project here is created inside ``tmp_path`` and the identity database is
redirected by ``isolated_user_state``, so nothing in this file can see a real
project. The folder each test "loses" is one it created itself.

The risk this covers is a wording risk. The two operations share a window, and
a window that says "everything will be permanently deleted" over an operation
that deletes nothing teaches the admin to ignore that sentence - which is the
sentence that has to stop them next time.
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.gui.pages.projects import ProjectsPage  # noqa: E402
from kinecapture.gui.state import AppState  # noqa: E402
from kinecapture.gui.theme import get_theme  # noqa: E402
from kinecapture.gui.widgets.delete_project_dialog import (  # noqa: E402
    DeleteProjectDialog,
)

_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def owner_state(qapp, tmp_path, isolated_user_state):
    root = tmp_path / "datasets"
    root.mkdir()
    state = AppState(AppConfig(dataset_root=root, backend="mock"))
    owner = state.identity.create_initial_owner(
        first_name="Sys",
        last_name="Owner",
        title="",
        username="owner",
        password="owner-password",
    )
    state.activate_user(owner)
    return state, owner, root


@pytest.fixture
def orphaned(owner_state):
    """A registered project whose folder has been moved away behind our back."""
    state, owner, _root = owner_state
    workspace = state.create_project("Taşınmış Proje")
    record_id = workspace.project.project_id
    state.close_project()
    shutil.rmtree(workspace.root)
    assert not workspace.root.exists()

    page = ProjectsPage(state)
    page.on_activated()
    for row in range(page._list.count()):
        item = page._list.item(row)
        if item.data(_ID_ROLE) == record_id:
            page._list.setCurrentItem(item)
            break
    else:  # pragma: no cover - the record must still be listed
        raise AssertionError("the orphan record vanished from the list")
    return state, owner, page, record_id, workspace


def run_dialog(page, *, typed, start=True):
    """Drive the confirmation window without a human, and hand it back."""
    captured: dict = {}
    real_exec = DeleteProjectDialog.exec

    def fake_exec(dialog):
        captured["dialog"] = dialog
        dialog.confirm_field.setText(typed)
        if start and dialog.delete_button.isEnabled():
            dialog.delete_button.click()
            worker = dialog._worker
            if worker is not None:
                worker.wait(60_000)
                QApplication.processEvents()
        return (
            QDialog.DialogCode.Accepted
            if dialog.outcome is not None
            else QDialog.DialogCode.Rejected
        )

    DeleteProjectDialog.exec = fake_exec
    try:
        page._delete_selected()
    finally:
        DeleteProjectDialog.exec = real_exec
    return captured.get("dialog")


# ------------------------------------------------------------ the wording


def test_the_window_says_nothing_will_be_deleted(orphaned) -> None:
    _state, _owner, page, _record_id, _workspace = orphaned
    dialog = run_dialog(page, typed="", start=False)

    assert dialog is not None and dialog.orphan
    assert dialog.windowTitle() == "Yetim proje kaydını kaldır"
    assert dialog.delete_button.text() == "Kaydı listeden kaldır"

    warning = dialog.warning.text()
    assert "BULUNAMADI" in warning
    assert "hiçbir dosyayı silmez" in warning
    assert "GERİ ALINAMAZ" not in warning, "this is not the destructive wording"
    assert "kalıcı olarak silinir" not in warning


def test_it_says_what_to_do_if_the_folder_was_only_moved(orphaned) -> None:
    """The recoverable case must be named before the record is thrown away."""
    _state, _owner, page, _record_id, _workspace = orphaned
    dialog = run_dialog(page, typed="", start=False)
    assert "taşındıysa" in dialog.warning.text()


def test_the_missing_path_is_shown_in_full(orphaned) -> None:
    _state, _owner, page, _record_id, workspace = orphaned
    dialog = run_dialog(page, typed="", start=False)
    assert dialog.path_box.toPlainText() == str(workspace.root)
    assert dialog.path_box.isReadOnly()


def test_the_normal_delete_window_keeps_the_destructive_wording(
    owner_state, qapp
) -> None:
    """The contrast is the point: the two must not read the same."""
    state, _owner, _root = owner_state
    workspace = state.create_project("Duran Proje")
    page = ProjectsPage(state)
    page.on_activated()
    for row in range(page._list.count()):
        item = page._list.item(row)
        if item.data(_ID_ROLE) == workspace.project.project_id:
            page._list.setCurrentItem(item)
            break

    dialog = run_dialog(page, typed="", start=False)
    assert dialog is not None and not dialog.orphan
    assert dialog.windowTitle() == "Projeyi kalıcı olarak sil"
    assert dialog.delete_button.text() == "Kalıcı olarak sil"
    assert "GERİ ALINAMAZ" in dialog.warning.text()


# --------------------------------------------------------------- the gate


def test_the_name_still_has_to_be_typed(orphaned) -> None:
    _state, _owner, page, record_id, _workspace = orphaned
    dialog = run_dialog(page, typed="Taşınmış", start=False)

    assert not dialog.delete_button.isEnabled()
    assert "aynı değil" in dialog._status.text()

    dialog.confirm_field.setText("Taşınmış Proje")
    assert dialog.delete_button.isEnabled()


def test_cancelling_leaves_the_record_exactly_where_it_was(orphaned) -> None:
    state, owner, page, record_id, _workspace = orphaned
    before = len(state.list_accessible_projects())

    run_dialog(page, typed="", start=False)

    assert len(state.list_accessible_projects()) == before
    assert any(
        record.project_id == record_id
        for record in state.list_accessible_projects()
    )


def test_a_normal_user_cannot_reach_it_at_all(qapp, tmp_path, isolated_user_state):
    """Owner-only, enforced in the service and not only by a hidden button."""
    from kinecapture.identity.service import AuthorizationError

    root = tmp_path / "datasets"
    root.mkdir()
    state = AppState(AppConfig(dataset_root=root, backend="mock"))
    owner = state.identity.create_initial_owner(
        first_name="Sys", last_name="Owner", title="",
        username="owner", password="owner-password",
    )
    normal = state.identity.create_user(
        owner,
        first_name="Normal", last_name="User", title="",
        username="normal", password="normal-password",
    )
    state.activate_user(owner)
    workspace = state.create_project("Kaybolan Proje")
    project_id = workspace.project.project_id
    state.close_project()
    shutil.rmtree(workspace.root)

    state.activate_user(normal)
    page = ProjectsPage(state)
    page.on_activated()
    assert not page._delete_button.isVisible()

    with pytest.raises(AuthorizationError):
        state.deletion.forget_orphan(normal, project_id)
    assert any(
        record.project_id == project_id
        for record in state.identity.list_projects(owner)
    ), "the record survived the refusal"


# ------------------------------------------------------------- the outcome


def test_confirming_removes_the_row_and_nothing_else(orphaned) -> None:
    state, owner, page, record_id, _workspace = orphaned
    others = [
        record.project_id
        for record in state.list_accessible_projects()
        if record.project_id != record_id
    ]
    state.create_project("Kalacak Proje")
    page.on_activated()
    for row in range(page._list.count()):
        item = page._list.item(row)
        if item.data(_ID_ROLE) == record_id:
            page._list.setCurrentItem(item)
            break

    dialog = run_dialog(page, typed="Taşınmış Proje")
    assert dialog is not None and dialog.outcome is not None

    remaining = {r.project_id for r in state.list_accessible_projects()}
    assert record_id not in remaining
    assert all(other in remaining for other in others)
    assert any(r.name == "Kalacak Proje" for r in state.list_accessible_projects())


def test_the_list_refreshes_without_a_restart(orphaned) -> None:
    _state, _owner, page, record_id, _workspace = orphaned
    run_dialog(page, typed="Taşınmış Proje")
    QApplication.processEvents()

    listed = {page._list.item(row).data(_ID_ROLE) for row in range(page._list.count())}
    assert record_id not in listed


def test_the_audit_log_calls_it_a_record_removal(orphaned) -> None:
    """A reader of the log must be able to tell whether files were destroyed."""
    state, owner, page, record_id, _workspace = orphaned
    run_dialog(page, typed="Taşınmış Proje")

    with state.identity.database.connection() as connection:
        kinds = [
            row["event_type"]
            for row in connection.execute("SELECT event_type FROM audit_log")
        ]
    assert "project_record_removed" in kinds
    assert "project_deleted" not in kinds, (
        "the log must say whether files were destroyed"
    )


# ------------------------------------------------------------- the geometry


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_the_window_fits_the_smallest_supported_screen(
    qapp, orphaned, theme_name
) -> None:
    from kinecapture.gui.theme import build_stylesheet

    _state, _owner, page, _record_id, _workspace = orphaned
    qapp.setStyleSheet(build_stylesheet(get_theme(theme_name)))
    dialog = run_dialog(page, typed="", start=False)
    dialog.show()
    QApplication.processEvents()

    assert dialog.minimumSizeHint().width() <= 1120 - 40
    assert dialog.minimumSizeHint().height() <= 700 - 60
    assert dialog.warning.wordWrap(), "the long warning must not be clipped"
    assert not dialog.grab().isNull()
    dialog.hide()
