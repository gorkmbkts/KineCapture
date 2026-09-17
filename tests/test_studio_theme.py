"""One theme, everywhere, with enough contrast to read.

The 15 September audit switched to the light theme with Ayarlar open and got a
light shell wrapped around a dark form: the shell was styled, the page was not,
and the unstyled part fell back to the *platform's* palette, which on this
machine is dark.

So this file checks three things, none of them by looking at a screenshot:

* the application palette is built from the tokens, in both themes, so there is
  no third source of colour;
* the stylesheet names every surface Qt would otherwise leave to the platform;
* the colours are actually readable - measured, in both themes, including the
  secondary and disabled text the eye is most likely to let through.
"""

from __future__ import annotations

import itertools
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.theme import (  # noqa: E402
    CLASS_COLOURS,
    FAULT_COLOURS,
    class_colour_token,
    load_tokens,
    stylesheet_for,
    theme_names,
)
from kinecapture.studio.theme.generator import load_template  # noqa: E402
from kinecapture.studio.views.palette import palette_for  # noqa: E402
from kinecapture.studio.views.qssassets import STYLESHEET_ICONS, install  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------ colour
def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(value: str) -> float:
    colour = QColor(value)
    r, g, b = (_linear(c / 255.0) for c in (colour.red(), colour.green(), colour.blue()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def _lab(value: str) -> tuple[float, float, float]:
    colour = QColor(value)
    r, g, b = (_linear(c / 255.0) for c in (colour.red(), colour.green(), colour.blue()))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def distance(first: str, second: str) -> float:
    """Perceptual distance. Two colours can have equal brightness and still be
    obviously different, which is exactly what a class palette wants."""
    return math.dist(_lab(first), _lab(second))


#: (foreground, background, minimum ratio). The secondary, muted and disabled
#: rows are the point: the brief asks for readable *secondary* text, passive
#: buttons and timeline labels, not only for headline contrast.
CONTRAST_RULES = (
    ("KcTextPrimary", "KcSurfaceBase", 7.0),
    ("KcTextPrimary", "KcSurfaceRaised", 7.0),
    ("KcTextPrimary", "KcSurfaceControl", 7.0),
    ("KcTextPrimary", "KcSurfaceHeader", 7.0),
    ("KcTextPrimary", "KcSurfaceOverlay", 7.0),
    ("KcTextPrimary", "KcSurfaceSelected", 4.5),
    ("KcTextSecondary", "KcSurfaceRaised", 4.5),
    ("KcTextSecondary", "KcSurfaceHeader", 4.5),
    ("KcTextMuted", "KcSurfaceRaised", 3.0),
    ("KcTextMuted", "KcSurfaceHeader", 3.0),
    ("KcTextDisabled", "KcSurfaceBase", 3.0),
    ("KcTextDisabled", "KcSurfaceRaised", 3.0),
    ("KcTextOnAccent", "KcAccentPrimary", 4.5),
    ("KcStatusRecording", "KcStatusRecordingMuted", 4.5),
    ("KcStatusWarning", "KcStatusWarningMuted", 4.5),
    ("KcStatusLive", "KcStatusLiveMuted", 4.5),
    ("KcStatusRecording", "KcSurfaceRaised", 3.0),
    ("KcStatusWarning", "KcSurfaceRaised", 3.0),
    ("KcStatusLive", "KcSurfaceRaised", 3.0),
    ("KcAccentPrimary", "KcSurfaceRaised", 3.0),
    ("KcFocusRing", "KcSurfaceControl", 3.0),
    ("KcPlayhead", "KcSurfaceSunken", 4.5),
    ("KcTrimHandle", "KcSurfaceSunken", 4.5),
)


@pytest.mark.parametrize("theme", theme_names())
def test_every_pairing_the_interface_uses_is_readable(theme: str) -> None:
    tokens = load_tokens(theme)
    failures = []
    for foreground, background, minimum in CONTRAST_RULES:
        found = contrast(tokens.colour(foreground), tokens.colour(background))
        if found < minimum:
            failures.append(f"{theme}: {foreground} on {background} = {found:.2f} < {minimum}")
    assert not failures, failures


@pytest.mark.parametrize("theme", theme_names())
def test_a_class_keeps_a_colour_you_can_tell_from_its_neighbours(theme: str) -> None:
    tokens = load_tokens(theme)
    for family in (CLASS_COLOURS, FAULT_COLOURS):
        for first, second in itertools.combinations(family, 2):
            found = distance(tokens.colour(first), tokens.colour(second))
            assert found >= 18.0, f"{theme}: {first} and {second} are {found:.1f} apart"


@pytest.mark.parametrize("theme", theme_names())
def test_movement_and_error_colours_are_two_different_families(theme: str) -> None:
    """A glance must separate "this is a movement" from "this is a fault"."""
    tokens = load_tokens(theme)
    worst = min(
        distance(tokens.colour(movement), tokens.colour(fault))
        for movement in CLASS_COLOURS
        for fault in FAULT_COLOURS
    )
    assert worst >= 25.0, f"{theme}: families are only {worst:.1f} apart"


@pytest.mark.parametrize("theme", theme_names())
def test_class_intervals_stand_out_from_the_timeline_ground(theme: str) -> None:
    tokens = load_tokens(theme)
    ground = tokens.colour("KcSurfaceSunken")
    for token in CLASS_COLOURS + FAULT_COLOURS:
        assert contrast(tokens.colour(token), ground) >= 2.0, token


def test_a_class_colour_is_stable_and_wraps_rather_than_running_out() -> None:
    assert class_colour_token(0) == CLASS_COLOURS[0]
    assert class_colour_token(len(CLASS_COLOURS)) == CLASS_COLOURS[0]
    assert class_colour_token(0, fault=True) == FAULT_COLOURS[0]
    # Same index, same token, every time: a project's colours do not move.
    assert class_colour_token(3) == class_colour_token(3)


# ----------------------------------------------------------------- palette
@pytest.mark.parametrize("theme", theme_names())
def test_the_palette_comes_from_the_tokens(app, theme: str) -> None:
    tokens = load_tokens(theme)
    palette = palette_for(tokens)
    assert palette.color(QPalette.ColorRole.Window) == QColor(tokens.colour("KcSurfaceBase"))
    assert palette.color(QPalette.ColorRole.Base) == QColor(tokens.colour("KcSurfaceControl"))
    assert palette.color(QPalette.ColorRole.WindowText) == QColor(
        tokens.colour("KcTextPrimary")
    )
    # Inactive is not the platform's business either: a window that lost focus
    # must not change colour family.
    assert palette.color(
        QPalette.ColorGroup.Inactive, QPalette.ColorRole.Window
    ) == QColor(tokens.colour("KcSurfaceBase"))
    assert palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
    ) == QColor(tokens.colour("KcTextDisabled"))


def test_the_two_themes_do_not_share_a_palette(app) -> None:
    dark = palette_for(load_tokens("dark"))
    light = palette_for(load_tokens("light"))
    assert dark.color(QPalette.ColorRole.Window) != light.color(QPalette.ColorRole.Window)


# -------------------------------------------------------------- stylesheet
#: Selectors Qt would otherwise paint from the platform palette. Each one was
#: either seen leaking in the audit or is the same class of surface as one
#: that was.
REQUIRED_SELECTORS = (
    "QAbstractScrollArea",
    "QScrollArea",
    "QTabBar::tab",
    "QTabWidget::pane",
    "QMenu",
    "QHeaderView::section",
    "QTableView::item",
    "QGroupBox",
    "QProgressBar",
    "QSpinBox::up-button",
    "QComboBox::down-arrow",
    "QToolTip",
    "QToolButton",
)


@pytest.mark.parametrize("selector", REQUIRED_SELECTORS)
def test_the_stylesheet_owns_every_surface_qt_would_guess_at(selector: str) -> None:
    template = load_template()
    assert selector in template, f"{selector} is left to the platform palette"


def test_the_viewport_of_a_scroll_area_is_painted_by_us() -> None:
    """The exact rule that fixes the dark island in the light theme."""
    template = load_template()
    assert "QScrollArea > QWidget > QWidget" in template


#: Containers that draw a border of their own. Whatever they hold has to be
#: held *inside* it, not printed on the line.
BORDERED_CONTAINERS = (
    "QTabWidget::pane",
    'QFrame[kcSurface="raised"]',
    'QFrame[kcSurface="sunken"]',
    "QGroupBox",
)


@pytest.mark.parametrize("selector", BORDERED_CONTAINERS)
def test_a_container_that_draws_a_border_keeps_its_contents_off_it(
    selector: str,
) -> None:
    """Padding is declared next to the border that makes it necessary.

    Every one of these rules drew a border and then let a layout start on the
    pixel after it. In the 16 September screenshots the labelling inspector's
    heading and its help text were printed against the pane outline.
    """
    template = load_template()
    block = template.split(selector, 1)[1].split("}", 1)[0]
    assert "padding" in block, f"{selector} draws a border with nothing inside it"


def test_a_tab_pane_really_insets_what_it_holds(app) -> None:
    """The box model, not the text of the rule: measured through Qt."""
    from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

    app.setStyleSheet(stylesheet_for("dark"))
    tabs = QTabWidget()
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel("Hareketler"))
    layout.addStretch(1)
    tabs.addTab(page, "Etiket")
    tabs.resize(320, 400)
    tabs.show()
    app.processEvents()
    try:
        inset = page.mapTo(tabs, page.rect().topLeft()).x()
        assert inset >= 8, f"the pane insets its contents by only {inset}px"
    finally:
        tabs.close()
        app.setStyleSheet("")


@pytest.mark.parametrize("theme", theme_names())
def test_the_generated_sheet_has_no_unresolved_token(theme: str) -> None:
    sheet = stylesheet_for(theme)
    assert "@" not in sheet.split("*/", 1)[1]


@pytest.mark.parametrize("theme", theme_names())
def test_the_stylesheet_images_exist_for_each_theme(app, theme: str) -> None:
    """Arrows and ticks are ours too; Qt's own are drawn for Qt's own palette."""
    tokens = load_tokens(theme)
    directory = install(tokens)
    for name, (_icon, token) in STYLESHEET_ICONS.items():
        path = directory / name
        assert path.exists(), name
        assert tokens.colour(token) in path.read_text(encoding="utf-8")


# ----------------------------------------------------- switching for real
@pytest.fixture
def window(app, tmp_path, monkeypatch):
    from kinecapture.core.config import AppConfig
    from kinecapture.studio.app import build_window

    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    config.theme = "dark"
    built = build_window(config, state_path=tmp_path / "window.json")
    built.resize(1920, 1032)
    built.show()
    assert built.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    yield built
    built.close()


def _grounds(window) -> dict[str, QColor]:
    """The ground colour every kind of surface is actually painted with."""
    from PySide6.QtWidgets import QAbstractScrollArea

    found: dict[str, QColor] = {}
    for widget in window.findChildren(QAbstractScrollArea):
        viewport = widget.viewport()
        if viewport is not None:
            found[f"viewport:{id(viewport)}"] = viewport.palette().color(
                viewport.backgroundRole()
            )
    found["window"] = window.palette().color(QPalette.ColorRole.Window)
    return found


def test_switching_to_the_light_theme_leaves_no_dark_islands(window, app) -> None:
    """Ayarlar open, dark -> light, and nothing keeps the old family.

    This is the audit's exact sequence. The failure it found was a light shell
    around a dark form, which shows up here as a scroll-area viewport whose
    ground is still a dark colour.
    """
    window.viewmodel.navigate("settings")
    app.processEvents()

    window.viewmodel.set_theme("light")
    app.processEvents()
    light = load_tokens("light")

    assert QApplication.instance().palette().color(QPalette.ColorRole.Window) == QColor(
        light.colour("KcSurfaceBase")
    )
    for name, colour in _grounds(window).items():
        assert luminance(colour.name()) > 0.4, f"{name} stayed dark: {colour.name()}"


def test_switching_back_restores_exactly_the_dark_theme(window, app) -> None:
    before = QApplication.instance().palette().color(QPalette.ColorRole.Window)
    window.viewmodel.set_theme("light")
    app.processEvents()
    window.viewmodel.set_theme("dark")
    app.processEvents()
    assert QApplication.instance().palette().color(QPalette.ColorRole.Window) == before
    for name, colour in _grounds(window).items():
        assert luminance(colour.name()) < 0.2, f"{name} stayed light: {colour.name()}"


def test_a_helper_window_opened_earlier_follows_the_theme(window, app) -> None:
    """A tool window is top-level; nothing else would reach it."""
    tool = window.open_tool_window("device")
    app.processEvents()
    window.viewmodel.set_theme("light")
    app.processEvents()
    light = load_tokens("light")
    assert tool._tokens.name == "light"
    ground = tool.tree.viewport().palette().color(tool.tree.viewport().backgroundRole())
    assert luminance(ground.name()) > 0.4, ground.name()
    assert light.colour("KcSurfaceBase")
    tool.close()


def test_pages_built_after_the_switch_get_the_new_theme(window, app) -> None:
    window.viewmodel.set_theme("light")
    app.processEvents()
    page = window.page("dataset")  # built for the first time now
    app.processEvents()
    assert page._tokens.name == "light"


def test_stylesheet_image_urls_name_files_that_exist(app) -> None:
    """``kc:name`` is a filename, not a key: the extension has to be in it.

    Without it Qt resolves nothing, silently, and the combo arrow and the
    checkbox tick simply do not appear.
    """
    import re

    from kinecapture.studio.views.qssassets import SEARCH_PREFIX

    template = load_template()
    referenced = set(re.findall(rf"url\({SEARCH_PREFIX}:([^)]+)\)", template))
    assert referenced, "no themed stylesheet images are referenced at all"
    for theme in theme_names():
        directory = install(load_tokens(theme))
        for name in referenced:
            assert (directory / name).exists(), f"{theme}: {name} was never written"
