"""NumPy to Qt image conversion.

The subtle part is buffer lifetime: ``QImage`` does not copy the data it is
constructed from, so a QImage built over a temporary NumPy array becomes a
dangling pointer the moment the array is garbage collected. Every function here
either calls ``.copy()`` on the QImage or keeps the source array alive on the
returned object, and says which.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from kinecapture.gui.theme import Theme


def rgb_to_qimage(rgb: np.ndarray) -> QImage:
    """Convert contiguous ``uint8 [H, W, 3]`` RGB to a self-owned QImage.

    The result owns its pixels (``.copy()``), so the caller may discard the
    source array immediately.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"RGB image must be [H, W, 3], got {rgb.shape}")
    if rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8)
    data = np.ascontiguousarray(rgb)
    height, width = data.shape[:2]
    image = QImage(
        data.data, width, height, width * 3, QImage.Format.Format_RGB888
    )
    return image.copy()


def rgb_to_pixmap(rgb: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(rgb_to_qimage(rgb))


def depth_to_qimage(
    depth: np.ndarray,
    theme: Theme,
    *,
    near: Optional[float] = None,
    far: Optional[float] = None,
) -> QImage:
    """Colourise a depth map for display.

    Pixels with no depth (NaN or infinite) are painted in the theme's muted
    colour rather than being clamped to "very near" or "very far", so an
    unmeasured region never looks like a measurement.

    ``near`` and ``far`` default to the 5th and 95th percentile of the valid
    range, which keeps a person visible instead of being washed out by a distant
    wall.
    """
    values = np.asarray(depth, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError(f"Depth image must be [H, W], got {values.shape}")
    valid = np.isfinite(values)
    height, width = values.shape
    output = np.zeros((height, width, 3), dtype=np.uint8)

    missing = np.array(_hex_to_rgb(theme.skeleton_dim), dtype=np.uint8)
    output[~valid] = missing

    if valid.any():
        finite = values[valid]
        low = float(near) if near is not None else float(np.percentile(finite, 5))
        high = float(far) if far is not None else float(np.percentile(finite, 95))
        if high - low < 1e-6:
            high = low + 1e-6
        normalised = np.clip((values - low) / (high - low), 0.0, 1.0)
        # Near is bright and warm, far is dark and cool: a perceptually
        # monotonic ramp so relative distance reads correctly at a glance.
        red = np.clip(1.35 - 1.5 * normalised, 0.0, 1.0)
        green = np.clip(1.15 - 1.05 * np.abs(normalised - 0.35) * 2.0, 0.0, 1.0)
        blue = np.clip(0.25 + 0.85 * normalised, 0.0, 1.0)
        ramp = np.stack([red, green, blue], axis=2)
        shade = (0.25 + 0.75 * (1.0 - normalised))[..., None]
        coloured = (ramp * shade * 255.0).astype(np.uint8)
        output[valid] = coloured[valid]

    return rgb_to_qimage(output)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def placeholder_image(
    width: int, height: int, theme: Theme, *, checker: int = 24
) -> QImage:
    """A neutral checkerboard shown where no frame has arrived yet."""
    base = np.array(_hex_to_rgb(theme.bg_sunken), dtype=np.uint8)
    alt = np.array(_hex_to_rgb(theme.grid), dtype=np.uint8)
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:, :] = base
    ys, xs = np.mgrid[0:height, 0:width]
    mask = ((xs // checker) + (ys // checker)) % 2 == 1
    image[mask] = alt
    return rgb_to_qimage(image)


__all__ = [
    "depth_to_qimage",
    "placeholder_image",
    "rgb_to_pixmap",
    "rgb_to_qimage",
]
