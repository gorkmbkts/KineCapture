"""Searchable class picker with in-place class creation.

Choosing a class happens mid-labelling, dozens of times a session, so this is
optimised for typing rather than clicking: type a fragment, see matches ranked,
press Enter. If the class does not exist yet, the same Enter creates it and
assigns it, without leaving the labelling dialog.

Free-text entry - what this replaces - could not do any of that: it silently
created near-duplicate classes ("Diz içe çöküyor" vs "diz ice cokuyor") that
then split one class into several in the exported dataset.

Both vocabularies use the same widget. Movement classes used to be editable
only from the Settings screen, which meant an annotator who met a new exercise
mid-session had to leave the take, edit the project, and come back. Error
classes never had that problem, and now neither do movements.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.domain.labels import LabelOption, LabelSchema
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import make_button, make_label, restyle
from kinecapture.gui.widgets.timeline import error_class_colour


class LabelKind(str, Enum):
    """Which project vocabulary a picker is editing."""

    MOVEMENT = "movement"
    ERROR = "error"

    @property
    def noun(self) -> str:
        return {
            LabelKind.MOVEMENT: "hareket türü",
            LabelKind.ERROR: "hata türü",
        }[self]

    @property
    def empty_label(self) -> str:
        return {
            LabelKind.MOVEMENT: "Hareket türü seçilmedi",
            LabelKind.ERROR: "Hata türü seçilmedi",
        }[self]

    @property
    def shows_colour(self) -> bool:
        """Error classes are colour-coded on the timeline; movements are not."""
        return self is LabelKind.ERROR


class LabelClassPicker(QWidget):
    """A search box over one project vocabulary, plus "create new"."""

    #: An existing or newly created class was chosen. Carries the class code.
    class_chosen = Signal(str)
    #: The user asked for a class that does not exist yet. Carries the typed
    #: name; the caller decides whether to create it (it owns the repository).
    creation_requested = Signal(str)

    def __init__(
        self,
        theme: Theme,
        kind: LabelKind = LabelKind.ERROR,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._kind = kind
        self._schema = LabelSchema.default()
        self._current_code = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_xs)

        header = QHBoxLayout()
        header.setSpacing(theme.space_sm)
        self._current = make_label(kind.empty_label, role="muted")
        self._swatch = QLabel()
        self._swatch.setFixedSize(12, 12)
        self._swatch.setVisible(False)
        header.addWidget(self._swatch)
        header.addWidget(self._current, 1)
        container = QWidget()
        container.setLayout(header)
        layout.addWidget(container)

        self._search = QLineEdit()
        self._search.setPlaceholderText(f"{kind.noun.capitalize()} ara veya yeni ad yaz…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_results)
        self._search.returnPressed.connect(self._activate_current)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        self._results = QListWidget()
        self._results.setMinimumHeight(110)
        self._results.setAlternatingRowColors(True)
        self._results.itemActivated.connect(self._item_activated)
        self._results.itemClicked.connect(self._item_activated)
        layout.addWidget(self._results, 1)

        self._create_button = make_button(
            f"Yeni {kind.noun} ekle", icon="add", theme=theme
        )
        self._create_button.setToolTip(
            "Yazdığınız adı projeye kalıcı olarak ekler ve bu aralığa atar."
        )
        self._create_button.clicked.connect(self._request_creation)
        layout.addWidget(self._create_button)

        self._hint = make_label("", role="muted")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._refresh_results("")

    # ----------------------------------------------------------------- data
    @property
    def kind(self) -> LabelKind:
        return self._kind

    def set_schema(self, schema: LabelSchema) -> None:
        self._schema = schema
        self._refresh_results(self._search.text())

    def _options(self, query: str) -> Sequence[LabelOption]:
        if self._kind is LabelKind.MOVEMENT:
            return self._schema.search_exercises(query)
        return self._schema.search_error_types(query)

    def _match(self, query: str) -> Optional[LabelOption]:
        if not query:
            return None
        if self._kind is LabelKind.MOVEMENT:
            return self._schema.match_exercise(query)
        return self._schema.match_error_type(query)

    def _label_for(self, code: str) -> str:
        if self._kind is LabelKind.MOVEMENT:
            return self._schema.label_for_exercise(code)
        return self._schema.label_for_error(code)

    @property
    def _defined(self) -> Sequence[LabelOption]:
        return (
            self._schema.exercises
            if self._kind is LabelKind.MOVEMENT
            else self._schema.error_types
        )

    def set_current(self, code: str) -> None:
        """Show which class the selected interval currently carries."""
        self._current_code = code or ""
        if self._current_code:
            self._current.setText(self._label_for(self._current_code))
            self._current.setProperty("role", "")
            if self._kind.shows_colour:
                self._swatch.setStyleSheet(
                    f"background-color: {error_class_colour(self._current_code)};"
                    " border-radius: 3px;"
                )
                self._swatch.setVisible(True)
        else:
            self._current.setText(self._kind.empty_label)
            self._current.setProperty("role", "muted")
            self._swatch.setVisible(False)
        restyle(self._current)
        self._refresh_results(self._search.text())

    @property
    def current_code(self) -> str:
        return self._current_code

    def clear_search(self) -> None:
        self._search.clear()

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    # -------------------------------------------------------------- results
    def _refresh_results(self, text: str) -> None:
        query = text.strip()
        matches = self._options(query)
        self._results.clear()
        for option in matches:
            item = QListWidgetItem(option.label)
            item.setData(Qt.ItemDataRole.UserRole, option.code)
            if self._kind.shows_colour:
                item.setIcon(_swatch_icon(error_class_colour(option.code)))
            if option.code == self._current_code:
                item.setText(f"{option.label}   ✓")
            self._results.addItem(item)
        if matches:
            self._results.setCurrentRow(0)

        exact = self._match(query)
        can_create = bool(query) and exact is None
        self._create_button.setEnabled(can_create)
        self._create_button.setText(
            f"Yeni {self._kind.noun} ekle: “{query}”"
            if can_create
            else f"Yeni {self._kind.noun} ekle"
        )

        if not self._defined:
            self._hint.setText(
                f"Bu projede henüz {self._kind.noun} tanımlı değil. Bir ad yazıp "
                f"“Yeni {self._kind.noun} ekle” ile başlayın."
            )
        elif query and exact is not None and exact.code != self._current_code:
            self._hint.setText(
                f"“{exact.label}” zaten tanımlı — Enter ile seçilir, yeni tür "
                "oluşturulmaz."
            )
        elif not matches:
            self._hint.setText("Eşleşme yok. Enter yeni tür oluşturur.")
        else:
            self._hint.setText("")

    # ------------------------------------------------------------- activate
    def eventFilter(self, obj, event) -> bool:  # type: ignore[no-untyped-def]
        """Let Up/Down move through results while the search box keeps focus."""
        if obj is self._search and isinstance(event, QKeyEvent):
            if event.type() == QKeyEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Down,
                Qt.Key.Key_Up,
            ):
                row = self._results.currentRow()
                count = self._results.count()
                if count:
                    step = 1 if event.key() == Qt.Key.Key_Down else -1
                    self._results.setCurrentRow(max(0, min(count - 1, row + step)))
                return True
        return super().eventFilter(obj, event)

    def _item_activated(self, item: QListWidgetItem) -> None:
        code = item.data(Qt.ItemDataRole.UserRole)
        if code:
            self.class_chosen.emit(code)

    def _activate_current(self) -> None:
        """Enter: pick the highlighted match, or create what was typed."""
        query = self._search.text().strip()
        exact = self._match(query)
        if exact is not None:
            self.class_chosen.emit(exact.code)
            return
        item = self._results.currentItem()
        if item is not None and not query:
            self._item_activated(item)
            return
        if query:
            self.creation_requested.emit(query)
            return
        if item is not None:
            self._item_activated(item)

    def _request_creation(self) -> None:
        query = self._search.text().strip()
        if query:
            self.creation_requested.emit(query)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.set_current(self._current_code)


def _swatch_icon(colour: str) -> QIcon:
    """A small filled square in the class colour, for the result list."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, 12, 12, 3, 3)
    painter.end()
    return QIcon(pixmap)


class ErrorClassPicker(LabelClassPicker):
    """The error-class picker. Kept as its own name for existing call sites."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(theme, LabelKind.ERROR, parent)


class MovementClassPicker(LabelClassPicker):
    """The movement-class picker."""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(theme, LabelKind.MOVEMENT, parent)


__all__ = [
    "ErrorClassPicker",
    "LabelClassPicker",
    "LabelKind",
    "MovementClassPicker",
]
