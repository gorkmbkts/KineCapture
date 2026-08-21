"""One viewing area with three modes: RGB, skeleton, and the two combined.

The review screen used to show the camera image and the 3D skeleton side by
side permanently, which spent half the width on whichever one the user was not
looking at. This widget replaces both with a single area and an explicit mode
switch.

Mode choices, and why
---------------------
``RGB``
    The proxy video alone. What the camera saw, with nothing drawn on it.

``OVERLAY``
    The same frame with the skeleton projected onto it. This is the honest
    check that tracking actually followed the person, because image and joints
    are shown in the same coordinate frame.

``SKELETON``
    The metric 3D view, orbitable and root-centreable. Deliberately *not* a
    fixed camera projection: the overlay mode already answers "does this line
    up with the video", so the skeleton-only mode is the one place a researcher
    can rotate the capture and inspect the actual 3D geometry - depth errors
    are invisible from the camera's own viewpoint.

All three modes always show the same playback position. Switching mode changes
visualisation only; it never touches raw coordinates or exported data.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QWidget

from kinecapture.domain.models import BodyPose
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.skeleton_view import SkeletonView3D
from kinecapture.gui.widgets.video_view import VideoView
from kinecapture.visualization.skeleton_spec import SkeletonSpec


class SceneMode(str, Enum):
    """Which representation the single viewing area is showing."""

    RGB = "rgb"
    SKELETON = "skeleton"
    OVERLAY = "overlay"

    @property
    def label(self) -> str:
        return {
            SceneMode.RGB: "RGB",
            SceneMode.SKELETON: "İskelet",
            SceneMode.OVERLAY: "RGB + İskelet",
        }[self]

    @property
    def icon(self) -> str:
        return {
            SceneMode.RGB: "camera",
            SceneMode.SKELETON: "skeleton",
            SceneMode.OVERLAY: "eye",
        }[self]

    @property
    def needs_video(self) -> bool:
        """Whether this mode is useless without a proxy video."""
        return self is not SceneMode.SKELETON


class SceneView(QWidget):
    """A single frame view that can render RGB, skeleton, or both."""

    mode_changed = Signal(str)

    def __init__(
        self,
        theme: Theme,
        *,
        mode: SceneMode = SceneMode.OVERLAY,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._mode = mode
        self._has_video = True
        self._rgb: Optional[np.ndarray] = None
        self._bodies: tuple[BodyPose, ...] = ()
        self._spec: Optional[SkeletonSpec] = None
        self._active_id: Optional[int] = None
        self._no_video_reason = "Proxy video yok."

        self._video = VideoView(theme, placeholder_text=self._no_video_reason)
        self._skeleton = SkeletonView3D(theme)
        self._skeleton.set_placeholder_text("Bu karede gövde algılanmadı")

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._video)
        self._stack.addWidget(self._skeleton)

        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self.set_mode(mode)

    # ----------------------------------------------------------------- mode
    @property
    def mode(self) -> SceneMode:
        return self._mode

    def set_mode(self, mode: SceneMode | str) -> None:
        resolved = SceneMode(mode)
        self._mode = resolved
        if resolved is SceneMode.SKELETON:
            self._stack.setCurrentWidget(self._skeleton)
        else:
            self._stack.setCurrentWidget(self._video)
            self._video.set_overlay_enabled(resolved is SceneMode.OVERLAY)
            self._refresh_video_placeholder()
        self.mode_changed.emit(resolved.value)

    def available_modes(self) -> tuple[SceneMode, ...]:
        """Every mode. A mode needing video stays selectable but explains itself.

        Hiding a control because data is missing is worse than showing why it
        cannot help right now: the user would wonder where the button went.
        """
        return tuple(SceneMode)

    def is_mode_useful(self, mode: SceneMode) -> bool:
        return self._has_video or not mode.needs_video

    # ----------------------------------------------------------------- data
    def set_video_available(self, available: bool, reason: str = "") -> None:
        """Tell the view whether a proxy video exists for this take."""
        self._has_video = available
        if reason:
            self._no_video_reason = reason
        self._refresh_video_placeholder()

    def _refresh_video_placeholder(self) -> None:
        if self._has_video:
            return
        self._video.set_rgb(None)
        self._video.set_placeholder_text(
            f"{self._no_video_reason}\n"
            "İskelet görünümü çalışmaya devam eder — İskelet moduna geçin."
        )

    def set_frame(
        self,
        rgb: Optional[np.ndarray],
        bodies: Sequence[BodyPose],
        spec: Optional[SkeletonSpec],
        *,
        active_id: Optional[int] = None,
    ) -> None:
        """Show one playback position in whichever mode is active."""
        self._rgb = rgb
        self._bodies = tuple(bodies)
        self._spec = spec
        self._active_id = active_id

        if self._mode is SceneMode.SKELETON:
            self._skeleton.set_bodies(self._bodies, spec, active_id=active_id)
            return

        if rgb is not None:
            self._video.set_rgb(rgb)
        elif not self._has_video:
            self._refresh_video_placeholder()
        self._video.set_bodies(self._bodies, spec, active_id=active_id)

    def clear(self) -> None:
        self._rgb = None
        self._bodies = ()
        self._video.clear()
        self._skeleton.clear()

    def set_badge(self, text: str, colour: str = "") -> None:
        self._video.set_badge(text, colour)

    # ------------------------------------------------------ skeleton options
    @property
    def skeleton_view(self) -> SkeletonView3D:
        """The 3D view, for wiring its preset / centring controls."""
        return self._skeleton

    @property
    def video_view(self) -> VideoView:
        return self._video

    def set_root_centered(self, enabled: bool) -> None:
        self._skeleton.set_root_centered(enabled)

    def set_skeleton_preset(self, key: str) -> None:
        self._skeleton.set_preset(key)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._video.apply_theme(theme)
        self._skeleton.apply_theme(theme)


__all__ = ["SceneMode", "SceneView"]
