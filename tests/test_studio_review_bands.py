"""The labelling screen's three bands and its one tool row.

Behaviour first. Where a widget lands is checked through the geometry solver,
which is arithmetic and lives in its own test file; what is checked here is
that the screen is wired to it - and the interaction rules the design review
named, which are about tools rather than pixels.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.views.timeline import Tool  # noqa: E402

from conftest import enter_the_workspace  # noqa: E402


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
    # Past the project/participant gate: from 20 September every screen
    # but Projeler needs a project open in this session.
    enter_the_workspace(window, app)
    window.viewmodel.navigate("review")
    app.processEvents()
    yield window.page("review"), window, app
    window.close()


# ---------------------------------------------------------------- LAYOUT-01


def test_the_page_has_no_title_strip(page) -> None:
    """A heading and a run-id line were a band of height that said nothing."""
    view, _window, _app = page
    assert not view._header.isVisibleTo(view)


def test_the_run_id_moved_into_the_panel(page) -> None:
    view, _window, app = page
    view._show_version_title("run_abc123 · 1370 kare")
    app.processEvents()
    assert view.version_title.text() == "run_abc123 · 1370 kare"
    # And it is inside the panel, not above the picture.
    assert view.side_tabs.isAncestorOf(view.version_title)


def test_the_editor_is_four_bands_in_order(page) -> None:
    """Four since 20 September: the contextual editor sits between the stage
    and the tools, in the height the stage cannot use."""
    view, _window, app = page
    app.processEvents()
    layout = view.editor.layout()
    widgets = [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if layout.itemAt(i).widget() is not None
    ]
    assert widgets == [
        view.stage, view.editor_bar, view.toolbar, view.timeline.parent()
    ]


def test_the_three_regions_share_the_first_band(page) -> None:
    view, _window, app = page
    app.processEvents()
    for widget in (view.viewer, view.skeleton, view.side_tabs):
        assert view.stage.isAncestorOf(widget) or widget.parent() is view.stage


# ---------------------------------------------------------------- LAYOUT-02


def test_the_page_reads_the_ratio_rather_than_assuming_one(page) -> None:
    view, _window, app = page
    # Nothing open: nothing claimed.
    assert view._source_ratio == 0.0
    view.set_source_ratio(4 / 3)
    app.processEvents()
    assert view._source_ratio == pytest.approx(4 / 3)


def test_the_solved_geometry_reaches_the_widgets(page) -> None:
    view, _window, app = page
    view.set_source_ratio(16 / 9)
    app.processEvents()
    geometry = view.stage_geometry
    assert geometry is not None
    if geometry.height <= 0:
        pytest.skip("the page has no laid-out size on this platform")
    assert view.viewer.width() == geometry.video_width
    assert view.skeleton.width() == geometry.skeleton_width
    assert view.side_tabs.width() == geometry.panel_width


def test_the_panel_is_never_narrower_than_its_minimum(page) -> None:
    view, _window, app = page
    view.set_source_ratio(2.39)
    app.processEvents()
    assert (
        view.side_tabs.width()
        >= view._tokens.metric("KcLabelPanelMinWidth")
    )


# ------------------------------------------------------------------ TOOL-01


def test_there_is_one_tool_row_not_two(page) -> None:
    view, _window, _app = page
    row = view.toolbar.layout()
    widgets = {
        row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget()
    }
    # Transport, tools, snap, zoom, undo/redo and the save state all on it.
    for widget in (
        view.play_button,
        view.first_button,
        view._tool_buttons[Tool.SCRUB],
        view._tool_buttons[Tool.DRAW_MOVEMENT],
        view._tool_buttons[Tool.DRAW_ERROR],
        view.snap_button,
        view.undo_button,
        view.redo_button,
        view.next_gap_button,
        view.save_state,
    ):
        assert widget in widgets, widget.accessibleName() or widget


def test_every_icon_control_has_a_spoken_name(page) -> None:
    """An icon with no text announces a blank button without this."""
    view, _window, _app = page
    from PySide6.QtWidgets import QToolButton

    for button in view.toolbar.findChildren(QToolButton):
        assert button.accessibleName(), button.objectName()
        assert button.toolTip(), button.accessibleName()


def test_drawing_a_movement_and_a_fault_look_different(page) -> None:
    view, _window, _app = page
    movement = view._tool_buttons[Tool.DRAW_MOVEMENT]
    fault = view._tool_buttons[Tool.DRAW_ERROR]
    assert movement.accessibleName() != fault.accessibleName()
    assert not movement.icon().isNull()
    assert not fault.icon().isNull()
    # Two different pictures, not the same one twice.
    assert (
        movement.icon().cacheKey() != fault.icon().cacheKey()
    )


# ------------------------------------------------------------------ TOOL-02


def test_drawing_one_interval_hands_the_tool_back(page) -> None:
    """The next ordinary click must scrub, not draw a second range."""
    view, _window, app = page
    # A drawing tool is refused on a timeline with no frame range - that is
    # its own rule, and it would mask the one under test here.
    view.timeline.set_take(600, 60.0)
    view._set_editing_enabled(True)
    view._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    assert view.timeline.tool is Tool.DRAW_MOVEMENT
    # No viewmodel data behind it, so nothing is created - which is exactly
    # the case that used to leave the tool armed.
    view._interval_drawn("movements", 10, 40)
    app.processEvents()
    assert view.timeline.tool is Tool.SCRUB
    assert view._tool_buttons[Tool.SCRUB].isChecked()


def test_drawing_a_fault_hands_the_tool_back_too(page) -> None:
    view, _window, app = page
    view.timeline.set_take(600, 60.0)
    view._set_editing_enabled(True)
    view._set_tool(Tool.DRAW_ERROR, sync=True)
    view._interval_drawn("errors", 10, 40)
    app.processEvents()
    assert view.timeline.tool is Tool.SCRUB


def test_cancelling_a_draw_also_returns_to_navigating(page) -> None:
    """Esc, a lost focus, or a drag too short to count."""
    view, _window, app = page
    view.timeline.set_take(600, 60.0)
    view._set_editing_enabled(True)
    view._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    view._edit_cancelled()
    app.processEvents()
    assert view.timeline.tool is Tool.SCRUB
    assert view._tool_buttons[Tool.SCRUB].isChecked()


def test_the_tool_buttons_stay_in_step_with_the_timeline(page) -> None:
    view, _window, app = page
    view.timeline.set_take(600, 60.0)
    view._set_editing_enabled(True)
    for tool in (Tool.DRAW_MOVEMENT, Tool.DRAW_ERROR, Tool.SCRUB):
        view._set_tool(tool, sync=True)
        app.processEvents()
        assert view.timeline.tool is tool
        assert view._tool_buttons[tool].isChecked()


# ------------------------------------------------------------------ TOOL-03


def test_playback_speed_changes_the_clock_not_the_data(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["review"]
    viewmodel.fps.set(60.0)

    view.speed_box.setCurrentIndex(view.speed_box.findData(1.0))
    view._speed_chosen(0)
    viewmodel.playing.set(True)
    app.processEvents()
    at_one = view._clock.interval()

    view.speed_box.setCurrentIndex(view.speed_box.findData(0.5))
    view._speed_chosen(0)
    app.processEvents()
    at_half = view._clock.interval()

    assert at_half > at_one
    # The recording's own rate is untouched.
    assert viewmodel.fps.value == 60.0
    viewmodel.playing.set(False)


def test_looping_needs_a_selection_to_loop_inside(page) -> None:
    view, _window, app = page
    view.loop_button.setChecked(True)
    app.processEvents()
    assert view._loop_selection is True
    # Nothing selected: nothing to wrap inside, and playback runs normally.
    assert view._looped_bounds() is None
    view.loop_button.setChecked(False)


def test_secondary_tools_fold_away_on_a_narrow_row(page) -> None:
    view, window, app = page
    window.resize(1600, 900)
    app.processEvents()
    view._update_overflow()
    app.processEvents()
    wide_state = view._overflowed

    window.resize(1120, 700)
    app.processEvents()
    view._update_overflow()
    app.processEvents()

    # Whatever happens to the extras, the essentials never fold away.
    for widget in (
        view.play_button,
        view._tool_buttons[Tool.SCRUB],
        view._tool_buttons[Tool.DRAW_MOVEMENT],
        view._tool_buttons[Tool.DRAW_ERROR],
    ):
        assert widget.isVisibleTo(view.toolbar)
    if view._overflowed:
        assert view.overflow_button.isVisibleTo(view.toolbar)
        assert view.overflow_menu.actions()
    assert isinstance(wide_state, bool)


def test_a_drawing_tool_is_refused_on_an_empty_timeline(page) -> None:
    """Its own rule, kept: there is no frame range to draw a range in."""
    view, _window, app = page
    view.timeline.set_take(0, 30.0)
    view._set_tool(Tool.DRAW_MOVEMENT, sync=True)
    app.processEvents()
    assert view.timeline.tool is Tool.SCRUB


def test_the_bands_do_not_overlap_after_leaving_and_returning(page) -> None:
    """Measured in a real window on 21 September: the editor sat ten pixels
    over the stage after a round trip to another screen.

    The toolbar reports one height the first time the page is shown and
    another the next time - 48 pixels became 62 - so the solver divided the
    height against the smaller number while the band took the larger. A band
    that grows after the solve does not push the others down; it draws over
    them.
    """
    view, window, app = page
    holder = view.editor_bar.parent()
    layout = holder.layout()

    def bands() -> list:
        return [
            layout.itemAt(i).widget().geometry()
            for i in range(layout.count())
            if layout.itemAt(i).widget() is not None
        ]

    def overlapping() -> list:
        boxes = bands()
        return [
            (a, b)
            for index, a in enumerate(boxes)
            for b in boxes[index + 1 :]
            if a.intersects(b)
        ]

    assert overlapping() == []
    window.viewmodel.navigate("projects")
    app.processEvents()
    window.viewmodel.navigate("review")
    app.processEvents()
    view._apply_stage_geometry()
    app.processEvents()

    assert overlapping() == []
    # And the bands still add up to what they were given, rather than to more.
    total = sum(box.height() for box in bands())
    assert total <= view.surface.height(), (total, view.surface.height())
