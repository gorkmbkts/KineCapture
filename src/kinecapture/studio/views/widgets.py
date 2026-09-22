"""Small shared widgets. Every visual value comes from a token.

Nothing here sets a colour or a pixel size literally: widgets carry Qt dynamic
properties (``kcRole``, ``kcStatus``, ``kcSurface``…) and the generated
stylesheet does the painting. That is what makes one ``tokens.json`` edit
re-theme the whole product, and what
``tests/test_studio_layers.py::test_views_write_no_literal_colours`` checks.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QLayout,
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
#:
#: ``OK`` carries no icon. A green tick beside the user, the project, the data
#: folder and the disk said only "still fine", four times, on every screen -
#: decoration that made the two states worth noticing harder to spot. The word
#: is kept for the accessible name; what disappears is the drawn mark.
_STATE_PRESENTATION = {
    ContextState.OK: ("live", "", "tamam"),
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
        if icon_key:
            self._icon.setPixmap(
                iconset.pixmap(
                    icon_key,
                    self._tokens.colour(colour_token),
                    size,
                    self.devicePixelRatioF(),
                )
            )
            self._icon.show()
        else:
            # A state with nothing to report draws nothing and gives its width
            # back, rather than reserving room for a mark that never appears.
            self._icon.clear()
            self._icon.hide()
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


class FlowLayout(QLayout):
    """Left to right, wrapping to the next line. Qt has no such layout.

    Written because the alternative for a row of class buttons is a fixed
    grid - which wastes the width when names are short and clips it when they
    are long - or a scroll area, which the acceptance brief rules out.
    """

    def __init__(self, parent: Optional[QWidget] = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self._spacing = int(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: ANN001, N802 - Qt naming
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: ANN201, N802 - Qt naming
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: ANN201, N802 - Qt naming
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 - Qt naming
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt naming
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt naming
        return self._lay(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt naming
        super().setGeometry(rect)
        self._lay(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt naming
        """Wide enough for the widest item, tall enough for one row.

        The height matters: a layout that claims less than it draws gets less
        than it needs, and Qt then puts the next widget on top of it. That is
        what happened - the name field ended up two pixels over the hint under
        it, and the Ekle button ten.
        """
        size = QSize(0, 0)
        for item in self._items:
            hint = item.sizeHint()
            size = QSize(
                max(size.width(), hint.width()), max(size.height(), hint.height())
            )
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _lay(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        right = rect.right() - margins.right()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            if x > rect.x() + margins.left() and x + hint.width() > right:
                x = rect.x() + margins.left()
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(x, y, hint.width(), hint.height()))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class MessageBar(QFrame):
    """The visible layer of a message, with "Ayrıntılar" holding the rest."""

    #: The key of an action the user pressed on this message.
    action_triggered = Signal(str)
    #: Emitted when the card's content changed shape. Whoever positions it -
    #: the toast layer - has to measure it again, or the part that grew is
    #: drawn outside the rectangle it was given.
    resized = Signal()

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._message: Optional[Message] = None
        self._details_open = False
        self._action_buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(tokens.metric("KcSpacingLg"),) * 4)
        outer.setSpacing(tokens.metric("KcSpacingMd"))

        # The headline gets a line to itself. It used to share one with
        # "Ayrıntılar" and "Kapat", whose padding left it about 120px inside a
        # 400px card - so "take_20260916T224651_d41e işlendi" arrived on screen
        # as "take_20260916T22465..." and a warning about a missing subject as
        # "Bu sürümde işlenen kişi...". A message nobody can read is not a
        # message. The two buttons moved down to the action row, where there is
        # room for them and where the other things to press already are.
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
        outer.addLayout(row)

        # Wrapped, not elided: the sentence that says what to do about the
        # headline is the half people actually need, and it was being cut at
        # the first line every time.
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(self._detail)

        # What to do about it, next to the message that raised it. A message
        # saying "use the Verileri Hesapla screen" and leaving the user to find
        # the take again is a message that made them do the work twice.
        #
        # A wrapping row, not a fixed one. Four buttons in a 400-pixel card is
        # about 380 pixels of text and padding, and a QHBoxLayout given less
        # than that does not wrap or elide: it squeezes the buttons and each
        # one clips its own label from both ends.
        self._actions = FlowLayout(spacing=tokens.metric("KcSpacingSm"))
        self._actions.addWidget(self._details_button)
        self._actions.addWidget(self._close_button)
        outer.addLayout(self._actions)

        self.setProperty("kcMessage", "info")
        self.hide()

    def _rebuild_actions(self, message: Message) -> None:
        for button in self._action_buttons:
            self._actions.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._action_buttons.clear()
        # Rebuilt in order: what to *do* first, then "Ayrıntılar", then
        # "Kapat". The row wraps, so the order is the reading order rather
        # than a fight over which edge each button keeps.
        self._actions.removeWidget(self._details_button)
        self._actions.removeWidget(self._close_button)
        for action in message.actions:
            button = QPushButton(action.label)
            button.setProperty("kcVariant", "primary" if action.primary else "quiet")
            button.setAccessibleName(action.label)
            button.clicked.connect(
                lambda _checked=False, key=action.key: self.action_triggered.emit(key)
            )
            _reserve_button_width(button)
            self._actions.addWidget(button)
            button.show()
            self._action_buttons.append(button)
        for button in (self._details_button, self._close_button):
            _reserve_button_width(button)
            self._actions.addWidget(button)
            button.setVisible(
                button is not self._details_button or message.has_details
            )

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
        self._rebuild_actions(message)
        self.setProperty("kcMessage", status)
        _restyle(self)
        self.show()
        self.resized.emit()

    def clear(self) -> None:
        self._message = None
        self._details_open = False
        window = getattr(self, "_details_window", None)
        if window is not None:
            window.close()
        self.hide()

    @property
    def current(self) -> Optional[Message]:
        return self._message

    @property
    def details_visible(self) -> bool:
        window = getattr(self, "_details_window", None)
        return bool(window is not None and window.isVisible())

    @property
    def details_text(self) -> str:
        window = getattr(self, "_details_window", None)
        return window.text if window is not None else ""

    def _toggle_details(self) -> None:
        """Open the technical detail in a window of its own.

        It used to unfold inside the card, and two things went wrong at once
        on 20 September: the technical line is a list of issue codes with no
        spaces, so a word-wrapping label could not break it and it ran off the
        right edge; and the card's height had already been measured, so the
        sentence above it was cut off at the bottom. A window has room for
        both, and the card keeps the height it was measured at.
        """
        message = self._message
        if message is None or not message.has_details:
            return
        window = getattr(self, "_details_window", None)
        if window is None:
            from .labelwindows import DetailWindow

            # Parented to the window, not to the card. A card is transient -
            # it fades out on a timer and deletes itself - and a dialog whose
            # parent disappears underneath it is a crash waiting for the
            # right timing.
            window = DetailWindow(
                "Bildirim ayrıntıları", self._tokens, self.window()
            )
            self._details_window = window
        rows = [(word_for_severity(message.severity), message.headline)]
        if message.detail:
            rows.append(("AÇIKLAMA", message.detail))
        if message.technical_text():
            rows.append(("TEKNİK", message.technical_text()))
        window.show_rows(rows)
        self._details_open = True
        window.show()
        window.raise_()
        window.activateWindow()


def word_for_severity(severity: Severity) -> str:
    """"Bilgi" / "Uyarı" / "Hata", the same word the card's headline carries."""
    return _SEVERITY_PRESENTATION[severity][2].upper()


def _reserve_button_width(button: QPushButton) -> None:
    """Room for the label, in the font the button actually has.

    ``QPushButton`` neither wraps nor elides: below the width its text needs
    it draws the text centred and clips both ends, which is how
    "Etiketlemeyi aç" reached a screenshot as "iketlemeyi a". The padding
    allowance is deliberately generous - a button two pixels wider than its
    text reads as a mistake, and one two pixels narrower loses a letter.
    """
    metrics = QFontMetrics(button.font())
    button.setMinimumWidth(metrics.horizontalAdvance(button.text()) + 28)


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
    "FlowLayout",
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
