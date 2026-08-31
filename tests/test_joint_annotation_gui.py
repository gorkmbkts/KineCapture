"""Marking which joints an error is about, through the real dialog.

The interaction has one property that is easy to get backwards and expensive to
get wrong: a front view mirrors the athlete, so the athlete's left knee is on
the *viewer's right*. Several tests here exist only to pin that down.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.domain.enums import JointAnnotationStatus  # noqa: E402
from kinecapture.domain.labels import LabelSchema  # noqa: E402
from kinecapture.domain.project import ErrorInterval  # noqa: E402
from kinecapture.gui.theme import build_stylesheet, get_theme  # noqa: E402
from kinecapture.gui.widgets.joint_picker import (  # noqa: E402
    JointRolePicker,
    describe_joint_annotation,
    role_label,
)
from kinecapture.gui.widgets.label_dialogs import ErrorLabelDialog  # noqa: E402
from kinecapture.visualization.skeleton_spec import (  # noqa: E402
    try_get_skeleton_spec,
)

FORMATS = ["zed_body_18", "zed_body_34", "zed_body_38", "mock_16"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def click(widget, point: QPointF) -> None:
    widget.mousePressEvent(
        QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )


def make_picker(qapp, fmt="zed_body_34", theme_name="dark"):
    picker = JointRolePicker(get_theme(theme_name), try_get_skeleton_spec(fmt))
    picker.resize(360, 470)
    picker.show()
    qapp.processEvents()
    return picker


# ------------------------------------------------------------- topologies


@pytest.mark.parametrize("fmt", FORMATS)
def test_the_picker_offers_exactly_the_roles_the_format_has(qapp, fmt) -> None:
    """The take's own spec decides, not the app's current capture setting."""
    from kinecapture.features.roles import resolve_roles

    spec = try_get_skeleton_spec(fmt)
    picker = make_picker(qapp, fmt)
    resolved = resolve_roles(spec)

    for role in picker.available_roles:
        assert resolved[role] is not None, f"{role} is not in {fmt}"
    for role in picker.unavailable_roles:
        assert (
            resolved.get(role) is None or role not in picker.available_roles
        ), f"{role} should have been offered"
    assert picker.available_roles, f"{fmt} must offer something"
    assert not picker.grab().isNull()
    picker.hide()


def test_body_18_has_no_pelvis_and_body_34_does(qapp) -> None:
    """A concrete difference, so the per-format wiring is really exercised."""
    eighteen = make_picker(qapp, "zed_body_18")
    assert "pelvis" not in eighteen.available_roles
    assert "left_knee" in eighteen.available_roles
    eighteen.hide()

    thirty_four = make_picker(qapp, "zed_body_34")
    assert "pelvis" in thirty_four.available_roles
    assert "left_heel" in thirty_four.available_roles
    thirty_four.hide()


def test_switching_format_drops_roles_the_new_one_cannot_express(qapp) -> None:
    picker = make_picker(qapp, "zed_body_34")
    picker.set_selected_roles(["pelvis", "left_knee"])
    assert set(picker.selected_roles()) == {"pelvis", "left_knee"}

    picker.set_spec(try_get_skeleton_spec("zed_body_18"))
    assert picker.selected_roles() == ("left_knee",), (
        "a target this format has no joint for must not survive"
    )
    picker.hide()


def test_non_target_joints_are_counted_not_hidden(qapp) -> None:
    """They stay in the export; they are simply not clickable here."""
    picker = make_picker(qapp, "zed_body_38")
    spec = try_get_skeleton_spec("zed_body_38")
    assert picker.non_target_joint_count > 0
    assert (
        picker.non_target_joint_count + len(picker.available_roles)
        == spec.num_joints
    )
    picker.hide()


# ------------------------------------------------------- the athlete's sides


def test_the_athletes_left_is_drawn_on_the_viewers_right(qapp) -> None:
    """A front view mirrors; getting this backwards marks the wrong knee."""
    picker = make_picker(qapp)
    left = picker._point("left_knee")
    right = picker._point("right_knee")
    centre = picker._figure_rect().center().x()

    assert left.x() > centre, "the athlete's left knee sits right of centre"
    assert right.x() < centre, "and the athlete's right knee left of centre"
    assert abs((left.x() - centre) - (centre - right.x())) < 2.0, "symmetric"
    picker.hide()


def test_clicking_the_right_half_selects_the_athletes_left(qapp) -> None:
    picker = make_picker(qapp)
    point = picker._point("left_knee")
    click(picker, point)
    assert picker.selected_roles() == ("left_knee",)
    assert role_label("left_knee") == "Sol diz"
    picker.hide()


def test_the_figure_says_whose_left_is_whose(qapp) -> None:
    picker = make_picker(qapp)
    image = picker.grab()
    assert not image.isNull()
    # The band is reserved above the figure, so the labels cannot be clipped.
    assert picker._figure_rect().top() >= 20
    picker.hide()


# ---------------------------------------------------------------- selecting


def test_clicking_selects_and_clicking_again_deselects(qapp) -> None:
    picker = make_picker(qapp)
    changes: list[int] = []
    picker.selection_changed.connect(lambda: changes.append(1))

    click(picker, picker._point("left_knee"))
    assert picker.selected_roles() == ("left_knee",)
    click(picker, picker._point("left_knee"))
    assert picker.selected_roles() == ()
    assert len(changes) == 2
    picker.hide()


def test_several_joints_can_be_selected_and_keep_a_stable_order(qapp) -> None:
    picker = make_picker(qapp)
    for role in ("right_knee", "left_shoulder", "left_knee"):
        click(picker, picker._point(role))

    # ALL_ROLES order, not click order: two annotators picking the same joints
    # in different sequences must produce identical files.
    assert picker.selected_roles() == ("left_shoulder", "left_knee", "right_knee")
    picker.hide()


def test_a_click_near_a_joint_still_hits_it(qapp) -> None:
    """A coach with a trackpad should not have to hit an 8px dot."""
    picker = make_picker(qapp)
    point = picker._point("left_knee")
    click(picker, QPointF(point.x() + 9, point.y() - 9))
    assert picker.selected_roles() == ("left_knee",)
    picker.hide()


def test_a_click_in_empty_space_selects_nothing(qapp) -> None:
    picker = make_picker(qapp)
    click(picker, QPointF(4, 4))
    assert picker.selected_roles() == ()
    picker.hide()


def test_the_keyboard_can_walk_and_toggle_joints(qapp) -> None:
    from PySide6.QtGui import QKeyEvent

    picker = make_picker(qapp)
    picker.setFocus()
    qapp.processEvents()

    def press(key):
        picker.keyPressEvent(
            QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
        )

    press(Qt.Key.Key_Right)
    press(Qt.Key.Key_Space)
    assert len(picker.selected_roles()) == 1
    press(Qt.Key.Key_Space)
    assert picker.selected_roles() == ()
    assert picker.accessibleName()
    picker.hide()


# ------------------------------------------------------------- the dialog


@pytest.fixture
def schema():
    schema = LabelSchema.default()
    for name in ("Diz içe çöküyor", "Sırt yuvarlanıyor", "Topuk kalkıyor"):
        schema.add_error_type(name)
    return schema


def make_dialog(qapp, schema, interval=None, fmt="zed_body_34", theme_name="dark"):
    theme = get_theme(theme_name)
    qapp.setStyleSheet(build_stylesheet(theme))
    if interval is None:
        interval = ErrorInterval.create(120, 168, "diz-ice-cokuyor")
    dialog = ErrorLabelDialog(
        theme, interval, schema, skeleton_spec=try_get_skeleton_spec(fmt)
    )
    dialog.resize(880, 620)
    dialog.show()
    qapp.processEvents()
    return dialog


def test_the_dialog_reports_the_selection_and_its_status(qapp, schema) -> None:
    dialog = make_dialog(qapp, schema)
    assert dialog.joint_status is JointAnnotationStatus.UNREVIEWED
    assert dialog.affected_roles == ()

    click(dialog.joint_picker, dialog.joint_picker._point("left_knee"))
    click(dialog.joint_picker, dialog.joint_picker._point("right_knee"))
    qapp.processEvents()

    assert dialog.selected_radio.isChecked(), "clicking a joint is the answer"
    assert dialog.joint_status is JointAnnotationStatus.SELECTED
    assert dialog.affected_roles == ("left_knee", "right_knee")
    assert "Sol diz" in dialog._chips.text()
    dialog.hide()


def test_the_two_explicit_empty_states_exclude_a_selection(qapp, schema) -> None:
    dialog = make_dialog(qapp, schema)
    click(dialog.joint_picker, dialog.joint_picker._point("left_knee"))

    dialog.not_applicable_radio.setChecked(True)
    qapp.processEvents()
    assert dialog.joint_status is JointAnnotationStatus.NOT_APPLICABLE
    assert dialog.affected_roles == (), "a selection is not reported here"
    assert not dialog.clear_button.isEnabled()

    dialog.indeterminate_radio.setChecked(True)
    qapp.processEvents()
    assert dialog.joint_status is JointAnnotationStatus.INDETERMINATE
    assert not dialog.not_applicable_radio.isChecked(), "mutually exclusive"
    dialog.hide()


def test_saving_is_refused_while_the_answer_contradicts_itself(qapp, schema) -> None:
    """Claiming a selection with nothing selected must not close the window."""
    dialog = make_dialog(qapp, schema)
    dialog.selected_radio.setChecked(True)
    qapp.processEvents()

    assert not dialog._save_button.isEnabled()
    dialog._attempt_accept()
    assert dialog.isVisible(), "the dialog stays open"
    assert dialog.result() != int(ErrorLabelDialog.DialogCode.Accepted)
    assert "işaretlenmedi" in dialog._status.text()

    click(dialog.joint_picker, dialog.joint_picker._point("left_knee"))
    qapp.processEvents()
    assert dialog._save_button.isEnabled()
    dialog.hide()


def test_saving_is_refused_without_an_error_class(qapp, schema) -> None:
    dialog = make_dialog(qapp, schema, ErrorInterval.create(1, 9))
    assert not dialog._save_button.isEnabled()
    assert "hata türü" in dialog._status.text()
    dialog.hide()


def test_an_unreviewed_interval_can_still_be_saved(qapp, schema) -> None:
    """Missing joints must never block the temporal label."""
    dialog = make_dialog(qapp, schema)
    assert dialog._save_button.isEnabled()
    assert dialog.joint_status is JointAnnotationStatus.UNREVIEWED
    assert "maskelenir" in dialog._status.text()
    dialog.hide()


def test_playing_the_interval_neither_saves_nor_closes(qapp, schema) -> None:
    """Watching it again is part of deciding, not the end of deciding."""
    dialog = make_dialog(qapp, schema)
    played: list[int] = []
    dialog.play_requested_now.connect(lambda: played.append(1))

    dialog.play_button.click()
    qapp.processEvents()

    assert played == [1]
    assert dialog.isVisible(), "the window stays open"
    assert dialog.result() != int(ErrorLabelDialog.DialogCode.Accepted)
    dialog.hide()


def test_reopening_a_saved_interval_restores_everything(qapp, schema) -> None:
    interval = ErrorInterval.create(120, 168, "diz-ice-cokuyor", note="sol taraf")
    interval.set_affected_joints("selected", ["left_knee", "chest"])

    dialog = make_dialog(qapp, schema, interval)
    assert dialog.error_code == "diz-ice-cokuyor"
    assert dialog.note == "sol taraf"
    assert dialog.selected_radio.isChecked()
    assert dialog.affected_roles == ("chest", "left_knee")
    assert set(dialog.joint_picker.selected_roles()) == {"chest", "left_knee"}
    dialog.hide()


def test_reopening_an_explicit_empty_state_restores_it(qapp, schema) -> None:
    interval = ErrorInterval.create(1, 9, "diz-ice-cokuyor")
    interval.set_affected_joints("indeterminate")
    dialog = make_dialog(qapp, schema, interval)
    assert dialog.indeterminate_radio.isChecked()
    assert dialog.joint_status is JointAnnotationStatus.INDETERMINATE
    dialog.hide()


def test_an_old_interval_opens_with_the_question_visibly_unanswered(
    qapp, schema
) -> None:
    """No radio pre-filled: a guess would look like somebody's decision."""
    dialog = make_dialog(qapp, schema, ErrorInterval.create(1, 9, "diz-ice-cokuyor"))
    assert not dialog.selected_radio.isChecked()
    assert not dialog.not_applicable_radio.isChecked()
    assert not dialog.indeterminate_radio.isChecked()
    dialog.hide()


def test_the_dialog_names_the_format_and_what_stays_in_the_export(
    qapp, schema
) -> None:
    dialog = make_dialog(qapp, schema, fmt="zed_body_38")
    note = dialog._topology_note.text()
    assert "zed_body_38" in note
    assert "export" in note, "non-target joints are not dropped from the data"

    # The label is capped at two lines, so the part that would be cut off
    # lives in the tooltip instead of being truncated mid-word on screen.
    detail = dialog._topology_note.toolTip()
    assert detail.startswith(note.split(".")[0])
    assert "bulunmayan roller" in detail
    assert "Baş" in detail, "the roles this format lacks are named in full"
    assert "bulunmayan roller" not in note
    dialog.hide()


# -------------------------------------------------------------- geometry


@pytest.mark.parametrize("size", [(1120, 700), (1366, 768), (1600, 980)])
@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("fmt", ["zed_body_18", "zed_body_34", "zed_body_38"])
def test_the_dialog_fits_every_supported_window(
    qapp, schema, fmt, theme_name, size
) -> None:
    width, height = size
    dialog = make_dialog(qapp, schema, fmt=fmt, theme_name=theme_name)
    dialog.resize(min(880, width - 80), min(620, height - 80))
    qapp.processEvents()

    # The size the window can really be dragged down to is whichever is
    # larger: the floor the dialog declares, or what its layout needs. Font
    # metrics differ between platforms, so which one wins is not fixed - only
    # that the larger of the two still fits the screen.
    declared, needed = dialog.minimumSize(), dialog.minimumSizeHint()
    floor_w = max(declared.width(), needed.width())
    floor_h = max(declared.height(), needed.height())
    assert floor_w <= width - 40, f"{fmt} dialog too wide: {floor_w}"
    assert floor_h <= height - 60, f"{fmt} dialog too tall: {floor_h}"
    assert not dialog.grab().isNull()

    # The controls that decide the answer must all be on screen.
    for widget in (
        dialog.joint_picker,
        dialog.selected_radio,
        dialog.not_applicable_radio,
        dialog.indeterminate_radio,
        dialog._save_button,
        dialog.play_button,
    ):
        assert widget.isVisible(), f"{widget} is not reachable"
    dialog.hide()


def test_a_long_selection_does_not_push_the_buttons_off(qapp, schema) -> None:
    """Every joint at once, at the smallest size the dialog allows."""
    dialog = make_dialog(qapp, schema)
    floor = dialog.minimumSize()
    dialog.resize(floor)
    dialog.joint_picker.set_selected_roles(dialog.joint_picker.available_roles)
    dialog.selected_radio.setChecked(True)
    qapp.processEvents()

    assert dialog._save_button.isVisible()
    assert dialog._chips.height() <= 40, "the summary is capped"
    assert dialog.joint_picker.isVisible()
    assert dialog._save_button.geometry().bottom() <= dialog.height()
    dialog.hide()


def test_the_floor_is_a_size_the_dialog_is_usable_at(qapp, schema) -> None:
    """Not the narrowest the splitter permits - the narrowest that reads."""
    dialog = make_dialog(qapp, schema)
    declared = dialog.minimumSize()
    assert declared.width() >= 700, "a squeezed figure is not a usable picker"
    assert declared.width() <= 1080 and declared.height() <= 640, "fits 1120x700"

    dialog.resize(declared)
    qapp.processEvents()
    picker = dialog.joint_picker
    assert picker.width() >= 200
    assert picker._figure_rect().width() > 0
    dialog.hide()


# ------------------------------------------------------------- the summary


def test_the_status_line_distinguishes_all_four_states() -> None:
    interval = ErrorInterval.create(1, 9, "k")
    assert "incelenmedi" in describe_joint_annotation(interval)

    interval.set_affected_joints("not_applicable")
    assert "belirli eklem yok" in describe_joint_annotation(interval)

    interval.set_affected_joints("indeterminate")
    assert "belirlenemiyor" in describe_joint_annotation(interval)

    interval.set_affected_joints("selected", ["left_knee"])
    assert "Sol diz" in describe_joint_annotation(interval)


# ------------------------------------------------------- timeline visibility


def _timeline_with_interval(qapp, status, roles=()):
    from kinecapture.domain.project import MovementSample
    from kinecapture.gui.widgets.timeline import TimelineMode, TimelineWidget

    sample = MovementSample.create("take-1", 0, 200, index=1)
    error = ErrorInterval.create(40, 90, "diz-ice-cokuyor")
    if status is not None:
        error.set_affected_joints(status, roles)
    sample.error_intervals.append(error)

    widget = TimelineWidget(get_theme("dark"))
    widget.set_take(frame_count=200, fps=30.0)
    widget.set_samples([sample])
    widget.set_error_labels({"diz-ice-cokuyor": "Diz içe çöküyor"})
    widget.set_mode(TimelineMode.ERROR)
    widget.resize(900, 240)
    widget.show()
    qapp.processEvents()
    return widget, sample, error


def test_the_timeline_tooltip_names_the_joints(qapp) -> None:
    widget, _sample, error = _timeline_with_interval(
        qapp, "selected", ["left_knee", "right_hip"]
    )
    text = widget._hover_text(60, (error, "body"))
    assert "Diz içe çöküyor" in text
    assert "Sol diz" in text and "Sağ kalça" in text
    widget.hide()


def test_the_tooltip_separates_unreviewed_from_reviewed_and_empty(qapp) -> None:
    """The two draw identically; the tooltip is where they must differ."""
    widget, _sample, unreviewed = _timeline_with_interval(qapp, None)
    blank = widget._hover_text(60, (unreviewed, "body"))
    widget.hide()

    widget, _sample, reviewed = _timeline_with_interval(qapp, "not_applicable")
    empty = widget._hover_text(60, (reviewed, "body"))
    widget.hide()

    assert blank != empty
    assert "incelenmedi" in blank
    assert "belirli eklem yok" in empty


def test_the_plain_tooltip_still_gives_frame_and_time(qapp) -> None:
    widget, _sample, _error = _timeline_with_interval(qapp, None)
    text = widget._hover_text(60, None)
    assert "Kare 60" in text and "2.00 s" in text
    assert "eklem" not in text, "no interval under the pointer, nothing to say"
    widget.hide()


def test_the_side_labels_never_overprint_each_other(qapp) -> None:
    """Narrow enough and the two would meet in the middle and blur together."""
    picker = make_picker(qapp)
    for width in (500, 380, 260, 200):
        picker.resize(width, 470)
        qapp.processEvents()
        assert not picker.grab().isNull(), f"paint failed at {width}px"
    picker.hide()


def test_a_narrow_picker_still_says_which_side_is_which(qapp) -> None:
    """The fallback is a shorter sentence, never a truncated one."""
    from PySide6.QtGui import QFontMetrics

    picker = make_picker(qapp)
    picker.resize(200, 470)
    qapp.processEvents()

    metrics = QFontMetrics(picker.font())
    fits = [
        text
        for text in (
            "Önden görünüş: sporcunun solu sağda",
            "Sporcunun solu sağda",
            "Solu sağda",
        )
        if metrics.horizontalAdvance(text) <= picker.width() - 4
    ]
    assert fits, "at least the shortest wording must fit any allowed width"
    picker.hide()
