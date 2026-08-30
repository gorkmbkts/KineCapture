"""The labelling flow as the user drives it, through the real Review page.

These exercise the screen rather than the repository: mode switching, selection,
creating an error interval from the timeline, picking and creating an error
class, and the view modes - all offscreen, with no camera and no real time.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QShortcut  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.capture.service import CaptureService  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.domain.enums import (  # noqa: E402
    Correctness,
    SampleReadiness,
    TakeQuality,
)
from kinecapture.gui.widgets.scene_view import SceneMode  # noqa: E402
from kinecapture.gui.widgets.timeline import TimelineMode  # noqa: E402
from tests.conftest import paced_backend, record_take


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def review(qapp, workspace, session):
    """A window on the Review page with one recorded, unlabelled take."""
    from kinecapture.gui.main_window import MainWindow
    from tests.conftest import authenticate_state

    schema = workspace.label_schema
    schema.add_exercise("Squat")
    workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=60, exercise="squat")
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    config = AppConfig(
        dataset_root=workspace.root.parent.parent, log_dir=workspace.root / "logs"
    )
    window = MainWindow(config)
    window.resize(1366, 768)
    user = authenticate_state(window.state, workspace, open_workspace=False)
    window._authentication_completed(user)
    qapp.processEvents()
    window.navigate("review")
    qapp.processEvents()

    page = window._pages["review"]
    assert page._loaded is not None
    yield window, page, workspace, take
    window.state.release_capture_service()
    window.close()


def make_sample(page, start=2, end=25):
    page._create_sample_range(start, end)
    return page._current_sample()


def label_movement(
    page,
    sample_id,
    *,
    exercise="",
    note="",
    new_class="",
    accept=True,
):
    """Drive the movement label dialog exactly as a user would.

    ``ReviewPage._run_dialog`` is the single place the page blocks on a modal,
    so replacing it here exercises the real dialog widget - its picker, its
    draft semantics, its Save gating - without a human to click Save.

    There is no verdict to pass: the dialog does not ask for one, and the
    movement's correctness comes from its error intervals.
    """

    def run(dialog):
        if new_class:
            dialog.picker._search.setText(new_class)
            dialog.picker._activate_current()
        elif exercise:
            dialog.picker.class_chosen.emit(exercise)
        if note:
            dialog._note.setPlainText(note)
        return accept

    page._run_dialog = run
    try:
        page._open_movement_dialog(sample_id)
    finally:
        del page._run_dialog


def label_error(
    page,
    interval_id,
    *,
    error_code=None,
    note="",
    new_class="",
    delete=False,
    accept=True,
):
    """Drive the error label dialog. See :func:`label_movement`."""

    def run(dialog):
        if new_class:
            dialog.picker._search.setText(new_class)
            dialog.picker._activate_current()
        elif error_code:
            dialog.picker.class_chosen.emit(error_code)
        if note:
            dialog._note.setPlainText(note)
        if delete:
            dialog.delete_requested = True
        return accept

    page._run_dialog = run
    try:
        page._open_error_dialog(interval_id)
    finally:
        del page._run_dialog


# ------------------------------------------------------------ scene modes


def test_three_view_modes_share_one_area_and_one_position(review, qapp) -> None:
    _window, page, _workspace, _take = review
    page._seek(12)
    for mode in SceneMode:
        page._set_scene_mode(mode)
        qapp.processEvents()
        assert page._scene.mode is mode
        # Mode is presentation only: the playback position never moves.
        assert page._position == 12
    # There is one scene widget, not two permanent panels.
    assert page._scene._stack.count() == 2  # video + skeleton, one visible


def test_skeleton_controls_only_enabled_in_skeleton_mode(review, qapp) -> None:
    _window, page, _workspace, _take = review
    page._set_scene_mode(SceneMode.RGB)
    assert not page._preset_selector.isEnabled()
    page._set_scene_mode(SceneMode.SKELETON)
    assert page._preset_selector.isEnabled()
    assert page._center_toggle.isEnabled()


def test_view_modes_work_without_a_proxy_video(review, qapp) -> None:
    _window, page, _workspace, _take = review
    page._scene.set_video_available(False, "Proxy video dosyası yok.")
    for mode in SceneMode:
        page._set_scene_mode(mode)
        qapp.processEvents()
        assert not page._scene.grab().isNull()
    assert page._scene.is_mode_useful(SceneMode.SKELETON)
    assert not page._scene.is_mode_useful(SceneMode.OVERLAY)


# ------------------------------------------------------------ mode switch


def test_error_mode_requires_a_selected_movement(review, qapp) -> None:
    _window, page, _workspace, _take = review
    assert page._current_sample() is None
    page._set_timeline_mode(TimelineMode.ERROR)
    # Refused, and the UI stays on movement mode rather than half-switching.
    assert page._timeline.mode is TimelineMode.MOVEMENT
    assert page._timeline_mode_buttons[TimelineMode.MOVEMENT].isChecked()

    make_sample(page)
    page._set_timeline_mode(TimelineMode.ERROR)
    assert page._timeline.mode is TimelineMode.ERROR


def test_mode_hint_names_the_active_level(review, qapp) -> None:
    """A first-time user should not need documentation to tell them apart."""
    _window, page, _workspace, _take = review

    # The checked button names the level, and the hint names the lane to drag.
    assert page._timeline_mode_buttons[TimelineMode.MOVEMENT].isChecked()
    assert page._timeline_mode_buttons[TimelineMode.MOVEMENT].text() == (
        TimelineMode.MOVEMENT.label
    )
    movement_hint = page._mode_hint.text()
    assert "HAREKET" in movement_hint and "HATA" not in movement_hint

    sample = make_sample(page)
    page._set_timeline_mode(TimelineMode.ERROR)
    assert page._timeline_mode_buttons[TimelineMode.ERROR].isChecked()
    error_hint = page._mode_hint.text()
    assert error_hint != movement_hint
    # It names the movement being worked inside.
    assert f"Hareket {sample.index}" in error_hint
    assert "HATA" in error_hint


def test_only_two_writable_layers_exist(review, qapp) -> None:
    """Movement and error. There is no third lane, hidden or otherwise."""
    _window, page, _workspace, _take = review
    assert set(page._timeline_mode_buttons) == {
        TimelineMode.MOVEMENT,
        TimelineMode.ERROR,
    }
    assert len(list(TimelineMode)) == 2


def test_adding_an_error_is_blocked_until_a_movement_exists(review, qapp) -> None:
    _window, page, _workspace, _take = review
    assert not page._add_error_button.isEnabled()
    make_sample(page)
    assert page._add_error_button.isEnabled()


# ------------------------------------------------------- movement labelling


def test_creating_a_movement_selects_it_without_a_dialog(review, qapp) -> None:
    """Drawing ten repetitions must not mean dismissing ten modal windows."""
    _window, page, _workspace, _take = review
    opened: list[object] = []
    page._run_dialog = lambda dialog: opened.append(dialog) or False

    sample = make_sample(page, 2, 25)
    assert sample is not None
    assert page._timeline.selected_sample_id == sample.sample_id
    assert page._selected_sample_id == sample.sample_id
    assert opened == [], "creating a movement must not open a modal"


def test_labelling_a_movement_through_its_dialog(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)

    label_movement(page, sample.sample_id, exercise="squat", note="ilk tekrar")
    qapp.processEvents()

    updated = page._current_sample()
    assert updated.exercise == "squat"
    assert updated.note == "ilk tekrar"
    # Saving the class *is* the review. With no error interval marked the
    # movement is correct and export-ready at once, with no second question.
    assert updated.reviewed_at
    assert updated.derived_correctness is Correctness.CORRECT
    assert page._repo.readiness(updated).is_ready


def test_cancelling_the_movement_dialog_changes_nothing(review, qapp) -> None:
    """Cancel means cancel: the draft is discarded, not half-applied."""
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    before = page._current_sample()

    label_movement(page, sample.sample_id, exercise="",
                   note="bu not kaydedilmemeli", accept=False)
    qapp.processEvents()

    after = page._current_sample()
    assert after.exercise == before.exercise
    assert after.note == before.note
    assert after.reviewed_at == before.reviewed_at


def test_a_movement_without_a_class_cannot_be_saved(review, qapp) -> None:
    """The dialog refuses rather than recording a review that decided nothing."""
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)

    captured: list[object] = []

    def run(dialog):
        captured.append(dialog)
        assert not dialog._save_button.isEnabled()
        assert "hareket türü seçin" in dialog._status.text()
        return False

    page._run_dialog = run
    try:
        page._open_movement_dialog(sample.sample_id)
    finally:
        del page._run_dialog

    assert captured, "the dialog must have opened"
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()) is SampleReadiness.UNLABELLED
    assert "1/1" not in page._progress_chip._text.text()


def test_an_unclassified_interval_holds_the_movement_back(review, qapp) -> None:
    """The one way a reviewed movement can still be unready."""
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    assert page._repo.readiness(page._current_sample()).is_ready

    page._create_interval_range(10, 20)
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()) is (
        SampleReadiness.INVALID_INTERVAL
    )
    assert "1/1" not in page._progress_chip._text.text()


def test_creating_a_movement_class_from_the_dialog(review, qapp) -> None:
    """Movement classes are created in place, exactly like error classes."""
    _window, page, workspace, _take = review
    sample = make_sample(page, 2, 40)

    label_movement(page, sample.sample_id, new_class="Bulgar Split Squat")
    qapp.processEvents()

    updated = page._current_sample()
    assert updated.exercise
    reopened = type(workspace).open(workspace.root)
    assert updated.exercise in reopened.label_schema.exercise_codes()


def test_a_near_duplicate_movement_class_reuses_the_existing_one(
    review, qapp
) -> None:
    _window, page, workspace, _take = review
    first = make_sample(page, 2, 20)
    label_movement(page, first.sample_id, new_class="Bulgar Split Squat")
    code = page._current_sample().exercise

    second_sample = page._repo.create_sample(30, 50)
    label_movement(page, second_sample.sample_id,
                   new_class="  bulgar   SPLIT squat ")
    qapp.processEvents()

    codes = {s.exercise for s in page._repo.samples}
    assert codes == {code}
    live = page.state.workspace.label_schema
    assert len([o for o in live.exercises if o.code == code]) == 1


def test_a_class_created_in_a_cancelled_dialog_still_exists(review, qapp) -> None:
    """Adding a class is a project edit; cancelling only drops the assignment."""
    _window, page, workspace, _take = review
    sample = make_sample(page, 2, 40)

    label_movement(page, sample.sample_id, new_class="Goblet Squat", accept=False)
    qapp.processEvents()

    live = page.state.workspace.label_schema
    assert any(o.label == "Goblet Squat" for o in live.exercises)
    # ... but it was not assigned to the interval the dialog was opened for.
    assert page._current_sample().exercise == ""


def test_the_verdict_is_not_something_the_user_can_type(review, qapp) -> None:
    """No buttons, no shortcuts, no method - the intervals decide."""
    _window, page, _workspace, _take = review
    assert not hasattr(page, "_set_verdict")
    assert not hasattr(page, "_verdict_buttons")

    shortcuts = {
        shortcut.key().toString()
        for shortcut in page.findChildren(QShortcut)
    }
    assert "1" not in shortcuts and "2" not in shortcuts

    sample = make_sample(page, 2, 40)
    captured: list[object] = []

    def run(dialog):
        captured.append(dialog)
        dialog.picker.class_chosen.emit("squat")
        return True

    page._run_dialog = run
    try:
        page._open_movement_dialog(sample.sample_id)
    finally:
        del page._run_dialog

    dialog = captured[0]
    assert not hasattr(dialog, "_set_verdict")
    assert not hasattr(dialog, "correctness")
    assert not hasattr(dialog, "_correct_button")


def test_readiness_is_shown_and_matches_the_repository(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page)
    assert page._repo.readiness(page._current_sample()) is SampleReadiness.UNLABELLED
    assert "Etiketlenmedi" in page._status_label.text()

    label_movement(page, sample.sample_id, exercise="squat")
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()).is_ready
    assert "1/1 hazır" in page._progress_chip._text.text()
    assert "Hazır" in page._status_label.text()


def test_saving_the_class_says_what_the_verdict_became(review, qapp) -> None:
    """The user is told the consequence rather than asked a second question."""
    _window, page, _workspace, _take = review
    messages: list[str] = []
    page.state.notify = lambda text, timeout=4000: messages.append(text)

    sample = make_sample(page)
    label_movement(page, sample.sample_id, exercise="squat")
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()).is_ready
    assert any("DOĞRU" in text for text in messages)

    messages.clear()
    page._create_interval_range(6, 14)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    label_movement(page, sample.sample_id, exercise="squat")
    qapp.processEvents()
    assert any("HATALI" in text for text in messages)


# ------------------------------------------------------ error localisation


def test_creating_an_error_interval_from_the_timeline(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    qapp.processEvents()

    updated = page._current_sample()
    assert len(updated.error_intervals) == 1
    interval = updated.error_intervals[0]
    assert (interval.start_frame, interval.end_frame) == (10, 20)
    # Creating one switches to error mode and selects it, ready for a class.
    assert page._timeline.mode is TimelineMode.ERROR
    assert page._selected_interval_id == interval.interval_id


def test_an_interval_cannot_be_drawn_outside_its_movement(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 20, 40)
    page._create_interval_range(0, 30)
    interval = page._current_sample().error_intervals[0]
    assert interval.start_frame >= sample.start_frame
    assert interval.end_frame <= sample.end_frame


def test_picking_an_existing_error_class_assigns_it(review, qapp) -> None:
    _window, page, workspace, _take = review
    schema = workspace.label_schema
    option = schema.add_error_type("Diz içe çöküyor")
    workspace.save_label_schema(schema)
    page._populate_schema_choices()

    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, error_code=option.code)
    qapp.processEvents()

    assert page._current_sample().error_intervals[0].error_code == option.code


def test_creating_an_error_class_from_the_dialog_persists_and_assigns(
    review, qapp
) -> None:
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Topuk kalkıyor")
    qapp.processEvents()

    interval = page._current_sample().error_intervals[0]
    assert interval.error_code
    reopened = type(workspace).open(workspace.root)
    assert interval.error_code in reopened.label_schema.error_type_codes()


def test_a_near_duplicate_error_class_reuses_the_existing_class(
    review, qapp
) -> None:
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Diz İçe Çöküyor")
    first = page._current_sample().error_intervals[0].error_code

    page._create_interval_range(25, 35)
    label_error(page, page._selected_interval_id,
                new_class="  diz içe   çöküyor ")
    codes = [i.error_code for i in page._current_sample().error_intervals]

    assert codes.count(first) == 2
    assert len(page.state.workspace.label_schema.error_types) == 1
    assert len(type(workspace).open(workspace.root).label_schema.error_types) == 1


def test_cancelling_the_error_dialog_leaves_the_interval_alone(
    review, qapp
) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    interval_id = page._selected_interval_id
    label_error(page, interval_id, new_class="Topuk kalkıyor")
    before = page._current_interval().error_code
    assert before

    label_error(page, interval_id, error_code="", note="atılacak", accept=False)
    qapp.processEvents()
    after = page._current_interval()
    assert after.error_code == before
    assert after.note == ""


def test_an_unclassified_interval_keeps_the_movement_unready(review, qapp) -> None:
    """A half-finished interval must not be silently counted as done."""
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    page._create_interval_range(10, 20)
    qapp.processEvents()

    assert not page._repo.readiness(page._current_sample()).is_ready
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()).is_ready


def test_deleting_from_the_error_dialog(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, delete=True)
    qapp.processEvents()
    assert page._current_sample().error_intervals == []


def test_completing_the_flow_makes_the_movement_ready(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    qapp.processEvents()

    assert page._repo.readiness(page._current_sample()).is_ready
    assert "1 hata aralığı" in page._status_label.text()


def test_overlapping_intervals_stay_separate(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 50)
    page._create_interval_range(10, 25)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    page._create_interval_range(20, 35)
    label_error(page, page._selected_interval_id, new_class="Sırt yuvarlanıyor")
    qapp.processEvents()

    sample = page._current_sample()
    assert len(sample.error_intervals) == 2
    assert sample.error_intervals[0].overlaps(sample.error_intervals[1])
    assert len({i.error_code for i in sample.error_intervals}) == 2


def test_deleting_an_interval_updates_readiness(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    assert page._repo.readiness(page._current_sample()).is_ready

    assert page._current_sample().derived_correctness is Correctness.INCORRECT

    page._delete_interval()
    qapp.processEvents()
    # Removing the evidence removes the verdict with it, and the movement is
    # ready again - correct, on its own evidence.
    updated = page._current_sample()
    assert updated.derived_correctness is Correctness.CORRECT
    assert page._repo.readiness(updated).is_ready


def test_undo_after_creating_a_class_keeps_the_class(review, qapp) -> None:
    """Undo is about labels; the project vocabulary is configuration."""
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Topuk kalkıyor")
    code = page._current_sample().error_intervals[0].error_code

    page._undo()
    qapp.processEvents()
    assert page._current_sample().error_intervals[0].error_code == ""
    assert code in page.state.workspace.label_schema.error_type_codes()
    # ... and it is still on disk, not just in memory.
    assert code in type(workspace).open(workspace.root).label_schema.error_type_codes()


# ---------------------------------------------------------------- autosave


def test_edits_autosave_and_reload(review, qapp) -> None:
    _window, page, workspace, take = review
    sample = make_sample(page, 2, 40)
    label_movement(page, sample.sample_id, exercise="squat")
    page._create_interval_range(10, 20)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")
    page._save_now()

    reloaded = workspace.load_samples(take)
    assert len(reloaded) == 1
    assert reloaded[0].exercise == "squat"
    assert reloaded[0].derived_correctness is Correctness.INCORRECT
    assert reloaded[0].correctness is Correctness.INCORRECT, (
        "the serialised cache must agree with the derived value"
    )
    assert len(reloaded[0].error_intervals) == 1
    assert reloaded[0].error_intervals[0].error_code == "diz-ice-cokuyor"


def test_narrowing_a_movement_warns_the_user(review, qapp, monkeypatch) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 50)
    page._create_interval_range(40, 48)
    label_error(page, page._selected_interval_id, new_class="Diz içe çöküyor")

    messages: list[str] = []
    monkeypatch.setattr(
        page.state, "notify", lambda text, timeout=4000: messages.append(text)
    )
    sample = page._current_sample()
    page._sample_bounds_changed(sample.sample_id, 2, 20)
    qapp.processEvents()

    assert any("kaldırıldı" in text and "Ctrl+Z" in text for text in messages)
    assert page._current_sample().error_intervals == []


# --------------------------------------------------------------- info window


def test_take_information_lives_in_a_window_not_a_column(review, qapp) -> None:
    """The viewer and the timeline own the screen; the rest opens on demand."""
    _window, page, _workspace, _take = review
    assert page._info is None, "the info window is not built until it is wanted"
    for gone in ("_sample_list", "_interval_list", "_picker", "_exercise_selector"):
        assert not hasattr(page, gone), f"{gone} should no longer exist"

    page._toggle_info()
    qapp.processEvents()
    assert page._info is not None and page._info.isVisible()
    rows = {key.text(): value.text() for key, value in page._take_details._rows}
    assert rows["Kayıt"]
    assert "Kişi kilidi" in {
        key.text() for key, _value in page._diagnostics._rows
    }
    page._toggle_info()
    assert not page._info.isVisible()
