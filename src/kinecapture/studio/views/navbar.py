"""The bottom navigation strip: the workflow, left to right.

Icons sit above their labels and every destination keeps its position whether
or not it is ready yet, so the bar reads as a sequence rather than a menu.
Keyboard: Ctrl+1…Ctrl+8 jump directly, Ctrl+PgUp/PgDn step.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QToolButton, QWidget

from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination, destination as destination_for

from . import iconset


class NavBar(QFrame):
    """Emits ``navigate(key)``; it never changes pages itself.

    The viewmodel owns the current page. If the bar switched pages directly,
    two sources of truth would exist the moment anything else (a shortcut, a
    deep link from another screen) also wanted to navigate.
    """

    navigate = Signal(str)

    def __init__(
        self,
        destinations: tuple[Destination, ...],
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("kcNavBar")
        self._tokens = tokens
        self._buttons: dict[str, QToolButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            tokens.metric("KcSpacingMd"), 0, tokens.metric("KcSpacingMd"), 0
        )
        layout.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for index, item in enumerate(destinations, start=1):
            button = QToolButton(self)
            button.setProperty("kcRole", "navItem")
            button.setText(item.title)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(iconset.icon_size(tokens))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(f"{item.title} — {item.subtitle}  (Ctrl+{index})")
            button.setAccessibleName(item.title)
            button.setAccessibleDescription(item.subtitle)
            button.clicked.connect(lambda _=False, key=item.key: self.navigate.emit(key))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[item.key] = button

        layout.addStretch(1)
        self._layout = layout
        self._compact = False
        #: key -> why it cannot be entered. Empty means everything is open.
        self._gated: dict = {}
        self.setFixedHeight(tokens.metric("KcNavBarHeight"))
        self.apply_tokens(tokens)

    def apply_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.setFixedHeight(tokens.metric("KcNavBarHeight"))
        self._repaint_icons()
        self._apply_density(self.width())

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._apply_density(event.size().width())

    def _apply_density(self, available: int) -> None:
        """Drop the labels rather than let the workflow scroll off the edge.

        At 1120px with 150% scaling the eight labels stop fitting. Hiding the
        overflow behind a scroll would hide steps of the workflow; falling back
        to icons keeps all eight visible and reachable, with the name in the
        tooltip and the accessible name.
        """
        needed = sum(
            button.sizeHint().width() for button in self._buttons.values()
        ) + 2 * self._tokens.metric("KcSpacingMd")
        compact = available > 0 and needed > available
        if compact == self._compact:
            return
        self._compact = compact
        style = (
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if compact
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        for button in self._buttons.values():
            button.setToolButtonStyle(style)

    @property
    def is_compact(self) -> bool:
        return self._compact

    def set_gated(self, reasons: dict) -> None:
        """Show which steps are not enterable yet, and why.

        The destinations stay visible in their real places - hiding them would
        make the workflow look shorter than it is and leave somebody wondering
        where the step they were told about went. They are dimmed, and their
        tooltip says what is missing rather than repeating the subtitle.
        """
        self._gated = dict(reasons)
        for key, button in self._buttons.items():
            reason = self._gated.get(key, "")
            button.setEnabled(not reason)
            item = destination_for(key)
            index = self.keys.index(key) + 1 if key in self.keys else 0
            button.setToolTip(
                f"{item.title} — {reason}"
                if reason
                else f"{item.title} — {item.subtitle}  (Ctrl+{index})"
            )
            button.setAccessibleDescription(reason or item.subtitle)

    @property
    def gated(self) -> dict:
        return dict(self._gated)

    def set_active(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._repaint_icons()

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._buttons)

    def button_for(self, key: str) -> Optional[QToolButton]:
        return self._buttons.get(key)

    def _repaint_icons(self) -> None:
        """Selected item gets the accent tint; the rest stay secondary."""
        ratio = self.devicePixelRatioF()
        size = self._tokens.metric("KcIconSize")
        from kinecapture.studio.viewmodels.navigation import destination

        for key, button in self._buttons.items():
            item = destination(key)
            token = "KcAccentPrimary" if button.isChecked() else "KcTextSecondary"
            icon_key = item.icon if item is not None else "info"
            button.setIcon(
                iconset.icon(
                    icon_key,
                    self._tokens,
                    colour_token=token,
                    size=size,
                    ratio=ratio,
                )
            )


__all__ = ["NavBar"]
