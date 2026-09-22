"""Theme-tinted, DPI-correct icons from the bundled Lucide set.

Lucide ships every icon with ``stroke="currentColor"``. Qt's SVG renderer has
no cascading colour, so the tint is applied by substituting that string before
rendering - which keeps one file per icon serving both themes instead of
shipping a dark and a light copy of each.

Rendering happens at the widget's device pixel ratio, so an icon stays sharp at
125/150/200% Windows scaling instead of being a blurred upscale of a 16px
bitmap.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from kinecapture.studio.theme import ThemeTokens

#: Nav destination icon key -> Lucide file name. The indirection is deliberate:
#: the product's vocabulary ("record") should not be pinned to one icon set's
#: naming, so swapping sets later is a change in this table alone.
ICON_NAMES: dict[str, str] = {
    "folder": "folder",
    "record": "video",
    "cpu": "cpu",
    "film": "film",
    "tag": "tag",
    "grid": "table",
    "export": "package",
    "settings": "settings",
    # shell and status
    "inspector": "panel-right",
    "theme-dark": "moon",
    "theme-light": "sun",
    "expand": "chevron-down",
    "forward": "chevron-right",
    "close": "x",
    "warning": "triangle-alert",
    "info": "info",
    "error": "circle-alert",
    "ok": "check",
    "search": "search",
    "refresh": "refresh-cw",
    "sign-out": "log-out",
    "user": "user",
    "disk": "hard-drive",
    "live": "circle-dot",
    "play": "play",
    "pause": "pause",
    # Transport. Five controls that used to be three "▶" characters and two
    # bracketed ones: at 16 px nobody could tell "oynat" from "bir kare ileri".
    "first": "skip-back",
    "last": "skip-forward",
    "step-back": "chevron-left",
    "step-forward": "chevron-right",
    "loop": "repeat",
    "speed": "gauge",
    # Capture. Recording is a dot, stopping a square - the two shapes every
    # recorder has used since tape, so the meaning does not rest on red.
    # ("record" above is the *destination* icon for Yakalama and stays a
    # camera; these two are the action.)
    "record-start": "circle",
    "record-stop": "square",
    "marker": "flag",
    "connect": "plug",
    "disconnect": "unplug",
    # The labelling tools. "Gez", "Hareket çiz" and "Hata çiz" were words in a
    # row of identical buttons; they are three different jobs and now look it.
    "navigate": "move",
    "draw-movement": "activity",
    "draw-fault": "triangle-alert",
    "snap": "magnet",
    "zoom-in": "zoom-in",
    "zoom-out": "zoom-out",
    "zoom-all": "scan",
    "undo": "undo-2",
    "redo": "redo-2",
    "save": "save",
    "saved": "circle-check",
    "more": "ellipsis",
    # The right-hand panel's vertical strip, and the camera tools on it.
    "camera-tools": "box",
    "labels": "tag",
    "people": "users",
    "summary": "list",
    "compass": "compass",
    "centre": "crosshair",
    "fit": "scan",
    "floor": "grid-3x3",
    "overlay-on": "eye",
    "overlay-off": "eye-off",
    "save-view": "bookmark",
    "previous-view": "rotate-ccw",
    "joints": "bone",
    # Shared small actions.
    "add": "plus",
    "delete": "trash-2",
    "edit": "square-pen",
    "back": "arrow-left",
    "next": "arrow-right",
    "filter": "filter",
    "layers": "layers",
    "busy": "loader-circle",
    "clock": "clock",
    "collapse": "chevrons-up-down",
}


class IconError(KeyError):
    """An icon was asked for that the bundled set does not contain."""


@lru_cache(maxsize=64)
def _source(name: str) -> str:
    file_name = ICON_NAMES.get(name, name)
    try:
        return (
            resources.files("kinecapture.studio.views.icons")
            .joinpath(f"{file_name}.svg")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise IconError(f"İkon paketinde yok: {name} ({file_name}.svg)") from exc


def available() -> tuple[str, ...]:
    return tuple(sorted(ICON_NAMES))


@lru_cache(maxsize=512)
def pixmap(name: str, colour: str, size: int, ratio: float = 1.0) -> QPixmap:
    """One rendered icon. Cached: the nav bar repaints far more often than it changes."""
    svg = _source(name).replace("currentColor", colour)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    scaled = max(1, int(round(size * ratio)))
    image = QImage(scaled, scaled, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(ratio)
    return result


def icon(
    name: str,
    tokens: ThemeTokens,
    *,
    colour_token: str = "KcTextSecondary",
    size: Optional[int] = None,
    ratio: float = 1.0,
) -> QIcon:
    """A :class:`QIcon` tinted with ``colour_token`` from the active theme."""
    resolved = size or tokens.metric("KcIconSize")
    return QIcon(pixmap(name, tokens.colour(colour_token), resolved, ratio))


def icon_size(tokens: ThemeTokens, *, large: bool = False) -> QSize:
    value = tokens.metric("KcIconSizeLarge" if large else "KcIconSize")
    return QSize(value, value)


__all__ = ["ICON_NAMES", "IconError", "available", "icon", "icon_size", "pixmap"]
