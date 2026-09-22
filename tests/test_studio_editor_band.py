"""The height the screen was throwing away, and the panel that scrolled.

Two measurements, both taken on the real screen with a real version open,
because both were rejected as *observations* rather than as opinions:

* at 1900x970 the labelling screen left roughly 135 px of empty band under the
  timeline while the fault editor's frame boxes were below a fold;
* the right-hand panel scrolled by 319 px for a movement, 124 for a fault,
  136 for the camera and 124 for the summary.

So the tests are arithmetic on the real widgets. "Looks better" is not a
result; "no scroll range anywhere in the panel, at four window sizes, with a
long Turkish class name and twelve classes" is.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from kinecapture.studio.services.stage_layout import solve_stage  # noqa: E402
from kinecapture.studio.views.annotationbar import (  # noqa: E402
    BROWSE_TEXT,
    VISIBLE_CLASSES,
    AnnotationEditorBar,
)

from _gui_harness import (  # noqa: E402
    clipped_controls,
    open_review,
    record_and_process,
    scroll_census,
)

#: The sizes the acceptance brief names, plus the window's own minimum.
SIZES = ((1920, 1080), (1600, 900), (1366, 768), (1129, 700))


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
    yield view, window, app
    review.close()
    window.close()


def a_movement(view, start: int = 2, end: int = 8) -> str:
    return view.viewmodel.add_movement(start, end)


# ------------------------------------------------------- the solver's share


def test_the_height_the_stage_cannot_use_goes_to_the_editor() -> None:
    """The arithmetic behind the rejected empty band, stated directly.

    At the audit's window the widths allow a 498 px stage while the height
    would have allowed 634. The 136 px difference used to be a margin.
    """
    geometry = solve_stage(
        available_width=1852,
        available_height=830,
        source_ratio=320 / 180,
        panel_min_width=300,
        timeline_min_height=148,
        toolbar_height=48,
        stage_min_height=260,
        editor_min_height=96,
        editor_max_height=220,
    )
    assert geometry.height == 498
    assert geometry.editor_height == 136
    assert geometry.slack_height == 0


def test_the_editor_and_timeline_keep_room_when_the_stage_floor_cannot_fit() -> None:
    """The preferred picture height must not force the bands to overlap."""
    geometry = solve_stage(
        available_width=1100,
        available_height=520,
        source_ratio=16 / 9,
        panel_min_width=300,
        timeline_min_height=148,
        toolbar_height=48,
        stage_min_height=260,
        editor_min_height=96,
        editor_max_height=220,
    )
    assert geometry.height > 0
    assert geometry.editor_height >= 96
    assert geometry.height + geometry.editor_height + 148 + 48 <= 520


def test_a_taller_window_buys_a_bigger_editor_not_a_bigger_margin() -> None:
    short = solve_stage(
        available_width=1852, available_height=830, source_ratio=320 / 180,
        panel_min_width=300, timeline_min_height=148, toolbar_height=48,
        stage_min_height=260, editor_min_height=96, editor_max_height=220,
    )
    tall = solve_stage(
        available_width=1852, available_height=940, source_ratio=320 / 180,
        panel_min_width=300, timeline_min_height=148, toolbar_height=48,
        stage_min_height=260, editor_min_height=96, editor_max_height=220,
    )
    assert tall.editor_height > short.editor_height


def test_the_editor_has_a_ceiling_and_the_rest_is_reported_as_slack() -> None:
    """Honesty about the residue: past the ceiling the band would be a wide
    empty box, and pretending otherwise would hide a real leftover."""
    geometry = solve_stage(
        available_width=1852, available_height=1400, source_ratio=320 / 180,
        panel_min_width=300, timeline_min_height=148, toolbar_height=48,
        stage_min_height=260, editor_min_height=96, editor_max_height=220,
    )
    assert geometry.editor_height == 220
    assert geometry.slack_height > 0


# ------------------------------------------------------- on the real screen


def test_the_screen_has_no_band_of_unused_height(screen) -> None:
    view, _window, app = screen
    app.processEvents()
    spacing = view._tokens.metric("KcSpacingSm")
    used = (
        view.stage.height()
        + view.editor_bar.height()
        + view.toolbar.height()
        + view.timeline.height()
        + spacing * 3
    )
    wasted = view.surface.height() - used
    # A few pixels of rounding is a layout; 135 is a design decision.
    assert wasted <= 24, f"{wasted} px unused"


def test_the_editor_band_is_on_screen_and_has_room(screen) -> None:
    view, _window, app = screen
    app.processEvents()
    assert view.editor_bar.isVisible()
    assert view.editor_bar.height() >= view.editor_bar.minimumSizeHint().height()


@pytest.mark.parametrize("size", SIZES)
def test_the_top_panel_never_scrolls(screen, size) -> None:
    """R-02, as a measurement rather than an intention.

    Checked in all three views and at every supported size. A hidden
    scrollbar would still fail this: what is asserted is that no content is
    out of reach, which is what a non-zero range means.
    """
    view, window, app = screen
    window.resize(*size)
    app.processEvents()
    view._apply_stage_geometry()
    app.processEvents()
    for key in ("camera", "labels", "subject"):
        view.side_tabs.show_view(key)
        app.processEvents()
        found = scroll_census(view.side_tabs)
        assert found == [], f"{key} @ {size}: {found}"


@pytest.mark.parametrize("size", SIZES)
def test_the_editor_band_never_scrolls(screen, size) -> None:
    """A band that scrolled would have moved the problem, not solved it."""
    view, window, app = screen
    window.resize(*size)
    app.processEvents()
    view._apply_stage_geometry()
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert scroll_census(view.editor_bar) == []

    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    assert scroll_census(view.editor_bar) == []


def test_only_the_label_summary_may_scroll(screen) -> None:
    """The 21 September user decision, which supersedes the earlier ban.

    The old rule was "no scroll area anywhere in this panel". It was kept by
    moving the forms into the band below, and that part stands. What it could
    not solve is the label summary: twenty movements do not fit any fixed
    height, and a ``QVBoxLayout`` that is short of room squeezes its children
    rather than hiding them. So exactly one tab may scroll, without a visible
    bar, and the other two still have to fit.
    """
    view, _window, app = screen
    app.processEvents()
    areas = [
        area for area in view.side_tabs.findChildren(QScrollArea)
        if area.isVisible()
    ]
    assert areas == [view.summary_scroll]
    for bar in (
        view.summary_scroll.verticalScrollBar(),
        view.summary_scroll.horizontalScrollBar(),
    ):
        assert not bar.isVisible()

    for key in ("camera", "subject"):
        view.side_tabs.show_view(key)
        app.processEvents()
        assert scroll_census(view.side_tabs) == []
    view.side_tabs.show_view("labels")
    app.processEvents()


# ------------------------------------------------------------- the two modes


def test_selecting_a_movement_opens_the_movement_editor(screen) -> None:
    view, _window, app = screen
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert view.editor_bar.mode == "movement"
    assert view.editor_bar.movement_start.value() == 2
    assert view.editor_bar.movement_end.value() == 8


def test_selecting_a_fault_opens_the_fault_editor(screen) -> None:
    view, _window, app = screen
    a_movement(view)
    interval = view.viewmodel.add_error(3, 5)
    view._timeline_selected(interval)
    app.processEvents()
    assert view.editor_bar.mode == "fault"
    assert view.editor_bar.error_start.value() == 3


def test_nothing_selected_still_shows_the_movement_editor(screen) -> None:
    """The 21 September decision: opening Etiketleme must not show an empty
    band with one sentence in it.

    With nothing selected the band shows the movement editor with its class
    strip live - a class can be created or chosen before an interval exists -
    and everything that edits *an interval* disabled, because there is none.
    """
    view, _window, app = screen
    view._label_icon_pressed()
    app.processEvents()
    assert view.editor_bar.mode == ""
    assert view.editor_bar.modes.currentIndex() == 0
    assert view.editor_bar.exercise_classes.isVisible()
    assert view.editor_bar.exercise_classes.new_name.isEnabled()
    for control in view.editor_bar._movement_controls:
        assert not control.isEnabled()
    assert view.editor_bar.movement_title.fullText() == "Hareket seçilmedi"


def test_the_frame_boxes_are_reachable_without_scrolling(screen) -> None:
    """They were below the fold. That is the specific complaint."""
    view, _window, app = screen
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    for box in (view.editor_bar.movement_start, view.editor_bar.movement_end):
        assert box.isVisible()
        assert box.visibleRegion().boundingRect().height() >= box.height() - 1


def test_the_movement_list_is_not_repeated_above_every_editor(screen) -> None:
    """One row of content used to occupy a third of the panel's height."""
    view, _window, _app = screen
    assert not hasattr(view, "movement_list")


def test_the_checkbox_joint_list_is_gone_from_the_main_flow(screen) -> None:
    view, _window, _app = screen
    assert not hasattr(view, "role_list")
    assert hasattr(view.editor_bar, "joint_summary")


# --------------------------------------------------------- classes and width


def test_many_classes_do_not_turn_the_band_into_a_list(screen) -> None:
    """A project with a full vocabulary is the normal case, not the edge."""
    view, _window, app = screen
    # The strip lives on the movement page of the band's stack, so it has to
    # be the page on screen before "is it visible" means anything.
    view._timeline_selected(a_movement(view))
    options = tuple(
        (f"c{i}", f"çok uzun bir hareket sınıfı adı {i}") for i in range(14)
    )
    strip = view.editor_bar.exercise_classes
    strip.set_options(options)
    app.processEvents()
    # The capacity is measured from this band's real width and these names'
    # real widths, so the count is not a constant any more. What it must never
    # do is show all fourteen, wrap to a second row, or scroll.
    shown = len(strip.visible_codes)
    assert 0 < shown < len(options)
    assert strip.hidden_count == len(options) - shown
    assert strip.browse_button.isVisible()
    assert strip.browse_button.text() == BROWSE_TEXT
    assert scroll_census(view.editor_bar) == []
    # One row: every chip shares a top edge with the first one.
    tops = {button.y() for button in strip._buttons.values()}
    assert len(tops) == 1


def test_the_applied_class_is_always_one_of_the_buttons(screen) -> None:
    """A class on this interval that was not on the band would read as none."""
    view, _window, app = screen
    options = tuple((f"c{i}", f"sınıf {i}") for i in range(14))
    strip = view.editor_bar.exercise_classes
    strip.set_options(options)
    strip.set_selected("c12")
    app.processEvents()
    assert "c12" in strip._buttons


@pytest.mark.parametrize("size", SIZES)
def test_nothing_in_the_band_is_clipped(screen, size) -> None:
    view, window, app = screen
    window.resize(*size)
    app.processEvents()
    view._apply_stage_geometry()
    sample_id = a_movement(view)
    view._timeline_selected(sample_id)
    app.processEvents()
    assert clipped_controls(view.editor_bar) == []


def test_the_bar_alone_fits_the_narrowest_supported_window(app) -> None:
    """Measured on the widget itself, so a regression is caught before the
    whole screen has to be built."""
    from kinecapture.studio.theme import load_tokens

    bar = AnnotationEditorBar(load_tokens("dark"))
    assert bar.minimumSizeHint().width() <= 1129
