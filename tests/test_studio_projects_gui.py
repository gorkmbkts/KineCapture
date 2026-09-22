"""The Projects and Settings widgets, built for real.

What is worth checking at this level is the part that only exists once Qt does:
that the lists are backed by a model rather than per-cell widgets, that the
worker thread reports back on the GUI thread, and that the settings page
renders every declared field with its explanation.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableView  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.projects import ParticipantRow  # noqa: E402
from kinecapture.studio.services.settings import all_fields  # noqa: E402
from kinecapture.studio.services.window_state import WindowState  # noqa: E402
from kinecapture.studio.views.models import (  # noqa: E402
    ROW_ROLE,
    Column,
    RowTableModel,
    SearchProxy,
)
from kinecapture.studio.views.tasks import QtTaskRunner  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    built = build_window(
        config,
        window_state=WindowState(width=1400, height=900, maximised=False),
        state_path=tmp_path / "ws.json",
    )
    built.resize(1400, 900)
    built.show()
    app.processEvents()
    yield built
    built.close()


@pytest.fixture
def open_window(window, app: QApplication):
    """A window with an owner account created and signed in."""
    assert window.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    return window


# --------------------------------------------------------------------- gate


def test_the_workspace_is_behind_the_sign_in_gate(window, app: QApplication) -> None:
    assert window.gate.currentWidget() is window.auth_view


def test_signing_in_opens_the_workspace(open_window, app: QApplication) -> None:
    assert open_window.gate.currentWidget() is open_window.shell_body


# -------------------------------------------------------------- table model


def _rows(count: int) -> list[ParticipantRow]:
    return [
        ParticipantRow(
            participant_id=f"P{i:04d}",
            code=f"P{i:04d}",
            created_at="2026-09-13T10:00:00+00:00",
            take_count=i % 7,
            processed_count=i % 3,
            awaiting_count=i % 5,
        )
        for i in range(1, count + 1)
    ]


def test_model_is_virtualised_not_one_widget_per_cell(app: QApplication) -> None:
    """The thing this replaces allocated nine objects per row, seen or not."""
    columns = (
        Column[ParticipantRow]("code", "Katılımcı", lambda r: r.code),
        Column[ParticipantRow](
            "takes", "Kayıt", lambda r: str(r.take_count), sort_key=lambda r: r.take_count
        ),
    )
    model = RowTableModel(columns)
    view = QTableView()
    view.setModel(model)
    view.resize(600, 400)
    view.show()
    app.processEvents()

    model.set_rows(_rows(5000))
    app.processEvents()
    assert model.rowCount() == 5000
    # Qt creates no per-cell objects: the data comes from the model on demand.
    index = model.index(4999, 0)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "P5000"
    assert model.data(index, ROW_ROLE).code == "P5000"
    view.close()


def test_filling_a_thousand_rows_is_fast(app: QApplication) -> None:
    """The F1 baseline for the same job was 36 ms; this must stay well under it."""
    columns = tuple(
        Column[ParticipantRow](f"c{i}", f"C{i}", lambda r, i=i: f"{r.code}-{i}")
        for i in range(9)
    )
    model = RowTableModel(columns)
    view = QTableView()
    view.setModel(model)
    view.resize(900, 600)
    view.show()
    rows = _rows(1000)
    app.processEvents()

    started = time.perf_counter()
    model.set_rows(rows)
    app.processEvents()
    elapsed_ms = (time.perf_counter() - started) * 1000
    view.close()
    assert model.rowCount() == 1000
    assert elapsed_ms < 25, f"1000 satır doldurma {elapsed_ms:.1f} ms sürdü"


def test_search_filters_across_every_column(app: QApplication) -> None:
    columns = (
        Column[ParticipantRow]("code", "Katılımcı", lambda r: r.code),
        Column[ParticipantRow]("takes", "Kayıt", lambda r: str(r.take_count)),
    )
    model = RowTableModel(columns)
    model.set_rows(_rows(30))
    proxy = SearchProxy()
    proxy.setSourceModel(model)
    assert proxy.rowCount() == 30
    proxy.set_search("P0007")
    assert proxy.rowCount() == 1
    proxy.set_search("")
    assert proxy.rowCount() == 30


def test_sorting_uses_the_sort_key_not_the_text(app: QApplication) -> None:
    """Ten must sort after nine, which sorting the strings would get wrong."""
    columns = (
        Column[ParticipantRow](
            "takes",
            "Kayıt",
            lambda r: str(r.take_count),
            sort_key=lambda r: r.take_count,
        ),
    )
    model = RowTableModel(columns)
    model.set_rows(
        [
            ParticipantRow("a", "a", "", take_count=9),
            ParticipantRow("b", "b", "", take_count=10),
        ]
    )
    proxy = SearchProxy()
    proxy.setSourceModel(model)
    proxy.sort(0, Qt.SortOrder.AscendingOrder)
    first = proxy.index(0, 0).data(ROW_ROLE)
    assert first.take_count == 9


# ------------------------------------------------------------- task runner


def test_worker_results_arrive_on_the_gui_thread(app: QApplication) -> None:
    """A callback that ran on the worker would corrupt Qt somewhere else, later."""
    import threading

    runner = QtTaskRunner()
    main_thread = threading.current_thread().ident
    seen: dict[str, object] = {}

    def work() -> int:
        assert threading.current_thread().ident != main_thread
        return 42

    runner.run(work, lambda value: seen.update(value=value, thread=threading.current_thread().ident))

    deadline = time.time() + 10
    while "value" not in seen and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert seen.get("value") == 42
    assert seen.get("thread") == main_thread


def test_a_failing_task_reports_instead_of_killing_the_pool(app: QApplication) -> None:
    runner = QtTaskRunner()
    seen: list[BaseException] = []
    runner.run(lambda: 1 / 0, lambda _v: None, seen.append)
    deadline = time.time() + 10
    while not seen and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert seen and isinstance(seen[0], ZeroDivisionError)


# --------------------------------------------------------------- projects page


def test_projects_page_lists_what_was_created(open_window, app: QApplication) -> None:
    open_window.viewmodel.navigate("projects")
    app.processEvents()
    page = open_window.page("projects")
    page.page_activated()
    app.processEvents()

    viewmodel = open_window.viewmodel_for["projects"]
    viewmodel.create_project("Squat")
    viewmodel.create_participant()
    app.processEvents()

    assert page.project_model.rowCount() == 1
    assert page.participant_model.rowCount() == 1
    assert page.participant_model.index(0, 0).data(Qt.ItemDataRole.DisplayRole) == "P0001"


def test_searching_narrows_the_participant_list(open_window, app: QApplication) -> None:
    open_window.viewmodel.navigate("projects")
    app.processEvents()
    page = open_window.page("projects")
    page.page_activated()
    viewmodel = open_window.viewmodel_for["projects"]
    viewmodel.create_project("Squat")
    for _ in range(4):
        viewmodel.create_participant()
    app.processEvents()

    assert page.participant_proxy.rowCount() == 4
    page.search.setText("P0003")
    app.processEvents()
    assert page.participant_proxy.rowCount() == 1


def test_refresh_button_is_disabled_while_the_scan_runs(
    open_window, app: QApplication
) -> None:
    page = open_window.page("projects")
    viewmodel = open_window.viewmodel_for["projects"]
    viewmodel.busy.set(True)
    app.processEvents()
    assert page.refresh_button.isEnabled() is False
    viewmodel.busy.set(False)
    app.processEvents()
    assert page.refresh_button.isEnabled() is True


# --------------------------------------------------------------- settings page


def test_settings_page_renders_every_declared_field(
    open_window, app: QApplication
) -> None:
    open_window.viewmodel.navigate("settings")
    app.processEvents()
    page = open_window.page("settings")
    assert set(page.rows) == {field.key for field in all_fields()}


def test_every_field_shows_its_explanation(open_window, app: QApplication) -> None:
    """The sentence is shown in full now: it wraps instead of being elided.

    A help text cut off at the width of a control is not an explanation, so
    the label was changed from an eliding one to a wrapping one.
    """
    page = open_window.page("settings")
    for key, row in page.rows.items():
        assert row.help.text().strip(), key
        assert row.help.wordWrap(), key
        assert row.accessibleDescription().strip(), key


def test_editing_marks_the_page_dirty_with_a_count(
    open_window, app: QApplication
) -> None:
    page = open_window.page("settings")
    viewmodel = open_window.viewmodel_for["settings"]
    viewmodel.edit("capture.fps", 30)
    viewmodel.edit("processing.body_format", "BODY_34")
    app.processEvents()
    # Two edits, two counted: bound to the pending map, not to a boolean that
    # stops changing after the first one.
    assert "2" in page.dirty_label.fullText()
    assert page.discard_button.isEnabled()


def test_an_invalid_value_blocks_save_and_names_the_field(
    open_window, app: QApplication
) -> None:
    # A project first: from 20 September every screen but Projeler is gated on
    # one, and a gated navigation goes back to Projeler. Then navigated to,
    # because a widget on a stack page that is not current reports
    # isVisible() False and the assertion below would fail for that reason.
    projects = open_window.viewmodel_for["projects"]
    projects.reload_projects()
    assert projects.create_project("Gezinti")
    app.processEvents()
    assert open_window.viewmodel.navigate("settings")
    app.processEvents()
    page = open_window.page("settings")
    viewmodel = open_window.viewmodel_for["settings"]
    viewmodel.edit("capture.preview_fps", 0.0)
    app.processEvents()
    assert page.save_button.isEnabled() is False
    assert page.rows["capture.preview_fps"].problem.isVisible()


def test_discard_clears_the_edits(open_window, app: QApplication) -> None:
    page = open_window.page("settings")
    viewmodel = open_window.viewmodel_for["settings"]
    viewmodel.edit("capture.fps", 45)
    app.processEvents()
    page.discard_button.click()
    app.processEvents()
    assert viewmodel.pending.value == {}
    assert "Tüm değişiklikler" in page.dirty_label.fullText()
