"""Theme-tinted images the stylesheet can reference by name.

A Qt stylesheet can draw a combo arrow or a checkbox tick, but only from a
file: there is no way to say "use the current text colour". Left alone Qt falls
back to the platform's own arrow, which is drawn for the platform palette -
the same class of bug as an unstyled scroll-area viewport, and just as visible
the moment the light theme is switched on.

So each theme gets its own small set of tinted SVGs written to a temporary
folder, and that folder is registered under the ``kc:`` search prefix. The
stylesheet then says ``url(kc:chevron-down.svg)`` and gets an arrow in the
colour the theme asked for.

Nothing here is user data and nothing is read back: the folder is scratch
space for the current process, rebuilt whenever the theme changes.
"""

from __future__ import annotations

import logging
import tempfile
from functools import lru_cache
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QDir

from kinecapture.studio.theme import ThemeTokens

logger = logging.getLogger(__name__)

#: Stylesheet asset name -> (icon file, colour token). Small on purpose: every
#: entry here is a place where Qt would otherwise draw something of its own.
STYLESHEET_ICONS: dict[str, tuple[str, str]] = {
    "chevron-down.svg": ("chevron-down", "KcTextSecondary"),
    "chevron-up.svg": ("chevron-up", "KcTextSecondary"),
    "check.svg": ("check", "KcTextOnAccent"),
    # The checked radio. A thick border cannot be made round reliably - Qt
    # keeps drawing a square - so "on" is a drawn dot inside a round outline.
    "radio-dot.svg": ("radio-dot", "KcAccentPrimary"),
}

#: The prefix the template uses. Registered with ``QDir`` so ``kc:name.svg``
#: resolves to the current theme's folder.
SEARCH_PREFIX = "kc"


@lru_cache(maxsize=1)
def _root() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="kinecapture-theme-"))
    return directory


def _source(name: str) -> str:
    return (
        resources.files("kinecapture.studio.views.icons")
        .joinpath(f"{name}.svg")
        .read_text(encoding="utf-8")
    )


def build(tokens: ThemeTokens) -> Path:
    """Write this theme's stylesheet images and return the folder.

    Never raises: a missing arrow image is a cosmetic loss, and refusing to
    apply a theme because of one would be a much larger one.
    """
    directory = _root() / tokens.name
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for file_name, (icon, token) in STYLESHEET_ICONS.items():
            target = directory / file_name
            svg = _source(icon).replace("currentColor", tokens.colour(token))
            if not target.exists() or target.read_text(encoding="utf-8") != svg:
                target.write_text(svg, encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 - see docstring
        logger.warning("Tema görselleri yazılamadı: %s", exc)
    return directory


def install(tokens: ThemeTokens) -> Path:
    """Build the images and point ``kc:`` at them. Called on every theme change."""
    directory = build(tokens)
    QDir.setSearchPaths(SEARCH_PREFIX, [str(directory)])
    return directory


__all__ = ["SEARCH_PREFIX", "STYLESHEET_ICONS", "build", "install"]
