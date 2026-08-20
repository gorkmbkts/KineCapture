"""Vector icon set.

Icons are SVG path data rendered through ``QPainter`` at request time. That
choice buys three things:

* they are tinted by the current theme, so the same icon works on dark and
  light backgrounds without shipping two files;
* they are rendered per device-pixel-ratio, so they stay crisp under Windows
  display scaling instead of blurring like a bitmap;
* there are no binary assets in the repository.

No emoji are used anywhere in the interface.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: All paths are authored on a 24x24 grid with a 2px stroke.
_ICON_PATHS: dict[str, str] = {
    "dashboard": "M4 13h7V4H4v9zm0 7h7v-5H4v5zm9 0h7V11h-7v9zm0-16v5h7V4h-7z",
    "project": "M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z",
    "participants": (
        "M9 11a3.5 3.5 0 100-7 3.5 3.5 0 000 7zm-7 8a7 7 0 0114 0H2zm14.5-8.5"
        "a3 3 0 100-6 3 3 0 000 6zM17 12a5.5 5.5 0 015 5.5h-4.2A8.7 8.7 0 0017 12z"
    ),
    "capture": (
        "M4 7h3l1.5-2h7L17 7h3a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V8a1 1 0 011-1z"
        "M12 16.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7z"
    ),
    "review": (
        "M4 5h16v11H4V5zm4 15h8M12 16v4M9 8.5v5l4.5-2.5L9 8.5z"
    ),
    "dataset": (
        "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 9v4c0 1.7 3.6 3 8 3"
        "s8-1.3 8-3V9M4 15v3c0 1.7 3.6 3 8 3s8-1.3 8-3v-3"
    ),
    "export": "M12 3v11m0-11l-4 4m4-4l4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2",
    "settings": (
        "M12 15.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM19.4 13a7.6 7.6 0 000-2l2-1.5"
        "-2-3.5-2.4 1a7.6 7.6 0 00-1.7-1L15 3H9l-.3 2.9a7.6 7.6 0 00-1.7 1l-2.4-1"
        "-2 3.5L4.6 11a7.6 7.6 0 000 2l-2 1.5 2 3.5 2.4-1a7.6 7.6 0 001.7 1L9 21h6"
        "l.3-2.9a7.6 7.6 0 001.7-1l2.4 1 2-3.5-2-1.5z"
    ),
    "record": "M12 20a8 8 0 100-16 8 8 0 000 16z",
    "stop": "M6 6h12v12H6z",
    "play": "M7 4.5l12 7.5-12 7.5v-15z",
    "pause": "M8 5h3v14H8zm5 0h3v14h-3z",
    "step-forward": "M6 5l9 7-9 7V5zm11 0h2v14h-2z",
    "step-back": "M18 5l-9 7 9 7V5zM7 5H5v14h2z",
    "marker": "M12 3l2.5 6.5H21l-5.2 4 2 6.5-5.8-4-5.8 4 2-6.5-5.2-4h6.5L12 3z",
    "check": "M4 12.5l5.5 5.5L20 6.5",
    "warning": "M12 3l9.5 17H2.5L12 3zm0 6v5m0 3v.5",
    "error": "M12 4a8 8 0 100 16 8 8 0 000-16zm-3 5l6 6m0-6l-6 6",
    "info": "M12 4a8 8 0 100 16 8 8 0 000-16zm0 4v.5m0 3v5",
    "camera": "M4 8h16v11H4V8zm5 0l1.5-3h3L15 8M12 16.5a3 3 0 100-6 3 3 0 000 6z",
    "disk": "M4 5h16v14H4V5zm4 0v6h8V5M8 15h8",
    "refresh": "M20 12a8 8 0 11-2.3-5.7M20 4v4h-4",
    "add": "M12 5v14M5 12h14",
    "trash": "M5 7h14M9 7V5h6v2m-8 0v12h10V7M10 11v5m4-5v5",
    "edit": "M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4",
    "split": "M12 4v6m0 0l-5 4v6m5-10l5 4v6",
    "merge": "M7 4v6l5 4v6m10-16v6l-5 4",
    "undo": "M9 8H5V4M5.5 8.5A8 8 0 1112 20",
    "redo": "M15 8h4V4m-.5 4.5A8 8 0 1012 20",
    "chevron-left": "M15 5l-7 7 7 7",
    "chevron-right": "M9 5l7 7-7 7",
    "chevron-down": "M5 9l7 7 7-7",
    "close": "M6 6l12 12M18 6L6 18",
    "search": "M11 18a7 7 0 100-14 7 7 0 000 14zm5.5-1.5L21 21",
    "eye": "M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6zm10 2.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z",
    "skeleton": (
        "M12 3.5a2 2 0 100 4 2 2 0 000-4zM12 8v5m0 0l-3.5 3M12 13l3.5 3M8 9.5h8"
        "M8.5 20l0-4M15.5 20l0-4"
    ),
    "depth": "M4 6h16M4 12h16M4 18h16M8 3v18M16 3v18",
    "clock": "M12 4a8 8 0 100 16 8 8 0 000-16zm0 3.5V12l3 2",
    "folder-open": "M3 8h14l-2 10H3.5L3 8zm0 0V6a1 1 0 011-1h4l2 2h7a1 1 0 011 1v1",
    "shield": "M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6l8-3z",
    "flask": "M9 3h6M10 3v6l-5 9a2 2 0 001.8 3h10.4a2 2 0 001.8-3l-5-9V3",
    "list": "M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01",
    "target": (
        "M12 4a8 8 0 100 16 8 8 0 000-16zm0 4a4 4 0 100 8 4 4 0 000-8zm0 3.5"
        "a.5.5 0 100 1 .5.5 0 000-1z"
    ),
}

#: Icons that read better filled than stroked.
_FILLED = frozenset({"record", "stop", "play", "pause", "marker", "dashboard"})


def icon_names() -> tuple[str, ...]:
    return tuple(sorted(_ICON_PATHS))


def _svg_source(name: str, color: str, stroke_width: float) -> str:
    path = _ICON_PATHS.get(name, _ICON_PATHS["info"])
    if name in _FILLED:
        paint = f'fill="{color}" stroke="none"'
    else:
        paint = (
            f'fill="none" stroke="{color}" stroke-width="{stroke_width}" '
            'stroke-linecap="round" stroke-linejoin="round"'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path d="{path}" {paint}/></svg>'
    )


@lru_cache(maxsize=512)
def _render(name: str, color: str, size: int, ratio: float, stroke: float) -> QPixmap:
    device = max(1, int(round(size * ratio)))
    pixmap = QPixmap(device, device)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_svg_source(name, color, stroke).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_pixmap(
    name: str,
    color: str,
    size: int = 18,
    *,
    device_pixel_ratio: float = 1.0,
    stroke_width: float = 1.9,
) -> QPixmap:
    """Render one icon as a pixmap tinted ``color``."""
    return _render(name, color, size, float(device_pixel_ratio), stroke_width)


def get_icon(
    name: str,
    color: str,
    size: int = 18,
    *,
    disabled_color: Optional[str] = None,
    device_pixel_ratio: float = 1.0,
) -> QIcon:
    """A :class:`QIcon` with a normal and (optionally) a disabled appearance."""
    icon = QIcon()
    icon.addPixmap(
        icon_pixmap(name, color, size, device_pixel_ratio=device_pixel_ratio),
        QIcon.Mode.Normal,
    )
    if disabled_color:
        icon.addPixmap(
            icon_pixmap(name, disabled_color, size, device_pixel_ratio=device_pixel_ratio),
            QIcon.Mode.Disabled,
        )
    return icon


def app_icon(accent: str, background: str) -> QIcon:
    """Window and taskbar icon: the skeleton glyph on a rounded plate."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(background))
        painter.setPen(Qt.PenStyle.NoPen)
        radius = size * 0.22
        painter.drawRoundedRect(0, 0, size, size, radius, radius)
        painter.end()

        glyph = icon_pixmap("skeleton", accent, int(size * 0.68))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        offset = int((size - glyph.width()) / 2)
        painter.drawPixmap(offset, offset, glyph)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def clear_icon_cache() -> None:
    """Drop cached renders. Called when the theme changes."""
    _render.cache_clear()


def icon_size(size: int) -> QSize:
    return QSize(size, size)


__all__ = [
    "app_icon",
    "clear_icon_cache",
    "get_icon",
    "icon_names",
    "icon_pixmap",
    "icon_size",
]
