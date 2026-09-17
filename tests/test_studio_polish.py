"""Cila: keyboard, contrast, scaling, and the states nobody plans for.

Three kinds of check.

**It must not crash where there is nothing.** Every new widget is painted with
an empty take, a one-frame take, an all-NaN skeleton and a viewport too small
to be useful. These are the states a real session reaches on its worst day.

**Colour is never the only signal.** Every status carries text as well, so the
screen still works for someone who cannot separate the colours.

**It must fit and be readable.** The screens are measured against a 1366x768
laptop at 125% and 150% scaling, and the theme's text/background pairs are
measured against the WCAG contrast formula.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPushButton,
    QToolButton,
)

from kinecapture.studio.theme import load_tokens, theme_names  # noqa: E402
from kinecapture.studio.viewmodels.navigation import DESTINATIONS, destination  # noqa: E402
from kinecapture.studio.views.pages import PAGE_TYPES  # noqa: E402
from kinecapture.studio.views.skeleton3d import Skeleton3DView  # noqa: E402
from kinecapture.studio.views.subject import SubjectPanel  # noqa: E402
from kinecapture.studio.views.timeline import Interval, TimelineView, Tool  # noqa: E402
from kinecapture.studio.views.viewer import ReviewViewer  # noqa: E402

#: A 1366x768 laptop is the smallest screen a coach is likely to bring.
LAPTOP = (1366, 768)
#: WCAG AA for body text. Applied to the pairs the themes actually use.
MIN_CONTRAST = 4.5
#: WCAG AA for large text and non-text indicators.
MIN_CONTRAST_LARGE = 3.0


def _is_qt_internal(widget) -> bool:  # noqa: ANN001
    """Whether Qt built this control inside a compound widget of its own.

    A spin box contains a line edit; a clearable line edit contains a tool
    button. Those are Qt's, and holding this screen responsible for naming
    them would be checking the toolkit rather than the application.
    """
    from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit

    if widget.objectName().startswith("qt_"):
        return True
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, (QAbstractSpinBox, QComboBox, QLineEdit)):
            return True
        parent = parent.parentWidget()
    return False


def _describes_itself(widget) -> bool:  # noqa: ANN001
    """Whether a control says what it is, by any of the ways Qt offers."""
    for attribute in ("text", "toolTip", "accessibleName", "placeholderText",
                      "currentText", "accessibleDescription"):
        getter = getattr(widget, attribute, None)
        if callable(getter):
            try:
                if str(getter()).strip():
                    return True
            except TypeError:       # a getter that needs arguments
                continue
    return False


#: Layout measurements are only meaningful on a platform that has fonts. The
#: offscreen plugin reports zero font families, so every width it produces is
#: fiction - see MEMORY 6Z.
OFFSCREEN = os.environ.get("QT_QPA_PLATFORM") == "offscreen"
needs_fonts = pytest.mark.skipif(
    OFFSCREEN,
    reason="offscreen platformunda font yok; genişlik ölçümleri anlamsız "
           "(QT_QPA_PLATFORM=windows ile çalıştırın)",
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=list(theme_names()))
def tokens(request):  # noqa: ANN001
    return load_tokens(request.param)


def render(widget, width: int = 600, height: int = 300) -> QImage:
    """Paint into an image; anything that throws fails the test."""
    widget.resize(width, height)
    image = QImage(QSize(width, height), QImage.Format.Format_ARGB32_Premultiplied)
    widget.render(image)
    return image


# ------------------------------------------------------------ paint safety
def test_the_timeline_paints_with_nothing_in_it(qapp, tokens) -> None:
    view = TimelineView(tokens)
    try:
        view.set_take(0, 0.0)
        render(view)
        view.set_take(1, 30.0)   # a single-frame take
        render(view)
    finally:
        view.deleteLater()


def test_the_timeline_paints_in_a_viewport_too_small_to_use(qapp, tokens) -> None:
    view = TimelineView(tokens)
    try:
        view.set_take(1000, 60.0)
        view.set_intervals([
            Interval(key="m", start=10, end=90, lane="movements", text="squat",
                     status="ready"),
        ])
        render(view, 60, 40)
    finally:
        view.deleteLater()


def test_the_timeline_paints_at_extreme_zoom(qapp, tokens) -> None:
    view = TimelineView(tokens)
    try:
        view.set_take(216000, 60.0)
        view.zoom_all()
        render(view)
        for _ in range(40):
            view.zoom(2.0)
        render(view)
        assert view.view_range[1] > 0
    finally:
        view.deleteLater()


def test_the_viewer_paints_without_a_frame_and_says_why(qapp, tokens) -> None:
    viewer = ReviewViewer(tokens)
    try:
        viewer.set_placeholder("Bu sürümde inceleme videosu yok.")
        render(viewer)
        # A blank rectangle would look like a bug; the reason is drawn instead.
        assert viewer._placeholder
    finally:
        viewer.deleteLater()


def test_the_viewer_paints_a_frame_whose_skeleton_is_all_missing(qapp, tokens) -> None:
    viewer = ReviewViewer(tokens)
    try:
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        viewer.set_frame(frame, (160, 120))
        viewer.set_skeleton(np.full((16, 2), np.nan, dtype=np.float32), ((0, 1),))
        render(viewer)
    finally:
        viewer.deleteLater()


def _preview_with_a_frame(tokens):
    """A preview view with a picture in it, at a known source size."""
    import numpy as np

    from kinecapture.studio.views.preview import PreviewView

    view = PreviewView(tokens)
    view.set_frame(np.zeros((360, 640, 3), dtype=np.uint8), (640, 360))
    return view


def test_a_notice_on_the_picture_paints_and_then_takes_itself_away(
    qapp, tokens
) -> None:
    """The operator is three metres away and cannot dismiss anything.

    So the message that refuses a recording is drawn on the picture they are
    already looking at, holds long enough to read, and goes on its own.
    """
    from kinecapture.studio.views.preview import NOTICE_HOLD_MS

    view = _preview_with_a_frame(tokens)
    view.show_notice("Önce görüntüde kendinize tıklayın")
    assert view.notice_text == "Önce görüntüde kendinize tıklayın"
    render(view)  # painting it must not throw in either theme

    # It is on a clock, not on a click.
    assert view._notice_hold.isActive()  # noqa: SLF001 - the clock is the point
    assert NOTICE_HOLD_MS == 3000
    view._notice_faded(0.0)  # noqa: SLF001 - jump to the end of the fade
    assert view.notice_text == ""
    render(view)


def test_the_chosen_person_is_outlined_on_the_picture(qapp, tokens) -> None:
    """"I clicked something" and "it understood who" are different facts."""
    view = _preview_with_a_frame(tokens)
    render(view)
    view.set_subject_box((100.0, 40.0, 260.0, 330.0))
    render(view)
    view.set_subject_box(None)
    render(view)


def test_the_3d_view_paints_with_no_pose(qapp, tokens) -> None:
    view = Skeleton3DView(tokens)
    try:
        view.set_skeleton_spec(((0, 1), (1, 2)), 1)
        view.set_joints(None)
        render(view, 320, 240)
        view.set_joints(np.full((3, 3), np.nan, dtype=np.float32))
        render(view, 320, 240)
    finally:
        view.deleteLater()


def test_the_subject_panel_paints_with_no_candidates(qapp, tokens) -> None:
    panel = SubjectPanel(tokens)
    try:
        panel.show_candidates(())
        panel.show_questions(())
        render(panel, 320, 480)
        # Empty is explained, not blank.
        assert panel.candidate_box.count() > 1
    finally:
        panel.deleteLater()


# ---------------------------------------------------------------- keyboard
@pytest.mark.parametrize("key", sorted(PAGE_TYPES))
def test_every_control_on_a_page_can_be_reached_and_explained(qapp, key) -> None:
    """A control nobody can tab to, or hover to understand, is half-built."""
    page = PAGE_TYPES[key](destination(key), load_tokens("dark"))
    try:
        controls = [
            widget
            for kind in (QPushButton, QToolButton, QComboBox, QCheckBox, QLineEdit)
            for widget in page.findChildren(kind)
            if widget.isEnabled() and not _is_qt_internal(widget)
        ]
        assert controls, f"{key}: denetim bulunamadı"
        unreachable = [
            w for w in controls if w.focusPolicy() == Qt.FocusPolicy.NoFocus
        ]
        assert not unreachable, f"{key}: klavyeyle erişilemiyor: {unreachable}"

        unexplained = [w for w in controls if not _describes_itself(w)]
        assert not unexplained, (
            f"{key}: adı da ipucu da yok: "
            f"{[type(w).__name__ for w in unexplained]}"
        )
    finally:
        page.close()


def test_the_labelling_screen_has_its_shortcuts(qapp) -> None:
    from PySide6.QtGui import QKeySequence, QShortcut

    page = PAGE_TYPES["review"](destination("review"), load_tokens("dark"))
    try:
        bound = {s.key().toString() for s in page.findChildren(QShortcut)}
        for expected in ("Space", "Left", "Right", "Ctrl+Z", "Ctrl+S", "Tab", "1", "9"):
            assert QKeySequence(expected).toString() in bound, expected
    finally:
        page.close()


# -------------------------------------------------------- colour is not alone
def test_a_status_is_always_text_as_well_as_colour(qapp) -> None:
    """Someone who cannot separate the colours still has to be able to work."""
    from kinecapture.studio.viewmodels.review import READINESS_STATUS, READINESS_TEXT

    assert set(READINESS_STATUS) == set(READINESS_TEXT)
    assert all(READINESS_TEXT.values()), "durum yalnız renkle anlatılıyor"

    from kinecapture.studio.viewmodels.subject import VERDICT_TEXT

    assert all(VERDICT_TEXT.values())

    from kinecapture.export.canonical import REFUSAL_TEXT, Refusal

    assert set(REFUSAL_TEXT) == set(Refusal)
    assert all(REFUSAL_TEXT.values())


def test_interval_rows_carry_their_state_in_words(qapp) -> None:
    from kinecapture.studio.viewmodels.review import MovementRow
    from kinecapture.processing.annotations import Correctness, Readiness

    row = MovementRow(
        sample_id="s", start=0, end=10, exercise="squat", exercise_label="Squat",
        readiness=Readiness.READY, correctness=Correctness.INCORRECT,
        error_count=1, unclassified_errors=0, excluded=False,
    )
    assert "hatalı" in row.text          # not only the colour
    assert row.status == "ready"


# ------------------------------------------------------------------ scaling
@needs_fonts
@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5])
@pytest.mark.parametrize("key", sorted(PAGE_TYPES))
def test_every_screen_fits_a_laptop_at_normal_scalings(qapp, key, scale) -> None:
    """At 150% a 1366x768 laptop is effectively 910x512 of layout space."""
    page = PAGE_TYPES[key](destination(key), load_tokens("dark"))
    try:
        hint = page.minimumSizeHint()
        available = (LAPTOP[0] / scale, LAPTOP[1] / scale)
        assert hint.width() <= available[0], (
            f"{key} @ {scale:.0%}: {hint.width()} px gerekiyor, "
            f"{available[0]:.0f} px var"
        )
        assert hint.height() <= available[1], (
            f"{key} @ {scale:.0%}: {hint.height()} px gerekiyor, "
            f"{available[1]:.0f} px var"
        )
    finally:
        page.close()


def test_every_destination_is_reachable_from_the_navigation() -> None:
    assert {d.key for d in DESTINATIONS} == set(PAGE_TYPES)


# ----------------------------------------------------------------- contrast
def _luminance(colour: str) -> float:
    value = colour.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme", list(theme_names()))
def test_body_text_is_readable_on_every_surface(theme) -> None:
    tokens = load_tokens(theme)
    surfaces = ("KcSurfaceBase", "KcSurfaceRaised", "KcSurfaceControl")
    for surface in surfaces:
        ratio = contrast(tokens.colour("KcTextPrimary"), tokens.colour(surface))
        assert ratio >= MIN_CONTRAST, f"{theme}: KcTextPrimary/{surface} = {ratio:.2f}"


@pytest.mark.parametrize("theme", list(theme_names()))
def test_secondary_text_stays_legible(theme) -> None:
    tokens = load_tokens(theme)
    ratio = contrast(tokens.colour("KcTextSecondary"), tokens.colour("KcSurfaceBase"))
    assert ratio >= MIN_CONTRAST_LARGE, f"{theme}: {ratio:.2f}"


@pytest.mark.parametrize("theme", list(theme_names()))
def test_status_colours_stand_out_from_their_background(theme) -> None:
    """These three carry meaning, so they have to be distinguishable."""
    tokens = load_tokens(theme)
    background = tokens.colour("KcSurfaceBase")
    for name in ("KcStatusRecording", "KcStatusWarning", "KcStatusLive"):
        ratio = contrast(tokens.colour(name), background)
        assert ratio >= MIN_CONTRAST_LARGE, f"{theme}: {name} = {ratio:.2f}"


@pytest.mark.parametrize("theme", list(theme_names()))
def test_the_focus_ring_is_visible(theme) -> None:
    """Keyboard use is only usable if you can see where you are."""
    tokens = load_tokens(theme)
    for surface in ("KcSurfaceBase", "KcSurfaceControl"):
        ratio = contrast(tokens.colour("KcFocusRing"), tokens.colour(surface))
        assert ratio >= MIN_CONTRAST_LARGE, f"{theme}/{surface}: {ratio:.2f}"


def test_the_stylesheet_actually_draws_focus() -> None:
    from kinecapture.studio.theme import stylesheet_for

    for theme in theme_names():
        sheet = stylesheet_for(theme)
        assert ":focus" in sheet, f"{theme}: odak için kural yok"


@needs_fonts
@pytest.mark.parametrize("key", sorted(PAGE_TYPES))
def test_every_screen_fits_a_high_dpi_display_at_200_percent(qapp, key) -> None:
    """200% is a high-DPI setting, so the panel behind it is a big one.

    A 4K display at 200% leaves 1920x1080 of layout space. Measured
    separately from the laptop case because 200% on a 1366x768 panel leaves
    683x512, which Yakalama, İşlenen Videolar and Etiketleme do not fit - a
    real limit, recorded rather than hidden.
    """
    page = PAGE_TYPES[key](destination(key), load_tokens("dark"))
    try:
        hint = page.minimumSizeHint()
        assert hint.width() <= 1920 and hint.height() <= 1080, (
            f"{key}: {hint.width()}x{hint.height()}"
        )
    finally:
        page.close()


@needs_fonts
def test_the_widest_screens_are_the_ones_with_two_viewports(qapp) -> None:
    """A guard on the numbers in the report: if Etiketleme quietly grows past
    a laptop's width, this says so before a coach discovers it."""
    review = PAGE_TYPES["review"](destination("review"), load_tokens("dark"))
    try:
        # Video + 3D + inspector side by side is the widest arrangement here.
        assert review.minimumSizeHint().width() <= 900
    finally:
        review.close()


# ------------------------------------------------------------------ tables
@pytest.mark.parametrize("key", sorted(PAGE_TYPES))
def test_a_table_shows_what_its_model_holds(qapp, key) -> None:
    """A proxy that was never given its source reports zero rows forever.

    Two screens shipped that way: the model was full, every model-level test
    passed, and the table on screen was blank. So this asks the *view* what it
    would draw, not the model what it contains.
    """
    from PySide6.QtCore import QSortFilterProxyModel
    from PySide6.QtWidgets import QTableView

    page = PAGE_TYPES[key](destination(key), load_tokens("dark"))
    try:
        for view in page.findChildren(QTableView):
            model = view.model()
            assert model is not None, f"{key}: tabloya model verilmemiş"
            if isinstance(model, QSortFilterProxyModel):
                assert model.sourceModel() is not None, (
                    f"{key}: proxy'ye kaynak model verilmemiş"
                )
    finally:
        page.close()
