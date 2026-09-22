"""The labelling panel's vertical icon strip, and the three views behind it.

Horizontal tabs with words on them cost a row of height across the whole panel
and, at this width, elide to nothing useful: "Etik…" and "Spor…". A column of
square icons down the panel's right edge costs no height at all and reads as
three places rather than three words.

Two rules the design review is explicit about.

**The strip says which view is open, and so does the content.** The icon takes
the view's colour - neutral for the summary, blue for a movement, coral for a
fault - but the panel also carries a short line naming what is being edited.
Colour alone is never the signal.

**Changing view does not move the panel.** All three views live in a stack of
one width, so switching between them does not make the panel jump or the
picture beside it resize.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens

from . import iconset
from .widgets import separator


class IconStripPanel(QWidget):
    """A stack of views, chosen by a column of square icons on the right."""

    #: The key of the view the strip now shows.
    view_changed = Signal(str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._buttons: dict[str, QToolButton] = {}
        self._icons: dict[str, str] = {}
        self._contexts: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._tooltips: dict[str, str] = {}
        self._attention: dict[str, str] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.stack = QStackedWidget(self)
        row.addWidget(self.stack, 1)
        row.addWidget(separator(Qt.Orientation.Vertical))

        strip = QWidget(self)
        strip.setFixedWidth(tokens.metric("KcIconStripWidth"))
        self._strip_layout = QVBoxLayout(strip)
        # Narrow on purpose. The strip is a rail for three square buttons,
        # not a column: the 21 September review found it reserving a corridor
        # of empty width beside them. The side margins are the smallest the
        # token set has, the top and bottom keep the first button off the
        # panel's edge, and the buttons themselves are unchanged - the rail
        # got thinner, the click targets did not.
        self._strip_layout.setContentsMargins(
            tokens.metric("KcSpacingXs"),
            tokens.metric("KcSpacingSm"),
            tokens.metric("KcSpacingXs"),
            tokens.metric("KcSpacingSm"),
        )
        self._strip_layout.setSpacing(tokens.metric("KcSpacingSm"))
        self._strip_layout.addStretch(1)
        row.addWidget(strip)
        self.strip = strip

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

    # ------------------------------------------------------------------ build
    def add_view(
        self,
        key: str,
        widget: QWidget,
        *,
        icon: str,
        name: str,
        tooltip: str = "",
        context: str = "summary",
    ) -> QToolButton:
        """One destination: a page in the stack and a button on the strip."""
        tokens = self._tokens
        button = QToolButton(self.strip)
        button.setProperty("kcRole", "stripButton")
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setAccessibleName(name)
        button.setToolTip(tooltip or name)
        button.setIconSize(iconset.icon_size(tokens))
        button.clicked.connect(lambda _checked=False, k=key: self.show_view(k))
        self._group.addButton(button)
        # Above the stretch, so the icons sit at the top of the strip in the
        # order they were added.
        self._strip_layout.insertWidget(
            self._strip_layout.count() - 1, button, 0, Qt.AlignmentFlag.AlignHCenter
        )
        self._buttons[key] = button
        self._icons[key] = icon
        self._contexts[key] = context
        self._names[key] = name
        self._tooltips[key] = tooltip or name
        self._attention[key] = ""
        self.stack.addWidget(widget)
        if len(self._buttons) == 1:
            button.setChecked(True)
        self._retint()
        return button

    # ----------------------------------------------------------------- state
    def show_view(self, key: str) -> bool:
        """Open one view. Pressing an icon that is already open re-opens it.

        LABEL-01 asks for exactly that: the label icon shows the summary even
        when the label view is already the one on screen, because the panel
        may be showing a movement or a fault editor *inside* it.
        """
        index = list(self._buttons).index(key) if key in self._buttons else -1
        if index < 0:
            return False
        self.stack.setCurrentIndex(index)
        self._buttons[key].setChecked(True)
        self._retint()
        self.view_changed.emit(key)
        return True

    @property
    def current_view(self) -> str:
        index = self.stack.currentIndex()
        keys = list(self._buttons)
        return keys[index] if 0 <= index < len(keys) else ""

    def set_context(self, key: str, context: str) -> None:
        """Which of summary / movement / fault a view is currently showing."""
        if self._contexts.get(key) == context:
            return
        self._contexts[key] = context
        self._retint()

    def context_of(self, key: str) -> str:
        return self._contexts.get(key, "summary")

    def set_attention(self, key: str, reason: str) -> None:
        """Mark a view as needing something, and say what.

        With word tabs this was an exclamation mark appended to the
        label. An icon has no label, so the reason goes where a reader
        can actually get at it - the tooltip and the accessible name -
        and the icon takes the warning colour alongside it. A bare
        colour change would be a mark nobody can look up.
        """
        if key not in self._buttons or self._attention.get(key) == reason:
            return
        self._attention[key] = reason
        name = self._names.get(key, key)
        base = self._tooltips.get(key, name)
        button = self._buttons[key]
        button.setToolTip(f"{base} · {reason}" if reason else base)
        button.setAccessibleName(f"{name} · {reason}" if reason else name)
        self._retint()

    def attention_of(self, key: str) -> str:
        return self._attention.get(key, "")

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.strip.setFixedWidth(tokens.metric("KcIconStripWidth"))
        self._retint()

    # -------------------------------------------------------------- painting
    #: Which colour token each context tints its icon with. Colour is an
    #: accompaniment to the panel's own wording, never a replacement for it.
    CONTEXT_TOKENS = {
        "summary": "KcContextSummary",
        "movement": "KcContextMovement",
        "fault": "KcContextFault",
    }

    def _retint(self) -> None:
        tokens = self._tokens
        current = self.current_view
        for key, button in self._buttons.items():
            context = self._contexts.get(key, "summary")
            token = self.CONTEXT_TOKENS.get(context, "KcContextSummary")
            if key != current and context == "summary":
                token = "KcTextSecondary"
            if self._attention.get(key):
                # Something is waiting here. That outranks which of the
                # three things the view happens to be showing.
                token = "KcStatusWarning"
            button.setIcon(
                iconset.icon(
                    self._icons[key],
                    tokens,
                    colour_token=token,
                    size=tokens.metric("KcIconSize"),
                    ratio=self.devicePixelRatioF(),
                )
            )


__all__ = ["IconStripPanel"]
