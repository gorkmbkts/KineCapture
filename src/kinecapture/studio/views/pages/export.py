"""Dışa Aktarım: what will go in, what will not, and why.

The list is the point. A coach should be able to look at this screen and
answer "is everything I labelled actually in the dataset?" without opening a
file - so every version appears here either as a row that goes in or a row
with the reason it does not, and the build button does not hide the second
group.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.export import (
    CHECK_STATE_TEXT,
    CheckState,
    ExportViewModel,
    PreflightRow,
)
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
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

        #: How much of the width the version list gets. The package column is
        #: a fixed set of choices and a destination; the list is the part that
        #: grows with the project, so the remainder is its.
        self._list_share = 0.62

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_versions())
        split.addWidget(self._build_package())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        self.split = split
        #: Until the user drags the handle, the ratio is re-applied on every
        #: resize. Setting sizes once before the first layout gave 39% of a
        #: window that did not exist yet.
        self._split_pinned = False
        split.splitterMoved.connect(lambda *_a: setattr(self, "_split_pinned", True))
        self.body_layout.addWidget(split, 1)

    # ----------------------------------------------------------------- build
    def _build_versions(self) -> QWidget:
        """The left half: what was checked, and what each version's answer is."""
        tokens = self._tokens
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        head = QHBoxLayout()
        head.setSpacing(tokens.metric("KcSpacingSm"))
        head.addWidget(label("SÜRÜMLER VE DOĞRULAMA", role="sectionTitle"))
        head.addStretch(1)
        self.check_button = QPushButton("Sürümleri kontrol et")
        self.check_button.setProperty("kcVariant", "primary")
        self.check_button.setToolTip(
            "Her sürümü açar, türetilmiş dosyaların checksum'ını doğrular ve "
            "etiketleri sürümüne karşı denetler. Yazmadan önce yapılır."
        )
        self.check_button.setIcon(
            iconset.icon("ok", tokens, size=tokens.metric("KcIconSize"))
        )
        self.check_button.clicked.connect(self._check)
        head.addWidget(self.check_button)
        column.addLayout(head)

        # The six states the screen can be in, said in words. "Not checked
        # yet" and "checked and refused" are different answers to the same
        # question, and a screen that shows one for the other is lying.
        self.state_line = ElidedLabel(CHECK_STATE_TEXT[CheckState.NOT_CHECKED])
        self.state_line.setProperty("kcRole", "contextValue")
        column.addWidget(self.state_line)
        self.summary = ElidedLabel("")
        self.summary.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.summary)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Kayıt veya sürüm ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Sürüm ara")
        column.addWidget(self.search)

        self.model = RowTableModel(_columns())
        self.proxy = SearchProxy(self)
        self.proxy.setSourceModel(self.model)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
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
        column.addWidget(self.table, 1)

        # The selected version's reasons, given room. This was a one-line
        # strip at the bottom of the window, which is where a refusal with
        # three reasons went to be elided into nothing.
        column.addWidget(separator())
        column.addWidget(label("SEÇİLİ SÜRÜM", role="sectionTitle"))
        self.detail = QLabel("Bir sürüm seçin.")
        self.detail.setWordWrap(True)
        self.detail.setProperty("kcRole", "pageSubtitle")
        self.detail.setMinimumHeight(tokens.metric("KcControlHeight") * 2)
        self.detail.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        column.addWidget(self.detail)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)
        return panel

    def _build_package(self) -> QWidget:
        """The right half: what goes in the package, and where it lands."""
        tokens = self._tokens
        panel = QWidget()
        panel.setMinimumWidth(tokens.metric("KcLabelPanelMinWidth"))
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        column.addWidget(label("PAKET", role="sectionTitle"))
        self.confidences_box = QCheckBox("Güven dizilerini yaz")
        self.confidences_box.setChecked(True)
        self.confidences_box.setToolTip(
            "Kapatmak paketi küçültür; karşılığında bir karenin ne kadar "
            "güvenilir olduğunu söyleyen tek sinyal gider."
        )
        self.confidences_box.toggled.connect(
            lambda on: self._set_option(store_confidences=on)
        )
        column.addWidget(self.confidences_box)

        self.dense_box = QCheckBox("Kare başına hata hedefi")
        self.dense_box.setChecked(True)
        self.dense_box.setToolTip(
            "Aralık biçimi her zaman yazılır; bu, ondan türetilen kolaylık."
        )
        self.dense_box.toggled.connect(
            lambda on: self._set_option(store_dense_error_targets=on)
        )
        column.addWidget(self.dense_box)

        column.addWidget(separator())
        column.addWidget(label("HEDEF KONUM", role="sectionTitle"))
        self.target_path = QLabel("Önce bir proje açın.")
        self.target_path.setWordWrap(True)
        self.target_path.setProperty("kcRole", "mono")
        column.addWidget(self.target_path)

        column.addWidget(separator())
        column.addWidget(label("İÇERİK", role="sectionTitle"))
        self.contents = QLabel("Henüz kontrol edilmedi.")
        self.contents.setWordWrap(True)
        self.contents.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.contents)
        column.addStretch(1)

        self.build_button = QPushButton("Paketi yaz")
        self.build_button.setProperty("kcVariant", "primary")
        self.build_button.setEnabled(False)
        self.build_button.setIcon(
            iconset.icon("export", tokens, size=tokens.metric("KcIconSize"))
        )
        self.build_button.clicked.connect(self._build)
        column.addWidget(self.build_button)

        self.release_path = mono_label("")
        self.release_path.setWordWrap(True)
        column.addWidget(self.release_path)
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
        left = int(width * self._list_share)
        self.split.setSizes([left, max(1, width - left)])

    # ------------------------------------------------------------------ bind
    def attach(self, viewmodel: ExportViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.rows, self._rows_changed)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.state, self._show_state)
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
        if self.viewmodel is not None:
            # EXPORT-02. Coming back to this screen after labelling is exactly
            # when a previous "hazır" stops being true, so the result is
            # re-checked against the revisions on disk before it is believed.
            self.viewmodel.recheck_freshness()
            self._show_target()

    # --------------------------------------------------------------- slots
    def _check(self) -> None:
        """Check every finished version - once the list of them exists.

        Pressing this while the library is still reading the project would
        otherwise check an empty list and report "nothing to export", which is
        the most misleading thing this screen could say.
        """
        if self.viewmodel is None or self.library is None:
            return
        if self.library.busy.value:
            self.summary.setText("Sürüm listesi okunuyor…")
            QTimer.singleShot(200, self._check)
            return
        rows = tuple(self.library.all_rows)
        if not rows:
            self.show_message(
                Message(
                    headline="Kontrol edilecek tamamlanmış sürüm yok.",
                    severity=Severity.WARNING,
                    detail="Önce İşlenen Videolar ekranında bir sürüm görünmeli.",
                )
            )
            return
        self.viewmodel.check(rows)

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

    #: Which status each check state paints itself with. STALE is a warning
    #: rather than an error: nothing is wrong with the data, the screen is
    #: simply out of date about it.
    STATE_STATUS = {
        CheckState.NOT_CHECKED: "",
        CheckState.CHECKING: "",
        CheckState.EMPTY: "warning",
        CheckState.READY: "ready",
        CheckState.WARNING: "warning",
        CheckState.BLOCKED: "error",
        CheckState.STALE: "warning",
    }

    def _show_state(self, state: CheckState) -> None:
        self.state_line.setText(CHECK_STATE_TEXT[state])
        self.state_line.setProperty("kcStatus", self.STATE_STATUS.get(state) or None)
        style = self.state_line.style()
        if style is not None:
            style.unpolish(self.state_line)
            style.polish(self.state_line)
        # The check button says what pressing it would do now. After a stale
        # result that is not "check", it is "check again".
        self.check_button.setText(
            "Yeniden kontrol et"
            if state in (CheckState.STALE, CheckState.WARNING, CheckState.BLOCKED)
            else "Sürümleri kontrol et"
        )

    def _rows_changed(self, rows) -> None:  # noqa: ANN001 - tuple[PreflightRow, ...]
        self.model.set_rows(rows)
        ready = [r for r in rows if r.accepted]
        if not rows:
            self.contents.setText("Henüz kontrol edilmedi.")
            return
        samples = sum(r.samples for r in ready)
        blocked = len(rows) - len(ready)
        lines = [f"{len(ready)} sürüm · {samples} hareket"]
        if blocked:
            # Named here as well as in the list: a count of what will *not* be
            # in the package is part of knowing what the package is.
            lines.append(f"{blocked} sürüm dışarıda kalacak")
        self.contents.setText("\n".join(lines))

    def _show_target(self) -> None:
        releases = self.viewmodel.releases_dir if self.viewmodel else None
        self.target_path.setText(str(releases) if releases else "Önce bir proje açın.")

    def _show_detail(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.detail.setText("Bir sürüm seçin.")
            return
        row = self.model.row_at(self.proxy.mapToSource(rows[0]).row())
        if row is None:
            return
        # One reason per line. Joined with separators they were a paragraph
        # that elided away at exactly the width where a refusal has three of
        # them and the reader most needs to see all three.
        lines = [f"{row.run_id} · {'Hazır' if row.accepted else 'Dışarıda'}"]
        lines.extend(row.reasons or ())
        lines.extend(row.detail or ())
        self.detail.setText("\n".join(line for line in lines if line))


__all__ = ["ExportPage"]
