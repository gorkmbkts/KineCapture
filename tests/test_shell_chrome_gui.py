"""The two surfaces seen before any work starts: sign-in and the nav rail.

Neither does anything, which is exactly why they are worth testing. A crest
that fails to load, a form that runs off the bottom of a 700px laptop, or a
"Daralt" button whose label sits a few pixels off centre are all invisible to
the feature tests and all the first thing a user sees.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.gui.main_window import MainWindow, NavigationRail  # noqa: E402
from kinecapture.gui.theme import build_stylesheet, get_theme  # noqa: E402

VIEWPORTS = [(1120, 700), (1366, 768), (1600, 980)]
THEMES = ["dark", "light"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def destroy(widget) -> None:
    """Actually delete a window, not merely schedule it.

    ``deleteLater`` only queues the deletion; without an event loop turn the
    window stays alive for the rest of the session. That matters here because
    ``QApplication.setStyleSheet`` restyles *every* live widget, so windows
    left behind by earlier tests make each later theme switch slower than the
    last - these tests took minutes each before this line existed.
    """
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def build_window(tmp_path) -> MainWindow:
    config = AppConfig(
        dataset_root=tmp_path / "data",
        log_dir=tmp_path / "logs",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    window = MainWindow(config)
    window.resize(1120, 700)
    window.show()
    QApplication.processEvents()
    return window


@pytest.fixture
def window(qapp, tmp_path):
    """A window whose identity database is this test's own."""
    window = build_window(tmp_path)
    yield window
    destroy(window)


@pytest.fixture
def rail(qapp):
    widget = NavigationRail(get_theme("dark"))
    for key, title, icon in (
        ("dashboard", "Ana Sayfa", "dashboard"),
        ("projects", "Projeler", "project"),
        ("capture", "Capture", "capture"),
        ("review", "İnceleme ve Etiketleme", "review"),
        ("dataset", "Dataset", "dataset"),
        ("export", "Export", "export"),
        ("settings", "Ayarlar ve Tanılama", "settings"),
    ):
        widget.add_page(key, title, icon)
    widget.resize(208, 700)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.hide()


# ------------------------------------------------------------- the nav rail


def test_the_collapse_button_label_is_centred(rail, qapp) -> None:
    """It spans the rail, so a left-aligned label reads as a mistake."""
    assert rail._toggle.property("role") == "navToggle"
    qapp.setStyleSheet(build_stylesheet(get_theme("dark")))
    qapp.processEvents()
    assert not rail.grab().isNull()


def test_collapsing_leaves_no_gap_where_the_logo_was(rail, qapp) -> None:
    """The spacer has to go with it, or the rail keeps a hole."""
    assert rail._logo_gap.isVisible()
    logo_block = rail._logo.height() + rail._logo_gap.height()
    assert logo_block > 0
    # The layout is what has to give the space back. Reading the hidden
    # widgets' own geometry proves nothing: Qt leaves their last rectangle
    # behind, and the stretch above keeps the toggle pinned to the bottom
    # either way.
    expanded = rail.layout().minimumSize().height()

    rail.toggle()
    qapp.processEvents()
    assert not rail._logo_gap.isVisible(), "the spacer goes with the crest"
    assert rail._logo.height() == 0
    collapsed = rail.layout().minimumSize().height()
    assert collapsed <= expanded - logo_block

    rail.toggle()
    qapp.processEvents()
    assert rail._logo_gap.isVisible()
    assert rail.layout().minimumSize().height() == expanded


def test_the_logo_and_the_toggle_do_not_overlap(rail) -> None:
    assert rail._logo.geometry().bottom() < rail._toggle.geometry().top()
    assert rail._toggle.geometry().bottom() <= rail.height()


def test_the_toggle_stays_reachable_when_collapsed(rail, qapp) -> None:
    rail.toggle()
    qapp.processEvents()
    assert rail._toggle.isVisible()
    assert rail._toggle.width() <= rail.width()
    assert rail._toggle.geometry().left() >= 0


@pytest.mark.parametrize("height", [700, 768, 980])
def test_nothing_in_the_rail_falls_off_the_screen(rail, qapp, height) -> None:
    rail.resize(208, height)
    qapp.processEvents()
    for key, button in rail._buttons.items():
        assert button.geometry().bottom() <= height, f"{key} is off the screen"
    assert rail._logo.geometry().bottom() <= height
    assert rail._toggle.geometry().bottom() <= height


# --------------------------------------------------------------- sign-in


def test_the_sign_in_screen_carries_the_packaged_crest(window) -> None:
    page = window._auth_page
    assert page._logo.isVisible()
    pixmap = page._logo.pixmap()
    assert not pixmap.isNull()
    assert pixmap.height() <= 88, "large enough to see, small enough to fit"
    assert page._logo.accessibleName()


def test_a_missing_crest_leaves_a_working_sign_in(qapp, tmp_path, monkeypatch):
    """Decoration must never be load-bearing."""
    monkeypatch.setattr("kinecapture.gui.auth.asset_bytes", lambda name: None)
    config = AppConfig(
        dataset_root=tmp_path / "data",
        log_dir=tmp_path / "logs",
        identity_db_path=tmp_path / "identity.sqlite3",
    )
    window = MainWindow(config)
    window.resize(1120, 700)
    window.show()
    qapp.processEvents()
    try:
        page = window._auth_page
        assert not page._logo.isVisible()
        assert page._setup_fields.line("username").isVisible()
        assert not window.grab().isNull()
    finally:
        destroy(window)


@pytest.mark.parametrize("theme_name", THEMES)
def test_the_sign_in_form_fits_every_supported_window(
    qapp, window, theme_name
) -> None:
    """All three viewports against one window, one stylesheet application.

    The sizes are looped inside the test rather than parametrised because
    applying the stylesheet is what costs time, and the size is what is being
    varied - reapplying the theme per size measured nothing extra.
    """
    qapp.setStyleSheet(build_stylesheet(get_theme(theme_name)))
    page = window._auth_page
    fields = page._setup_fields

    for width, height in VIEWPORTS:
        window.resize(width, height)
        qapp.processEvents()

        assert page._scroll.widget() is not None
        for name in ("first_name", "last_name", "username"):
            line = fields.line(name)
            assert line.width() > 0, f"{name} collapsed at {width}x{height}"
        assert page._logo.isVisible() or page._logo.pixmap().isNull()
        assert not window.grab().isNull(), f"paint failed at {width}x{height}"


def test_the_column_never_stretches_across_a_wide_screen(qapp, window) -> None:
    """A 1600px-wide login form is unreadable; the column is bounded."""
    column = window._auth_page._stack
    for width, height in VIEWPORTS:
        window.resize(width, height)
        qapp.processEvents()
        assert column.width() <= 520, f"too wide at {width}"
        assert column.width() >= 320, f"collapsed at {width}"


def test_the_short_screen_scrolls_instead_of_clipping(qapp, window) -> None:
    """The sign-in button must never be the part that goes off the bottom."""
    window.resize(700, 420)
    qapp.processEvents()

    page = window._auth_page
    assert isinstance(page._scroll, QScrollArea)
    assert page._scroll.widgetResizable()
    canvas = page._scroll.widget()
    viewport = page._scroll.viewport()
    if canvas.sizeHint().height() > viewport.height():
        assert page._scroll.verticalScrollBar().maximum() > 0, (
            "content taller than the viewport must be scrollable"
        )
    assert (
        page._scroll.horizontalScrollBarPolicy()
        is Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    ), "a login form must never scroll sideways"


def test_the_footer_wraps_rather_than_widening_the_column(qapp, window) -> None:
    window.resize(1120, 700)
    qapp.processEvents()
    footer = window._auth_page._footer
    assert footer.wordWrap()
    assert footer.width() <= 520


def test_the_login_form_can_be_driven_from_the_keyboard(qapp, window) -> None:
    fields = window._auth_page._setup_fields
    fields.line("first_name").setText("Sistem")
    fields.line("last_name").setText("Sahibi")
    fields.line("title").setText("")
    fields.line("username").setText("admin")
    fields.password.setText("owner-password")
    fields.password_confirmation.setText("owner-password")
    window._auth_page._create_owner()
    qapp.processEvents()
    assert window.state.current_user is not None, "the owner was created"
    window._logout()
    qapp.processEvents()

    page = window._auth_page
    assert page._stack.currentWidget() is page._login
    assert page._username.accessibleName() == "Kullanıcı adı"
    assert page._password.accessibleName() == "Şifre"
    assert page._login_button.isDefault(), "Enter submits the form"

    page._username.setText("admin")
    page._password.setText("owner-password")
    page._password.returnPressed.emit()
    qapp.processEvents()
    assert window.state.current_user is not None


def test_the_placeholders_do_not_pretend_to_be_values(window) -> None:
    page = window._auth_page
    assert page._username.placeholderText()
    assert page._username.text() == ""
    assert page._password.placeholderText()
    assert page._password.echoMode() == page._password.EchoMode.Password
