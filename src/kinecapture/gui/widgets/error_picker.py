"""Searchable error-class picker with in-place class creation.

Choosing an error class happens mid-labelling, dozens of times a session, so
this is optimised for typing rather than clicking: type a fragment, see matches
ranked, press Enter. If the class does not exist yet, the same Enter creates it
and assigns it, without leaving the review screen.

Free-text comma-separated entry - what this replaces - could not do any of
that: it silently created near-duplicate classes ("Diz içe çöküyor" vs "diz ice
cokuyor") that then split one class into several in the exported dataset.
"""

from __future__ import annotations

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
from kinecapture.gui.widgets.common import make_button, make_label
from kinecapture.gui.widgets.timeline import error_class_colour


class ErrorClassPicker(QWidget):
    """A search box over the project's error classes, plus "create new"."""

    #: An existing or newly created class was chosen. Carries the class code.
    class_chosen = Signal(str)
    #: The user asked for a class that does not exist yet. Carries the typed
    #: name; the page decides whether to create it (it owns the repository).
    creation_requested = Signal(str)

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._schema = LabelSchema.default()
        self._current_code = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_xs)

        header = QHBoxLayout()
        header.setSpacing(theme.space_sm)
        self._current = make_label("Sınıf seçilmedi", role="muted")
        self._swatch = QLabel()
        self._swatch.setFixedSize(12, 12)
        header.addWidget(self._swatch)
        header.addWidget(self._current, 1)
        container = QWidget()
        container.setLayout(header)
        layout.addWidget(container)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Hata türü ara veya yeni ad yaz…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._refresh_results)
        self._search.returnPressed.connect(self._activate_current)
        self._search.installEventFilter(self)
        layout.addWidget(self._search)

        self._results = QListWidget()
        self._results.setMaximumHeight(92)
        self._results.setAlternatingRowColors(True)
        self._results.itemActivated.connect(self._item_activated)
        self._results.itemClicked.connect(self._item_activated)
        layout.addWidget(self._results)

        self._create_button = make_button(
            "Yeni hata türü ekle", icon="add", theme=theme
        )
        self._create_button.setMaximumHeight(28)
        self._create_button.setToolTip(
            "Yazdığınız adı projeye kalıcı olarak ekler ve seçili aralığa atar."
        )
        self._create_button.clicked.connect(self._request_creation)
        layout.addWidget(self._create_button)

        self._hint = make_label("", role="muted")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        self._refresh_results("")

    # ----------------------------------------------------------------- data
    def set_schema(self, schema: LabelSchema) -> None:
        self._schema = schema
        self._refresh_results(self._search.text())

    def set_current(self, code: str) -> None:
        """Show which class the selected interval currently carries."""
        self._current_code = code or ""
        if self._current_code:
            self._current.setText(self._schema.label_for_error(self._current_code))
            self._current.setProperty("role", "")
            self._swatch.setStyleSheet(
                f"background-color: {error_class_colour(self._current_code)};"
                " border-radius: 3px;"
            )
            self._swatch.setVisible(True)
        else:
            self._current.setText("Sınıf seçilmedi")
            self._current.setProperty("role", "muted")
            self._swatch.setVisible(False)
        from kinecapture.gui.widgets.common import restyle

        restyle(self._current)
        self._refresh_results(self._search.text())

    def clear_search(self) -> None:
        self._search.clear()

    def focus_search(self) -> None:
        self._search.setFocus()
        self._search.selectAll()

    # -------------------------------------------------------------- results
    def _refresh_results(self, text: str) -> None:
        query = text.strip()
        matches: Sequence[LabelOption] = self._schema.search_error_types(query)
        self._results.clear()
        for option in matches:
            item = QListWidgetItem(option.label)
            item.setData(Qt.ItemDataRole.UserRole, option.code)
            item.setIcon(
                _swatch_icon(error_class_colour(option.code))
            )
            if option.code == self._current_code:
                item.setText(f"{option.label}   ✓")
            self._results.addItem(item)
        if matches:
            self._results.setCurrentRow(0)

        exact = self._schema.match_error_type(query) if query else None
        can_create = bool(query) and exact is None
        self._create_button.setEnabled(can_create)
        self._create_button.setText(
            f"Yeni hata türü ekle: “{query}”" if can_create else "Yeni hata türü ekle"
        )

        if not self._schema.error_types:
            self._hint.setText(
                "Bu projede henüz hata türü tanımlı değil. Bir ad yazıp "
                "“Yeni hata türü ekle” ile başlayın."
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
        exact = self._schema.match_error_type(query) if query else None
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
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(1, 1, 10, 10, 3, 3)
    painter.end()
    return QIcon(pixmap)


__all__ = ["ErrorClassPicker"]
