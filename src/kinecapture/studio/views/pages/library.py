"""İşlenen Videolar: the library of finished versions.

A list on the left, the selected version's details on the right, and - when a
take has more than one finished version - those versions side by side, so the
question "did BODY_38 actually do better here?" can be answered by looking.

Preview images are read from disk. Nothing on this screen decodes video, which
is what keeps a long list scrolling smoothly.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.formatting import local_datetime, timezone_note
from kinecapture.studio.services.library import VersionRow
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from ..models import ROW_ROLE, Column, RowTableModel, SearchProxy, configure_columns
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: Cover image size in the detail panel. Small on purpose: this is a glance,
#: not a viewer.
_COVER_WIDTH = 240


def _columns() -> tuple[Column[VersionRow], ...]:
    return (
        # The row names what a person recognises: who, when, and which take.
        # The run_/take_ identifiers live in the detail panel and the tooltip.
        Column(
            "participant",
            "Katılımcı",
            lambda r: r.participant_id,
            tooltip=lambda r: f"{r.take_id}\n{r.run_id}",
        ),
        Column(
            "started",
            "Tarih",
            lambda r: local_datetime(r.started_at),
            sort_key=lambda r: r.started_at,
            tooltip=lambda r: timezone_note(r.started_at),
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
            "frames", "Kare", lambda r: str(r.frames), sort_key=lambda r: r.frames, numeric=True
        ),
        Column("model", "Model", lambda r: r.model_text),
        Column(
            "quality",
            "Durum",
            lambda r: r.quality_text,
            status=lambda r: r.quality_status,
            tooltip=lambda r: " · ".join(r.issues) or r.quality_text,
        ),
        Column(
            "versions",
            "Sürüm",
            lambda r: (f"{r.sibling_versions} sürüm" if r.sibling_versions > 1 else "tek"),
            sort_key=lambda r: r.sibling_versions,
            numeric=True,
        ),
        Column(
            "annotated",
            "Etiket",
            lambda r: "var" if r.annotated else "—",
            status=lambda r: "live" if r.annotated else "",
        ),
    )


class _VersionCard(QWidget):
    """One version in the comparison strip: cover, model, coverage."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.metric("KcSpacingXs"))
        self.cover = label("")
        self.cover.setMinimumSize(QSize(160, 90))
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = ElidedLabel("")
        self.model = mono_label("")
        self.quality = label("", role="sectionTitle")
        layout.addWidget(self.cover)
        layout.addWidget(self.title)
        layout.addWidget(self.model)
        layout.addWidget(self.quality)
        layout.addStretch(1)

    def show_row(self, row: VersionRow, width: int) -> None:
        path = row.thumbnail()
        if path is not None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.cover.setPixmap(
                    pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
                )
            else:
                self.cover.setText("önizleme okunamadı")
        else:
            self.cover.setText("önizleme yok")
        self.title.setText(row.run_id)
        self.model.setText(f"{row.model_text} · {row.frames} kare")
        self.quality.setText(row.quality_text)
        self.quality.setProperty("kcStatus", row.quality_status)
        style = self.quality.style()
        style.unpolish(self.quality)
        style.polish(self.quality)
        self.setToolTip(" · ".join(row.issues) or "Bulgu yok")


class LibraryPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[LibraryViewModel] = None

        top = QHBoxLayout()
        top.setSpacing(tokens.metric("KcSpacingMd"))
        self.filter_box = QComboBox()
        self.filter_box.setAccessibleName("Sürüm filtresi")
        self.filter_box.setToolTip("Listeyi duruma göre daraltır")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Katılımcı, tarih veya model ara")
        self.search.setMaximumWidth(360)
        self.search.setClearButtonEnabled(True)
        self.label_button = QPushButton("Etiketle")
        self.label_button.setProperty("kcVariant", "primary")
        self.label_button.setEnabled(False)
        self.recompute_button = QPushButton("Yeni sürüm hesapla")
        self.recompute_button.setToolTip(
            "Bu kaydı şu anki ayarlarla yeniden işler. Mevcut sürüm silinmez."
        )
        self.recompute_button.setEnabled(False)
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setProperty("kcVariant", "quiet")
        top.addWidget(self.filter_box)
        top.addWidget(self.search)
        top.addStretch(1)
        top.addWidget(self.recompute_button)
        top.addWidget(self.label_button)
        top.addWidget(self.refresh_button)
        self.body_layout.addLayout(top)

        self.summary = ElidedLabel("")
        self.summary.setProperty("kcRole", "sectionTitle")
        self.body_layout.addWidget(self.summary)
        self.body_layout.addWidget(separator())

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        self.model = RowTableModel(_columns(), self)
        self.proxy = SearchProxy(self)
        self.proxy.setSourceModel(self.model)
        self.view = QTableView(self)
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.verticalHeader().setVisible(False)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        # Every column here holds a fixed-length value, so none of them
        # is stretched and the remaining width stays empty.
        configure_columns(self.view, _columns(), fill=False)
        self.view.setAccessibleName("İşlenmiş sürümler")
        splitter.addWidget(self.view)
        splitter.addWidget(self._build_detail(tokens))
        # The list is the library; the panel is one item's detail. It has a
        # floor so it stays readable and a ceiling so it stops eating the list.
        splitter.setSizes([1180, 420])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.body_layout.addWidget(splitter, 1)

        self.filter_box.currentIndexChanged.connect(self._filter_chosen)
        self.search.textChanged.connect(self.proxy.set_search)
        self.refresh_button.clicked.connect(self._refresh)
        self.label_button.clicked.connect(self._label)
        self.recompute_button.clicked.connect(self._recompute)
        self.view.selectionModel().selectionChanged.connect(self._selection_changed)
        self.view.doubleClicked.connect(lambda _index: self._label())

    def _build_detail(self, tokens: ThemeTokens) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(tokens.metric("KcSpacingLg"), 0, 0, 0)
        layout.setSpacing(tokens.metric("KcSpacingMd"))

        layout.addWidget(label("SEÇİLİ SÜRÜM", role="sectionTitle"))
        self.detail_cover = label("")
        self.detail_cover.setMinimumSize(QSize(_COVER_WIDTH, 135))
        self.detail_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_cover)

        self.detail_title = ElidedLabel("Bir sürüm seçin")
        self.detail_lines = mono_label("")
        self.detail_lines.setWordWrap(True)
        self.detail_issues = label("", role="fieldError")
        self.detail_issues.setWordWrap(True)
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_lines)
        layout.addWidget(self.detail_issues)

        layout.addWidget(separator())
        self.compare_caption = label("AYNI KAYDIN SÜRÜMLERİ", role="sectionTitle")
        layout.addWidget(self.compare_caption)
        self.compare_holder = QWidget(panel)
        self.compare_layout = QHBoxLayout(self.compare_holder)
        self.compare_layout.setContentsMargins(0, 0, 0, 0)
        self.compare_layout.setSpacing(tokens.metric("KcSpacingMd"))
        layout.addWidget(self.compare_holder)
        layout.addStretch(1)
        return panel

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: LibraryViewModel) -> None:
        self.viewmodel = viewmodel
        for key, caption in viewmodel.filters:
            self.filter_box.addItem(caption, key)
        self.bind(viewmodel.rows, self.model.set_rows)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.selected, self._show_selected)
        self.bind(viewmodel.comparison, self._show_comparison)
        self.bind(viewmodel.busy, lambda busy: self.refresh_button.setEnabled(not busy))
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.reload()

    # ----------------------------------------------------------------- slots
    def _filter_chosen(self, _index: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_filter(self.filter_box.currentData())

    def _refresh(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.reload(force=True)

    def _selection_changed(self, *_args) -> None:
        rows = self.view.selectionModel().selectedRows()
        row = rows[0].data(ROW_ROLE) if rows else None
        if self.viewmodel is not None:
            self.viewmodel.select(row)

    def _recompute(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.recompute()

    def _show_selected(self, row: Optional[VersionRow]) -> None:
        self.label_button.setEnabled(row is not None)
        self.recompute_button.setEnabled(row is not None)
        if row is not None and not row.subject_chosen and self.viewmodel is not None:
            # Said once per selection, with the only repair that actually works.
            self.show_message(self.viewmodel.subject_recovery_message(row))
        if row is None:
            self.detail_title.setText("Bir sürüm seçin")
            self.detail_lines.setText("")
            self.detail_issues.setText("")
            self.detail_issues.hide()
            self.detail_cover.setText("")
            self.detail_cover.setPixmap(QPixmap())
            return
        path = row.thumbnail()
        if path is not None:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.detail_cover.setPixmap(
                    pixmap.scaledToWidth(
                        _COVER_WIDTH, Qt.TransformationMode.SmoothTransformation
                    )
                )
            else:
                self.detail_cover.setText("önizleme okunamadı")
        else:
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("önizleme yok")

        self.detail_title.setText(f"{row.participant_id} · {row.run_id}")
        parameters = self.viewmodel.parameters(row) if self.viewmodel else {}
        lines = [
            f"kare        {row.frames}",
            f"model       {row.model_text}",
            f"derinlik    {parameters.get('depth_mode', '—')}",
            f"fitting     {'açık' if parameters.get('body_fitting') else 'kapalı'}",
            f"şema        {row.schema_version or '—'}",
            f"kişi        {'seçildi' if row.subject_chosen else 'seçilmedi'}",
            f"derinlik dosyası {'var' if row.has_depth else 'yok'}",
        ]
        self.detail_lines.setText("\n".join(lines))
        if row.issues:
            from kinecapture.studio.services.processing import describe_issue

            self.detail_issues.setText(
                "\n".join(describe_issue(code) for code in row.issues)
            )
            self.detail_issues.show()
        else:
            self.detail_issues.hide()

    def _show_comparison(self, rows: tuple[VersionRow, ...]) -> None:
        while self.compare_layout.count():
            item = self.compare_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        # Only shown when there is genuinely something to compare.
        visible = len(rows) > 1
        self.compare_caption.setVisible(visible)
        self.compare_holder.setVisible(visible)
        if not visible:
            return
        for row in rows:
            card = _VersionCard(self._tokens, self.compare_holder)
            card.show_row(row, 150)
            self.compare_layout.addWidget(card)

    def inspector_sections(self) -> tuple:
        """The selected version: what it is, and what produced it."""
        from kinecapture.studio.services.inspectors import Row, Section

        row = self.viewmodel.selected.value if self.viewmodel else None
        if row is None:
            return ()
        parameters = self.viewmodel.parameters(row)
        return (
            Section(
                "Sürüm",
                (
                    Row("Katılımcı", row.participant_id),
                    Row(
                        "Tarih",
                        local_datetime(row.started_at),
                        detail=timezone_note(row.started_at),
                    ),
                    Row("Kare", str(row.frames)),
                    Row("Model", row.model_text),
                    Row(
                        "Durum",
                        row.quality_text,
                        level={"live": "ready", "warning": "warning"}.get(
                            row.quality_status, "neutral"
                        ),
                        detail=" · ".join(row.issues),
                    ),
                    Row("Etiket", "var" if row.annotated else "yok"),
                ),
            ),
            Section(
                "Kimlikler",
                (
                    Row("Kayıt", row.take_id),
                    Row("Sürüm", row.run_id),
                    Row("Klasör", row.directory, detail=row.directory),
                ),
                note="Ayrıntılar ve kopyalama için; satırlarda kısaltılır.",
            ),
            Section(
                "Üretim ayarları",
                (
                    Row("Şema", row.schema_version or "—"),
                    Row("Derinlik", str(parameters.get("depth_mode", "—"))),
                    Row(
                        "Fitting",
                        "açık" if parameters.get("body_fitting") else "kapalı",
                    ),
                    Row("Derinlik dosyası", "var" if row.has_depth else "yok"),
                ),
            ),
        )

    def _label(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.label()


__all__ = ["LibraryPage"]
