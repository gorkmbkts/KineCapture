"""Camera backends.

The ZED backend is *not* imported here: importing this package must never
require the ZED SDK. Use :func:`create_backend` to obtain one lazily.
"""

from __future__ import annotations

from typing import Any

from kinecapture.camera.base import (
    AvailabilityResult,
    BackendCapabilities,
    CameraBackend,
)
from kinecapture.core.config import AppConfig
from kinecapture.domain.enums import BackendKind


def create_backend(kind: BackendKind | str, **kwargs: Any) -> CameraBackend:
    """Create a backend by kind, importing the implementation lazily.

    ``kind`` may be a plain string: Qt widgets that carry a :class:`BackendKind`
    as item data hand it back as ``str``, so it is normalised here rather than
    at every call site.
    """
    try:
        resolved = BackendKind(kind)
    except ValueError:
        valid = ", ".join(b.value for b in BackendKind)
        raise ValueError(
            f"Bilinmeyen backend türü: {kind}. Geçerli değerler: {valid}"
        ) from None

    if resolved is BackendKind.MOCK:
        from kinecapture.camera.mock import MockCameraBackend

        return MockCameraBackend(**kwargs)

    from kinecapture.camera.zed import ZedCameraBackend

    return ZedCameraBackend(**kwargs)


def create_backend_from_config(
    config: AppConfig, kind: BackendKind | str | None = None
) -> CameraBackend:
    """Build the configured backend with the settings that belong to it."""
    resolved = BackendKind(kind) if kind is not None else config.backend
    if resolved is BackendKind.MOCK:
        return create_backend(
            resolved,
            width=config.mock.width,
            height=config.mock.height,
            fps=config.mock.fps,
            seed=config.mock.seed,
            num_bodies=config.mock.num_bodies,
            enable_depth=config.mock.enable_depth,
            tracking_loss_every=config.mock.tracking_loss_every,
            low_confidence_every=config.mock.low_confidence_every,
            real_time=True,
            profile=config.capture,
        )
    return create_backend(resolved, profile=config.capture)


__all__ = [
    "AvailabilityResult",
    "BackendCapabilities",
    "CameraBackend",
    "create_backend",
    "create_backend_from_config",
]
