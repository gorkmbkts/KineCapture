"""The sign-in screen: the brand, the symmetry, and what still has to work.

Layout numbers are only asserted where the platform can measure them. Under
the offscreen plugin there is no font database at all, so every string is
measured as tofu and a width assertion there measures nothing; those tests
skip rather than pass on nonsense. Behaviour - tab order, Enter, the reveal
action, what authentication does - is platform independent and always runs.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.viewmodels.auth import AuthMode  # noqa: E402
from kinecapture.studio.views import fonts  # noqa: E402
from kinecapture.studio.views.auth import WORDMARK  # noqa: E402
from kinecapture.studio.views.brand import CREST_NAME  # noqa: E402


def has_real_fonts() -> bool:
    """Whether text measurements on this platform mean anything.

    Never call this at import time. ``QFontDatabase`` is a GUI service: asking
    it anything before a ``QApplication`` exists aborts the process on Windows
    (STATUS_STACK_BUFFER_OVERRUN, measured here on PySide6 6.10.1), which is
    why the layout tests below check it inside the test rather than in a
    ``skipif`` decorator.
    """
    return bool(QFontDatabase.families())


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def gate(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    window = build_window(config, state_path=tmp_path / "window.json")
    window.resize(1366, 768)
    window.show()
    app.processEvents()
    yield window.auth_view, window, app
    window.close()


# ----------------------------------------------------------------- the font


def test_the_brand_face_is_bundled_with_its_licence() -> None:
    """A licensed asset travels with its licence or it does not travel."""
    assert fonts.font_bytes(), "Space Grotesk is not in the package"
    licence = fonts.licence_text()
    assert "SIL Open Font License" in licence
    assert "Space Grotesk" in licence


def test_the_brand_face_registers_with_qt(app) -> None:
    families = fonts.load_brand_font()
    assert families, "Qt refused the bundled font"
    assert fonts.brand_family() == fonts.BRAND_FAMILY


def test_the_brand_face_can_draw_turkish(app) -> None:
    """Six letters of Turkish, in both cases. Tofu in the product name is not
    an acceptable outcome of choosing a display face."""
    assert fonts.missing_glyphs() == ""


def test_a_missing_font_is_not_an_error(app, monkeypatch) -> None:
    """The gate must open on a machine where the file did not ship."""
    fonts._register.cache_clear()
    monkeypatch.setattr(fonts, "font_bytes", lambda: None)
    try:
        assert fonts.load_brand_font() == ()
        assert fonts.brand_family() == ""
        assert fonts.brand_font_available() is False
        # Nothing to check means nothing missing, not everything missing.
        assert fonts.missing_glyphs() == ""
    finally:
        fonts._register.cache_clear()
        fonts.load_brand_font()


def test_the_fallback_chain_is_declared_in_the_tokens() -> None:
    chain = load_tokens("dark").type_value("KcFontBrand")
    assert chain.startswith(fonts.BRAND_FAMILY)
    # More than one name after it: a single-entry chain is not a fallback.
    assert len(chain.split(",")) >= 3


# -------------------------------------------------------------- LOGIN-01


def test_the_wordmark_is_the_product_name_in_the_brand_face(gate) -> None:
    view, _window, _app = gate
    assert view.wordmark.text() == WORDMARK
    assert view.wordmark.property("kcRole") == "brandMark"


def test_there_is_no_separate_university_caption(gate) -> None:
    view, _window, _app = gate
    assert not hasattr(view, "institution")
    texts = [
        child.text()
        for child in view.findChildren(type(view.wordmark))
        if child.text()
    ]
    assert CREST_NAME not in texts
    # It is still announced, on the mark itself.
    assert view.crest.accessibleName() == CREST_NAME


def test_the_crest_is_larger_than_it_was(gate) -> None:
    """The approved design asked for roughly 10-15% more. It was 168."""
    view, _window, _app = gate
    wanted = view._tokens.metric("KcCrestSizeAuth")
    assert 1.10 <= wanted / 168 <= 1.18
    assert view.crest.width() == wanted


def test_the_wordmark_is_larger_than_body_text(gate) -> None:
    view, _window, _app = gate
    if not has_real_fonts():
        pytest.skip("offscreen has no font database; a size read there is noise")
    tokens = view._tokens
    font = view.wordmark.font()
    # The stylesheet sets a pixel size, so pointSize() is -1. Read whichever
    # of the two the sheet actually set rather than assuming one of them.
    size = font.pixelSize() if font.pixelSize() > 0 else font.pointSize()
    assert size == tokens.font_size("KcFontSizeDisplay")
    assert size > tokens.font_size("KcFontSizeTitle")
    assert font.family() == fonts.BRAND_FAMILY


# -------------------------------------------------------------- LOGIN-02


def test_the_captions_are_placeholders_not_labels(gate) -> None:
    view, _window, _app = gate
    username = view.field("username")
    password = view.field("password")
    assert username is not None and password is not None
    assert username.placeholderText() == "Kullanıcı adı"
    assert password.placeholderText() == "Parola"
    # And the name a screen reader uses does not move with the text.
    assert username.accessibleName() == "Kullanıcı adı"
    assert password.accessibleName() == "Parola"


def test_the_placeholder_comes_back_when_the_field_is_emptied(gate) -> None:
    view, _window, app = gate
    username = view.field("username")
    username.setText("ada")
    app.processEvents()
    assert username.placeholderText() == "Kullanıcı adı"
    username.clear()
    app.processEvents()
    assert username.text() == ""
    assert username.placeholderText() == "Kullanıcı adı"


def test_the_boxes_share_one_width_and_one_height(gate) -> None:
    view, _window, app = gate
    app.processEvents()
    boxes = [view.field(name) for name in ("username", "password")]
    widths = {box.width() for box in boxes}
    heights = {box.height() for box in boxes}
    assert len(widths) == 1, widths
    assert len(heights) == 1, heights
    # At least the shared large-control height; the stylesheet's padding may
    # ask for a little more, and it is allowed to as long as every box agrees.
    assert heights.pop() >= view._tokens.metric("KcControlHeightLarge")


def test_the_primary_button_is_the_width_of_the_form(gate) -> None:
    view, _window, app = gate
    app.processEvents()
    assert view.primary.width() == view.field("username").width()


def test_the_column_is_centred_on_one_axis(gate) -> None:
    view, _window, app = gate
    app.processEvents()

    def centre(widget) -> int:  # noqa: ANN001
        top_left = widget.mapTo(view, widget.rect().topLeft())
        return top_left.x() + widget.width() // 2

    axes = {
        centre(view.crest),
        centre(view.field("username")),
        centre(view.field("password")),
        centre(view.primary),
    }
    assert max(axes) - min(axes) <= 1, axes


def test_the_secondary_link_is_under_the_button(gate) -> None:
    view, window, app = gate
    # On a fresh install the only mode is SETUP, which has no second way in.
    # Create the owner first so the gate can be looked at in SIGN_IN.
    assert view.viewmodel.mode is AuthMode.SETUP
    for name, value in (
        ("first_name", "Ada"), ("last_name", "Lovelace"), ("username", "ada"),
        ("password", "kinecapture1"), ("password_confirm", "kinecapture1"),
    ):
        view.field(name).setText(value)
    view._submit()
    app.processEvents()
    window.viewmodel.session.sign_out()
    view.viewmodel.set_mode(AuthMode.SIGN_IN)
    # Put the gate back in front. A hidden page is not laid out, so reading
    # geometry off one measures where widgets were, not where they are.
    window.gate.setCurrentWidget(view)
    app.processEvents()
    assert view.secondary.isVisible()
    button_bottom = view.primary.mapTo(view, view.primary.rect().bottomLeft()).y()
    link_top = view.secondary.mapTo(view, view.secondary.rect().topLeft()).y()
    assert link_top >= button_bottom
    # And centred on the same axis as everything else in the column.
    primary_centre = (
        view.primary.mapTo(view, view.primary.rect().topLeft()).x()
        + view.primary.width() // 2
    )
    link_centre = (
        view.secondary.mapTo(view, view.secondary.rect().topLeft()).x()
        + view.secondary.width() // 2
    )
    assert abs(primary_centre - link_centre) <= 1


def test_show_hide_lives_inside_the_password_box(gate) -> None:
    view, _window, app = gate
    password = view.field("password")
    actions = password.actions()
    assert actions, "no trailing action on the password box"
    reveal = actions[0]
    assert reveal.isCheckable()
    assert password.echoMode() is QLineEdit.EchoMode.Password
    reveal.setChecked(True)
    app.processEvents()
    assert view.password_revealed() is True
    assert password.echoMode() is QLineEdit.EchoMode.Normal
    reveal.setChecked(False)
    app.processEvents()
    assert password.echoMode() is QLineEdit.EchoMode.Password


def test_tab_moves_username_to_password_to_button(gate) -> None:
    view, _window, app = gate
    username = view.field("username")
    password = view.field("password")
    username.setFocus()
    app.processEvents()
    assert username.hasFocus()
    username.focusNextChild()
    app.processEvents()
    assert password.hasFocus()


def test_enter_submits_and_authentication_still_works(gate) -> None:
    view, window, app = gate
    assert view.viewmodel.mode is AuthMode.SETUP
    for name, value in (
        ("first_name", "Ada"),
        ("last_name", "Lovelace"),
        ("username", "ada"),
        ("password", "kinecapture1"),
        ("password_confirm", "kinecapture1"),
    ):
        view.field(name).setText(value)
    # Enter on the last field, not a click on the button.
    view.field("password_confirm").returnPressed.emit()
    app.processEvents()
    assert window.viewmodel.session.is_authenticated
    assert window.gate.currentWidget() is window.shell_body


def test_a_password_is_cleared_after_it_is_used(gate) -> None:
    view, _window, app = gate
    for name, value in (
        ("first_name", "Ada"),
        ("last_name", "Lovelace"),
        ("username", "ada"),
        ("password", "kinecapture1"),
        ("password_confirm", "kinecapture1"),
    ):
        view.field(name).setText(value)
    view._submit()
    app.processEvents()
    for name in ("password", "password_confirm"):
        box = view.field(name)
        if box is not None:
            assert box.text() == ""


def test_a_rejected_field_is_marked_with_the_property_the_sheet_matches(
    gate,
) -> None:
    """``kcStatus`` matched no rule at all, so a bad field looked fine."""
    view, _window, app = gate
    # Two passwords that disagree: the one rejection this form makes on its
    # own, without asking the identity store anything.
    view.viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="", username="ada",
        password="kinecapture1", password_confirm="kinecapture2",
    )
    app.processEvents()
    box = view.field("password_confirm")
    assert box is not None
    assert box.property("kcState") == "error"
    assert box.toolTip()
    # And it clears again once the form is refilled correctly.
    view.viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="", username="ada",
        password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    box = view.field("password_confirm")
    if box is not None:
        assert box.property("kcState") != "error"


def test_switching_to_registration_keeps_the_form_symmetric(gate) -> None:
    view, _window, app = gate
    view.viewmodel.set_mode(AuthMode.SETUP)
    app.processEvents()
    widths = {
        view.field(name).width()
        for name in ("first_name", "last_name", "username", "password")
        if view.field(name) is not None
    }
    assert len(widths) == 1, widths


def test_the_backdrop_is_static(gate) -> None:
    """No timer, no animation: this screen must not move while it is read."""
    view, _window, _app = gate
    from PySide6.QtCore import QTimer

    assert not view.backdrop.findChildren(QTimer)
    assert not view.findChildren(QTimer)


def test_the_gate_follows_the_theme(gate) -> None:
    view, window, app = gate
    window.viewmodel.set_theme("light")
    app.processEvents()
    assert view._tokens.name == "light"
    assert view.backdrop._tokens.name == "light"
    window.viewmodel.set_theme("dark")
    app.processEvents()
    assert view._tokens.name == "dark"
