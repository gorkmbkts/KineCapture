"""The university crest, and the room things have inside their containers.

The crest identifies the institution the work belongs to. Two rules govern it:
it is never the reason the application fails to start, and it is never altered
to suit a palette - on a dark theme it is placed on a light plate instead, so
navy lettering stays navy and stays readable.

The spacing checks are here because "text touching the edge of its box" was a
direct piece of feedback, and a padding that quietly goes back to zero looks
like nothing in a diff.
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.theme import load_tokens, theme_names  # noqa: E402
from kinecapture.studio.theme.generator import load_template  # noqa: E402
from kinecapture.studio.views.brand import (  # noqa: E402
    CREST_NAME,
    crest_available,
    crest_bytes,
    crest_image,
    crest_pixmap,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------------- crest
def test_the_crest_is_a_package_resource() -> None:
    """An installed application has no ``files/`` folder to look in."""
    data = crest_bytes()
    assert data, "the crest must resolve through importlib.resources"
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "and still be the original PNG"


def test_the_crest_loads(app) -> None:
    image = crest_image()
    assert image is not None and not image.isNull()
    assert crest_available() is True


def test_the_crest_is_never_stretched(app) -> None:
    """The source is 398x405. A round mark squashed into a square is wrong."""
    from kinecapture.studio.views.brand import _fitted
    from PySide6.QtCore import QRectF

    box = QRectF(0, 0, 100, 100)
    fitted = _fitted(box, 398, 405)
    assert fitted.width() / fitted.height() == pytest.approx(398 / 405, abs=1e-6)
    assert fitted.width() <= box.width() and fitted.height() <= box.height()
    # Centred in whatever room is left over.
    assert fitted.center().x() == pytest.approx(box.center().x())
    assert fitted.center().y() == pytest.approx(box.center().y())


@pytest.mark.parametrize("theme", theme_names())
def test_the_crest_is_offered_at_the_size_that_was_asked_for(app, theme: str) -> None:
    tokens = load_tokens(theme)
    pixmap = crest_pixmap(tokens, size=96, ratio=1.0)
    assert pixmap is not None
    assert pixmap.width() == 96 and pixmap.height() == 96


def test_a_high_dpi_crest_is_rendered_not_upscaled(app) -> None:
    tokens = load_tokens("dark")
    pixmap = crest_pixmap(tokens, size=96, ratio=2.0)
    assert pixmap is not None
    # Twice the device pixels, still 96 logical.
    assert pixmap.width() == 192
    assert pixmap.devicePixelRatio() == 2.0


def test_the_dark_theme_puts_the_crest_on_a_light_plate(app) -> None:
    """Navy on charcoal is unreadable; the mark is not recoloured to fix that.

    The plate is a disc that reaches the edges of the box, so the dark
    rendering covers strictly more of the box than the light one, which draws
    the crest straight onto the surface.
    """
    size = 64
    dark = crest_pixmap(load_tokens("dark"), size=size).toImage()
    light = crest_pixmap(load_tokens("light"), size=size).toImage()

    def covered(image) -> int:  # noqa: ANN001
        return sum(
            1
            for x in range(size)
            for y in range(size)
            if image.pixelColor(x, y).alpha() > 0
        )

    assert covered(dark) > covered(light), "the dark theme needs a plate"
    # And the mark itself is untouched: the gold ring is still gold.
    centre_ring = dark.pixelColor(size // 2, 3)
    assert centre_ring.alpha() > 0


def test_a_missing_crest_never_stops_anything(app, monkeypatch) -> None:
    """A decoration that will not load is a log line, not a failure to start."""
    from kinecapture.studio.views import brand

    brand._rendered.cache_clear()
    monkeypatch.setattr(brand, "crest_image", lambda: None)
    try:
        assert brand.crest_pixmap(load_tokens("dark")) is None
        assert brand.crest_pixmap(load_tokens("light")) is None
    finally:
        brand._rendered.cache_clear()


def test_the_sign_in_screen_leads_with_the_crest(app, tmp_path, monkeypatch) -> None:
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
    window = build_window(config, state_path=tmp_path / "window.json")
    try:
        gate = window.auth_view
        assert gate.crest.pixmap() is not None
        assert not gate.crest.pixmap().isNull()
        assert gate.crest.accessibleName() == CREST_NAME
        # The institution's name is *in* the mark. A second, smaller copy of it
        # underneath was removed on 19 September; the accessible name and the
        # tooltip are what carry it now, so nothing is lost to a reader that
        # cannot see the crest.
        assert gate.crest.toolTip() == CREST_NAME
        assert not hasattr(gate, "institution")
        # Large: this is the one screen where the institution leads. Grown by
        # about an eighth in the same change.
        assert gate.crest.width() >= 96
        # And it follows the theme with everything else.
        window.viewmodel.set_theme("light")
        QApplication.processEvents()
        assert gate._tokens.name == "light"
        assert not gate.crest.pixmap().isNull()
    finally:
        window.close()


def test_the_context_bar_carries_a_small_crest(app, tmp_path, monkeypatch) -> None:
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
    window = build_window(config, state_path=tmp_path / "window.json")
    try:
        bar = window.context_bar
        assert not bar.crest.pixmap().isNull()
        # It must not push the bar taller than the bar is allowed to be.
        assert bar.crest.height() <= bar.height()
        # The context fields still land after it, in order.
        window.viewmodel.refresh_context()
        QApplication.processEvents()
        assert bar.field("user") is not None
        assert bar.field("disk") is not None
    finally:
        window.close()


# ----------------------------------------------------------------- spacing
def _padding_values(rule: str, template: str) -> list[str]:
    block = re.search(re.escape(rule) + r"\s*\{([^}]*)\}", template)
    assert block, f"{rule} is not in the stylesheet"
    return re.findall(r"padding:\s*([^;]+);", block.group(1))


#: Selectors whose contents used to sit against their own border. Each must
#: declare a padding, and none of it may be zero.
PADDED = (
    "QPushButton",
    "QToolTip",
    "QMenu::item",
    "QTableView::item, QListWidget::item, QTreeWidget::item, QListView::item",
    "QHeaderView::section",
    "QTabBar::tab",
    "QGroupBox",
    'QLabel[kcStatus="warning"]',
)


@pytest.mark.parametrize("selector", PADDED)
def test_every_container_gives_its_contents_room(selector: str) -> None:
    values = _padding_values(selector, load_template())
    assert values, f"{selector} declares no padding"
    for value in values:
        assert "0px" not in value.split(), f"{selector} pads with zero: {value}"


def test_the_spacing_scale_is_ordered_and_has_a_generous_step() -> None:
    tokens = load_tokens("dark")
    steps = [
        tokens.metric(name)
        for name in (
            "KcSpacingXs",
            "KcSpacingSm",
            "KcSpacingMd",
            "KcSpacingLg",
            "KcSpacingXl",
            "KcSpacingXxl",
        )
    ]
    assert steps == sorted(steps), steps
    assert len(set(steps)) == len(steps), "each step must be a real step"
    assert steps[-1] >= 24, "there has to be a step big enough to frame a page"


def test_a_page_keeps_its_content_off_the_window_edge(app) -> None:
    from kinecapture.studio.viewmodels.navigation import destination
    from kinecapture.studio.views.pages.base import StudioPage

    tokens = load_tokens("dark")
    page = StudioPage(destination("projects"), tokens)
    margins = page.layout().contentsMargins()
    for side in (margins.left(), margins.top(), margins.right(), margins.bottom()):
        assert side >= tokens.metric("KcSpacingXl"), margins
    page.deleteLater()


def test_a_checkbox_keeps_its_label_off_its_own_tick() -> None:
    template = load_template()
    # Anchored to the start of a line so the longer
    # "QLabel, QCheckBox, QRadioButton" rule above it cannot match instead.
    block = re.search(r"^QCheckBox, QRadioButton \{([^}]*)\}", template, re.M)
    assert block, "checkbox spacing is not declared"
    assert "spacing:" in block.group(1)
