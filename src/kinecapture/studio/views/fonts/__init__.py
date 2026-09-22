"""The bundled brand face, registered with Qt once per process.

Space Grotesk is the product's display face and is used for the product name
and nothing else. It is shipped in the package rather than fetched or assumed
installed, for two reasons: the sign-in screen is the first thing on screen and
must never wait on a network, and a machine in a lab may have no fonts beyond
what Windows ships.

Loading is best effort in the strictest sense. A font that will not register is
a decoration that did not arrive: :func:`brand_family` then answers with the
next family in the token's fallback chain, and the sign-in screen renders in it
without noticing. Nothing here may raise into a caller.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import resources
from typing import Optional

logger = logging.getLogger(__name__)

#: The variable font, exactly as published. One file covers every weight.
BRAND_FONT_FILE = "SpaceGrotesk[wght].ttf"

#: What the file claims to be, so a caller can check the family it asked for is
#: the family it got rather than trusting the file name.
BRAND_FAMILY = "Space Grotesk"

#: Where the licence lives. Shipped beside the font, never separated from it.
LICENCE_FILE = "OFL.txt"

_PACKAGE = "kinecapture.studio.views.fonts"


def font_bytes() -> Optional[bytes]:
    """The font file's contents, or ``None`` when it is not in the package."""
    try:
        return (resources.files(_PACKAGE) / BRAND_FONT_FILE).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        logger.warning("Marka fontu okunamadı: %s (%s)", BRAND_FONT_FILE, exc)
        return None


def licence_text() -> str:
    """The SIL Open Font Licence this font is used under."""
    try:
        return (resources.files(_PACKAGE) / LICENCE_FILE).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):  # pragma: no cover
        return ""


@lru_cache(maxsize=1)
def _register() -> tuple[str, ...]:
    """Hand the font to Qt. Cached: registering twice wastes work, not memory."""
    data = font_bytes()
    if not data:
        return ()
    try:
        from PySide6.QtGui import QFontDatabase
    except ImportError:  # pragma: no cover - Qt is present wherever this runs
        return ()
    identifier = QFontDatabase.addApplicationFontFromData(data)
    if identifier < 0:
        # -1 means Qt read the bytes and refused them. That is a broken file,
        # not a missing one, so it is worth a louder line in the log.
        logger.warning("Marka fontu Qt tarafından kabul edilmedi: %s", BRAND_FONT_FILE)
        return ()
    families = tuple(QFontDatabase.applicationFontFamilies(identifier))
    if not families:  # pragma: no cover - a registered font always has a family
        return ()
    logger.debug("Marka fontu yüklendi: %s", ", ".join(families))
    return families


def load_brand_font() -> tuple[str, ...]:
    """Register the brand face and return the families Qt now knows about."""
    return _register()


def brand_family() -> str:
    """The family to set on a display label, or ``""`` to use the fallback.

    Returning the empty string rather than a guess is the point: the caller
    leaves the family unset and the stylesheet's own chain takes over, which is
    what makes a missing font invisible instead of wrong.
    """
    families = load_brand_font()
    if not families:
        return ""
    for family in families:
        if family.strip().lower() == BRAND_FAMILY.lower():
            return family
    return families[0]


def brand_font_available() -> bool:
    return bool(load_brand_font())


#: The characters the interface cannot do without. Turkish needs six letters
#: beyond ASCII in each case, and a display face that lacks them would render
#: the product name with tofu in it on a Turkish machine.
TURKISH_GLYPHS = "ğüşıöçĞÜŞİÖÇ"


def missing_glyphs(text: str = TURKISH_GLYPHS) -> str:
    """Which characters of ``text`` the bundled face cannot draw.

    Asked of Qt rather than of the font tables, because what matters is what
    the widget will actually paint. An unavailable font reports nothing
    missing: there is no claim to check.

    The test is the glyph index, not ``QRawFont.supportsCharacter``. Measured
    on PySide6 6.10.1 with this file: ``supportsCharacter`` answered ``False``
    for all twelve Turkish letters while ``glyphIndexesForString`` returned
    real, non-zero glyphs for the same characters and the font's own cmap
    contained every one of them. Index ``0`` is ``.notdef`` - the empty box a
    reader would actually see - and is the only answer worth trusting.
    """
    family = brand_family()
    if not family:
        return ""
    from PySide6.QtGui import QFont, QRawFont

    raw = QRawFont.fromFont(QFont(family))
    if not raw.isValid():  # pragma: no cover - a registered family is valid
        return ""
    indexes = raw.glyphIndexesForString(text)
    if len(indexes) != len(text):  # pragma: no cover - ligatures do not apply here
        return ""
    return "".join(
        character for character, glyph in zip(text, indexes) if int(glyph) == 0
    )


__all__ = [
    "BRAND_FAMILY",
    "BRAND_FONT_FILE",
    "LICENCE_FILE",
    "TURKISH_GLYPHS",
    "brand_family",
    "brand_font_available",
    "font_bytes",
    "licence_text",
    "load_brand_font",
    "missing_glyphs",
]
