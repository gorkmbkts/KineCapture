"""Veri Seti: everything the project holds, and what each row is waiting on.

A list, not a verdict. The expensive authoritative check lives in Dışa
Aktarım; this screen reads sidecars and says what it sees, which is why its
wording is "hazır görünüyor" rather than "hazır".
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.dataset import (
    BLOCKER_TEXT,
    DatasetRow,
    DatasetViewModel,
)
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
from ..models import Column, RowTableModel, SearchProxy
from ..widgets import ElidedLabel, label, separator
from .base import StudioPage

FILTERS = (
    ("all", "Tümü"),
    ("ready", "Hazır görünüyor"),
    ("blocked", "Bir şey bekliyor"),
    ("unlabelled", "Etiketlenmemiş"),
)


def _columns() -> tuple[Column[DatasetRow], ...]:
    return (
        Column("participant", "Katılımcı", lambda r: r.participant_id),
        Column(
            "started",
            "Tarih",
            lambda r: r.started_at[:16].replace("T", " "),
            sort_key=lambda r: r.started_at,
            numeric=True,
        ),
        Column(
            "duration",
            "Süre",
            lambda r: f"{r.duration_s:.0f} sn",
            sort_key=lambda r: r.duration_s,
            numeric=True,
        ),
        Column(
            "movements",
            "Hareket",
            lambda r: f"{r.ready}/{r.movements}" if r.movements else "—",
            sort_key=lambda r: r.movements,
            numeric=True,
        ),
        Column(
            "errors",
            "Hata aralığı",
            lambda r: str(r.error_intervals) if r.error_intervals else "—",
            sort_key=lambda r: r.error_intervals,
            numeric=True,
        ),
        Column(
            "athlete",
            "Sporcu",
            lambda r: "seçildi" if r.athlete_chosen else "—",
            sort_key=lambda r: r.athlete_chosen,
        ),
        Column("state", "Durum", lambda r: r.text),
    )


class DatasetPage(StudioPage):
    """The project-wide coverage view."""

    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[DatasetViewModel] = None
        self._all: tuple[DatasetRow, ...] = ()

        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingSm"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Katılımcı veya sürüm ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Kayıtlarda ara")
        self.search.addAction(
            iconset.icon("search", tokens, size=tokens.metric("KcIconSize")),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        # Capped, like every other search box in the product: stretched across
        # 1650 pixels it was the widest thing on the screen and no easier to
        # type into. Left-aligned, at a width the placeholder fits in.
        self.search.setMinimumWidth(320)
        self.search.setMaximumWidth(480)
        self.search.textChanged.connect(self.proxy_filter)
        bar.addWidget(self.search, 0)

        self.filter_box = QComboBox()
        self.filter_box.setAccessibleName("Durum filtresi")
        self.filter_box.setToolTip("Listeyi hazırlık durumuna göre daraltır")
        for key, text in FILTERS:
            self.filter_box.addItem(text, key)
        self.filter_box.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.filter_box)

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setIcon(
            iconset.icon("refresh", tokens, size=tokens.metric("KcIconSize"))
        )
        self.refresh_button.clicked.connect(lambda: self._reload(force=True))
        for control in (self.search, self.filter_box, self.refresh_button):
            control.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        bar.addStretch(1)
        bar.addWidget(self.refresh_button)
        self.body_layout.addLayout(bar)

        self.model = RowTableModel(_columns())
        self.proxy = SearchProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _i: self._open_selected())

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self.table)
        split.addWidget(self._build_detail())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        self.split = split
        self._split_pinned = False
        split.splitterMoved.connect(lambda *_a: setattr(self, "_split_pinned", True))
        self.body_layout.addWidget(split, 1)

        self.totals = ElidedLabel("—")
        self.totals.setProperty("kcRole", "contextValue")
        self.body_layout.addWidget(self.totals)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)

    #: How much of the width the list keeps. The detail panel is a fixed set
    #: of lines and at most a handful of actions; the list is the part that
    #: grows with the project.
    _LIST_SHARE = 0.66

    def _build_detail(self) -> QWidget:
        """What the selected record is waiting on, and how to go and fix it."""
        tokens = self._tokens
        panel = QWidget()
        panel.setMinimumWidth(tokens.metric("KcLabelPanelMinWidth"))
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        column.addWidget(label("SEÇİLİ KAYIT", role="sectionTitle"))
        self.detail_title = ElidedLabel("Bir kayıt seçin.")
        self.detail_title.setProperty("kcRole", "contextValue")
        column.addWidget(self.detail_title)
        self.detail_lines = QLabel("")
        self.detail_lines.setWordWrap(True)
        self.detail_lines.setProperty("kcRole", "pageSubtitle")
        self.detail_lines.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        column.addWidget(self.detail_lines)

        column.addWidget(separator())
        column.addWidget(label("BEKLEYEN", role="sectionTitle"))
        self.blocker_holder = QWidget(panel)
        self._blocker_layout = QVBoxLayout(self.blocker_holder)
        self._blocker_layout.setContentsMargins(0, 0, 0, 0)
        self._blocker_layout.setSpacing(tokens.metric("KcSpacingXs"))
        column.addWidget(self.blocker_holder)
        column.addStretch(1)

        self.open_button = QPushButton("Etiketlemede aç")
        self.open_button.setProperty("kcVariant", "primary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        column.addWidget(self.open_button)
        return panel

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._apply_split_ratio()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().showEvent(event)
        self._apply_split_ratio()

    def _apply_split_ratio(self) -> None:
        if self._split_pinned:
            return
        width = max(1, self.split.width())
        left = int(width * self._LIST_SHARE)
        self.split.setSizes([left, max(1, width - left)])

    # ------------------------------------------------------------------ bind
    def attach(self, viewmodel: DatasetViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.rows, self._show_rows)
        self.bind(viewmodel.totals, lambda t: self.totals.setText(t.text))
        self.bind(viewmodel.busy, lambda b: self.refresh_button.setEnabled(not b))
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        self._reload()

    def _reload(self, *, force: bool = False) -> None:
        if self.viewmodel is not None:
            self.viewmodel.reload(force=force)

    # ---------------------------------------------------------------- slots
    def proxy_filter(self, text: str) -> None:
        self.proxy.set_search(text)

    def _show_rows(self, rows: tuple[DatasetRow, ...]) -> None:
        self._all = rows
        self._apply_filter()

    def _selected_row(self) -> Optional[DatasetRow]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.model.row_at(self.proxy.mapToSource(rows[0]).row())

    def _show_detail(self) -> None:
        for position in reversed(range(self._blocker_layout.count())):
            item = self._blocker_layout.takeAt(position)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        row = self._selected_row()
        self.open_button.setEnabled(row is not None)
        if row is None:
            self.detail_title.setText("Bir kayıt seçin.")
            self.detail_lines.setText("")
            return

        self.detail_title.setText(f"{row.participant_id} · {row.run_id}")
        lines = [
            f"{row.started_at[:16].replace('T', ' ')} · {row.duration_s:.0f} sn"
            f" · {row.frames} kare",
            f"{row.ready}/{row.movements} hareket hazır"
            if row.movements
            else "hareket işaretlenmemiş",
        ]
        if row.error_intervals:
            lines.append(f"{row.error_intervals} hata aralığı")
        if row.excluded:
            lines.append(f"{row.excluded} hareket dışarıda bırakılmış")
        self.detail_lines.setText("\n".join(lines))

        if not row.blockers:
            # A record with nothing outstanding still does not get a green
            # verdict here: the authoritative answer is the export check, and
            # this screen reads sidecars.
            note = label("Bu ekrana göre bekleyen bir şey yok.", role="pageSubtitle")
            self._blocker_layout.addWidget(note)
            return
        for blocker in row.blockers:
            self._blocker_layout.addWidget(self._blocker_action(row, blocker))

    #: Where each blocker is actually fixed. A blocker with no destination
    #: gets a line and no button rather than a button that goes nowhere.
    BLOCKER_FOCUS = {
        "athlete": ("subject", "Kişi sekmesinde aç"),
        "questions": ("subject", "Belirsiz aralıkları yanıtla"),
        "open_error": ("open_error", "Sınıfsız hata aralığına git"),
        "no_exercise": ("no_exercise", "Sınıfsız harekete git"),
        "unlabelled": ("labels", "Etiketlemeye git"),
        "unreviewed": ("labels", "Etiketlemeye git"),
    }

    def _blocker_action(self, row: DatasetRow, blocker: str) -> QWidget:
        text = BLOCKER_TEXT.get(blocker, blocker)
        focus = self.BLOCKER_FOCUS.get(blocker)
        if focus is None:
            # "kişi seçilmeden işlenmiş" is not fixed by going anywhere: the
            # run has to be processed again. Saying so is more use than a
            # button that opens a screen which cannot help.
            note = label(f"· {text}", role="pageSubtitle")
            note.setProperty("kcStatus", "error")
            return note
        key, caption = focus
        button = QPushButton(f"{text} — {caption}")
        button.setToolTip(f"{row.run_id} sürümünü açar ve doğrudan oraya götürür.")
        button.clicked.connect(
            lambda _checked=False, r=row, k=key: self._open_at(r, k)
        )
        return button

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self._open_at(row, "labels")

    def _open_at(self, row: DatasetRow, focus: str) -> None:
        """Open *this* version and land on the thing that needs doing.

        DATA-01 is explicit that changing page is not enough: navigating
        without carrying the version leaves whichever one happened to be open
        on screen, and the reader fixes the wrong recording.
        """
        shell = self.window()
        if not hasattr(shell, "pending_review"):
            return
        shell.pending_review = row.directory
        shell.pending_review_focus = focus
        shell.viewmodel.navigate("review")

    def _apply_filter(self) -> None:
        key = self.filter_box.currentData() or "all"
        if key == "ready":
            rows = [r for r in self._all if r.looks_ready]
        elif key == "blocked":
            rows = [r for r in self._all if r.blockers and r.movements]
        elif key == "unlabelled":
            rows = [r for r in self._all if not r.movements]
        else:
            rows = list(self._all)
        self.model.set_rows(rows)


__all__ = ["DatasetPage", "FILTERS"]
