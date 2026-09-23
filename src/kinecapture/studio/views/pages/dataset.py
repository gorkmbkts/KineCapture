"""Veri Seti: what the project holds, as a list and as a shape.

Two halves, and they answer different questions.

**Left: which recordings.** The list, its search, and what the selected one
is still waiting on. Narrower than it was - seven short columns never needed
two thirds of a 1900-pixel window - with its own toolbar above it so the two
things somebody does here, refresh and open, are at the top of the thing they
act on.

**Right: what the dataset looks like.** Readiness, the distribution of
movement classes and of fault classes, and coverage per participant. Asked
for on 22 September: the screen listed rows and said nothing about the set
they form, which is the question somebody actually has before an export.

The charts are drawn from *the rows on screen*, so narrowing the list with
the search box or the filter narrows the charts with it - and what a chart
says can never disagree with what the table shows.

A list, not a verdict. The expensive authoritative check lives in Dışa
Aktarım; this screen reads sidecars and says what it sees, which is why its
wording is "hazır görünüyor" rather than "hazır".
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens, class_colour_token
from kinecapture.studio.viewmodels.dataset import (
    BLOCKER_TEXT,
    UNCLASSED,
    DatasetRow,
    DatasetViewModel,
    aggregate,
)
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
from ..charts import BarRows, Proportion
from ..models import ROW_ROLE, Column, RowTableModel, SearchProxy
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
        #: One scheduled chart refresh at a time. See :meth:`_refresh_stats`.
        self._stats_pending = False

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
        # "Etiketlemede aç" used to live at the foot of the right-hand
        # panel, which is now the dataset's own overview and has nothing to do
        # with one selected row. Both actions belong over the list they act
        # on, and the 22 September request puts them here.
        self.open_button = QPushButton("Etiketlemede aç")
        self.open_button.setProperty("kcVariant", "primary")
        self.open_button.setEnabled(False)
        self.open_button.setToolTip(
            "Seçili sürümü Etiketleme ekranında açar."
        )
        self.open_button.clicked.connect(self._open_selected)
        for control in (
            self.search,
            self.filter_box,
            self.refresh_button,
            self.open_button,
        ):
            control.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        bar.addStretch(1)
        bar.addWidget(self.open_button)
        bar.addWidget(self.refresh_button)

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
        split.addWidget(self._build_list(bar))
        split.addWidget(self._build_stats())
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        self.split = split
        self._split_pinned = False
        split.splitterMoved.connect(lambda *_a: setattr(self, "_split_pinned", True))
        self.body_layout.addWidget(split, 1)

        self.totals = ElidedLabel("—")
        self.totals.setProperty("kcRole", "contextValue")
        self.body_layout.addWidget(self.totals)
        self.table.selectionModel().selectionChanged.connect(self._show_detail)
        # Settle the empty state once, rather than waiting for a selection
        # that may never come: an unselected screen has to look deliberate.
        self._show_detail()

    #: How much of the width the list keeps. Seven short columns; the part
    #: that grows with the project is the overview beside it, not this.
    _LIST_SHARE = 0.52

    def _build_list(self, bar) -> QWidget:  # noqa: ANN001 - QHBoxLayout
        """The left half: its own toolbar, the table, and what one row needs."""
        tokens = self._tokens
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, tokens.metric("KcSpacingLg"), 0)
        column.setSpacing(tokens.metric("KcSpacingMd"))
        column.addLayout(bar)
        column.addWidget(self.table, 1)
        column.addWidget(separator())
        column.addWidget(self._build_detail(panel))
        return panel

    def _build_detail(self, parent: QWidget) -> QWidget:
        """What the selected record is waiting on, and how to go and fix it.

        Under the list rather than beside it. It is about *one row*, so it
        belongs with the rows; the space it used to occupy is now the
        dataset's own overview, which is about all of them.
        """
        tokens = self._tokens
        panel = QWidget(parent)
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        head = QHBoxLayout()
        head.setSpacing(tokens.metric("KcSpacingMd"))
        head.addWidget(label("SEÇİLİ KAYIT", role="sectionTitle"))
        self.detail_title = ElidedLabel("Bir kayıt seçin.")
        self.detail_title.setProperty("kcRole", "contextValue")
        head.addWidget(self.detail_title, 1)
        column.addLayout(head)

        self.detail_lines = QLabel("")
        self.detail_lines.setWordWrap(True)
        self.detail_lines.setProperty("kcRole", "pageSubtitle")
        self.detail_lines.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        column.addWidget(self.detail_lines)

        self.blocker_caption = label("BEKLEYEN", role="sectionTitle")
        column.addWidget(self.blocker_caption)
        self.blocker_holder = QWidget(panel)
        self._blocker_layout = QVBoxLayout(self.blocker_holder)
        self._blocker_layout.setContentsMargins(0, 0, 0, 0)
        self._blocker_layout.setSpacing(tokens.metric("KcSpacingXs"))
        column.addWidget(self.blocker_holder)
        return panel

    # ---------------------------------------------------------- the overview
    def _stat_block(self, column, title: str, note: str, chart) -> None:  # noqa: ANN001
        """One titled block of the overview, in the list's own language.

        Same caption role, same rules, same rhythm as the panel across the
        splitter - the two halves have to read as one screen.
        """
        tokens = self._tokens
        if column.count():
            # A share of the column's spare height, between the blocks rather
            # than in one lump under the last one - the same thing the
            # Yakalama console does, and for the same reason: a column beside
            # a full-height table that stops two thirds of the way down reads
            # as unfinished. Bounded in :meth:`_spread_stats`: an unbounded
            # stretch put a hundred and fifty pixels between a chart and its
            # neighbour and the four blocks stopped reading as one panel.
            spacer = QSpacerItem(
                0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
            column.addSpacerItem(spacer)
            self._stat_gaps.append(spacer)
            column.addWidget(separator())
        column.addWidget(label(title, role="sectionTitle"))
        if note:
            caption = ElidedLabel(note)
            caption.setProperty("kcRole", "pageSubtitle")
            caption.setToolTip(note)
            column.addWidget(caption)
        column.addWidget(chart)
        del tokens

    def _build_stats(self) -> QWidget:
        """The right half: what this dataset looks like, in four numbers."""
        tokens = self._tokens
        panel = QWidget()
        panel.setMinimumWidth(tokens.metric("KcLabelPanelMinWidth"))
        column = QVBoxLayout(panel)
        column.setContentsMargins(tokens.metric("KcSpacingLg"), 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingMd"))
        #: One per gap between two blocks, sized once the column has a height.
        self._stat_gaps: list[QSpacerItem] = []
        self._stat_column = column

        self.readiness_chart = Proportion(tokens, panel)
        self._stat_block(
            column,
            "HAZIRLIK DURUMU",
            "Listedeki sürümlerin kaçı hazır görünüyor.",
            self.readiness_chart,
        )

        self.exercise_chart = BarRows(tokens, panel)
        self._stat_block(
            column,
            "HAREKET SINIFI DAĞILIMI",
            "Etiketlenmiş tekrar sayısı. Veri setinin dışında tutulanlar sayılmaz.",
            self.exercise_chart,
        )

        self.error_chart = BarRows(tokens, panel)
        self._stat_block(
            column,
            "HATA SINIFI DAĞILIMI",
            "İşaretlenmiş hata aralığı sayısı.",
            self.error_chart,
        )

        self.coverage_chart = BarRows(tokens, panel)
        self.coverage_chart.set_empty_text("Henüz kayıt yok.")
        self._stat_block(
            column,
            "KATILIMCI BAŞINA KAPSAM",
            "Her katılımcıda kaç hareket etiketlendi.",
            self.coverage_chart,
        )
        self.coverage_note = ElidedLabel("")
        self.coverage_note.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.coverage_note)

        column.addStretch(1)
        return panel

    #: The most a gap between two overview blocks may grow. Past this the four
    #: stop reading as one panel and start reading as four loose cards.
    STAT_GAP_MAX = 28

    def _spread_stats(self) -> None:
        """Share the overview column's spare height between its blocks."""
        gaps = getattr(self, "_stat_gaps", None)
        if not gaps:
            return
        column = self._stat_column
        for spacer in gaps:
            spacer.changeSize(
                0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
        column.invalidate()
        column.activate()
        packed = column.minimumSize().height()
        spare = max(0, column.geometry().height() - packed)
        extra = min(self.STAT_GAP_MAX, spare // len(gaps))
        if extra <= 0:
            return
        for spacer in gaps:
            spacer.changeSize(
                0, extra, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
        column.invalidate()

    def _show_stats(self) -> None:
        """Re-draw the four charts from the rows the list is showing.

        From the *filtered* rows, so searching or filtering narrows the
        overview with the list. Reading them off the proxy rather than the
        viewmodel is what keeps the two halves from ever disagreeing.
        """
        rows = [
            self.proxy.index(position, 0).data(ROW_ROLE)
            for position in range(self.proxy.rowCount())
        ]
        stats = aggregate([row for row in rows if row is not None])

        self.readiness_chart.set_parts(
            (
                ("hazır görünüyor", stats.ready, "KcStatusLive"),
                ("bir şey bekliyor", stats.blocked, "KcStatusWarning"),
                ("etiketlenmemiş", stats.unlabelled, "KcTextMuted"),
            )
        )
        for chart, counts, fault in (
            (self.exercise_chart, stats.exercises, False),
            (self.error_chart, stats.errors, True),
        ):
            chart.set_rows(
                [
                    (
                        stats.label_for(code),
                        count,
                        "KcTextMuted"
                        if code == UNCLASSED
                        else class_colour_token(
                            max(0, stats.order_of(code)), fault=fault
                        ),
                    )
                    for code, count in stats.ranked(counts)
                ]
            )
        self.coverage_chart.set_rows(
            [
                (name, values[1], "KcAccentPrimary")
                for name, values in sorted(
                    stats.participants.items(), key=lambda p: -p[1][1]
                )
            ]
        )
        minutes = sum(v[2] for v in stats.participants.values()) / 60.0
        versions = sum(v[0] for v in stats.participants.values())
        self.coverage_note.setText(
            f"{len(stats.participants)} katılımcı · {versions} sürüm · "
            f"{minutes:.1f} dk"
            if stats.participants
            else ""
        )

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
        self._spread_stats()

    def apply_tokens(self, tokens: ThemeTokens) -> None:
        super().apply_tokens(tokens)
        for chart in (
            getattr(self, "readiness_chart", None),
            getattr(self, "exercise_chart", None),
            getattr(self, "error_chart", None),
            getattr(self, "coverage_chart", None),
        ):
            if chart is not None:
                chart.set_tokens(tokens)

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
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        """Called wherever the visible set changes: new rows, search, filter.

        Scheduled rather than run on the spot. ``SearchProxy.set_search``
        invalidates the proxy, and a proxy that has just been invalidated
        reports no rows until it has re-filtered - so reading it inside the
        same call gave an empty chart beside a table with rows in it, which is
        precisely the disagreement these charts exist not to have. Repeated
        calls coalesce into one pass.
        """
        if not hasattr(self, "readiness_chart") or self._stats_pending:
            return
        self._stats_pending = True
        QTimer.singleShot(0, self._run_refresh_stats)

    def _run_refresh_stats(self) -> None:
        self._stats_pending = False
        if hasattr(self, "readiness_chart"):
            self._show_stats()
            self._spread_stats()

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
        # A caption with nothing under it is a heading for no content.
        self.blocker_caption.setVisible(row is not None)
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
        self._refresh_stats()


__all__ = ["DatasetPage", "FILTERS"]
