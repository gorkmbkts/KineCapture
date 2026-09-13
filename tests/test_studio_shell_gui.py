"""The Studio window itself, built for real and driven without a human.

Everything here constructs the actual :class:`StudioWindow` - no mocks of our
own widgets - because the things worth checking at this level (lazy pages, the
stylesheet reaching the application, a clean close) only exist once real Qt
objects do.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.studio.app import build_window, install_exception_hook  # noqa: E402
from kinecapture.studio.services.messages import Message, Severity  # noqa: E402
from kinecapture.studio.services.window_state import (  # noqa: E402
    WindowState,
    load_window_state,
)
from kinecapture.studio.theme import load_tokens, stylesheet_for  # noqa: E402
from kinecapture.studio.views import iconset  # noqa: E402
from kinecapture.studio.views.pages.base import PlaceholderPage  # noqa: E402

def has_real_fonts() -> bool:
    """Whether text measurements on this platform mean anything.

    The offscreen plugin reports no font families at all, so every string is
    measured as tofu boxes and comes out far wider than it would on screen.
    Layout assertions are skipped there rather than asserted against nonsense -
    a green test that measured nothing is worse than an honest skip.
    """
    return bool(QFontDatabase.families())


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _config: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True, exist_ok=True)
    state_path = tmp_path / "window_state.json"
    built = build_window(
        config,
        window_state=WindowState(width=1366, height=768, maximised=False),
        state_path=state_path,
    )
    built.state_path_for_test = state_path  # type: ignore[attr-defined]
    built.resize(1366, 768)
    # Shown for real: isVisible() on a child is False for an unshown window,
    # which would make every visibility assertion below pass vacuously.
    built.show()
    # Signed in, because the workspace lives behind the sign-in gate and
    # nothing inside it is visible until somebody is. The gate itself is
    # covered by tests/test_studio_projects_gui.py.
    assert built.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    yield built
    built.close()


# ------------------------------------------------------------------- shell


def test_window_shows_the_whole_workflow(window) -> None:
    assert window.nav_bar.keys == tuple(
        item.key for item in window.viewmodel.destinations
    )
    assert len(window.nav_bar.keys) == 8


def test_pages_are_built_lazily(window, app: QApplication) -> None:
    """Opening the application must not construct seven unseen screens."""
    assert len(window._pages) == 1
    window.viewmodel.navigate("review")
    app.processEvents()
    assert set(window._pages) == {"projects", "review"}


def test_navigating_twice_reuses_the_page(window, app: QApplication) -> None:
    window.viewmodel.navigate("capture")
    app.processEvents()
    first = window.page("capture")
    window.viewmodel.navigate("projects")
    window.viewmodel.navigate("capture")
    app.processEvents()
    assert window.page("capture") is first


def test_nav_selection_follows_the_viewmodel(window, app: QApplication) -> None:
    window.viewmodel.navigate("export")
    app.processEvents()
    button = window.nav_bar.button_for("export")
    assert button is not None and button.isChecked()
    assert window.nav_bar.button_for("projects").isChecked() is False


def test_clicking_a_nav_button_navigates(window, app: QApplication) -> None:
    window.nav_bar.button_for("dataset").click()
    app.processEvents()
    assert window.viewmodel.active_page.value == "dataset"


def test_window_title_names_the_open_screen(window, app: QApplication) -> None:
    window.viewmodel.navigate("processing")
    app.processEvents()
    assert "Verileri Hesapla" in window.windowTitle()


def test_unbuilt_screens_say_which_phase_delivers_them(window, app: QApplication) -> None:
    """A screen that is not built yet stands in its place and names its phase.

    Asks the registry which destinations are still pending rather than naming
    one, so delivering a screen does not break this test.
    """
    from kinecapture.studio.views.pages import PAGE_TYPES

    pending = [d for d in window.viewmodel.destinations if d.key not in PAGE_TYPES]
    assert pending, "her ekran yapıldı; bu test kaldırılabilir"
    destination = pending[0]
    window.viewmodel.navigate(destination.key)
    app.processEvents()
    page = window.page(destination.key)
    assert isinstance(page, PlaceholderPage)
    assert destination.phase in page.accessibleDescription()


# ------------------------------------------------------------------ theming


def test_theme_change_replaces_the_application_stylesheet(
    window, app: QApplication
) -> None:
    window.viewmodel.set_theme("dark")
    app.processEvents()
    assert app.styleSheet() == stylesheet_for("dark")
    window.viewmodel.set_theme("light")
    app.processEvents()
    assert app.styleSheet() == stylesheet_for("light")
    assert window.tokens.name == "light"


def test_both_themes_produce_a_different_sheet() -> None:
    assert stylesheet_for("dark") != stylesheet_for("light")


def test_toggle_theme_returns_to_where_it_started(window) -> None:
    start = window.viewmodel.theme.value
    window.viewmodel.toggle_theme()
    assert window.viewmodel.theme.value != start
    window.viewmodel.toggle_theme()
    assert window.viewmodel.theme.value == start


# -------------------------------------------------------------------- icons


def test_every_named_icon_renders(app: QApplication) -> None:
    tokens = load_tokens("dark")
    for name in iconset.available():
        pixmap = iconset.pixmap(name, tokens.colour("KcTextPrimary"), 16, 1.0)
        assert not pixmap.isNull(), name
        assert pixmap.width() == 16


def test_icons_render_at_device_pixel_ratio(app: QApplication) -> None:
    """A 200% display must get twice the pixels, not an upscaled 16px bitmap."""
    tokens = load_tokens("dark")
    pixmap = iconset.pixmap("folder", tokens.colour("KcTextPrimary"), 16, 2.0)
    assert pixmap.width() == 32
    assert pixmap.devicePixelRatio() == 2.0


def test_unknown_icon_is_reported_not_silently_blank(app: QApplication) -> None:
    with pytest.raises(iconset.IconError):
        iconset.pixmap("no-such-icon", "#000000", 16, 1.0)


# ----------------------------------------------------------------- inspector


def test_closed_inspector_takes_no_width(window, app: QApplication) -> None:
    window.viewmodel.inspector_open.set(False)
    app.processEvents()
    assert window.inspector.isVisible() is False
    assert window.inspector.width() == 0 or not window.inspector.isVisible()


def test_inspector_toggles_from_the_context_bar(window, app: QApplication) -> None:
    window.context_bar.inspector_button.click()
    app.processEvents()
    assert window.viewmodel.inspector_open.value is True
    assert window.inspector.isVisible() is True


# ------------------------------------------------------------------ messages


def test_a_message_lands_on_the_open_page(window, app: QApplication) -> None:
    window.viewmodel.navigate("capture")
    app.processEvents()
    window.viewmodel.report(
        Message(
            headline="Disk yetersiz.",
            severity=Severity.WARNING,
            detail="Daha fazla yer açın.",
            code="insufficient_disk_space",
            technical={"gereken": "12 GB"},
        )
    )
    app.processEvents()
    page = window.page("capture")
    assert page.messages.isVisible()
    assert page.messages.current is not None
    assert page.messages.current.code == "insufficient_disk_space"


def test_technical_detail_is_hidden_until_asked_for(window, app: QApplication) -> None:
    window.viewmodel.report(
        Message(headline="Bir şey oldu.", code="x", technical={"a": 1})
    )
    app.processEvents()
    bar = window.page(window.viewmodel.active_page.value).messages
    assert bar.details_visible is False
    bar._toggle_details()
    app.processEvents()
    assert bar.details_visible is True
    assert "a: 1" in bar._technical.text()


def test_closing_a_message_hides_the_bar(window, app: QApplication) -> None:
    window.viewmodel.notify("Tamamlandı")
    app.processEvents()
    bar = window.page(window.viewmodel.active_page.value).messages
    assert bar.isVisible()
    bar.clear()
    assert bar.isVisible() is False
    assert bar.current is None


def test_exception_hook_turns_a_crash_into_a_message(window) -> None:
    import sys

    seen = []
    window.viewmodel.message.subscribe(seen.append)
    previous = sys.excepthook
    try:
        install_exception_hook(window)
        try:
            raise RuntimeError("beklenmedik")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
    finally:
        sys.excepthook = previous
    assert len(seen) == 1
    assert seen[0].severity is Severity.ERROR
    assert "beklenmedik" in seen[0].technical_text()


# --------------------------------------------------------------------- close


def test_closing_saves_what_the_user_was_looking_at(window, app: QApplication) -> None:
    window.viewmodel.navigate("dataset")
    window.viewmodel.inspector_open.set(True)
    app.processEvents()
    path = window.state_path_for_test
    window.close()
    saved = load_window_state(path)
    assert saved.active_page == "dataset"
    assert saved.inspector_open is True


def test_closing_detaches_every_subscription(window, app: QApplication) -> None:
    viewmodel = window.viewmodel
    window.viewmodel.navigate("review")
    app.processEvents()
    assert viewmodel.active_page.subscriber_count > 0
    window.close()
    assert viewmodel.active_page.subscriber_count == 0
    assert viewmodel.context.subscriber_count == 0


# -------------------------------------------------------------------- layout


@pytest.mark.parametrize("size", [(1120, 700), (1366, 768), (1600, 980)])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_shell_fits_every_supported_viewport(window, app, size, theme) -> None:
    if not has_real_fonts():
        pytest.skip("offscreen platformda font ailesi yok; ölçüm anlamsız")
    window.viewmodel.set_theme(theme)
    window.resize(*size)
    app.processEvents()
    hint = window.minimumSizeHint()
    assert hint.width() <= size[0], f"{theme} {size}: {hint.width()}px gerekiyor"
    assert hint.height() <= size[1], f"{theme} {size}: {hint.height()}px gerekiyor"
