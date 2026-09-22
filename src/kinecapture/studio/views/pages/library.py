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
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.formatting import (
    MISSING,
    file_size,
    local_datetime,
    timezone_note,
)
from kinecapture.studio.services.library import VersionRow
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.library import LibraryViewModel
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
from ..models import ROW_ROLE, Column, RowTableModel, SearchProxy, configure_columns
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: Cover image width in the detail panel. Larger than it was: the preview is
#: how a version is recognised, and at 240 px a squat and a lunge looked the
#: same. Still a still image - nothing on this screen decodes video.
_COVER_WIDTH = 420

#: The list's share of the screen at rest. The rest goes to the preview and
#: the version's details, which is the approved 55/45.
_LIST_SHARE = 0.55


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
            # Which of the take's versions this row is. The rows are grouped
            # by take, so "2 / 3" reads down the group and says at a glance
            # that there is something to compare.
            "versions",
            "Sürüm",
            lambda r: (
                f"{r.version_ordinal} / {r.sibling_versions}"
                if r.sibling_versions > 1
                else "tek"
            ),
            sort_key=lambda r: (r.take_id, r.version_ordinal),
            tooltip=lambda r: (
                f"Bu kaydın {r.sibling_versions} işleme sürümü var."
                if r.sibling_versions > 1
                else "Bu kaydın tek işleme sürümü var."
            ),
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
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Sürümlerde ara")
        self.search.addAction(
            iconset.icon("search", tokens, size=tokens.metric("KcIconSize")),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        # Wide enough to read the placeholder whole - it was showing
        # "Katılımcı, tarih v…", which explains nothing - and no wider.
        hint = QFontMetrics(self.search.font()).horizontalAdvance(
            self.search.placeholderText()
        )
        self.search.setMinimumWidth(min(480, hint + 96))
        self.search.setMaximumWidth(480)
        self.label_button = QPushButton("Etiketle")
        self.label_button.setProperty("kcVariant", "primary")
        self.label_button.setEnabled(False)
        self.recompute_button = QPushButton("Yeni sürüm hesapla")
        self.recompute_button.setToolTip(
            "Bu kaydı şu anki ayarlarla yeniden işler. Mevcut sürüm silinmez."
        )
        self.recompute_button.setEnabled(False)
        # One button family across the row, as on Projeler: "quiet" draws
        # neither a surface nor a border, so beside two real buttons it read
        # as a word somebody had left there.
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setIcon(
            iconset.icon("refresh", tokens, size=tokens.metric("KcIconSize"))
        )
        self.refresh_button.setToolTip("Sürüm listesini diskten yeniden okur.")
        for control in (
            self.filter_box,
            self.search,
            self.recompute_button,
            self.label_button,
            self.refresh_button,
        ):
            control.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
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
        # The list is the library; the panel is one item's detail. The preview
        # in the panel is how a version is recognised, so it gets real room:
        # the approved split is 55/45, applied once the page has a width.
        splitter.setStretchFactor(0, 55)
        splitter.setStretchFactor(1, 45)
        self.splitter = splitter
        # Held until the user takes hold of the handle. Applying it once, on
        # the first layout, set it against a width the window did not have yet
        # and left the list at 39% instead of 55%.
        self._split_pinned = True
        splitter.splitterMoved.connect(lambda *_: setattr(self, "_split_pinned", False))
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
        # The preview keeps the source's own aspect ratio. A cover box with a
        # fixed 16:9 hole in it would letterbox a 4:3 capture into grey bars
        # and crop a portrait one, and the aspect is the first thing that says
        # which camera a version came from.
        self.detail_cover = label("")
        self.detail_cover.setMinimumHeight(160)
        self.detail_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_cover.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.detail_cover)

        self.detail_title = ElidedLabel("Bir sürüm seçin")
        self.detail_lines = mono_label("")
        self.detail_lines.setWordWrap(True)
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_lines)

        # Findings as a line plus a fold. The summary is enough to decide
        # whether to look; the list is there when the answer is yes. Nothing
        # is dropped - the count is of the same issues the fold contains.
        issues_row = QHBoxLayout()
        issues_row.setSpacing(tokens.metric("KcSpacingSm"))
        self.detail_issue_summary = ElidedLabel("")
        self.detail_issue_summary.setProperty("kcRole", "pageSubtitle")
        issues_row.addWidget(self.detail_issue_summary, 1)
        self.detail_issue_button = QPushButton("Ayrıntılar")
        self.detail_issue_button.setProperty("kcVariant", "quiet")
        self.detail_issue_button.setCheckable(True)
        self.detail_issue_button.toggled.connect(
            lambda shown: self.detail_issues.setVisible(shown)
        )
        issues_row.addWidget(self.detail_issue_button)
        self.issues_row_holder = QWidget(panel)
        self.issues_row_holder.setLayout(issues_row)
        layout.addWidget(self.issues_row_holder)
        self.detail_issues = label("", role="fieldError")
        self.detail_issues.setWordWrap(True)
        self.detail_issues.hide()
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

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._apply_split_ratio()
        self._redraw_cover()

    def _apply_split_ratio(self) -> None:
        """Hold the approved ratio through resizes, until the user overrides it."""
        if not self._split_pinned:
            return
        width = self.splitter.width()
        if width <= 0:
            return
        listed = int(width * _LIST_SHARE)
        sizes = self.splitter.sizes()
        if sizes and abs(sizes[0] - listed) <= 1:
            return
        self.splitter.setSizes([listed, width - listed])

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: LibraryViewModel) -> None:
        self.viewmodel = viewmodel
        for key, caption in viewmodel.filters:
            self.filter_box.addItem(caption, key)
        self.bind(viewmodel.rows, self.model.set_rows)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.selected, self._show_selected)
        self.bind(viewmodel.comparison, self._show_comparison)
        self.bind(viewmodel.selected_sizes, self._show_sizes)
        self.bind(viewmodel.busy, lambda busy: self.refresh_button.setEnabled(not busy))
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        self._apply_split_ratio()
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
        self._cover_path = None
        if row is None:
            self.detail_title.setText("Bir sürüm seçin")
            self.detail_lines.setText("")
            self.detail_issue_summary.setText("")
            self.issues_row_holder.hide()
            self.detail_issues.setText("")
            self.detail_issues.hide()
            self.detail_cover.setText("")
            self.detail_cover.setPixmap(QPixmap())
            return

        self._cover_path = row.thumbnail()
        self._redraw_cover()

        version = (
            f"sürüm {row.version_ordinal} / {row.sibling_versions}"
            if row.sibling_versions > 1
            else "tek sürüm"
        )
        self.detail_title.setText(f"{row.participant_id} · {version}")
        self.detail_title.setToolTip(f"{row.take_id}\n{row.run_id}")
        self._fill_lines(row)

        findings = tuple(row.issues)
        if findings:
            from kinecapture.studio.services.processing import describe_issue

            self.detail_issue_summary.setText(
                f"{len(findings)} bulgu: {describe_issue(findings[0])}"
                if len(findings) > 1
                else describe_issue(findings[0])
            )
            self.detail_issues.setText(
                "\n".join(describe_issue(code) for code in findings)
            )
            self.issues_row_holder.show()
            self.detail_issues.setVisible(self.detail_issue_button.isChecked())
        else:
            self.detail_issue_summary.setText("")
            self.issues_row_holder.hide()
            self.detail_issues.setText("")
            self.detail_issues.hide()

    def _fill_lines(self, row: VersionRow) -> None:
        """Everything about the version, in one block of aligned pairs."""
        parameters = self.viewmodel.parameters(row) if self.viewmodel else {}
        run_id, derived, raw = (
            self.viewmodel.selected_sizes.value if self.viewmodel else ("", None, None)
        )
        # Sizes only when they belong to *this* version. A measurement still in
        # flight leaves the two lines saying "ölçülüyor…", never the previous
        # version's numbers.
        measuring = run_id != row.run_id
        lines = [
            ("tarih", local_datetime(row.started_at)),
            ("süre", f"{row.duration_s:.0f} sn"),
            ("kare", str(row.frames)),
            ("model", row.model_text),
            ("derinlik", str(parameters.get("depth_mode", MISSING))),
            ("fitting", "açık" if parameters.get("body_fitting") else "kapalı"),
            ("şema", row.schema_version or MISSING),
            # The two sizes are never added together and never shared. The raw
            # recording belongs to the take; counting it once per version would
            # treble a 2 GB SVO for a take processed three ways.
            ("sürüm boyutu", "ölçülüyor…" if measuring else file_size(derived)),
            ("ham kayıt", "ölçülüyor…" if measuring else file_size(raw)),
            ("sporcu", "seçildi" if row.subject_chosen else "seçilmedi"),
            ("etiket", "var" if row.annotated else "yok"),
            ("derinlik dosyası", "var" if row.has_depth else "yok"),
        ]
        width = max(len(name) for name, _value in lines)
        self.detail_lines.setText(
            "\n".join(f"{name:<{width}}  {value}" for name, value in lines)
        )

    def _show_sizes(self, _sizes) -> None:  # noqa: ANN001
        """A measurement arrived. Only the size lines change."""
        row = self.viewmodel.selected.value if self.viewmodel else None
        if row is not None:
            self._fill_lines(row)

    def _redraw_cover(self) -> None:
        """Draw the still at the panel's width, keeping the source's aspect."""
        path = getattr(self, "_cover_path", None)
        if path is None:
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("önizleme yok")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("önizleme okunamadı")
            return
        width = max(160, min(_COVER_WIDTH, self.detail_cover.width()))
        scaled = pixmap.scaled(
            width,
            # Tall enough that the ratio, not the box, decides the height.
            width * 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.detail_cover.setText("")
        self.detail_cover.setPixmap(scaled)
        self.detail_cover.setFixedHeight(scaled.height())

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
