"""The labelling panel: three places behind one strip, and how a class is made.

What is checked here is the part of the screen an annotator touches most and
the part that is easiest to get subtly wrong.

**One click, the right editor.** Clicking a box on the timeline has to open the
editor for *that* box on the first click. The failure this file is written
against is quiet: with a fault already selected, clicking its own movement's
box left the fault editor on screen, so the click looked like it did nothing.

**A class carries its joints.** A fault class is a name *and* the joints it is
about, and the two are one decision. A class that reached the schema without
its joints is a class the next annotator is asked about again - and, worse,
the record would not say whether the omission was a judgement or an
interruption. So the store refuses roles without an origin, and inherited
joints are never mistaken for reviewed ones.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.annotations import RolesOrigin  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.review import ReviewSession  # noqa: E402

from conftest import enter_the_workspace

FRAMES = 24


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def processed(workspace, session) -> Path:
    """A real processed version, anchored the way the capture screen anchors."""
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=11, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(
        session, origin=backend.origin, camera_info=info
    )
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(
        paths.raw_dir / "subject_anchors.json",
        [
            {
                "camera_timestamp_ns": packet.camera_timestamp_ns,
                "source_resolution": list(packet.resolution),
                "point_xy": np.nanmean(points, axis=0).tolist(),
                "bbox_xyxy": np.r_[
                    np.nanmin(points, axis=0), np.nanmax(points, axis=0)
                ].tolist(),
            }
        ],
    )
    source.close()
    return process_take(paths.root, config)


@pytest.fixture
def page(app, tmp_path, monkeypatch, processed, workspace):
    """The real labelling screen with a real opened version behind it."""
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
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
    # Past the project/participant gate: from 20 September every screen
    # but Projeler needs a project open in this session.
    enter_the_workspace(window, app)
    window.viewmodel.navigate("review")
    app.processEvents()

    # The screen creates classes through the *session's* workspace, so it has
    # to be the same project the take was processed in - otherwise a new
    # class would be written somewhere the recording cannot see.
    window.viewmodel.session.workspace = workspace
    view = window.page("review")
    review = ReviewSession.open(processed)
    view.viewmodel._attach(review)
    # A fresh project has no vocabulary at all, so the two movement classes
    # the tests press are created the way the screen creates them.
    view.viewmodel.create_exercise("squat")
    view.viewmodel.create_exercise("deadlift")
    view._after_open()
    app.processEvents()
    yield view, app
    review.close()
    window.close()


def a_movement(view, start: int = 2, end: int = 8) -> str:
    return view.viewmodel.add_movement(start, end)


# ------------------------------------------------------------------ PANEL-01


def test_the_panel_is_reached_by_icons_not_words(page) -> None:
    """Word tabs cost a row of height and elided to 'Etik…' at this width."""
    view, _app = page
    assert set(view.side_tabs._buttons) == {"camera", "labels", "subject"}
    for button in view.side_tabs._buttons.values():
        assert button.text() == ""
        # An icon with no name is a puzzle. Every one carries its own.
        assert button.accessibleName()
        assert button.toolTip()


def test_changing_view_does_not_move_the_panel(page) -> None:
    """PANEL-02. A panel that resizes on every view change makes the picture
    beside it jump, which is expensive to read past."""
    view, app = page
    view.side_tabs.show_view("labels")
    app.processEvents()
    before = view.side_tabs.width()
    for key in ("camera", "subject", "labels"):
        view.side_tabs.show_view(key)
        app.processEvents()
        assert view.side_tabs.width() == before


# ------------------------------------------------------------------ LABEL-01


def test_clicking_a_movement_box_opens_the_movement_editor(page) -> None:
    view, app = page
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert view.editor_bar.mode == "movement"
    assert view.side_tabs.current_view == "labels"
    assert view.side_tabs.context_of("labels") == "movement"


def test_clicking_a_fault_box_opens_the_fault_editor(page) -> None:
    view, app = page
    sample_id = a_movement(view)
    interval = view.viewmodel.add_error(3, 5)
    assert interval
    view._timeline_selected(interval)
    app.processEvents()
    assert view.editor_bar.mode == "fault"
    assert view.side_tabs.context_of("labels") == "fault"
    assert view.viewmodel.selected_error.value == interval
    assert view.viewmodel.selected_movement.value == sample_id


def test_a_movement_box_opens_its_editor_on_the_first_click(page) -> None:
    """The quiet failure: a fault of *this* movement stayed selected, so the
    fault editor stayed on screen and the click appeared to do nothing."""
    view, app = page
    sample_id = a_movement(view)
    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    assert view.editor_bar.mode == "fault"

    view._timeline_selected(sample_id)  # one click, the movement's own box
    app.processEvents()
    assert view.editor_bar.mode == "movement"
    assert view.viewmodel.selected_error.value == ""


def test_the_label_icon_returns_to_the_summary(page) -> None:
    view, app = page
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert view.editor_bar.mode == "movement"

    view._label_icon_pressed()
    app.processEvents()
    assert view.editor_bar.mode == ""
    assert view.side_tabs.context_of("labels") == "summary"
    assert view.viewmodel.selected_movement.value == ""


def test_the_context_is_words_as_well_as_colour(page) -> None:
    """Colour alone is never the signal: the strip also says what is open."""
    view, app = page
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert "Hareket" in view._label_button.accessibleDescription()

    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    assert "Hata" in view._label_button.accessibleDescription()

    tokens = view.side_tabs.CONTEXT_TOKENS
    assert tokens["movement"] != tokens["fault"] != tokens["summary"]


# ------------------------------------------------------------------ LABEL-02


def test_the_summary_counts_what_is_ready_rather_than_what_is_clean(page) -> None:
    """A movement nobody reviewed is amber, however many faults it lacks."""
    view, app = page
    a_movement(view, 2, 6)
    a_movement(view, 8, 12)
    view._label_icon_pressed()
    app.processEvents()
    text = view.summary_counts.text()
    assert "2 hareket" in text
    assert "0 hazır" in text


def test_the_summary_is_bounded(page) -> None:
    """Four hundred cards rebuilt on every edit is a cost with nothing
    behind it, and a scroll nobody reads."""
    view, _app = page
    assert view.SUMMARY_CARDS <= 60


# ------------------------------------------------------------------ LABEL-03


def test_movement_classes_are_buttons_not_a_dropdown(page) -> None:
    view, _app = page
    assert not hasattr(view, "exercise_combo")
    codes = {code for code, _text in view.viewmodel.exercise_options.value}
    assert len(codes) == 2
    assert set(view.editor_bar.exercise_classes._buttons) == codes


def test_the_quick_keys_are_printed_on_the_buttons(page) -> None:
    """The shortcut exists either way; printing it is what makes it usable."""
    view, _app = page
    first = view.viewmodel.exercise_options.value[0][0]
    assert "[1]" in view.editor_bar.exercise_classes._buttons[first].text()


def test_pressing_a_class_labels_the_selected_movement(page) -> None:
    view, app = page
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    code = view.viewmodel.exercise_options.value[0][0]
    view.editor_bar.exercise_classes._choose(code)
    assert view.viewmodel.movement_row(sample_id).exercise == code


def test_creating_a_movement_class_needs_no_dialog(page) -> None:
    """A dialog closes over the interval that prompted the class."""
    view, app = page
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    view.editor_bar.exercise_classes.new_name.setText("overhead press")
    assert view.editor_bar.exercise_classes.add_button.isEnabled()
    view.editor_bar.exercise_classes._create()
    app.processEvents()
    assert view.viewmodel.movement_row(sample_id).exercise
    assert view.editor_bar.exercise_classes.new_name.text() == ""
    assert view.editor_bar.mode == "movement"  # still on the movement


# ------------------------------------------------------------- LABEL-04/JOINT


# The joint-selection group that used to live here called
# `_joint_picked(index)` directly. The 20 September audit is explicit that
# this proves the data path and not the interaction, so it was replaced by
# tests/test_studio_joint_picking.py, which sends real double clicks at the
# pixel each joint is projected to.


# -------------------------------------------------------------------- TOOL-03


def test_looping_wraps_inside_the_selected_interval(page) -> None:
    """The playhead comes back to the start rather than running past it.

    Checked on a real interval with the real clock tick, not by reading the
    flag: the failure worth catching is looping that silently plays on, and a
    flag says nothing about that.
    """
    view, app = page
    sample_id = a_movement(view, 4, 9)
    view._timeline_selected(sample_id)
    view._loop_toggled(True)
    app.processEvents()
    assert view._looped_bounds() == (4, 9)

    view.viewmodel.seek(9)
    view._tick()          # at the end of the interval
    app.processEvents()
    assert view.viewmodel.position.value == 4

    view.viewmodel.seek(2)   # before it
    view._tick()
    app.processEvents()
    assert view.viewmodel.position.value == 4


def test_looping_a_fault_wraps_inside_the_fault_not_its_movement(page) -> None:
    view, app = page
    a_movement(view, 2, 20)
    interval = view.viewmodel.add_error(6, 8)
    view._timeline_selected(interval)
    view._loop_toggled(True)
    app.processEvents()
    assert view._looped_bounds() == (6, 8)


def test_looping_with_nothing_selected_plays_normally(page) -> None:
    """An empty selection is not an interval of length zero."""
    view, app = page
    view._loop_toggled(True)
    view._label_icon_pressed()
    app.processEvents()
    assert view._looped_bounds() is None


def test_turning_looping_off_lets_playback_run_on(page) -> None:
    view, app = page
    sample_id = a_movement(view, 4, 9)
    view._timeline_selected(sample_id)
    view._loop_toggled(True)
    app.processEvents()
    view._loop_toggled(False)
    assert view._looped_bounds() is None
    view.viewmodel.seek(9)
    view.viewmodel.playing.set(True)   # `advance` is a no-op while paused
    view._tick()
    app.processEvents()
    assert view.viewmodel.position.value == 10
