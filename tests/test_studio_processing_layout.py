"""Verileri Hesapla's two columns, and what each of them is allowed to claim.

Driven with rows handed straight to the page. Building a real take here would
mean launching the processing child process for a question about layout, and
the honesty rules - no invented percentage, no green for a run that only
*looks* finished - are properties of the rendering, not of the subprocess.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.dataset.summary_index import TakeSummary  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.processing import (  # noqa: E402
    Job,
    JobProgress,
    JobState,
)

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
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    # Shown directly: this file is about how the screen renders, not about
    # the project gate in front of it.
    show_page_directly(window, "processing", app)
    yield window.page("processing"), window, app
    window.close()


def take(participant: str, index: int, *, seconds: float = 12.0) -> TakeSummary:
    return TakeSummary(
        take_id=f"take_{participant}_{index:03d}",
        participant_id=participant,
        session_id="ses_1",
        directory=f"/tmp/{participant}/{index}",
        started_at=f"2026-09-1{index % 9}T10:0{index % 6}:00+00:00",
        state="closed",
        processing_status="awaiting_processing",
        frames=int(seconds * 60),
        duration_s=seconds,
    )


def job(state: JobState, participant: str = "P0001", **progress) -> Job:  # noqa: ANN003
    return Job(take=take(participant, 1), progress=JobProgress(state=state, **progress))


# ------------------------------------------------------------------ PROC-01


def test_the_two_lists_are_side_by_side(page) -> None:
    view, _window, app = page
    app.processEvents()
    left = view.split.widget(0)
    right = view.split.widget(1)
    assert left.x() < right.x()
    # Same band vertically: side by side, not one above the other.
    assert left.y() == right.y()
    assert left.height() == right.height()


def test_the_starting_split_is_about_forty_sixty(page) -> None:
    view, _window, app = page
    app.processEvents()
    sizes = view.split.sizes()
    total = sum(sizes)
    assert total > 0
    share = sizes[0] / total
    assert 0.34 <= share <= 0.46, sizes


def test_both_lists_stay_readable_with_many_rows(page) -> None:
    view, _window, app = page
    view._show_waiting(tuple(take("P0001", i) for i in range(60)))
    view._show_jobs(tuple(job(JobState.QUEUED) for _ in range(40)))
    app.processEvents()
    # Each table keeps most of its column's height rather than being squeezed
    # to a strip by the block of controls under it.
    assert view.waiting_view.height() > view.split.widget(0).height() * 0.4
    assert view.job_view.height() > view.split.widget(1).height() * 0.5


# ------------------------------------------------------------------ PROC-02


def test_search_narrows_the_waiting_list(page) -> None:
    view, _window, app = page
    view._show_waiting((take("P0001", 1), take("P0002", 2), take("P0002", 3)))
    app.processEvents()
    assert view.waiting_proxy.rowCount() == 3
    view.search.setText("P0002")
    app.processEvents()
    assert view.waiting_proxy.rowCount() == 2


def test_the_participant_filter_follows_the_rows(page) -> None:
    view, _window, app = page
    view._show_waiting((take("P0001", 1), take("P0002", 2)))
    app.processEvents()
    offered = [
        view.participant_box.itemData(i) for i in range(view.participant_box.count())
    ]
    assert offered == ["", "P0001", "P0002"]


def test_the_filter_and_the_search_narrow_together(page) -> None:
    """Choosing a participant and then typing must leave rows matching both."""
    view, _window, app = page
    view._show_waiting(
        (take("P0001", 1), take("P0002", 2), take("P0002", 3))
    )
    app.processEvents()
    index = view.participant_box.findData("P0002")
    view.participant_box.setCurrentIndex(index)
    app.processEvents()
    assert view.waiting_proxy.rowCount() == 2
    view.search.setText("P0001")
    app.processEvents()
    # Nothing is both P0002 and P0001.
    assert view.waiting_proxy.rowCount() == 0


def test_more_than_one_take_can_be_chosen(page) -> None:
    from PySide6.QtWidgets import QAbstractItemView

    view, _window, _app = page
    assert (
        view.waiting_view.selectionMode()
        is QAbstractItemView.SelectionMode.ExtendedSelection
    )


def test_the_selection_says_what_would_be_processed(page) -> None:
    view, _window, app = page
    view._show_waiting((take("P0007", 1, seconds=42.0),))
    app.processEvents()
    view.waiting_view.selectRow(0)
    app.processEvents()
    text = view.selection_summary.text()
    assert "P0007" in text
    assert "42" in text
    assert "2520 kare" in text


def test_no_selection_offers_nothing_to_start(page) -> None:
    view, _window, app = page
    view._show_waiting((take("P0001", 1),))
    app.processEvents()
    view.waiting_view.clearSelection()
    app.processEvents()
    assert not view.start_button.isEnabled()
    assert "seçin" in view.selection_summary.text().casefold()


def test_the_queue_counts_come_from_the_jobs(page) -> None:
    view, _window, app = page
    view._show_jobs(
        (
            job(JobState.QUEUED),
            job(JobState.PAUSED),
            job(JobState.RUNNING),
            job(JobState.COMPLETE),
            job(JobState.COMPLETE),
            job(JobState.FAILED),
            job(JobState.PARTIAL),
            job(JobState.CANCELLED),
        )
    )
    app.processEvents()
    assert view.counts["queued"].text() == "2"
    assert view.counts["running"].text() == "1"
    assert view.counts["done"].text() == "2"
    # PARTIAL, FAILED and CANCELLED all want somebody to look at them.
    assert view.counts["failed"].text() == "3"


def test_a_problem_count_is_marked_and_a_clean_one_is_not(page) -> None:
    view, _window, app = page
    view._show_jobs((job(JobState.COMPLETE),))
    app.processEvents()
    assert not view.counts["failed"].property("kcStatus")
    view._show_jobs((job(JobState.FAILED),))
    app.processEvents()
    assert view.counts["failed"].property("kcStatus") == "error"


def test_no_percentage_is_shown_without_a_declared_total(page) -> None:
    view, _window, app = page
    view._show_jobs(
        (job(JobState.RUNNING, frames_processed=412, frames_declared=None),)
    )
    app.processEvents()
    assert view.progress.isVisibleTo(view)
    # An indeterminate bar: minimum and maximum both zero.
    assert view.progress.minimum() == 0 and view.progress.maximum() == 0
    assert "%" not in view.progress.format()


def test_a_declared_total_gives_a_real_percentage(page) -> None:
    view, _window, app = page
    view._show_jobs(
        (job(JobState.RUNNING, frames_processed=450, frames_declared=900),)
    )
    app.processEvents()
    assert view.progress.maximum() == 100
    assert view.progress.value() == 50
    assert "%50" in view.progress.format()


def test_the_actions_follow_the_selected_job(page) -> None:
    view, _window, app = page
    view._show_jobs((job(JobState.RUNNING), job(JobState.COMPLETE)))
    app.processEvents()
    view.job_view.selectRow(0)
    app.processEvents()
    assert view.cancel_button.isEnabled()
    assert not view.retry_button.isEnabled()
    view.job_view.selectRow(1)
    app.processEvents()
    assert view.retry_button.isEnabled()
    assert not view.cancel_button.isEnabled()


def test_the_long_profile_detail_stays_folded_away(page) -> None:
    view, _window, app = page
    app.processEvents()
    assert not view.profile_detail.isVisibleTo(view)
    view.profile_button.setChecked(True)
    app.processEvents()
    assert view.profile_detail.isVisibleTo(view)
