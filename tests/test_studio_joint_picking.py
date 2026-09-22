"""Picking a joint by pointing at it, through the events a person generates.

The 20 September audit's objection to the previous round is the reason this
file exists in this shape: the joint-selection tests called
``_joint_picked(index)`` directly, which proves the data path and says nothing
about whether a double click on a node reaches it. So every test here goes
through ``QTest`` - press, move, double click - at the pixel the joint is
actually projected to, and the projection is asked of the widget rather than
recomputed, so a test cannot agree with a broken view.

What that catches, and a direct call cannot:

* a hit radius that grows with the display scaling while the node does not;
* a drag that ends in a double click marking a joint by accident;
* a click on empty space inventing the nearest joint;
* NaN joints - the ones a tracker did not find - becoming pickable points.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.processing.annotations import RolesOrigin  # noqa: E402

from _gui_harness import (  # noqa: E402
    aim_at_joint,
    double_click,
    drag,
    joint_screen_position,
    named_joints,
    open_review,
    record_and_process,
    use_known_pose,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def processed(workspace, session):
    return record_and_process(workspace, session)


@pytest.fixture
def screen(app, tmp_path, monkeypatch, processed, workspace):
    view, window, review = open_review(
        app, tmp_path, monkeypatch, processed, workspace
    )
    use_known_pose(view, app)
    yield view, window, app
    review.close()
    window.close()


@pytest.fixture
def drafting(screen):
    """A fault selected and a class name typed: the draft is open."""
    view, window, app = screen
    view.viewmodel.add_movement(2, 8)
    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    view.editor_bar.error_classes.new_name.setText("dizde valgus")
    app.processEvents()
    return view, window, app, interval


def a_visible_joint(view, app=None) -> tuple[int, float, float]:
    """One named joint that can be aimed at without ambiguity."""
    return aim_at_joint(view, set(named_joints(view)), app)


def isolated_joints(view, app=None) -> list[tuple[int, float, float]]:
    """Several such joints, found one at a time as the view zooms in."""
    found: list[tuple[int, float, float]] = []
    taken: set[int] = set()
    wanted = set(named_joints(view))
    for _ in range(3):
        remaining = wanted - taken
        if not remaining:
            break
        index, x, y = aim_at_joint(view, remaining, app)
        taken.add(index)
        found.append((index, x, y))
    return found


# ------------------------------------------------------------- the gate


def test_picking_is_off_until_a_class_is_being_defined(screen) -> None:
    """A double click meant for the camera must not edit anatomy."""
    view, _window, app = screen
    assert not view.skeleton.is_picking
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    assert view._draft_joints == []


def test_typing_a_name_opens_a_visible_picking_state(drafting) -> None:
    """R-03 asks for an explicit state, not a hint somewhere below.

    "Visible" is asserted as visibility. Both earlier attempts set the text
    and drew nothing - a `QPainter` over a `QOpenGLWidget` reaches a surface
    nobody displays - and a test that only read the string would have passed
    through all of it.
    """
    view, _window, _app, _interval = drafting
    assert view.skeleton.is_picking
    assert "çift tık" in view.skeleton.picking_note.lower()
    banner = view.skeleton._picking_label
    assert banner.isVisible()
    assert banner.text() == view.skeleton.picking_note
    assert banner.width() > 100 and banner.height() > 10
    assert not view.editor_bar.error_classes.add_button.isEnabled()


def test_closing_the_draft_takes_the_banner_away(drafting) -> None:
    view, _window, app, _interval = drafting
    view.editor_bar.error_classes.new_name.clear()
    app.processEvents()
    assert not view.skeleton._picking_label.isVisible()


def test_opening_the_draft_stops_playback(drafting) -> None:
    """Picking on a moving body is picking whatever was under the pointer."""
    view, _window, app = drafting[0], drafting[1], drafting[2]
    view.viewmodel.playing.set(True)
    view.editor_bar.error_classes.new_name.clear()
    app.processEvents()
    view.editor_bar.error_classes.new_name.setText("başka sınıf")
    app.processEvents()
    assert not view.viewmodel.playing.value


def test_clearing_the_name_closes_the_draft_and_the_state(drafting) -> None:
    view, _window, app, _interval = drafting
    view.editor_bar.error_classes.new_name.clear()
    app.processEvents()
    assert not view.skeleton.is_picking
    assert view.skeleton.picking_note == ""
    assert view._draft_joints == []


# --------------------------------------------------- real double clicks


def test_a_real_double_click_on_a_node_selects_that_joint(drafting) -> None:
    """The assertion the previous round could not make."""
    view, _window, app, _interval = drafting
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    assert view._draft_joints == [index]
    assert view.editor_bar.error_classes.add_button.isEnabled()


def test_a_second_double_click_takes_the_joint_off_again(drafting) -> None:
    view, _window, app, _interval = drafting
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    double_click(view.skeleton, x, y)
    app.processEvents()
    assert view._draft_joints == []
    assert not view.editor_bar.error_classes.add_button.isEnabled()


def test_several_joints_can_be_selected(drafting) -> None:
    view, _window, app, _interval = drafting
    # Clicked as each is found: the helper zooms between finds, so a position
    # collected earlier may no longer be where that joint is.
    aimed = []
    for _ in range(3):
        index, x, y = aim_at_joint(
            view, set(named_joints(view)) - set(aimed), app
        )
        double_click(view.skeleton, x, y)
        app.processEvents()
        aimed.append(index)
    assert set(view._draft_joints) == set(aimed)
    assert "3 seçildi" in view.skeleton.picking_note


def test_clicking_empty_space_picks_nothing(drafting) -> None:
    """It must not invent the nearest joint."""
    view, _window, app, _interval = drafting
    double_click(view.skeleton, 4, 4)
    app.processEvents()
    assert view._draft_joints == []


def test_a_drag_that_ends_in_a_double_click_does_not_select(drafting) -> None:
    """Turning the camera is the commonest thing to do in this view."""
    view, _window, app, _interval = drafting
    _index, x, y = a_visible_joint(view, app)
    drag(view.skeleton, (x - 70, y), (x, y))
    app.processEvents()
    double_click(view.skeleton, x, y)
    app.processEvents()
    assert view._draft_joints == []


def test_turning_the_camera_still_works_while_picking(drafting) -> None:
    """Both at once is the normal case: turn to see the joint, then pick it."""
    view, _window, app, _interval = drafting
    before = view.skeleton.camera.azimuth
    drag(view.skeleton, (200, 200), (280, 200))
    app.processEvents()
    assert view.skeleton.camera.azimuth != before


# ------------------------------------------------------- the hit radius


@pytest.mark.parametrize("ratio", [1.0, 1.5, 2.0])
def test_the_hit_radius_is_the_same_on_the_page_at_any_scaling(
    screen, ratio, monkeypatch
) -> None:
    """It used to be multiplied by the device ratio while the coordinates
    stayed logical, so at 150% a click well away from a node still marked it.
    """
    view, _window, app = screen
    monkeypatch.setattr(
        type(view.skeleton), "devicePixelRatioF", lambda _self: ratio
    )
    index, x, y = a_visible_joint(view, app)
    from kinecapture.studio.views.skeleton3d import PICK_RADIUS_PX

    assert view.skeleton.joint_at(x, y) == index
    # Just outside the radius: not a hit, whatever the scaling.
    assert view.skeleton.joint_at(x + PICK_RADIUS_PX + 6, y) != index


def test_a_joint_the_tracker_did_not_find_is_not_pickable(screen) -> None:
    """NaN is missing data. A pickable point there would be an invention."""
    view, _window, app = screen
    pose = view.skeleton._joints.copy()
    index, x, y = a_visible_joint(view, app)
    pose[index] = np.nan
    view.skeleton.set_joints(pose)
    app.processEvents()
    assert view.skeleton.joint_at(x, y) != index


# ------------------------------------------------- creating and applying


def test_a_created_class_is_stored_with_the_joints_that_were_pointed_at(
    drafting,
) -> None:
    view, _window, app, interval = drafting
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    role = view._role_names([index])[0]

    view.editor_bar.error_classes.add_button.click()
    app.processEvents()

    option = view.viewmodel._schema.match_error_type("dizde valgus")
    assert option is not None
    assert role in option.default_roles

    row = view.viewmodel.error_row(interval)
    assert row.error_class == option.code
    assert role in row.roles
    assert row.roles_origin is RolesOrigin.REVIEWED


def test_the_draft_closes_once_the_class_is_stored(drafting) -> None:
    view, _window, app, _interval = drafting
    _index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    view.editor_bar.error_classes.add_button.click()
    app.processEvents()
    assert not view.skeleton.is_picking
    assert view.skeleton.picking_note == ""
    assert view.editor_bar.error_classes.new_name.text() == ""


def test_the_editor_stays_open_on_the_interval_that_prompted_the_class(
    drafting,
) -> None:
    view, _window, app, interval = drafting
    _index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    view.editor_bar.error_classes.add_button.click()
    app.processEvents()
    assert view.editor_bar.mode == "fault"
    assert view.viewmodel.selected_error.value == interval


def test_applying_a_known_class_does_not_ask_for_joints_again(drafting) -> None:
    """JOINT-04: the anatomical question is asked once per class."""
    view, _window, app, first = drafting
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    view.editor_bar.error_classes.add_button.click()
    app.processEvents()
    code = view.viewmodel.error_row(first).error_class
    role = view._role_names([index])[0]

    second = view.viewmodel.add_error(6, 7)
    view._timeline_selected(second)
    app.processEvents()
    view.editor_bar.error_classes._choose(code)
    app.processEvents()

    row = view.viewmodel.error_row(second)
    assert role in row.roles
    assert row.roles_origin is RolesOrigin.CLASS_DEFAULT
    assert not view.skeleton.is_picking


def test_the_joints_are_shown_as_words_not_a_checkbox_list(drafting) -> None:
    view, _window, app, _interval = drafting
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    view.editor_bar.error_classes.add_button.click()
    app.processEvents()
    role = view._role_names([index])[0].replace("_", " ")
    assert role in view.editor_bar.joint_summary.text()
    assert "seçildi" in view.editor_bar.joint_origin.fullText()


def test_the_selection_survives_reopening_the_version(
    app, tmp_path, monkeypatch, processed, workspace
) -> None:
    """A class that is not there next time was never really stored."""
    view, window, review = open_review(
        app, tmp_path, monkeypatch, processed, workspace
    )
    use_known_pose(view, app)
    view.viewmodel.add_movement(2, 8)
    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    view.editor_bar.error_classes.new_name.setText("kalıcı sınıf")
    app.processEvents()
    index, x, y = a_visible_joint(view, app)
    double_click(view.skeleton, x, y)
    app.processEvents()
    view.editor_bar.error_classes.add_button.click()
    app.processEvents()
    role = view._role_names([index])[0]
    assert view.viewmodel.flush()
    review.close()
    window.close()

    view2, window2, review2 = open_review(
        app, tmp_path, monkeypatch, processed, workspace
    )
    try:
        rows = view2.viewmodel.errors.value
        assert rows, "the fault interval did not survive"
        assert role in rows[0].roles
        option = view2.viewmodel._schema.match_error_type("kalıcı sınıf")
        assert option is not None and role in option.default_roles
    finally:
        review2.close()
        window2.close()
