"""Yakalama's one control row, and where "Bağlan" lives now.

The order in CAP-02 is a contract, not a suggestion: an operator reaches for
the record button without looking, and a readout that moves between sessions
is a readout nobody trusts. So the order is measured from the widgets' real
positions rather than from the code that added them.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.capture import CaptureMetrics  # noqa: E402

from conftest import enter_the_workspace


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
    window.viewmodel.navigate("capture")
    app.processEvents()
    yield window.page("capture"), window, app
    window.close()


def metrics(**overrides) -> CaptureMetrics:  # noqa: ANN003
    """A reading of the capture path. ``free_minutes`` is derived, not set."""
    defaults = dict(
        connected=False,
        recording=False,
        acquisition_fps=0.0,
        recorded_frames=0,
        recording_dropped=0,
        preview_dropped=0,
        free_bytes=0,
        elapsed_s=0.0,
    )
    defaults.update(overrides)
    return CaptureMetrics(**defaults)


# ------------------------------------------------------------------- CAP-01


def test_connect_sits_beside_the_record_button(page) -> None:
    """The 21 September user decision, which supersedes the header placement.

    The previous round moved connecting into the page header on the argument
    that it is a property of the machine rather than a step. The user's answer
    is that in practice it *is* the step before recording, so it is back in
    the transport row - immediately after "Kayda başla" and before the
    readouts that describe a take.
    """
    view, _window, app = page
    app.processEvents()
    row = view._transport_row
    widgets = [
        row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget()
    ]
    assert view.connect_button in widgets
    assert widgets.index(view.connect_button) == widgets.index(view.record_button) + 1

    record = view.record_button.mapTo(view, view.record_button.rect().center())
    connect = view.connect_button.mapTo(view, view.connect_button.rect().center())
    assert connect.x() > record.x()
    # One line with it, not a second row under it.
    assert abs(connect.y() - record.y()) <= 2


def test_connect_is_not_in_the_page_header(page) -> None:
    view, _window, app = page
    app.processEvents()
    header_bottom = view._subtitle.mapTo(view, view._subtitle.rect().bottomLeft()).y()
    button_top = (
        view.connect_button.mapTo(view, view.connect_button.rect().topLeft()).y()
    )
    assert button_top > header_bottom


def test_the_connection_is_said_in_colour_and_in_words(page) -> None:
    """Green while connected, and the wording changes with it.

    Since the status block left this screen the button is the only place the
    connection is stated, so it must not rest on hue alone.
    """
    view, _window, app = page
    view._show_metrics(metrics(connected=False))
    app.processEvents()
    assert view.connect_button.text() == "Bağlan"
    assert view.connect_button.property("kcConnected") == "idle"

    view._show_metrics(metrics(connected=True))
    app.processEvents()
    assert view.connect_button.text() == "Bağlantıyı kes"
    assert view.connect_button.property("kcConnected") == "connected"


# ------------------------------------------------------------------- CAP-02


def test_the_control_row_is_in_the_approved_order(page) -> None:
    view, _window, app = page
    app.processEvents()
    assert view.control_row_order() == view.CONTROL_ORDER


def test_everything_on_the_row_is_on_one_line(page) -> None:
    """Two rows is exactly what this change removed."""
    view, _window, app = page
    app.processEvents()
    items = [view.record_button, view.marker_button, *view.metrics_widgets.values()]
    tops = {w.mapTo(view, w.rect().topLeft()).y() for w in items}
    bottoms = {w.mapTo(view, w.rect().bottomLeft()).y() for w in items}
    # Different controls have different heights; what must hold is that every
    # one of them overlaps every other vertically, i.e. one band.
    assert max(tops) < min(bottoms), (sorted(tops), sorted(bottoms))


def test_the_readouts_are_vertically_centred_with_the_buttons(page) -> None:
    view, _window, app = page
    app.processEvents()
    items = [view.record_button, view.marker_button, *view.metrics_widgets.values()]
    centres = [w.mapTo(view, w.rect().center()).y() for w in items]
    assert max(centres) - min(centres) <= 2, centres


def test_a_telemetry_pair_does_not_form_a_second_row(page) -> None:
    """Caption and value side by side, not stacked."""
    view, _window, _app = page
    for key, widget in view.metrics_widgets.items():
        caption = widget._caption  # noqa: SLF001 - measuring the pair is the point
        value = widget._value  # noqa: SLF001
        assert caption.y() == value.y() or abs(caption.y() - value.y()) <= 2, key
        assert value.x() > caption.x(), key


def test_the_frame_count_survives_as_the_duration_detail(page) -> None:
    """CAP-02 allows it there; it may not become a seventh column."""
    view, _window, app = page
    view._show_metrics(metrics(connected=True, recorded_frames=1234, elapsed_s=12.0))
    app.processEvents()
    assert "1234" in view.metrics_widgets["elapsed"].toolTip()
    assert "recorded" not in view.metrics_widgets


def test_a_reserved_width_is_measured_in_the_font_that_is_used(page) -> None:
    """The floor has to follow the font, not the font at construction time.

    The theme's stylesheet reaches the application *after* the widgets are
    built, so a width measured in `__init__` is taken from the default face.
    For `preview_loss` that floor came out at 24 px while four mono digits
    need 28, and a count reaching four digits shoved the next readout four
    pixels sideways - exactly what the slot exists to prevent.

    An offscreen run cannot catch this: with no font database every glyph is
    the same tofu width, so the wrong measurement and the right one agree.
    """
    view, _window, app = page
    app.processEvents()
    for key, widget in view.metrics_widgets.items():
        value = widget._value
        needed = QFontMetrics(value.font()).horizontalAdvance(widget._sample)
        assert value.minimumWidth() >= needed, key


def test_the_countdown_slot_is_wide_enough_for_its_own_text(page) -> None:
    """A *fixed* width measured in the wrong font clips instead of shoving,
    which is the worse of the two failures."""
    view, _window, app = page
    app.processEvents()
    needed = QFontMetrics(view.countdown_label.font()).horizontalAdvance("00 sn")
    assert view.countdown_slot.width() >= needed


def test_the_row_does_not_move_when_a_number_grows(page) -> None:
    """A 9 becoming a 10 must not shove the next readout sideways."""
    view, _window, app = page
    view._show_metrics(metrics(connected=True, acquisition_fps=9.0, preview_dropped=9))
    app.processEvents()
    before = {
        key: widget.mapTo(view, widget.rect().topLeft()).x()
        for key, widget in view.metrics_widgets.items()
    }
    view._show_metrics(
        metrics(connected=True, acquisition_fps=60.0, preview_dropped=1234)
    )
    app.processEvents()
    after = {
        key: widget.mapTo(view, widget.rect().topLeft()).x()
        for key, widget in view.metrics_widgets.items()
    }
    assert before == after


# ------------------------------------------------------------------- CAP-03


def test_the_record_button_is_red_not_the_accent(page) -> None:
    view, _window, _app = page
    assert view.record_button.property("kcVariant") == "record"


def test_the_four_record_states_are_told_apart(page) -> None:
    view, window, app = page
    seen: dict[str, tuple[str, str]] = {}

    view._show_metrics(metrics(connected=True))
    app.processEvents()
    seen["idle"] = (view.record_state, view.record_button.text())

    view._show_metrics(metrics(connected=True, recording=True))
    app.processEvents()
    seen["recording"] = (view.record_state, view.record_button.text())

    viewmodel = window.viewmodel_for["capture"]
    viewmodel.stopping.set(True)
    view._show_metrics(metrics(connected=True, recording=True))
    app.processEvents()
    seen["stopping"] = (view.record_state, view.record_button.text())
    viewmodel.stopping.set(False)

    viewmodel.countdown.set(3)
    view._show_metrics(metrics(connected=True))
    app.processEvents()
    seen["counting"] = (view.record_state, view.record_button.text())
    viewmodel.countdown.set(0)

    assert seen["idle"][0] == "idle"
    assert seen["recording"][0] == "recording"
    assert seen["stopping"][0] == "stopping"
    assert seen["counting"][0] == "counting"
    # Four different states, four different sentences.
    assert len({text for _state, text in seen.values()}) == 4


def test_the_button_is_disabled_while_the_take_is_closing(page) -> None:
    view, window, app = page
    viewmodel = window.viewmodel_for["capture"]
    viewmodel.stopping.set(True)
    view._show_metrics(metrics(connected=True, recording=True))
    app.processEvents()
    assert not view.record_button.isEnabled()
    viewmodel.stopping.set(False)


def test_the_two_loss_counters_never_share_a_source(page) -> None:
    view, _window, app = page
    view._show_metrics(
        metrics(connected=True, recording_dropped=7, preview_dropped=93)
    )
    app.processEvents()
    assert view.metrics_widgets["recording_loss"]._value.text().strip() == "7"  # noqa: SLF001
    assert view.metrics_widgets["preview_loss"]._value.text().strip() == "93"  # noqa: SLF001


def test_recording_loss_is_marked_when_it_is_not_zero(page) -> None:
    view, _window, app = page
    view._show_metrics(metrics(connected=True, recording_dropped=0))
    app.processEvents()
    assert not view.metrics_widgets["recording_loss"]._value.property("kcStatus")  # noqa: SLF001
    view._show_metrics(metrics(connected=True, recording_dropped=4))
    app.processEvents()
    assert (
        view.metrics_widgets["recording_loss"]._value.property("kcStatus") == "error"  # noqa: SLF001
    )


def test_a_counter_is_not_reset_by_a_repaint(page) -> None:
    view, _window, app = page
    view._show_metrics(metrics(connected=True, recording_dropped=5, preview_dropped=6))
    app.processEvents()
    for _ in range(3):
        view._show_metrics(
            metrics(connected=True, recording_dropped=5, preview_dropped=6)
        )
        app.processEvents()
    assert view.metrics_widgets["recording_loss"]._value.text().strip() == "5"  # noqa: SLF001
    assert view.metrics_widgets["preview_loss"]._value.text().strip() == "6"  # noqa: SLF001


# --------------------------------------------------- the console still fits


def test_the_console_does_not_overlap_its_own_controls(page) -> None:
    """A QVBoxLayout given less than its minimum overlaps rather than clips.

    Measured on 19 September: "Süre sonunda dur" was printed through
    "Önizlemeyi aynala". The console became a scroll area, and on 20 September
    scrolling was ruled out as well - a control that has to be scrolled to
    during a recording is a control that is not there. It now becomes two
    columns instead, so its contents keep their own rectangles at any height.
    """
    view, _window, app = page
    app.processEvents()
    controls = [
        view.countdown_box,
        view.duration_box,
        view.mirror_box,
        view.guides_box,
    ]
    rects = [
        (c.mapTo(view.console, c.rect().topLeft()).y(), c.height(), c)
        for c in controls
    ]
    rects.sort()
    for (top, height, first), (next_top, _h, second) in zip(rects, rects[1:]):
        assert top + height <= next_top, (
            f"{type(first).__name__} overlaps {type(second).__name__}"
        )


def test_the_console_keeps_a_readable_width(page) -> None:
    """Not a fixed number any more: a share, between two readable limits.

    The picture is given exactly the width its own aspect ratio can use, and
    the console takes what is left - which on a wide window is more than the
    360 pixels it used to be nailed to, and never more than a settings column
    can use.
    """
    from kinecapture.studio.services.capture_layout import (
        CONSOLE_MAX_WIDTH,
        CONSOLE_MIN_WIDTH,
    )

    view, _window, app = page
    app.processEvents()
    stage = view.stage_geometry
    assert stage is not None
    columns = stage.console_columns
    assert CONSOLE_MIN_WIDTH * columns <= view.console.width()
    assert view.console.width() <= CONSOLE_MAX_WIDTH * columns + 40


def test_the_camera_image_got_the_height_the_second_row_used_to_take(page) -> None:
    """The point of merging the rows. One row is worth ~40px of picture."""
    view, _window, app = page
    app.processEvents()
    row_height = max(
        view.record_button.height(),
        *(w.height() for w in view.metrics_widgets.values()),
    )
    # The whole control band is one control tall plus its own margins, not two.
    band_top = min(
        w.mapTo(view, w.rect().topLeft()).y()
        for w in (view.record_button, *view.metrics_widgets.values())
    )
    band_bottom = max(
        w.mapTo(view, w.rect().bottomLeft()).y()
        for w in (view.record_button, *view.metrics_widgets.values())
    )
    assert band_bottom - band_top <= row_height + 4


def test_the_countdown_does_not_move_the_row(page) -> None:
    """Starting a countdown used to push FPS and both loss counters right."""
    view, window, app = page
    viewmodel = window.viewmodel_for["capture"]
    view._show_metrics(metrics(connected=True))
    app.processEvents()
    before = {
        key: widget.mapTo(view, widget.rect().topLeft()).x()
        for key, widget in view.metrics_widgets.items()
    }
    before["marker"] = view.marker_button.mapTo(
        view, view.marker_button.rect().topLeft()
    ).x()

    viewmodel.countdown.set(10)
    view._show_metrics(metrics(connected=True))
    app.processEvents()
    assert view.countdown_label.isVisible()
    after = {
        key: widget.mapTo(view, widget.rect().topLeft()).x()
        for key, widget in view.metrics_widgets.items()
    }
    after["marker"] = view.marker_button.mapTo(
        view, view.marker_button.rect().topLeft()
    ).x()
    viewmodel.countdown.set(0)
    assert before == after


def test_a_readout_value_is_coloured_rather_than_boxed(page) -> None:
    """A pill around a two-character figure reads as a clipped control."""
    view, _window, app = page
    view._show_metrics(metrics(connected=True, recording_dropped=2))
    app.processEvents()
    value = view.metrics_widgets["recording_loss"]._value  # noqa: SLF001
    assert value.property("kcRole") == "mono"
    assert value.property("kcStatus") == "error"
    # The rule that neutralises the pill for a mono value has to exist.
    from kinecapture.studio.theme import stylesheet_for

    sheet = stylesheet_for("dark")
    assert 'QLabel[kcRole="mono"][kcStatus="error"]' in sheet
