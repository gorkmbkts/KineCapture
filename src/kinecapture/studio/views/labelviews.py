"""The three things the label panel can be showing, and the widgets they share.

The panel is one place with three jobs: a summary of what has been labelled, an
editor for one movement, and an editor for one fault. Which one is open follows
what the annotator just did - clicking a movement box on the timeline opens the
movement editor on *that* movement, first click, no second step - so the panel
is never showing something other than the thing being worked on.

Two things this file is careful about.

**Readiness is three states, not two.** Green is "finished and clean"; amber is
"something is still missing"; red is "this repetition contains a fault". A
movement nobody has reviewed is *amber*, not green, however many faults it does
not have - which is why the summary reads its colour from the existing
``Readiness`` rather than from ``len(errors) == 0``.

**A class is a button, not a line in a dropdown.** Thirty repetitions is thirty
choices, and a dropdown costs two clicks and a read each time. With many
classes the buttons stay usable by being filtered, not by becoming a list
again.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens, class_colour_token
from kinecapture.studio.viewmodels.review import READINESS_TEXT, MovementRow

from . import iconset
from .widgets import ElidedLabel, label, separator

#: Above this many classes the picker offers a search box. Below it, scanning
#: a grid of buttons is faster than typing.
SEARCH_AFTER = 8


class ClassPicker(QWidget):
    """Classes as buttons, with a place to add one.

    The "add" row is part of the picker rather than a dialog: a class is
    created mid-labelling, applied to the interval that prompted it, and the
    panel stays open. A dialog would close over the thing being labelled and
    lose the place.
    """

    chosen = Signal(str)
    #: A name was typed and Ekle pressed. The owner decides what creating one
    #: involves - a fault class also needs its joints, a movement class does
    #: not - so this only carries the name.
    create_requested = Signal(str)

    def __init__(
        self,
        tokens: ThemeTokens,
        *,
        placeholder: str,
        fault: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._fault = fault
        self._options: tuple[tuple[str, str], ...] = ()
        self._selected = ""
        self._buttons: dict[str, QToolButton] = {}

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Sınıf ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Sınıf ara")
        self.search.textChanged.connect(lambda _text: self._rebuild())
        self.search.hide()
        column.addWidget(self.search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._holder = QWidget()
        self._grid = QVBoxLayout(self._holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(tokens.metric("KcSpacingXs"))
        self._grid.addStretch(1)
        self._scroll.setWidget(self._holder)
        column.addWidget(self._scroll, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(tokens.metric("KcSpacingSm"))
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText(placeholder)
        self.new_name.setAccessibleName(placeholder)
        self.new_name.returnPressed.connect(self._create)
        add_row.addWidget(self.new_name, 1)
        self.add_button = QPushButton("Ekle")
        self.add_button.setProperty("kcVariant", "primary")
        self.add_button.setIcon(
            iconset.icon("add", tokens, size=tokens.metric("KcIconSize"))
        )
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._create)
        add_row.addWidget(self.add_button)
        column.addLayout(add_row)
        self.new_name.textChanged.connect(self._name_typed)

        self.hint = ElidedLabel("")
        self.hint.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.hint)

    # ----------------------------------------------------------------- state
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._rebuild()

    def set_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._options = tuple(options)
        self.search.setVisible(len(self._options) > SEARCH_AFTER)
        self._rebuild()

    def set_selected(self, code: str) -> None:
        if code == self._selected:
            return
        self._selected = code
        self._restyle()

    @property
    def selected(self) -> str:
        return self._selected

    def set_hint(self, text: str, *, warning: bool = False) -> None:
        self.hint.setText(text)
        self.hint.setProperty("kcStatus", "warning" if warning else None)
        style = self.hint.style()
        if style is not None:
            style.unpolish(self.hint)
            style.polish(self.hint)

    def set_add_enabled(self, enabled: bool) -> None:
        """Owner-imposed gate: a fault class also needs at least one joint."""
        self._add_gate = bool(enabled)
        self._name_typed(self.new_name.text())

    def typed_name(self) -> str:
        return " ".join(self.new_name.text().split())

    def clear_new_name(self) -> None:
        self.new_name.clear()

    # ---------------------------------------------------------------- build
    def _matching(self) -> tuple[tuple[str, str], ...]:
        needle = self.search.text().strip().casefold()
        if not needle:
            return self._options
        return tuple(
            (code, text)
            for code, text in self._options
            if needle in text.casefold() or needle in code.casefold()
        )

    def _rebuild(self) -> None:
        while self._grid.count() > 1:
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # See ClassStrip._rebuild: unparenting a visible widget
                # turns it into a floating window until it is collected.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._buttons.clear()
        for index, (code, text) in enumerate(self._matching()):
            button = QToolButton(self._holder)
            button.setText(text)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setSizePolicy(
                button.sizePolicy().horizontalPolicy(),
                button.sizePolicy().verticalPolicy(),
            )
            button.setAccessibleName(text)
            button.clicked.connect(
                lambda _checked=False, key=code: self._choose(key)
            )
            # The class's own colour, the same one the timeline paints it in,
            # so the button and the box on the timeline are recognisably the
            # same thing.
            position = self._position_of(code)
            if position >= 0:
                token = class_colour_token(position, fault=self._fault)
                button.setIcon(
                    iconset.icon(
                        "circle",
                        self._tokens,
                        colour_token=token,
                        size=self._tokens.metric("KcIconSize"),
                    )
                )
            self._grid.insertWidget(self._grid.count() - 1, button)
            self._buttons[code] = button
        self._restyle()

    def _position_of(self, code: str) -> int:
        for index, (key, _text) in enumerate(self._options):
            if key == code:
                return index
        return -1

    def _restyle(self) -> None:
        for code, button in self._buttons.items():
            button.setChecked(code == self._selected)

    # --------------------------------------------------------------- actions
    def _choose(self, code: str) -> None:
        self.set_selected(code)
        self.chosen.emit(code)

    def _name_typed(self, text: str) -> None:
        gate = getattr(self, "_add_gate", True)
        self.add_button.setEnabled(bool(text.strip()) and gate)

    def _create(self) -> None:
        name = self.typed_name()
        if not name or not self.add_button.isEnabled():
            return
        self.create_requested.emit(name)


class MovementCard(QWidget):
    """One movement in the summary: what it is, how long, and what it needs."""

    activated = Signal(str)
    expanded = Signal(str, bool)

    def __init__(
        self,
        tokens: ThemeTokens,
        row: MovementRow,
        fps: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._row = row
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingXs"))

        head = QHBoxLayout()
        head.setSpacing(tokens.metric("KcSpacingSm"))
        self.title = QToolButton()
        self.title.setText(row.exercise_label or "sınıf yok")
        self.title.setAutoRaise(True)
        self.title.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.title.setAccessibleName(row.exercise_label or "sınıfı olmayan hareket")
        self.title.clicked.connect(lambda: self.activated.emit(row.sample_id))
        if row.colour_index >= 0:
            self.title.setIcon(
                iconset.icon(
                    "circle",
                    tokens,
                    colour_token=class_colour_token(row.colour_index),
                    size=tokens.metric("KcIconSize"),
                )
            )
        head.addWidget(self.title, 1)

        # Readiness as a word *and* a colour. Amber for unreviewed, whatever
        # the fault count is: "nobody has looked" is not "clean".
        self.state = QLabel(READINESS_TEXT[row.readiness])
        self.state.setProperty("kcRole", "mono")
        self.state.setProperty("kcStatus", row.status)
        head.addWidget(self.state)
        column.addLayout(head)

        seconds = (row.end - row.start + 1) / max(1.0, fps)
        detail = (
            f"{row.start}–{row.end} · {seconds:.1f} sn · "
            + (f"{row.error_count} hata" if row.error_count else "hata yok")
        )
        self.detail = ElidedLabel(detail)
        self.detail.setProperty("kcRole", "pageSubtitle")
        self.detail.setToolTip(detail)
        column.addWidget(self.detail)

        self.faults = QWidget(self)
        self._fault_layout = QVBoxLayout(self.faults)
        self._fault_layout.setContentsMargins(
            tokens.metric("KcSpacingLg"), 0, 0, 0
        )
        self._fault_layout.setSpacing(tokens.metric("KcSpacingXs"))
        self.faults.hide()
        column.addWidget(self.faults)

        if row.error_count:
            self.expand = QToolButton()
            self.expand.setText(f"{row.error_count} hata")
            self.expand.setCheckable(True)
            self.expand.setAutoRaise(True)
            self.expand.setIcon(
                iconset.icon("expand", tokens, size=tokens.metric("KcIconSize"))
            )
            self.expand.setAccessibleName("Bu hareketin hatalarını aç")
            self.expand.toggled.connect(self._toggled)
            column.addWidget(self.expand)
        else:
            self.expand = None

    def _toggled(self, shown: bool) -> None:
        self.faults.setVisible(shown)
        self.expanded.emit(self._row.sample_id, shown)

    def add_fault(self, widget: QWidget) -> None:
        self._fault_layout.addWidget(widget)

    @property
    def row(self) -> MovementRow:
        return self._row


__all__ = ["ClassPicker", "MovementCard", "SEARCH_AFTER"]
