"""The 22 September labelling follow-up: the floor grid and the band's actions.

Two user reports from the labelling screen, both checkable without looking.

* **The athlete stood on the edge of the floor grid.** Measured on the user's
  own version (855 frames, floor detected by the SDK): the grid was centred on
  the recording's origin - the camera - and the feet were 3.03 m from that
  centre on a grid reaching 3 m each way. Centring on the feet happened only
  when *no* floor had been measured; a second version opened in the same view
  kept the first one's centre.
* **The band's actions, in the user's order.** "Hata aralığı ekle" is gone -
  the timeline's own tool draws a fault. Against the right edge, left to
  right: movement ``sil · Diğer sınıflar · Sınıfsızlara uygula``; fault
  ``sil · Diğer sınıflar · Eklemleri düzenle · Harekete dön · Not``. Asked
  and answered: "Diğer sınıflar" sits right after delete in both modes and is
  always shown.

An order is what was asked for, and an order is what a layout gets wrong, so
the band is checked as geometry on the real screen rather than as a list of
attributes - at the one size the 21 September decision targets, the
maximised window on the user's 1920-wide screen, and not across a size
matrix, which that decision declined.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QAbstractButton, QApplication, QWidget  # noqa: E402

from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.views.annotationbar import BROWSE_TEXT  # noqa: E402
from kinecapture.studio.views.skeleton3d import Skeleton3DView  # noqa: E402

from _gui_harness import clipped_controls, open_review, record_and_process  # noqa: E402

#: The target: the maximised window on the user's screen.
TARGET = (1920, 1080)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------ the floor grid

#: Where the user's athlete stood, in the recording's own metres (y up).
ATHLETE = (0.01, -3.03)


def _feet(centre, *, floor: float, frames: int = 30) -> np.ndarray:
    """A window of two ankles standing around ``centre`` (x, z), swaying."""
    x, z = centre
    window = np.zeros((frames, 2, 3), dtype=np.float32)
    window[:, 0] = (x - 0.12, floor + 0.08, z)
    window[:, 1] = (x + 0.12, floor + 0.08, z)
    window[:, :, 2] += np.linspace(-0.05, 0.05, frames, dtype=np.float32)[:, None]
    return window


def _open_version(view: Skeleton3DView, window: np.ndarray, *, floor) -> None:
    """What the labelling page does when a version opens, in its order."""
    view.set_skeleton_spec(((0, 1),), 1)
    view.set_floor_height(floor)
    view.set_references(window, left_ankle=0, right_ankle=1)


def _grid_middle(view: Skeleton3DView) -> tuple[float, float, float]:
    lines = view._grid_data.reshape(-1, 3)
    middle = (lines.min(axis=0) + lines.max(axis=0)) / 2.0
    return float(middle[0]), float(middle[1]), float(middle[2])


def test_a_measured_floor_still_centres_the_grid_under_the_athlete(app) -> None:
    """The reported case: a detected floor, an athlete three metres out."""
    view = Skeleton3DView(load_tokens("dark"))
    _open_version(view, _feet(ATHLETE, floor=-0.78), floor=-0.78)
    x, height, z = _grid_middle(view)
    assert view.floor_source == "detected"
    # The measured plane decides the height, and only the height.
    assert height == pytest.approx(-0.78)
    assert (x, z) == pytest.approx(ATHLETE, abs=1e-4)


def test_the_next_version_gets_its_own_centre(app) -> None:
    """One view serves every version; the grid follows the version, not the
    first athlete it was ever shown."""
    view = Skeleton3DView(load_tokens("dark"))
    _open_version(view, _feet(ATHLETE, floor=-0.78), floor=-0.78)
    elsewhere = (0.63, -3.36)
    _open_version(view, _feet(elsewhere, floor=-0.95), floor=-0.95)
    x, height, z = _grid_middle(view)
    assert height == pytest.approx(-0.95)
    assert (x, z) == pytest.approx(elsewhere, abs=1e-4)


def test_without_a_measured_floor_the_grid_is_still_a_reference(app) -> None:
    """The path that already worked stays as it was: centred on the feet, at
    the lowest they reached, and not described as a detected floor."""
    view = Skeleton3DView(load_tokens("dark"))
    _open_version(view, _feet(ATHLETE, floor=-1.0), floor=None)
    x, height, z = _grid_middle(view)
    assert view.floor_source == "visual_reference"
    assert height == pytest.approx(-1.0 + 0.08)
    assert (x, z) == pytest.approx(ATHLETE, abs=1e-4)


# ------------------------------------------------------------------ the band


@pytest.fixture
def processed(workspace, session):
    return record_and_process(workspace, session)


@pytest.fixture
def screen(app, tmp_path, monkeypatch, processed, workspace):
    view, window, review = open_review(app, tmp_path, monkeypatch, processed, workspace)
    # Sized after it is shown, as the band's other tests do: showing
    # maximises the window onto the offscreen platform's own small screen,
    # and a band measured there is 748 px wide - not the screen in question.
    window.resize(*TARGET)
    app.processEvents()
    view._apply_stage_geometry()
    app.processEvents()
    assert view.editor_bar.width() > 1800
    yield view, window
    review.close()
    window.close()


def _movement_selected(view, app) -> str:
    sample_id = view.viewmodel.add_movement(2, 8)
    view._timeline_selected(sample_id)
    app.processEvents()
    return sample_id


def _fault_selected(view, app) -> str:
    _movement_selected(view, app)
    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    return interval


def _movement_actions(bar) -> list[QWidget]:
    return [
        bar.delete_movement_button,
        bar.exercise_classes.browse_button,
        bar.apply_all_button,
    ]


def _fault_actions(bar) -> list[QWidget]:
    return [
        bar.delete_error_button,
        bar.error_classes.browse_button,
        bar.edit_joints_button,
        bar.back_to_movement_button,
        bar.error_note_button,
    ]


def _assert_closes_the_line(bar, actions: list[QWidget]) -> None:
    """``actions`` are the last things on the interval line, in this order,
    one layout gap apart, with the last one on the line's right edge."""
    page = bar.modes.currentWidget()
    grid = page.layout()
    line = grid.itemAtPosition(1, 2).geometry()
    classes = grid.itemAtPosition(0, 2).geometry()
    gap = grid.itemAtPosition(1, 2).layout().spacing()

    boxes = [action.geometry() for action in actions]
    for action, box in zip(actions, boxes):
        assert action.isVisible(), action.text() or action.accessibleName()
        assert action.parentWidget() is page
        # The bottom row: on the interval line, below the classes.
        assert line.top() <= box.center().y() <= line.bottom()
        assert box.top() > classes.bottom()
    for before, after in zip(boxes, boxes[1:]):
        assert after.left() - before.right() - 1 == gap
    assert boxes[-1].right() == line.right()

    # Nothing else from the delete button onwards.
    intruders = [
        child.text() or child.accessibleName() or type(child).__name__
        for child in page.findChildren(QWidget)
        if child.parentWidget() is page
        and child.isVisible()
        and child not in actions
        and child.geometry().intersects(line)
        and child.geometry().right() >= boxes[0].left()
    ]
    assert intruders == []


def test_the_add_fault_button_is_gone(screen, app) -> None:
    view, _window = screen
    _movement_selected(view, app)
    bar = view.editor_bar
    assert not hasattr(bar, "add_error_button")
    assert not hasattr(view, "add_error_button")
    texts = [button.text() for button in bar.findChildren(QAbstractButton)]
    assert "Hata aralığı ekle" not in texts


def test_the_movement_actions_are_in_the_users_order(screen, app) -> None:
    """``sil · Diğer sınıflar · Sınıfsızlara uygula``, against the right edge."""
    view, _window = screen
    _movement_selected(view, app)
    assert view.editor_bar.mode == "movement"
    _assert_closes_the_line(view.editor_bar, _movement_actions(view.editor_bar))


def test_the_fault_actions_are_in_the_users_order(screen, app) -> None:
    """``sil · Diğer sınıflar · Eklemleri düzenle · Harekete dön · Not``."""
    view, _window = screen
    _fault_selected(view, app)
    assert view.editor_bar.mode == "fault"
    _assert_closes_the_line(view.editor_bar, _fault_actions(view.editor_bar))


def test_nothing_selected_keeps_the_same_order(screen, app) -> None:
    """The band opens on the movement editor with nothing selected; the row a
    person first sees is the same row, with delete off."""
    view, _window = screen
    view._label_icon_pressed()
    app.processEvents()
    bar = view.editor_bar
    _assert_closes_the_line(bar, _movement_actions(bar))
    assert not bar.delete_movement_button.isEnabled()
    assert bar.exercise_classes.browse_button.isEnabled()


@pytest.mark.parametrize("many", (False, True), ids=("all-fit", "overflow"))
def test_the_class_picker_is_always_there(screen, app, many) -> None:
    """The user's answer: shown whether or not a chip was left off, in both
    modes, so the delete button beside it never moves."""
    view, _window = screen
    bar = view.editor_bar
    count = 14 if many else 2
    bar.exercise_classes.set_options(
        tuple((f"c{i}", f"çok uzun bir hareket sınıfı adı {i}") for i in range(count))
    )
    bar.error_classes.set_options(tuple((f"f{i}", f"hata {i}") for i in range(count)))
    _movement_selected(view, app)
    strip = bar.exercise_classes
    assert (strip.hidden_count > 0) is many
    assert strip.browse_button.isVisible()
    assert strip.browse_button.text() == BROWSE_TEXT
    if many:
        assert str(strip.hidden_count) in strip.browse_button.toolTip()

    _fault_selected(view, app)
    assert bar.error_classes.browse_button.isVisible()
    assert bar.error_classes.browse_button.text() == BROWSE_TEXT


def test_the_chips_have_their_row_to_themselves(screen, app) -> None:
    """The picker left the class line, so it no longer takes room from the
    chips and no longer switches off with the strip by accident."""
    view, _window = screen
    _movement_selected(view, app)
    for strip in (view.editor_bar.exercise_classes, view.editor_bar.error_classes):
        assert strip.layout().indexOf(strip.browse_button) == -1
        assert not strip.isAncestorOf(strip.browse_button)


def test_the_class_picker_opens_every_class(screen, app) -> None:
    view, _window = screen
    _movement_selected(view, app)
    for name in ("çömelme", "hamle"):
        view.viewmodel.create_exercise(name)
    app.processEvents()
    view.editor_bar.exercise_classes.browse_button.click()
    app.processEvents()
    browser = view._exercise_browser
    assert browser.isVisible()
    assert browser.list.count() == len(view.viewmodel.exercise_options.value) >= 2
    browser.close()

    _fault_selected(view, app)
    view.editor_bar.error_classes.browse_button.click()
    app.processEvents()
    assert view._fault_browser.isVisible()
    view._fault_browser.close()


def test_the_picker_is_off_when_editing_is(screen, app) -> None:
    """It used to be switched off as part of the strip; it is not the strip's
    child any more, so the page switches it itself."""
    view, _window = screen
    browse = view.editor_bar.exercise_classes.browse_button
    view._set_editing_enabled(False)
    assert not browse.isEnabled()
    view._set_editing_enabled(True)
    assert browse.isEnabled()


def test_nothing_in_either_mode_is_clipped(screen, app) -> None:
    """Every word on both lines readable at the target. The fault line is the
    one that grew by a button."""
    view, _window = screen
    _movement_selected(view, app)
    assert clipped_controls(view.editor_bar) == []
    _fault_selected(view, app)
    assert clipped_controls(view.editor_bar) == []
