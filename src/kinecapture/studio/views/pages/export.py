"""Dışa Aktarım: what will go in, what will not, and why.

The list is the point. A coach should be able to look at this screen and
answer "is everything I labelled actually in the dataset?" without opening a
file - so every version appears here either as a row that goes in or a row
with the reason it does not, and the build button does not hide the second
group.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.export import ExportViewModel, PreflightRow
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from ..models import Column, RowTableModel, SearchProxy
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage


def _columns() -> tuple[Column[PreflightRow], ...]:
    return (
        Column("take", "Kayıt", lambda r: r.take_id or "—"),
        Column("run", "Sürüm", lambda r: r.run_id),
        Column(
            "samples",
            "Hareket",
            lambda r: str(r.samples) if r.accepted else "—",
            sort_key=lambda r: r.samples,
            numeric=True,
        ),
        Column(
            "state",
            "Durum",
            lambda r: "Hazır" if r.accepted else "Dışarıda",
            sort_key=lambda r: (0 if r.accepted else 1, r.run_id),
        ),
        Column("why", "Açıklama", lambda r: r.text),
    )


class ExportPage(StudioPage):
    """Preflight, then build."""

    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ExportViewModel] = None
        self.library: Optional[LibraryViewModel] = None

        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingSm"))
        self.check_button = QPushButton("Sürümleri kontrol et")
        self.check_button.setToolTip(
            "Her sürümü açar, türetilmiş dosyaların checksum'ını doğrular ve "
            "etiketleri sürümüne karşı denetler. Yazmadan önce yapılır."
        )
        self.check_button.clicked.connect(self._check)
        bar.addWidget(self.check_button)

        self.build_button = QPushButton("Paketi yaz")
        self.build_button.setEnabled(False)
        self.build_button.clicked.connect(self._build)
        bar.addWidget(self.build_button)
        bar.addWidget(separator(Qt.Orientation.Vertical))

        self.confidences_box = QCheckBox("Güven dizilerini yaz")
        self.confidences_box.setChecked(True)
        self.confidences_box.setToolTip(
            "Kapatmak paketi küçültür; karşılığında bir karenin ne kadar "
            "güvenilir olduğunu söyleyen tek sinyal gider."
        )
        self.confidences_box.toggled.connect(
            lambda on: self._set_option(store_confidences=on)
        )
        bar.addWidget(self.confidences_box)

        self.dense_box = QCheckBox("Kare başına hata hedefi")
        self.dense_box.setChecked(True)
        self.dense_box.setToolTip(
            "Aralık biçimi her zaman yazılır; bu, ondan türetilen kolaylık."
        )
        self.dense_box.toggled.connect(
            lambda on: self._set_option(store_dense_error_targets=on)
        )
        bar.addWidget(self.dense_box)
        bar.addStretch(1)

        self.summary = ElidedLabel("Henüz kontrol edilmedi.")
        self.summary.setProperty("kcRole", "contextValue")
        bar.addWidget(self.summary)
        self.body_layout.addLayout(bar)

        self.model = RowTableModel(_columns())
        self.proxy = SearchProxy(self.model)
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
        self.table.selectionModel  # noqa: B018 - created with the model
        self.body_layout.addWidget(self.table, 1)

        detail = QVBoxLayout()
        detail.setSpacing(tokens.metric("KcSpacingXs"))
        detail.addWidget(label("Seçili sürümün ayrıntısı", role="section"))
        self.detail = ElidedLabel("—")
        self.detail.setProperty("kcRole", "pageSubtitle")
        detail.addWidget(self.detail)
        self.release_path = mono_label("")
        detail.addWidget(self.release_path)
        self.body_layout.addLayout(detail)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)

    # ------------------------------------------------------------------ bind
    def attach(self, viewmodel: ExportViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.rows, self.model.set_rows)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.can_build, self.build_button.setEnabled)
        self.bind(viewmodel.busy, self._show_busy)
        self.bind(viewmodel.last_release, self._show_release)
        self.bind_event(viewmodel.message, self.show_message)

    def use_library(self, library: LibraryViewModel) -> None:
        """The set of versions to consider comes from İşlenen Videolar."""
        self.library = library

    def page_activated(self) -> None:
        if self.library is not None:
            self.library.reload()

    # --------------------------------------------------------------- slots
    def _check(self) -> None:
        if self.viewmodel is None or self.library is None:
            return
        self.viewmodel.check(tuple(self.library.all_rows))

    def _build(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.build()

    def _set_option(self, **changes) -> None:  # noqa: ANN003
        if self.viewmodel is not None:
            self.viewmodel.set_option(**changes)

    def _show_busy(self, busy: bool) -> None:
        self.check_button.setEnabled(not busy)
        self.build_button.setEnabled(
            not busy and bool(self.viewmodel and self.viewmodel.can_build.value)
        )

    def _show_release(self, path: str) -> None:
        self.release_path.setText(f"Yazılan paket: {path}" if path else "")

    def _show_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.detail.setText("—")
            return
        row = self.model.row_at(self.proxy.mapToSource(rows[0]).row())
        if row is None:
            return
        lines = [row.text]
        lines.extend(row.detail)
        self.detail.setText("  ·  ".join(lines))


__all__ = ["ExportPage"]
