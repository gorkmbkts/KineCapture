"""The 21 September user revision, checked where it can be checked headlessly.

What this file covers is the part of that round that is a *behaviour*: the
window's chrome, the capture screen's geometry contract, where the camera's
state went, and - the one the user reported as broken outright - the four
buttons under the job queue.

The queue checks run against **real child processes**. ``pause``, ``resume``
and ``cancel`` go through the same psutil suspend, psutil resume and
terminate paths a processing run uses; what is synthetic is only what the
child is doing, so a state can be held still for as long as a check takes.
Nothing here mocks the service.

The *visual* half of the round - spacing, alignment, whether the band looks
like an editor - is not decided here. It was checked by opening the real
window maximised on the target display and looking at it; see the validation
note in the wiki.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.services.processing import (  # noqa: E402
    Job,
    JobProgress,
    JobState,
)
from kinecapture.studio.views.windows import WINDOW_TITLES  # noqa: E402

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


# --------------------------------------------------------------- the window


def test_the_window_has_no_minimise_or_maximise_button(window) -> None:
    """One target size: maximised windowed. Closing is untouched."""
    flags = window.windowFlags()
    assert flags & Qt.WindowType.CustomizeWindowHint
    assert flags & Qt.WindowType.WindowCloseButtonHint
    assert not (flags & Qt.WindowType.WindowMinimizeButtonHint)
    assert not (flags & Qt.WindowType.WindowMaximizeButtonHint)
    # Not borderless fullscreen: the title bar and the frame stay.
    assert flags & Qt.WindowType.WindowTitleHint
    assert not window.isFullScreen()


def test_an_un_maximise_is_answered_by_maximising_again(window, app) -> None:
    """Win+Down and a title-bar double click still exist. Both are answered."""
    window.showMaximized()
    app.processEvents()
    assert window.isMaximized()
    window.showNormal()
    app.processEvents()
    # The answer is queued, so it lands on the next turn of the loop.
    for _ in range(10):
        app.processEvents()
        if window.isMaximized():
            break
    assert window.isMaximized()


# -------------------------------------------------------------- the capture


def test_the_preview_box_does_not_move_when_a_camera_appears(window, app) -> None:
    """Connect, disconnect and reconnect must not move anything.

    The box is solved from the page, never from the frame that has just
    arrived, so the black rectangle before Bağlan and the picture after it
    occupy the same place to the pixel. The image's own ratio is still exact -
    it is letterboxed inside this fixed box.
    """
    window.viewmodel.navigate("capture")
    app.processEvents()
    view = window.page("capture")
    view.apply_stage_geometry()
    app.processEvents()
    empty = view.preview.geometry()
    console = view.console.geometry()

    # A 4:3 source, deliberately not the box's own ratio.
    view._note_source_shape((640, 480))
    view.apply_stage_geometry()
    app.processEvents()
    assert view.preview.geometry() == empty
    assert view.console.geometry() == console

    view._note_source_shape((1920, 1080))
    view.apply_stage_geometry()
    app.processEvents()
    assert view.preview.geometry() == empty
    assert view.console.geometry() == console


def test_the_picture_carries_no_notifications(window, app) -> None:
    """No framing badge, no history line, no caption inside the box.

    The selection frame itself stays: it is how the screen says which body it
    understood, and the user asked for the frame without the word.
    """
    window.viewmodel.navigate("capture")
    app.processEvents()
    view = window.page("capture")
    preview = view.preview
    assert not hasattr(preview, "_paint_framing")
    # The measurement is still taken and still stored - it is what the status
    # window reads - it is simply never drawn.
    preview.set_framing("Ayaklar kadraj dışında", "cut", "Son 15 sn")
    assert preview._framing == ("Ayaklar kadraj dışında", "cut", "Son 15 sn")
    preview.set_subject_box((10.0, 10.0, 40.0, 90.0))
    assert preview._subject_box is not None


def test_the_console_has_no_changing_status_block(window, app) -> None:
    window.viewmodel.navigate("capture")
    app.processEvents()
    view = window.page("capture")
    # Four blocks, all of them controls. The DURUM block is not one of them.
    assert len(view._groups) == 4
    assert not view.status_group.isVisible()
    assert not view.mode_state.isVisible()
    for group in view._groups:
        assert group.isAncestorOf(view.framing_label) is False


def test_the_camera_state_is_reachable_from_araclar(window, app) -> None:
    """Moved out of sight, not switched off."""
    assert "capture" in WINDOW_TITLES
    window.viewmodel.navigate("capture")
    app.processEvents()
    view = window.page("capture")
    view._show_framing(
        type("F", (), {"text": "Kadraj tamam", "advice": "", "state": "ok"})()
    )
    sections = window._capture_status_sections()
    titles = [section.title for section in sections]
    assert titles == ["Kamera", "Kadraj", "Uyarılar"]
    printed = "\n".join(
        f"{row.label} {row.value}" for section in sections for row in section.rows
    )
    assert "Kadraj tamam" in printed
    assert "Bağlantı" in printed


def test_a_record_press_with_nobody_chosen_refuses_every_time(
    window, app, participant
) -> None:
    """The one notification this screen keeps, and it has to keep arriving.

    Every other gate is satisfied first - a project is open, a participant is
    chosen, the camera is connected - so the refusal under test is the one
    about the person in the frame and not one of the earlier ones.
    """
    window.viewmodel.session.selected_participant_id = participant.participant_id
    window.viewmodel.navigate("capture")
    app.processEvents()
    view = window.page("capture")
    viewmodel = view.viewmodel
    viewmodel.service.connect()
    deadline = time.time() + 10
    while time.time() < deadline and not viewmodel.service.is_connected:
        app.processEvents()
        time.sleep(0.01)
    assert viewmodel.service.is_connected
    viewmodel.refresh()
    app.processEvents()
    viewmodel.clear_subject()

    seen: list[str] = []
    viewmodel.message.subscribe(lambda message: seen.append(message.headline))
    assert viewmodel.toggle_recording() is False
    assert viewmodel.toggle_recording() is False
    assert seen == ["Önce görüntüde kişiyi seçin."] * 2, seen
    assert not viewmodel.service.is_recording
    viewmodel.service.disconnect()


# ------------------------------------------------------------- the job queue


def _held_child() -> subprocess.Popen:
    """A real process that will not finish on its own."""
    return subprocess.Popen(  # noqa: S603 - fixed argv
        [sys.executable, "-c", "import time; time.sleep(600)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def queue(window, app):
    """The processing screen with one real, controllable job in the queue."""
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
    if process.poll() is None:
        try:
            import psutil

            psutil.Process(process.pid).resume()
        except Exception:  # noqa: BLE001 - best effort on the way out
            pass
        process.terminate()
        process.wait(timeout=10)


def test_the_selection_survives_the_queue_being_re_read(queue, app) -> None:
    """The reason the four buttons looked dead.

    ``set_rows`` resets the model and a reset clears the selection, and the
    queue is re-read four times a second - so a job stayed selected for at
    most 400 ms, after which every action was disabled again.
    """
    view, _job, _take = queue
    assert view.job_view.selectionModel().selectedRows()
    for _ in range(5):
        view.viewmodel.poll()
        app.processEvents()
    assert view.job_view.selectionModel().selectedRows()
    assert view._selected_job() is not None


def test_pause_resume_and_cancel_really_act_on_the_job(queue, app) -> None:
    view, job, take = queue
    service = view.viewmodel.service
    raw = Path(str(take.directory)) / "raw"
    before = sorted(p.name for p in raw.rglob("*")) if raw.exists() else None

    assert view.pause_button.isEnabled()
    assert view.cancel_button.isEnabled()
    assert not view.resume_button.isEnabled()
    assert not view.retry_button.isEnabled()

    view.pause_button.click()
    app.processEvents()
    assert service.job_for(take.take_id).progress.state is JobState.PAUSED
    # Held, not killed: the work done so far is still there.
    assert job.process.poll() is None
    assert view.resume_button.isEnabled()

    view.resume_button.click()
    app.processEvents()
    assert service.job_for(take.take_id).progress.state is JobState.RUNNING
    assert view.pause_button.isEnabled()

    view.cancel_button.click()
    for _ in range(80):
        app.processEvents()
        if job.process.poll() is not None:
            break
    assert job.process.poll() is not None
    view.viewmodel.poll()
    app.processEvents()
    assert service.job_for(take.take_id).progress.state is JobState.CANCELLED
    # The raw recording is untouched. That is what the note beside the button
    # says, and it is the one thing a cancel must never get wrong. (The
    # cancelled attempt's own partial directory is a different matter: that
    # one is *meant* to go away, and nothing half-finished is published.)
    assert raw.exists()
    assert sorted(p.name for p in raw.rglob("*")) == before
    assert view.retry_button.isEnabled()


def test_an_action_that_is_off_says_what_would_turn_it_on(queue, app) -> None:
    view, _job, _take = queue
    assert view.action_note.text()
    view.job_view.clearSelection()
    app.processEvents()
    assert "Bir iş seçin" in view.action_note.text()
    assert not any(
        button.isEnabled()
        for button in (
            view.pause_button,
            view.resume_button,
            view.cancel_button,
            view.retry_button,
        )
    )


def test_the_two_processing_containers_share_their_top_and_bottom(window, app) -> None:
    window.viewmodel.navigate("processing")
    app.processEvents()
    view = window.page("processing")
    view._align_bands()
    app.processEvents()
    waiting = view.waiting_view
    jobs = view.job_view
    top_left = waiting.mapTo(view, waiting.rect().topLeft()).y()
    top_right = jobs.mapTo(view, jobs.rect().topLeft()).y()
    bottom_left = waiting.mapTo(view, waiting.rect().bottomLeft()).y()
    bottom_right = jobs.mapTo(view, jobs.rect().bottomLeft()).y()
    assert top_left == top_right
    assert bottom_left == bottom_right
    assert waiting.height() == jobs.height()
