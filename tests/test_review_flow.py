"""The labelling flow as the user drives it, through the real Review page.

These exercise the screen rather than the repository: mode switching, selection,
creating an error interval from the timeline, picking and creating an error
class, and the view modes - all offscreen, with no camera and no real time.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

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
    window.state.open_project(workspace.root)
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
    # It names the movement being worked inside, and the constraint.
    assert f"Hareket {sample.index}" in error_hint
    assert "HATA" in error_hint
    assert "dışına çıkamaz" in error_hint


def test_error_card_is_disabled_until_a_movement_exists(review, qapp) -> None:
    _window, page, _workspace, _take = review
    assert not page._error_card.isEnabled()
    make_sample(page)
    assert page._error_card.isEnabled()


# ------------------------------------------------------- movement labelling


def test_creating_a_movement_selects_it(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 25)
    assert sample is not None
    assert page._timeline.selected_sample_id == sample.sample_id
    assert page._sample_list.count() == 1


def test_verdict_buttons_are_binary(review, qapp) -> None:
    _window, page, _workspace, _take = review
    assert set(page._verdict_buttons) == {Correctness.CORRECT, Correctness.INCORRECT}
    sample = make_sample(page)
    page._set_verdict(Correctness.CORRECT)
    assert page._current_sample().correctness is Correctness.CORRECT
    assert page._verdict_buttons[Correctness.CORRECT].isChecked()
    assert not page._verdict_buttons[Correctness.INCORRECT].isChecked()


def test_readiness_is_shown_and_matches_the_repository(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page)
    page._label_edited()  # no exercise yet
    assert page._repo.readiness(page._current_sample()) is SampleReadiness.UNLABELLED
    assert "seçilmedi" in page._exercise_row._error.text()

    page._exercise_selector.setCurrentIndex(
        page._exercise_selector.findData("squat")
    )
    page._set_verdict(Correctness.CORRECT)
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()).is_ready
    assert "1/1 hazır" in page._movement_progress._text.text()


def test_marking_incorrect_points_at_the_next_step(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page)
    page._exercise_selector.setCurrentIndex(
        page._exercise_selector.findData("squat")
    )
    page._set_verdict(Correctness.INCORRECT)
    qapp.processEvents()
    state = page._repo.readiness(page._current_sample())
    assert state is SampleReadiness.NEEDS_ERROR_INTERVAL
    assert "Aralık gerekli" in page._error_chip._text.text()


# ------------------------------------------------------ error localisation


def test_creating_an_error_interval_from_the_timeline(review, qapp) -> None:
    _window, page, _workspace, _take = review
    sample = make_sample(page, 2, 40)
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


def test_picking_an_existing_class_assigns_it(review, qapp) -> None:
    _window, page, workspace, _take = review
    schema = workspace.label_schema
    option = schema.add_error_type("Diz içe çöküyor")
    workspace.save_label_schema(schema)
    page._populate_schema_choices()

    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    page._assign_error_class(option.code)
    qapp.processEvents()

    assert page._current_sample().error_intervals[0].error_code == option.code


def test_creating_a_class_from_the_picker_persists_and_assigns(review, qapp) -> None:
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    page._create_error_class("Topuk kalkıyor")
    qapp.processEvents()

    interval = page._current_sample().error_intervals[0]
    assert interval.error_code
    # Written to the project, so it survives a reopen and shows up elsewhere.
    reopened = type(workspace).open(workspace.root)
    assert interval.error_code in reopened.label_schema.error_type_codes()
    # And it is immediately offered by the picker.
    assert interval.error_code in [
        o.code for o in page._picker._schema.error_types
    ]


def test_a_near_duplicate_class_name_reuses_the_existing_class(review, qapp) -> None:
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    page._create_error_class("Diz İçe Çöküyor")
    first = page._current_sample().error_intervals[0].error_code

    page._create_interval_range(25, 35)
    page._create_error_class("  diz içe   çöküyor ")
    codes = [i.error_code for i in page._current_sample().error_intervals]

    assert codes.count(first) == 2
    # The page's own workspace is the one the app writes through; the fixture
    # holds a separate instance with its own cached schema.
    assert len(page.state.workspace.label_schema.error_types) == 1
    assert len(type(workspace).open(workspace.root).label_schema.error_types) == 1


def test_completing_the_flow_makes_the_movement_ready(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 40)
    page._exercise_selector.setCurrentIndex(
        page._exercise_selector.findData("squat")
    )
    page._set_verdict(Correctness.INCORRECT)
    page._create_interval_range(10, 20)
    page._create_error_class("Diz içe çöküyor")
    qapp.processEvents()

    assert page._repo.readiness(page._current_sample()).is_ready
    assert "1 aralık" in page._error_chip._text.text()


def test_overlapping_intervals_are_listed_separately(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 50)
    page._create_interval_range(10, 25)
    page._create_error_class("Diz içe çöküyor")
    page._create_interval_range(20, 35)
    page._create_error_class("Sırt yuvarlanıyor")
    qapp.processEvents()

    sample = page._current_sample()
    assert len(sample.error_intervals) == 2
    assert sample.error_intervals[0].overlaps(sample.error_intervals[1])
    # Both readable in the list, each with its class name.
    rows = [
        page._interval_list.item(i).text() for i in range(page._interval_list.count())
    ]
    assert any("Diz içe çöküyor" in row for row in rows)
    assert any("Sırt yuvarlanıyor" in row for row in rows)


def test_deleting_an_interval_updates_readiness(review, qapp) -> None:
    _window, page, _workspace, _take = review
    make_sample(page, 2, 40)
    page._exercise_selector.setCurrentIndex(
        page._exercise_selector.findData("squat")
    )
    page._set_verdict(Correctness.INCORRECT)
    page._create_interval_range(10, 20)
    page._create_error_class("Diz içe çöküyor")
    assert page._repo.readiness(page._current_sample()).is_ready

    page._delete_interval()
    qapp.processEvents()
    assert page._repo.readiness(page._current_sample()) is (
        SampleReadiness.NEEDS_ERROR_INTERVAL
    )


def test_undo_after_creating_a_class_keeps_the_class(review, qapp) -> None:
    """Undo is about labels; the project vocabulary is configuration."""
    _window, page, workspace, _take = review
    make_sample(page, 2, 40)
    page._create_interval_range(10, 20)
    page._create_error_class("Topuk kalkıyor")
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
    make_sample(page, 2, 40)
    page._exercise_selector.setCurrentIndex(
        page._exercise_selector.findData("squat")
    )
    page._set_verdict(Correctness.INCORRECT)
    page._create_interval_range(10, 20)
    page._create_error_class("Diz içe çöküyor")
    page._save_now()

    reloaded = workspace.load_samples(take)
    assert len(reloaded) == 1
    assert reloaded[0].exercise == "squat"
    assert reloaded[0].correctness is Correctness.INCORRECT
    assert len(reloaded[0].error_intervals) == 1
    assert reloaded[0].error_intervals[0].error_code == "diz-ice-cokuyor"


def test_narrowing_a_movement_warns_the_user(review, qapp, monkeypatch) -> None:
    _window, page, _workspace, _take = review
    messages: list[str] = []
    monkeypatch.setattr(
        page.state, "notify", lambda text, timeout=4000: messages.append(text)
    )

    make_sample(page, 2, 50)
    page._create_interval_range(40, 48)
    page._create_error_class("Diz içe çöküyor")

    sample = page._current_sample()
    page._sample_bounds_changed(sample.sample_id, 2, 20)
    qapp.processEvents()

    assert any("kaldırıldı" in text and "Ctrl+Z" in text for text in messages)
    assert page._current_sample().error_intervals == []
