"""The delete flow as the user drives it, through the real Projects page.

Every project here is created inside ``tmp_path`` by the test itself. The
identity database is redirected by ``isolated_user_state``, so nothing in this
file can see - let alone delete - a real project.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.core.errors import ValidationError  # noqa: E402
from kinecapture.dataset.deletion import tombstone_root  # noqa: E402
from kinecapture.gui.pages.projects import ProjectsPage  # noqa: E402
from kinecapture.gui.state import AppState  # noqa: E402
from kinecapture.gui.widgets.delete_project_dialog import (  # noqa: E402
    DeleteProjectDialog,
)
from kinecapture.identity.service import AuthorizationError  # noqa: E402


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


def make_project(state, name="Silinecek Proje"):
    workspace = state.create_project(name)
    take = workspace.root / "participants" / "P0001" / "raw" / "chunk.bin"
    take.parent.mkdir(parents=True, exist_ok=True)
    take.write_bytes(b"\x00" * 8192)
    return workspace


def run_dialog(page, *, typed, start=True):
    """Open the delete dialog, type ``typed``, and optionally confirm."""
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


#: The list stores the project path in UserRole and the id one slot along.
_ID_ROLE = int(Qt.ItemDataRole.UserRole) + 1


def select(page, project_id):
    for row in range(page._list.count()):
        item = page._list.item(row)
        if item.data(_ID_ROLE) == project_id:
            page._list.setCurrentItem(item)
            return item
    raise AssertionError(f"{project_id} not in the list")


# ------------------------------------------------------------ visibility


def test_a_normal_user_never_sees_the_button(qapp, tmp_path, isolated_user_state):
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
    state.activate_user(normal)
    workspace = make_project(state)

    page = ProjectsPage(state)
    page.on_activated()
    qapp.processEvents()
    assert not page._delete_button.isVisible() or page._delete_button.isHidden()

    # ... and the service refuses even if the button is reached anyway.
    with pytest.raises(AuthorizationError):
        state.deletion.preflight(normal, workspace.project.project_id)


def test_the_owner_sees_the_button(owner_state, qapp):
    state, _owner, _root = owner_state
    make_project(state)
    page = ProjectsPage(state)
    page.on_activated()
    page.show()
    qapp.processEvents()
    assert page._delete_button.isVisible()
    page.hide()


# ------------------------------------------------------------ confirmation


def test_the_wrong_confirmation_text_is_a_complete_no_op(owner_state, qapp):
    state, _owner, root = owner_state
    workspace = make_project(state, "Doğru Ad")
    project_id = workspace.project.project_id
    page = ProjectsPage(state)
    page.on_activated()
    select(page, project_id)

    dialog = run_dialog(page, typed="Yanlış Ad")

    assert dialog is not None
    assert not dialog.delete_button.isEnabled()
    assert not dialog.started
    assert dialog.outcome is None
    assert workspace.project_file.is_file()
    assert state.identity.repository.get_project(project_id) is not None
    assert not tombstone_root(root).exists()


def test_cancelling_changes_nothing(owner_state, qapp):
    state, _owner, root = owner_state
    workspace = make_project(state)
    project_id = workspace.project.project_id
    page = ProjectsPage(state)
    page.on_activated()
    select(page, project_id)

    dialog = run_dialog(page, typed=workspace.project.name, start=False)

    assert dialog is not None
    assert dialog.delete_button.isEnabled(), "the name matched"
    assert not dialog.started, "but nothing was started"
    assert workspace.project_file.is_file()
    assert state.identity.repository.get_project(project_id) is not None


def test_the_dialog_shows_the_full_path_without_eliding_it(owner_state, qapp):
    state, _owner, _root = owner_state
    workspace = make_project(state)
    page = ProjectsPage(state)
    page.on_activated()
    select(page, workspace.project.project_id)

    dialog = run_dialog(page, typed="", start=False)
    assert dialog is not None
    assert dialog.path_box.toPlainText() == str(workspace.root)
    assert dialog.path_box.isReadOnly()
    assert "GERİ ALINAMAZ" in dialog.warning.text()
    assert "boşalır" in dialog.warning.text()


def test_a_second_click_cannot_start_a_second_deletion(owner_state, qapp):
    state, _owner, _root = owner_state
    workspace = make_project(state)
    calls: list[int] = []

    dialog = DeleteProjectDialog(
        state.theme,
        project_name="X",
        project_id="prj_x",
        project_path=workspace.root,
        work=lambda progress: calls.append(1),
    )
    dialog.confirm_field.setText("X")
    dialog.delete_button.click()
    dialog.delete_button.click()
    dialog.start()
    if dialog._worker is not None:
        dialog._worker.wait(30_000)
    qapp.processEvents()

    assert calls == [1]
    assert not dialog.cancel_button.isEnabled(), (
        "an uninterruptible delete must not offer a Cancel button"
    )


# ------------------------------------------------------------- the real thing


def test_deleting_removes_the_project_and_clears_every_reference(owner_state, qapp):
    state, _owner, root = owner_state
    workspace = make_project(state)
    project_id = workspace.project.project_id
    project_root = workspace.root
    state.open_project(project_root)
    assert state.has_project

    page = ProjectsPage(state)
    page.on_activated()
    select(page, project_id)

    dialog = run_dialog(page, typed=workspace.project.name)

    assert dialog is not None and dialog.error is None
    assert dialog.outcome is not None and dialog.outcome.complete
    assert not project_root.exists()
    assert state.identity.repository.get_project(project_id) is None
    assert project_id not in {p.project_id for p in state.list_accessible_projects()}
    assert not state.has_project, "the active project must be released"
    assert state.config.last_project_path is None
    assert not tombstone_root(root).exists(), "no hidden trash may remain"

    page.on_activated()
    qapp.processEvents()
    ids = {
        page._list.item(row).data(_ID_ROLE) for row in range(page._list.count())
    }
    assert project_id not in ids


def test_deleting_is_refused_while_a_recording_runs(owner_state, qapp):
    """Data loss must not be traded for disk space behind the operator's back."""
    state, owner, _root = owner_state
    workspace = make_project(state)
    project_id = workspace.project.project_id
    state.open_project(workspace.root)

    class FakeRecording:
        is_recording = True

        def shutdown(self):  # pragma: no cover - must never be reached
            raise AssertionError("a running recording must not be shut down")

    state._capture = FakeRecording()
    try:
        with pytest.raises(ValidationError) as info:
            state.prepare_project_deletion(project_id)
    finally:
        state._capture = None

    assert info.value.code == "recording_blocks_delete"
    assert workspace.project_file.is_file()
    assert state.identity.repository.get_project(project_id) is not None
    assert state.has_project


def test_the_worker_keeps_the_gui_thread_free(owner_state, qapp):
    """The delete runs on its own thread, not on the one painting the window."""
    import threading

    state, _owner, _root = owner_state
    workspace = make_project(state)
    seen: dict = {}

    def work(progress):
        seen["thread"] = threading.current_thread().name
        progress("çalışıyor…")
        return None

    dialog = DeleteProjectDialog(
        state.theme,
        project_name="X",
        project_id="prj_x",
        project_path=workspace.root,
        work=work,
    )
    dialog.confirm_field.setText("X")
    dialog.start()
    assert dialog._worker is not None
    dialog._worker.wait(30_000)
    qapp.processEvents()

    assert seen["thread"] != threading.main_thread().name
