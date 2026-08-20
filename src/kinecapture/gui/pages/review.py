"""Review and label: synchronised playback, repetition editing, annotation.

Playback is driven by a ``QTimer``, never a blocking loop, so the window stays
responsive at any speed and the user can scrub while it plays.

Video and skeleton are advanced from the *same* position index and the elapsed
time shown comes from the recorded camera timestamps, so a dropped frame appears
as a gap in the timeline rather than being smoothed away by an assumed frame
rate.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.enums import (
    AnnotationStatus,
    Correctness,
    SegmentStatus,
    TakeQuality,
)
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import RepetitionSegment, Take
from kinecapture.playback.take_reader import LoadedTake, load_take
from kinecapture.gui.icons import get_icon
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    EmptyState,
    FieldRow,
    KeyValueList,
    StatusChip,
    make_button,
    make_label,
)
from kinecapture.gui.widgets.skeleton_view import VIEW_PRESETS, SkeletonView3D
from kinecapture.gui.widgets.timeline import TimelineWidget
from kinecapture.gui.widgets.video_view import VideoView

_CORRECTNESS_ORDER = (
    Correctness.CORRECT,
    Correctness.INCORRECT,
    Correctness.UNCERTAIN,
    Correctness.UNKNOWN,
)

_STATUS_LABELS = {
    AnnotationStatus.DRAFT: "Taslak",
    AnnotationStatus.REVIEWED: "İncelendi",
    AnnotationStatus.APPROVED: "Onaylandı",
    AnnotationStatus.EXCLUDED: "Dışlandı",
}

_PLAYBACK_SPEEDS = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)


class ReviewPage(Page):
    """Playback, repetition segmentation and labelling for one take."""

    navigate_requested = Signal(str)

    title = "İnceleme ve Etiketleme"
    description = (
        "Kaydı senkron oynatın, tekrar aralıklarını düzenleyin ve etiketleyin."
    )
    icon = "review"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme
        self._loaded: Optional[LoadedTake] = None
        self._repo: Optional[AnnotationRepository] = None
        self._position = 0
        self._playing = False
        self._speed = 1.0
        self._loop_selected = False
        self._suppress_form = False

        self._take_selector = QComboBox()
        self._take_selector.setMinimumWidth(320)
        self._take_selector.currentIndexChanged.connect(self._take_selected)
        self.header.add_action(make_label("Kayıt", role="caption"))
        self.header.add_action(self._take_selector)

        self._autosave_chip = StatusChip("Kaydedildi", theme=theme, icon="check")
        self.header.add_action(self._autosave_chip)

        self._empty = EmptyState(
            "İncelenecek kayıt yok",
            "Önce bir kayıt alın veya bir proje açın.",
            theme=theme,
            icon="capture",
            action_text="Capture ekranına git",
        )
        self._empty.action_triggered.connect(
            lambda: self.navigate_requested.emit("capture")
        )
        self.content.addWidget(self._empty)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(theme.space_sm)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_viewer(theme))
        splitter.addWidget(self._build_side(theme))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([880, 480])
        body.addWidget(splitter, 1)

        body.addWidget(self._build_transport(theme))
        body.addWidget(self._build_timeline(theme))
        self.content.addWidget(self._body, 1)

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave)

        self._install_shortcuts()
        state.dataset_changed.connect(self._reload_take_list)
        state.review_requested.connect(self.open_take)
        self._set_empty(True)

    # --------------------------------------------------------------- layout
    def _build_viewer(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_sm)

        views = QSplitter(Qt.Orientation.Horizontal)

        video_card = Card("Görüntü", theme=theme, icon="camera")
        self._video = VideoView(theme, placeholder_text="Proxy video yok")
        self._overlay_toggle = make_button("Bindirme", icon="skeleton", theme=theme)
        self._overlay_toggle.setCheckable(True)
        self._overlay_toggle.setChecked(True)
        self._overlay_toggle.toggled.connect(self._video.set_overlay_enabled)
        video_card.add_header_widget(self._overlay_toggle)
        video_card.add_widget(self._video, 1)
        views.addWidget(video_card)

        skeleton_card = Card("3B iskelet", theme=theme, icon="skeleton")
        self._preset_selector = QComboBox()
        for preset in VIEW_PRESETS:
            self._preset_selector.addItem(preset.label, preset.key)
        self._preset_selector.setCurrentIndex(2)
        self._preset_selector.currentIndexChanged.connect(
            lambda: self._skeleton.set_preset(self._preset_selector.currentData())
        )
        skeleton_card.add_header_widget(self._preset_selector)
        self._center_toggle = make_button("Merkezle", icon="target", theme=theme)
        self._center_toggle.setCheckable(True)
        self._center_toggle.setChecked(True)
        self._center_toggle.setToolTip(
            "Yalnızca görüntüleme için kök merkezleme; ham veri değişmez."
        )
        skeleton_card.add_header_widget(self._center_toggle)
        self._skeleton = SkeletonView3D(theme)
        self._center_toggle.toggled.connect(self._skeleton.set_root_centered)
        skeleton_card.add_widget(self._skeleton, 1)
        views.addWidget(skeleton_card)

        views.setSizes([540, 460])
        layout.addWidget(views, 1)
        return wrapper

    def _build_side(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        info_card = Card("Kayıt bilgisi", theme=theme, icon="info")
        self._take_chip = StatusChip("-", theme=theme, icon="info")
        info_card.add_header_widget(self._take_chip)
        self._take_details = KeyValueList(theme)
        info_card.add_widget(self._take_details)
        quality_row = QHBoxLayout()
        self._quality_selector = QComboBox()
        for quality in TakeQuality:
            self._quality_selector.addItem(quality.value, quality.value)
        self._quality_selector.currentIndexChanged.connect(self._quality_changed)
        quality_row.addWidget(make_label("Kalite kararı", role="caption"))
        quality_row.addWidget(self._quality_selector, 1)
        quality_container = QWidget()
        quality_container.setLayout(quality_row)
        info_card.add_widget(quality_container)
        layout.addWidget(info_card)

        rep_card = Card(
            "Tekrarlar",
            subtitle="Zaman çizelgesinde sürükleyerek oluşturun ve düzenleyin.",
            theme=theme,
            icon="list",
        )
        self._segment_list = QListWidget()
        self._segment_list.currentItemChanged.connect(
            lambda current, _: self._segment_selected(current)
        )
        rep_card.add_widget(self._segment_list, 1)

        buttons = QHBoxLayout()
        for text, icon, handler, tooltip in (
            ("Ekle", "add", self._create_segment_here, "Oynatma konumunda yeni tekrar (N)"),
            ("Böl", "split", self._split_segment, "Seçili tekrarı konumdan böl (S)"),
            ("Birleştir", "merge", self._merge_segments, "Seçiliyi sonrakiyle birleştir"),
            ("Dışla", "eye", self._toggle_exclude, "Datasetten çıkar / geri al (X)"),
            ("Sil", "trash", self._delete_segment, "Tekrar aralığını sil"),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        button_container = QWidget()
        button_container.setLayout(buttons)
        rep_card.add_widget(button_container)

        extra = QHBoxLayout()
        markers_button = make_button(
            "Marker'lardan oluştur",
            icon="marker",
            theme=theme,
            tooltip="Kayıt sırasında bırakılan marker'ları sınır olarak kullan",
        )
        markers_button.clicked.connect(self._segments_from_markers)
        extra.addWidget(markers_button)
        self._loop_button = make_button(
            "Seçiliyi döngüle", icon="refresh", theme=theme
        )
        self._loop_button.setCheckable(True)
        self._loop_button.toggled.connect(self._toggle_loop)
        extra.addWidget(self._loop_button)
        extra.addStretch(1)
        extra_container = QWidget()
        extra_container.setLayout(extra)
        rep_card.add_widget(extra_container)
        layout.addWidget(rep_card, 1)

        layout.addWidget(self._build_annotation_card(theme))
        return wrapper

    def _build_annotation_card(self, theme: Theme) -> QWidget:
        card = Card(
            "Etiket",
            subtitle="Değişiklikler otomatik kaydedilir.",
            theme=theme,
            icon="edit",
        )
        self._exercise_selector = QComboBox()
        self._exercise_selector.setEditable(True)
        self._exercise_selector.currentTextChanged.connect(self._annotation_edited)
        self._exercise_row = FieldRow(
            "Egzersiz", self._exercise_selector, theme=theme, required=True
        )
        card.add_widget(self._exercise_row)

        correctness_row = QHBoxLayout()
        self._correctness_buttons: dict[Correctness, QWidget] = {}
        for correctness in _CORRECTNESS_ORDER:
            button = make_button(
                LabelSchema.label_for_correctness(correctness), theme=theme
            )
            button.setCheckable(True)
            button.clicked.connect(
                lambda _=False, c=correctness: self._set_correctness(c)
            )
            self._correctness_buttons[correctness] = button
            correctness_row.addWidget(button)
        correctness_container = QWidget()
        correctness_container.setLayout(correctness_row)
        card.add_widget(
            FieldRow(
                "Değerlendirme (1-4)",
                correctness_container,
                theme=theme,
                required=True,
            )
        )

        self._error_types = QLineEdit()
        self._error_types.setPlaceholderText("Virgülle ayırın (şemada tanımlı kodlar)")
        self._error_types.editingFinished.connect(self._annotation_edited)
        card.add_widget(
            FieldRow(
                "Hata türleri",
                self._error_types,
                theme=theme,
                help_text="Hata ontolojisi proje etiket şemasında tanımlanır.",
            )
        )

        self._affected_joints = QLineEdit()
        self._affected_joints.setPlaceholderText("Örn. left_knee, pelvis")
        self._affected_joints.editingFinished.connect(self._annotation_edited)
        card.add_widget(
            FieldRow("Etkilenen eklemler", self._affected_joints, theme=theme)
        )

        detail_row = QHBoxLayout()
        self._phase_selector = QComboBox()
        self._phase_selector.setEditable(True)
        self._phase_selector.currentTextChanged.connect(self._annotation_edited)
        detail_row.addWidget(FieldRow("Hareket fazı", self._phase_selector, theme=theme))
        self._severity = QDoubleSpinBox()
        self._severity.setRange(0.0, 10.0)
        self._severity.setSingleStep(0.5)
        self._severity.setSpecialValueText("-")
        self._severity.valueChanged.connect(lambda _: self._annotation_edited())
        detail_row.addWidget(FieldRow("Şiddet", self._severity, theme=theme))
        self._confidence = QDoubleSpinBox()
        self._confidence.setRange(0.0, 1.0)
        self._confidence.setSingleStep(0.1)
        self._confidence.setSpecialValueText("-")
        self._confidence.valueChanged.connect(lambda _: self._annotation_edited())
        detail_row.addWidget(
            FieldRow("Etiket güveni", self._confidence, theme=theme)
        )
        detail_container = QWidget()
        detail_container.setLayout(detail_row)
        card.add_widget(detail_container)

        self._note = QPlainTextEdit()
        self._note.setMaximumHeight(56)
        self._note.textChanged.connect(self._annotation_edited)
        card.add_widget(FieldRow("Not", self._note, theme=theme))

        self._status_selector = QComboBox()
        for status in AnnotationStatus:
            self._status_selector.addItem(_STATUS_LABELS[status], status.value)
        self._status_selector.currentIndexChanged.connect(self._annotation_edited)
        card.add_widget(FieldRow("Durum", self._status_selector, theme=theme))

        actions = QHBoxLayout()
        for text, icon, handler, tooltip in (
            ("Öncekini kopyala", "list", self._copy_previous, "Önceki tekrarın etiketini kopyala (C)"),
            ("Tümüne uygula", "check", self._apply_all, "Bu etiketi tüm tekrarlara uygula"),
            ("Geri al", "undo", self._undo, "Ctrl+Z"),
            ("Yinele", "redo", self._redo, "Ctrl+Y"),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        next_button = make_button(
            "Sonraki etiketsiz",
            variant="primary",
            icon="chevron-right",
            theme=theme,
            tooltip="Etiketsiz bir sonraki kayda geç",
        )
        next_button.clicked.connect(self._next_unlabelled)
        actions.addWidget(next_button)
        actions_container = QWidget()
        actions_container.setLayout(actions)
        card.add_widget(actions_container)

        self._problem_label = make_label("", role="error")
        self._problem_label.setWordWrap(True)
        card.add_widget(self._problem_label)
        self._annotation_card = card
        return card

    def _build_transport(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        row = QHBoxLayout()
        row.setSpacing(theme.space_sm)

        for text, icon, handler, tooltip in (
            ("", "step-back", lambda: self._step(-1), "Bir kare geri (,)"),
            ("", "play", self._toggle_play, "Oynat / duraklat (Boşluk)"),
            ("", "stop", self._stop, "Durdur"),
            ("", "step-forward", lambda: self._step(1), "Bir kare ileri (.)"),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            row.addWidget(button)
            if icon == "play":
                self._play_button = button

        self._speed_selector = QComboBox()
        for speed in _PLAYBACK_SPEEDS:
            self._speed_selector.addItem(f"{speed:g}x", speed)
        self._speed_selector.setCurrentIndex(_PLAYBACK_SPEEDS.index(1.0))
        self._speed_selector.currentIndexChanged.connect(self._speed_changed)
        row.addWidget(self._speed_selector)

        self._body_selector = QComboBox()
        self._body_selector.currentIndexChanged.connect(self._redraw)
        row.addWidget(make_label("Gövde", role="caption"))
        row.addWidget(self._body_selector)

        row.addSpacing(theme.space_md)
        self._position_label = make_label("-", role="muted")
        row.addWidget(self._position_label)
        row.addStretch(1)

        zoom_fit = make_button("Tümünü göster", icon="search", theme=theme)
        zoom_fit.clicked.connect(lambda: self._timeline.zoom_to_fit())
        row.addWidget(zoom_fit)

        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        return card

    def _build_timeline(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        self._timeline = TimelineWidget(theme)
        self._timeline.position_changed.connect(self._seek)
        self._timeline.segment_selected.connect(self._select_segment_by_id)
        self._timeline.segment_bounds_changed.connect(self._segment_bounds_changed)
        self._timeline.segment_create_requested.connect(self._create_segment_range)
        self._timeline.segment_double_clicked.connect(self._zoom_to_segment)
        card.add_widget(self._timeline)
        legend = make_label(
            "Katmanlar: veri kapsamı · takip güveni · marker'lar · tekrarlar   —   "
            "Sürükle: aralık oluştur/taşı · Tekerlek: yakınlaştır · Shift+Tekerlek: kaydır",
            role="muted",
        )
        legend.setWordWrap(True)
        card.add_widget(legend)
        return card

    def _install_shortcuts(self) -> None:
        def add(sequence: str, handler) -> None:  # type: ignore[no-untyped-def]
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

        add("Space", self._guarded(self._toggle_play))
        add(",", self._guarded(lambda: self._step(-1)))
        add(".", self._guarded(lambda: self._step(1)))
        add("N", self._guarded(self._create_segment_here))
        add("S", self._guarded(self._split_segment))
        add("X", self._guarded(self._toggle_exclude))
        add("C", self._guarded(self._copy_previous))
        add("Ctrl+Z", self._undo)
        add("Ctrl+Y", self._redo)
        add("Ctrl+S", self._save_now)
        for number, correctness in enumerate(_CORRECTNESS_ORDER, start=1):
            add(str(number), self._guarded(lambda c=correctness: self._set_correctness(c)))

    def _guarded(self, handler):  # type: ignore[no-untyped-def]
        """Wrap a shortcut so it never fires while the user is typing."""

        def wrapper() -> None:
            widget = self.focusWidget()
            if isinstance(widget, (QLineEdit, QPlainTextEdit)):
                return
            if isinstance(widget, QComboBox) and widget.isEditable():
                return
            handler()

        return wrapper

    # ---------------------------------------------------------------- state
    def _set_empty(self, empty: bool) -> None:
        self._empty.setVisible(empty)
        self._body.setVisible(not empty)

    def on_activated(self) -> None:
        self._reload_take_list()

    def on_deactivated(self) -> None:
        self._pause()
        self._save_now()

    def can_leave(self) -> bool:
        self._save_now()
        return True

    def _reload_take_list(self) -> None:
        index = self.state.index
        current = self._loaded.take.take_id if self._loaded else None
        self._take_selector.blockSignals(True)
        self._take_selector.clear()
        rows = list(index.rows) if index else []
        for row in rows:
            take = row.take
            flag = " [SENTETİK]" if take.is_synthetic else ""
            state_flag = " [YARIM]" if take.is_recoverable_partial else ""
            label = (
                f"{row.participant_code} · Kayıt {take.index_in_session} · "
                f"{take.started_at[:16].replace('T', ' ')} · "
                f"{row.repetition_count} tekrar ({row.labelled_count} etiketli)"
                f"{flag}{state_flag}"
            )
            self._take_selector.addItem(label, take.take_id)
        self._take_selector.blockSignals(False)
        if not rows:
            self._set_empty(True)
            return
        self._set_empty(False)
        position = self._take_selector.findData(current)
        if position >= 0:
            self._take_selector.setCurrentIndex(position)
        elif self._loaded is None:
            self._take_selector.setCurrentIndex(0)
            self._take_selected()

    def _take_selected(self) -> None:
        take_id = self._take_selector.currentData()
        index = self.state.index
        if not take_id or index is None:
            return
        row = index.row_for(take_id)
        if row is not None and (
            self._loaded is None or self._loaded.take.take_id != take_id
        ):
            self.open_take(row.take)

    def open_take(self, take: Take) -> None:
        """Load a take for review; called by the page and by other pages."""
        workspace = self.state.workspace
        if workspace is None:
            return
        self._save_now()
        self._pause()
        if self._loaded is not None:
            self._loaded.close()
            self._loaded = None

        try:
            loaded = load_take(workspace, take)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return

        self._loaded = loaded
        self._repo = AnnotationRepository(
            workspace,
            take,
            frame_count=loaded.frame_count,
            annotator=self.state.session.operator if self.state.session else "",
        )
        self._repo.add_change_listener(self._on_repo_changed)
        self._set_empty(False)

        position = self._take_selector.findData(take.take_id)
        if position >= 0 and position != self._take_selector.currentIndex():
            self._take_selector.blockSignals(True)
            self._take_selector.setCurrentIndex(position)
            self._take_selector.blockSignals(False)

        self._populate_schema_choices()
        self._reload_body_selector()
        self._reload_timeline()
        self._refresh_take_info()
        self._refresh_segment_list()
        self._seek(0)

        if loaded.stream.truncated:
            self.state.notify(
                "Bu kaydın akışı yarım kalmış; son satır okunamadı. "
                "Yazılan kareler kullanılabilir.",
                8000,
            )
        if not loaded.has_video:
            reason = loaded.video.unavailable_reason if loaded.video else "-"
            self._video.set_placeholder_text(
                f"Proxy video yok ({reason}).\nİskelet oynatma çalışmaya devam eder."
            )

    def _populate_schema_choices(self) -> None:
        schema = self.state.label_schema
        self._suppress_form = True
        self._exercise_selector.clear()
        self._exercise_selector.addItem("", "")
        for option in schema.exercises:
            self._exercise_selector.addItem(option.label, option.code)
        self._phase_selector.clear()
        self._phase_selector.addItem("")
        for option in schema.movement_phases:
            self._phase_selector.addItem(option.label, option.code)
        self._suppress_form = False

    def _reload_body_selector(self) -> None:
        if self._loaded is None:
            return
        self._body_selector.blockSignals(True)
        self._body_selector.clear()
        self._body_selector.addItem("Otomatik", None)
        for tracking_id in self._loaded.stream.tracking_ids:
            self._body_selector.addItem(f"ID {tracking_id}", tracking_id)
        self._body_selector.blockSignals(False)

    def _reload_timeline(self) -> None:
        if self._loaded is None:
            return
        stream = self._loaded.stream
        tracking_id = self._body_selector.currentData()
        coverage = stream.coverage_curve(tracking_id)
        markers = [
            stream.position_of_frame_index(int(m.get("frame_index", 0)))
            for m in stream.markers
        ]
        gaps = [
            position
            for position, _ in stream.timestamp_gaps(target_fps=self._loaded.target_fps)
        ]
        self._timeline.set_take(
            self._loaded.frame_count,
            fps=self._loaded.target_fps,
            markers=markers,
            coverage=coverage,
            gaps=gaps,
        )
        if self._repo is not None:
            self._timeline.set_segments(self._repo.segments)

    def _refresh_take_info(self) -> None:
        if self._loaded is None:
            return
        take = self._loaded.take
        metrics = take.metrics
        stream = self._loaded.stream
        camera = take.camera_info

        if take.is_synthetic:
            self._take_chip.set_status(
                "SENTETİK", icon="flask", colour=self.theme.synthetic
            )
        elif take.is_recoverable_partial:
            self._take_chip.set_status(
                "Yarım kayıt", icon="warning", colour=self.theme.warning
            )
        else:
            self._take_chip.set_status(
                "Gerçek kayıt", icon="check", colour=self.theme.success
            )

        gaps = stream.timestamp_gaps(target_fps=self._loaded.target_fps)
        self._take_details.set_items(
            [
                ("Kayıt", take.take_id),
                ("Katılımcı / oturum", f"{take.participant_id} / {take.session_id[-12:]}"),
                ("Kare", f"{stream.frame_count} (kaydedilen {metrics.frames_written})"),
                (
                    "Süre",
                    f"{stream.duration_s:.2f} sn (kamera zaman damgasından)",
                ),
                (
                    "FPS",
                    f"{metrics.measured_fps:.1f} ölçülen / {metrics.target_fps:.0f} hedef",
                ),
                ("Zaman boşluğu", f"{len(gaps)} yerde kare eksik" if gaps else "yok"),
                ("Takip kapsamı", f"%{metrics.tracking_coverage * 100:.0f}"),
                ("İskelet biçimi", take.skeleton_format or "-"),
                (
                    "Koordinat",
                    f"{camera.coordinate_system} · {camera.length_unit}"
                    if camera
                    else "-",
                ),
                ("Kamera", camera.display_name if camera else "-"),
                ("Backend", camera.backend if camera else "-"),
                ("Native kayıt", take.files.get("native_recording", "yok")),
            ]
        )
        self._quality_selector.blockSignals(True)
        self._quality_selector.setCurrentIndex(
            self._quality_selector.findData(take.quality.value)
        )
        self._quality_selector.blockSignals(False)

    # -------------------------------------------------------------- playback
    def _toggle_play(self) -> None:
        if self._loaded is None:
            return
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        if self._loaded is None or self._loaded.frame_count == 0:
            return
        self._playing = True
        interval = max(8, int(1000.0 / (self._loaded.target_fps * self._speed)))
        self._play_timer.start(interval)
        self._play_button.setIcon(get_icon("pause", self.theme.text_primary, 16))

    def _pause(self) -> None:
        self._playing = False
        self._play_timer.stop()
        self._play_button.setIcon(get_icon("play", self.theme.text_primary, 16))

    def _stop(self) -> None:
        self._pause()
        self._seek(0)

    def _speed_changed(self) -> None:
        self._speed = float(self._speed_selector.currentData())
        if self._playing:
            self._play()

    def _advance(self) -> None:
        if self._loaded is None:
            return
        loop = self._timeline.loop_range
        following = self._position + 1
        if loop is not None and (following > loop[1] or self._position < loop[0]):
            following = loop[0]
        elif following >= self._loaded.frame_count:
            following = 0
            if loop is None:
                self._pause()
                self._seek(self._loaded.frame_count - 1)
                return
        self._seek(following)

    def _step(self, delta: int) -> None:
        if self._loaded is None:
            return
        self._pause()
        self._seek(self._position + delta)

    def _seek(self, position: int) -> None:
        if self._loaded is None:
            return
        self._position = int(
            np.clip(position, 0, max(0, self._loaded.frame_count - 1))
        )
        self._timeline.set_position(self._position)
        self._redraw()

    def _redraw(self) -> None:
        loaded = self._loaded
        if loaded is None:
            return
        frame = loaded.stream.frame_at(self._position)
        tracking_id = self._body_selector.currentData()

        if loaded.has_video and loaded.video is not None:
            image = loaded.video.read_at(loaded.video_position_for(self._position))
            if image is not None:
                self._video.set_rgb(image)
        bodies = frame.bodies if frame else ()
        self._video.set_bodies(bodies, loaded.spec, active_id=tracking_id)
        self._skeleton.set_bodies(bodies, loaded.spec, active_id=tracking_id)

        if frame is not None and loaded.stream.frames:
            first = loaded.stream.frames[0].camera_timestamp_ns
            elapsed = (
                (frame.camera_timestamp_ns - first) / 1e9
                if first and frame.camera_timestamp_ns
                else self._position / loaded.target_fps
            )
            self._position_label.setText(
                f"Konum {self._position + 1}/{loaded.frame_count}  ·  "
                f"kayıt karesi {frame.frame_index}  ·  {elapsed:.2f} sn"
            )

    # ------------------------------------------------------------- segments
    def _on_repo_changed(self) -> None:
        self._refresh_segment_list()
        if self._repo is not None:
            self._timeline.set_segments(self._repo.segments)
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._autosave_chip.set_status(
            "Kaydedilmedi", icon="edit", colour=self.theme.warning
        )
        if self.state.config.autosave_enabled:
            self._autosave_timer.start(self.state.config.autosave_delay_ms)

    def _autosave(self) -> None:
        if self._repo is None:
            return
        try:
            if self._repo.save_if_dirty():
                self._autosave_chip.set_status(
                    "Otomatik kaydedildi", icon="check", colour=self.theme.success
                )
                self.state.refresh_dataset(force=True)
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _save_now(self) -> None:
        self._autosave_timer.stop()
        self._autosave()

    def _refresh_segment_list(self) -> None:
        if self._repo is None:
            return
        current = self._current_segment_id()
        self._segment_list.blockSignals(True)
        self._segment_list.clear()
        for segment in self._repo.segments:
            annotation = segment.annotation
            flags = []
            if not segment.is_active:
                flags.append("dışlandı")
            if annotation.is_labelled:
                flags.append(LabelSchema.label_for_correctness(annotation.correctness))
            else:
                flags.append("etiketsiz")
            label = (
                f"{segment.index}. kare {segment.start_frame}-{segment.end_frame} "
                f"({segment.frame_count})  ·  "
                f"{annotation.exercise or '—'}  ·  {' / '.join(flags)}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, segment.segment_id)
            self._segment_list.addItem(item)
            if segment.segment_id == current:
                self._segment_list.setCurrentItem(item)
        self._segment_list.blockSignals(False)

        problems = self._repo.validation_problems()
        self._problem_label.setText(
            "  ·  ".join(problem["message"] for problem in problems)
        )
        self._annotation_card.set_subtitle(
            f"{self._repo.labelled_count}/{len(self._repo.active_segments)} tekrar "
            "etiketlendi. Değişiklikler otomatik kaydedilir."
        )
        self._load_annotation_form()

    def _current_segment_id(self) -> Optional[str]:
        item = self._segment_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _current_segment(self) -> Optional[RepetitionSegment]:
        if self._repo is None:
            return None
        segment_id = self._current_segment_id()
        return self._repo.find(segment_id) if segment_id else None

    def _segment_selected(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        segment_id = item.data(Qt.ItemDataRole.UserRole)
        self._timeline.set_selected(segment_id)
        segment = self._repo.find(segment_id) if self._repo else None
        if segment is not None:
            self._seek(segment.start_frame)
            if self._loop_selected:
                self._timeline.set_loop_range((segment.start_frame, segment.end_frame))
        self._load_annotation_form()

    def _select_segment_by_id(self, segment_id: str) -> None:
        for row in range(self._segment_list.count()):
            item = self._segment_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == segment_id:
                self._segment_list.setCurrentItem(item)
                return

    def _create_segment_here(self) -> None:
        if self._repo is None or self._loaded is None:
            return
        span = max(2, int(self._loaded.target_fps))
        end = min(self._loaded.frame_count - 1, self._position + span)
        self._create_segment_range(self._position, end)

    def _create_segment_range(self, start: int, end: int) -> None:
        if self._repo is None or self._loaded is None:
            return
        frames = self._loaded.stream.frames
        start_ts = frames[start].camera_timestamp_ns if start < len(frames) else None
        end_ts = frames[end].camera_timestamp_ns if end < len(frames) else None
        try:
            segment = self._repo.create_segment(
                start, end, start_timestamp_ns=start_ts, end_timestamp_ns=end_ts
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._select_segment_by_id(segment.segment_id)

    def _segment_bounds_changed(self, segment_id: str, start: int, end: int) -> None:
        if self._repo is None:
            return
        try:
            self._repo.update_bounds(segment_id, start, end)
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _split_segment(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        try:
            self._repo.split(segment.segment_id, self._position)
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)

    def _merge_segments(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        ordered = list(self._repo.segments)
        position = next(
            (i for i, s in enumerate(ordered) if s.segment_id == segment.segment_id), -1
        )
        if position < 0 or position + 1 >= len(ordered):
            self.state.notify("Birleştirilecek bir sonraki tekrar yok.", 4000)
            return
        try:
            merged = self._repo.merge(
                segment.segment_id, ordered[position + 1].segment_id
            )
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)
            return
        self._select_segment_by_id(merged.segment_id)

    def _toggle_exclude(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        target = (
            SegmentStatus.EXCLUDED if segment.is_active else SegmentStatus.ACTIVE
        )
        self._repo.set_status(segment.segment_id, target)

    def _delete_segment(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        answer = QMessageBox.question(
            self,
            "Tekrarı sil",
            f"{segment.index}. tekrar aralığı silinsin mi?\n\n"
            "Bu yalnızca etiket verisini siler; kayıt kareleri korunur.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._repo.delete(segment.segment_id)

    def _segments_from_markers(self) -> None:
        if self._repo is None or self._loaded is None:
            return
        stream = self._loaded.stream
        positions = [
            stream.position_of_frame_index(int(m.get("frame_index", 0)))
            for m in stream.markers
        ]
        if not positions:
            self.state.notify("Bu kayıtta marker yok.", 4000)
            return
        created = self._repo.create_from_markers(
            positions, final_frame=self._loaded.frame_count - 1
        )
        self.state.notify(f"{len(created)} tekrar aralığı önerildi.")

    def _toggle_loop(self, enabled: bool) -> None:
        self._loop_selected = enabled
        segment = self._current_segment()
        if enabled and segment is not None:
            self._timeline.set_loop_range((segment.start_frame, segment.end_frame))
        else:
            self._timeline.set_loop_range(None)

    def _zoom_to_segment(self, segment_id: str) -> None:
        if self._repo is None:
            return
        segment = self._repo.find(segment_id)
        if segment is not None:
            self._timeline.zoom_to_range(segment.start_frame, segment.end_frame)

    # ------------------------------------------------------------ annotation
    def _load_annotation_form(self) -> None:
        segment = self._current_segment()
        self._annotation_card.setEnabled(segment is not None)
        if segment is None:
            return
        annotation = segment.annotation
        self._suppress_form = True

        position = self._exercise_selector.findData(annotation.exercise)
        if position >= 0:
            self._exercise_selector.setCurrentIndex(position)
        else:
            self._exercise_selector.setCurrentText(annotation.exercise)
        for correctness, button in self._correctness_buttons.items():
            button.setChecked(correctness is annotation.correctness)
        self._error_types.setText(", ".join(annotation.error_types))
        self._affected_joints.setText(", ".join(annotation.affected_joints))
        phase_position = self._phase_selector.findData(annotation.movement_phase)
        if phase_position >= 0:
            self._phase_selector.setCurrentIndex(phase_position)
        else:
            self._phase_selector.setCurrentText(annotation.movement_phase)
        self._severity.setValue(annotation.severity or 0.0)
        self._confidence.setValue(annotation.annotator_confidence or 0.0)
        self._note.setPlainText(annotation.note)
        self._status_selector.setCurrentIndex(
            self._status_selector.findData(annotation.status.value)
        )
        self._exercise_row.set_error(
            "" if annotation.exercise else "Egzersiz seçilmedi."
        )
        self._suppress_form = False

    def _annotation_edited(self) -> None:
        if self._suppress_form or self._repo is None:
            return
        segment = self._current_segment()
        if segment is None:
            return
        exercise = self._exercise_selector.currentData()
        if exercise is None:
            exercise = self._exercise_selector.currentText().strip()
        self._repo.annotate(
            segment.segment_id,
            exercise=exercise,
            error_types=[
                value.strip()
                for value in self._error_types.text().split(",")
                if value.strip()
            ],
            affected_joints=[
                value.strip()
                for value in self._affected_joints.text().split(",")
                if value.strip()
            ],
            movement_phase=(
                self._phase_selector.currentData()
                or self._phase_selector.currentText().strip()
            ),
            severity=self._severity.value() or None,
            annotator_confidence=self._confidence.value() or None,
            note=self._note.toPlainText().strip(),
            status=AnnotationStatus(self._status_selector.currentData()),
        )

    def _set_correctness(self, correctness: Correctness) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        self._repo.annotate(segment.segment_id, correctness=correctness)
        for value, button in self._correctness_buttons.items():
            button.setChecked(value is correctness)

    def _copy_previous(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        ordered = list(self._repo.segments)
        position = next(
            (i for i, s in enumerate(ordered) if s.segment_id == segment.segment_id), 0
        )
        if position == 0:
            self.state.notify("Kopyalanacak önceki tekrar yok.", 4000)
            return
        self._repo.copy_annotation_from(
            ordered[position - 1].segment_id, segment.segment_id
        )
        self._load_annotation_form()

    def _apply_all(self) -> None:
        segment = self._current_segment()
        if segment is None or self._repo is None:
            return
        annotation = segment.annotation
        answer = QMessageBox.question(
            self,
            "Tümüne uygula",
            f"'{annotation.exercise or '—'}' / "
            f"'{LabelSchema.label_for_correctness(annotation.correctness)}' "
            "etiketi bu kayıttaki tüm tekrarlara uygulansın mı?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count = self._repo.apply_to_all(
            exercise=annotation.exercise, correctness=annotation.correctness
        )
        self.state.notify(f"{count} tekrar güncellendi.")

    def _undo(self) -> None:
        if self._repo is not None and self._repo.undo():
            self._load_annotation_form()

    def _redo(self) -> None:
        if self._repo is not None and self._repo.redo():
            self._load_annotation_form()

    def _quality_changed(self) -> None:
        workspace = self.state.workspace
        if self._loaded is None or workspace is None:
            return
        take = self._loaded.take
        value = self._quality_selector.currentData()
        if value == take.quality.value:
            return
        take.quality = TakeQuality(value)
        try:
            workspace.save_take(take)
            self.state.refresh_dataset(force=True)
            self.state.notify(f"Kalite kararı: {take.quality.value}")
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _next_unlabelled(self) -> None:
        index = self.state.index
        if index is None:
            return
        self._save_now()
        rows = index.needing_review()
        current = self._loaded.take.take_id if self._loaded else None
        for row in rows:
            if row.take.take_id != current:
                self.open_take(row.take)
                return
        self.state.notify("Etiketlenmemiş başka kayıt yok.", 4000)


__all__ = ["ReviewPage"]
