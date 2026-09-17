"""Settings, rendered from the declarations in the settings service.

The page knows how to draw a choice, a switch, a number and a path. It does not
know what a depth mode is - that sentence lives with the setting, so the two
cannot drift apart.

Save sits outside the scrollable area and says how many changes are waiting, so
leaving with unsaved edits is visible rather than silent.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.settings import APPLIES_TEXT, SettingField
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.settings import SettingsViewModel

from ..widgets import ElidedLabel, label, separator
from .base import StudioPage

#: How wide a control is allowed to get. A settings page is a column of
#: sentences with a control at the end of each, not a row of full-width bars.
CONTROL_WIDTH = 320

#: How wide the readable column is. Beyond this a help sentence stops being a
#: sentence and becomes a line to track across a monitor.
CONTENT_WIDTH = 900


class _FieldRow(QWidget):
    """One setting: name, control, the sentence, the cost, and any problem."""

    def __init__(
        self,
        field: SettingField,
        tokens: ThemeTokens,
        on_change,  # noqa: ANN001
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.field = field
        self._on_change = on_change
        self._silent = False

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, tokens.metric("KcSpacingLg"))
        outer.setSpacing(tokens.metric("KcSpacingXl"))

        # Name and explanation on the left, the control on the right. The
        # control is capped rather than stretched: a spin box the width of a
        # 1920px window is not easier to use, it is just the widest thing on
        # the screen, which is what the audit called a "control gallery".
        left = QVBoxLayout()
        left.setSpacing(tokens.metric("KcSpacingXs"))
        self.caption = label(field.label)
        self.caption.setProperty("kcRole", "fieldLabel")
        left.addWidget(self.caption)
        self.help = QLabel(field.help_text)
        self.help.setWordWrap(True)
        self.help.setProperty("kcRole", "pageSubtitle")
        left.addWidget(self.help)
        if field.cost_note:
            cost = QLabel(field.cost_note)
            cost.setWordWrap(True)
            cost.setProperty("kcRole", "fieldCost")
            left.addWidget(cost)
        self.problem = label("", role="fieldError")
        self.problem.setWordWrap(True)
        self.problem.hide()
        left.addWidget(self.problem)
        outer.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(tokens.metric("KcSpacingXs"))
        control_row = QHBoxLayout()
        control_row.setSpacing(tokens.metric("KcSpacingSm"))
        self.control = self._build_control(field)
        self.control.setMaximumWidth(CONTROL_WIDTH)
        self.control.setMinimumWidth(min(CONTROL_WIDTH, 160))
        control_row.addStretch(1)
        control_row.addWidget(self.control)
        if field.kind == "path":
            browse = QPushButton("Seç…")
            browse.setProperty("kcVariant", "quiet")
            browse.clicked.connect(self._browse)
            control_row.addWidget(browse)
        right.addLayout(control_row)
        # When a saved change starts to matter. "Kaydedildi" and "etkin" are
        # not the same statement and the screen must not merge them.
        self.applies = label(APPLIES_TEXT[field.applies_when], role="fieldApplies")
        self.applies.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.applies.setToolTip(
            "Bu ayar kaydedildikten sonra ne zaman etkili olur"
        )
        right.addWidget(self.applies)
        outer.addLayout(right)

        self.setAccessibleName(field.label)
        self.setAccessibleDescription(
            f"{field.help_text} Etkili olma zamanı: {APPLIES_TEXT[field.applies_when]}."
        )
        if field.read_only:
            self.control.setEnabled(False)

    @property
    def search_text(self) -> str:
        """Everything about this setting, lower-cased, for one-call searching."""
        return " ".join(
            (self.field.label, self.field.help_text, self.field.key, self.field.cost_note)
        ).casefold()

    def _build_control(self, field: SettingField) -> QWidget:
        if field.kind == "choice":
            box = QComboBox()
            for choice in field.choices:
                text = f"{choice.label}   ·   {choice.cost}" if choice.cost else choice.label
                box.addItem(text, choice.value)
            box.currentIndexChanged.connect(
                lambda _i: self._emit(box.currentData())
            )
            return box
        if field.kind == "bool":
            check = QCheckBox()
            check.toggled.connect(lambda value: self._emit(bool(value)))
            return check
        if field.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(field.minimum or 0), int(field.maximum or 1_000_000))
            spin.setSuffix(field.suffix)
            spin.valueChanged.connect(lambda value: self._emit(int(value)))
            return spin
        if field.kind == "float":
            spin = QDoubleSpinBox()
            spin.setDecimals(1)
            spin.setRange(float(field.minimum or 0.0), float(field.maximum or 1e6))
            spin.setSuffix(field.suffix)
            spin.valueChanged.connect(lambda value: self._emit(float(value)))
            return spin
        edit = QLineEdit()
        edit.textChanged.connect(lambda text: self._emit(text))
        return edit

    def _emit(self, value: Any) -> None:
        if not self._silent:
            self._on_change(self.field.key, value)

    def set_value(self, value: Any) -> None:
        """Show ``value`` without reporting it back as a user edit."""
        self._silent = True
        try:
            control = self.control
            if isinstance(control, QComboBox):
                index = control.findData(value)
                control.setCurrentIndex(max(0, index))
            elif isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QDoubleSpinBox):
                control.setValue(float(value))
            elif isinstance(control, QLineEdit):
                control.setText("" if value is None else str(value))
        finally:
            self._silent = False

    def set_problem(self, text: str) -> None:
        self.problem.setText(text)
        self.problem.setVisible(bool(text))

    def _browse(self) -> None:
        current = self.control.text() if isinstance(self.control, QLineEdit) else ""
        chosen = QFileDialog.getExistingDirectory(self, self.field.label, current)
        if chosen and isinstance(self.control, QLineEdit):
            self.control.setText(chosen)


class SettingsPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[SettingsViewModel] = None
        self.rows: dict[str, _FieldRow] = {}
        self._sections: dict[str, QWidget] = {}
        self._section_buttons: dict[str, QToolButton] = {}

        search_row = QHBoxLayout()
        search_row.setSpacing(tokens.metric("KcSpacingMd"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Ayar ara")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(360)
        self.search.setToolTip("Ad, açıklama veya anahtar içinde arar")
        self.search.textChanged.connect(self._apply_search)
        search_row.addWidget(self.search)
        search_row.addStretch(1)
        self.body_layout.addLayout(search_row)

        columns = QHBoxLayout()
        columns.setSpacing(tokens.metric("KcSpacingXl"))

        # A rail of sections, so a long form is navigable instead of scrolled
        # through from the top every time.
        self._rail = QWidget(self)
        self._rail_layout = QVBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_layout.setSpacing(tokens.metric("KcSpacingXs"))
        self._rail.setFixedWidth(176)
        columns.addWidget(self._rail)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content = QWidget()
        self._content.setMaximumWidth(CONTENT_WIDTH)
        self._content_layout = QVBoxLayout(self._content)
        # Every side, not just the right. The form used to start on the exact
        # pixel where the scroll viewport did, so the section heading and the
        # first field label sat against the edge of their container.
        self._content_layout.setContentsMargins(
            tokens.metric("KcSpacingXl"),
            tokens.metric("KcSpacingLg"),
            tokens.metric("KcSpacingXl"),
            tokens.metric("KcSpacingXl"),
        )
        self._content_layout.setSpacing(tokens.metric("KcSpacingLg"))
        self.scroll.setWidget(self._content)
        columns.addWidget(self.scroll, 1)
        columns.addStretch(0)
        self.body_layout.addLayout(columns, 1)

        self.body_layout.addWidget(separator())
        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingMd"))
        self.dirty_label = ElidedLabel("")
        self.dirty_label.setProperty("kcRole", "sectionTitle")
        self.discard_button = QPushButton("Değişiklikleri geri al")
        self.discard_button.setProperty("kcVariant", "quiet")
        self.save_button = QPushButton("Kaydet")
        self.save_button.setProperty("kcVariant", "primary")
        bar.addWidget(self.dirty_label, 1)
        bar.addWidget(self.discard_button)
        bar.addWidget(self.save_button)
        self.body_layout.addLayout(bar)

        self.save_button.clicked.connect(self._save)
        self.discard_button.clicked.connect(self._discard)

    def bottom_reserve(self) -> int:
        """The save bar, plus the gap above it. Measured, not guessed."""
        return self.save_button.sizeHint().height() + self._tokens.metric(
            "KcSpacingXxl"
        ) * 2

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: SettingsViewModel) -> None:
        self.viewmodel = viewmodel
        self._build_rows()
        self.bind(viewmodel.values, lambda _v: self._refresh_values())
        self.bind(viewmodel.pending, lambda _p: self._refresh_values())
        self.bind(viewmodel.problems, self._show_problems)
        # Bound to `pending` rather than `dirty`: the boolean stops changing
        # after the first edit, so a count bound to it would freeze at one.
        self.bind(viewmodel.pending, self._show_dirty)
        self.bind_event(viewmodel.message, self.show_message)

    def _build_rows(self) -> None:
        assert self.viewmodel is not None
        tokens = self._tokens
        for key, title, subtitle, fields in self.viewmodel.groups():
            section = QWidget(self._content)
            column = QVBoxLayout(section)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(tokens.metric("KcSpacingSm"))
            column.addWidget(label(title.upper(), role="sectionTitle"))
            caption = QLabel(subtitle)
            caption.setWordWrap(True)
            caption.setProperty("kcRole", "pageSubtitle")
            column.addWidget(caption)
            column.addWidget(separator())
            for field in fields:
                row = _FieldRow(field, tokens, self._edited, section)
                self.rows[field.key] = row
                column.addWidget(row)
            self._sections[key] = section
            self._content_layout.addWidget(section)

            button = QToolButton(self._rail)
            button.setText(title)
            button.setCheckable(False)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setToolTip(subtitle)
            button.clicked.connect(lambda _c=False, k=key: self.scroll_to(k))
            self._section_buttons[key] = button
            self._rail_layout.addWidget(button)
        self._rail_layout.addStretch(1)
        self._content_layout.addStretch(1)

    def scroll_to(self, group: str) -> bool:
        """Put a section at the top of the view. Returns whether it was found."""
        section = self._sections.get(group)
        if section is None:
            return False
        self.scroll.ensureWidgetVisible(section, 0, self.scroll.height())
        self.scroll.verticalScrollBar().setValue(
            section.mapTo(self._content, section.rect().topLeft()).y()
        )
        return True

    def _apply_search(self, text: str) -> None:
        """Hide what does not match, and the sections that end up empty.

        Filtering in place rather than jumping to a result: the page is short
        enough that showing only the matching settings *is* the answer.
        """
        needle = text.strip().casefold()
        for key, section in self._sections.items():
            shown = 0
            for row in self.rows.values():
                if row.parent() is not section:
                    continue
                matches = not needle or needle in row.search_text
                row.setVisible(matches)
                shown += int(matches)
            section.setVisible(bool(shown))
            button = self._section_buttons.get(key)
            if button is not None:
                button.setEnabled(bool(shown))

    # ---------------------------------------------------------------- slots
    def _edited(self, key: str, value: Any) -> None:
        if self.viewmodel is not None:
            self.viewmodel.edit(key, value)

    def _refresh_values(self) -> None:
        if self.viewmodel is None:
            return
        for key, row in self.rows.items():
            row.set_value(self.viewmodel.value_of(key))

    def _show_problems(self, problems: dict[str, str]) -> None:
        for key, row in self.rows.items():
            row.set_problem(problems.get(key, ""))
        self.save_button.setEnabled(not problems)

    def _show_dirty(self, pending: dict) -> None:
        count = len(pending)
        self.dirty_label.setText(
            f"{count} kaydedilmemiş değişiklik" if count else "Tüm değişiklikler kaydedildi"
        )
        self.discard_button.setEnabled(bool(count))

    def _save(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.save()

    def _discard(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.discard()


__all__ = ["SettingsPage"]
