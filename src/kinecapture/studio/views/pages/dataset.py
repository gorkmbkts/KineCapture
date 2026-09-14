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
    QLineEdit,
    QPushButton,
    QTableView,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.dataset import DatasetRow, DatasetViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from ..models import Column, RowTableModel, SearchProxy
from ..widgets import ElidedLabel
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
        self.search.textChanged.connect(self.proxy_filter)
        bar.addWidget(self.search, 1)

        self.filter_box = QComboBox()
        self.filter_box.setAccessibleName("Durum filtresi")
        self.filter_box.setToolTip("Listeyi hazırlık durumuna göre daraltır")
        for key, text in FILTERS:
            self.filter_box.addItem(text, key)
        self.filter_box.currentIndexChanged.connect(lambda _i: self._apply_filter())
        bar.addWidget(self.filter_box)

        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.clicked.connect(lambda: self._reload(force=True))
        bar.addWidget(self.refresh_button)
        self.body_layout.addLayout(bar)

        self.model = RowTableModel(_columns())
        self.proxy = SearchProxy(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.body_layout.addWidget(self.table, 1)

        self.totals = ElidedLabel("—")
        self.totals.setProperty("kcRole", "contextValue")
        self.body_layout.addWidget(self.totals)

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
