"""Review and label: playback, movement segmentation, error localisation.

Two writable layers, and only two:

* **Hareket** - the repetitions across the take, each with an exercise class.
* **Hata** - inside one selected repetition, the stretches where the error is
  visible, each with an error class.

Correct-or-incorrect is not a third thing to fill in: a repetition with a
classified error interval is incorrect and one without is correct, so the
second layer *is* the verdict.

The screen is built around one idea: *the picture and the timeline are the
work*, everything else is a window you open when you need it. So the take
metadata, the quality decision and the diagnostics live in a modeless info
window behind one button, the class forms live in small dialogs that open on a
double click, and what stays permanently on screen is the viewer, a compact row
of actions, the timeline, and any alert the user has to act on now.

**Only the person selected during recording is drawn.** ``subject_body()`` is
the single authority; if it does not find the subject in a frame, the frame is
drawn without a skeleton and says so. Nothing is substituted, nothing is frozen
from the previous frame, and the other bodies in shot are not drawn at all - not
even dimmed, because a dim skeleton in a review screen reads as "this is your
participant, tracked poorly" rather than "this is somebody else".

Playback is driven by a ``QTimer``, never a blocking loop, so the window stays
responsive at any speed and the user can scrub while it plays. Video and
skeleton advance from the *same* position index, and the elapsed time shown
comes from the recorded camera timestamps, so a dropped frame appears as a gap
rather than being smoothed away by an assumed frame rate.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.enums import (
    SampleReadiness,
    SegmentStatus,
    TakeQuality,
)
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import ErrorInterval, MovementSample
from kinecapture.gui.icons import get_icon
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    ElidedLabel,
    EmptyState,
    KeyValueList,
    StatusChip,
    make_button,
    make_label,
    restyle,
)
from kinecapture.gui.widgets.flow_layout import flow_row
from kinecapture.gui.widgets.info_window import InfoWindow
from kinecapture.gui.widgets.joint_picker import describe_joint_annotation
from kinecapture.gui.widgets.label_dialogs import ErrorLabelDialog, MovementLabelDialog
from kinecapture.gui.widgets.scene_view import SceneMode, SceneView
from kinecapture.gui.widgets.skeleton_view import VIEW_PRESETS
from kinecapture.gui.widgets.timeline import TimelineMode, TimelineWidget
from kinecapture.playback.take_reader import LoadedTake, load_take

_PLAYBACK_SPEEDS = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)

#: Icon, short label and colour role for each readiness state.
_READINESS_PRESENTATION = {
    SampleReadiness.READY: ("check", "Hazır", "success"),
    SampleReadiness.UNLABELLED: ("edit", "Etiketlenmedi", "text_muted"),
    SampleReadiness.NEEDS_ERROR_INTERVAL: (
        "target",
        "Hata aralığı bekliyor",
        "warning",
    ),
    SampleReadiness.CONTRADICTION: ("warning", "Çelişki", "danger"),
    SampleReadiness.INVALID_INTERVAL: ("error", "Geçersiz aralık", "danger"),
    SampleReadiness.LEGACY_CONFLICT: ("warning", "Eski karar çelişkisi", "danger"),
    SampleReadiness.EXCLUDED: ("eye", "Dışlandı", "text_muted"),
}

#: Shown on the viewer when the participant was not tracked in this frame. It
#: has to be unmistakably about *this frame*, or it reads as a broken take.
_SUBJECT_ABSENT = "Seçilen kişi bu karede bulunamadı — iskelet çizilmiyor."


class ReviewPage(Page):
    """Playback, movement segmentation and two-level labelling for one take."""

    navigate_requested = Signal(str)

    title = "İnceleme ve Etiketleme"
    description = (
        "Hareketleri işaretleyin ve hatanın tam olarak nerede göründüğünü "
        "gösterin. Doğru/hatalı kararı hata aralıklarından türetilir."
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
        self._selected_sample_id: Optional[str] = None
        self._selected_interval_id: Optional[str] = None
        self._info: Optional[InfoWindow] = None
        #: Where the playhead was when a trim drag began, so it can go back
        #: there afterwards rather than to wherever the mouse was released.
        self._playhead_before_edit: Optional[int] = None

        self._take_selector = QComboBox()
        self._take_selector.setMinimumWidth(240)
        # Row labels carry the participant, the take number, the timestamp and
        # the progress count, so the *longest* one must not become the page's
        # minimum width. The popup still shows every row in full.
        self._take_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._take_selector.setMinimumContentsLength(20)
        self._take_selector.setMaximumWidth(340)
        self._take_selector.setToolTip("İncelenecek kaydı seçin")
        self._take_selector.currentIndexChanged.connect(self._take_selected)
        # No "Kayıt" caption beside it: every row already begins with the
        # participant code and the take number, and the header is the single
        # most width-constrained row on the page.
        self.header.add_action(self._take_selector)

        self._autosave_chip = StatusChip("Kaydedildi", theme=theme, icon="check")
        self.header.add_action(self._autosave_chip)
        info_button = make_button(
            "Kayıt bilgisi",
            icon="info",
            theme=theme,
            tooltip="Kayıt bilgisi, kalite kararı ve tanılama penceresi (F4)",
        )
        info_button.clicked.connect(self._toggle_info)
        self.header.add_action(info_button)

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
        # The viewer takes every pixel the timeline and the action row do not
        # need. There is no side column any more: reference material moved into
        # the info window, forms into dialogs. The actions live in the same
        # card as the timeline because that is what they act on, and because a
        # third card's padding is 30px the camera view can have instead.
        body.addWidget(self._build_viewer(theme), 1)
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
        self._sync_mode_ui()

    # --------------------------------------------------------------- layout
    def _build_viewer(self, theme: Theme) -> QWidget:
        card = Card("Görüntü", theme=theme, icon="camera", compact=True)

        self._subject_chip = StatusChip("Kişi -", theme=theme, icon="user")
        card.add_header_widget(self._subject_chip)

        self._mode_buttons: dict[SceneMode, QWidget] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for mode in SceneMode:
            button = make_button(mode.label, icon=mode.icon, theme=theme)
            button.setCheckable(True)
            button.setToolTip(f"Görüntü modu: {mode.label}")
            button.clicked.connect(lambda _=False, m=mode: self._set_scene_mode(m))
            group.addButton(button)
            card.add_header_widget(button)
            self._mode_buttons[mode] = button
        self._mode_buttons[SceneMode.OVERLAY].setChecked(True)

        self._scene = SceneView(theme, mode=SceneMode.OVERLAY)
        card.add_widget(self._scene, 1)

        controls = QHBoxLayout()
        controls.setSpacing(theme.space_sm)
        self._preset_selector = QComboBox()
        for preset in VIEW_PRESETS:
            self._preset_selector.addItem(preset.label, preset.key)
        self._preset_selector.setCurrentIndex(2)
        self._preset_selector.currentIndexChanged.connect(
            lambda: self._scene.set_skeleton_preset(self._preset_selector.currentData())
        )
        controls.addWidget(make_label("3B görünüm", role="caption"))
        controls.addWidget(self._preset_selector)

        self._center_toggle = make_button("Merkezle", icon="target", theme=theme)
        self._center_toggle.setCheckable(True)
        self._center_toggle.setChecked(True)
        self._center_toggle.setToolTip(
            "Yalnızca görüntüleme için kök merkezleme; ham veri değişmez."
        )
        self._center_toggle.toggled.connect(self._scene.set_root_centered)
        controls.addWidget(self._center_toggle)

        # One status line under the picture, not two. The left half is the
        # alert - never hidden, never scrolled away, because everything that
        # appears there is something the user must know before trusting what
        # they just looked at. The right half is where they are in the take.
        self._alert = ElidedLabel("", role="muted")
        controls.addWidget(self._alert, 3)

        self._position_label = ElidedLabel("-", role="muted")
        self._position_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        controls.addWidget(self._position_label, 2)

        container = QWidget()
        container.setLayout(controls)
        card.add_widget(container)
        return card

    def _build_actions(self, theme: Theme) -> QWidget:
        """The whole editing vocabulary, on one row, always visible.

        Two primary verbs and five utilities. Anything that needs more than a
        button - choosing a class, deciding a verdict - opens on a double click
        instead of living permanently on screen.

        Wrapping, not clipping: at 1120px this row becomes two lines rather
        than pushing the page into a horizontal scroll.
        """
        widgets: list[QWidget] = []

        self._add_movement_button = make_button(
            "Hareket ekle",
            variant="primary",
            icon="add",
            theme=theme,
            tooltip="Oynatma konumunda yeni hareket aralığı (N)",
        )
        self._add_movement_button.clicked.connect(self._create_sample_here)
        widgets.append(self._add_movement_button)

        self._add_error_button = make_button(
            "Hata ekle",
            icon="target",
            theme=theme,
            tooltip="Seçili hareketin içinde yeni hata aralığı (E)",
        )
        self._add_error_button.clicked.connect(self._create_interval_here)
        widgets.append(self._add_error_button)

        self._label_button = make_button(
            "Etiketle",
            icon="edit",
            theme=theme,
            tooltip="Seçili aralığın etiket penceresini aç (Enter veya çift tık)",
        )
        self._label_button.clicked.connect(self._label_selection)
        widgets.append(self._label_button)

        self._delete_button = make_button(
            icon="trash",
            theme=theme,
            tooltip="Seçili aralığı sil (Delete)",
        )
        self._delete_button.clicked.connect(self._delete_selection)
        widgets.append(self._delete_button)

        self._undo_button = make_button(
            icon="undo", theme=theme, tooltip="Geri al (Ctrl+Z)"
        )
        self._undo_button.clicked.connect(self._undo)
        widgets.append(self._undo_button)

        self._redo_button = make_button(
            icon="redo", theme=theme, tooltip="Yinele (Ctrl+Y)"
        )
        self._redo_button.clicked.connect(self._redo)
        widgets.append(self._redo_button)

        self._loop_button = make_button(
            icon="refresh",
            theme=theme,
            tooltip="Seçili aralığı döngüde oynat (L)",
        )
        self._loop_button.setCheckable(True)
        self._loop_button.toggled.connect(self._toggle_loop)
        widgets.append(self._loop_button)

        self._progress_chip = StatusChip("0/0 hazır", theme=theme, icon="check")
        widgets.append(self._progress_chip)

        self._next_button = make_button(
            "Sonraki eksik",
            icon="chevron-right",
            theme=theme,
            tooltip=(
                "Bu kayıtta etiketi eksik bir sonraki harekete, kalmadıysa "
                "eksik bir sonraki kayda geç"
            ),
        )
        self._next_button.clicked.connect(self._go_to_next_gap)
        widgets.append(self._next_button)

        more = make_button(
            icon="list",
            theme=theme,
            tooltip="Böl, birleştir, dışla, marker'lardan oluştur, yakınlaştır",
        )
        more.clicked.connect(self._show_more_menu)
        widgets.append(more)
        self._more_button = more

        return flow_row(widgets, spacing=theme.space_xs)

    def _build_transport(self, theme: Theme) -> QWidget:
        """Playback controls. Lives inside the timeline card: they are one tool,
        and a separate card costs ~40px of vertical space a 768px screen needs."""
        row = QHBoxLayout()
        row.setSpacing(theme.space_xs)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._timeline_mode_buttons: dict[TimelineMode, QWidget] = {}
        for mode, icon, tip in (
            (
                TimelineMode.MOVEMENT,
                "list",
                "Kayıttaki hareket tekrarlarını çizin ve düzenleyin (F1)",
            ),
            (
                TimelineMode.ERROR,
                "target",
                "Seçili hareketin İÇİNDE hatanın göründüğü aralıkları işaretleyin (F2)",
            ),
        ):
            button = make_button(mode.label, icon=icon, theme=theme, tooltip=tip)
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, m=mode: self._set_timeline_mode(m))
            self._mode_group.addButton(button)
            row.addWidget(button)
            self._timeline_mode_buttons[mode] = button
        self._timeline_mode_buttons[TimelineMode.MOVEMENT].setChecked(True)

        row.addSpacing(theme.space_md)
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

        row.addStretch(1)
        # A hint, not a control: it may wrap to a second line rather than
        # setting a minimum width the whole page then has to honour.
        self._mode_hint = make_label("", role="muted")
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self._mode_hint, 2)

        container = QWidget()
        container.setLayout(row)
        return container

    def _build_timeline(self, theme: Theme) -> QWidget:
        card = Card(theme=theme, compact=True)
        card.add_widget(self._build_actions(theme))
        card.add_widget(self._build_transport(theme))
        self._timeline = TimelineWidget(theme)
        self._timeline.position_changed.connect(self._seek)
        self._timeline.sample_selected.connect(self._select_sample_by_id)
        self._timeline.sample_bounds_changed.connect(self._sample_bounds_changed)
        self._timeline.sample_create_requested.connect(self._create_sample_range)
        self._timeline.sample_double_clicked.connect(self._open_movement_dialog)
        self._timeline.interval_selected.connect(self._select_interval_by_id)
        self._timeline.interval_bounds_changed.connect(self._interval_bounds_changed)
        self._timeline.interval_create_requested.connect(self._create_interval_range)
        self._timeline.interval_double_clicked.connect(self._open_error_dialog)
        self._timeline.edit_started.connect(self._edit_started)
        self._timeline.preview_position_changed.connect(self._preview_position)
        self._timeline.edit_finished.connect(self._edit_finished)
        self._timeline.edit_cancelled.connect(self._edit_finished)
        card.add_widget(self._timeline)

        self._status_label = ElidedLabel("", role="muted")
        card.add_widget(self._status_label)
        return card

    # ----------------------------------------------------------- info window
    def _ensure_info(self) -> InfoWindow:
        if self._info is not None:
            return self._info
        theme = self.theme
        window = InfoWindow("Kayıt bilgileri", theme, self)

        card = Card("Kayıt bilgisi", theme=theme, icon="info")
        self._take_chip = StatusChip("-", theme=theme, icon="info")
        card.add_header_widget(self._take_chip)
        self._take_details = KeyValueList(theme)
        card.add_widget(self._take_details)
        window.add_card(card)

        quality_card = Card("Kalite kararı", theme=theme, icon="check")
        self._quality_selector = QComboBox()
        for quality in TakeQuality:
            self._quality_selector.addItem(quality.value, quality.value)
        self._quality_selector.currentIndexChanged.connect(self._quality_changed)
        quality_card.add_widget(self._quality_selector)
        window.add_card(quality_card)

        diagnostics = Card("Görüntü tanılaması", theme=theme, icon="camera")
        self._diagnostics = KeyValueList(theme)
        diagnostics.add_widget(self._diagnostics)
        window.add_card(diagnostics)

        legacy = Card("Etiket geçmişi", theme=theme, icon="timeline")
        self._legacy_note = make_label("", role="muted")
        self._legacy_note.setWordWrap(True)
        legacy.add_widget(self._legacy_note)
        window.add_card(legacy)

        self._info = window
        return window

    def _toggle_info(self) -> None:
        window = self._ensure_info()
        self._refresh_take_info()
        window.toggle()

    # -------------------------------------------------------------- more menu
    def _show_more_menu(self) -> None:
        """The rarely-used structural edits, out of the way but reachable."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        for text, handler, enabled in (
            ("Hareketi böl (S)", self._split_sample, self._current_sample() is not None),
            (
                "Sonraki hareketle birleştir",
                self._merge_samples,
                self._current_sample() is not None,
            ),
            (
                "Datasetten çıkar / geri al (X)",
                self._toggle_exclude,
                self._current_sample() is not None,
            ),
            ("Marker'lardan hareket oluştur", self._samples_from_markers, True),
            ("Seçili aralığa yakınlaş", self._zoom_selected, True),
            ("Tüm kaydı göster", lambda: self._timeline.zoom_to_fit(), True),
        ):
            action = menu.addAction(text)
            action.setEnabled(enabled)
            action.triggered.connect(handler)
        menu.exec(self._more_button.mapToGlobal(self._more_button.rect().bottomLeft()))

    # ----------------------------------------------------------- shortcuts
    def _install_shortcuts(self) -> None:
        def add(sequence: str, handler) -> None:  # type: ignore[no-untyped-def]
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(handler)

        add("Space", self._guarded(self._toggle_play))
        add(",", self._guarded(lambda: self._step(-1)))
        add(".", self._guarded(lambda: self._step(1)))
        add("N", self._guarded(self._create_sample_here))
        add("E", self._guarded(self._create_interval_here))
        add("S", self._guarded(self._split_sample))
        add("X", self._guarded(self._toggle_exclude))
        add("L", self._guarded(lambda: self._loop_button.toggle()))
        add("Return", self._guarded(self._label_selection))
        add("Enter", self._guarded(self._label_selection))
        add("Delete", self._guarded(self._delete_selection))
        add("F1", self._guarded(lambda: self._set_timeline_mode(TimelineMode.MOVEMENT)))
        add("F2", self._guarded(lambda: self._set_timeline_mode(TimelineMode.ERROR)))
        add("F4", self._toggle_info)
        add("Ctrl+Z", self._undo)
        add("Ctrl+Y", self._redo)
        add("Ctrl+S", self._save_now)
        for index, mode in enumerate(SceneMode, start=1):
            add(f"Ctrl+{index}", self._guarded(lambda m=mode: self._set_scene_mode(m)))

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

    # ----------------------------------------------------------------- mode
    def _set_scene_mode(self, mode: SceneMode) -> None:
        self._scene.set_mode(mode)
        for candidate, button in self._mode_buttons.items():
            button.setChecked(candidate is mode)
        # The 3D controls only mean anything in the skeleton view.
        is_skeleton = mode is SceneMode.SKELETON
        self._preset_selector.setEnabled(is_skeleton)
        self._center_toggle.setEnabled(is_skeleton)
        self._redraw()

    def _set_timeline_mode(self, mode: TimelineMode) -> None:
        if mode is TimelineMode.ERROR and self._current_sample() is None:
            self.state.notify(
                "Hata aralığı işaretlemek için önce bir hareket seçin.", 4000
            )
            self._timeline_mode_buttons[TimelineMode.MOVEMENT].setChecked(True)
            return
        self._timeline.set_mode(mode)
        for candidate, button in self._timeline_mode_buttons.items():
            button.setChecked(candidate is mode)
        self._sync_mode_ui()

    def _sync_mode_ui(self) -> None:
        mode = self._timeline.mode
        sample = self._current_sample()
        if mode is TimelineMode.MOVEMENT:
            self._mode_hint.setText(
                "HAREKET şeridinde sürükleyerek tekrar çizin · çift tık: etiketle"
            )
        else:
            name = f"Hareket {sample.index}" if sample else "Seçili hareket"
            self._mode_hint.setText(
                f"{name} içinde HATA şeridinde sürükleyin · çift tık: etiketle"
            )
        self._add_error_button.setEnabled(sample is not None)
        self._refresh_status_line()

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
            flags = []
            if take.is_synthetic:
                flags.append("SENTETİK")
            if take.is_recoverable_partial:
                flags.append("YARIM")
            label = (
                f"{row.participant_code} · Kayıt {take.index_in_session} · "
                f"{take.started_at[:16].replace('T', ' ')} · "
                f"{row.labelled_count}/{row.movement_count} hazır"
            )
            if flags:
                label += "  [" + " ".join(flags) + "]"
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

    def open_take(self, take) -> None:  # type: ignore[no-untyped-def]
        """Load a take for review; called by this page and by other pages."""
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
        self._selected_sample_id = None
        self._selected_interval_id = None
        self._set_empty(False)

        position = self._take_selector.findData(take.take_id)
        if position >= 0 and position != self._take_selector.currentIndex():
            self._take_selector.blockSignals(True)
            self._take_selector.setCurrentIndex(position)
            self._take_selector.blockSignals(False)

        # The overlay's coordinate frame, declared once per take. The proxy
        # video is a downscaled copy of the camera image, so the 2D joints are
        # NOT in the displayed picture's pixels; see SceneView.set_joint_space.
        self._scene.set_joint_space(
            loaded.joint_pixel_space, calibration=loaded.camera_calibration
        )
        self._populate_schema_choices()
        self._reload_timeline()
        self._refresh_take_info()
        self._refresh_sample_state()
        self._scene.set_video_available(
            loaded.has_video,
            loaded.video.unavailable_reason if loaded.video else "Proxy video yok.",
        )
        self._set_timeline_mode(TimelineMode.MOVEMENT)
        self._seek(0)

        if loaded.stream.truncated:
            self.state.notify(
                "Bu kaydın akışı yarım kalmış; son satır okunamadı. "
                "Yazılan kareler kullanılabilir.",
                8000,
            )
        if not loaded.has_video:
            self.state.notify(
                "Proxy video yok; RGB modları boş görünür, İskelet modu çalışır.",
                6000,
            )
        if not loaded.has_subject_lock:
            self.state.notify(
                "Bu kayıt kişi kilidi olmadan alınmış. Ekranda kayıtta en çok "
                "görünen gövde çizilir ve bu bir tahmindir; doğruluğunu "
                "etiketlemeden önce kendiniz doğrulayın.",
                10000,
            )

    def _populate_schema_choices(self) -> None:
        schema = self.state.label_schema
        self._timeline.set_error_labels(
            {o.code: o.label for o in schema.error_types}
        )

    def _reload_timeline(self) -> None:
        if self._loaded is None:
            return
        stream = self._loaded.stream
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
            # The coverage curve describes the person being drawn, and nobody
            # else. Plotting the best-tracked body here used to claim full
            # coverage over the exact stretch where the participant was lost.
            coverage=self._loaded.subject_coverage_curve(),
            gaps=gaps,
        )
        if self._repo is not None:
            self._timeline.set_samples(self._repo.samples)

    def _refresh_take_info(self) -> None:
        if self._loaded is None or self._info is None:
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
                ("Süre", f"{stream.duration_s:.2f} sn (kamera zaman damgasından)"),
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
            ]
        )

        space = self._loaded.joint_pixel_space
        calibration = self._loaded.camera_calibration
        self._diagnostics.set_items(
            [
                ("Proxy video", "var" if self._loaded.has_video else "yok"),
                (
                    "Proxy kare sayısı",
                    f"{self._loaded.video.frame_count} "
                    f"(eksik {self._loaded.proxy_frame_shortfall})"
                    if self._loaded.video is not None
                    else "-",
                ),
                (
                    "2B eklem uzayı",
                    f"{space[0]}x{space[1]} px (kamera görüntüsü)"
                    if space
                    else "bilinmiyor",
                ),
                (
                    "Kalibrasyon",
                    "var (fx/fy/cx/cy kayıtlı)" if calibration else "yok",
                ),
                (
                    "Kişi kilidi",
                    "var" if self._loaded.has_subject_lock else "yok (eski kayıt)",
                ),
                (
                    "Çizilen kimlik",
                    str(stream.subject_id or "-")
                    if self._loaded.has_subject_lock
                    else f"tahmin: ID {self._loaded.legacy_tracking_id}",
                ),
            ]
        )

        activity_count = len(self._repo.activity_intervals) if self._repo else 0
        self._legacy_note.setText(
            "Aktivite etiketleme bu sürümde kaldırıldı. Daha önce girilmiş "
            f"{activity_count} aktivite aralığı dosyada olduğu gibi korunuyor; "
            "silinmiyor, dönüştürülmüyor ve buradan düzenlenemiyor."
            if activity_count
            else "Bu kayıtta eski aktivite etiketi yok."
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
        self._pause() if self._playing else self._play()

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
        self._position = int(np.clip(position, 0, max(0, self._loaded.frame_count - 1)))
        self._timeline.set_position(self._position)
        self._redraw()

    # --------------------------------------------------------------- drawing
    def _redraw(self, position: Optional[int] = None) -> None:
        """Draw one position: the selected person, on their own colour frame.

        ``position`` defaults to the playhead. Passing one draws that frame
        *without* moving anything - the trim preview looks at a frame the way
        you would hold a strip of film up to the light, and the playhead stays
        where the user left it.

        Everything here is deliberately allowed to come out empty. A missing
        subject, a missing proxy frame and an unprojectable skeleton are three
        different facts, each stated rather than papered over.
        """
        loaded = self._loaded
        if loaded is None:
            return
        if position is None:
            position = self._position
        position = int(np.clip(position, 0, max(0, loaded.frame_count - 1)))
        frame = loaded.stream.frame_at(position)
        body = loaded.review_body_at(position)
        bodies = (body,) if body is not None else ()

        rgb = None
        rgb_missing = ""
        if loaded.has_video and loaded.video is not None:
            video_position = loaded.video_position_for(position)
            if video_position is None:
                # No colour frame for this position. The previous one is not a
                # substitute: it would show this pose over another moment.
                rgb_missing = (
                    "Bu konum için renkli kare yok "
                    f"(proxy {loaded.video.frame_count} kare, akış "
                    f"{loaded.frame_count} kare)."
                )
            else:
                rgb = loaded.video.read_at(video_position)
                if rgb is None:
                    rgb_missing = "Bu karenin görüntüsü proxy videodan okunamadı."

        # Say when the overlay would have to be guessed, instead of guessing.
        overlay_reason = ""
        if bodies and not self._scene.can_overlay(bodies):
            overlay_reason = (
                "Bu kayıtta 2B eklem konumu ve kamera kalibrasyonu yok; "
                "RGB üzerine iskelet çizilemez. İskelet modunu kullanın."
            )
        self._scene.set_overlay_unavailable(overlay_reason)
        self._scene.set_frame(
            rgb,
            bodies,
            loaded.spec,
            active_id=body.tracking_id if body is not None else None,
            rgb_missing_reason=rgb_missing,
        )

        self._refresh_subject_chip(body)
        self._refresh_alert(body, rgb_missing, overlay_reason)

        if frame is not None and loaded.stream.frames:
            first = loaded.stream.frames[0].camera_timestamp_ns
            elapsed = (
                (frame.camera_timestamp_ns - first) / 1e9
                if first and frame.camera_timestamp_ns
                else position / loaded.target_fps
            )
            inside = ""
            sample = self._current_sample()
            if sample is not None and sample.contains(position):
                inside = f"  ·  hareket {sample.index} içinde"
            previewing = (
                "  ·  ÖNİZLEME" if self._playhead_before_edit is not None else ""
            )
            self._position_label.setText(
                f"Konum {position + 1}/{loaded.frame_count}  ·  "
                f"kayıt karesi {frame.frame_index}  ·  {elapsed:.2f} sn"
                f"{inside}{previewing}"
            )

    # ------------------------------------------------------- trim preview
    def _edit_started(self) -> None:
        """A bounds drag began: pause, and remember where we were."""
        if self._playhead_before_edit is None:
            self._playhead_before_edit = self._position
        self._pause()

    def _preview_position(self, frame: int) -> None:
        """Show the frame under the dragged endpoint, in whichever view is up.

        Deliberately not a seek. ``self._position`` and the timeline playhead
        are untouched, so the three scene modes all show this frame and the
        take's own idea of "where am I" survives the drag intact.
        """
        if self._loaded is None:
            return
        self._redraw(frame)

    def _edit_finished(self) -> None:
        """The drag is over - put the playhead back exactly where it started."""
        restore, self._playhead_before_edit = self._playhead_before_edit, None
        if restore is None:
            return
        # Paused, not playing: an edit should never start playback on its own.
        self._pause()
        self._seek(restore)

    def _refresh_subject_chip(self, body) -> None:  # type: ignore[no-untyped-def]
        loaded = self._loaded
        if loaded is None:
            return
        theme = self.theme
        if not loaded.has_subject_lock:
            self._subject_chip.set_status(
                f"Kilit yok · tahmin ID {loaded.legacy_tracking_id}"
                if loaded.legacy_tracking_id is not None
                else "Kilit yok · gövde yok",
                icon="warning",
                colour=theme.warning,
            )
            return
        if body is None:
            self._subject_chip.set_status(
                "Kişi bu karede yok", icon="warning", colour=theme.warning
            )
            return
        self._subject_chip.set_status(
            f"Seçili kişi · ID {body.tracking_id}",
            icon="user",
            colour=theme.success,
        )

    def _refresh_alert(self, body, rgb_missing: str, overlay_reason: str) -> None:  # type: ignore[no-untyped-def]
        """The one line on the main screen the user must not be able to miss."""
        loaded = self._loaded
        parts: list[str] = []
        if loaded is not None and loaded.has_subject_lock and body is None:
            parts.append(_SUBJECT_ABSENT)
        if rgb_missing:
            parts.append(rgb_missing)
        if overlay_reason:
            parts.append(overlay_reason)
        text = "  ·  ".join(parts)
        self._alert.setText(text)
        self._alert.setProperty("role", "error" if text else "muted")
        restyle(self._alert)

    # ------------------------------------------------------------ repository
    def _on_repo_changed(self) -> None:
        self._refresh_sample_state()
        if self._repo is not None:
            self._timeline.set_samples(self._repo.samples)
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
                    "Kaydedildi", icon="check", colour=self.theme.success
                )
                self._autosave_chip.setToolTip(
                    "Etiketler otomatik olarak diske yazıldı."
                )
                self.state.refresh_dataset(force=True)
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _save_now(self) -> None:
        self._autosave_timer.stop()
        self._autosave()

    # -------------------------------------------------------------- selection
    def _current_sample(self) -> Optional[MovementSample]:
        if self._repo is None or not self._selected_sample_id:
            return None
        return self._repo.find(self._selected_sample_id)

    def _current_interval(self) -> Optional[ErrorInterval]:
        sample = self._current_sample()
        if sample is None or not self._selected_interval_id:
            return None
        return sample.interval(self._selected_interval_id)

    def _readiness_text(self, sample: MovementSample) -> str:
        assert self._repo is not None
        _icon, text, _colour = _READINESS_PRESENTATION[self._repo.readiness(sample)]
        return text

    def _refresh_sample_state(self) -> None:
        """Everything derived from the label data, in one place."""
        if self._repo is None:
            return
        ready = self._repo.ready_count
        total = len(self._repo.active_samples)
        self._progress_chip.set_status(
            f"{ready}/{total} hazır",
            icon="check" if ready == total and total else "edit",
            colour=self.theme.success if total and ready == total else self.theme.warning,
        )
        self._undo_button.setEnabled(self._repo.can_undo)
        self._redo_button.setEnabled(self._repo.can_redo)
        self._refresh_status_line()

    def _refresh_status_line(self) -> None:
        if self._repo is None:
            return
        parts: list[str] = []
        sample = self._current_sample()
        if sample is None:
            parts.append(
                "Hareket seçilmedi. Zaman çizelgesinde sürükleyin veya "
                "“Hareket ekle”."
            )
        else:
            interval = self._current_interval()
            exercise = (
                self.state.label_schema.label_for_exercise(sample.exercise)
                if sample.exercise
                else "— tür yok"
            )
            parts.append(
                f"Seçili: {sample.index}. hareket · {exercise} · "
                f"{LabelSchema.label_for_correctness(sample.derived_correctness)} · "
                f"{len(sample.error_intervals)} hata aralığı · "
                f"{self._readiness_text(sample)}"
            )
            if interval is not None:
                name = (
                    self.state.label_schema.label_for_error(interval.error_code)
                    if interval.error_code
                    else "— tür seçilmedi"
                )
                parts.append(
                    f"Hata aralığı {interval.start_frame}-{interval.end_frame}: "
                    f"{name} · {describe_joint_annotation(interval)}"
                )
            problems = self._repo.problems(sample)
            if problems:
                parts.append(" · ".join(p.message for p in problems))
        structural = self._repo.validation_problems()
        if structural:
            parts.append(" · ".join(p["message"] for p in structural))
        self._status_label.setText("  |  ".join(parts))
        self._status_label.setProperty(
            "role", "error" if (structural or self._has_problem()) else "muted"
        )
        restyle(self._status_label)

    def _has_problem(self) -> bool:
        sample = self._current_sample()
        return bool(sample is not None and self._repo and self._repo.problems(sample))

    def _select_sample_by_id(self, sample_id: str) -> None:
        if self._repo is None:
            return
        self._selected_sample_id = sample_id
        self._selected_interval_id = None
        self._timeline.set_selected_sample(sample_id)
        sample = self._repo.find(sample_id)
        if sample is not None:
            self._seek(sample.start_frame)
            if self._loop_selected:
                self._timeline.set_loop_range((sample.start_frame, sample.end_frame))
        self._sync_mode_ui()

    def _select_interval_by_id(self, interval_id: str) -> None:
        self._selected_interval_id = interval_id
        self._timeline.set_selected_interval(interval_id)
        interval = self._current_interval()
        if interval is not None:
            self._seek(interval.start_frame)
            if self._loop_selected:
                self._timeline.set_loop_range(
                    (interval.start_frame, interval.end_frame)
                )
        self._refresh_status_line()

    # ------------------------------------------------------- label dialogs
    def _run_dialog(self, dialog) -> bool:  # type: ignore[no-untyped-def]
        """Show a label dialog and report whether it was saved.

        The single place this page blocks on a modal, so a test can drive the
        whole labelling flow by replacing this one method - the dialog itself
        stays exactly the widget the user gets.
        """
        return dialog.exec() == dialog.DialogCode.Accepted

    def _label_selection(self) -> None:
        """Open whichever label window matches the current mode and selection."""
        if self._timeline.mode is TimelineMode.ERROR:
            interval = self._current_interval()
            if interval is not None:
                self._open_error_dialog(interval.interval_id)
                return
            self.state.notify("Etiketlenecek hata aralığı seçilmedi.", 4000)
            return
        sample = self._current_sample()
        if sample is not None:
            self._open_movement_dialog(sample.sample_id)
            return
        self.state.notify("Etiketlenecek hareket seçilmedi.", 4000)

    def _open_movement_dialog(self, sample_id: str) -> None:
        if self._repo is None:
            return
        sample = self._repo.find(sample_id)
        if sample is None:
            return
        self._pause()
        self._select_sample_by_id(sample_id)
        dialog = MovementLabelDialog(
            self.theme, sample, self.state.label_schema, parent=self
        )
        accepted = self._run_dialog(dialog)
        created = self._create_requested_classes(dialog.requested_classes)
        if not accepted:
            # Cancel abandons the assignment, not the vocabulary: see the
            # dialog's module docstring for why the two differ.
            self._refresh_sample_state()
            return

        exercise = dialog.exercise
        if dialog.pending_new_class:
            option = created.get(dialog.pending_new_class)
            if option is None:
                return
            exercise = option
        try:
            # ``reviewed=True`` is what Save means: the class review of this
            # movement is finished. With no classified error interval that
            # makes it correct and export-ready immediately - the verdict is
            # read off the intervals, so there is nothing else to confirm.
            updated = self._repo.label_sample(
                sample_id, exercise=exercise, note=dialog.note, reviewed=True
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(
            f"Hareket {updated.index}: "
            + (
                "hata aralığı yok → DOĞRU kabul edildi."
                if not updated.has_localised_error
                else f"{len(updated.localised_error_codes)} hata aralığı → HATALI."
            ),
            5000,
        )

    def _open_error_dialog(self, interval_id: str) -> None:
        if self._repo is None:
            return
        self._select_interval_by_id(interval_id)
        sample = self._current_sample()
        interval = self._current_interval()
        if sample is None or interval is None:
            return
        self._pause()
        dialog = ErrorLabelDialog(
            self.theme,
            interval,
            self.state.label_schema,
            # The joints on offer come from the take being edited, not from
            # whatever the camera happens to be configured for right now.
            skeleton_spec=self._loaded.spec if self._loaded else None,
            parent=self,
        )
        # Playing loops the interval behind the dialog; it no longer closes it,
        # so watching the movement again cannot commit a half-made decision.
        dialog.play_requested_now.connect(self._loop_interval)
        accepted = self._run_dialog(dialog)
        created = self._create_requested_classes(dialog.requested_classes)
        if not accepted:
            self._refresh_sample_state()
            return
        if dialog.delete_requested:
            self._repo.delete_error_interval(sample.sample_id, interval.interval_id)
            self._selected_interval_id = None
            self._refresh_sample_state()
            return

        code = dialog.error_code
        if dialog.pending_new_class:
            option = created.get(dialog.pending_new_class)
            if option is None:
                return
            code = option
        try:
            # One call, one snapshot, one autosave. Class, joints and note were
            # decided together and are written together.
            self._repo.update_error_interval(
                sample.sample_id,
                interval.interval_id,
                error_code=code or None,
                note=dialog.note,
                joint_status=dialog.joint_status,
                affected_roles=dialog.affected_roles,
                skeleton_spec=self._loaded.spec if self._loaded else None,
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return

    def _create_requested_classes(self, names: list[str]) -> dict[str, str]:
        """Persist every class the user asked for; report name -> code.

        Runs whether the dialog was saved or cancelled. Adding a class edits the
        *project*, not this take's labels, so it survives a cancelled dialog and
        stays out of the annotation undo stack - undoing a label must not
        un-define a class other takes may already be using.
        """
        created: dict[str, str] = {}
        if self._repo is None or not names:
            return created
        kind_is_error = self._timeline.mode is TimelineMode.ERROR
        for name in names:
            try:
                option = (
                    self._repo.ensure_error_class(name)
                    if kind_is_error
                    else self._repo.ensure_movement_class(name)
                )
            except KineCaptureError as exc:
                self.state.notify(exc.user_text(), 6000)
                continue
            created[name] = option.code
        if created:
            self._populate_schema_choices()
            self.state.notify(
                f"{len(created)} yeni tür projeye eklendi: "
                + ", ".join(sorted(created)),
                5000,
            )
        return created

    # ------------------------------------------------------ movement editing
    def _create_sample_here(self) -> None:
        if self._repo is None or self._loaded is None:
            return
        span = max(2, int(self._loaded.target_fps))
        end = min(self._loaded.frame_count - 1, self._position + span)
        self._create_sample_range(self._position, end)

    def _create_sample_range(self, start: int, end: int) -> None:
        if self._repo is None or self._loaded is None:
            return
        frames = self._loaded.stream.frames
        try:
            sample = self._repo.create_sample(
                start,
                end,
                start_timestamp_ns=frames[start].camera_timestamp_ns
                if start < len(frames)
                else None,
                end_timestamp_ns=frames[end].camera_timestamp_ns
                if end < len(frames)
                else None,
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._select_sample_by_id(sample.sample_id)
        # No modal here on purpose. Segmenting a take means drawing a dozen
        # repetitions in a row; a dialog after each one turns that into a dozen
        # interruptions. Labelling is a separate, explicit act: Enter, the
        # "Etiketle" button, or a double click on the band.
        self.state.notify(
            "Hareket eklendi. Etiketlemek için çift tıklayın veya Enter'a basın.",
            5000,
        )

    def _sample_bounds_changed(self, sample_id: str, start: int, end: int) -> None:
        if self._repo is None:
            return
        try:
            report = self._repo.update_sample_bounds(sample_id, start, end)
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        if not report.is_lossless:
            # Never lose a localised error silently.
            self.state.notify(report.message(), 9000)

    def _split_sample(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        try:
            self._repo.split_sample(sample.sample_id, self._position)
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)

    def _merge_samples(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        ordered = list(self._repo.samples)
        position = next(
            (i for i, s in enumerate(ordered) if s.sample_id == sample.sample_id), -1
        )
        if position < 0 or position + 1 >= len(ordered):
            self.state.notify("Birleştirilecek bir sonraki hareket yok.", 4000)
            return
        try:
            report = self._repo.merge_samples(
                sample.sample_id, ordered[position + 1].sample_id
            )
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)
            return
        self.state.notify(report.message(), 9000 if report.had_conflict else 4000)
        self._select_sample_by_id(sample.sample_id)

    def _toggle_exclude(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        target = SegmentStatus.EXCLUDED if sample.is_active else SegmentStatus.ACTIVE
        self._repo.set_sample_status(sample.sample_id, target)

    def _delete_selection(self) -> None:
        """Delete whatever is selected in the current mode."""
        if self._timeline.mode is TimelineMode.ERROR:
            self._delete_interval()
            return
        self._delete_sample()

    def _delete_sample(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            self.state.notify("Silinecek hareket seçilmedi.", 4000)
            return
        extra = (
            f"\n\nBu hareketteki {len(sample.error_intervals)} hata aralığı da silinir."
            if sample.error_intervals
            else ""
        )
        answer = QMessageBox.question(
            self,
            "Hareketi sil",
            f"{sample.index}. hareket aralığı silinsin mi?{extra}\n\n"
            "Bu yalnızca etiket verisini siler; kayıt kareleri korunur.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._repo.delete_sample(sample.sample_id)
        self._selected_sample_id = None
        self._refresh_sample_state()

    def _samples_from_markers(self) -> None:
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
        created = self._repo.create_samples_from_markers(
            positions, final_frame=self._loaded.frame_count - 1
        )
        self.state.notify(f"{len(created)} hareket aralığı önerildi.")

    def _toggle_loop(self, enabled: bool) -> None:
        self._loop_selected = enabled
        if not enabled:
            self._timeline.set_loop_range(None)
            return
        interval = self._current_interval()
        if self._timeline.mode is TimelineMode.ERROR and interval is not None:
            self._timeline.set_loop_range((interval.start_frame, interval.end_frame))
            self._seek(interval.start_frame)
            self._play()
            return
        sample = self._current_sample()
        if sample is not None:
            self._timeline.set_loop_range((sample.start_frame, sample.end_frame))
            self._seek(sample.start_frame)
            self._play()

    def _zoom_selected(self) -> None:
        interval = self._current_interval()
        if self._timeline.mode is TimelineMode.ERROR and interval is not None:
            self._timeline.zoom_to_range(interval.start_frame, interval.end_frame)
            return
        sample = self._current_sample()
        if sample is not None:
            self._timeline.zoom_to_range(sample.start_frame, sample.end_frame)

    # ----------------------------------------------------------- error editing
    def _create_interval_here(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None or self._loaded is None:
            self.state.notify("Önce bir hareket seçin.", 4000)
            return
        span = max(2, int(self._loaded.target_fps // 3))
        start = max(sample.start_frame, min(self._position, sample.end_frame - 1))
        self._create_interval_range(start, min(sample.end_frame, start + span))

    def _create_interval_range(self, start: int, end: int) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None or self._loaded is None:
            return
        frames = self._loaded.stream.frames
        try:
            interval = self._repo.create_error_interval(
                sample.sample_id,
                start,
                end,
                start_timestamp_ns=frames[start].camera_timestamp_ns
                if start < len(frames)
                else None,
                end_timestamp_ns=frames[end].camera_timestamp_ns
                if end < len(frames)
                else None,
            )
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)
            return
        self._set_timeline_mode(TimelineMode.ERROR)
        self._select_interval_by_id(interval.interval_id)
        self.state.notify(
            "Hata aralığı eklendi. Türünü seçmek için çift tıklayın veya "
            "Enter'a basın; türsüz aralık export'a girmez.",
            6000,
        )

    def _interval_bounds_changed(self, interval_id: str, start: int, end: int) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        try:
            self._repo.update_error_interval_bounds(
                sample.sample_id, interval_id, start, end
            )
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 5000)

    def _delete_interval(self) -> None:
        sample = self._current_sample()
        interval = self._current_interval()
        if sample is None or interval is None or self._repo is None:
            self.state.notify("Silinecek hata aralığı seçilmedi.", 4000)
            return
        self._repo.delete_error_interval(sample.sample_id, interval.interval_id)
        self._selected_interval_id = None
        self._refresh_sample_state()

    def _loop_interval(self) -> None:
        interval = self._current_interval()
        if interval is None:
            return
        self._timeline.set_loop_range((interval.start_frame, interval.end_frame))
        self._seek(interval.start_frame)
        self._play()

    # ------------------------------------------------------------- undo/redo
    def _undo(self) -> None:
        if self._repo is not None and self._repo.undo():
            self._refresh_sample_state()

    def _redo(self) -> None:
        if self._repo is not None and self._repo.redo():
            self._refresh_sample_state()

    # ---------------------------------------------------------------- take
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

    def _go_to_next_gap(self) -> None:
        """The next thing that needs a decision, in this take or the next one."""
        if self._repo is not None:
            current = self._selected_sample_id
            ordered = list(self._repo.samples)
            start = next(
                (i + 1 for i, s in enumerate(ordered) if s.sample_id == current), 0
            )
            rotated = ordered[start:] + ordered[:start]
            for sample in rotated:
                if not self._repo.readiness(sample).is_ready and sample.is_active:
                    self._select_sample_by_id(sample.sample_id)
                    self._timeline.zoom_to_range(sample.start_frame, sample.end_frame)
                    return
        self._next_unlabelled()

    def _next_unlabelled(self) -> None:
        index = self.state.index
        if index is None:
            return
        self._save_now()
        current = self._loaded.take.take_id if self._loaded else None
        for row in index.needing_review():
            if row.take.take_id != current:
                self.open_take(row.take)
                return
        self.state.notify("Etiketi eksik başka kayıt yok.", 4000)


__all__ = ["ReviewPage"]
