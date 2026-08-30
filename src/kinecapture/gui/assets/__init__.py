"""Image resources shipped inside the package.

Loaded through :mod:`importlib.resources` rather than by walking up from
``__file__`` to a repository folder. The difference matters the moment the
application is installed rather than run from a checkout: a development-relative
path finds nothing there, and a path relative to the working directory finds
nothing whenever the user starts the app from somewhere else.

The source image lives in ``files/`` at the repository root, where the user put
it. This is a byte-identical copy - not a re-encode - so the package has a
resource of its own without the original being altered or the two being able to
drift in quality.
"""

from __future__ import annotations

from importlib import resources
from typing import Optional

from kinecapture.core.logging import get_logger

logger = get_logger(__name__)

#: Yıldız Technical University logo, RGBA with a transparent background.
YTU_LOGO = "yildiz_technical_university_logo.png"


def asset_bytes(name: str) -> Optional[bytes]:
    """Read a packaged asset, or ``None`` if it is not there.

    Returning ``None`` rather than raising is deliberate: a missing decoration
    must never stop the application from starting. The caller logs it and
    carries on without the image.
    """
    try:
        return (resources.files(__package__) / name).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
        logger.warning("Paket kaynağı okunamadı: %s (%s)", name, exc)
        return None


__all__ = ["YTU_LOGO", "asset_bytes"]
