"""Small shared widgets. Every visual value comes from a token.

Nothing here sets a colour or a pixel size literally: widgets carry Qt dynamic
properties (``kcRole``, ``kcStatus``, ``kcSurface``…) and the generated
stylesheet does the painting. That is what makes one ``tokens.json`` edit
re-theme the whole product, and what
``tests/test_studio_layers.py::test_views_write_no_literal_colours`` checks.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.context import ContextItem, ContextState
from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.theme import ThemeTokens

from . import iconset

#: Context/message state -> (stylesheet status value, icon key, spoken word).
#: Colour is never the only carrier: every state also has an icon and a word,
#: so the interface stays readable for someone who cannot separate the hues.
_STATE_PRESENTATION = {
    ContextState.OK: ("live", "ok", "tamam"),
    ContextState.WARNING: ("warning", "warning", "uyarı"),
    ContextState.ERROR: ("error", "error", "hata"),
    ContextState.UNKNOWN: ("neutral", "info", "bilinmiyor"),
}

_SEVERITY_PRESENTATION = {
    Severity.INFO: ("info", "info", "Bilgi"),
    Severity.WARNING: ("warning", "warning", "Uyarı"),
    Severity.ERROR: ("error", "error", "Hata"),
}


def separator(orientation: Qt.Orientation = Qt.Orientation.Horizontal) -> QFrame:
    """A one-pixel rule. The only divider this interface uses."""
    frame = QFrame()
    frame.setProperty(
        "kcSeparator",
        "horizontal" if orientation is Qt.Orientation.Horizontal else "vertical",
    )
    return frame


def surface(kind: str = "raised") -> QFrame:
    frame = QFrame()
    frame.setProperty("kcSurface", kind)
    return frame


def label(text: str = "", *, role: str = "") -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("kcRole", role)
    return widget


def mono_label(text: str = "") -> QLabel:
    """For any number that changes while you watch it.

    Proportional digits make a frame counter or an FPS readout jitter
    horizontally; the layout must not move because a 1 became a 7.
    """
    return label(text, role="mono")


class ElidedLabel(QLabel):
    """Shortens instead of wrapping.

    A wrapped path or description silently steals vertical space from the
    viewport below it, which on a 700px screen is the difference between seeing
    the camera image and not.
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full = text
        if not self.toolTip() or self.toolTip() == self._full:
            self.setToolTip(text)
        super().setText(self._elided(text))

    def fullText(self) -> str:  # noqa: N802 - Qt naming
        return self._full

    def _elided(self, text: str) -> str:
        metrics = QFontMetrics(self.font())
        return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(24, self.width()))

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        super().setText(self._elided(self._full))


class StatusPill(QLabel):
    """Colour **and** icon **and** text, always all three."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setProperty("kcStatus", "neutral")

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens

    def show_state(self, state: ContextState, text: str) -> None:
        status, _icon, word = _STATE_PRESENTATION[state]
        self.setProperty("kcStatus", status)
        self.setText(text)
        self.setAccessibleDescription(word)
        _restyle(self)


class ContextField(QWidget):
    """One ``Etiket  değer`` pair in the context bar."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.metric("KcSpacingSm"))
        self._icon = QLabel()
        self._icon.setFixedSize(iconset.icon_size(tokens))
        self._key = label(role="contextKey")
        self._value = label(role="contextValue")
        layout.addWidget(self._icon)
        layout.addWidget(self._key)
        layout.addWidget(self._value)

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens

    def update_item(self, item: ContextItem) -> None:
        status, icon_key, word = _STATE_PRESENTATION[item.state]
        colour_token = {
            "live": "KcStatusLive",
            "warning": "KcStatusWarning",
            "error": "KcStatusRecording",
            "neutral": "KcTextMuted",
        }[status]
        size = self._tokens.metric("KcIconSize")
        self._icon.setPixmap(
            iconset.pixmap(icon_key, self._tokens.colour(colour_token), size, self.devicePixelRatioF())
        )
        self._key.setText(item.label)
        self._value.setProperty("kcRole", "mono" if item.numeric else "contextValue")
        self._value.setText(item.value)
        _restyle(self._value)
        tooltip = item.detail or item.value
        self.setToolTip(f"{item.label}: {tooltip}")
        self.setAccessibleName(f"{item.label} {item.value} ({word})")


class MessageBar(QFrame):
    """The visible layer of a message, with "Ayrıntılar" holding the rest."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._message: Optional[Message] = None
        self._details_open = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(tokens.metric("KcSpacingMd"),) * 4)
        outer.setSpacing(tokens.metric("KcSpacingSm"))

        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingMd"))
        self._icon = QLabel()
        self._icon.setFixedSize(iconset.icon_size(tokens))
        self._headline = ElidedLabel()
        self._details_button = QPushButton("Ayrıntılar")
        self._details_button.setProperty("kcVariant", "quiet")
        self._details_button.clicked.connect(self._toggle_details)
        self._close_button = QPushButton("Kapat")
        self._close_button.setProperty("kcVariant", "quiet")
        self._close_button.clicked.connect(self.clear)
        row.addWidget(self._icon)
        row.addWidget(self._headline, 1)
        row.addWidget(self._details_button)
        row.addWidget(self._close_button)
        outer.addLayout(row)

        self._detail = ElidedLabel()
        self._detail.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(self._detail)

        self._technical = QLabel()
        self._technical.setProperty("kcRole", "mono")
        self._technical.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._technical.setWordWrap(True)
        self._technical.hide()
        outer.addWidget(self._technical)

        self.setProperty("kcMessage", "info")
        self.hide()

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        if self._message is not None:
            self.show_message(self._message)

    def show_message(self, message: Message) -> None:
        self._message = message
        status, icon_key, word = _SEVERITY_PRESENTATION[message.severity]
        colour_token = {
            "info": "KcTextSecondary",
            "warning": "KcStatusWarning",
            "error": "KcStatusRecording",
        }[status]
        size = self._tokens.metric("KcIconSize")
        self._icon.setPixmap(
            iconset.pixmap(icon_key, self._tokens.colour(colour_token), size, self.devicePixelRatioF())
        )
        self._headline.setText(f"{word}: {message.headline}")
        self._detail.setText(message.detail)
        self._detail.setVisible(bool(message.detail))
        self._technical.setText(message.technical_text())
        self._details_button.setVisible(message.has_details)
        self._technical.setVisible(self._details_open and message.has_details)
        self.setProperty("kcMessage", status)
        _restyle(self)
        self.show()

    def clear(self) -> None:
        self._message = None
        self._details_open = False
        self._technical.hide()
        self.hide()

    @property
    def current(self) -> Optional[Message]:
        return self._message

    @property
    def details_visible(self) -> bool:
        return self._technical.isVisible()

    def _toggle_details(self) -> None:
        self._details_open = not self._details_open
        self._technical.setVisible(
            self._details_open and self._message is not None and self._message.has_details
        )


def _restyle(widget: QWidget) -> None:
    """Re-evaluate the stylesheet after a dynamic property changed.

    Qt does not do this on its own; without it a pill that turns from OK to
    warning keeps its old colour.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


__all__ = [
    "ContextField",
    "ElidedLabel",
    "MessageBar",
    "StatusPill",
    "label",
    "mono_label",
    "separator",
    "surface",
]
