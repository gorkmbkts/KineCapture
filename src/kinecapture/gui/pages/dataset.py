"""Dataset screen: composition, filters and quality assurance."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QSplitter,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.dataset.index import DatasetQuery, TakeRow
from kinecapture.domain.enums import (
    Correctness,
    DataOrigin,
    SampleReadiness,
    TakeState,
)
from kinecapture.domain.labels import LabelSchema
from kinecapture.gui.pages.base import Page, scrollable
from kinecapture.gui.pages.dashboard import format_duration
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.flow_layout import flow_row
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    MetricTile,
    StatusChip,
    make_button,
    make_label,
)
from kinecapture.gui.widgets.timeline import error_class_colour

_ANY = "__any__"

_SEVERITY_LABELS = {
    "blocked": ("Engel", "error"),
    "warning": ("Uyarı", "warning"),
    "info": ("Bilgi", "info"),
}

#: Short Turkish name for each readiness state, used in the filter and tiles.
_READINESS_LABELS = {
    SampleReadiness.READY: "Hazır",
    SampleReadiness.UNLABELLED: "Etiketlenmedi",
    SampleReadiness.NEEDS_ERROR_INTERVAL: "Hata aralığı bekliyor",
    SampleReadiness.CONTRADICTION: "Çelişki",
    SampleReadiness.INVALID_INTERVAL: "Geçersiz aralık",
    SampleReadiness.LEGACY_CONFLICT: "Eski karar çelişkisi",
    SampleReadiness.EXCLUDED: "Dışlandı",
}


def _readiness_detail(counts: dict[str, int]) -> str:
    """Why the unready samples are unready, most common reason first."""
    parts = []
    for state in (
        SampleReadiness.LEGACY_CONFLICT,
        SampleReadiness.NEEDS_ERROR_INTERVAL,
        SampleReadiness.UNLABELLED,
        SampleReadiness.CONTRADICTION,
        SampleReadiness.INVALID_INTERVAL,
    ):
        count = counts.get(state.value, 0)
        if count:
            parts.append(f"{count} {_READINESS_LABELS[state].lower()}")
    return " · ".join(parts)


class DistributionBar(QWidget):
    """A one-line stacked bar for a categorical distribution.

    Every segment is labelled with its category and count, so the chart is
    readable without relying on colour alone.
    """

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(theme.space_xs)
        self._rows: list[QWidget] = []

    def set_distribution(
        self, counts: dict[str, int], *, colours: Optional[dict[str, str]] = None
    ) -> None:
        for row in self._rows:
            row.setParent(None)
        self._rows.clear()

        total = sum(counts.values())
        if not total:
            label = make_label("Veri yok", role="muted")
            self._layout.addWidget(label)
            self._rows.append(label)
            return

        theme = self._theme
        for key, count in sorted(counts.items(), key=lambda item: -item[1]):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(theme.space_sm)

            name = make_label(key, role="muted")
            # Wide enough to read a class name, not so wide that a long
            # Turkish label sets the distribution card's minimum width.
            name.setMinimumWidth(96)
            name.setMaximumWidth(200)
            layout.addWidget(name)

            share = count / total
            bar = QWidget()
            bar.setFixedHeight(10)
            colour = (colours or {}).get(key, theme.accent)
            bar.setStyleSheet(
                f"background-color: {colour}; border-radius: 5px;"
            )
            bar.setMinimumWidth(max(4, min(160, int(share * 240))))
            bar.setMaximumWidth(max(4, int(share * 240)))
            layout.addWidget(bar)

            value = make_label(f"{count}  (%{share * 100:.0f})")
            layout.addWidget(value)
            layout.addStretch(1)

            self._layout.addWidget(row)
            self._rows.append(row)

    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme


class DatasetPage(Page):
    """Composition, filters, take table and QA findings."""

    navigate_requested = Signal(str)

    title = "Dataset"
    description = "Veri kümesinin bileşimi, filtreler ve kalite bulguları."
    icon = "dataset"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme

        refresh = make_button("Yenile", icon="refresh", theme=theme)
        refresh.clicked.connect(lambda: self._reload(force=True))
        self.header.add_action(refresh)

        export_button = make_button(
            "Export ekranı", variant="primary", icon="export", theme=theme
        )
        export_button.clicked.connect(lambda: self.navigate_requested.emit("export"))
        self.header.add_action(export_button)

        self._empty = EmptyState(
            "Önce bir proje açın",
            "Dataset özeti açık projeye aittir.",
            theme=theme,
            icon="project",
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.space_md)
        body.addWidget(self._build_filters(theme))
        body.addWidget(self._build_metrics(theme))

        # A splitter, not a fixed pair: the table and the analysis column are
        # both useful at full width and neither has to keep the other's
        # minimum. Fixed side-by-side made the page 1643px wide at minimum,
        # which is a horizontal scrollbar on every supported screen.
        columns = QSplitter(Qt.Orientation.Horizontal)
        columns.setChildrenCollapsible(False)
        columns.addWidget(self._build_table(theme))
        columns.addWidget(self._build_analysis(theme))
        columns.setStretchFactor(0, 3)
        columns.setStretchFactor(1, 2)
        columns.setSizes([700, 420])
        body.addWidget(columns, 1)
        # Filters, twelve metric tiles, a table and an analysis column do not
        # fit in 606px however they are arranged. A browsing page may scroll
        # vertically - what it may not do is clip the bottom card away.
        self._scroll = scrollable(self._body)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content.addWidget(self._scroll, 1)

        state.project_changed.connect(lambda _: self._reload(force=True))
        state.dataset_changed.connect(self._reload)
        self._set_empty(True)

    # --------------------------------------------------------------- layout
    def _build_filters(self, theme: Theme) -> QWidget:
        """Eight filters that wrap onto a second line instead of clipping.

        In a fixed row they set a 1495px minimum width all on their own, which
        put a horizontal scrollbar under every screen this app supports - and
        the filter most likely to be scrolled off was the last one added.
        """
        card = Card("Filtreler", theme=theme, icon="search")
        cells: list[QWidget] = []

        def add(label: str) -> QComboBox:
            column = QVBoxLayout()
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(2)
            column.addWidget(make_label(label, role="caption"))
            selector = QComboBox()
            selector.setMinimumWidth(120)
            selector.setMaximumWidth(190)
            selector.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            selector.setMinimumContentsLength(10)
            selector.currentIndexChanged.connect(self._apply_filters)
            column.addWidget(selector)
            container = QWidget()
            container.setLayout(column)
            cells.append(container)
            return selector

        self._participant_filter = add("Katılımcı")
        self._session_filter = add("Oturum")
        self._exercise_filter = add("Egzersiz")
        self._correctness_filter = add("Değerlendirme")
        self._readiness_filter = add("Etiket durumu")
        self._error_filter = add("Hata türü")
        self._state_filter = add("Kayıt durumu")
        self._origin_filter = add("Kaynak")

        clear = make_button("Temizle", icon="close", theme=theme)
        clear.clicked.connect(self._clear_filters)
        cells.append(clear)

        self._filter_chip = StatusChip("Tümü", theme=theme, icon="list")
        cells.append(self._filter_chip)

        card.add_widget(flow_row(cells, spacing=theme.space_sm))
        return card

    def _build_metrics(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        self._tiles: dict[str, MetricTile] = {}
        specs = [
            ("takes", "Kayıt", "capture"),
            ("movements", "Hareket", "list"),
            ("ready", "Hazır etiket", "check"),
            ("unready", "Eksik etiket", "review"),
            ("intervals", "Hata aralığı", "target"),
            ("duration", "Toplam süre", "clock"),
            ("coverage", "Ort. takip kapsamı", "target"),
            ("synthetic", "Sentetik kayıt", "flask"),
            # The continuous layer is counted apart: "ready movements" and
            # "takes ready for continuous export" are different questions and
            # adding them would be meaningless.
            ("continuous", "Sürekli export hazır", "timeline"),
            ("negatives", "Egzersizsiz kayıt", "info"),
            ("unlabelled_time", "Etiketsiz süre", "review"),
            ("subject", "Ort. kişi kapsamı", "participant"),
            # Node evidence coverage. Deliberately its own tile rather than
            # folded into "ready": a take can be ready for temporal error
            # training while no interval has been reviewed for joints.
            ("joint_reviewed", "Eklemi işaretli aralık", "skeleton"),
            ("joint_pending", "Eklemi incelenmemiş", "review"),
        ]
        tiles = []
        for key, caption, icon in specs:
            tile = MetricTile(caption, "0", theme=theme, icon=icon)
            # Capped so a long caption like "Ort. takip kapsamı" cannot make
            # four tiles across into a 1336px minimum for the whole page.
            tile.setMinimumWidth(150)
            tile.setMaximumWidth(210)
            self._tiles[key] = tile
            tiles.append(tile)
        # Wraps to as many rows as the window needs rather than a fixed grid.
        card.add_widget(flow_row(tiles, spacing=theme.space_sm))
        return card

    def _build_table(self, theme: Theme) -> QWidget:
        card = Card("Kayıtlar", theme=theme, icon="list")
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            [
                "Katılımcı",
                "Kayıt",
                "Tarih",
                "Süre",
                "FPS",
                "Kapsam",
                "Hareket",
                "Hazır",
                "Durum",
            ]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        # ResizeToContents lets the widest cell in nine columns dictate the
        # page's minimum width; a long participant code or a timestamp then
        # makes the whole screen scroll sideways. The columns are sized once
        # and remain draggable.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((90, 150, 70, 130, 90, 90, 80, 90, 110)):
            self._table.setColumnWidth(column, width)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._table.setHorizontalScrollMode(
            QTableWidget.ScrollMode.ScrollPerPixel
        )
        header.setStretchLastSection(True)
        self._table.itemDoubleClicked.connect(self._open_selected)
        card.add_widget(self._table, 1)

        review = make_button(
            "Seçili kaydı incele", variant="primary", icon="review", theme=theme
        )
        review.clicked.connect(lambda: self._open_selected(self._table.currentItem()))
        card.add_widget(review)
        return card

    def _build_analysis(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        exercise_card = Card("Egzersiz dağılımı", theme=theme, icon="dashboard")
        self._exercise_bars = DistributionBar(theme)
        exercise_card.add_widget(self._exercise_bars)
        layout.addWidget(exercise_card)

        correctness_card = Card(
            "Değerlendirme dağılımı",
            subtitle="Hata aralıklarından türetilir.",
            theme=theme,
            icon="target",
        )
        self._correctness_bars = DistributionBar(theme)
        correctness_card.add_widget(self._correctness_bars)
        layout.addWidget(correctness_card)

        error_card = Card(
            "Hata türü dağılımı",
            subtitle="Zamansal hata aralıklarının sınıf dağılımı.",
            theme=theme,
            icon="target",
        )
        self._error_bars = DistributionBar(theme)
        error_card.add_widget(self._error_bars)
        layout.addWidget(error_card)

        qa_card = Card(
            "Kalite bulguları",
            subtitle="En kritik olanlar üstte.",
            theme=theme,
            icon="shield",
        )
        self._qa_table = QTableWidget(0, 2)
        self._qa_table.setHorizontalHeaderLabels(["Önem", "Bulgu"])
        self._qa_table.verticalHeader().setVisible(False)
        self._qa_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._qa_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        qa_header = self._qa_table.horizontalHeader()
        qa_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self._qa_table.setColumnWidth(0, 110)
        self._qa_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        qa_header.setStretchLastSection(True)
        self._qa_table.itemDoubleClicked.connect(self._open_qa_take)
        qa_card.add_widget(self._qa_table, 1)
        layout.addWidget(qa_card, 1)
        return wrapper

    # ----------------------------------------------------------------- data
    def _set_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._scroll.setVisible(not empty)

    def on_activated(self) -> None:
        self._reload()

    def _reload(self, *, force: bool = False) -> None:
        index = self.state.index
        if index is None:
            self._set_empty(True)
            return
        self._set_empty(False)
        if force:
            self.state.refresh_dataset(force=True)
            index = self.state.index
            if index is None:
                return
        else:
            index.refresh()
        self._populate_filters(index)
        self._apply_filters()

    def _populate_filters(self, index) -> None:  # type: ignore[no-untyped-def]
        schema = self.state.label_schema

        def fill(selector: QComboBox, entries: list[tuple[str, object]]) -> None:
            previous = selector.currentData()
            selector.blockSignals(True)
            selector.clear()
            selector.addItem("Tümü", _ANY)
            for label, value in entries:
                selector.addItem(label, value)
            position = selector.findData(previous)
            selector.setCurrentIndex(max(0, position))
            selector.blockSignals(False)

        fill(
            self._participant_filter,
            [(p.code, p.participant_id) for p in index.participants],
        )
        fill(
            self._session_filter,
            [
                (f"{s.started_at[:16].replace('T', ' ')}", s.session_id)
                for s in index.sessions
            ],
        )
        exercises = sorted(set(index.known_exercises()) | set(schema.exercise_codes()))
        fill(
            self._exercise_filter,
            [(schema.label_for_exercise(code), code) for code in exercises],
        )
        fill(
            self._correctness_filter,
            [
                (LabelSchema.label_for_correctness(value), value.value)
                for value in Correctness
            ],
        )
        fill(
            self._readiness_filter,
            [
                (_READINESS_LABELS[state], state.value)
                for state in SampleReadiness
            ],
        )
        fill(
            self._error_filter,
            [
                (schema.label_for_error(code), code)
                for code in sorted(
                    set(index.used_error_codes()) | set(schema.error_type_codes())
                )
            ],
        )
        fill(self._state_filter, [(state.value, state.value) for state in TakeState])
        fill(
            self._origin_filter,
            [("Gerçek", DataOrigin.REAL.value), ("Sentetik", DataOrigin.SYNTHETIC.value)],
        )

    def _build_query(self) -> DatasetQuery:
        def value(selector: QComboBox) -> Optional[object]:
            data = selector.currentData()
            return None if data == _ANY else data

        participant = value(self._participant_filter)
        session = value(self._session_filter)
        exercise = value(self._exercise_filter)
        correctness = value(self._correctness_filter)
        readiness = value(self._readiness_filter)
        error_code = value(self._error_filter)
        take_state = value(self._state_filter)
        origin = value(self._origin_filter)

        return DatasetQuery(
            participant_ids=(str(participant),) if participant else (),
            session_ids=(str(session),) if session else (),
            exercises=(str(exercise),) if exercise else (),
            correctness=(Correctness(correctness),) if correctness else (),
            readiness=(SampleReadiness(readiness),) if readiness else (),
            error_codes=(str(error_code),) if error_code else (),
            take_states=(TakeState(take_state),) if take_state else (),
            origin=DataOrigin(origin) if origin else None,
        )

    def _clear_filters(self) -> None:
        for selector in (
            self._participant_filter,
            self._session_filter,
            self._exercise_filter,
            self._correctness_filter,
            self._readiness_filter,
            self._error_filter,
            self._state_filter,
            self._origin_filter,
        ):
            selector.blockSignals(True)
            selector.setCurrentIndex(0)
            selector.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        index = self.state.index
        if index is None:
            return
        query = self._build_query()
        rows = index.filter(query)
        self._filter_chip.set_status(
            "Tümü" if query.is_empty else f"{len(rows)} / {len(index.rows)} kayıt",
            icon="list",
            colour=self.theme.text_secondary if query.is_empty else self.theme.accent,
        )
        self._fill_metrics(index, rows)
        self._fill_table(rows)
        self._fill_analysis(index, rows)

    def _fill_metrics(self, index, rows: list[TakeRow]) -> None:  # type: ignore[no-untyped-def]
        summary = index.summary(rows)
        theme = self.theme
        self._tiles["takes"].set_value(str(summary.takes))
        self._tiles["takes"].set_detail(
            f"{summary.finalized_takes} tamam · {summary.partial_takes} yarım"
        )
        self._tiles["movements"].set_value(str(summary.movement_samples))
        self._tiles["movements"].set_detail(
            f"{summary.excluded_samples} dışlandı"
        )
        self._tiles["ready"].set_value(
            str(summary.ready_samples), colour=theme.success
        )
        self._tiles["ready"].set_detail("export'a girer")
        self._tiles["unready"].set_value(
            str(summary.unready_samples),
            colour=theme.warning if summary.unready_samples else None,
        )
        self._tiles["unready"].set_detail(
            _readiness_detail(summary.readiness_counts)
        )
        self._tiles["intervals"].set_value(str(summary.error_intervals))
        self._tiles["intervals"].set_detail(
            f"{len(summary.error_class_counts)} hata türü"
        )
        self._tiles["duration"].set_value(format_duration(summary.total_duration_s))
        self._tiles["coverage"].set_value(
            f"%{summary.mean_tracking_coverage * 100:.0f}"
            if summary.mean_tracking_coverage
            else "-"
        )
        self._tiles["continuous"].set_value(
            str(summary.continuous_ready_takes),
            colour=theme.success if summary.continuous_ready_takes else None,
        )
        self._tiles["continuous"].set_detail(
            f"{summary.continuous_unlabelled_takes} kayıtta aktivite etiketi yok"
        )
        self._tiles["negatives"].set_value(str(summary.negative_takes))
        self._tiles["negatives"].set_detail("hiç hedef egzersiz içermeyen")
        self._tiles["unlabelled_time"].set_value(
            format_duration(summary.unlabelled_activity_seconds)
            if summary.unlabelled_activity_seconds
            else "-",
            colour=theme.warning if summary.unlabelled_activity_seconds else None,
        )
        self._tiles["unlabelled_time"].set_detail("arka plan SAYILMAZ")
        self._tiles["subject"].set_value(
            f"%{summary.mean_subject_coverage * 100:.0f}"
            if summary.takes_with_subject_lock
            else "-"
        )
        self._tiles["subject"].set_detail(
            f"{summary.takes_with_subject_lock} kayıtta kişi kilidi"
            + (
                f" · {summary.takes_with_raw_archive_loss} ham arşiv eksik"
                if summary.takes_with_raw_archive_loss
                else ""
            )
        )
        # Node evidence coverage, reported next to - never mixed into - the
        # temporal label readiness above it.
        counts = summary.joint_status_counts
        self._tiles["joint_reviewed"].set_value(str(summary.intervals_with_joints))
        self._tiles["joint_reviewed"].set_detail(
            f"{counts.get('not_applicable', 0)} eklem yok · "
            f"{counts.get('indeterminate', 0)} belirlenemiyor"
        )
        self._tiles["joint_pending"].set_value(
            str(summary.intervals_missing_joint_review),
            colour=theme.warning if summary.intervals_missing_joint_review else None,
        )
        self._tiles["joint_pending"].set_detail(
            f"{summary.takes_missing_joint_review} kayıtta"
            if summary.intervals_missing_joint_review
            else "node denetimi tam"
        )
        self._tiles["synthetic"].set_value(
            str(summary.synthetic_takes),
            colour=theme.synthetic if summary.synthetic_takes else None,
        )
        self._tiles["synthetic"].set_detail(f"{summary.real_takes} gerçek")

    def _fill_table(self, rows: list[TakeRow]) -> None:
        self._table.setRowCount(len(rows))
        for position, row in enumerate(rows):
            take = row.take
            metrics = take.metrics
            values = [
                row.participant_code,
                str(take.index_in_session),
                take.started_at[:16].replace("T", " "),
                format_duration(metrics.duration_s),
                f"{metrics.measured_fps:.1f}",
                f"%{metrics.tracking_coverage * 100:.0f}",
                str(row.movement_count),
                f"{row.labelled_count}/{row.movement_count}",
                take.state.value + (" · sentetik" if take.is_synthetic else ""),
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, take.take_id)
                if column == 8 and take.is_recoverable_partial:
                    item.setForeground(Qt.GlobalColor.yellow)
                self._table.setItem(position, column, item)

    def _fill_analysis(self, index, rows: list[TakeRow]) -> None:  # type: ignore[no-untyped-def]
        summary = index.summary(rows)
        schema = self.state.label_schema
        theme = self.theme

        self._exercise_bars.set_distribution(
            {
                schema.label_for_exercise(code): count
                for code, count in summary.exercise_counts.items()
            }
        )
        self._error_bars.set_distribution(
            {
                schema.label_for_error(code): count
                for code, count in summary.error_class_counts.items()
            },
            colours={
                schema.label_for_error(code): error_class_colour(code)
                for code in summary.error_class_counts
            },
        )
        self._correctness_bars.set_distribution(
            {
                LabelSchema.label_for_correctness(Correctness(code)): count
                for code, count in summary.correctness_counts.items()
            },
            colours={
                "Doğru": theme.success,
                "Hatalı": theme.warning,
                "Etiketlenmedi": theme.text_muted,
            },
        )

        issues = index.quality_issues(rows)
        self._qa_table.setRowCount(len(issues) or 1)
        if not issues:
            item = QTableWidgetItem("Bulgu yok")
            self._qa_table.setItem(0, 0, QTableWidgetItem("Bilgi"))
            self._qa_table.setItem(0, 1, item)
            return
        for position, issue in enumerate(issues):
            label, _icon = _SEVERITY_LABELS.get(issue["severity"], ("?", "info"))
            severity_item = QTableWidgetItem(label)
            if issue["severity"] == "blocked":
                severity_item.setForeground(Qt.GlobalColor.red)
            elif issue["severity"] == "warning":
                severity_item.setForeground(Qt.GlobalColor.yellow)
            self._qa_table.setItem(position, 0, severity_item)
            message_item = QTableWidgetItem(issue["message"])
            message_item.setData(Qt.ItemDataRole.UserRole, issue.get("take_id", ""))
            self._qa_table.setItem(position, 1, message_item)

    # -------------------------------------------------------------- actions
    def _open_selected(self, item) -> None:  # type: ignore[no-untyped-def]
        if item is None:
            return
        take_id = item.data(Qt.ItemDataRole.UserRole)
        self._open_take_id(take_id)

    def _open_qa_take(self, item) -> None:  # type: ignore[no-untyped-def]
        if item is None:
            return
        self._open_take_id(item.data(Qt.ItemDataRole.UserRole))

    def _open_take_id(self, take_id: Optional[str]) -> None:
        index = self.state.index
        if not take_id or index is None:
            return
        row = index.row_for(take_id)
        if row is not None:
            self.state.request_review(row.take)


__all__ = ["DatasetPage", "DistributionBar"]
