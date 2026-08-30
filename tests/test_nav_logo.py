"""The university logo in the navigation rail.

It is decoration, which makes two things important: it must never be the reason
the application fails to start, and it must never take space the navigation
needs. Both are easy to get wrong and neither is visible in a screenshot of the
happy path.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.gui.assets import YTU_LOGO, asset_bytes  # noqa: E402
from kinecapture.gui.main_window import (  # noqa: E402
    NavigationRail,
    _load_logo_pixmap,
)
from kinecapture.gui.theme import get_theme  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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


# ------------------------------------------------------------- the resource


def test_the_logo_is_a_package_resource_not_a_repository_path() -> None:
    """An installed application has no ``files/`` folder to look in."""
    data = asset_bytes(YTU_LOGO)
    assert data, "the logo must resolve through importlib.resources"
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "and still be the original PNG"


def test_the_logo_keeps_its_transparency_and_aspect(qapp) -> None:
    pixmap = _load_logo_pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.hasAlphaChannel(), "the crest is drawn on a transparent field"
    assert pixmap.width() == 398 and pixmap.height() == 405, (
        "the source must not be re-encoded or resampled on disk"
    )


def test_a_missing_logo_does_not_break_the_rail(qapp, monkeypatch) -> None:
    monkeypatch.setattr(
        "kinecapture.gui.main_window.asset_bytes", lambda name: None
    )
    widget = NavigationRail(get_theme("dark"))
    widget.add_page("dashboard", "Ana Sayfa", "dashboard")
    widget.resize(208, 700)
    widget.show()
    qapp.processEvents()

    assert widget._logo_source is None
    assert not widget._logo.isVisible()
    assert widget._buttons["dashboard"].isVisible(), "navigation still works"
    assert not widget.grab().isNull()
    widget.hide()


def test_corrupt_image_data_is_reported_not_raised(qapp, monkeypatch) -> None:
    monkeypatch.setattr(
        "kinecapture.gui.main_window.asset_bytes", lambda name: b"not a png"
    )
    assert _load_logo_pixmap() is None


# --------------------------------------------------------------- placement


def test_the_logo_sits_between_the_navigation_and_the_collapse_button(rail) -> None:
    assert rail._logo.isVisible()
    last_button = rail._buttons["settings"]
    assert last_button.geometry().bottom() < rail._logo.geometry().top()
    assert rail._logo.geometry().bottom() <= rail._toggle.geometry().top()


def test_the_logo_is_horizontally_centred(rail) -> None:
    logo = rail._logo.geometry()
    assert abs(logo.center().x() - rail.rect().center().x()) <= 2


def test_the_logo_keeps_its_aspect_ratio_when_scaled(rail) -> None:
    pixmap = rail._logo.pixmap()
    assert not pixmap.isNull()
    source = rail._logo_source
    assert abs(
        pixmap.width() / pixmap.height() - source.width() / source.height()
    ) < 0.02
    assert pixmap.width() <= 208


def test_the_logo_never_pushes_the_navigation_off_a_700px_screen(qapp, rail) -> None:
    rail.resize(208, 700)
    qapp.processEvents()
    for key, button in rail._buttons.items():
        assert button.geometry().bottom() <= 700, f"{key} is off the screen"
    assert rail._toggle.geometry().bottom() <= 700
    assert rail._logo.height() <= 96


# ------------------------------------------------------------- collapsing


def test_collapsing_hides_the_logo_completely(rail, qapp) -> None:
    """Not shrunk to an icon: a 40px crest is unreadable and still costs space."""
    rail.toggle()
    qapp.processEvents()

    assert not rail._logo.isVisible()
    assert rail._logo.height() == 0, "it must leave no gap behind"
    assert rail._logo.pixmap().isNull()
    assert not rail.grab().isNull()


def test_expanding_restores_it_at_the_right_size(rail, qapp) -> None:
    rail.toggle()  # collapsed
    qapp.processEvents()
    rail.toggle()  # expanded again
    qapp.processEvents()

    assert rail._logo.isVisible()
    assert not rail._logo.pixmap().isNull()
    assert rail._logo.height() > 0


def test_repeated_collapsing_does_not_degrade_or_leak(rail, qapp) -> None:
    """Rescaling from the last scaled copy would blur it a little each time."""
    first = rail._logo.pixmap().size()
    source_id = id(rail._logo_source)

    for _ in range(8):
        rail.toggle()
        qapp.processEvents()
        rail.toggle()
        qapp.processEvents()

    assert rail._logo.pixmap().size() == first, "the size must be stable"
    assert id(rail._logo_source) == source_id, (
        "the original must be kept and rescaled, not replaced"
    )


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_the_rail_paints_in_both_themes_with_the_logo(qapp, theme_name) -> None:
    widget = NavigationRail(get_theme(theme_name))
    widget.add_page("dashboard", "Ana Sayfa", "dashboard")
    widget.resize(208, 700)
    widget.show()
    qapp.processEvents()
    assert widget._logo.isVisible()
    assert not widget.grab().isNull()
    widget.hide()
