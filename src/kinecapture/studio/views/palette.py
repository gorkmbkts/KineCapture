"""The application palette, built from the same tokens as the stylesheet.

A stylesheet only paints what it names. Everything else - a viewport Qt fills
itself, a native widget's ground, a control drawn before the sheet is applied -
comes from ``QPalette``, and by default that palette is the *platform's*. On a
Windows 11 machine in dark mode the light theme therefore came up with dark
islands in it, which is exactly what the 15 September audit saw in Ayarlar.

Setting the palette from the tokens closes that gap: the stylesheet and the
fallback now say the same thing, and there is no third source of colour.

Fusion is chosen as the base style for the same reason. The native Windows
style draws several controls with the system's own colours no matter what the
palette says; Fusion honours the palette everywhere, which is the property
this file depends on.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from kinecapture.studio.theme import ThemeTokens

#: Palette role -> colour token. Written out rather than derived so the mapping
#: can be read, argued with and tested.
_ROLES: tuple[tuple[QPalette.ColorRole, str], ...] = (
    (QPalette.ColorRole.Window, "KcSurfaceBase"),
    (QPalette.ColorRole.WindowText, "KcTextPrimary"),
    (QPalette.ColorRole.Base, "KcSurfaceControl"),
    (QPalette.ColorRole.AlternateBase, "KcSurfaceBase"),
    (QPalette.ColorRole.Text, "KcTextPrimary"),
    (QPalette.ColorRole.PlaceholderText, "KcTextMuted"),
    (QPalette.ColorRole.Button, "KcSurfaceControl"),
    (QPalette.ColorRole.ButtonText, "KcTextPrimary"),
    (QPalette.ColorRole.BrightText, "KcStatusRecording"),
    (QPalette.ColorRole.Highlight, "KcAccentPrimary"),
    (QPalette.ColorRole.HighlightedText, "KcTextOnAccent"),
    (QPalette.ColorRole.ToolTipBase, "KcSurfaceOverlay"),
    (QPalette.ColorRole.ToolTipText, "KcTextPrimary"),
    (QPalette.ColorRole.Link, "KcAccentPrimary"),
    (QPalette.ColorRole.LinkVisited, "KcAccentPrimaryHover"),
    (QPalette.ColorRole.Light, "KcSurfaceControlHover"),
    (QPalette.ColorRole.Midlight, "KcSurfaceControl"),
    (QPalette.ColorRole.Mid, "KcBorderSubtle"),
    (QPalette.ColorRole.Dark, "KcBorderStrong"),
    (QPalette.ColorRole.Shadow, "KcSurfaceSunken"),
)

#: Roles that read differently when the control cannot be used.
_DISABLED: tuple[tuple[QPalette.ColorRole, str], ...] = (
    (QPalette.ColorRole.WindowText, "KcTextDisabled"),
    (QPalette.ColorRole.Text, "KcTextDisabled"),
    (QPalette.ColorRole.ButtonText, "KcTextDisabled"),
    (QPalette.ColorRole.Base, "KcSurfaceBase"),
    (QPalette.ColorRole.Button, "KcSurfaceBase"),
    (QPalette.ColorRole.Highlight, "KcSurfaceControlActive"),
    (QPalette.ColorRole.HighlightedText, "KcTextDisabled"),
)


def palette_for(tokens: ThemeTokens) -> QPalette:
    """One complete palette for ``tokens``. No colour is left to the platform."""
    palette = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        for role, token in _ROLES:
            palette.setColor(group, role, QColor(tokens.colour(token)))
    for role, token in _DISABLED:
        palette.setColor(
            QPalette.ColorGroup.Disabled, role, QColor(tokens.colour(token))
        )
    return palette


__all__ = ["palette_for"]
