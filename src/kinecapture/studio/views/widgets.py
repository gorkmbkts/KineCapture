"""Small shared widgets. Every visual value comes from a token.

Nothing here sets a colour or a pixel size literally: widgets carry Qt dynamic
properties (``kcRole``, ``kcStatus``, ``kcSurface``…) and the generated
stylesheet does the painting. That is what makes one ``tokens.json`` edit
re-theme the whole product, and what
``tests/test_studio_layers.py::test_views_write_no_literal_colours`` checks.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
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


class SectionList(QScrollArea):
    """``label: value`` rows under headings, redrawn only when they change.

    Used by the shell's inspector, which is refreshed several times a second
    from whatever is selected. Rebuilding the widgets on every tick would
    churn a panel that usually says exactly what it said before, so the
    sections are compared first and the rebuild is skipped when they match.
    """

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._sections: tuple = ()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(tokens.metric("KcSpacingMd"))
        self.setWidget(self._body)
        self._empty = QLabel("")
        self._empty.setWordWrap(True)
        self._empty.setProperty("kcRole", "pageSubtitle")
        self._layout.addWidget(self._empty)
        self._layout.addStretch(1)
        self.show_sections(())

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        sections, self._sections = self._sections, ()
        self.show_sections(sections)

    @property
    def sections(self) -> tuple:
        return self._sections

    def show_sections(self, sections) -> None:  # noqa: ANN001 - Sequence[Section]
        wanted = tuple(sections)
        if wanted == self._sections:
            return
        self._sections = wanted
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._empty:
                widget.deleteLater()
        if not wanted:
            # A panel with nothing in it says *why* and what would fill it,
            # rather than sitting there as unexplained empty width.
            self._empty.setText(
                "Bu ekranda henüz bir şey seçilmedi.\n\n"
                "Bir satır seçin; ayrıntıları burada görünür."
            )
            self._layout.addWidget(self._empty)
            self._layout.addStretch(1)
            return
        self._empty.hide()
        for section in wanted:
            self._layout.addWidget(label(section.title.upper(), role="sectionTitle"))
            for row in section.rows:
                self._layout.addWidget(self._row_widget(row))
            if section.note:
                note = QLabel(section.note)
                note.setWordWrap(True)
                note.setProperty("kcRole", "pageSubtitle")
                self._layout.addWidget(note)
            self._layout.addWidget(separator())
        self._layout.addStretch(1)

    def _row_widget(self, row) -> QWidget:  # noqa: ANN001 - inspectors.Row
        holder = QWidget()
        column = QVBoxLayout(holder)
        margin = self._tokens.metric("KcSpacingXs")
        column.setContentsMargins(0, margin, 0, margin)
        column.setSpacing(self._tokens.metric("KcSpacingXs"))
        caption = label(row.label, role="contextKey")
        value = QLabel(row.value)
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        status = {"ready": "live", "warning": "warning", "error": "error"}.get(
            getattr(row, "level", "neutral")
        )
        if status:
            value.setProperty("kcStatus", status)
        else:
            value.setProperty("kcRole", "contextValue")
        if row.detail:
            holder.setToolTip(row.detail)
        column.addWidget(caption)
        column.addWidget(value)
        holder.setAccessibleName(f"{row.label}: {row.value}")
        return holder


class RecordingStrip(QWidget):
    """The live recording, visible on every screen, in a fixed-size region.

    Two rules it exists to keep:

    *It is always there.* The width is reserved whether or not a take is open,
    so a recording starting cannot shift the controls next to it out from under
    the pointer. Only the contents change.

    *It can always be stopped.* The audit found a take running with no way to
    end it except going back to Yakalama, and the indicator disappearing on the
    way. The button here is the same stop the Capture screen uses.
    """

    stop_requested = Signal()

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName("kcRecordingStrip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            tokens.metric("KcSpacingMd"), 0, tokens.metric("KcSpacingMd"), 0
        )
        layout.setSpacing(tokens.metric("KcSpacingMd"))

        self._dot = QLabel()
        self._dot.setFixedSize(iconset.icon_size(tokens))
        self._text = label(role="contextValue")
        self._elapsed = mono_label("")
        self.stop_button = QPushButton("Kaydı durdur")
        self.stop_button.setProperty("kcVariant", "danger")
        self.stop_button.setToolTip("Açık kaydı kapat (Ctrl+Shift+S)")
        self.stop_button.setAccessibleName("Kaydı durdur")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.hide()

        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addWidget(self._elapsed)
        layout.addWidget(self.stop_button)
        layout.addStretch(1)
        self.setFixedWidth(tokens.metric("KcRecordingStripWidth"))
        self.show_status(None)

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.setFixedWidth(tokens.metric("KcRecordingStripWidth"))
        self._dot.setFixedSize(iconset.icon_size(tokens))
        self.show_status(self._status)

    def show_status(self, status) -> None:  # noqa: ANN001 - RecordingStatus | None
        """Paint one reading. ``None`` means "nothing is recording"."""
        self._status = status
        open_take = bool(status is not None and status.is_open)
        phase = status.phase.value if status is not None else "idle"
        icon_key, colour_token = {
            "idle": ("info", "KcTextMuted"),
            "preparing": ("info", "KcStatusWarning"),
            "recording": ("live", "KcStatusRecording"),
            "closing": ("pause", "KcStatusWarning"),
        }.get(phase, ("info", "KcTextMuted"))
        size = self._tokens.metric("KcIconSize")
        self._dot.setPixmap(
            iconset.pixmap(
                icon_key,
                self._tokens.colour(colour_token),
                size,
                self.devicePixelRatioF(),
            )
        )
        if status is None or phase == "idle":
            self._text.setText("kayıt yok")
            self._text.setProperty("kcRole", "contextKey")
            self._elapsed.setText("")
            self.stop_button.hide()
            self.setToolTip("Şu anda açık bir kayıt yok.")
        else:
            headline = "KAYIT" if phase == "recording" else status.phase_text.upper()
            self._text.setText(f"{headline} · {status.target_text}")
            self._text.setProperty("kcRole", "contextValue")
            self._elapsed.setText(status.elapsed_text)
            # Still shown while closing, but disabled: the take is already on
            # its way down and a second press must not start a second close.
            self.stop_button.setVisible(open_take)
            self.stop_button.setEnabled(phase == "recording")
            self.setToolTip(
                f"{status.phase_text} · {status.frames} kare\n"
                f"{status.target_detail or status.target_text}"
            )
        _restyle(self._text)
        self.setAccessibleName(
            "Kayıt yok" if status is None or phase == "idle"
            else f"{status.phase_text} {status.target_text} {status.elapsed_text}"
        )

    @property
    def is_showing_recording(self) -> bool:
        return bool(self._status is not None and self._status.is_open)


class MessageBar(QFrame):
    """The visible layer of a message, with "Ayrıntılar" holding the rest."""

    #: The key of an action the user pressed on this message.
    action_triggered = Signal(str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._message: Optional[Message] = None
        self._details_open = False
        self._action_buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(tokens.metric("KcSpacingLg"),) * 4)
        outer.setSpacing(tokens.metric("KcSpacingMd"))

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

        # What to do about it, next to the message that raised it. A message
        # saying "use the Verileri Hesapla screen" and leaving the user to find
        # the take again is a message that made them do the work twice.
        self._actions = QHBoxLayout()
        self._actions.setSpacing(tokens.metric("KcSpacingSm"))
        self._actions.addStretch(1)
        outer.addLayout(self._actions)

        self.setProperty("kcMessage", "info")
        self.hide()

    def _rebuild_actions(self, message: Message) -> None:
        for button in self._action_buttons:
            self._actions.removeWidget(button)
            button.deleteLater()
        self._action_buttons.clear()
        for action in message.actions:
            button = QPushButton(action.label)
            button.setProperty("kcVariant", "primary" if action.primary else "quiet")
            button.setAccessibleName(action.label)
            button.clicked.connect(
                lambda _checked=False, key=action.key: self.action_triggered.emit(key)
            )
            self._actions.addWidget(button)
            self._action_buttons.append(button)

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
        self._rebuild_actions(message)
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
    "RecordingStrip",
    "SectionList",
    "StatusPill",
    "label",
    "mono_label",
    "separator",
    "surface",
]
