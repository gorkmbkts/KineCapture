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
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.settings import SettingField
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.settings import SettingsViewModel

from ..widgets import ElidedLabel, label, separator
from .base import StudioPage


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, tokens.metric("KcSpacingMd"))
        outer.setSpacing(tokens.metric("KcSpacingXs"))

        top = QHBoxLayout()
        top.setSpacing(tokens.metric("KcSpacingMd"))
        caption = label(field.label)
        caption.setMinimumWidth(200)
        top.addWidget(caption)
        self.control = self._build_control(field)
        top.addWidget(self.control, 1)
        if field.kind == "path":
            browse = QPushButton("Seç…")
            browse.setProperty("kcVariant", "quiet")
            browse.clicked.connect(self._browse)
            top.addWidget(browse)
        outer.addLayout(top)

        self.help = ElidedLabel(field.help_text)
        self.help.setProperty("kcRole", "pageSubtitle")
        self.help.setToolTip(field.help_text)
        outer.addWidget(self.help)

        if field.cost_note:
            cost = label(field.cost_note, role="fieldCost")
            cost.setToolTip(field.cost_note)
            outer.addWidget(cost)

        self.problem = label("", role="fieldError")
        self.problem.hide()
        outer.addWidget(self.problem)

        self.setAccessibleName(field.label)
        self.setAccessibleDescription(field.help_text)
        if field.read_only:
            self.control.setEnabled(False)

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

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, tokens.metric("KcSpacingLg"), 0)
        self._content_layout.setSpacing(tokens.metric("KcSpacingLg"))
        self.scroll.setWidget(self._content)
        self.body_layout.addWidget(self.scroll, 1)

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
        for _key, title, subtitle, fields in self.viewmodel.groups():
            header = label(title.upper(), role="sectionTitle")
            self._content_layout.addWidget(header)
            caption = ElidedLabel(subtitle)
            caption.setProperty("kcRole", "pageSubtitle")
            self._content_layout.addWidget(caption)
            self._content_layout.addWidget(separator())
            for field in fields:
                row = _FieldRow(field, tokens, self._edited, self._content)
                self.rows[field.key] = row
                self._content_layout.addWidget(row)
        self._content_layout.addStretch(1)

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
