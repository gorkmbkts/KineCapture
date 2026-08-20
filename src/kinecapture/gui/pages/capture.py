"""Capture screen: live preview, health, recording controls and the take verdict.

The GUI thread here only *reads*. Frames arrive from the acquisition thread into
a latest-wins slot; a timer picks up whatever is there and repaints. If the GUI
falls behind, preview frames are skipped and counted - the recording is never
throttled to keep the UI smooth, and the two counters are shown separately so
the operator can see which one is happening.
"""

from __future__ import annotations

import shutil
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.diagnostics import collect_diagnostics, estimate_recording_minutes
from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.enums import (
    BackendKind,
    CaptureMode,
    CaptureState,
    HealthLevel,
    TakeQuality,
)
from kinecapture.domain.models import FramePacket
from kinecapture.domain.project import ProtocolTask, Take
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    FieldRow,
    KeyValueList,
    MetricTile,
    StatusChip,
    make_button,
    make_label,
    monospace_font,
)
from kinecapture.gui.widgets.skeleton_view import VIEW_PRESETS, SkeletonView3D
from kinecapture.gui.widgets.video_view import VideoView

#: How often the live metric row refreshes. Slower than the preview on purpose:
#: numbers that update 30 times a second are unreadable.
_METRIC_INTERVAL_MS = 250

_QUALITY_CHOICES = (
    (TakeQuality.GOOD, "Başarılı", "check"),
    (TakeQuality.RETAKE, "Tekrar çekilmeli", "refresh"),
    (TakeQuality.TECHNICAL_ISSUE, "Teknik sorun", "warning"),
    (TakeQuality.EXCLUDED, "Datasetten çıkar", "trash"),
    (TakeQuality.UNCERTAIN, "Kararsız", "info"),
)


class TakeVerdictDialog(QDialog):
    """The immediate post-take decision, asked while the operator remembers."""

    def __init__(
        self, take: Take, theme: Theme, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kayıt değerlendirmesi")
        self.setMinimumWidth(520)
        self._take = take
        self._choice = TakeQuality.UNDECIDED

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.space_md)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )

        metrics = take.metrics
        summary = Card("Kalite özeti", theme=theme, icon="target")
        details = KeyValueList(theme)
        loss = (
            f"{metrics.frames_dropped_recording} yazılamadı, "
            f"{metrics.missing_frame_indices} eksik"
        )
        details.set_items(
            [
                ("Süre", f"{metrics.duration_s:.1f} sn"),
                (
                    "FPS",
                    f"{metrics.measured_fps:.1f} ölçülen / {metrics.target_fps:.0f} hedef",
                ),
                ("Yazılan kare", str(metrics.frames_written)),
                ("Kayıp kare", loss),
                ("Takip kapsamı", f"%{metrics.tracking_coverage * 100:.0f}"),
                (
                    "Ortalama eklem güveni",
                    f"{metrics.mean_joint_confidence:.2f}"
                    if metrics.mean_joint_confidence == metrics.mean_joint_confidence
                    else "bilinmiyor",
                ),
                ("Çoklu gövde", f"{metrics.frames_with_multiple_bodies} kare"),
                ("Takip kimliği değişimi", str(metrics.body_id_changes)),
                ("Durum", take.state.value),
            ]
        )
        summary.add_widget(details)
        layout.addWidget(summary)

        if metrics.has_capture_loss:
            warning = make_label(
                "Bu kayıtta veri kaybı var. Datasete almadan önce inceleyin.",
                role="error",
            )
            warning.setWordWrap(True)
            layout.addWidget(warning)

        self._note = QPlainTextEdit()
        self._note.setPlaceholderText("Bu kayıtla ilgili not (isteğe bağlı)")
        self._note.setMaximumHeight(70)
        layout.addWidget(FieldRow("Not", self._note, theme=theme))

        layout.addWidget(make_label("Değerlendirme", role="caption"))
        grid = QGridLayout()
        grid.setSpacing(theme.space_sm)
        for position, (quality, label, icon) in enumerate(_QUALITY_CHOICES):
            variant = "primary" if quality is TakeQuality.GOOD else ""
            if quality is TakeQuality.EXCLUDED:
                variant = "danger"
            button = make_button(label, variant=variant, icon=icon, theme=theme)
            button.clicked.connect(lambda _=False, q=quality: self._choose(q))
            grid.addWidget(button, position // 3, position % 3)
        container = QWidget()
        container.setLayout(grid)
        layout.addWidget(container)

        buttons = QDialogButtonBox()
        later = buttons.addButton(
            "Sonra karar ver", QDialogButtonBox.ButtonRole.RejectRole
        )
        later.clicked.connect(self.reject)
        review = buttons.addButton(
            "İncele ve etiketle", QDialogButtonBox.ButtonRole.ActionRole
        )
        review.clicked.connect(self._choose_review)
        layout.addWidget(buttons)
        self.review_requested = False

    def _choose(self, quality: TakeQuality) -> None:
        self._choice = quality
        self.accept()

    def _choose_review(self) -> None:
        self._choice = TakeQuality.GOOD
        self.review_requested = True
        self.accept()

    @property
    def quality(self) -> TakeQuality:
        return self._choice

    @property
    def note(self) -> str:
        return self._note.toPlainText().strip()


class CapturePage(Page):
    """Live capture with preview, health panel, protocol guidance and controls."""

    navigate_requested = Signal(str)

    title = "Capture"
    description = "Canlı önizleme, kayıt kontrolü ve anlık kalite göstergeleri."
    icon = "capture"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme
        self._last_packet: Optional[FramePacket] = None
        self._active_task: Optional[ProtocolTask] = None
        self._task_position = 0
        self._known_body_ids: list[int] = []

        self._backend_selector = QComboBox()
        for kind in BackendKind:
            label = "Sentetik (donanımsız)" if kind is BackendKind.MOCK else "ZED 2i"
            self._backend_selector.addItem(label, kind.value)
        self._backend_selector.setCurrentIndex(
            self._backend_selector.findData(state.config.backend.value)
        )
        self._backend_selector.currentIndexChanged.connect(self._backend_changed)
        self.header.add_action(make_label("Backend", role="caption"))
        self.header.add_action(self._backend_selector)

        self._connect_button = make_button(
            "Bağlan", variant="primary", icon="camera", theme=theme
        )
        self._connect_button.clicked.connect(self._toggle_connection)
        self.header.add_action(self._connect_button)

        self._empty = EmptyState(
            "Kayıt için bir oturum gerekiyor",
            "Katılımcı seçip oturum başlattıktan sonra buraya dönün.",
            theme=theme,
            icon="participants",
            action_text="Katılımcılara git",
        )
        self._empty.action_triggered.connect(
            lambda: self.navigate_requested.emit("participants")
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.space_sm)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_views(theme))
        splitter.addWidget(self._build_side_panel(theme))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([900, 460])
        body.addWidget(splitter, 1)

        body.addWidget(self._build_metrics(theme))
        body.addWidget(self._build_controls(theme))
        self.content.addWidget(self._body, 1)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(state.config.preview_interval_ms)
        self._preview_timer.timeout.connect(self._pull_frame)

        self._metric_timer = QTimer(self)
        self._metric_timer.setInterval(_METRIC_INTERVAL_MS)
        self._metric_timer.timeout.connect(self._refresh_metrics)

        self._install_shortcuts()

        state.session_changed.connect(lambda _: self._refresh_context())
        state.participant_changed.connect(lambda _: self._refresh_context())
        state.project_changed.connect(lambda _: self._refresh_context())
        self._refresh_context()
        self._update_controls()

    # --------------------------------------------------------------- layout
    def _build_views(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_sm)

        views = QSplitter(Qt.Orientation.Horizontal)

        rgb_card = Card("Canlı görüntü", theme=theme, icon="camera")
        self._view_selector = QComboBox()
        self._view_selector.addItem("RGB", "rgb")
        self._view_selector.addItem("Derinlik", "depth")
        self._view_selector.currentIndexChanged.connect(self._redraw_last_frame)
        rgb_card.add_header_widget(self._view_selector)
        self._overlay_toggle = make_button(
            "İskelet bindirme", icon="skeleton", theme=theme
        )
        self._overlay_toggle.setCheckable(True)
        self._overlay_toggle.setChecked(True)
        self._overlay_toggle.toggled.connect(
            lambda on: self._video.set_overlay_enabled(on)
        )
        rgb_card.add_header_widget(self._overlay_toggle)
        self._video = VideoView(theme, placeholder_text="Önizleme kapalı")
        rgb_card.add_widget(self._video, 1)
        views.addWidget(rgb_card)

        skeleton_card = Card("3B iskelet", theme=theme, icon="skeleton")
        self._preset_selector = QComboBox()
        for preset in VIEW_PRESETS:
            self._preset_selector.addItem(preset.label, preset.key)
        self._preset_selector.setCurrentIndex(2)
        self._preset_selector.currentIndexChanged.connect(
            lambda: self._skeleton.set_preset(self._preset_selector.currentData())
        )
        skeleton_card.add_header_widget(self._preset_selector)
        self._skeleton = SkeletonView3D(theme, preset="perspective")
        self._skeleton.set_placeholder_text("Gövde algılanmadı")
        skeleton_card.add_widget(self._skeleton, 1)
        views.addWidget(skeleton_card)

        views.setSizes([560, 460])
        layout.addWidget(views, 1)
        return wrapper

    def _build_side_panel(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        self._health_card = Card(
            "Ön kontrol",
            subtitle="Kayıt öncesi sistem ve kamera durumu.",
            theme=theme,
            icon="shield",
        )
        self._health_chip = StatusChip("Kontrol edilmedi", theme=theme, icon="info")
        self._health_card.add_header_widget(self._health_chip)
        self._health_details = KeyValueList(theme)
        self._health_card.add_widget(self._health_details)
        health_row = QHBoxLayout()
        check_button = make_button("Kontrol et", icon="refresh", theme=theme)
        check_button.clicked.connect(self._run_health_check)
        health_row.addWidget(check_button)
        copy_button = make_button("Raporu kopyala", icon="list", theme=theme)
        copy_button.clicked.connect(self._copy_health_report)
        health_row.addWidget(copy_button)
        health_row.addStretch(1)
        health_container = QWidget()
        health_container.setLayout(health_row)
        self._health_card.add_widget(health_container)
        layout.addWidget(self._health_card)

        self._task_card = Card(
            "Protokol", subtitle="Önceki / aktif / sonraki görev.", theme=theme, icon="list"
        )
        self._task_details = KeyValueList(theme)
        self._task_card.add_widget(self._task_details)
        task_row = QHBoxLayout()
        previous_button = make_button("Önceki", icon="chevron-left", theme=theme)
        previous_button.clicked.connect(lambda: self._step_task(-1))
        task_row.addWidget(previous_button)
        next_button = make_button("Sonraki", icon="chevron-right", theme=theme)
        next_button.clicked.connect(lambda: self._step_task(1))
        task_row.addWidget(next_button)
        task_row.addStretch(1)
        task_container = QWidget()
        task_container.setLayout(task_row)
        self._task_card.add_widget(task_container)
        layout.addWidget(self._task_card)

        self._take_card = Card("Kayıt bilgisi", theme=theme, icon="capture")
        self._exercise_input = QLineEdit()
        self._exercise_input.setPlaceholderText("Örn. squat")
        self._take_card.add_widget(
            FieldRow("Egzersiz", self._exercise_input, theme=theme)
        )
        self._note_input = QPlainTextEdit()
        self._note_input.setMaximumHeight(56)
        self._note_input.setPlaceholderText("Bu kayda ait not")
        self._take_card.add_widget(FieldRow("Take notu", self._note_input, theme=theme))

        self._body_selector = QComboBox()
        self._body_selector.addItem("Otomatik (en iyi gövde)", None)
        self._body_selector.currentIndexChanged.connect(self._body_selected)
        self._take_card.add_widget(
            FieldRow(
                "Aktif gövde",
                self._body_selector,
                theme=theme,
                help_text="Hedef kişi kaybolursa kimlik değişimi metadata'ya yazılır.",
            )
        )
        layout.addWidget(self._take_card)
        layout.addStretch(1)
        return wrapper

    def _build_metrics(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        row = QHBoxLayout()
        row.setSpacing(theme.space_sm)
        self._metrics: dict[str, MetricTile] = {}
        specs = [
            ("state", "Durum", "info"),
            ("fps", "Yakalama FPS", "clock"),
            ("latency", "Gecikme", "clock"),
            ("preview_drop", "Önizleme atlanan", "eye"),
            ("capture_drop", "KAYIT KAYBI", "warning"),
            ("bodies", "Gövde", "participants"),
            ("confidence", "Güven", "target"),
            ("disk", "Disk", "disk"),
            ("elapsed", "Süre", "clock"),
        ]
        for key, caption, icon in specs:
            tile = MetricTile(caption, "-", theme=theme, icon=icon)
            tile._value.setFont(monospace_font(theme.font_size_lg))
            self._metrics[key] = tile
            row.addWidget(tile)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        return card

    def _build_controls(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        row = QHBoxLayout()
        row.setSpacing(theme.space_sm)

        self._mode_group = QButtonGroup(self)
        self._guided_button = make_button("Rehberli", theme=theme)
        self._guided_button.setCheckable(True)
        self._free_button = make_button("Serbest", theme=theme)
        self._free_button.setCheckable(True)
        self._free_button.setChecked(True)
        self._mode_group.addButton(self._guided_button)
        self._mode_group.addButton(self._free_button)
        row.addWidget(self._guided_button)
        row.addWidget(self._free_button)
        row.addSpacing(theme.space_md)

        self._preview_button = make_button("Önizleme", icon="eye", theme=theme)
        self._preview_button.setCheckable(True)
        self._preview_button.toggled.connect(self._toggle_preview)
        row.addWidget(self._preview_button)

        self._record_button = make_button(
            "Kaydı başlat  (R)", variant="danger", icon="record", theme=theme
        )
        self._record_button.clicked.connect(self._toggle_recording)
        row.addWidget(self._record_button)

        self._marker_button = make_button("Marker  (M)", icon="marker", theme=theme)
        self._marker_button.clicked.connect(self._add_marker)
        row.addWidget(self._marker_button)

        self._review_button = make_button(
            "Son kaydı incele", icon="review", theme=theme
        )
        self._review_button.clicked.connect(self._review_last)
        row.addWidget(self._review_button)

        row.addStretch(1)
        self._context_label = make_label("", role="muted")
        row.addWidget(self._context_label)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        self._last_take: Optional[Take] = None
        return card

    def _install_shortcuts(self) -> None:
        """Capture shortcuts, scoped so typing in a field cannot trigger them."""

        def add(sequence: str, handler) -> None:  # type: ignore[no-untyped-def]
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

        add("R", self._shortcut_record)
        add("M", self._shortcut_marker)
        add("Space", self._shortcut_preview)
        add("Esc", self._shortcut_stop)

    def _typing(self) -> bool:
        widget = self.focusWidget()
        return isinstance(widget, (QLineEdit, QPlainTextEdit))

    def _shortcut_record(self) -> None:
        if not self._typing():
            self._toggle_recording()

    def _shortcut_marker(self) -> None:
        if not self._typing():
            self._add_marker()

    def _shortcut_preview(self) -> None:
        if not self._typing():
            self._preview_button.toggle()

    def _shortcut_stop(self) -> None:
        service = self.state.capture
        if service is not None and service.is_recording and not self._typing():
            self._toggle_recording()

    # ------------------------------------------------------------- lifecycle
    def on_activated(self) -> None:
        self._refresh_context()
        self._run_health_check()
        self._update_controls()

    def on_deactivated(self) -> None:
        # Leaving the page stops the preview but never a recording; a running
        # take is protected by can_leave().
        service = self.state.capture
        if service is not None and not service.is_recording:
            self._stop_preview()

    def can_leave(self) -> bool:
        service = self.state.capture
        if service is not None and service.is_recording:
            self.state.notify(
                "Kayıt sürüyor. Sayfadan ayrılmadan önce kaydı durdurun.", 6000
            )
            return False
        return True

    def _refresh_context(self) -> None:
        has_session = self.state.can_capture
        self._empty.setVisible(not has_session)
        self._body.setVisible(has_session)
        if not has_session:
            self._context_label.setText("")
            return
        participant = self.state.participant
        session = self.state.session
        project = self.state.project
        self._context_label.setText(
            f"{project.name if project else '-'}  ·  "
            f"{participant.code if participant else '-'}  ·  "
            f"{session.session_id[-12:] if session else '-'}"
        )
        self._reload_protocol()

    # ---------------------------------------------------------- connection
    def _backend_changed(self) -> None:
        kind = BackendKind(self._backend_selector.currentData())
        service = self.state.capture
        if service is not None and service.is_recording:
            self.state.notify("Kayıt sırasında backend değiştirilemez.", 5000)
            self._backend_selector.setCurrentIndex(
                self._backend_selector.findData(self.state.config.backend.value)
            )
            return
        self._stop_preview()
        self.state.release_capture_service()
        self.state.config.backend = kind
        self.state.save_preferences()
        self._run_health_check()
        self._update_controls()

    def _toggle_connection(self) -> None:
        service = self.state.capture
        if service is not None and service.state is not CaptureState.DISCONNECTED:
            self._stop_preview()
            service.disconnect()
            self.state.notify("Kamera bağlantısı kapatıldı.")
            self._update_controls()
            return

        kind = BackendKind(self._backend_selector.currentData())
        service = self.state.ensure_capture_service(kind)
        self._connect_button.setEnabled(False)
        self._connect_button.setText("Bağlanıyor...")
        # A first ZED connection optimises neural models and can take minutes;
        # say so rather than looking frozen.
        if kind is BackendKind.ZED:
            self.state.notify(
                "ZED kamera açılıyor. İlk çalıştırmada SDK model optimizasyonu "
                "birkaç dakika sürebilir.",
                12000,
            )
        QWidget.repaint(self)
        try:
            info = service.connect()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            self._update_controls()
            return
        finally:
            self._connect_button.setEnabled(True)

        self._skeleton.set_bodies((), service.skeleton_spec)
        self.state.notify(
            f"Bağlandı: {info.display_name} · {info.resolution[0]}x{info.resolution[1]} "
            f"@ {info.target_fps:.0f} FPS"
        )
        self._update_controls()
        self._preview_button.setChecked(True)

    def _toggle_preview(self, enabled: bool) -> None:
        service = self.state.capture
        if service is None:
            return
        if enabled:
            if service.state is CaptureState.DISCONNECTED:
                self._preview_button.setChecked(False)
                return
            try:
                service.start_preview()
            except KineCaptureError as exc:
                self.state.report_error(exc)
                self._preview_button.setChecked(False)
                return
            except Exception as exc:
                self.state.notify(f"Önizleme başlatılamadı: {exc}", 6000)
                self._preview_button.setChecked(False)
                return
            self._preview_timer.start()
            self._metric_timer.start()
        else:
            self._stop_preview()
        self._update_controls()

    def _stop_preview(self) -> None:
        self._preview_timer.stop()
        self._metric_timer.stop()
        service = self.state.capture
        if service is not None and service.state in (
            CaptureState.PREVIEWING,
            CaptureState.RECORDING,
        ):
            service.stop_preview()
        self._video.clear()
        self._video.set_badge("")
        self._skeleton.clear()
        self._preview_button.setChecked(False)

    # -------------------------------------------------------------- preview
    def _pull_frame(self) -> None:
        service = self.state.capture
        if service is None:
            return
        packet = service.latest_frame()
        if packet is None:
            return
        self._last_packet = packet
        self._render_packet(packet)

    def _redraw_last_frame(self) -> None:
        if self._last_packet is not None:
            self._render_packet(self._last_packet)

    def _render_packet(self, packet: FramePacket) -> None:
        service = self.state.capture
        spec = service.skeleton_spec if service else None
        active_id = service.active_body_id if service else None

        if self._view_selector.currentData() == "depth":
            if packet.depth_frame is not None:
                self._video.set_depth(packet.depth_frame)
            else:
                self._video.set_image(None)
                self._video.set_placeholder_text(
                    "Bu backend derinlik görüntüsü sağlamıyor."
                )
        else:
            self._video.set_rgb(packet.color_frame)

        self._video.set_bodies(packet.bodies, spec, active_id=active_id)
        self._skeleton.set_bodies(packet.bodies, spec, active_id=active_id)

        if service is not None and service.is_recording:
            self._video.set_badge("● KAYIT", self.theme.danger)
        elif packet.is_synthetic:
            self._video.set_badge("SENTETİK", self.theme.synthetic)
        else:
            self._video.set_badge("")

        self._sync_body_selector(packet)

    def _sync_body_selector(self, packet: FramePacket) -> None:
        ids = sorted(body.tracking_id for body in packet.bodies)
        if ids == self._known_body_ids:
            return
        self._known_body_ids = ids
        current = self._body_selector.currentData()
        self._body_selector.blockSignals(True)
        self._body_selector.clear()
        self._body_selector.addItem("Otomatik (en iyi gövde)", None)
        for tracking_id in ids:
            self._body_selector.addItem(f"ID {tracking_id}", tracking_id)
        position = self._body_selector.findData(current)
        self._body_selector.setCurrentIndex(max(0, position))
        self._body_selector.blockSignals(False)

    def _body_selected(self) -> None:
        service = self.state.capture
        if service is not None:
            service.set_active_body_id(self._body_selector.currentData())

    # -------------------------------------------------------------- metrics
    def _refresh_metrics(self) -> None:
        service = self.state.capture
        if service is None:
            return
        stats = service.statistics
        theme = self.theme

        self._metrics["state"].set_value(service.state.value)
        self._metrics["fps"].set_value(f"{stats.acquisition_fps:5.1f}")
        target = service.camera_info.target_fps if service.camera_info else 0
        if target and stats.acquisition_fps and stats.acquisition_fps < 0.8 * target:
            self._metrics["fps"].set_value(
                f"{stats.acquisition_fps:5.1f}", colour=theme.warning
            )
        self._metrics["fps"].set_detail(f"hedef {target:.0f}")

        self._metrics["latency"].set_value(f"{stats.last_latency_ms:5.1f} ms")
        self._metrics["preview_drop"].set_value(str(stats.preview_frames_dropped))
        self._metrics["preview_drop"].set_detail("kabul edilebilir")

        loss = stats.recording_frames_dropped
        self._metrics["capture_drop"].set_value(
            str(loss), colour=theme.danger if loss else theme.success
        )
        self._metrics["capture_drop"].set_detail(
            "veri kaybı!" if loss else "kayıp yok"
        )

        packet = self._last_packet
        body_count = len(packet.bodies) if packet else 0
        self._metrics["bodies"].set_value(str(body_count))
        active = service.active_body_id
        self._metrics["bodies"].set_detail(
            f"aktif ID {active}" if active is not None else "otomatik"
        )

        if packet and packet.bodies:
            primary = packet.primary_body(active)
            if primary is not None:
                confidence = primary.mean_confidence()
                valid = primary.valid_joint_ratio
                text = "-" if confidence != confidence else f"{confidence:4.2f}"
                colour = (
                    theme.warning
                    if confidence == confidence and confidence < 0.5
                    else None
                )
                self._metrics["confidence"].set_value(text, colour=colour)
                self._metrics["confidence"].set_detail(f"eklem %{valid * 100:.0f}")
        else:
            self._metrics["confidence"].set_value("-")
            self._metrics["confidence"].set_detail("gövde yok")

        try:
            usage = shutil.disk_usage(self.state.config.dataset_root)
            free_gb = usage.free / 1024**3
            minutes = estimate_recording_minutes(usage.free)
            self._metrics["disk"].set_value(
                f"{free_gb:5.1f} GB",
                colour=theme.danger if free_gb < 1 else (theme.warning if free_gb < 10 else None),
            )
            self._metrics["disk"].set_detail(f"~{minutes:.0f} dk kayıt")
        except OSError:
            self._metrics["disk"].set_value("?")

        if service.is_recording:
            elapsed = service.recording_elapsed_s
            self._metrics["elapsed"].set_value(
                f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}", colour=theme.danger
            )
            self._metrics["elapsed"].set_detail(
                f"{service.recorded_frame_count} kare"
            )
        else:
            self._metrics["elapsed"].set_value("--:--")
            self._metrics["elapsed"].set_detail("")

    # -------------------------------------------------------------- health
    def _run_health_check(self) -> None:
        report = collect_diagnostics(
            dataset_root=self.state.config.dataset_root,
            backend=self.state.config.backend,
        )
        self._health_report = report
        self._health_chip.set_health(report.level)
        items: list[tuple[str, str]] = []
        for check in report.checks:
            mark = {
                HealthLevel.READY: "OK",
                HealthLevel.WARNING: "UYARI",
                HealthLevel.BLOCKED: "ENGEL",
                HealthLevel.UNKNOWN: "?",
            }[check.level]
            text = f"[{mark}] {check.message}"
            if check.remedy and check.level is not HealthLevel.READY:
                text += f"  →  {check.remedy}"
            items.append((check.name, text))
        self._health_details.set_items(items)

    def _copy_health_report(self) -> None:
        from PySide6.QtWidgets import QApplication

        report = getattr(self, "_health_report", None)
        if report is None:
            self._run_health_check()
            report = self._health_report
        QApplication.clipboard().setText(report.as_text())
        self.state.notify("Tanı raporu panoya kopyalandı (kişisel veri içermez).")

    # ------------------------------------------------------------- protocol
    def _reload_protocol(self) -> None:
        workspace = self.state.workspace
        session = self.state.session
        if workspace is None or session is None or not session.protocol_id:
            self._task_details.set_items(
                [("Mod", "Serbest kayıt (protokol seçilmedi)")]
            )
            self._active_task = None
            return
        protocol = workspace.project.protocol_by_id(session.protocol_id)
        if protocol is None or not protocol.tasks:
            self._task_details.set_items([("Protokol", "Görev tanımlı değil")])
            self._active_task = None
            return
        self._task_position = max(0, min(self._task_position, len(protocol.tasks) - 1))
        self._active_task = protocol.tasks[self._task_position]
        self._render_task(protocol.tasks)

    def _render_task(self, tasks: list[ProtocolTask]) -> None:
        workspace = self.state.workspace
        session = self.state.session
        task = self._active_task
        if task is None or workspace is None or session is None:
            return
        previous = tasks[self._task_position - 1] if self._task_position > 0 else None
        following = (
            tasks[self._task_position + 1]
            if self._task_position + 1 < len(tasks)
            else None
        )
        recorded = sum(
            1
            for take in workspace.list_takes(session.participant_id, session.session_id)
            if take.protocol_task_id == task.task_id
        )
        items = [
            ("Önceki", previous.display_label if previous else "-"),
            (
                "AKTİF",
                f"{task.display_label}  ({self._task_position + 1}/{len(tasks)})",
            ),
            ("Sonraki", following.display_label if following else "-"),
            ("İlerleme", f"{recorded} / {task.target_total_takes} kayıt"),
        ]
        if task.reps_per_take:
            items.append(("Kayıt başına tekrar", str(task.reps_per_take)))
        if task.side != "both":
            items.append(("Taraf", task.side))
        if task.planned_error_type:
            items.append(("Planlanan hata", task.planned_error_type))
        if task.operator_instruction:
            items.append(("Talimat", task.operator_instruction))
        if task.safety_note:
            items.append(("Güvenlik", task.safety_note))
        self._task_details.set_items(items)
        if not self._exercise_input.text().strip():
            self._exercise_input.setText(task.exercise)

    def _step_task(self, delta: int) -> None:
        workspace = self.state.workspace
        session = self.state.session
        if workspace is None or session is None or not session.protocol_id:
            return
        protocol = workspace.project.protocol_by_id(session.protocol_id)
        if protocol is None or not protocol.tasks:
            return
        self._task_position = max(
            0, min(len(protocol.tasks) - 1, self._task_position + delta)
        )
        self._active_task = protocol.tasks[self._task_position]
        self._exercise_input.setText(self._active_task.exercise)
        self._render_task(protocol.tasks)

    # ------------------------------------------------------------ recording
    def _toggle_recording(self) -> None:
        service = self.state.capture
        if service is None:
            return
        if service.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        service = self.state.capture
        workspace = self.state.workspace
        session = self.state.session
        if service is None or workspace is None or session is None:
            return
        if service.state is not CaptureState.PREVIEWING:
            self.state.notify("Önce önizlemeyi başlatın.", 5000)
            return

        report = getattr(self, "_health_report", None)
        if report is not None and report.is_blocked:
            self.state.notify(
                "Ön kontrol engel bildirdi; kayıt başlatılmadı. Ayrıntı için "
                "Ön kontrol panelini inceleyin.",
                8000,
            )
            return

        mode = (
            CaptureMode.GUIDED if self._guided_button.isChecked() else CaptureMode.FREE
        )
        try:
            take = service.start_recording(
                workspace,
                session,
                exercise=self._exercise_input.text().strip(),
                notes=self._note_input.toPlainText().strip(),
                protocol_task_id=self._active_task.task_id if self._active_task else None,
                capture_mode=mode,
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        except Exception as exc:
            self.state.notify(f"Kayıt başlatılamadı: {exc}", 6000)
            return
        self.state.notify(f"Kayıt başladı: {take.take_id}")
        self._update_controls()

    def _stop_recording(self) -> None:
        service = self.state.capture
        if service is None:
            return
        take = service.stop_recording()
        self._update_controls()
        if take is None:
            return
        self._last_take = take
        self.state.notify(
            f"Kayıt tamamlandı: {take.metrics.frames_written} kare, "
            f"{take.metrics.duration_s:.1f} sn"
        )
        self._note_input.clear()
        self._ask_verdict(take)

    def _ask_verdict(self, take: Take) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        dialog = TakeVerdictDialog(take, self.theme, self)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if accepted:
            take.quality = dialog.quality
            if dialog.note:
                take.notes = f"{take.notes}\n{dialog.note}".strip()
            try:
                workspace.save_take(take)
            except KineCaptureError as exc:
                self.state.report_error(exc)
        self.state.notify_take_saved(take)
        if accepted and dialog.review_requested:
            self.state.request_review(take)
        elif accepted and take.quality is TakeQuality.RETAKE:
            self.state.notify("Tekrar çekim için hazır. R tuşuyla yeniden kaydedin.")

    def _add_marker(self) -> None:
        service = self.state.capture
        if service is None or not service.is_recording:
            return
        marker = service.add_marker("operator")
        if marker:
            self.state.notify(f"Marker: kare {marker['frame_index']}", 2000)

    def _review_last(self) -> None:
        if self._last_take is not None:
            self.state.request_review(self._last_take)
            return
        index = self.state.index
        if index is not None:
            recent = index.recent(1)
            if recent:
                self.state.request_review(recent[0].take)
                return
        self.state.notify("İncelenecek kayıt yok.", 4000)

    # -------------------------------------------------------------- controls
    def _update_controls(self) -> None:
        service = self.state.capture
        connected = service is not None and service.state is not CaptureState.DISCONNECTED
        recording = service is not None and service.is_recording
        previewing = service is not None and service.state in (
            CaptureState.PREVIEWING,
            CaptureState.RECORDING,
        )

        self._connect_button.setText("Bağlantıyı kes" if connected else "Bağlan")
        self._backend_selector.setEnabled(not recording)
        self._preview_button.setEnabled(connected and not recording)
        self._preview_button.blockSignals(True)
        self._preview_button.setChecked(previewing)
        self._preview_button.blockSignals(False)
        self._record_button.setEnabled(previewing)
        self._record_button.setText(
            "Kaydı durdur  (Esc)" if recording else "Kaydı başlat  (R)"
        )
        self._marker_button.setEnabled(recording)
        self._guided_button.setEnabled(not recording)
        self._free_button.setEnabled(not recording)
        self._exercise_input.setEnabled(not recording)

        capabilities = service.backend.capabilities() if service else None
        depth_index = self._view_selector.findData("depth")
        if capabilities is not None and depth_index >= 0:
            # Capability-driven: an unavailable view is disabled and explained,
            # never silently shown as an empty panel.
            model = self._view_selector.model()
            item = model.item(depth_index)
            item.setEnabled(capabilities.depth)
            self._view_selector.setItemData(
                depth_index,
                "Bu backend derinlik sağlamıyor." if not capabilities.depth else "",
                Qt.ItemDataRole.ToolTipRole,
            )
            if not capabilities.depth and self._view_selector.currentIndex() == depth_index:
                self._view_selector.setCurrentIndex(self._view_selector.findData("rgb"))


__all__ = ["CapturePage", "TakeVerdictDialog"]
