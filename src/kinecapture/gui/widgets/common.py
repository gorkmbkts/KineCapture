"""Reusable presentation widgets built from the theme tokens.

Everything here is theme-aware and re-styles in place when the theme changes, so
switching between dark and light does not require rebuilding the window.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kinecapture.domain.enums import HealthLevel
from kinecapture.gui.icons import get_icon, icon_pixmap, icon_size
from kinecapture.gui.theme import Theme

#: Icon and word for each health level. Colour is never the only signal.
HEALTH_PRESENTATION: dict[HealthLevel, tuple[str, str]] = {
    HealthLevel.READY: ("check", "Hazır"),
    HealthLevel.WARNING: ("warning", "Uyarı"),
    HealthLevel.BLOCKED: ("error", "Engel"),
    HealthLevel.UNKNOWN: ("info", "Bilinmiyor"),
}


class ThemedWidget(QWidget):
    """Base for widgets that repaint themselves when the theme changes."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme

    @property
    def theme(self) -> Theme:
        return self._theme

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.on_theme_changed()
        self.update()

    def on_theme_changed(self) -> None:
        """Hook for subclasses that cache theme-derived resources."""


def make_label(
    text: str = "", *, role: str = "", parent: Optional[QWidget] = None
) -> QLabel:
    """A label carrying a ``role`` property that the stylesheet reads."""
    label = QLabel(text, parent)
    if role:
        label.setProperty("role", role)
    return label


def make_button(
    text: str = "",
    *,
    variant: str = "",
    icon: str = "",
    theme: Optional[Theme] = None,
    tooltip: str = "",
    parent: Optional[QWidget] = None,
) -> QPushButton:
    """A button with an optional themed icon and a style variant."""
    button = QPushButton(text, parent)
    if variant:
        button.setProperty("variant", variant)
    if icon and theme is not None:
        colour = theme.text_on_accent if variant in ("primary", "danger") else theme.text_primary
        button.setIcon(get_icon(icon, colour, 16, disabled_color=theme.text_muted))
        button.setIconSize(icon_size(16))
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def horizontal_rule(parent: Optional[QWidget] = None) -> QFrame:
    rule = QFrame(parent)
    rule.setProperty("role", "separator")
    rule.setFrameShape(QFrame.Shape.HLine)
    rule.setFixedHeight(1)
    return rule


def restyle(widget: QWidget) -> None:
    """Force Qt to re-evaluate the stylesheet after a property change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class Card(QFrame):
    """A titled surface. The standard container for everything on a page."""

    def __init__(
        self,
        title: str = "",
        *,
        subtitle: str = "",
        theme: Optional[Theme] = None,
        icon: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "card")
        self._theme = theme
        self._icon_name = icon

        outer = QVBoxLayout(self)
        margin = theme.space_sm + 2 if theme else 10
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(theme.space_sm if theme else 8)

        self._header = QHBoxLayout()
        self._header.setSpacing(theme.space_sm if theme else 8)
        self._icon_label = QLabel()
        self._icon_label.setVisible(False)
        self._header.addWidget(self._icon_label)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        self._title = make_label(title, role="section")
        self._subtitle = make_label(subtitle, role="subtitle")
        self._subtitle.setVisible(bool(subtitle))
        self._subtitle.setWordWrap(True)
        title_column.addWidget(self._title)
        title_column.addWidget(self._subtitle)
        self._header.addLayout(title_column, 1)

        self._header_extra = QHBoxLayout()
        self._header_extra.setSpacing(theme.space_sm if theme else 8)
        self._header.addLayout(self._header_extra)

        self._title.setVisible(bool(title))
        outer.addLayout(self._header)

        self.body = QVBoxLayout()
        self.body.setSpacing(theme.space_sm if theme else 8)
        outer.addLayout(self.body, 1)

        if icon and theme:
            self.apply_theme(theme)

    def set_title(self, text: str) -> None:
        self._title.setText(text)
        self._title.setVisible(bool(text))

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def add_header_widget(self, widget: QWidget) -> None:
        self._header_extra.addWidget(widget)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._icon_name:
            self._icon_label.setPixmap(
                icon_pixmap(self._icon_name, theme.text_secondary, 18)
            )
            self._icon_label.setVisible(True)
        restyle(self)


class MetricTile(QFrame):
    """A single number with a caption - the dashboard's basic unit."""

    def __init__(
        self,
        caption: str,
        value: str = "-",
        *,
        theme: Theme,
        icon: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "inset")
        self._theme = theme
        self._icon_name = icon

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_md, theme.space_sm, theme.space_md, theme.space_sm
        )
        layout.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(theme.space_xs)
        self._icon_label = QLabel()
        self._icon_label.setVisible(bool(icon))
        top.addWidget(self._icon_label)
        self._caption = make_label(caption, role="caption")
        top.addWidget(self._caption, 1)
        layout.addLayout(top)

        self._value = make_label(value, role="metric")
        layout.addWidget(self._value)

        self._detail = make_label("", role="muted")
        self._detail.setVisible(False)
        layout.addWidget(self._detail)

        self.apply_theme(theme)

    def set_value(self, value: str, *, colour: Optional[str] = None) -> None:
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {colour};" if colour else "")

    def set_detail(self, text: str) -> None:
        self._detail.setText(text)
        self._detail.setVisible(bool(text))

    def set_caption(self, text: str) -> None:
        self._caption.setText(text)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._icon_name:
            self._icon_label.setPixmap(
                icon_pixmap(self._icon_name, theme.text_muted, 14)
            )
        restyle(self)


class StatusChip(QFrame):
    """Icon + word + colour. Used for every status in the application."""

    def __init__(
        self,
        text: str = "",
        *,
        theme: Theme,
        icon: str = "info",
        colour: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_name = icon
        self._colour = colour or theme.text_secondary

        layout = QHBoxLayout(self)
        layout.setContentsMargins(theme.space_sm, 3, theme.space_sm, 3)
        layout.setSpacing(theme.space_xs + 2)
        self._icon_label = QLabel()
        layout.addWidget(self._icon_label)
        self._text = QLabel(text)
        layout.addWidget(self._text)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._refresh()

    def set_status(
        self, text: str, *, icon: Optional[str] = None, colour: Optional[str] = None
    ) -> None:
        self._text.setText(text)
        if icon:
            self._icon_name = icon
        if colour:
            self._colour = colour
        self._refresh()

    def set_health(self, level: HealthLevel, text: str = "") -> None:
        """Set from a health level, pairing colour with an icon and a word."""
        icon, word = HEALTH_PRESENTATION[level]
        self.set_status(
            text or word, icon=icon, colour=self._theme.health_color(level)
        )

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._refresh()

    def _refresh(self) -> None:
        theme = self._theme
        self._icon_label.setPixmap(icon_pixmap(self._icon_name, self._colour, 14))
        self._text.setStyleSheet(
            f"color: {self._colour}; font-weight: 600; font-size: {theme.font_size_sm}px;"
        )
        self.setStyleSheet(
            f"QFrame {{ background-color: {theme.bg_elevated};"
            f" border: 1px solid {theme.border};"
            f" border-radius: {theme.radius_sm + 4}px; }}"
        )


class FieldRow(QWidget):
    """A labelled form row with an inline validation message.

    The error text lives under the field rather than in a dialog, so a form can
    show every problem at once and the user fixes them in one pass.
    """

    def __init__(
        self,
        label: str,
        field: QWidget,
        *,
        theme: Theme,
        required: bool = False,
        help_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._field = field
        self._required = required

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        caption = f"{label} *" if required else label
        self._label = make_label(caption, role="caption")
        layout.addWidget(self._label)
        layout.addWidget(field)

        self._help = make_label(help_text, role="muted")
        self._help.setVisible(bool(help_text))
        self._help.setWordWrap(True)
        layout.addWidget(self._help)

        self._error = make_label("", role="error")
        self._error.setVisible(False)
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

    @property
    def field(self) -> QWidget:
        return self._field

    @property
    def is_required(self) -> bool:
        return self._required

    def set_error(self, message: str) -> None:
        """Show or clear the inline error and mark the field visually."""
        self._error.setText(message)
        self._error.setVisible(bool(message))
        self._field.setProperty("state", "invalid" if message else "")
        restyle(self._field)

    def clear_error(self) -> None:
        self.set_error("")

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        restyle(self)


class EmptyState(QWidget):
    """What a page shows when it has nothing yet, with the next action on it."""

    action_triggered = Signal()

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        theme: Theme,
        icon: str = "info",
        action_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon_name = icon

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(theme.space_sm)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title = make_label(title, role="section")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._description = make_label(description, role="muted")
        self._description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description.setWordWrap(True)
        self._description.setVisible(bool(description))
        layout.addWidget(self._description)

        self._button: Optional[QPushButton] = None
        if action_text:
            self._button = make_button(action_text, variant="primary", theme=theme)
            self._button.clicked.connect(self.action_triggered.emit)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(self._button)
            row.addStretch(1)
            layout.addLayout(row)

        self.apply_theme(theme)

    def set_text(self, title: str, description: str = "") -> None:
        self._title.setText(title)
        self._description.setText(description)
        self._description.setVisible(bool(description))

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._icon_label.setPixmap(icon_pixmap(self._icon_name, theme.text_muted, 44))
        restyle(self)


class KeyValueList(QWidget):
    """A compact two-column detail list, used by every info panel."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(theme.space_xs)
        self._rows: list[tuple[QLabel, QLabel]] = []

    def set_items(self, items: Iterable[tuple[str, str]]) -> None:
        """Replace the contents. Rows are reused to avoid layout churn."""
        entries = list(items)
        while len(self._rows) < len(entries):
            row = QHBoxLayout()
            row.setSpacing(self._theme.space_sm)
            key = make_label("", role="muted")
            key.setMinimumWidth(150)
            value = QLabel("")
            value.setWordWrap(True)
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            row.addWidget(key)
            row.addWidget(value, 1)
            self._layout.addLayout(row)
            self._rows.append((key, value))

        for index, (key_label, value_label) in enumerate(self._rows):
            if index < len(entries):
                key_text, value_text = entries[index]
                key_label.setText(key_text)
                value_label.setText(value_text)
                key_label.setVisible(True)
                value_label.setVisible(True)
            else:
                key_label.setVisible(False)
                value_label.setVisible(False)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        restyle(self)


class SectionHeader(QWidget):
    """A page-level heading with an optional description and action slot."""

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        theme: Theme,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        column = QVBoxLayout()
        column.setSpacing(2)
        self._title = make_label(title, role="title")
        column.addWidget(self._title)
        self._description = make_label(description, role="subtitle")
        self._description.setVisible(bool(description))
        self._description.setWordWrap(True)
        column.addWidget(self._description)
        layout.addLayout(column, 1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(theme.space_sm)
        layout.addLayout(self.actions)

    def set_description(self, text: str) -> None:
        self._description.setText(text)
        self._description.setVisible(bool(text))

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        restyle(self)


def monospace_font(size: int) -> QFont:
    """Tabular font for numbers that must not jitter as they update."""
    font = QFont("Consolas")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    return font


__all__ = [
    "HEALTH_PRESENTATION",
    "Card",
    "EmptyState",
    "FieldRow",
    "KeyValueList",
    "MetricTile",
    "SectionHeader",
    "StatusChip",
    "ThemedWidget",
    "horizontal_rule",
    "make_button",
    "make_label",
    "monospace_font",
    "restyle",
]
