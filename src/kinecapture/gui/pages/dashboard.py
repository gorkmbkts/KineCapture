"""Dashboard: what is open, what is unfinished, and what to do next."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.diagnostics import collect_diagnostics
from kinecapture.dataset.index import TakeRow
from kinecapture.domain.enums import HealthLevel
from kinecapture.gui.pages.base import Page, scrollable
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    KeyValueList,
    MetricTile,
    StatusChip,
    make_button,
    make_label,
)


def format_duration(seconds: float) -> str:
    """``1s 04d 12sn`` style compact duration, or ``-`` for nothing."""
    total = int(round(seconds))
    if total <= 0:
        return "-"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} sa {minutes} dk"
    if minutes:
        return f"{minutes} dk {secs} sn"
    return f"{secs} sn"


def take_row_summary(row: TakeRow) -> str:
    """One-line description of a take for a list view."""
    take = row.take
    parts = [
        f"{row.participant_code} · Kayıt {take.index_in_session}",
        format_duration(take.metrics.duration_s),
        f"{row.movement_count} hareket",
    ]
    if row.movement_count:
        parts.append(f"{row.labelled_count} hazır")
    if row.error_interval_count:
        parts.append(f"{row.error_interval_count} hata aralığı")
    if take.is_synthetic:
        parts.append("SENTETİK")
    if take.is_recoverable_partial:
        parts.append("YARIM")
    return "  ·  ".join(parts)


class DashboardPage(Page):
    """Landing page with counts, unfinished work and quick actions."""

    navigate_requested = Signal(str)

    title = "Ana Sayfa"
    description = "Projenin durumu, bekleyen işler ve hızlı eylemler."
    icon = "dashboard"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme

        self._refresh_button = make_button(
            "Yenile", icon="refresh", theme=theme, tooltip="Dataset özetini yeniden oku"
        )
        self._refresh_button.clicked.connect(lambda: self._reload(force=True))
        self.header.add_action(self._refresh_button)

        self._empty = EmptyState(
            "Henüz bir proje açık değil",
            "Veri toplamaya başlamak için bir proje oluşturun veya var olanı açın.",
            theme=theme,
            icon="project",
            action_text="Projelere git",
        )
        self._empty.action_triggered.connect(
            lambda: self.navigate_requested.emit("projects")
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(theme.space_md)

        body_layout.addWidget(self._build_metrics(theme))

        columns = QHBoxLayout()
        columns.setSpacing(theme.space_md)
        columns.addWidget(self._build_pending(theme), 3)
        columns.addWidget(self._build_status(theme), 2)
        body_layout.addLayout(columns, 1)

        self._scroll = scrollable(self._body)
        self.content.addWidget(self._scroll, 1)
        self._show_empty(True)

        state.dataset_changed.connect(self._reload)
        state.project_changed.connect(lambda _: self._reload(force=True))

    # --------------------------------------------------------------- layout
    def _build_metrics(self, theme: Theme) -> QWidget:
        card = Card("Genel bakış", theme=theme, icon="dashboard")
        grid = QGridLayout()
        grid.setSpacing(theme.space_sm)
        self._tiles: dict[str, MetricTile] = {}
        specs = [
            ("participants", "Katılımcı", "participants"),
            ("sessions", "Oturum", "clock"),
            ("takes", "Kayıt", "capture"),
            ("movements", "Hareket", "list"),
            ("labelled", "Hazır etiket", "check"),
            ("pending", "Eksik etiket", "review"),
        ]
        for position, (key, caption, icon) in enumerate(specs):
            tile = MetricTile(caption, "0", theme=theme, icon=icon)
            self._tiles[key] = tile
            grid.addWidget(tile, position // 3, position % 3)
        container = QWidget()
        container.setLayout(grid)
        card.add_widget(container)

        self._duration_label = make_label("", role="muted")
        card.add_widget(self._duration_label)
        return card

    def _build_pending(self, theme: Theme) -> QWidget:
        card = Card(
            "Bekleyen işler",
            subtitle="Yarım kalan kayıtlar ve etiketlenmemiş tekrarlar.",
            theme=theme,
            icon="review",
        )
        self._pending_list = QListWidget()
        self._pending_list.setAlternatingRowColors(True)
        self._pending_list.itemDoubleClicked.connect(self._open_take)
        card.add_widget(self._pending_list, 1)

        row = QHBoxLayout()
        review_button = make_button(
            "Seçili kaydı incele", variant="primary", icon="review", theme=theme
        )
        review_button.clicked.connect(
            lambda: self._open_take(self._pending_list.currentItem())
        )
        row.addWidget(review_button)
        capture_button = make_button("Yeni kayıt", icon="capture", theme=theme)
        capture_button.clicked.connect(
            lambda: self.navigate_requested.emit("capture")
        )
        row.addWidget(capture_button)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        return card

    def _build_status(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        self._project_card = Card("Aktif proje", theme=theme, icon="project")
        self._project_details = KeyValueList(theme)
        self._project_card.add_widget(self._project_details)
        layout.addWidget(self._project_card)

        self._health_card = Card("Sistem durumu", theme=theme, icon="shield")
        self._health_chip = StatusChip("Kontrol edilmedi", theme=theme, icon="info")
        self._health_card.add_header_widget(self._health_chip)
        self._health_details = KeyValueList(theme)
        self._health_card.add_widget(self._health_details)
        health_button = make_button("Tanıyı çalıştır", icon="refresh", theme=theme)
        health_button.clicked.connect(self._run_diagnostics)
        self._health_card.add_widget(health_button)
        layout.addWidget(self._health_card)

        self._quality_card = Card(
            "Son kayıt kalitesi", theme=theme, icon="target"
        )
        self._quality_details = KeyValueList(theme)
        self._quality_card.add_widget(self._quality_details)
        layout.addWidget(self._quality_card)
        layout.addStretch(1)
        return wrapper

    # ----------------------------------------------------------------- data
    def on_activated(self) -> None:
        self._reload()

    def _show_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._scroll.setVisible(not empty)
        self._refresh_button.setEnabled(not empty)

    def _reload(self, *, force: bool = False) -> None:
        index = self.state.index
        if index is None:
            self._show_empty(True)
            return
        self._show_empty(False)
        if force:
            self.state.refresh_dataset(force=True)
            index = self.state.index
            if index is None:
                return
        else:
            index.refresh()

        summary = index.summary()
        self._tiles["participants"].set_value(str(summary.participants))
        self._tiles["sessions"].set_value(str(summary.sessions))
        self._tiles["takes"].set_value(str(summary.takes))
        self._tiles["takes"].set_detail(
            f"{summary.finalized_takes} tamamlandı · {summary.partial_takes} yarım"
        )
        self._tiles["movements"].set_value(str(summary.movement_samples))
        self._tiles["movements"].set_detail(
            f"{summary.error_intervals} hata aralığı"
        )
        self._tiles["labelled"].set_value(
            str(summary.ready_samples),
            colour=self.theme.success if summary.ready_samples else None,
        )
        pending = summary.unready_samples
        self._tiles["pending"].set_value(
            str(pending), colour=self.theme.warning if pending else self.theme.success
        )
        self._duration_label.setText(
            f"Toplam kayıt süresi: {format_duration(summary.total_duration_s)}"
            + (
                f"  ·  Ortalama takip kapsamı: %{summary.mean_tracking_coverage * 100:.0f}"
                if summary.mean_tracking_coverage
                else ""
            )
            + (
                f"  ·  {summary.synthetic_takes} sentetik kayıt"
                if summary.synthetic_takes
                else ""
            )
        )

        self._fill_pending(index)
        self._fill_project()
        self._fill_last_quality(index)

    def _fill_pending(self, index) -> None:  # type: ignore[no-untyped-def]
        self._pending_list.clear()
        rows: list[TakeRow] = list(index.partial_takes()) + [
            row for row in index.needing_review(limit=25)
        ]
        seen: set[str] = set()
        for row in rows:
            if row.take.take_id in seen:
                continue
            seen.add(row.take.take_id)
            prefix = "Yarım kayıt" if row.take.is_recoverable_partial else "Etiket bekliyor"
            item = QListWidgetItem(f"{prefix}  —  {take_row_summary(row)}")
            item.setData(Qt.ItemDataRole.UserRole, row.take.take_id)
            if row.take.is_recoverable_partial:
                item.setForeground(Qt.GlobalColor.yellow)
            self._pending_list.addItem(item)
        if self._pending_list.count() == 0:
            item = QListWidgetItem("Bekleyen iş yok. Bütün kayıtlar etiketlenmiş.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._pending_list.addItem(item)

    def _fill_project(self) -> None:
        project = self.state.project
        workspace = self.state.workspace
        if project is None or workspace is None:
            self._project_details.set_items([])
            return
        session = self.state.session
        participant = self.state.participant
        self._project_details.set_items(
            [
                ("Proje", project.name),
                ("Klasör", str(workspace.root)),
                ("Katılımcı", participant.code if participant else "seçilmedi"),
                (
                    "Oturum",
                    session.session_id if session else "seçilmedi",
                ),
                ("Etiket şeması", f"v{self.state.label_schema.schema_version}"),
                (
                    "Egzersizler",
                    ", ".join(self.state.label_schema.exercise_codes()) or "tanımsız",
                ),
            ]
        )

    def _fill_last_quality(self, index) -> None:  # type: ignore[no-untyped-def]
        recent = index.recent(1)
        if not recent:
            self._quality_details.set_items([("Durum", "Henüz kayıt yok")])
            return
        row = recent[0]
        metrics = row.take.metrics
        self._quality_details.set_items(
            [
                ("Kayıt", take_row_summary(row)),
                ("Süre", format_duration(metrics.duration_s)),
                (
                    "FPS",
                    f"{metrics.measured_fps:.1f} / {metrics.target_fps:.0f} hedef",
                ),
                ("Takip kapsamı", f"%{metrics.tracking_coverage * 100:.0f}"),
                (
                    "Kayıp kare",
                    f"{metrics.frames_dropped_recording} yazılamadı, "
                    f"{metrics.missing_frame_indices} eksik",
                ),
                ("Durum", row.take.state.value),
            ]
        )

    def _open_take(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        take_id = item.data(Qt.ItemDataRole.UserRole)
        index = self.state.index
        if not take_id or index is None:
            return
        row = index.row_for(take_id)
        if row is not None:
            self.state.request_review(row.take)

    def _run_diagnostics(self) -> None:
        report = collect_diagnostics(
            dataset_root=self.state.config.dataset_root,
            backend=self.state.config.backend,
        )
        self._health_chip.set_health(report.level)
        self._health_details.set_items(
            [(check.name, check.message) for check in report.checks[:8]]
        )
        if report.level is HealthLevel.BLOCKED:
            self.state.notify("Sistem tanısı engel bildirdi.", 6000)


__all__ = ["DashboardPage", "format_duration", "take_row_summary"]
