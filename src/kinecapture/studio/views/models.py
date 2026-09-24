"""One table model for every list in the Studio.

Qt only builds delegates for the rows it can actually see, so a table view over
a model stays flat as the data grows. The pattern this replaces - a
``QTableWidgetItem`` per cell - allocated nine objects per row whether or not
anyone looked at them: measured at 36 ms to fill a thousand rows and 183 ms for
five thousand, repeated on every filter change.

A column is a function from a row object to a string, so the model knows
nothing about takes, participants or projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, Sequence, TypeVar

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, QSortFilterProxyModel

T = TypeVar("T")

#: Carries the row object itself, for a selection handler that needs more than text.
ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 1
#: Carries a sort key that is not the displayed text (a date, a count).
SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 2
#: Carries a status word so a delegate can colour by state, never by parsing text.
STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 3
#: Every column of a row, lower-cased and joined, for one-call searching.
SEARCH_ROLE = int(Qt.ItemDataRole.UserRole) + 4


@dataclass(frozen=True)
class Column(Generic[T]):
    """One column: a heading and how to get its text out of a row.

    ``stretch`` marks the column whose content has no natural length - a
    project name, a take's title - and which should therefore take whatever
    room is left. Everything else is sized from its content. The 15 September
    audit found the opposite arrangement: a project name elided at about a
    hundred pixels while "Oluşturuldu" held several hundred.
    """

    key: str
    title: str
    text: Callable[[T], str]
    #: Sort key, when sorting by the displayed string would be wrong.
    sort_key: Optional[Callable[[T], Any]] = None
    #: Status word for this cell, if any. Drives colour *and* is read aloud.
    status: Optional[Callable[[T], str]] = None
    tooltip: Optional[Callable[[T], str]] = None
    numeric: bool = False
    width: int = 0
    #: Takes the leftover width. At most one per table in practice.
    stretch: bool = False
    #: A floor for a content-sized column, so a one-character value does not
    #: produce a column narrower than its own heading.
    minimum: int = 0


#: Everything below returns ``None`` for any other role, so the set is the
#: whole contract of :meth:`RowTableModel.data`.
_ANSWERED_ROLES = frozenset(
    {
        int(Qt.ItemDataRole.DisplayRole),
        int(Qt.ItemDataRole.ToolTipRole),
        int(Qt.ItemDataRole.TextAlignmentRole),
        int(Qt.ItemDataRole.AccessibleTextRole),
        ROW_ROLE,
        SORT_ROLE,
        STATUS_ROLE,
        SEARCH_ROLE,
    }
)


class RowTableModel(QAbstractTableModel, Generic[T]):
    """A read-only table over a list of value objects."""

    def __init__(
        self, columns: Sequence[Column[T]], parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: list[T] = []
        # Sort keys, computed once per column when that column is first sorted
        # by. Qt asks for a key on every comparison - O(n log n) of them - and
        # each one was calling a Python lambda: measured at 198 ms to fill a
        # thousand sorted rows, against 3 ms with the keys precomputed.
        self._sort_cache: dict[int, list[Any]] = {}
        # Display text per row, computed the first time that row is asked
        # about and kept. Painting, searching and tooltips all read it, and
        # each one used to call the column's lambda again: 30 visible rows of
        # nine columns is 270 crossings of the C++/Python boundary per repaint.
        self._text_cache: list[Optional[tuple[str, ...]]] = []
        self._search_cache: list[Optional[str]] = []

    # ------------------------------------------------------------------ data
    def set_rows(self, rows: Sequence[T]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._sort_cache.clear()
        self._text_cache = [None] * len(self._rows)
        self._search_cache = [None] * len(self._rows)
        self.endResetModel()

    def _row_text(self, row_index: int) -> tuple[str, ...]:
        cached = self._text_cache[row_index]
        if cached is None:
            row = self._rows[row_index]
            cached = tuple(column.text(row) for column in self._columns)
            self._text_cache[row_index] = cached
        return cached

    def _row_search_text(self, row_index: int) -> str:
        cached = self._search_cache[row_index]
        if cached is None:
            cached = " | ".join(self._row_text(row_index)).casefold()
            self._search_cache[row_index] = cached
        return cached

    def row_at(self, position: int) -> Optional[T]:
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None

    @property
    def rows(self) -> tuple[T, ...]:
        return tuple(self._rows)

    # ------------------------------------------------------- QAbstractItemModel
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        # Qt asks for eight or nine roles per cell while painting, and every
        # one of them is a crossing into Python. Rejecting the ones we never
        # answer with a single set lookup, before touching anything else, is
        # the cheapest part of the repaint to make cheaper.
        if role not in _ANSWERED_ROLES or not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._row_text(index.row())[index.column()]
        row = self._rows[index.row()]
        column = self._columns[index.column()]
        if role == SEARCH_ROLE:
            return self._row_search_text(index.row())
        if role == Qt.ItemDataRole.ToolTipRole:
            return (
                column.tooltip(row)
                if column.tooltip
                else self._row_text(index.row())[index.column()]
            )
        if role == ROW_ROLE:
            return row
        if role == SORT_ROLE:
            return self._sort_keys(index.column())[index.row()]
        if role == STATUS_ROLE:
            return column.status(row) if column.status else ""
        if role == Qt.ItemDataRole.TextAlignmentRole and column.numeric:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.AccessibleTextRole:
            status = column.status(row) if column.status else ""
            text = self._row_text(index.row())[index.column()]
            return f"{text} ({status})" if status else text
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation is Qt.Orientation.Horizontal:
            return self._columns[section].title
        return section + 1

    # ------------------------------------------------------------------ sort
    def sort(  # noqa: N802 - Qt naming
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Sort the rows here, in one pass, instead of through the proxy.

        Letting ``QSortFilterProxyModel`` do it means Qt calls ``data()`` twice
        per comparison - O(n log n) crossings of the C++/Python boundary, which
        measured 224 ms to fill a thousand sorted rows. One ``list.sort`` over
        the cached keys does the same job in about three.
        """
        if not self._rows or not 0 <= column < len(self._columns):
            return
        keys = list(self._sort_keys(column))
        order_index = sorted(
            range(len(self._rows)),
            key=lambda position: _sortable(keys[position]),
            reverse=order is Qt.SortOrder.DescendingOrder,
        )
        self.layoutAboutToBeChanged.emit()
        self._rows = [self._rows[position] for position in order_index]
        # Every cache is positional, so it moves with the rows rather than
        # being thrown away and recomputed on the next header click.
        for index, cached in self._sort_cache.items():
            self._sort_cache[index] = [cached[position] for position in order_index]
        self._text_cache = [self._text_cache[position] for position in order_index]
        self._search_cache = [self._search_cache[position] for position in order_index]
        self.layoutChanged.emit()

    def _sort_keys(self, column_index: int) -> list[Any]:
        cached = self._sort_cache.get(column_index)
        if cached is None:
            column = self._columns[column_index]
            getter = column.sort_key or column.text
            cached = [getter(row) for row in self._rows]
            self._sort_cache[column_index] = cached
        return cached

    @property
    def columns(self) -> tuple[Column[T], ...]:
        return tuple(self._columns)


def _sortable(value: Any) -> tuple[int, Any]:
    """A key that orders mixed types without raising.

    Missing values sort last in ascending order: an empty cell is not a small
    one, and letting it lead the list would push the rows that matter down.
    """
    if value is None or value == "":
        return (1, "")
    if isinstance(value, (int, float)):
        return (0, value)
    return (0, str(value))


class SearchProxy(QSortFilterProxyModel):
    """Case-insensitive search across every column, plus sorting.

    Filtering in the proxy rather than by rebuilding the source keeps the work
    off the data path: typing a letter re-evaluates rows, it does not re-read
    the project.
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        # Off: with it on, every model reset re-sorts the proxy, and that sort
        # is the expensive one this class exists to avoid.
        self.setDynamicSortFilter(False)
        self._needle = ""
        #: A second term every row must match as well, set by a filter control.
        self._required = ""

    def sort(  # noqa: N802 - Qt naming
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Hand sorting to the source model, which can do it in one pass."""
        source = self.sourceModel()
        if isinstance(source, RowTableModel):
            source.sort(column, order)
            return
        super().sort(column, order)

    def set_search(self, text: str) -> None:
        self._needle = text.strip().casefold()
        # ``invalidate``, not ``invalidateFilter``/``invalidateRowsFilter``:
        # PySide6 6.10 marks both of those deprecated, and this project turns
        # its own DeprecationWarnings into errors rather than letting them
        # accumulate until an upgrade breaks something.
        self.invalidate()

    def set_required(self, text: str) -> None:
        """A second term every row must also match, for a chosen filter.

        Kept apart from the search term so the two *narrow together* rather
        than replacing each other: choosing a participant and then typing a
        date must leave the rows that satisfy both, not the rows that satisfy
        whichever was set last.
        """
        required = text.strip().casefold()
        if required == self._required:
            return
        self._required = required
        self.invalidate()

    def filterAcceptsRow(  # noqa: N802
        self, source_row: int, source_parent: QModelIndex
    ) -> bool:
        if not self._needle and not self._required:
            return True
        model = self.sourceModel()
        # One call per row, not one per cell: the source keeps a joined,
        # lower-cased copy of the row for exactly this.
        haystack = model.data(
            model.index(source_row, 0, source_parent), SEARCH_ROLE
        )
        if not haystack:
            return False
        if self._required and self._required not in haystack:
            return False
        return not self._needle or self._needle in haystack


#: How many rows a content-sized column is measured over. Qt's default is a
#: thousand: every reset, filter, sort and style change then asked the model
#: for a thousand rows' worth of text, colours and alignment, per column, in
#: Python. Switching the theme with the list screens built made 490 000 such
#: calls and held the GUI thread for 8.9 s; each keystroke in a search box
#: paid a share of the same (release gate A3, 23 September 2026). The columns
#: sized this way hold fixed-shape values - ids, dates, counts, states - so the
#: first screenful says how wide they need to be; text of unknown length lives
#: in the stretch column.
CONTENT_SIZING_ROWS = 64


def limit_content_sizing(view) -> None:  # noqa: ANN001 - QTableView
    """Measure content-sized columns over :data:`CONTENT_SIZING_ROWS` rows."""
    view.horizontalHeader().setResizeContentsPrecision(CONTENT_SIZING_ROWS)


def configure_columns(  # noqa: ANN001
    view, columns: Sequence[Column], *, fill: bool = True
) -> None:
    """Give each column the width its content actually needs.

    Called once, when the table is built. The user can still drag any of them
    afterwards - a stretch column becomes interactive the moment it is
    dragged, which is Qt's own behaviour and the right one - but nobody should
    have to drag anything to read a name on first sight.
    """
    from PySide6.QtWidgets import QHeaderView

    header = view.horizontalHeader()
    limit_content_sizing(view)
    # Off: with it on, the last column absorbs the leftover width whatever it
    # holds, which is how a date column ended up several hundred pixels wide.
    header.setStretchLastSection(False)
    for index, column in enumerate(columns):
        if column.stretch:
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
            continue
        if column.width:
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(index, column.width)
            continue
        header.setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
    if column_minimums := {i: c.minimum for i, c in enumerate(columns) if c.minimum}:
        for index, minimum in column_minimums.items():
            if header.sectionSize(index) < minimum:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(index, minimum)
    if fill and not any(column.stretch for column in columns):
        # Nothing here has a variable length, so rather than inflate
        # one arbitrary column the leftover width is left blank.
        header.setStretchLastSection(True)


__all__ = [
    "ROW_ROLE",
    "SEARCH_ROLE",
    "SORT_ROLE",
    "STATUS_ROLE",
    "Column",
    "RowTableModel",
    "SearchProxy",
    "CONTENT_SIZING_ROWS",
    "configure_columns",
    "limit_content_sizing",
]
