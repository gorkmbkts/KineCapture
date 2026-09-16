"""The university crest, presented correctly on either theme.

The mark itself is Yıldız Teknik Üniversitesi's, and it is used unaltered: the
navy and the gold are the institution's colours and are not recoloured to suit
a palette. What changes between themes is what the crest is placed *on*.

* On the **light** theme the crest sits directly on the surface. Navy on a
  near-white ground is exactly what the mark was drawn for.
* On the **dark** theme the navy lettering would all but disappear against a
  charcoal ground, so the crest is drawn on a light, softly rounded plate.
  That keeps every colour of the original and still leaves "YILDIZ TEKNİK
  ÜNİVERSİTESİ 1911" readable, which recolouring the ink would not.

Nothing here can stop the application: a crest that will not load is a missing
decoration, logged once, and every caller carries on without it.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib import resources
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from kinecapture.studio.theme import ThemeTokens

logger = logging.getLogger(__name__)

#: The crest, as shipped with the package. Byte-identical to the file in
#: ``files/`` at the repository root.
CREST = "yildiz_technical_university_logo.png"

#: Where the crest lives. Shared with the legacy interface rather than copied,
#: so there is one file and the two cannot drift.
CREST_PACKAGE = "kinecapture.gui.assets"

#: How much of the plate is crest, on the dark theme. The rest is the margin
#: that keeps the gold ring from touching the plate's edge.
_PLATE_INSET = 0.11


@lru_cache(maxsize=1)
def crest_bytes() -> Optional[bytes]:
    try:
        return (resources.files(CREST_PACKAGE) / CREST).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        logger.warning("Üniversite logosu okunamadı: %s (%s)", CREST, exc)
        return None


@lru_cache(maxsize=1)
def crest_image() -> Optional[QImage]:
    data = crest_bytes()
    if not data:
        return None
    image = QImage()
    if not image.loadFromData(data, "PNG") or image.isNull():
        logger.warning("Üniversite logosu çözümlenemedi: %s", CREST)
        return None
    return image


def _fitted(box: QRectF, width: int, height: int) -> QRectF:
    """``box`` shrunk to the image's aspect ratio and centred inside it."""
    if width <= 0 or height <= 0:
        return box
    scale = min(box.width() / width, box.height() / height)
    drawn_w, drawn_h = width * scale, height * scale
    return QRectF(
        box.left() + (box.width() - drawn_w) / 2.0,
        box.top() + (box.height() - drawn_h) / 2.0,
        drawn_w,
        drawn_h,
    )


@lru_cache(maxsize=16)
def _rendered(theme: str, plate: str, size: int, ratio: float) -> Optional[QPixmap]:
    image = crest_image()
    if image is None:
        return None
    scaled = max(1, int(round(size * ratio)))
    canvas = QImage(scaled, scaled, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    box = QRectF(0, 0, scaled, scaled)
    if plate:
        # A light disc behind the crest. The crest keeps its own colours; it
        # is the ground under it that changes.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(plate))
        painter.drawEllipse(box)
        inset = scaled * _PLATE_INSET
        box = box.adjusted(inset, inset, -inset, -inset)
    # The source is 398x405, not square. Fitting it to a square box would
    # stretch a circular mark into an ellipse, so the aspect is preserved and
    # the result is centred in whatever room is left.
    painter.drawImage(_fitted(box, image.width(), image.height()), image)
    painter.end()
    pixmap = QPixmap.fromImage(canvas)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def crest_pixmap(
    tokens: ThemeTokens, *, size: int = 96, ratio: float = 1.0, plate: Optional[bool] = None
) -> Optional[QPixmap]:
    """The crest at ``size`` logical pixels, ready for this theme.

    ``plate`` forces the light disc on or off; by default it follows the theme,
    which is the behaviour every caller wants.
    """
    wants_plate = tokens.is_dark if plate is None else bool(plate)
    colour = tokens.colour("KcSurfaceControl") if wants_plate else ""
    return _rendered(tokens.name, colour, int(size), float(ratio))


def crest_available() -> bool:
    return crest_image() is not None


#: What the crest is, in words, for a screen reader and for a tooltip. The mark
#: identifies the institution the work belongs to; it is not a control.
CREST_NAME = "Yıldız Teknik Üniversitesi"


__all__ = [
    "CREST",
    "CREST_NAME",
    "CREST_PACKAGE",
    "crest_available",
    "crest_bytes",
    "crest_image",
    "crest_pixmap",
]
