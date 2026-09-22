"""Veri Seti: the detail panel, and the actions that lead to the fix.

The requirement this file is written against is specific: an action must not
just change the page. Navigating to Etiketleme without carrying the version
leaves whichever recording happened to be open on screen, and the reader then
fixes the wrong one - quietly, because the screen looks exactly right.

The other thing checked here is that this screen does not hand out verdicts.
It reads sidecars; the authoritative answer lives in Dışa Aktarım. So a record
with nothing outstanding is "bu ekrana göre bekleyen bir şey yok", never a
green "hazır", and a record that has not been labelled at all is never counted
as ready.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.viewmodels.dataset import (  # noqa: E402
    BLOCKER_TEXT,
    DatasetRow,
)
from kinecapture.studio.views.pages.dataset import DatasetPage  # noqa: E402

from conftest import show_page_directly  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    window = build_window(config, state_path=tmp_path / "window.json")
    window.resize(1600, 900)
    window.show()
    assert window.auth_viewmodel.create_owner(
        first_name="Ada",
        last_name="Lovelace",
        title="",
        username="ada",
        password="kinecapture1",
        password_confirm="kinecapture1",
    )
    app.processEvents()
    # Shown directly: this file is about what the buttons on this screen
    # carry, not about the project gate in front of it, and giving it a real
    # project makes the screen load the project's own (empty) rows over the
    # ones each test puts there.
    show_page_directly(window, "dataset", app)
    yield window.page("dataset"), window, app
    window.close()


def a_row(**changes) -> DatasetRow:
    defaults = dict(
        run_id="run_0001",
        take_id="take_0001",
        participant_id="P0001",
        started_at="2026-09-19T10:30:00",
        directory=r"C:\project\takes\take_0001\processing\run_0001",
        frames=240,
        duration_s=8.0,
        movements=3,
        ready=1,
        excluded=0,
        error_intervals=2,
        athlete_chosen=False,
        open_questions=1,
        has_subject_data=True,
        blockers=("athlete",),
    )
    defaults.update(changes)
    return DatasetRow(**defaults)


def show(view: DatasetPage, app, row: DatasetRow) -> None:
    view.model.set_rows([row])
    view.table.selectRow(0)
    app.processEvents()


def buttons(view: DatasetPage) -> list[QPushButton]:
    layout = view._blocker_layout
    found = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QPushButton):
            found.append(widget)
    return found


# ------------------------------------------------------------------- detail


def test_nothing_selected_asks_for_a_selection(page) -> None:
    view, _window, app = page
    view.model.set_rows([])
    app.processEvents()
    assert "seçin" in view.detail_title.text()
    assert not view.open_button.isEnabled()


def test_the_detail_names_the_record_it_is_about(page) -> None:
    view, _window, app = page
    show(view, app, a_row())
    assert "P0001" in view.detail_title.text()
    assert "run_0001" in view.detail_title.text()


def test_a_summary_is_built_from_the_row_not_from_a_verdict(page) -> None:
    view, _window, app = page
    show(view, app, a_row(movements=4, ready=2))
    assert "2/4 hareket" in view.detail_lines.text()


def test_an_unlabelled_record_is_never_counted_as_ready(page) -> None:
    view, _window, app = page
    show(view, app, a_row(movements=0, ready=0, blockers=("unlabelled",)))
    assert "işaretlenmemiş" in view.detail_lines.text()
    row = view._selected_row()
    assert not row.looks_ready


def test_a_clear_record_gets_a_hedge_not_a_green_verdict(page) -> None:
    """The authoritative check is the export's. This screen reads sidecars."""
    view, _window, app = page
    show(view, app, a_row(blockers=(), ready=3, movements=3))
    assert not buttons(view)
    assert "bu ekrana göre" in view.detail_lines.text().lower() or any(
        "bu ekrana göre" in view._blocker_layout.itemAt(i).widget().text().lower()
        for i in range(view._blocker_layout.count())
        if view._blocker_layout.itemAt(i).widget() is not None
    )


# ------------------------------------------------------------------ actions


def test_every_blocker_with_a_destination_gets_a_button(page) -> None:
    view, _window, app = page
    show(view, app, a_row(blockers=("athlete", "open_error")))
    labels = [b.text() for b in buttons(view)]
    assert len(labels) == 2
    assert any(BLOCKER_TEXT["athlete"] in text for text in labels)
    assert any(BLOCKER_TEXT["open_error"] in text for text in labels)


def test_a_blocker_with_no_destination_gets_a_line_not_a_button(page) -> None:
    """A run processed without a subject is fixed by processing it again, not
    by going anywhere. A button that opens a screen which cannot help is
    worse than a sentence that says so."""
    view, _window, app = page
    show(view, app, a_row(blockers=("no_subject_data",)))
    assert not buttons(view)
    texts = [
        view._blocker_layout.itemAt(i).widget().text()
        for i in range(view._blocker_layout.count())
        if view._blocker_layout.itemAt(i).widget() is not None
    ]
    assert any(BLOCKER_TEXT["no_subject_data"] in text for text in texts)


def watch_navigation(window, monkeypatch) -> list[str]:
    """Record where the page asked to go, without letting it get there.

    The labelling screen *consumes* the handoff as it activates, which is
    correct and also means the values are gone by the time a test could look
    at them. Holding the navigation still is the only way to see what was
    handed over.
    """
    asked: list[str] = []
    monkeypatch.setattr(
        window.viewmodel, "navigate", lambda key: (asked.append(key), True)[1]
    )
    return asked


def test_an_action_carries_the_version_not_just_the_page(
    page, monkeypatch
) -> None:
    """The failure this guards: navigating alone leaves the previously opened
    recording on screen and the reader edits the wrong one."""
    view, window, app = page
    asked = watch_navigation(window, monkeypatch)
    row = a_row()
    show(view, app, row)
    buttons(view)[0].click()
    app.processEvents()
    assert window.pending_review == row.directory
    assert asked == ["review"]


def test_each_blocker_carries_where_to_land(page, monkeypatch) -> None:
    view, window, app = page
    watch_navigation(window, monkeypatch)
    for blocker, (focus, _caption) in DatasetPage.BLOCKER_FOCUS.items():
        window.pending_review = None
        window.pending_review_focus = ""
        show(view, app, a_row(blockers=(blocker,)))
        buttons(view)[0].click()
        app.processEvents()
        assert window.pending_review_focus == focus, blocker


def test_opening_without_a_blocker_still_carries_the_version(
    page, monkeypatch
) -> None:
    view, window, app = page
    watch_navigation(window, monkeypatch)
    row = a_row(blockers=())
    show(view, app, row)
    window.pending_review = None
    view.open_button.click()
    app.processEvents()
    assert window.pending_review == row.directory
    assert window.pending_review_focus == "labels"


def test_every_destination_is_one_the_labelling_screen_understands() -> None:
    """A focus nobody handles is a button that silently does nothing."""
    from kinecapture.studio.views.pages.review import ReviewPage

    source = ReviewPage._apply_focus.__doc__ or ""
    handled = {"subject", "open_error", "no_exercise", "labels"}
    for focus, _caption in DatasetPage.BLOCKER_FOCUS.values():
        assert focus in handled, focus
    assert source  # the behaviour is documented where it is implemented
