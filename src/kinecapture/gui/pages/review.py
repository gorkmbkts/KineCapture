"""Review and label: playback, movement segmentation, error localisation.

The screen is organised around the two-level label model, and the mode switch
is the spine of it:

* **Hareket modu** - draw and adjust movement samples across the take, then give
  each one an exercise and a binary correct/incorrect verdict.
* **Hata modu** - with a movement selected, draw error intervals inside it and
  assign each one an error class.

The mode is always visible, the selected movement is always visible, and the
timeline masks everything outside it while in error mode, so it is never
ambiguous whether a drag is creating a movement or an error.

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
    Correctness,
    SampleReadiness,
    SegmentStatus,
    TakeQuality,
)
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import ErrorInterval, MovementSample
from kinecapture.gui.icons import get_icon
from kinecapture.gui.pages.base import Page, scrollable
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
from kinecapture.gui.widgets.error_picker import ErrorClassPicker
from kinecapture.gui.widgets.scene_view import SceneMode, SceneView
from kinecapture.gui.widgets.skeleton_view import VIEW_PRESETS
from kinecapture.gui.widgets.timeline import (
    TimelineMode,
    TimelineWidget,
    error_class_colour,
)
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
    SampleReadiness.EXCLUDED: ("eye", "Dışlandı", "text_muted"),
}


class ReviewPage(Page):
    """Playback, movement segmentation and two-level labelling for one take."""

    navigate_requested = Signal(str)

    title = "İnceleme ve Etiketleme"
    description = (
        "Hareketleri işaretleyin, doğru/yanlış kararını verin ve hatalı "
        "hareketlerde hatanın tam olarak nerede olduğunu gösterin."
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
        self._selected_sample_id: Optional[str] = None
        self._selected_interval_id: Optional[str] = None

        self._take_selector = QComboBox()
        self._take_selector.setMinimumWidth(300)
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
        splitter.addWidget(scrollable(self._build_side(theme)))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([820, 540])
        body.addWidget(splitter, 1)

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
        card = Card("Görüntü", theme=theme, icon="camera")

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

        controls.addStretch(1)
        self._body_selector = QComboBox()
        self._body_selector.currentIndexChanged.connect(self._redraw)
        controls.addWidget(make_label("Gövde", role="caption"))
        controls.addWidget(self._body_selector)

        container = QWidget()
        container.setLayout(controls)
        card.add_widget(container)
        return card

    def _build_side(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        wrapper.setMinimumWidth(430)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        self._side_layout = layout
        layout.addWidget(self._build_mode_card(theme))
        layout.addWidget(self._build_movement_card(theme))
        layout.addWidget(self._build_error_card(theme))
        layout.addWidget(self._build_take_card(theme))
        layout.addStretch(1)
        return wrapper

    def _order_side_cards(self, editing_errors: bool) -> None:
        """Put the active mode's card directly under the mode switch.

        Scrolling to reach the tool the user just switched to is the one thing
        this column must never do, and at 1366x768 there is only room for one
        expanded card above the fold.
        """
        first = self._error_card if editing_errors else self._movement_card
        second = self._movement_card if editing_errors else self._error_card
        if self._side_layout.indexOf(first) == 1:
            return
        for card in (first, second):
            self._side_layout.removeWidget(card)
        self._side_layout.insertWidget(1, first)
        self._side_layout.insertWidget(2, second)

    def _build_mode_card(self, theme: Theme) -> QWidget:
        """The spine of the screen: which level am I editing?"""
        card = Card(theme=theme)
        row = QHBoxLayout()
        row.setSpacing(theme.space_sm)

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
        row.addStretch(1)

        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)

        self._mode_hint = make_label("", role="muted")
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setMaximumHeight(34)
        card.add_widget(self._mode_hint)
        return card

    def _build_movement_card(self, theme: Theme) -> QWidget:
        card = Card("Hareketler", theme=theme, icon="list")
        self._movement_progress = StatusChip("0/0 hazır", theme=theme, icon="check")
        card.add_header_widget(self._movement_progress)

        self._sample_list = QListWidget()
        self._sample_list.setMinimumHeight(96)
        self._sample_list.currentItemChanged.connect(
            lambda current, _: self._sample_row_selected(current)
        )
        card.add_widget(self._sample_list, 1)

        # Everything below collapses while the user is working on error
        # intervals, so the tools for the active mode are never below the fold.
        self._movement_detail = QWidget()
        detail = QVBoxLayout(self._movement_detail)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(theme.space_sm)
        card.add_widget(self._movement_detail)

        buttons = QHBoxLayout()
        for text, icon, handler, tooltip in (
            ("Ekle", "add", self._create_sample_here, "Konumda yeni hareket (N)"),
            ("Böl", "split", self._split_sample, "Seçili hareketi konumdan böl (S)"),
            ("Birleştir", "merge", self._merge_samples, "Seçiliyi sonrakiyle birleştir"),
            ("Dışla", "eye", self._toggle_exclude, "Datasetten çıkar / geri al (X)"),
            ("Sil", "trash", self._delete_sample, "Hareket aralığını sil"),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        container = QWidget()
        container.setLayout(buttons)
        detail.addWidget(container)

        extra = QHBoxLayout()
        markers_button = make_button(
            "Marker'lardan oluştur",
            icon="marker",
            theme=theme,
            tooltip="Kayıt sırasında bırakılan marker'ları sınır olarak kullan",
        )
        markers_button.clicked.connect(self._samples_from_markers)
        extra.addWidget(markers_button)
        self._loop_button = make_button("Seçiliyi döngüle", icon="refresh", theme=theme)
        self._loop_button.setCheckable(True)
        self._loop_button.toggled.connect(self._toggle_loop)
        extra.addWidget(self._loop_button)
        extra.addStretch(1)
        extra_container = QWidget()
        extra_container.setLayout(extra)
        detail.addWidget(extra_container)

        # ---- the level-1 label -------------------------------------------
        self._exercise_selector = QComboBox()
        self._exercise_selector.setEditable(True)
        self._exercise_selector.currentTextChanged.connect(self._label_edited)
        self._exercise_row = FieldRow(
            "Hareket türü", self._exercise_selector, theme=theme, required=True
        )
        detail.addWidget(self._exercise_row)

        verdict_row = QHBoxLayout()
        verdict_row.setSpacing(theme.space_sm)
        self._verdict_buttons: dict[Correctness, QWidget] = {}
        for correctness, key in (
            (Correctness.CORRECT, "1"),
            (Correctness.INCORRECT, "2"),
        ):
            button = make_button(
                f"{LabelSchema.label_for_correctness(correctness)}  ({key})",
                theme=theme,
            )
            button.setCheckable(True)
            button.clicked.connect(
                lambda _=False, c=correctness: self._set_verdict(c)
            )
            self._verdict_buttons[correctness] = button
            verdict_row.addWidget(button)
        verdict_row.addStretch(1)
        verdict_container = QWidget()
        verdict_container.setLayout(verdict_row)
        self._verdict_row = FieldRow(
            "Doğru mu, yanlış mı?", verdict_container, theme=theme, required=True
        )
        detail.addWidget(self._verdict_row)

        self._note = QPlainTextEdit()
        self._note.setMaximumHeight(44)
        self._note.textChanged.connect(self._label_edited)
        detail.addWidget(FieldRow("Not", self._note, theme=theme))

        actions = QHBoxLayout()
        for text, icon, handler, tooltip in (
            ("Öncekini kopyala", "list", self._copy_previous, "Önceki hareketin etiketi (C)"),
            ("Tümüne uygula", "check", self._apply_all, "Bu etiketi tüm hareketlere uygula"),
            ("Geri al", "undo", self._undo, "Ctrl+Z"),
            ("Yinele", "redo", self._redo, "Ctrl+Y"),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        actions_container = QWidget()
        actions_container.setLayout(actions)
        detail.addWidget(actions_container)

        self._status_label = make_label("", role="muted")
        self._status_label.setWordWrap(True)
        card.add_widget(self._status_label)
        self._movement_card = card
        return card

    def _build_error_card(self, theme: Theme) -> QWidget:
        card = Card("Hata aralıkları", theme=theme, icon="target")
        # The primary action lives in the header so it survives any collapse or
        # small-screen scroll: adding an interval is the point of this card.
        header_add = make_button(
            "+ Hata aralığı",
            variant="primary",
            theme=theme,
            tooltip="Oynatma konumunda yeni hata aralığı (E)",
        )
        header_add.clicked.connect(self._create_interval_here)
        card.add_header_widget(header_add)
        self._error_chip = StatusChip("-", theme=theme, icon="info")
        card.add_header_widget(self._error_chip)

        self._interval_list = QListWidget()
        self._interval_list.setMinimumHeight(78)
        self._interval_list.currentItemChanged.connect(
            lambda current, _: self._interval_row_selected(current)
        )
        card.add_widget(self._interval_list, 1)

        self._error_detail = QWidget()
        detail = QVBoxLayout(self._error_detail)
        detail.setContentsMargins(0, 0, 0, 0)
        detail.setSpacing(theme.space_sm)
        card.add_widget(self._error_detail)

        buttons = QHBoxLayout()
        play_button = make_button(
            "Aralığı oynat", icon="play", theme=theme, tooltip="Seçili aralığı döngüle"
        )
        play_button.clicked.connect(self._loop_interval)
        buttons.addWidget(play_button)
        delete_button = make_button("Sil", icon="trash", theme=theme)
        delete_button.clicked.connect(self._delete_interval)
        buttons.addWidget(delete_button)
        buttons.addStretch(1)
        container = QWidget()
        container.setLayout(buttons)
        detail.addWidget(container)

        self._picker = ErrorClassPicker(theme)
        self._picker.class_chosen.connect(self._assign_error_class)
        self._picker.creation_requested.connect(self._create_error_class)
        detail.addWidget(
            FieldRow(
                "Hata türü",
                self._picker,
                theme=theme,
                help_text=(
                    "Yeni tür projeye kalıcı kaydolur ve diğer kayıtlarda da "
                    "önerilir. Geri al yalnız bu atamayı geri alır, tür listede kalır."
                ),
            )
        )
        self._error_card = card
        return card

    def _build_take_card(self, theme: Theme) -> QWidget:
        card = Card("Kayıt bilgisi", theme=theme, icon="info")
        self._take_chip = StatusChip("-", theme=theme, icon="info")
        card.add_header_widget(self._take_chip)
        self._take_details = KeyValueList(theme)
        card.add_widget(self._take_details)

        row = QHBoxLayout()
        self._quality_selector = QComboBox()
        for quality in TakeQuality:
            self._quality_selector.addItem(quality.value, quality.value)
        self._quality_selector.currentIndexChanged.connect(self._quality_changed)
        row.addWidget(make_label("Kalite kararı", role="caption"))
        row.addWidget(self._quality_selector, 1)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)

        next_button = make_button(
            "Sonraki eksik kayıt",
            variant="primary",
            icon="chevron-right",
            theme=theme,
            tooltip="Etiketi tamamlanmamış bir sonraki kayda geç",
        )
        next_button.clicked.connect(self._next_unlabelled)
        card.add_widget(next_button)
        return card

    def _build_transport(self, theme: Theme) -> QWidget:
        """Playback controls. Lives inside the timeline card: they are one tool,
        and a separate card costs ~40px of vertical space a 768px screen needs."""
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

        row.addSpacing(theme.space_md)
        self._position_label = make_label("-", role="muted")
        row.addWidget(self._position_label)
        row.addStretch(1)

        for text, icon, handler, tooltip in (
            ("Seçiliye yakınlaş", "search", self._zoom_selected, "Seçili aralığa yakınlaş"),
            ("Tümünü göster", "eye", lambda: self._timeline.zoom_to_fit(), ""),
        ):
            button = make_button(text, icon=icon, theme=theme, tooltip=tooltip)
            button.clicked.connect(handler)
            row.addWidget(button)

        container = QWidget()
        container.setLayout(row)
        return container

    def _build_timeline(self, theme: Theme) -> QWidget:
        card = Card(theme=theme)
        card.add_widget(self._build_transport(theme))
        self._timeline = TimelineWidget(theme)
        self._timeline.position_changed.connect(self._seek)
        self._timeline.sample_selected.connect(self._select_sample_by_id)
        self._timeline.sample_bounds_changed.connect(self._sample_bounds_changed)
        self._timeline.sample_create_requested.connect(self._create_sample_range)
        self._timeline.sample_double_clicked.connect(self._zoom_to_sample)
        self._timeline.interval_selected.connect(self._select_interval_by_id)
        self._timeline.interval_bounds_changed.connect(self._interval_bounds_changed)
        self._timeline.interval_create_requested.connect(self._create_interval_range)
        self._timeline.interval_double_clicked.connect(self._select_interval_by_id)
        card.add_widget(self._timeline)

        self._timeline_legend = make_label("", role="muted")
        self._timeline_legend.setWordWrap(True)
        card.add_widget(self._timeline_legend)
        return card

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
        add("C", self._guarded(self._copy_previous))
        add("F1", self._guarded(lambda: self._set_timeline_mode(TimelineMode.MOVEMENT)))
        add("F2", self._guarded(lambda: self._set_timeline_mode(TimelineMode.ERROR)))
        add("1", self._guarded(lambda: self._set_verdict(Correctness.CORRECT)))
        add("2", self._guarded(lambda: self._set_verdict(Correctness.INCORRECT)))
        add("Ctrl+F", self._picker.focus_search)
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
                "HAREKET şeridinde sürükleyerek tekrar çizin. Her tekrar bir örnek."
            )
            self._timeline_legend.setText(
                "HAREKET şeridinde sürükle: tekrar çiz/taşı  ·  "
                "Tekerlek: yakınlaştır  ·  Shift+Tekerlek: kaydır"
            )
        else:
            name = f"Hareket {sample.index}" if sample else "Seçili hareket"
            self._mode_hint.setText(
                f"{name} İÇİNDE, HATA şeridinde sürükleyip hata türünü seçin. "
                "Aralık hareketin dışına çıkamaz."
            )
            self._timeline_legend.setText(
                "HATA şeridinde sürükle: hata aralığı çiz/taşı  ·  "
                "Hareketin dışı maskelenir"
            )
        self._error_card.setEnabled(sample is not None)

        # Only the active mode's editing tools stay expanded. At 1366x768 the
        # side column cannot hold both, and burying the tool the user just
        # switched to would be the worst possible thing to hide.
        editing_errors = mode is TimelineMode.ERROR
        self._movement_detail.setVisible(not editing_errors)
        self._error_detail.setVisible(editing_errors)
        # A collapsed list is a reference, not a workspace: three rows is plenty.
        self._sample_list.setMaximumHeight(84 if editing_errors else 16777215)
        self._interval_list.setMaximumHeight(84 if not editing_errors else 16777215)
        self._order_side_cards(editing_errors)
        self._movement_card.set_subtitle(
            self._movement_summary() if editing_errors else ""
        )
        self._error_card.set_subtitle(
            "" if editing_errors else self._error_summary()
        )
        self._refresh_interval_list()

    def _error_summary(self) -> str:
        """One line about the selected movement's error intervals, collapsed."""
        sample = self._current_sample()
        if sample is None:
            return "Önce bir hareket seçin."
        count = len(sample.error_intervals)
        if not count:
            return (
                "Hata aralığı yok."
                if sample.correctness is not Correctness.INCORRECT
                else "Hatalı hareket — en az bir hata aralığı gerekli."
            )
        names = ", ".join(
            self.state.label_schema.label_for_error(code)
            for code in sample.error_codes
        )
        return f"{count} aralık · {names}"

    def _movement_summary(self) -> str:
        """One line describing the movement being worked on, while collapsed."""
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return "Hareket seçilmedi."
        _icon, readiness, _colour = self._readiness_chip(sample)
        return (
            f"Seçili: {sample.index}. hareket · "
            f"{sample.exercise or '— tür yok'} · "
            f"{LabelSchema.label_for_correctness(sample.correctness)} · {readiness}"
        )

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

        self._populate_schema_choices()
        self._reload_body_selector()
        self._reload_timeline()
        self._refresh_take_info()
        self._refresh_sample_list()
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

    def _populate_schema_choices(self) -> None:
        schema = self.state.label_schema
        self._suppress_form = True
        self._exercise_selector.clear()
        self._exercise_selector.addItem("", "")
        for option in schema.exercises:
            self._exercise_selector.addItem(option.label, option.code)
        self._suppress_form = False
        self._picker.set_schema(schema)
        self._timeline.set_error_labels(
            {o.code: o.label for o in schema.error_types}
        )

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
            coverage=stream.coverage_curve(tracking_id),
            gaps=gaps,
        )
        if self._repo is not None:
            self._timeline.set_samples(self._repo.samples)

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
                ("Proxy video", "var" if self._loaded.has_video else "yok"),
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

    def _redraw(self) -> None:
        loaded = self._loaded
        if loaded is None:
            return
        frame = loaded.stream.frame_at(self._position)
        tracking_id = self._body_selector.currentData()

        rgb = None
        if loaded.has_video and loaded.video is not None:
            rgb = loaded.video.read_at(loaded.video_position_for(self._position))
        self._scene.set_frame(
            rgb, frame.bodies if frame else (), loaded.spec, active_id=tracking_id
        )

        if frame is not None and loaded.stream.frames:
            first = loaded.stream.frames[0].camera_timestamp_ns
            elapsed = (
                (frame.camera_timestamp_ns - first) / 1e9
                if first and frame.camera_timestamp_ns
                else self._position / loaded.target_fps
            )
            inside = ""
            sample = self._current_sample()
            if sample is not None and sample.contains(self._position):
                inside = f"  ·  hareket {sample.index} içinde"
            self._position_label.setText(
                f"Konum {self._position + 1}/{loaded.frame_count}  ·  "
                f"kayıt karesi {frame.frame_index}  ·  {elapsed:.2f} sn{inside}"
            )

    # ------------------------------------------------------------ repository
    def _on_repo_changed(self) -> None:
        self._refresh_sample_list()
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
                    "Otomatik kaydedildi", icon="check", colour=self.theme.success
                )
                self.state.refresh_dataset(force=True)
        except KineCaptureError as exc:
            self.state.report_error(exc)

    def _save_now(self) -> None:
        self._autosave_timer.stop()
        self._autosave()

    # -------------------------------------------------------- movement list
    def _current_sample(self) -> Optional[MovementSample]:
        if self._repo is None or not self._selected_sample_id:
            return None
        return self._repo.find(self._selected_sample_id)

    def _current_interval(self) -> Optional[ErrorInterval]:
        sample = self._current_sample()
        if sample is None or not self._selected_interval_id:
            return None
        return sample.interval(self._selected_interval_id)

    def _readiness_chip(self, sample: MovementSample) -> tuple[str, str, str]:
        assert self._repo is not None
        state = self._repo.readiness(sample)
        icon, text, colour_name = _READINESS_PRESENTATION[state]
        return icon, text, getattr(self.theme, colour_name, self.theme.text_secondary)

    def _refresh_sample_list(self) -> None:
        if self._repo is None:
            return
        current = self._selected_sample_id
        self._sample_list.blockSignals(True)
        self._sample_list.clear()
        for sample in self._repo.samples:
            _icon, readiness_text, _colour = self._readiness_chip(sample)
            verdict = LabelSchema.label_for_correctness(sample.correctness)
            errors = (
                f" · {len(sample.error_intervals)} hata aralığı"
                if sample.error_intervals
                else ""
            )
            item = QListWidgetItem(
                f"{sample.index}. kare {sample.start_frame}-{sample.end_frame} "
                f"({sample.frame_count})\n"
                f"{sample.exercise or '— tür yok'} · {verdict}{errors} · {readiness_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, sample.sample_id)
            self._sample_list.addItem(item)
            if sample.sample_id == current:
                self._sample_list.setCurrentItem(item)
        self._sample_list.blockSignals(False)

        if self._timeline.mode is TimelineMode.ERROR:
            self._movement_card.set_subtitle(self._movement_summary())

        ready = self._repo.ready_count
        total = len(self._repo.active_samples)
        self._movement_progress.set_status(
            f"{ready}/{total} hazır",
            icon="check" if ready == total and total else "edit",
            colour=self.theme.success if total and ready == total else self.theme.warning,
        )
        self._refresh_status_line()
        self._load_label_form()
        self._refresh_interval_list()

    def _refresh_status_line(self) -> None:
        if self._repo is None:
            return
        parts: list[str] = []
        sample = self._current_sample()
        if sample is not None:
            problems = self._repo.problems(sample)
            if problems:
                parts.append(" · ".join(p.message for p in problems))
        structural = self._repo.validation_problems()
        if structural:
            parts.append(" · ".join(p["message"] for p in structural))
        self._status_label.setText("  ".join(parts))
        self._status_label.setProperty("role", "error" if parts else "muted")
        from kinecapture.gui.widgets.common import restyle

        restyle(self._status_label)

    def _sample_row_selected(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        self._select_sample_by_id(item.data(Qt.ItemDataRole.UserRole), from_list=True)

    def _select_sample_by_id(self, sample_id: str, *, from_list: bool = False) -> None:
        if self._repo is None:
            return
        self._selected_sample_id = sample_id
        self._selected_interval_id = None
        self._timeline.set_selected_sample(sample_id)
        sample = self._repo.find(sample_id)
        if sample is not None and not from_list:
            for row in range(self._sample_list.count()):
                item = self._sample_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == sample_id:
                    self._sample_list.blockSignals(True)
                    self._sample_list.setCurrentItem(item)
                    self._sample_list.blockSignals(False)
                    break
        if sample is not None:
            self._seek(sample.start_frame)
            if self._loop_selected:
                self._timeline.set_loop_range((sample.start_frame, sample.end_frame))
        self._load_label_form()
        self._sync_mode_ui()
        self._refresh_status_line()

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

    def _delete_sample(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
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
        self._refresh_sample_list()

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
        sample = self._current_sample()
        if enabled and sample is not None:
            self._timeline.set_loop_range((sample.start_frame, sample.end_frame))
        else:
            self._timeline.set_loop_range(None)

    def _zoom_to_sample(self, sample_id: str) -> None:
        if self._repo is None:
            return
        sample = self._repo.find(sample_id)
        if sample is not None:
            self._timeline.zoom_to_range(sample.start_frame, sample.end_frame)

    def _zoom_selected(self) -> None:
        interval = self._current_interval()
        if self._timeline.mode is TimelineMode.ERROR and interval is not None:
            self._timeline.zoom_to_range(interval.start_frame, interval.end_frame)
            return
        sample = self._current_sample()
        if sample is not None:
            self._timeline.zoom_to_range(sample.start_frame, sample.end_frame)

    # ----------------------------------------------------------- level-1 label
    def _load_label_form(self) -> None:
        sample = self._current_sample()
        self._movement_card.setEnabled(True)
        for widget in (self._exercise_selector, self._note):
            widget.setEnabled(sample is not None)
        for button in self._verdict_buttons.values():
            button.setEnabled(sample is not None)
        if sample is None:
            self._suppress_form = True
            self._exercise_selector.setCurrentIndex(0)
            self._note.setPlainText("")
            for button in self._verdict_buttons.values():
                button.setChecked(False)
            self._exercise_row.clear_error()
            self._verdict_row.clear_error()
            self._suppress_form = False
            return

        self._suppress_form = True
        position = self._exercise_selector.findData(sample.exercise)
        if position >= 0:
            self._exercise_selector.setCurrentIndex(position)
        else:
            self._exercise_selector.setCurrentText(sample.exercise)
        for correctness, button in self._verdict_buttons.items():
            button.setChecked(correctness is sample.correctness)
        self._note.setPlainText(sample.note)
        self._suppress_form = False

        self._exercise_row.set_error("" if sample.exercise else "Hareket türü seçilmedi.")
        self._verdict_row.set_error(
            "" if sample.correctness.is_decided else "Doğru/yanlış kararı verilmedi."
        )

    def _label_edited(self) -> None:
        if self._suppress_form or self._repo is None:
            return
        sample = self._current_sample()
        if sample is None:
            return
        exercise = self._exercise_selector.currentData()
        if exercise is None:
            exercise = self._exercise_selector.currentText().strip()
        self._repo.label_sample(
            sample.sample_id,
            exercise=exercise,
            note=self._note.toPlainText().strip(),
        )

    def _set_verdict(self, correctness: Correctness) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        self._repo.label_sample(sample.sample_id, correctness=correctness)
        for value, button in self._verdict_buttons.items():
            button.setChecked(value is correctness)
        if correctness is Correctness.INCORRECT and not sample.error_intervals:
            # Move the user straight to the next required step.
            self.state.notify(
                "Hatalı olarak işaretlendi. Şimdi hatanın göründüğü aralığı "
                "işaretleyin (F2 veya E).",
                6000,
            )

    def _copy_previous(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        ordered = list(self._repo.samples)
        position = next(
            (i for i, s in enumerate(ordered) if s.sample_id == sample.sample_id), 0
        )
        if position == 0:
            self.state.notify("Kopyalanacak önceki hareket yok.", 4000)
            return
        self._repo.copy_label_from(ordered[position - 1].sample_id, sample.sample_id)
        self.state.notify(
            "Etiket kopyalandı. Hata aralıkları kopyalanmaz; bu harekete özgüdür.",
            5000,
        )
        self._load_label_form()

    def _apply_all(self) -> None:
        sample = self._current_sample()
        if sample is None or self._repo is None:
            return
        answer = QMessageBox.question(
            self,
            "Tümüne uygula",
            f"'{sample.exercise or '—'}' / "
            f"'{LabelSchema.label_for_correctness(sample.correctness)}' "
            "etiketi bu kayıttaki tüm hareketlere uygulansın mı?\n\n"
            "Hata aralıkları etkilenmez.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count = self._repo.apply_to_all(
            exercise=sample.exercise, correctness=sample.correctness
        )
        self.state.notify(f"{count} hareket güncellendi.")

    # ----------------------------------------------------------- level-2 label
    def _refresh_interval_list(self) -> None:
        sample = self._current_sample()
        self._interval_list.blockSignals(True)
        self._interval_list.clear()
        if sample is None:
            self._interval_list.addItem(
                QListWidgetItem("Önce bir hareket seçin.")
            )
            self._interval_list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
            self._interval_list.blockSignals(False)
            self._error_chip.set_status("-", icon="info", colour=self.theme.text_muted)
            self._picker.set_current("")
            return

        schema = self.state.label_schema
        for interval in sample.sorted_intervals():
            name = (
                schema.label_for_error(interval.error_code)
                if interval.error_code
                else "— tür seçilmedi"
            )
            item = QListWidgetItem(
                f"kare {interval.start_frame}-{interval.end_frame} "
                f"({interval.frame_count})  ·  {name}"
            )
            item.setData(Qt.ItemDataRole.UserRole, interval.interval_id)
            if interval.error_code:
                from PySide6.QtGui import QColor

                item.setForeground(QColor(error_class_colour(interval.error_code)))
            self._interval_list.addItem(item)
            if interval.interval_id == self._selected_interval_id:
                self._interval_list.setCurrentItem(item)
        if not sample.error_intervals:
            hint = QListWidgetItem(
                "Hata aralığı yok."
                if sample.correctness is not Correctness.INCORRECT
                else "Hatalı hareket — en az bir hata aralığı gerekli."
            )
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self._interval_list.addItem(hint)
        self._interval_list.blockSignals(False)

        count = len(sample.error_intervals)
        if sample.correctness is Correctness.CORRECT and count:
            self._error_chip.set_status(
                "Çelişki", icon="warning", colour=self.theme.danger
            )
        elif sample.correctness is Correctness.INCORRECT and not count:
            self._error_chip.set_status(
                "Aralık gerekli", icon="target", colour=self.theme.warning
            )
        else:
            self._error_chip.set_status(
                f"{count} aralık",
                icon="check" if count else "info",
                colour=self.theme.success if count else self.theme.text_muted,
            )

        interval = self._current_interval()
        self._picker.set_current(interval.error_code if interval else "")

    def _interval_row_selected(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        interval_id = item.data(Qt.ItemDataRole.UserRole)
        if interval_id:
            self._select_interval_by_id(interval_id)

    def _select_interval_by_id(self, interval_id: str) -> None:
        self._selected_interval_id = interval_id
        self._timeline.set_selected_interval(interval_id)
        interval = self._current_interval()
        if interval is not None:
            self._seek(interval.start_frame)
            self._picker.set_current(interval.error_code)
        self._refresh_interval_list()

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
        self._picker.focus_search()
        self.state.notify("Hata aralığı eklendi. Şimdi hata türünü seçin.", 5000)

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

    def _assign_error_class(self, code: str) -> None:
        sample = self._current_sample()
        interval = self._current_interval()
        if sample is None or interval is None or self._repo is None:
            self.state.notify("Önce bir hata aralığı seçin.", 4000)
            return
        self._repo.set_error_interval_class(
            sample.sample_id, interval.interval_id, code
        )
        self._picker.clear_search()
        self._refresh_interval_list()

    def _create_error_class(self, name: str) -> None:
        sample = self._current_sample()
        interval = self._current_interval()
        if self._repo is None:
            return
        try:
            if sample is not None and interval is not None:
                _updated, option = self._repo.assign_new_error_class(
                    sample.sample_id, interval.interval_id, name
                )
            else:
                option = self._repo.ensure_error_class(name)
        except KineCaptureError as exc:
            self.state.notify(exc.user_text(), 6000)
            return
        # The vocabulary changed, so every picker and the timeline captions
        # need the new class immediately.
        self._populate_schema_choices()
        self._picker.clear_search()
        self._refresh_interval_list()
        self.state.notify(
            f"'{option.label}' hata türü projeye eklendi ve seçili aralığa atandı."
            if interval is not None
            else f"'{option.label}' hata türü projeye eklendi.",
            5000,
        )

    def _delete_interval(self) -> None:
        sample = self._current_sample()
        interval = self._current_interval()
        if sample is None or interval is None or self._repo is None:
            return
        self._repo.delete_error_interval(sample.sample_id, interval.interval_id)
        self._selected_interval_id = None
        self._refresh_interval_list()

    def _loop_interval(self) -> None:
        interval = self._current_interval()
        if interval is None:
            self.state.notify("Önce bir hata aralığı seçin.", 4000)
            return
        self._timeline.set_loop_range((interval.start_frame, interval.end_frame))
        self._seek(interval.start_frame)
        self._play()

    # ------------------------------------------------------------- undo/redo
    def _undo(self) -> None:
        if self._repo is not None and self._repo.undo():
            self._load_label_form()
            self._refresh_interval_list()

    def _redo(self) -> None:
        if self._repo is not None and self._repo.redo():
            self._load_label_form()
            self._refresh_interval_list()

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
