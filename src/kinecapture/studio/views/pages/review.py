"""Etiketleme: where a coach turns a recording into training data.

The shape is a video editor's, because that is the shape of the work: a
picture on top, a timeline underneath, and an inspector for whatever is
selected. Someone who has used DaVinci Resolve should not have to be taught
this screen - drag on the timeline to mark a range, grab an edge to trim it,
scroll to zoom, space to play.

What is *not* borrowed from an editor is the refusal. An editor lets you drop
a clip anywhere; this screen will not let a label be almost right. Every
decision goes through the annotation store, which validates the whole document
and rejects the edit whole rather than applying half of it, and every refusal
arrives as a sentence saying which movement and what is wrong with it.

Three things here exist specifically to make a long session bearable:

* **Live trim preview** - while an edge is being dragged the picture follows
  it, so the boundary is chosen by looking at the frame rather than by
  guessing and checking afterwards.
* **Number keys** - the first nine exercise classes are on 1..9, so labelling
  thirty repetitions is thirty keystrokes, not thirty trips to a dropdown.
* **Sonraki eksik** - jumps to the next movement that is still missing
  something and says what, so finishing a take does not mean hunting for the
  one repetition that was skipped.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import numpy as np

from kinecapture.features.roles import resolve_roles
from kinecapture.studio.services.skeleton3d import up_axis_for
from kinecapture.processing.annotations import JointStatus
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.subject import SubjectViewModel
from kinecapture.studio.viewmodels.review import (
    READINESS_TEXT,
    ErrorRow,
    MovementRow,
    ReviewViewModel,
)

from ..timeline import Interval, TimelineView, Tool
from ..skeleton3d import Skeleton3DView
from ..subject import SubjectPanel
from ..viewer import ReviewViewer
from ..widgets import label, mono_label, separator
from .base import StudioPage

#: How many exercise classes get a number key. Nine, because that is how many
#: digits there are above the letters.
QUICK_SLOTS = 9

_JOINT_STATUS_TEXT = (
    (JointStatus.SELECTED, "Eklemler seçildi"),
    (JointStatus.NOT_APPLICABLE, "Eklem ilişkisi yok"),
    (JointStatus.INDETERMINATE, "Belirlenemedi"),
    (JointStatus.UNREVIEWED, "Henüz bakılmadı"),
)


def _tool_button(text: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setToolTip(tooltip)
    button.setCheckable(True)
    button.setAutoRaise(True)
    return button


class ReviewPage(StudioPage):
    """The labelling screen."""

    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ReviewViewModel] = None
        self.subject: Optional[SubjectViewModel] = None
        self._suppress = False
        self._resume_position: Optional[int] = None
        self._roles: dict[str, Optional[int]] = {}
        self._camera = None

        self._clock = QTimer(self)
        self._clock.setTimerType(Qt.TimerType.PreciseTimer)
        self._clock.timeout.connect(self._tick)

        split = QSplitter(Qt.Orientation.Vertical, self)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_top())
        split.addWidget(self._build_timeline())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.body_layout.addWidget(split, 1)
        self._install_shortcuts()
        self._show_nothing()

    # ------------------------------------------------------------------ build
    def _build_top(self) -> QWidget:
        tokens = self._tokens
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)

        left = QWidget()
        column = QVBoxLayout(left)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        # Video and 3D side by side: the question a coach actually asks is
        # whether the tracked skeleton matches what the camera saw, and that is
        # only answerable with both on screen at the same frame.
        self.stage = QSplitter(Qt.Orientation.Horizontal)
        self.stage.setChildrenCollapsible(False)
        self.viewer = ReviewViewer(tokens)
        self.stage.addWidget(self.viewer)
        self.skeleton = Skeleton3DView(tokens)
        self.skeleton.camera_changed.connect(self._remember_camera)
        self.stage.addWidget(self.skeleton)
        self.stage.setStretchFactor(0, 3)
        self.stage.setStretchFactor(1, 2)
        column.addWidget(self.stage, 1)
        column.addWidget(self._build_transport())
        top.addWidget(left)

        top.addWidget(self._build_inspector())
        top.setStretchFactor(0, 3)
        top.setStretchFactor(1, 1)
        return top

    def _build_transport(self) -> QWidget:
        tokens = self._tokens
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.metric("KcSpacingSm"))

        self.first_button = QPushButton("|◀")
        self.first_button.setToolTip("Başa git (Home)")
        self.back_button = QPushButton("◀")
        self.back_button.setToolTip("Bir kare geri (←)")
        self.play_button = QPushButton("▶")
        self.play_button.setToolTip("Oynat / duraklat (Boşluk)")
        self.forward_button = QPushButton("▶")
        self.forward_button.setToolTip("Bir kare ileri (→)")
        self.last_button = QPushButton("▶|")
        self.last_button.setToolTip("Sona git (End)")
        for button in (
            self.first_button, self.back_button, self.play_button,
            self.forward_button, self.last_button,
        ):
            button.setFixedWidth(tokens.metric("KcControlHeightLarge") + 6)
            row.addWidget(button)

        self.first_button.clicked.connect(lambda: self._seek(0))
        self.back_button.clicked.connect(lambda: self._step(-1))
        self.play_button.clicked.connect(self._toggle_play)
        self.forward_button.clicked.connect(lambda: self._step(1))
        self.last_button.clicked.connect(self._seek_end)

        self.position_label = mono_label("—")
        row.addWidget(self.position_label)
        row.addStretch(1)

        self.next_gap_button = QPushButton("Sonraki eksik")
        self.next_gap_button.setToolTip(
            "Hâlâ bir şeyi eksik olan ilk harekete git (Tab)"
        )
        self.next_gap_button.clicked.connect(self._next_unfinished)
        row.addWidget(self.next_gap_button)

        self.skeleton_button = QToolButton()
        self.skeleton_button.setText("3B")
        self.skeleton_button.setToolTip(
            "3B iskelet gorunumunu goster/gizle. Surukle: dondur - "
            "orta dugme: kaydir - tekerlek: yakinlas - R: sifirla"
        )
        self.skeleton_button.setCheckable(True)
        self.skeleton_button.setChecked(True)
        self.skeleton_button.setAutoRaise(True)
        self.skeleton_button.toggled.connect(self._toggle_skeleton)
        row.addWidget(self.skeleton_button)
        return bar

    def _build_timeline(self) -> QWidget:
        tokens = self._tokens
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingSm"))
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_buttons: dict[Tool, QToolButton] = {}
        for tool, text, tip in (
            (Tool.SCRUB, "Gez", "Sürükleyerek gez, kaydır (V)"),
            (Tool.DRAW_MOVEMENT, "Hareket çiz", "Boş alanda sürükleyerek hareket ekle (M)"),
            (Tool.DRAW_ERROR, "Hata çiz", "Seçili hareketin içinde sürükleyerek hata ekle (E)"),
        ):
            button = _tool_button(text, tip)
            self.tool_group.addButton(button)
            self._tool_buttons[tool] = button
            button.clicked.connect(lambda _checked=False, t=tool: self._set_tool(t))
            bar.addWidget(button)
        self._tool_buttons[Tool.SCRUB].setChecked(True)

        bar.addWidget(separator(Qt.Orientation.Vertical))
        self.snap_box = QCheckBox("Kenara yapış")
        self.snap_box.setChecked(True)
        self.snap_box.setToolTip("Sürüklerken yakın kenarlara ve oynatma çizgisine yapış")
        self.snap_box.toggled.connect(lambda on: self.timeline.set_snap(on))
        bar.addWidget(self.snap_box)

        bar.addWidget(separator(Qt.Orientation.Vertical))
        for text, tip, slot in (
            ("−", "Uzaklaş (Ctrl+-)", lambda: self.timeline.zoom(1 / 1.4)),
            ("+", "Yakınlaş (Ctrl++)", lambda: self.timeline.zoom(1.4)),
            ("Tümü", "Tamamını göster (Ctrl+0)", lambda: self.timeline.zoom_all()),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            bar.addWidget(button)

        bar.addStretch(1)
        self.undo_button = QPushButton("Geri al")
        self.undo_button.setToolTip("Son kararı geri al (Ctrl+Z)")
        self.undo_button.clicked.connect(self._undo)
        self.redo_button = QPushButton("Yinele")
        self.redo_button.setToolTip("Geri alınanı yinele (Ctrl+Y)")
        self.redo_button.clicked.connect(self._redo)
        bar.addWidget(self.undo_button)
        bar.addWidget(self.redo_button)

        bar.addWidget(separator(Qt.Orientation.Vertical))
        self.progress_label = label("—", role="contextValue")
        bar.addWidget(self.progress_label)
        column.addLayout(bar)

        self.timeline = TimelineView(tokens)
        self.timeline.position_changed.connect(self._timeline_scrubbed)
        self.timeline.preview_position.connect(self._preview_frame)
        self.timeline.edit_started.connect(self._edit_started)
        self.timeline.edit_cancelled.connect(self._edit_finished)
        self.timeline.interval_changed.connect(self._interval_changed)
        self.timeline.interval_drawn.connect(self._interval_drawn)
        self.timeline.selection_changed.connect(self._timeline_selected)
        self.timeline.interval_activated.connect(self._timeline_activated)
        column.addWidget(self.timeline, 1)
        return panel

    def _build_inspector(self) -> QWidget:
        tokens = self._tokens
        panel = QWidget()
        panel.setMinimumWidth(tokens.metric("KcInspectorMinWidth"))
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingMd"))

        column.addWidget(label("Hareketler", role="section"))
        self.movement_list = QListWidget()
        self.movement_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.movement_list.setMaximumHeight(160)
        self.movement_list.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.movement_list.currentItemChanged.connect(self._list_selected)
        column.addWidget(self.movement_list)

        self.inspector = QStackedWidget()
        self.inspector.addWidget(self._build_empty_inspector())
        self.inspector.addWidget(self._build_movement_inspector())
        self.inspector.addWidget(self._build_error_inspector())
        column.addWidget(self.inspector, 1)

        # Scrolled, so the densest inspector page cannot set the window's
        # minimum height. Without this the screen demanded 923 px and would not
        # fit a 1366x768 laptop - which is what a coach is likely to have.
        frame = QScrollArea()
        frame.setWidget(panel)
        frame.setWidgetResizable(True)
        frame.setFrameShape(QScrollArea.Shape.NoFrame)
        frame.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frame.setMinimumWidth(tokens.metric("KcInspectorMinWidth"))
        frame.setMinimumHeight(tokens.metric("KcControlHeightLarge") * 4)

        # Two tabs, because they are two different jobs: "which movement is
        # this" and "who is this". Mixing them into one column made neither
        # readable, and the athlete question has to be answerable before the
        # labels underneath it mean anything.
        self.side_tabs = QTabWidget()
        self.side_tabs.addTab(frame, "Etiket")
        self.subject_panel = SubjectPanel(tokens)
        subject_scroll = QScrollArea()
        subject_scroll.setWidget(self.subject_panel)
        subject_scroll.setWidgetResizable(True)
        subject_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        subject_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.side_tabs.addTab(subject_scroll, "Sporcu")
        self.side_tabs.setMinimumWidth(tokens.metric("KcInspectorMinWidth"))
        return self.side_tabs

    def _build_empty_inspector(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(
            "Zaman çizelgesinde boş bir yere sürükleyerek hareket ekleyin.\n\n"
            "M: hareket çiz · E: hata çiz · Boşluk: oynat\n"
            "1-9: seçili harekete sınıf ata · Tab: sonraki eksik"
        )
        hint.setWordWrap(True)
        hint.setProperty("kcRole", "pageSubtitle")
        column.addWidget(hint)
        column.addStretch(1)
        return page

    def _build_movement_inspector(self) -> QWidget:
        tokens = self._tokens
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        self.movement_title = label("Hareket", role="section")
        column.addWidget(self.movement_title)
        self.movement_state = QLabel("")
        self.movement_state.setWordWrap(True)
        self.movement_state.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.movement_state)

        column.addWidget(label("Hareket sınıfı"))
        class_row = QHBoxLayout()
        class_row.setSpacing(tokens.metric("KcSpacingSm"))
        self.exercise_combo = QComboBox()
        self.exercise_combo.activated.connect(self._exercise_chosen)
        class_row.addWidget(self.exercise_combo, 1)
        self.new_exercise_button = QPushButton("Yeni…")
        self.new_exercise_button.setToolTip("Projeye yeni bir hareket sınıfı ekle")
        self.new_exercise_button.clicked.connect(self._new_exercise)
        class_row.addWidget(self.new_exercise_button)
        column.addLayout(class_row)

        self.apply_all_button = QPushButton("Sınıfsızların hepsine uygula")
        self.apply_all_button.setToolTip(
            "Bu sınıfı, henüz sınıfı olmayan bütün hareketlere ver. "
            "Sınıfı olanlar değişmez."
        )
        self.apply_all_button.clicked.connect(self._apply_to_unlabelled)
        column.addWidget(self.apply_all_button)

        column.addWidget(separator())
        bounds = QHBoxLayout()
        bounds.setSpacing(tokens.metric("KcSpacingSm"))
        bounds.addWidget(label("Başlangıç"))
        self.movement_start = QSpinBox()
        self.movement_start.setToolTip("Değiştirirken görüntü o kareye gider")
        bounds.addWidget(self.movement_start)
        bounds.addWidget(label("Bitiş"))
        self.movement_end = QSpinBox()
        bounds.addWidget(self.movement_end)
        column.addLayout(bounds)
        self.movement_start.valueChanged.connect(self._movement_bounds_typed)
        self.movement_end.valueChanged.connect(self._movement_bounds_typed)

        column.addWidget(label("Not"))
        self.movement_note = QPlainTextEdit()
        self.movement_note.setMaximumHeight(56)
        column.addWidget(self.movement_note)

        self.exclude_box = QCheckBox("Bu tekrarı veri setinin dışında tut")
        self.exclude_box.setToolTip(
            "Kayıt silinmez; yalnızca dışa aktarıma girmez."
        )
        self.exclude_box.toggled.connect(self._excluded_toggled)
        column.addWidget(self.exclude_box)

        column.addWidget(separator())
        column.addWidget(label("Bu hareketteki hatalar", role="section"))
        self.error_list = QListWidget()
        self.error_list.setMaximumHeight(110)
        self.error_list.currentItemChanged.connect(self._error_list_selected)
        column.addWidget(self.error_list)

        buttons = QHBoxLayout()
        self.add_error_button = QPushButton("Hata aralığı ekle")
        self.add_error_button.setToolTip(
            "Oynatma çizgisinin çevresine bir hata aralığı koyar; kenarlarından sürükleyin"
        )
        self.add_error_button.clicked.connect(self._add_error_here)
        buttons.addWidget(self.add_error_button)
        self.delete_movement_button = QPushButton("Hareketi sil")
        self.delete_movement_button.clicked.connect(self._delete_movement)
        buttons.addWidget(self.delete_movement_button)
        column.addLayout(buttons)
        column.addStretch(1)
        return page

    def _build_error_inspector(self) -> QWidget:
        tokens = self._tokens
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        self.error_title = label("Hata aralığı", role="section")
        column.addWidget(self.error_title)

        column.addWidget(label("Hata sınıfı"))
        class_row = QHBoxLayout()
        class_row.setSpacing(tokens.metric("KcSpacingSm"))
        self.error_combo = QComboBox()
        self.error_combo.activated.connect(self._error_class_chosen)
        class_row.addWidget(self.error_combo, 1)
        self.new_error_button = QPushButton("Yeni…")
        self.new_error_button.clicked.connect(self._new_error_class)
        class_row.addWidget(self.new_error_button)
        column.addLayout(class_row)

        column.addWidget(label("Eklem durumu"))
        self.joint_status_combo = QComboBox()
        for status, text in _JOINT_STATUS_TEXT:
            self.joint_status_combo.addItem(text, status.value)
        self.joint_status_combo.activated.connect(self._commit_error)
        column.addWidget(self.joint_status_combo)

        column.addWidget(label("İlgili eklemler"))
        self.role_list = QListWidget()
        self.role_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.role_list.itemChanged.connect(self._roles_changed)
        column.addWidget(self.role_list, 1)

        bounds = QHBoxLayout()
        bounds.setSpacing(tokens.metric("KcSpacingSm"))
        bounds.addWidget(label("Başlangıç"))
        self.error_start = QSpinBox()
        bounds.addWidget(self.error_start)
        bounds.addWidget(label("Bitiş"))
        self.error_end = QSpinBox()
        bounds.addWidget(self.error_end)
        column.addLayout(bounds)
        self.error_start.valueChanged.connect(self._error_bounds_typed)
        self.error_end.valueChanged.connect(self._error_bounds_typed)

        column.addWidget(label("Not"))
        self.error_note = QPlainTextEdit()
        self.error_note.setMaximumHeight(48)
        column.addWidget(self.error_note)

        row = QHBoxLayout()
        self.back_to_movement_button = QPushButton("Harekete dön")
        self.back_to_movement_button.clicked.connect(self._back_to_movement)
        row.addWidget(self.back_to_movement_button)
        self.delete_error_button = QPushButton("Hatayı sil")
        self.delete_error_button.clicked.connect(self._delete_error)
        row.addWidget(self.delete_error_button)
        column.addLayout(row)
        return page

    # -------------------------------------------------------------- shortcuts
    def _install_shortcuts(self) -> None:
        def add(sequence: str, slot) -> None:  # noqa: ANN001
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        add("Space", self._toggle_play)
        add("Left", lambda: self._step(-1))
        add("Right", lambda: self._step(1))
        add("Shift+Left", lambda: self._step(-10))
        add("Shift+Right", lambda: self._step(10))
        add("Home", lambda: self._seek(0))
        add("End", self._seek_end)
        add("V", lambda: self._set_tool(Tool.SCRUB, sync=True))
        add("M", lambda: self._set_tool(Tool.DRAW_MOVEMENT, sync=True))
        add("E", lambda: self._set_tool(Tool.DRAW_ERROR, sync=True))
        add("Tab", self._next_unfinished)
        add("Ctrl+Z", self._undo)
        add("Ctrl+Y", self._redo)
        add("Ctrl+Shift+Z", self._redo)
        add("Ctrl+S", self._flush)
        add("Delete", self._delete_selected)
        add("Ctrl+0", lambda: self.timeline.zoom_all())
        add("R", self.skeleton.reset_view)
        add("Ctrl++", lambda: self.timeline.zoom(1.4))
        add("Ctrl+-", lambda: self.timeline.zoom(1 / 1.4))
        for slot in range(1, QUICK_SLOTS + 1):
            add(str(slot), lambda index=slot - 1: self._quick_class(index))

    # ------------------------------------------------------------------ bind
    def attach(self, viewmodel: ReviewViewModel) -> None:
        self.viewmodel = viewmodel
        self.subject = SubjectViewModel(runner=viewmodel._runner)
        self.subject_panel.athlete_chosen.connect(self.subject.choose)
        self.subject_panel.answered.connect(self._answer_subject)
        self.subject_panel.cleared.connect(self.subject.clear_answer)
        self.subject_panel.show_requested.connect(self.subject.show_question)
        self.subject_panel.answer_all.connect(self.subject.answer_remaining)
        self.bind(self.subject.candidates, self.subject_panel.show_candidates)
        self.bind(self.subject.questions, self.subject_panel.show_questions)
        self.bind(self.subject.progress, self._show_subject_status)
        self.bind(self.subject.settled, lambda _s: self._show_subject_status())
        self.bind(self.subject.blocker, lambda _b: self._show_subject_status())
        self.bind_event(self.subject.message, self.show_message)
        self.bind_event(self.subject.go_to, self._seek)
        self.bind(viewmodel.movements, self._movements_changed)
        self.bind(viewmodel.errors, self._errors_changed)
        self.bind(viewmodel.selected_movement, lambda _key: self._selection_changed())
        self.bind(viewmodel.selected_error, lambda _key: self._selection_changed())
        self.bind(viewmodel.progress, self.progress_label.setText)
        self.bind(viewmodel.title, self._subtitle.setText)
        self.bind(viewmodel.can_undo, self.undo_button.setEnabled)
        self.bind(viewmodel.can_redo, self.redo_button.setEnabled)
        self.bind(viewmodel.exercise_options, lambda _o: self._refill_classes())
        self.bind(viewmodel.error_options, lambda _o: self._refill_classes())
        self.bind(viewmodel.playing, self._playing_changed)
        self.bind(viewmodel.frames, self._frames_changed)
        self.bind_event(viewmodel.message, self.show_message)
        self.bind_event(viewmodel.frame_changed, self._render_frame)

    # ------------------------------------------------------------- lifecycle
    def page_activated(self) -> None:
        """Open whichever version the library sent us here for."""
        shell = self.window()
        pending = getattr(shell, "pending_review", None)
        if pending is None or self.viewmodel is None:
            if self.viewmodel is None or self.viewmodel.review is None:
                self._show_nothing()
            return
        setattr(shell, "pending_review", None)
        directory = getattr(pending, "directory", None) or str(pending)
        self.viewmodel.open_version(directory)
        QTimer.singleShot(0, self._after_open)

    def page_deactivated(self) -> None:
        self._clock.stop()
        if self.viewmodel is not None:
            self.viewmodel.playing.set(False)
            self.viewmodel.flush()
        if getattr(self, "subject", None) is not None:
            self.subject.flush()

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self._clock.stop()
        if self.viewmodel is not None:
            self.viewmodel.close()
        super().closeEvent(event)

    def _after_open(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or viewmodel.review is None:
            return
        review = viewmodel.review
        self._roles = resolve_roles(review.skeleton) if review.skeleton else {}
        self._fill_roles()
        self._refill_classes()
        self.timeline.set_take(review.frames, viewmodel.fps.value)
        # The timeline reads its lanes straight from the pre-decimated summary.
        # A 1.0.0 run has none, and then the lanes are simply empty rather than
        # being computed from the full arrays while the user waits.
        self.timeline.lane_source = review.summary.lane if review.has_summary else None
        self.timeline.zoom_all()
        if not review.video:
            self.viewer.set_placeholder(
                f"{review.video.reason}\n\nEtiketleme yine de yapılabilir: "
                "zaman çizelgesi ve iskelet verisi eksiksiz."
            )
        overlay = review.joints_2d_available
        self.viewer.set_overlay_note("" if overlay else overlay.reason)

        camera_system = (review.job.get("processing_camera") or {}).get(
            "coordinate_system", ""
        )
        self.skeleton.set_skeleton_spec(review.bones, up_axis_for(camera_system))
        if self._camera is not None:
            self.skeleton.set_camera(self._camera)
        elif not self.skeleton.frame_on(
            review.joints_3d_window(0, min(review.frames, 300))
        ):
            self.skeleton.set_note("Bu surumde 3B eklem verisi yok.")
        self.skeleton_button.setEnabled(self.skeleton.is_available)

        self.subject_panel.set_context(
            review.frame, self.subject.candidate_title, viewmodel.fps.value
        )
        self.subject.open(review, annotator=viewmodel.store.annotator if viewmodel.store else "")
        self._render_frame(viewmodel.position.value)

    def _show_nothing(self) -> None:
        self.viewer.set_placeholder(
            "Etiketlenecek sürüm seçilmedi.\n\n"
            "İşlenen Videolar ekranından bir sürüm seçip 'Etiketle' deyin."
        )
        self.inspector.setCurrentIndex(0)

    # ------------------------------------------------------------- transport
    def _frames_changed(self, frames: int) -> None:
        for box in (self.movement_start, self.movement_end,
                    self.error_start, self.error_end):
            box.setRange(0, max(0, frames - 1))

    def _seek(self, position: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.seek(position)

    def _seek_end(self) -> None:
        if self.viewmodel is not None:
            self._seek(self.viewmodel.frames.value - 1)

    def _step(self, delta: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.step(delta)

    def _toggle_play(self) -> None:
        if self.viewmodel is not None and self.viewmodel.review is not None:
            self.viewmodel.toggle_play()

    def _playing_changed(self, playing: bool) -> None:
        self.play_button.setText("⏸" if playing else "▶")
        if playing and self.viewmodel is not None:
            fps = max(1.0, self.viewmodel.fps.value)
            self._clock.start(max(1, int(round(1000.0 / fps))))
        else:
            self._clock.stop()

    def _tick(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.advance()

    def _render_frame(self, position: int) -> None:
        """Put one frame and its skeleton on screen. The only place that does."""
        viewmodel = self.viewmodel
        review = viewmodel.review if viewmodel else None
        if viewmodel is None or review is None:
            return
        self.viewer.set_frame(review.frame(position), review.source_size)
        self.viewer.set_skeleton(
            review.joints_2d(position), review.bones, review.confidence(position)
        )
        self._show_pose(review, position)
        self.timeline.set_position(position)
        total = max(1, viewmodel.frames.value)
        seconds = position / max(1.0, viewmodel.fps.value)
        self.position_label.setText(
            f"kare {position + 1}/{total}   {int(seconds // 60):02d}:{seconds % 60:05.2f}"
        )

    def _show_pose(self, review, position: int) -> None:  # noqa: ANN001
        """The 3D view is driven by the same frame index as everything else."""
        if not self.skeleton.isVisible():
            return
        joints = review.joints_3d(position)
        self.skeleton.set_joints(joints)
        missing = joints is None or not bool(np.isfinite(joints).any())
        self.skeleton.set_note("Bu karede izlenen kisi yok." if missing else "")

    def _toggle_skeleton(self, shown: bool) -> None:
        self.skeleton.setVisible(shown)
        if shown and self.viewmodel is not None and self.viewmodel.review is not None:
            self._show_pose(self.viewmodel.review, self.viewmodel.position.value)

    def _remember_camera(self) -> None:
        """Keep the angle across version switches; it is the user's viewpoint."""
        self._camera = self.skeleton.camera

    def _answer_subject(self, interval_id: str, verdict, tracker_id) -> None:  # noqa: ANN001
        """The panel never guesses the tracker; it is passed or it is None."""
        self.subject.answer(interval_id, verdict, tracker_id=tracker_id)

    def _show_subject_status(self, _text: str = "") -> None:
        """Say plainly whether this version may be exported yet."""
        settled = self.subject.settled.value
        text = self.subject.progress.value
        blocker = self.subject.blocker.value
        if blocker:
            # A version with no skeleton at all is not an unfinished checklist;
            # say what actually has to happen instead of counting questions.
            text = blocker
        elif not settled:
            text += "  ·  bu sürüm dışa aktarılamaz"
        self.subject_panel.set_status(text, settled)
        index = self.side_tabs.indexOf(self.side_tabs.widget(1))
        self.side_tabs.setTabText(index, "Sporcu" if settled else "Sporcu  !")

    # ------------------------------------------------- live trim preview
    def _edit_started(self) -> None:
        """Remember where the playhead really is before a drag borrows it."""
        if self.viewmodel is not None and self._resume_position is None:
            self._resume_position = self.viewmodel.position.value

    def _preview_frame(self, position: int) -> None:
        """Follow a drag with the picture, without moving the playhead."""
        viewmodel = self.viewmodel
        review = viewmodel.review if viewmodel else None
        if review is None:
            return
        self.viewer.set_frame(review.frame(position), review.source_size)
        self.viewer.set_skeleton(
            review.joints_2d(position), review.bones, review.confidence(position)
        )
        self._show_pose(review, position)
        self.viewer.set_badge(f"kare {position + 1}")

    def _edit_finished(self) -> None:
        self.viewer.set_badge("")
        if self._resume_position is not None and self.viewmodel is not None:
            self._render_frame(self.viewmodel.position.value)
        self._resume_position = None

    # -------------------------------------------------------------- timeline
    def _set_tool(self, tool: Tool, *, sync: bool = False) -> None:
        self.timeline.set_tool(tool)
        if sync:
            self._tool_buttons[tool].setChecked(True)

    def _timeline_scrubbed(self, position: int) -> None:
        self._seek(position)

    def _interval_drawn(self, lane: str, start: int, end: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        if lane == "movements":
            viewmodel.add_movement(start, end)
        else:
            viewmodel.add_error(start, end)
        self._edit_finished()

    def _interval_changed(self, key: str, start: int, end: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        if viewmodel.movement_row(key) is not None:
            viewmodel.set_movement_bounds(key, start, end)
        else:
            viewmodel.set_error_bounds(key, start, end)
        self._edit_finished()

    def _timeline_selected(self, key: str) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        if viewmodel.movement_row(key) is not None:
            viewmodel.select_movement(key)
        elif key:
            viewmodel.select_error(key)

    def _timeline_activated(self, key: str) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        row = viewmodel.movement_row(key) or viewmodel.error_row(key)
        if row is not None:
            self.timeline.zoom_to(row.start, row.end)

    # ----------------------------------------------------------------- lists
    def _movements_changed(self, rows: tuple[MovementRow, ...]) -> None:
        self._push_intervals()
        self._suppress = True
        try:
            self.movement_list.clear()
            for index, row in enumerate(rows, start=1):
                item = QListWidgetItem(
                    f"{index:>2}. {row.text}   ({row.start}-{row.end})"
                )
                item.setData(Qt.ItemDataRole.UserRole, row.sample_id)
                item.setToolTip(READINESS_TEXT[row.readiness])
                self.movement_list.addItem(item)
        finally:
            self._suppress = False
        self._selection_changed()

    def _errors_changed(self, _rows: tuple[ErrorRow, ...]) -> None:
        self._push_intervals()
        self._selection_changed()

    def _push_intervals(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        intervals = [
            Interval(
                key=row.sample_id, start=row.start, end=row.end, lane="movements",
                text=row.text, status=row.status,
            )
            for row in viewmodel.movements.value
        ]
        intervals += [
            Interval(
                key=row.interval_id, start=row.start, end=row.end, lane="errors",
                text=row.text, status=row.status, parent=row.sample_id,
            )
            for row in viewmodel.errors.value
        ]
        self.timeline.set_intervals(intervals)

    def _list_selected(self, current: Optional[QListWidgetItem], _previous) -> None:  # noqa: ANN001
        if current is None or self._suppress or self.viewmodel is None:
            return
        self.viewmodel.select_movement(current.data(Qt.ItemDataRole.UserRole))

    def _error_list_selected(self, current: Optional[QListWidgetItem], _previous) -> None:  # noqa: ANN001
        if current is None or self._suppress or self.viewmodel is None:
            return
        self.viewmodel.select_error(current.data(Qt.ItemDataRole.UserRole))

    # ------------------------------------------------------------- selection
    def _selection_changed(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        error_key = viewmodel.selected_error.value
        movement_key = viewmodel.selected_movement.value
        self.timeline.set_active_movement(movement_key)
        self.timeline.set_selected(error_key or movement_key)

        self._suppress = True
        try:
            self._sync_movement_list(movement_key)
            if error_key and viewmodel.error_row(error_key) is not None:
                self._show_error(error_key)
                self.inspector.setCurrentIndex(2)
            elif movement_key and viewmodel.movement_row(movement_key) is not None:
                self._show_movement(movement_key)
                self.inspector.setCurrentIndex(1)
            else:
                self.inspector.setCurrentIndex(0)
                self.viewer.set_highlight(())
                self.skeleton.set_highlight(())
        finally:
            self._suppress = False

    def _sync_movement_list(self, sample_id: str) -> None:
        for index in range(self.movement_list.count()):
            item = self.movement_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == sample_id:
                self.movement_list.setCurrentItem(item)
                return
        self.movement_list.setCurrentItem(None)

    def _show_movement(self, sample_id: str) -> None:
        viewmodel = self.viewmodel
        row = viewmodel.movement_row(sample_id) if viewmodel else None
        if row is None:
            return
        order = [r.sample_id for r in viewmodel.movements.value].index(sample_id) + 1
        self.movement_title.setText(f"Hareket {order}/{len(viewmodel.movements.value)}")
        self.movement_state.setText(
            f"{READINESS_TEXT[row.readiness]} · {row.end - row.start + 1} kare"
            + (f" · {row.unclassified_errors} sınıfsız hata" if row.unclassified_errors else "")
        )
        self._select_combo(self.exercise_combo, row.exercise)
        self.movement_start.setValue(row.start)
        self.movement_end.setValue(row.end)
        self.exclude_box.setChecked(row.excluded)
        self.apply_all_button.setEnabled(bool(row.exercise))

        self.error_list.clear()
        for error in viewmodel.errors.value:
            if error.sample_id != sample_id:
                continue
            item = QListWidgetItem(f"{error.text}   ({error.start}-{error.end})")
            item.setData(Qt.ItemDataRole.UserRole, error.interval_id)
            self.error_list.addItem(item)
        self.viewer.set_highlight(())
        self.skeleton.set_highlight(())

    def _show_error(self, interval_id: str) -> None:
        viewmodel = self.viewmodel
        row = viewmodel.error_row(interval_id) if viewmodel else None
        if row is None:
            return
        self.error_title.setText(f"Hata aralığı · {row.end - row.start + 1} kare")
        self._select_combo(self.error_combo, row.error_class)
        index = self.joint_status_combo.findData(row.joint_status.value)
        self.joint_status_combo.setCurrentIndex(max(0, index))
        self.error_start.setValue(row.start)
        self.error_end.setValue(row.end)
        chosen = set(row.roles)
        for position in range(self.role_list.count()):
            item = self.role_list.item(position)
            item.setCheckState(
                Qt.CheckState.Checked
                if item.data(Qt.ItemDataRole.UserRole) in chosen
                else Qt.CheckState.Unchecked
            )
        marked = [self._roles[r] for r in row.roles if self._roles.get(r) is not None]
        self.viewer.set_highlight(marked)
        self.skeleton.set_highlight(marked)

    # ------------------------------------------------------------ vocabulary
    def _refill_classes(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        self._suppress = True
        try:
            for combo, options in (
                (self.exercise_combo, viewmodel.exercise_options.value),
                (self.error_combo, viewmodel.error_options.value),
            ):
                current = combo.currentData()
                combo.clear()
                combo.addItem("— seçilmedi —", "")
                for slot, (code, text) in enumerate(options, start=1):
                    suffix = f"  [{slot}]" if combo is self.exercise_combo and slot <= QUICK_SLOTS else ""
                    combo.addItem(f"{text}{suffix}", code)
                self._select_combo(combo, current or "")
        finally:
            self._suppress = False

    def _fill_roles(self) -> None:
        self.role_list.clear()
        for role, index in sorted(self._roles.items()):
            if index is None:
                # A role this skeleton has no joint for is not offered. Listing
                # it would invite a claim about a joint that does not exist.
                continue
            item = QListWidgetItem(role.replace("_", " "))
            item.setData(Qt.ItemDataRole.UserRole, role)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.role_list.addItem(item)

    @staticmethod
    def _select_combo(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    # --------------------------------------------------------------- editing
    def _exercise_chosen(self, _index: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        code = self.exercise_combo.currentData() or ""
        sample_id = viewmodel.selected_movement.value
        if sample_id and code:
            viewmodel.label_movement(
                sample_id, code, note=self.movement_note.toPlainText().strip()
            )

    def _quick_class(self, index: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        options = viewmodel.exercise_options.value
        sample_id = viewmodel.selected_movement.value
        if index < len(options) and sample_id:
            viewmodel.label_movement(sample_id, options[index][0])

    def _apply_to_unlabelled(self) -> None:
        if self.viewmodel is not None:
            code = self.exercise_combo.currentData() or ""
            if code:
                self.viewmodel.apply_exercise_to_unlabelled(code)

    def _new_exercise(self) -> None:
        self._create_class(exercise=True)

    def _new_error_class(self) -> None:
        self._create_class(exercise=False)

    def _create_class(self, *, exercise: bool) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        title = "Yeni hareket sınıfı" if exercise else "Yeni hata sınıfı"
        name, accepted = QInputDialog.getText(self, title, "Ad:")
        if not accepted or not name.strip():
            return
        code = (
            viewmodel.create_exercise(name)
            if exercise
            else viewmodel.create_error_class(name)
        )
        if not code:
            return
        if exercise:
            self._select_combo(self.exercise_combo, code)
            self._exercise_chosen(0)
        else:
            self._select_combo(self.error_combo, code)
            self._commit_error(0)

    def _movement_bounds_typed(self, _value: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        # Typed edits preview too: the number means nothing without the frame.
        self._preview_frame(self.sender().value() if self.sender() else 0)
        sample_id = viewmodel.selected_movement.value
        if sample_id:
            viewmodel.set_movement_bounds(
                sample_id, self.movement_start.value(), self.movement_end.value()
            )

    def _excluded_toggled(self, excluded: bool) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        sample_id = viewmodel.selected_movement.value
        if sample_id:
            viewmodel.set_excluded(sample_id, excluded)

    def _delete_movement(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is not None and viewmodel.selected_movement.value:
            viewmodel.remove_movement(viewmodel.selected_movement.value)

    def _add_error_here(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        row = viewmodel.movement_row(viewmodel.selected_movement.value)
        if row is None:
            return
        position = viewmodel.position.value
        span = max(1, (row.end - row.start) // 10)
        start = max(row.start, min(row.end, position))
        viewmodel.add_error(start, min(row.end, start + span))

    def _error_class_chosen(self, _index: int) -> None:
        self._commit_error(0)

    def _roles_changed(self, _item: QListWidgetItem) -> None:
        if self._suppress:
            return
        # Naming a joint *is* the claim that joints were chosen, so the status
        # follows the list rather than being a second thing to remember.
        if self._checked_roles():
            index = self.joint_status_combo.findData(JointStatus.SELECTED.value)
            if index >= 0:
                self.joint_status_combo.setCurrentIndex(index)
        self._commit_error(0)

    def _checked_roles(self) -> tuple[str, ...]:
        return tuple(
            self.role_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.role_list.count())
            if self.role_list.item(i).checkState() is Qt.CheckState.Checked
        )

    def _commit_error(self, _index: int = 0) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        interval_id = viewmodel.selected_error.value
        code = self.error_combo.currentData() or ""
        if not interval_id or not code:
            return
        roles = self._checked_roles()
        status = JointStatus(self.joint_status_combo.currentData())
        if roles and status is not JointStatus.SELECTED:
            status = JointStatus.SELECTED
        viewmodel.label_error(
            interval_id,
            error_class=code,
            roles=roles,
            joint_status=status,
            note=self.error_note.toPlainText().strip(),
        )
        marked = [self._roles[r] for r in roles if self._roles.get(r) is not None]
        self.viewer.set_highlight(marked)
        self.skeleton.set_highlight(marked)

    def _error_bounds_typed(self, _value: int) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        self._preview_frame(self.sender().value() if self.sender() else 0)
        interval_id = viewmodel.selected_error.value
        if interval_id:
            viewmodel.set_error_bounds(
                interval_id, self.error_start.value(), self.error_end.value()
            )

    def _delete_error(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is not None and viewmodel.selected_error.value:
            viewmodel.remove_error(viewmodel.selected_error.value)

    def _back_to_movement(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.selected_error.set("")
            self._selection_changed()

    def _delete_selected(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        if viewmodel.selected_error.value:
            self._delete_error()
        elif viewmodel.selected_movement.value:
            self._delete_movement()

    # ----------------------------------------------------------------- misc
    def _next_unfinished(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.go_to_next_unfinished()

    def _undo(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.undo()

    def _redo(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.redo()

    def _flush(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.flush()

    def apply_tokens(self, tokens: ThemeTokens) -> None:
        super().apply_tokens(tokens)
        self.viewer.set_tokens(tokens)
        self.skeleton.set_tokens(tokens)
        self.subject_panel.set_tokens(tokens)
        self.timeline.set_tokens(tokens)


__all__ = ["ReviewPage", "QUICK_SLOTS"]
