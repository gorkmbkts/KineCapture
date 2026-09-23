"""The 22 September follow-up: the gate, the top strip, the queue, Veri Seti.

Four separate user reports, and what they have in common is that each one was
a *behaviour* rather than a matter of taste - a button that could not be
pressed, a control that was there twice, a table wider than its container, a
screen that listed rows and said nothing about them. Those are the parts that
can be checked without looking, and this file checks them.

The retry check runs a **real** processing child process: "make sure that
button works" was the request, and a mocked service would not have answered
it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.services.processing import (  # noqa: E402
    Job,
    JobProgress,
    JobState,
)
from kinecapture.studio.viewmodels.dataset import (  # noqa: E402
    UNCLASSED,
    DatasetRow,
    aggregate,
)

from _gui_harness import open_review, record_and_process  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def processed(workspace, session):
    return record_and_process(workspace, session)


@pytest.fixture
def window(app, tmp_path, monkeypatch, processed, workspace):
    view, window, _session = open_review(app, tmp_path, monkeypatch, processed, workspace)
    yield window
    window.close()


# ------------------------------------------------------------------ the gate


def test_a_gated_step_is_dimmed_but_still_pressable(window, app) -> None:
    """Pressing Yakalama with no participant has to say what is missing.

    Qt sends no ``clicked`` from a disabled widget, so the refusal that
    already existed - and said the right thing - never got the chance to fire:
    the press did nothing at all. The button is dimmed by a property now, not
    disabled.
    """
    window.viewmodel.session.selected_participant_id = ""
    window.viewmodel.navigate("projects")
    app.processEvents()

    button = window.nav_bar._buttons["capture"]
    assert button.isEnabled()
    assert button.property("kcGated") == "true"

    seen: list[str] = []
    window.viewmodel.message.subscribe(lambda message: seen.append(message.headline))
    button.click()
    app.processEvents()
    assert seen == ["Kayıt için önce bir katılımcı seçin."]
    # Refused, so the screen did not change either.
    assert window.viewmodel.active_page.value == "projects"


def test_an_open_step_is_not_marked(window, app) -> None:
    window.viewmodel.navigate("projects")
    app.processEvents()
    # The gates are refreshed on the shell's heartbeat; ask for one now
    # rather than waiting a third of a second for it.
    window._refresh_gates()
    app.processEvents()
    button = window.nav_bar._buttons["library"]
    assert button.isEnabled()
    assert not button.property("kcGated")


# ------------------------------------------------------------- the top strip


def test_the_context_bar_carries_no_recording_controls(window, app) -> None:
    """A second stop button beside the first one is a second thing to think
    about. All three - indicator, clock, stop - are on Yakalama."""
    app.processEvents()
    strip = window.context_bar.recording
    assert not strip.isVisibleTo(window.context_bar)
    assert strip.parent() is window.context_bar
    # Not deleted: the shell still wires it, and the wording has one home.
    assert strip.stop_button.text() == "Kaydı durdur"


# ------------------------------------------------------------- the job queue


def _held_child() -> subprocess.Popen:
    return subprocess.Popen(  # noqa: S603 - fixed argv
        [sys.executable, "-c", "import time; time.sleep(600)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def queue(window, app):
    window.viewmodel.navigate("processing")
    app.processEvents()
    view = window.page("processing")
    view.viewmodel.reload(force=True)
    for _ in range(40):
        app.processEvents()
        if view.viewmodel.index is not None:
            break
    takes = list(view.viewmodel.index or ())
    if not takes:
        pytest.skip("no take to build a job from")
    take = takes[0]
    process = _held_child()
    job = Job(take=take, process=process, progress=JobProgress(state=JobState.RUNNING))
    view.viewmodel.service._jobs[take.take_id] = job
    view.viewmodel.poll()
    app.processEvents()
    view.job_view.selectRow(0)
    app.processEvents()
    yield view, job, take
    for held in list(view.viewmodel.service._jobs.values()):
        if held.process is not None and held.process.poll() is None:
            held.process.terminate()
            try:
                held.process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
                held.process.kill()


def test_retry_really_starts_the_job_again(queue, app) -> None:
    """The one queue action the user asked to keep, exercised for real.

    Not a state flag: the button has to end with a *new* child process
    running the actual processing module, and the previous attempt has to be
    left where it is.
    """
    view, job, take = queue
    service = view.viewmodel.service

    view.cancel_button.click()
    for _ in range(100):
        app.processEvents()
        if job.process.poll() is not None:
            break
        time.sleep(0.01)
    view.viewmodel.poll()
    app.processEvents()
    assert service.job_for(take.take_id).progress.state is JobState.CANCELLED
    assert view.retry_button.isEnabled()

    finished = job.process
    view.retry_button.click()
    for _ in range(200):
        app.processEvents()
        retried = service.job_for(take.take_id)
        if retried.process is not finished:
            break
        time.sleep(0.01)
    retried = service.job_for(take.take_id)
    assert retried.process is not finished
    assert retried.is_running
    assert retried.progress.state is JobState.RUNNING


# --------------------------------------------------------------- the dataset


def _row(**overrides) -> DatasetRow:
    base = dict(
        run_id="run", take_id="take", participant_id="P0001",
        started_at="2026-09-22T10:00", directory="", frames=100,
        duration_s=60.0, movements=0, ready=0, excluded=0, error_intervals=0,
        athlete_chosen=True, open_questions=0, has_subject_data=True,
        blockers=(),
    )
    base.update(overrides)
    return DatasetRow(**base)


def test_the_overview_counts_classes_across_versions() -> None:
    stats = aggregate(
        [
            _row(
                movements=3,
                ready=3,
                exercise_counts={"squat": 2, UNCLASSED: 1},
                error_counts={"valgus": 1},
                class_labels={"squat": "Squat", "valgus": "Valgus"},
                class_order={"squat": 0, "valgus": 1},
            ),
            _row(
                participant_id="P0002",
                movements=1,
                blockers=("unlabelled",),
                exercise_counts={"squat": 1},
                class_labels={"squat": "Squat"},
                class_order={"squat": 0},
            ),
        ]
    )
    assert stats.exercises == {"squat": 3, UNCLASSED: 1}
    assert stats.errors == {"valgus": 1}
    assert stats.ready == 1
    assert stats.blocked == 1
    assert stats.unlabelled == 0
    assert set(stats.participants) == {"P0001", "P0002"}


def test_the_unclassed_bucket_is_last_and_never_hidden() -> None:
    """How much is still unclassified is the number somebody labelling a
    dataset most wants to see, so it is never dropped - and it is not a
    class, so it does not compete for the top of the chart."""
    stats = aggregate(
        [
            _row(
                movements=9,
                exercise_counts={"squat": 1, UNCLASSED: 8},
                class_labels={"squat": "Squat"},
                class_order={"squat": 0},
            )
        ]
    )
    ranked = stats.ranked(stats.exercises)
    assert [code for code, _n in ranked] == ["squat", UNCLASSED]
    assert dict(ranked)[UNCLASSED] == 8


def test_an_empty_project_says_so_rather_than_drawing_nothing(window, app) -> None:
    view = _settled_dataset(window, app)
    view.search.setText("kesinlikle-olmayan-katılımcı")
    for _ in range(20):
        app.processEvents()
    assert view.exercise_chart.rows == ()
    assert view.error_chart.rows == ()
    # The proportion keeps all three parts so "nothing waiting" and "nothing
    # counted" cannot look alike.
    assert len(view.readiness_chart.parts) == 3


def _settled_dataset(window, app):
    """The Veri Seti page with its own project really loaded.

    Rows are *not* injected here. The page binds to the viewmodel, whose
    reload runs on a worker and lands whenever it lands - an injected set is
    replaced by the real one somewhere in the middle of the test, which is a
    flake rather than a check.
    """
    window.viewmodel.navigate("dataset")
    for _ in range(200):
        app.processEvents()
        if window.page("dataset").model.rowCount():
            break
        time.sleep(0.01)
    view = window.page("dataset")
    assert view.model.rowCount(), "the harness project has no version"
    for _ in range(20):
        app.processEvents()
    return view


def test_the_charts_follow_the_filter(window, app) -> None:
    """Narrowing the list narrows the overview: what a chart says and what
    the table shows are always the same rows."""
    view = _settled_dataset(window, app)
    assert view.coverage_chart.rows, "a loaded project should have coverage"
    everything = view.exercise_chart.rows

    view.search.setText("kesinlikle-olmayan-katılımcı")
    for _ in range(20):
        app.processEvents()
    assert view.proxy.rowCount() == 0
    assert view.exercise_chart.rows == ()
    assert view.coverage_chart.rows == ()
    assert view.readiness_chart.parts == (
        ("hazır görünüyor", 0, "KcStatusLive"),
        ("bir şey bekliyor", 0, "KcStatusWarning"),
        ("etiketlenmemiş", 0, "KcTextMuted"),
    )

    view.search.clear()
    for _ in range(20):
        app.processEvents()
    assert view.exercise_chart.rows == everything
    assert view.coverage_chart.rows


def test_the_list_actions_sit_over_the_list(window, app) -> None:
    """"Yenile" and "Etiketlemede aç" both act on the list, so both are above
    it - and the right-hand half is free for the dataset's own numbers."""
    view = _settled_dataset(window, app)
    view._apply_split_ratio()
    app.processEvents()

    table_top = view.table.mapTo(view, view.table.rect().topLeft()).y()
    for button in (view.refresh_button, view.open_button):
        bottom = button.mapTo(view, button.rect().bottomLeft()).y()
        assert bottom <= table_top
        left = button.mapTo(view, button.rect().topLeft()).x()
        assert left < view.readiness_chart.mapTo(
            view, view.readiness_chart.rect().topLeft()
        ).x()
    # The list is the narrower half now.
    assert view.table.width() < view.width() * 0.6
