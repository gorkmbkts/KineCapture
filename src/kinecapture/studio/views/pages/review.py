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

from typing import Optional, Sequence

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from kinecapture.studio.services.skeleton3d import body_target, up_axis_for
from kinecapture.studio.services.skeleton3d import (
    FACING_HIPS,
    FACING_MANUAL,
    FACING_SHOULDERS,
    FACING_UNKNOWN,
    facing_azimuth,
    is_left_handed,
    recording_azimuth,
)
from kinecapture.studio.services.stage_layout import solve_stage, source_ratio_from
from kinecapture.processing.annotations import JointStatus
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.subject import SubjectViewModel
from kinecapture.processing.annotations import Readiness, RolesOrigin
from kinecapture.studio.viewmodels.review import (
    READINESS_TEXT,
    ErrorRow,
    MovementRow,
    ReviewViewModel,
)

from .. import iconset
from ..annotationbar import AnnotationEditorBar
from ..camerapanel import CameraPanel
from ..labelwindows import (
    AdvancedCameraWindow,
    ClassBrowser,
    JointEvidenceWindow,
    NoteWindow,
    OverflowPanel,
    SubjectListWindow,
)
from ..iconstrip import IconStripPanel
from ..labelviews import ClassPicker, MovementCard
from ..loading import LoadingSurface
from ..timeline import Interval, TimelineView, Tool
from ..skeleton3d import Skeleton3DView
from ..subject import SubjectPanel
from ..viewer import ReviewViewer
from ..widgets import ElidedLabel, label, mono_label, separator
from .base import StudioPage

#: How many exercise classes get a number key. Nine, because that is how many
#: digits there are above the letters.
QUICK_SLOTS = 9

#: Playback speeds offered in the toolbar. A speed changes how fast frames
#: are *shown*; it never changes a timestamp, a frame index or a measurement.
PLAYBACK_SPEEDS = (0.25, 0.5, 1.0, 2.0)

#: How long after the last edit the labels are written. Short enough that
#: almost nothing is lost to a crash, long enough that holding an arrow key
#: does not write once per frame.
AUTOSAVE_MS = 4000

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

    #: This screen has a real inspector of its own - the label/athlete panel
    #: on the right. The shell keeps its generic one shut here rather than
    #: opening a second, emptier panel beside it.
    owns_inspector = True

    #: And it is not optional. The camera controls, the label summary and the
    #: athlete tab are how this screen is used; a recording was annotated for
    #: an hour on 20 September with all three gone, because a toggle meant for
    #: the shell's own panel had hidden the page's.
    inspector_is_permanent = True

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
        #: A fault class is being defined: a name has been typed and the 3-D
        #: view is in picking mode. JOINT-02 is explicit that picking exists
        #: only for the length of this, so a double-click meant for the camera
        #: never silently edits anatomy.
        self._fault_draft = False
        #: The joints picked for the draft, in the order they were picked.
        self._draft_joints: list[int] = []
        #: What the screen was sent here to fix, if anything. Applied once the
        #: version is actually open, never before: landing on an editor for a
        #: recording that has not loaded shows the previous one's labels.
        self._pending_focus = ""
        #: Where the current reference front came from. Never assumed: it is
        #: what the panel shows and what a report would have to cite.
        self._front_source = FACING_UNKNOWN
        self._camera = None
        self._editing_enabled = False
        #: Playback speed as a multiple of the recording's own rate.
        self._speed = 1.0
        #: While true, playback wraps inside the selected interval instead of
        #: running to the end of the take.
        self._loop_selection = False
        #: Whether the toolbar has folded its secondary controls away.
        self._overflowed = False
        #: Whether the annotator wants the 3-D view. Not the same question as
        #: whether Qt currently considers the widget visible.
        self._skeleton_shown = True
        #: Whether the 2-D skeleton is drawn over the picture, and the last
        #: points drawn, so the toggle can put them back without re-reading.
        self._overlay_shown = True
        self._last_points = None
        self._last_confidence = None

        self._clock = QTimer(self)
        self._clock.setTimerType(Qt.TimerType.PreciseTimer)
        self._clock.timeout.connect(self._tick)

        # Labels reach disk shortly after the last edit, not only when the
        # screen is left. An hour of labelling lost to a crash is an hour a
        # coach will not spend again, and the write is small enough that
        # doing it often costs nothing.
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self._save_now)

        # Four horizontal bands, in the order the 20 September review fixes
        # them: the working surface, the contextual editor, one row of tools,
        # the timeline. Not splitters - the first band's height is *solved*
        # from the recording's aspect ratio and the panel's minimum width, and
        # a splitter would let a drag put it somewhere the picture has to be
        # cropped to reach.
        editor = QWidget(self)
        bands = QVBoxLayout(editor)
        bands.setContentsMargins(0, 0, 0, 0)
        bands.setSpacing(tokens.metric("KcSpacingSm"))
        bands.addWidget(self._build_top())
        bands.addWidget(self._build_editor_bar())
        bands.addWidget(self._build_toolbar())
        bands.addWidget(self._build_timeline())
        # No stretch. There used to be one here, and the height the stage
        # could not use - 135 px at 1852x830 - collected under the timeline as
        # a margin. The editor band takes it now, which is what the review
        # asked for: a taller window should buy a roomier editor.
        self.editor = editor

        # One surface at a time. While a version is opening the screen shows
        # the preparation page *in place of* the editor, and the editor appears
        # whole when it is ready - not video first, then timeline, then a
        # skeleton, which is four screens in a row and none of them the one
        # that was asked for.
        self.loading = LoadingSurface(tokens, self)
        self.loading.cancelled.connect(self._cancel_open)
        self.loading.retried.connect(self._retry_open)
        self.surface = QStackedWidget(self)
        self.surface.addWidget(self.editor)
        self.surface.addWidget(self.loading)
        self.body_layout.addWidget(self.surface, 1)

        # LAYOUT-01: no page title and no run-id line. Both were a band of
        # height across the top of a screen whose scarcest direction is
        # height, and the run id belongs with the version's other details in
        # the panel rather than as a heading nobody reads twice.
        self._header.hide()

        self._install_shortcuts()
        self._show_nothing()

    # ------------------------------------------------------------------ build
    def _build_top(self) -> QWidget:
        """The first band: picture, 3-D and the editing panel, as one surface.

        Three regions inside one frame, divided by one-pixel rules rather than
        separated by gaps. Laid out by hand from
        :func:`~kinecapture.studio.services.stage_layout.solve_stage` rather
        than by stretch factors, because the two things that decide the widths
        are the recording's own aspect ratio and the panel's readable minimum -
        neither of which a stretch factor knows about.

        Video and 3-D side by side: the question a coach actually asks is
        whether the tracked skeleton matches what the camera saw, and that is
        only answerable with both on screen at the same frame.
        """
        tokens = self._tokens
        stage = QFrame()
        stage.setProperty("kcSurface", "stage")
        row = QHBoxLayout(stage)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # Stretches on both ends. A window wider than the tallest band its
        # height allows leaves room the band cannot use, and the band is
        # centred in it rather than anything being stretched to fill it.
        row.addStretch(1)
        self.viewer = ReviewViewer(tokens)
        row.addWidget(self.viewer)
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.skeleton = Skeleton3DView(tokens)
        self.skeleton.camera_changed.connect(self._remember_camera)
        self.skeleton.joint_picked.connect(self._joint_picked)
        row.addWidget(self.skeleton)
        row.addWidget(separator(Qt.Orientation.Vertical))
        row.addWidget(self._build_inspector())
        row.addStretch(1)

        self.stage = stage
        #: The recording's width / height, from its metadata. ``0.0`` until a
        #: version is open, which is the one case the solver falls back for.
        self._source_ratio = 0.0
        return stage

    def _build_editor_bar(self) -> QWidget:
        """The second band: whatever is selected, edited in place."""
        self.editor_bar = AnnotationEditorBar(self._tokens, self)
        bar = self.editor_bar
        bar.empty_next_button.clicked.connect(self._next_unfinished)

        # The page keeps the names its handlers already use. The widgets moved
        # out of the panel; the code that drives them did not have to.
        self.movement_title = bar.movement_title
        self.movement_state = bar.movement_state
        self.movement_start = bar.movement_start
        self.movement_end = bar.movement_end
        self.exclude_box = bar.exclude_box
        self.apply_all_button = bar.apply_all_button
        self.delete_movement_button = bar.delete_movement_button
        self.error_title = bar.error_title
        self.error_start = bar.error_start
        self.error_end = bar.error_end
        self.back_to_movement_button = bar.back_to_movement_button
        self.delete_error_button = bar.delete_error_button

        self.movement_start.valueChanged.connect(self._movement_bounds_typed)
        self.movement_end.valueChanged.connect(self._movement_bounds_typed)
        self.error_start.valueChanged.connect(self._error_bounds_typed)
        self.error_end.valueChanged.connect(self._error_bounds_typed)
        self.exclude_box.toggled.connect(self._excluded_toggled)
        self.apply_all_button.clicked.connect(self._apply_to_unlabelled)
        self.delete_movement_button.clicked.connect(self._delete_movement)
        self.back_to_movement_button.clicked.connect(self._back_to_movement)
        self.delete_error_button.clicked.connect(self._delete_error)

        bar.exercise_classes.chosen.connect(self._exercise_chosen)
        bar.exercise_classes.create_requested.connect(self._create_exercise)
        bar.exercise_classes.browse_requested.connect(
            lambda: self._browse_classes(fault=False)
        )
        bar.error_classes.chosen.connect(self._error_class_chosen)
        bar.error_classes.create_requested.connect(self._create_fault_class)
        bar.error_classes.browse_requested.connect(
            lambda: self._browse_classes(fault=True)
        )
        bar.error_classes.draft_changed.connect(self._fault_draft_typed)
        bar.edit_joints_button.clicked.connect(self._edit_joint_evidence)
        bar.error_note_button.clicked.connect(self._edit_error_note)
        return bar

    # ------------------------------------------------------------- geometry
    def _apply_stage_geometry(self) -> None:
        """Size the three regions from the window and the source's own ratio."""
        tokens = self._tokens
        # Before the first layout both of these are zero, and solving against
        # them would hand back the degenerate band. Asked again from
        # ``resizeEvent`` and from the moment the editor is shown.
        if self.stage.width() <= 0 or self.surface.height() <= 0:
            return
        geometry = solve_stage(
            available_width=self.stage.width(),
            available_height=self.surface.height(),
            source_ratio=self._source_ratio,
            panel_min_width=tokens.metric("KcLabelPanelMinWidth"),
            # Asked of the widget, not of a token. `KcTimelineMinHeight` is
            # 148, which is the lanes only - the ruler and the gaps between
            # them bring the real floor to 202. The band used to end in a
            # stretch, so a 54 px under-count simply shrank the empty margin
            # and nobody saw it; now that the editor takes that height, the
            # same error would make the bands overlap the stage.
            timeline_min_height=max(
                tokens.metric("KcTimelineMinHeight"),
                self.timeline.minimumHeight(),
            ),
            # What the toolbar *is*, not only what it hints. Its hint changes
            # between the first show and a later one - 48 pixels became 62
            # when the page was left and returned to - and the solver was
            # dividing the height against the smaller number while the band
            # took the larger, which put the editor ten pixels over the stage.
            toolbar_height=max(
                self.toolbar.sizeHint().height(),
                self.toolbar.minimumSizeHint().height(),
                self.toolbar.height(),
            ),
            stage_min_height=tokens.metric("KcStageMinHeight"),
            divider_width=tokens.metric("KcBorderWidth"),
            # The band is a working surface with a floor of its own, and a
            # ceiling past which extra height is a wide empty box rather than
            # a better editor.
            editor_min_height=self.editor_bar.minimumSizeHint().height(),
            editor_max_height=tokens.metric("KcEditorBarMaxHeight"),
            band_spacing=tokens.metric("KcSpacingSm"),
        )
        self._stage_geometry = geometry
        if geometry.height <= 0:
            return
        if not getattr(self, "_bands_watched", False):
            self.toolbar.installEventFilter(self)
            self.timeline.installEventFilter(self)
            self._bands_watched = True
        self.stage.setFixedHeight(geometry.height)
        self.editor_bar.setFixedHeight(geometry.editor_height)
        self.viewer.setFixedWidth(geometry.video_width)
        # Square. An orbit around a person is not a wider-than-tall thing, and
        # a stretched viewport makes a lean look like a camera angle.
        self.skeleton.setFixedWidth(geometry.skeleton_width)
        self.side_tabs.setFixedWidth(geometry.panel_width)

    @property
    def stage_geometry(self):  # noqa: ANN201 - StageGeometry
        return getattr(self, "_stage_geometry", None)

    def set_source_ratio(self, ratio: float) -> None:
        """Tell the layout what shape the recording is. Read, never assumed."""
        self._source_ratio = float(ratio or 0.0)
        self._apply_stage_geometry()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self._apply_stage_geometry()
        self._update_overflow()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().showEvent(event)
        self._apply_stage_geometry()
        self._update_overflow()
        # And again once this turn of the event loop has finished laying the
        # bands out. Widgets that report one height while hidden and another
        # once shown - the toolbar is one - are only measurable afterwards.
        QTimer.singleShot(0, self._apply_stage_geometry)

    def eventFilter(self, watched, event) -> bool:  # noqa: ANN001, N802 - Qt naming
        """Re-solve when a band this page does not control changes height.

        The stage's height is whatever is left after the toolbar, the timeline
        and the editor have taken theirs. Two of those size themselves, so a
        solution is only as good as the heights it was given - and a band that
        grows after the solve does not push the others down, it draws over
        them.
        """
        if event.type() == QEvent.Type.Resize and watched in (
            self.toolbar,
            self.timeline,
        ):
            self._apply_stage_geometry()
        return super().eventFilter(watched, event)

    def _build_toolbar(self) -> QWidget:
        """The second band: everything that drives playback and drawing.

        One row, not two. It used to be a transport strip under the video and
        a drawing strip above the timeline, which put "Oynat" and "Hareket çiz"
        at opposite ends of the screen although they are used within a second
        of each other - and cost two rows of height on a screen whose scarcest
        direction is height.

        The groups read left to right in the order the approved design fixes
        them: transport · position · tools · snap and zoom · undo/redo ·
        next gap · save state. Thin rules separate the groups; every button is
        the same square size, so the row has one optical rhythm.
        """
        tokens = self._tokens
        bar = QFrame()
        bar.setProperty("kcSurface", "header")
        row = QHBoxLayout(bar)
        # No margins here: ``QWidget[kcSurface="header"]`` carries the inset,
        # so the gap between the strip's edge and its buttons is decided in one
        # place rather than added twice.
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.metric("KcSpacingXs"))

        def icon_button(
            icon_key: str, name: str, tip: str, *, checkable: bool = False
        ) -> QToolButton:
            button = QToolButton()
            button.setProperty("kcRole", "iconButton")
            button.setIcon(
                iconset.icon(icon_key, tokens, size=tokens.metric("KcIconSize"))
            )
            button.setIconSize(iconset.icon_size(tokens))
            button.setCheckable(checkable)
            button.setAutoRaise(True)
            # An icon with no text needs a name of its own, or a screen reader
            # announces a blank button.
            button.setAccessibleName(name)
            button.setToolTip(tip)
            return button

        self._icon_button = icon_button

        # 1. Transport. Five different jobs, five different icons: they were
        #    "|◀ ◀ ▶ ▶ ▶|" once and the middle three were indistinguishable.
        self._transport: dict[str, QToolButton] = {}
        for key, icon_key, name, tip in (
            ("first", "first", "Başa git", "Başa git (Home)"),
            ("back", "step-back", "Bir kare geri", "Bir kare geri (←)"),
            ("play", "play", "Oynat", "Oynat / duraklat (Boşluk)"),
            ("forward", "step-forward", "Bir kare ileri", "Bir kare ileri (→)"),
            ("last", "last", "Sona git", "Sona git (End)"),
        ):
            button = icon_button(icon_key, name, tip)
            self._transport[key] = button
            row.addWidget(button)
        self.first_button = self._transport["first"]
        self.back_button = self._transport["back"]
        self.play_button = self._transport["play"]
        self.forward_button = self._transport["forward"]
        self.last_button = self._transport["last"]

        self.first_button.clicked.connect(lambda: self._seek(0))
        self.back_button.clicked.connect(lambda: self._step(-1))
        self.play_button.clicked.connect(self._toggle_play)
        self.forward_button.clicked.connect(lambda: self._step(1))
        self.last_button.clicked.connect(self._seek_end)

        # 2. Where we are, in both units a person asks in.
        row.addSpacing(tokens.metric("KcSpacingMd"))
        self.position_label = mono_label("—")
        self.position_label.setAccessibleName("Süre ve kare")
        row.addWidget(self.position_label)

        # 3. Review conveniences: loop the selection, and a playback speed.
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.loop_button = icon_button(
            "loop",
            "Seçili aralığı döngüde oynat",
            "Seçili aralığı döngüde oynat",
            checkable=True,
        )
        self.loop_button.toggled.connect(self._loop_toggled)
        row.addWidget(self.loop_button)
        self.speed_box = QComboBox()
        self.speed_box.setAccessibleName("Oynatma hızı")
        self.speed_box.setToolTip("Oynatma hızı. Kayıt verisi değişmez.")
        for factor in PLAYBACK_SPEEDS:
            self.speed_box.addItem(f"{factor:g}×", factor)
        self.speed_box.setCurrentIndex(PLAYBACK_SPEEDS.index(1.0))
        self.speed_box.activated.connect(self._speed_chosen)
        row.addWidget(self.speed_box)

        # 4. The three tools. Drawing a movement and drawing a fault are two
        #    different kinds of claim, so they get two different icons as well
        #    as two different colours.
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_buttons: dict[Tool, QToolButton] = {}
        for tool, icon_key, name, tip in (
            (Tool.SCRUB, "navigate", "Gez", "Sürükleyerek gez, kaydır (V)"),
            (
                Tool.DRAW_MOVEMENT,
                "draw-movement",
                "Hareket çiz",
                "Boş alanda sürükleyerek hareket ekle (M)",
            ),
            (
                Tool.DRAW_ERROR,
                "draw-fault",
                "Hata çiz",
                "Seçili hareketin içinde sürükleyerek hata ekle (E)",
            ),
        ):
            button = icon_button(icon_key, name, tip, checkable=True)
            self.tool_group.addButton(button)
            self._tool_buttons[tool] = button
            button.clicked.connect(lambda _checked=False, t=tool: self._set_tool(t))
            row.addWidget(button)
        self._tool_buttons[Tool.SCRUB].setChecked(True)

        # 5. Snapping and zoom.
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.snap_button = icon_button(
            "snap",
            "Kenara yapış",
            "Sürüklerken yakın kenarlara ve oynatma çizgisine yapış",
            checkable=True,
        )
        self.snap_button.setChecked(True)
        self.snap_button.toggled.connect(lambda on: self.timeline.set_snap(on))
        row.addWidget(self.snap_button)
        for icon_key, name, tip, slot in (
            ("zoom-out", "Uzaklaş", "Uzaklaş (Ctrl+-)",
             lambda: self.timeline.zoom(1 / 1.4)),
            ("zoom-in", "Yakınlaş", "Yakınlaş (Ctrl++)",
             lambda: self.timeline.zoom(1.4)),
            ("zoom-all", "Tümünü göster", "Tamamını göster (Ctrl+0)",
             lambda: self.timeline.zoom_all()),
        ):
            button = icon_button(icon_key, name, tip)
            button.clicked.connect(slot)
            row.addWidget(button)

        # 6. Undo and redo.
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.undo_button = icon_button(
            "undo", "Geri al", "Son kararı geri al (Ctrl+Z)"
        )
        self.undo_button.clicked.connect(self._undo)
        self.redo_button = icon_button(
            "redo", "Yinele", "Geri alınanı yinele (Ctrl+Y)"
        )
        self.redo_button.clicked.connect(self._redo)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)

        # 7. Next gap, and 8. the save state. Both stay to the right, where
        #    they are read rather than reached for.
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.next_gap_button = QPushButton("Sonraki eksik")
        self.next_gap_button.setToolTip(
            "Hâlâ bir şeyi eksik olan ilk harekete git (Tab)"
        )
        self.next_gap_button.clicked.connect(self._next_unfinished)
        row.addWidget(self.next_gap_button)

        row.addStretch(1)
        self.progress_label = label("—", role="contextValue")
        row.addWidget(self.progress_label)
        row.addWidget(separator(Qt.Orientation.Vertical))
        self.save_state = label("kaydedildi", role="contextValue")
        self.save_state.setProperty("kcStatus", "ready")
        self.save_state.setToolTip(
            "Etiketler son değişiklikten kısa süre sonra kendiliğinden yazılır "
            "(Ctrl+S hemen yazar)."
        )
        row.addWidget(self.save_state)

        # Secondary controls fold in here when the row runs out of width, so a
        # narrow window loses the extras and keeps playback and drawing.
        self.overflow_button = icon_button(
            "more", "Diğer araçlar", "Dar pencerede taşan araçlar"
        )
        self.overflow_menu = QMenu(self.overflow_button)
        self.overflow_button.setMenu(self.overflow_menu)
        self.overflow_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.overflow_button.hide()
        row.addWidget(self.overflow_button)

        # What may fold away, in the order it folds. Playback and the three
        # tools are never in this list.
        self._overflowable = (
            (self.speed_box, "Oynatma hızı"),
            (self.loop_button, "Seçili aralığı döngüde oynat"),
            (self.next_gap_button, "Sonraki eksik"),
        )
        self.toolbar = bar
        return bar

    def _update_overflow(self) -> None:
        """Fold the secondary controls away when the row will not fit them."""
        bar = getattr(self, "toolbar", None)
        if bar is None or bar.width() <= 0:
            return
        needed = bar.layout().minimumSize().width()
        crowded = needed > bar.width()
        if crowded == getattr(self, "_overflowed", False):
            return
        self._overflowed = crowded
        self.overflow_menu.clear()
        for widget, caption in self._overflowable:
            widget.setVisible(not crowded)
            if crowded:
                action = self.overflow_menu.addAction(caption)
                action.triggered.connect(
                    lambda _checked=False, w=widget: self._trigger_overflowed(w)
                )
        self.overflow_button.setVisible(crowded)

    @staticmethod
    def _trigger_overflowed(widget) -> None:  # noqa: ANN001
        """Run a folded-away control from the menu entry standing in for it."""
        if isinstance(widget, QToolButton):
            widget.toggle() if widget.isCheckable() else widget.click()
        elif isinstance(widget, QPushButton):
            widget.click()
        elif isinstance(widget, QComboBox):
            widget.showPopup()

    def _build_timeline(self) -> QWidget:
        """The third band: the timeline, and nothing else."""
        tokens = self._tokens
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.timeline = TimelineView(tokens)
        self.timeline.position_changed.connect(self._timeline_scrubbed)
        self.timeline.preview_position.connect(self._preview_frame)
        self.timeline.edit_started.connect(self._edit_started)
        self.timeline.edit_cancelled.connect(self._edit_cancelled)
        self.timeline.interval_changed.connect(self._interval_changed)
        self.timeline.interval_drawn.connect(self._interval_drawn)
        self.timeline.selection_changed.connect(self._timeline_selected)
        self.timeline.interval_activated.connect(self._timeline_activated)
        column.addWidget(self.timeline, 1)
        return panel

    def _build_inspector(self) -> QWidget:
        """The top-right panel: three places, and not one of them scrolls.

        R-02 is a hard constraint, so the rule here is structural rather than
        a matter of restraint: **nothing in this panel is wrapped in a scroll
        area.** What used to make one necessary - the movement and fault forms
        - is in the band below now, and what is still too long for the space
        goes to its own window rather than under a fold.

        A repeated movement list is gone too. It sat above every editor
        showing what the timeline already shows, and on the audit's screen it
        spent a third of the panel's height on one row.
        """
        tokens = self._tokens
        self.side_tabs = IconStripPanel(tokens)
        self.camera_panel = CameraPanel(tokens)
        quick = QWidget()
        quick_row = QHBoxLayout(quick)
        quick_row.setContentsMargins(0, 0, 0, 0)
        quick_row.setSpacing(tokens.metric("KcSpacingXs"))
        for preset in self.camera_panel.preset_buttons.values():
            button = QToolButton(quick)
            button.setText(preset.text())
            button.setAccessibleName(preset.accessibleName())
            button.setToolTip(preset.toolTip())
            button.clicked.connect(preset.click)
            quick_row.addWidget(button)
        more = QToolButton(quick)
        more.setText("Diğer")
        more.setAccessibleName("Diğer açılar")
        more.setMenu(self.camera_panel.preset_menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        quick_row.addWidget(more)
        self.camera_overflow = OverflowPanel(
            self.camera_panel, "Kamera araçları", tokens, quick
        )
        self.side_tabs.add_view(
            "camera",
            self.camera_overflow,
            icon="camera-tools",
            name="Kamera ve bakış",
            tooltip="Kamera presetleri, merkezle, zemin ve kaplama",
        )
        self._label_button = self.side_tabs.add_view(
            "labels",
            self._build_summary_inspector(),
            icon="labels",
            name="Etiket özeti",
            tooltip="Ne etiketlendi, ne eksik",
        )
        self._label_button.clicked.connect(self._label_icon_pressed)
        self.subject_panel = SubjectPanel(tokens)
        self.subject_overflow = OverflowPanel(
            self.subject_panel, "Kişi araçları", tokens
        )
        self.side_tabs.add_view(
            "subject",
            self.subject_overflow,
            icon="people",
            name="Kişi",
            tooltip="Kayıttaki kişiler, sporcu seçimi ve belirsiz aralıklar",
        )
        self.side_tabs.show_view("labels")
        self.side_tabs.setMinimumWidth(tokens.metric("KcLabelPanelMinWidth"))
        self._connect_camera_panel()
        return self.side_tabs

    # ------------------------------------------------------- helper windows
    def _window(self, name: str, factory):  # noqa: ANN001, ANN201
        """One modeless window per purpose, built the first time it is asked
        for and kept afterwards so it reopens where it was left."""
        existing = getattr(self, name, None)
        if existing is None:
            existing = factory()
            setattr(self, name, existing)
        return existing

    def _open_advanced_camera(self) -> None:
        """The occasional camera controls, in their own window."""
        window = self._window(
            "_advanced_camera",
            lambda: AdvancedCameraWindow(
                self._tokens, self.camera_panel.advanced_widgets(), self
            ),
        )
        window.show()
        window.raise_()

    def _open_subject_lists(self) -> None:
        """The people and the open questions, where they have room to be lists."""
        window = self._window("_subject_window", self._make_subject_window)
        window.show()
        window.raise_()

    def _make_subject_window(self) -> SubjectListWindow:
        window = SubjectListWindow(self._tokens, self)
        self.subject_panel.attach_lists(window.candidate_box, window.question_box)
        return window

    def _browse_classes(self, *, fault: bool) -> None:
        """The classes the band could not fit, as a searchable list."""
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        browser = self._window(
            "_fault_browser" if fault else "_exercise_browser",
            lambda: self._make_browser(fault=fault),
        )
        browser.set_options(
            viewmodel.error_options.value if fault else viewmodel.exercise_options.value
        )
        browser.show()
        browser.raise_()

    def _make_browser(self, *, fault: bool) -> ClassBrowser:
        browser = ClassBrowser(
            "Hata sınıfları" if fault else "Hareket sınıfları", self._tokens, self
        )
        # A class picked in "Diğer sınıflar" is a class the annotator chose,
        # so it becomes the first chip once the picker closes - the user asked
        # for exactly that. The strip's own `chosen` signal does this for a
        # chip press; the picker has to say so itself.
        strip = self.editor_bar.error_classes if fault else self.editor_bar.exercise_classes
        browser.chosen.connect(strip.note_used)
        browser.chosen.connect(
            self._error_class_chosen if fault else self._exercise_chosen
        )
        return browser

    def _edit_error_note(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or not viewmodel.selected_error.value:
            return
        row = viewmodel.error_row(viewmodel.selected_error.value)
        if row is None:
            return
        window = self._window("_note_window", self._make_note_window)
        window.show_note(f"Hata aralığı {row.start}–{row.end}", row.note)
        window.show()
        window.raise_()

    def _make_note_window(self) -> NoteWindow:
        window = NoteWindow(self._tokens, self)
        window.saved.connect(self._note_saved)
        return window

    def _note_saved(self, text: str) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or not viewmodel.selected_error.value:
            return
        self._commit_error(note=text)

    def _edit_joint_evidence(self) -> None:
        """The exception flow: correcting one interval's joints by name.

        Picking on the skeleton is the way in; this is for the joint that is
        hidden at every angle, the version with no 3-D data, and reading an
        old label back. Explicitly opened, never the default.
        """
        viewmodel = self.viewmodel
        if viewmodel is None or not viewmodel.selected_error.value:
            return
        row = viewmodel.error_row(viewmodel.selected_error.value)
        if row is None:
            return
        window = self._window("_joint_window", self._make_joint_window)
        window.set_statuses(
            [(status.value, text) for status, text in _JOINT_STATUS_TEXT]
        )
        window.show_interval(
            f"Hata aralığı {row.start}–{row.end}",
            [role for role, index in self._roles.items() if index is not None],
            row.roles,
            row.joint_status.value,
        )
        window.show()
        window.raise_()

    def _make_joint_window(self) -> JointEvidenceWindow:
        window = JointEvidenceWindow(self._tokens, self)
        window.applied.connect(self._joint_evidence_applied)
        return window

    def _joint_evidence_applied(self, roles, status: str) -> None:  # noqa: ANN001
        """Roles chosen by name are still roles somebody chose."""
        viewmodel = self.viewmodel
        interval_id = viewmodel.selected_error.value if viewmodel else ""
        if not interval_id:
            return
        chosen = tuple(str(role) for role in roles)
        joint_status = JointStatus(status) if status else JointStatus.UNSPECIFIED
        if chosen and joint_status is not JointStatus.SELECTED:
            joint_status = JointStatus.SELECTED
        viewmodel.label_error(
            interval_id,
            error_class=self.editor_bar.error_classes.selected,
            roles=chosen,
            joint_status=joint_status,
            note=None,
        )
        self._show_error(interval_id)

    def _connect_camera_panel(self) -> None:
        panel = self.camera_panel
        panel.preset_chosen.connect(self.skeleton.go_to_preset)
        panel.centre_requested.connect(self.skeleton.centre_on_body)
        panel.fit_requested.connect(self._fit_body)
        panel.previous_requested.connect(self.skeleton.return_to_previous_view)
        panel.view_saved.connect(self.skeleton.save_view)
        panel.view_restored.connect(self.skeleton.restore_saved_view)
        panel.front_set.connect(self._set_front)
        panel.floor_toggled.connect(self.skeleton.set_floor_visible)
        panel.overlay_toggled.connect(self._toggle_overlay)
        panel.reduce_motion_toggled.connect(self.skeleton.set_reduce_motion)
        panel.advanced_requested.connect(self._open_advanced_camera)
        self.skeleton.camera_changed.connect(self._show_compass)

    def _show_compass(self) -> None:
        camera = self.skeleton.camera
        # Measured from the recording's own front, not from the world axis, so
        # the dial and the preset labels agree with each other.
        self.camera_panel.compass.show_camera(
            camera.azimuth - self.skeleton.reference_azimuth, camera.elevation
        )

    def _fit_body(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or viewmodel.review is None:
            return
        review = viewmodel.review
        self.skeleton.frame_on(
            review.joints_3d_window(0, min(review.frames, 300))
        )

    def _set_front(self) -> None:
        """The manual override. A correction, never the normal way in."""
        self.skeleton.use_current_view_as_front()
        self._front_source = FACING_MANUAL
        self.camera_panel.show_front_source(
            FACING_MANUAL, self.FRONT_SOURCE_TEXT[FACING_MANUAL]
        )
        self._show_compass()
        self.show_message(
            Message(
                headline="Bu bakış 'ön' yönü olarak tanımlandı.",
                severity=Severity.INFO,
                detail="Presetler bundan sonra bu yöne göre hesaplanır.",
            )
        )

    def _toggle_overlay(self, shown: bool) -> None:
        """The 2-D skeleton over the picture. The picture itself stays."""
        self.viewer.set_skeleton(None if not shown else self._last_points,
                                 self.viewer._bones, self._last_confidence)
        self._overlay_shown = bool(shown)

    def _build_summary_inspector(self) -> QWidget:
        """What has been labelled so far, as cards rather than a flat list.

        LABEL-02. A line per movement told an annotator nothing they could act
        on; a card carries the class, the range, how long it is, how many
        faults it has and what it is still waiting for - and the faults fold
        out underneath the movement they belong to rather than living in a
        second list somewhere else.
        """
        tokens = self._tokens
        page = QWidget()
        column = QVBoxLayout(page)
        pad = tokens.metric("KcSpacingLg")
        column.setContentsMargins(pad, pad, pad, pad)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        # Which version is open. Identity, wanted while comparing two
        # versions, and not a heading - which is why it is a subtitle here
        # rather than a band across the top of the screen.
        self.version_title = ElidedLabel("")
        self.version_title.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.version_title)

        self.summary_context = label("Etiket özeti", role="section")
        self.summary_context.setProperty("kcContext", "summary")
        column.addWidget(self.summary_context)

        self.summary_counts = ElidedLabel("")
        self.summary_counts.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.summary_counts)

        # **The one place in this panel that scrolls.** The 21 September
        # decision makes this tab the single exception to the no-scrolling
        # rule, and the old behaviour shows why it was needed: a
        # ``QVBoxLayout`` given less height than its children ask for does not
        # hide the overflow, it *compresses* every child towards its minimum.
        # Twenty movements turned readable three-line cards into squeezed
        # ones and still lost the last of them off the bottom.
        #
        # Inside a scroll area the cards keep the height they ask for and the
        # last one is reachable. The bars are switched off in both directions:
        # the wheel, the trackpad and keyboard navigation all still work, and
        # the user asked for no visible bar or slider. Nothing else in the
        # panel is wrapped this way - Bakış and Sporcu still have to fit.
        self.summary_scroll = QScrollArea(page)
        self.summary_scroll.setProperty("kcSurface", "none")
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.summary_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.summary_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.summary_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.summary_holder = QWidget(self.summary_scroll)
        self._summary_layout = QVBoxLayout(self.summary_holder)
        self._summary_layout.setContentsMargins(0, 0, 0, 0)
        # A steady rhythm that does not depend on how many there are.
        self._summary_layout.setSpacing(tokens.metric("KcSpacingLg"))
        self._summary_layout.addStretch(1)
        self.summary_scroll.setWidget(self.summary_holder)
        column.addWidget(self.summary_scroll, 1)

        self.summary_hint = QLabel(
            "Zaman çizelgesinde boş bir yere sürükleyerek hareket ekleyin.\n\n"
            "M: hareket çiz · E: hata çiz · Boşluk: oynat\n"
            "1-9: seçili harekete sınıf ata · Tab: sonraki eksik"
        )
        self.summary_hint.setWordWrap(True)
        self.summary_hint.setProperty("kcRole", "pageSubtitle")
        column.addWidget(self.summary_hint)
        return page

    #: How many movement cards the summary draws. Above this the panel turns
    #: into a scroll nobody reads, and building four hundred widgets on every
    #: edit is a cost with nothing behind it; the rest are counted instead.
    SUMMARY_CARDS = 40

    def _show_summary(self) -> None:
        """Rebuild the cards. Bounded, and only when the labels changed."""
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        rows = viewmodel.movements.value
        errors = viewmodel.errors.value
        while self._summary_layout.count() > 1:
            item = self._summary_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # See ClassStrip._rebuild: unparenting a visible widget
                # turns it into a floating window until it is collected.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        ready = sum(1 for row in rows if row.readiness is Readiness.READY)
        faulty = sum(1 for row in rows if row.error_count)
        self.summary_counts.setText(
            f"{len(rows)} hareket · {ready} hazır · {faulty} hatalı"
            if rows
            else "Henüz hareket yok."
        )
        self.summary_hint.setVisible(not rows)

        fps = max(1.0, viewmodel.fps.value)
        by_sample: dict[str, list] = {}
        for error in errors:
            by_sample.setdefault(error.sample_id, []).append(error)
        for row in rows[: self.SUMMARY_CARDS]:
            card = MovementCard(self._tokens, row, fps, self.summary_holder)
            card.activated.connect(self._summary_card_chosen)
            for error in by_sample.get(row.sample_id, ()):
                button = QToolButton(card)
                button.setText(error.error_label or "sınıf seçin")
                button.setAutoRaise(True)
                button.setAccessibleName(error.error_label or "sınıfsız hata")
                button.setToolTip(f"{error.start}–{error.end}")
                button.clicked.connect(
                    lambda _checked=False, key=error.interval_id: (
                        self._summary_fault_chosen(key)
                    )
                )
                card.add_fault(button)
            self._summary_layout.insertWidget(
                self._summary_layout.count() - 1, card
            )
        if len(rows) > self.SUMMARY_CARDS:
            more = label(
                f"…ve {len(rows) - self.SUMMARY_CARDS} hareket daha",
                role="pageSubtitle",
            )
            self._summary_layout.insertWidget(
                self._summary_layout.count() - 1, more
            )

    def _summary_card_chosen(self, sample_id: str) -> None:
        if self.viewmodel is not None:
            self.viewmodel.select_movement(sample_id)
            self._seek(self.viewmodel.movement_row(sample_id).start)

    def _summary_fault_chosen(self, interval_id: str) -> None:
        if self.viewmodel is not None:
            self.viewmodel.select_error(interval_id)

    #: The panel's three states, in stack order, with the line each one shows
    #: on the strip's tooltip. LABEL-01 is explicit that the context must be
    #: readable as words, not only as the icon's colour.
    LABEL_CONTEXTS = {
        "summary": (0, "Etiket özeti"),
        "movement": (1, "Hareket düzenleyicisi"),
        "fault": (2, "Hata düzenleyicisi"),
    }

    def _label_icon_pressed(self) -> None:
        """Drop the selection and show what has been labelled so far."""
        viewmodel = self.viewmodel
        if viewmodel is not None:
            viewmodel.selected_error.set("")
            viewmodel.selected_movement.set("")
        self._show_summary()
        self._show_label_context("summary")

    def _show_label_context(self, context: str) -> None:
        """Open the editor for what is selected and say what it is.

        The band below carries the editing; the panel's own icon carries the
        context colour and the wording, because R-01 keeps the summary in the
        panel while the forms live underneath.
        """
        _index, caption = self.LABEL_CONTEXTS.get(
            context, self.LABEL_CONTEXTS["summary"]
        )
        # "summary" means nothing is selected, which since 21 September is the
        # *movement* editor with its interval controls off - not a blank band
        # with one sentence on it. Opening Etiketleme has to show what the
        # editor is, and the classes are usable before an interval exists.
        self.editor_bar.show_mode("" if context == "summary" else context)
        self.editor_bar.set_movement_enabled(context == "movement")
        if context == "summary":
            # The editor is on screen with nothing in it, which has to read as
            # "nothing is selected" rather than as a form that failed to fill.
            self.movement_title.setText("Hareket seçilmedi")
            # Short enough to be read whole in the slot it has. The longer
            # version was elided to "…ya da bo…", which is an instruction
            # nobody can follow; the full sentence is the timeline's own
            # empty-state line and the tooltip here.
            self.movement_state.setText("Zaman çizelgesinden bir hareket seçin.")
            self.movement_state.setToolTip(
                "Zaman çizelgesinden bir hareket seçin ya da boş bir yere "
                "sürükleyerek yeni bir hareket çizin."
            )
            self.editor_bar.movement_faults.setText("")
        self.side_tabs.set_context("labels", context)
        self._label_button.setToolTip(f"Etiket özeti · {caption}")
        self._label_button.setAccessibleDescription(caption)

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
        add("Ctrl+S", self._save_now)
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
        self.subject_panel.open_people.clicked.connect(self._open_subject_lists)
        self.subject_panel.open_questions.clicked.connect(self._open_subject_lists)
        self.bind(self.subject.candidates, self.subject_panel.show_candidates)
        self.bind(self.subject.questions, self.subject_panel.show_questions)
        self.bind(self.subject.progress, self._show_subject_status)
        self.bind(self.subject.settled, lambda _s: self._show_subject_status())
        self.bind(self.subject.blocker, lambda _b: self._show_subject_status())
        self.bind_event(self.subject.message, self.show_message)
        self.bind_event(self.subject.go_to, self._seek)
        # One redraw per change of labels, not one per list: the two lists
        # are always replaced together, and each redraw rebuilds the timeline
        # and the summary cards.
        self.bind_event(viewmodel.labels_changed, lambda _none: self._labels_changed())
        # ``bind`` drew the empty state on attach; an event does not, so it is
        # drawn here once.
        self._labels_changed()
        self.bind(viewmodel.selected_movement, lambda _key: self._selection_changed())
        self.bind(viewmodel.selected_error, lambda _key: self._selection_changed())
        self.bind(viewmodel.progress, self.progress_label.setText)
        self.bind(viewmodel.title, self._show_version_title)
        self.bind(viewmodel.dirty, self._changes_pending)
        self.bind(viewmodel.can_undo, self.undo_button.setEnabled)
        self.bind(viewmodel.can_redo, self.redo_button.setEnabled)
        self.bind(viewmodel.exercise_options, lambda _o: self._refill_classes())
        self.bind(viewmodel.error_options, lambda _o: self._refill_classes())
        self.bind(viewmodel.playing, self._playing_changed)
        self.bind(viewmodel.frames, self._frames_changed)
        self.bind(viewmodel.busy, self._loading_changed)
        self.bind(viewmodel.loading, self._show_loading)
        self.bind_event(viewmodel.message, self.show_message)
        self.bind_event(viewmodel.frame_changed, self._render_frame)
        # The whole screen is prepared from the *opened* event, never from a
        # timer after the request: the load runs on a worker thread and
        # anything scheduled alongside it arrives before the data does.
        self.bind_event(viewmodel.opened, lambda _directory: self._after_open())
        self.bind_event(viewmodel.open_failed, self._open_failed)

    # ------------------------------------------------------------- lifecycle
    def page_activated(self) -> None:
        """Open whichever version the library sent us here for."""
        shell = self.window()
        pending = getattr(shell, "pending_review", None)
        if self.viewmodel is None:
            self._show_nothing()
            return
        if pending is None:
            if self.viewmodel.review is None and not self.viewmodel.busy.value:
                self._show_nothing()
            return
        setattr(shell, "pending_review", None)
        self._pending_focus = getattr(shell, "pending_review_focus", "") or ""
        setattr(shell, "pending_review_focus", "")
        directory = getattr(pending, "directory", None) or str(pending)
        if self.viewmodel.review is not None and self.viewmodel.directory == directory:
            # Already showing exactly this version. Re-opening it would throw
            # away the playhead and the selection for no gain - but the reader
            # was still sent here to fix something, so that part is honoured.
            self._apply_focus()
            return
        self.viewmodel.open_version(directory)

    def page_deactivated(self) -> None:
        self._clock.stop()
        if self.viewmodel is not None:
            self.viewmodel.playing.set(False)
            self.viewmodel.flush()
        if getattr(self, "subject", None) is not None:
            self.subject.flush()

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self._clock.stop()
        self._autosave.stop()
        if getattr(self, "subject", None) is not None:
            self.subject.close()
        if self.viewmodel is not None:
            self.viewmodel.close()
        super().closeEvent(event)

    def _after_open(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or viewmodel.review is None:
            return
        review = viewmodel.review
        self._roles = resolve_roles(review.skeleton) if review.skeleton else {}
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
        self._apply_focus()

        # The picture's real shape, from the version's own metadata. Nothing
        # here assumes 16:9; a source that declared nothing returns 0.0 and the
        # solver's documented fallback is used, which is the one place that
        # number appears.
        self.set_source_ratio(source_ratio_from(review.source_size))

        camera_system = (review.job.get("processing_camera") or {}).get(
            "coordinate_system", ""
        )
        # The spec, not only the bones: it is what makes the colours
        # anatomical rather than a guess from index positions.
        self.skeleton.set_skeleton_spec(
            review.bones, up_axis_for(camera_system), review.skeleton
        )
        # The same anatomy on the picture, so a coach comparing the two views
        # is comparing limbs rather than reconciling two colour schemes.
        self.viewer.set_skeleton_spec(review.skeleton)
        window = review.joints_3d_window(0, min(review.frames, 300))
        remembered = self._camera
        # The measured floor, if this version has one. Passed *before* the
        # references are established so the pivot is solved against the real
        # plane rather than against the lowest foot - and so the grid is not
        # drawn twice in two different places.
        floor = review.floor
        if floor.is_measured:
            # The plane's height under the athlete, which is what a grid
            # needs. A plane with no component along the up axis - a wall -
            # gives None, and the viewer falls back to its visual reference
            # rather than drawing a floor standing on its edge.
            centre = body_target(window, ()) or (0.0, 0.0, 0.0)
            up_axis = up_axis_for(camera_system)
            others = [i for i in (0, 1, 2) if i != up_axis]
            height = floor.height_at(centre[others[0]], centre[others[1]], up_axis)
            self.skeleton.set_floor_height(height)
        else:
            self.skeleton.set_floor_height(None)
        # The axis the viewer walks around and the point the camera looks at,
        # established once over a window of frames. Recomputed per frame they
        # would follow the ankles' own noise and the scene would wobble.
        self.skeleton.set_references(
            window,
            left_ankle=self._roles.get("left_ankle"),
            right_ankle=self._roles.get("right_ankle"),
            hips=(self._roles.get("left_hip"), self._roles.get("right_hip")),
        )
        # Read *before* set_references, which emits camera_changed and would
        # otherwise fill this in with a camera that had never been framed.
        if remembered is not None:
            self.skeleton.set_camera(remembered)
        elif not self.skeleton.frame_on(window):
            self.skeleton.set_note("Bu sürümde 3B eklem verisi yok.")
        # The recording's own front, fixed once, **from the body**. What was
        # here before handed the camera its own azimuth back - 35 degrees by
        # default, or whatever angle the last session had been dragged to -
        # so every preset was an offset from an arbitrary direction and a
        # remembered camera could redefine a different recording's front.
        self._set_anatomical_front(window, camera_system)
        self.overlay_available = self.skeleton.is_available

        self.subject_panel.set_context(
            review.frame, self.subject.candidate_title, viewmodel.fps.value
        )
        self.subject.open(review, annotator=viewmodel.store.annotator if viewmodel.store else "")
        self._set_editing_enabled(review.frames > 0)
        # The first frame, drawn into both views from one position, before the
        # editor is shown. Video and skeleton therefore appear on the *same*
        # frame rather than one of them catching up afterwards.
        self._render_frame(viewmodel.position.value)
        # Everything the annotator needs is now built. Only here does the
        # screen stop being busy.
        viewmodel.ready()

    #: How each reference source is described where the annotator can read it.
    #: "Ölçüldü" and "varsayıldı" are different claims about the same arrow.
    FRONT_SOURCE_TEXT = {
        FACING_SHOULDERS: "Ön yön omuz çizgisinden ölçüldü.",
        FACING_HIPS: "Ön yön kalça çizgisinden ölçüldü (omuzlar okunamadı).",
        FACING_MANUAL: "Ön yönü siz tanımladınız.",
        FACING_UNKNOWN: (
            "Ön yön belirlenemedi; presetler kayıt kamerasına göre hesaplanıyor. "
            "Doğru yöne çevirip 'Bunu ön yap' diyebilirsiniz."
        ),
    }

    def _set_anatomical_front(self, window, camera_system: str) -> None:
        """Establish which way the athlete faces, and say where it came from.

        Once per version, over a window of frames rather than per frame: a
        front re-derived each frame follows the tracker's noise, and "ön"
        would mean something slightly different every time it was pressed.

        When the body cannot answer - no shoulders, no hips, everything NaN -
        nothing is invented. The reference stays where the recording's camera
        looked from, the source is reported as unknown, and the panel says so
        instead of showing a confident arrow that is wrong.
        """
        azimuth, source = facing_azimuth(
            window,
            up_axis=up_axis_for(camera_system),
            left_shoulder=self._roles.get("left_shoulder"),
            right_shoulder=self._roles.get("right_shoulder"),
            left_hip=self._roles.get("left_hip"),
            right_hip=self._roles.get("right_hip"),
            left_handed=is_left_handed(camera_system),
        )
        if azimuth is None:
            # The recording's own camera looked at the athlete from where it
            # stood, which is a real direction even when the body is unreadable
            # - just not an anatomical one, and it is labelled as such.
            azimuth = recording_azimuth(camera_system)
            if azimuth is None:
                azimuth = self.skeleton.camera.azimuth
        self._front_source = source
        self.skeleton.set_reference_azimuth(azimuth)
        # The recorded viewpoint is a separate fact, resolved from the
        # recording's own coordinate convention rather than from the athlete.
        recorded = recording_azimuth(camera_system)
        self.skeleton.set_recording_azimuth(recorded)
        self.camera_panel.set_recording_known(recorded is not None)
        self.camera_panel.show_front_source(
            source, self.FRONT_SOURCE_TEXT[source]
        )
        self._show_compass()

    # -------------------------------------------------------- loading states
    def _loading_changed(self, busy: bool) -> None:
        """While a version is loading the screen shows the preparation page.

        Nothing that edits a label exists on that page, so there is no state
        in which a drawing tool is live over data that has not arrived.
        """
        if busy:
            self._set_editing_enabled(False)
            self.timeline.set_intervals(())
            self.editor_bar.show_mode("")
            self.loading.prepare()
            self.surface.setCurrentWidget(self.loading)
            return
        # Not busy is not the same as ready. An open that was cancelled, or
        # one that failed, also stops being busy, and showing the editor for
        # either of them would be an empty editor with live tools on it.
        viewmodel = self.viewmodel
        if viewmodel is not None and viewmodel.review is not None:
            self.surface.setCurrentWidget(self.editor)
            # The band's widths depend on the page's real height, which is
            # only known once the editor is the widget being laid out.
            self._apply_stage_geometry()
            # And the picture is drawn into a surface that is now on screen.
            self._render_frame(viewmodel.position.value)
        else:
            self._show_nothing()

    def _show_loading(self, progress) -> None:  # noqa: ANN001 - LoadProgress
        if not progress.done:
            self.loading.show_progress(progress)

    def _open_failed(self, _directory: str) -> None:
        """A failed open is a state with a way out, not an empty screen."""
        self._set_editing_enabled(False)
        reason = self.viewmodel.open_error.value if self.viewmodel else ""
        self.loading.show_failure(reason)
        self.surface.setCurrentWidget(self.loading)

    def _cancel_open(self) -> None:
        """Stop the open and fall back to the empty state, cleanly."""
        if self.viewmodel is not None:
            self.viewmodel.cancel_open()
        self._show_nothing()

    def _retry_open(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        if viewmodel.retry_open():
            return
        # Nothing to retry: the way out is the screen that chooses a version.
        shell = self.window()
        navigate = getattr(getattr(shell, "viewmodel", None), "navigate", None)
        if callable(navigate):
            navigate("library")

    def _set_editing_enabled(self, enabled: bool) -> None:
        """Nothing that edits a label is reachable before the data is here.

        Drawing on a timeline that has no frame range produced a 0-0 movement
        in the 15 September audit: the tool was live while the view still
        thought the take was empty.
        """
        self._editing_enabled = enabled
        for tool, button in self._tool_buttons.items():
            button.setEnabled(enabled or tool is Tool.SCRUB)
        if not enabled:
            self._set_tool(Tool.SCRUB, sync=True)
        for widget in (
            self.snap_button,
            self.next_gap_button,
            self.delete_movement_button,
            self.apply_all_button,
            self.editor_bar.exercise_classes,
            # Laid out on the interval line, so no longer a child of the strip
            # and no longer switched off with it.
            self.editor_bar.exercise_classes.browse_button,
            self.movement_start,
            self.movement_end,
            self.exclude_box,
            self.play_button,
            self.first_button,
            self.back_button,
            self.forward_button,
            self.last_button,
        ):
            widget.setEnabled(enabled)
        # Having a version open is necessary, not sufficient. The band shows
        # the movement editor from the moment the screen opens, and with
        # nothing selected its interval controls must stay off - otherwise a
        # press on the delete button is a control that looks live and
        # silently does nothing, which is what the 21 September review calls
        # meaningless.
        self.editor_bar.set_movement_enabled(
            enabled and bool(self.viewmodel and self.viewmodel.selected_movement.value)
        )

    def set_inspector_visible(self, visible: bool) -> None:
        """Shown, always. See :attr:`inspector_is_permanent`.

        The argument is kept because the shell's contract passes one; it is
        deliberately ignored rather than honoured, so that no caller - a
        remembered preference, another screen's toggle, a future shortcut -
        can take this panel away without changing this line.
        """
        del visible
        self.side_tabs.setVisible(True)

    def _show_nothing(self) -> None:
        """No version chosen: one readable empty state with a way forward.

        Shown in place of the editor rather than as three separate "nothing
        here" notes scattered across a video pane, a 3-D pane and a timeline.
        """
        self.skeleton.set_joints(None)
        self.timeline.set_take(0, 30.0)
        self.timeline.set_intervals(())
        self._set_editing_enabled(False)
        self.editor_bar.show_mode("")
        self.loading.show_empty(
            "İşlenen Videolar ekranından bir sürüm seçip 'Etiketle' deyin.",
            action="İşlenen Videolar'a git",
        )
        self.surface.setCurrentWidget(self.loading)

    def _show_version_title(self, text: str) -> None:
        """The run id and frame count, in the panel rather than as a heading.

        LAYOUT-01 removed the page title and the line under it. The identity
        still has to be reachable - an annotator comparing two versions needs
        to know which one is open - so it lives with the version's other
        details, where it is read when it is wanted.
        """
        self.version_title.setText(text)
        self.version_title.setToolTip(text)

    def _speed_chosen(self, _index: int) -> None:
        """Playback speed. Shows frames faster; changes no measurement."""
        self._speed = float(self.speed_box.currentData() or 1.0)
        if self.viewmodel is not None and self.viewmodel.playing.value:
            # Re-arm the clock at the new rate rather than waiting for the
            # next tick, which at 0.25x is a second away.
            self._playing_changed(True)

    def _loop_toggled(self, enabled: bool) -> None:
        self._loop_selection = bool(enabled)

    def _looped_bounds(self):  # noqa: ANN201 - Optional[tuple[int, int]]
        """The interval playback should wrap inside, or ``None``."""
        viewmodel = self.viewmodel
        if not self._loop_selection or viewmodel is None:
            return None
        interval = viewmodel.selected_error.value or viewmodel.selected_movement.value
        if not interval:
            return None
        for row in viewmodel.movements.value:
            if row.sample_id == interval:
                return row.start, row.end
        for row in viewmodel.errors.value:
            if row.interval_id == interval:
                return row.start, row.end
        return None

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
        self.play_button.setIcon(
            iconset.icon(
                "pause" if playing else "play",
                self._tokens,
                colour_token="KcTextOnAccent",
                size=self._tokens.metric("KcIconSize"),
            )
        )
        self.play_button.setAccessibleName("Duraklat" if playing else "Oynat")
        if playing and self.viewmodel is not None:
            # The recording's own rate, divided by the chosen speed. The frame
            # *indices* are untouched: a slower playback shows the same frames
            # further apart, it does not resample anything.
            fps = max(1.0, self.viewmodel.fps.value) * max(0.01, self._speed)
            self._clock.start(max(1, int(round(1000.0 / fps))))
        else:
            self._clock.stop()

    def _tick(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        bounds = self._looped_bounds()
        if bounds is not None:
            start, end = bounds
            position = viewmodel.position.value
            if position >= end or position < start:
                # Wrap rather than run past the interval being reviewed. The
                # playhead is the only thing that moves; nothing is edited.
                viewmodel.seek(start)
                return
        viewmodel.advance()

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
        """The 3D view is driven by the same frame index as everything else.

        The guard here used to be ``isVisible()``, which is False for anything
        sitting behind a stacked page - including the editor itself while the
        version is being prepared. So the first frame's joints were computed,
        dropped, and never asked for again: the editor appeared with a floor
        grid and no skeleton on it. What matters is whether the annotator has
        *turned the view off*, which is a state of its own.
        """
        if not self._skeleton_shown:
            return
        joints = review.joints_3d(position)
        self.skeleton.set_joints(joints)
        missing = joints is None or not bool(np.isfinite(joints).any())
        self.skeleton.set_note("Bu karede izlenen kisi yok." if missing else "")

    def _toggle_skeleton(self, shown: bool) -> None:
        self._skeleton_shown = bool(shown)
        self.skeleton.setVisible(shown)
        if shown and self.viewmodel is not None and self.viewmodel.review is not None:
            self._show_pose(self.viewmodel.review, self.viewmodel.position.value)

    def _remember_camera(self) -> None:
        """Keep the angle across version switches; it is the user's viewpoint."""
        self._camera = self.skeleton.camera

    def _answer_subject(self, interval_id: str, verdict, tracker_id) -> None:  # noqa: ANN001
        """The panel never guesses the tracker; it is passed or it is None."""
        self.subject.answer(interval_id, verdict, tracker_id=tracker_id)

    def _apply_focus(self) -> None:
        """Land on the thing the Veri Seti screen sent us here to fix.

        Each case selects a real record and opens the editor for it. A focus
        with nothing to select falls back to the label view rather than
        pointing at whatever happened to be selected already, which would be a
        quiet way of showing the wrong repetition.
        """
        focus, self._pending_focus = self._pending_focus, ""
        viewmodel = self.viewmodel
        if not focus or viewmodel is None:
            return
        if focus == "subject":
            self.side_tabs.show_view("subject")
            return
        if focus == "open_error":
            for row in viewmodel.errors.value:
                if not row.error_class:
                    viewmodel.select_error(row.interval_id)
                    self._seek(row.start)
                    return
        if focus == "no_exercise":
            for row in viewmodel.movements.value:
                if not row.exercise:
                    viewmodel.select_movement(row.sample_id)
                    self._seek(row.start)
                    return
        self.side_tabs.show_view("labels")

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
        # The athlete question gates the export, so it has to be visible from
        # anywhere in the panel - including while the camera view is open.
        self.side_tabs.set_attention(
            "subject", "" if settled else "yanıtlanmamış soru var"
        )

    def _changes_pending(self, dirty: bool) -> None:
        """Restart the autosave countdown, and say plainly what is unsaved."""
        if dirty:
            self._autosave.start()
            self.save_state.setText("kaydedilmedi")
            self.save_state.setProperty("kcStatus", "warning")
        else:
            self._autosave.stop()
            self.save_state.setText("kaydedildi")
            self.save_state.setProperty("kcStatus", "ready")
        self.save_state.style().unpolish(self.save_state)
        self.save_state.style().polish(self.save_state)

    def _save_now(self) -> None:
        """Autosave. A failed write keeps the labels and tries again."""
        if self.viewmodel is None:
            return
        if not self.viewmodel.flush():
            self._autosave.start()
        if getattr(self, "subject", None) is not None:
            self.subject.flush()

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

    def _edit_cancelled(self) -> None:
        """Esc, a lost focus, or a drag too short to be one.

        TOOL-02 again: a cancelled draw goes back to Gez as well. Otherwise
        pressing Esc leaves the tool armed with nothing on screen saying so,
        and the next ordinary click draws.
        """
        self._edit_finished()
        self._set_tool(Tool.SCRUB, sync=True)

    # -------------------------------------------------------------- timeline
    def _set_tool(self, tool: Tool, *, sync: bool = False) -> None:
        self.timeline.set_tool(tool)
        if sync:
            self._tool_buttons[tool].setChecked(True)

    def _timeline_scrubbed(self, position: int) -> None:
        self._seek(position)

    def _interval_drawn(self, lane: str, start: int, end: int) -> None:
        """One interval drawn, then straight back to navigating.

        TOOL-02. A drawing tool that stays armed turns the next ordinary click
        on the timeline into a second interval nobody asked for, and the two
        are indistinguishable afterwards. So one drag draws one range and the
        tool hands itself back: the new range stays selected, its editor is
        open, and the next click scrubs.
        """
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        created = (
            viewmodel.add_movement(start, end)
            if lane == "movements"
            else viewmodel.add_error(start, end)
        )
        self._edit_finished()
        # Back to Gez whether or not the range was accepted. A refused draw
        # must not leave a hidden armed tool behind either.
        self._set_tool(Tool.SCRUB, sync=True)
        if created:
            self.timeline.set_selected(str(created))
            self._selection_changed()

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
            # LABEL-01. Clicking a movement box means "show me this movement",
            # and it has to work on the first click. The viewmodel only drops
            # the selected fault when it belongs to a *different* movement, so
            # a fault of this same movement would otherwise keep the fault
            # editor on screen and the click would look like it did nothing.
            # Suppressed, because the intermediate state - no fault, old
            # movement - is not a state worth redrawing the panel for.
            self._suppress = True
            try:
                viewmodel.selected_error.set("")
            finally:
                self._suppress = False
            viewmodel.select_movement(key)
            # When this movement was already the selected one - it owned the
            # fault that was open - nothing above changed value, so nothing
            # announced the new state. The editor is told directly. (It used
            # to happen as a side effect of every selection rebuilding every
            # row, which is what made each click cost 176 ms at 100
            # repetitions.)
            self._selection_changed()
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
    def _labels_changed(self) -> None:
        # No list to refill. The movements are boxes on the timeline and cards
        # in the summary; a third copy above every editor was the thing that
        # spent a third of the panel's height on one row.
        self._push_intervals()
        self._show_summary()
        self._selection_changed()

    def _push_intervals(self) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        intervals = [
            Interval(
                key=row.sample_id, start=row.start, end=row.end, lane="movements",
                text=row.exercise_label or "sınıf yok", status=row.status,
                colour_index=row.colour_index, code=row.code,
            )
            for row in viewmodel.movements.value
        ]
        intervals += [
            Interval(
                key=row.interval_id, start=row.start, end=row.end, lane="errors",
                text=row.error_label or "sınıf seçin", status=row.status,
                parent=row.sample_id, colour_index=row.colour_index, code=row.code,
            )
            for row in viewmodel.errors.value
        ]
        self.timeline.set_intervals(intervals)

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
            if error_key and viewmodel.error_row(error_key) is not None:
                self._show_error(error_key)
                self._show_label_context("fault")
            elif movement_key and viewmodel.movement_row(movement_key) is not None:
                self._show_movement(movement_key)
                self._show_label_context("movement")
            else:
                self._show_summary()
                self._show_label_context("summary")
                self.viewer.set_highlight(())
                self.skeleton.set_highlight(())
        finally:
            self._suppress = False

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
        self.editor_bar.exercise_classes.set_selected(row.exercise)
        self.movement_start.setValue(row.start)
        self.movement_end.setValue(row.end)
        self.exclude_box.setChecked(row.excluded)
        self.apply_all_button.setEnabled(bool(row.exercise))

        # A count and a way in, not a second list. The faults themselves are
        # boxes on the timeline directly under this movement, one click away,
        # and the summary panel lists them under the movement they belong to.
        faults = [e for e in viewmodel.errors.value if e.sample_id == sample_id]
        unclassified = sum(1 for e in faults if not e.error_class)
        self.editor_bar.movement_faults.setText(
            "Bu harekette hata yok"
            if not faults
            else f"{len(faults)} hata"
            + (f" · {unclassified} sınıfsız" if unclassified else "")
        )
        self.viewer.set_highlight(())
        self.skeleton.set_highlight(())

    def _show_error(self, interval_id: str) -> None:
        viewmodel = self.viewmodel
        row = viewmodel.error_row(interval_id) if viewmodel else None
        if row is None:
            return
        self.error_title.setText(f"Hata aralığı · {row.end - row.start + 1} kare")
        self.editor_bar.error_classes.set_selected(row.error_class)
        self.error_start.setValue(row.start)
        self.error_end.setValue(row.end)
        self._show_joint_summary(row)
        parent = viewmodel.movement_row(row.sample_id)
        self.editor_bar.error_parent.setText(
            f"{parent.exercise_label or 'sınıfsız hareket'} içinde"
            if parent is not None
            else ""
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
            # The first nine movement classes say which key assigns them. The
            # shortcut exists either way; printing it is what makes it usable
            # without reading the help text.
            self.editor_bar.exercise_classes.set_options(
                tuple(
                    (code, f"{text}  [{slot}]" if slot <= QUICK_SLOTS else text)
                    for slot, (code, text) in enumerate(
                        viewmodel.exercise_options.value, start=1
                    )
                )
            )
            self.editor_bar.error_classes.set_options(viewmodel.error_options.value)
        finally:
            self._suppress = False
        # The strips just changed shape, so the band's minimum did too.
        self._apply_stage_geometry()

    #: How each origin is described. The distinction is the point: joints
    #: inherited from a class and joints somebody looked at for *this*
    #: repetition are different evidence, and the record keeps them apart.
    ROLES_ORIGIN_TEXT = {
        RolesOrigin.REVIEWED: "bu aralık için seçildi",
        RolesOrigin.CLASS_DEFAULT: "sınıfın varsayılanı",
        RolesOrigin.UNKNOWN: "",
    }

    def _show_joint_summary(self, row) -> None:  # noqa: ANN001 - ErrorRow
        """The joints, in readable words, and where they came from.

        A checkbox list of technical role names used to sit in the panel.
        Reading it was navigation, not judgement - the question "which joint"
        is answered by pointing at a body, which is what the 3-D view is for.
        The names stay available for correction, in their own window.
        """
        names = [role.replace("_", " ") for role in sorted(row.roles)]
        if not names:
            self.editor_bar.joint_summary.setText("Eklem seçilmedi")
        elif len(names) <= 3:
            self.editor_bar.joint_summary.setText(", ".join(names))
        else:
            self.editor_bar.joint_summary.setText(
                f"{', '.join(names[:3])} +{len(names) - 3}"
            )
        self.editor_bar.joint_summary.setToolTip(", ".join(names))
        origin = self.ROLES_ORIGIN_TEXT.get(row.roles_origin, "")
        self.editor_bar.joint_origin.setText(
            f"{len(names)} eklem · {origin}" if names and origin else origin
        )


    # --------------------------------------------------------------- editing
    def _exercise_chosen(self, code: str) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        sample_id = viewmodel.selected_movement.value
        if sample_id and code:
            # The note is not re-sent with every class change: `None` means
            # "leave it alone", and a note is edited in its own window.
            viewmodel.label_movement(sample_id, code, note=None)

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
            code = self.editor_bar.exercise_classes.selected
            if code:
                self.viewmodel.apply_exercise_to_unlabelled(code)

    def _create_exercise(self, name: str) -> None:
        """A movement class is a name and nothing else, so it is one step."""
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        code = viewmodel.create_exercise(name)
        if not code:
            return
        self.editor_bar.exercise_classes.clear_new_name()
        self.editor_bar.exercise_classes.set_selected(code)
        self.editor_bar.exercise_classes.note_used(code)
        self._exercise_chosen(code)

    # ----------------------------------------------------- new fault classes
    def _fault_draft_typed(self, text: str) -> None:
        """Typing a fault-class name opens the 3-D view for picking joints.

        JOINT-02. Picking is on *only* while a class is being defined: with it
        on permanently, a double-click meant for the camera would silently
        edit anatomy. Clearing the name closes the draft and puts the view
        back the way it was.

        Playback stops when the draft opens. Picking a joint on a body that
        is moving means picking whatever happened to be under the pointer at
        that instant, and the pause is the safe direction - the playhead does
        not move, nothing is written, and pressing play again resumes.
        """
        wanted = bool(text.strip())
        if wanted == self._fault_draft:
            return
        self._fault_draft = wanted
        self.skeleton.set_picking(wanted)
        if not wanted:
            self._draft_joints = []
            self.skeleton.set_highlight(self._selected_role_joints())
            self.editor_bar.error_classes.set_add_enabled(True)
            self.editor_bar.error_classes.set_hint("")
            return
        if self.viewmodel is not None:
            self.viewmodel.playing.set(False)
        self._draft_joints = []
        self.skeleton.set_highlight(())
        # Ekle is refused until a joint is picked: JOINT-01 rules out a class
        # stored without the joints it is about.
        self.editor_bar.error_classes.set_add_enabled(False)
        self._show_draft_state()

    def _show_draft_state(self) -> None:
        """One message, in both places a reader might be looking.

        Over the scene, because that is where the double-clicking happens,
        and under the name box, because that is where Ekle is waiting.
        """
        if not self._fault_draft:
            self.skeleton.set_picking_note("")
            return
        count = len(self._draft_joints)
        if not count:
            message = "Eklem seçin: 3B görünümde ilgili eklemlere çift tıklayın."
            self.skeleton.set_picking_note(message)
            self.editor_bar.error_classes.set_hint(message, warning=True)
            return
        names = ", ".join(sorted(self._role_names(self._draft_joints))).replace(
            "_", " "
        )
        self.skeleton.set_picking_note(
            f"Eklem seçimi açık · {count} seçildi · çıkarmak için tekrar çift tıklayın"
        )
        self.editor_bar.error_classes.set_hint(f"{count} eklem · {names}")

    def _joint_picked(self, index: int) -> None:
        """A joint was double-clicked in the 3-D view while drafting."""
        if not self._fault_draft:
            return
        if index in self._draft_joints:
            self._draft_joints.remove(index)
        elif not self._role_names([index]):
            # Refused, and said out loud. A class is stored as role names, so
            # a joint with no role cannot be part of one; adding it to the
            # selection would show a count the record could not keep.
            name = self._joint_name(index)
            self.skeleton.set_picking_note(
                f"'{name}' bu gövde biçiminde adlandırılmış bir eklem değil; "
                "hata sınıfına eklenemez."
            )
            self.editor_bar.error_classes.set_hint(
                f"'{name}' seçilemez: anatomik karşılığı yok.", warning=True
            )
            return
        else:
            self._draft_joints.append(index)
        self.skeleton.set_highlight(self._draft_joints)
        self.viewer.set_highlight(self._draft_joints)
        self.editor_bar.error_classes.set_add_enabled(bool(self._draft_joints))
        self._show_draft_state()

    def _joint_name(self, index: int) -> str:
        """What this recording's own format calls that joint."""
        review = self.viewmodel.review if self.viewmodel else None
        spec = review.skeleton if review is not None else None
        if spec is None or not (0 <= index < spec.num_joints):
            return f"eklem {index}"
        return spec.joint_names[index].replace("_", " ")

    def _role_names(self, joints: Sequence[int]) -> list[str]:
        """The anatomical names of picked joints. Unnamed joints are dropped.

        A joint this skeleton has no role for cannot be written into a class:
        the class would then be about an index, and an index means a different
        body part on the next skeleton.
        """
        wanted = set(int(j) for j in joints)
        return [
            role
            for role, index in self._roles.items()
            if index is not None and int(index) in wanted
        ]

    def _selected_role_joints(self) -> tuple[int, ...]:
        """The joints the selected fault already names, for the highlight."""
        viewmodel = self.viewmodel
        interval_id = viewmodel.selected_error.value if viewmodel else ""
        row = viewmodel.error_row(interval_id) if interval_id else None
        if row is None:
            return ()
        return tuple(
            int(self._roles[role])
            for role in row.roles
            if self._roles.get(role) is not None
        )

    def _create_fault_class(self, name: str) -> None:
        """Store the drafted class and put it on the interval that prompted it.

        JOINT-03. The panel stays open and the interval stays selected: the
        class was created *because* of this interval, and closing over it
        would lose the place that prompted the question.
        """
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        roles = self._role_names(self._draft_joints)
        if not roles:
            self.editor_bar.error_classes.set_hint(
                "Seçilen eklemlerin anatomik karşılığı yok.", warning=True
            )
            return
        code = viewmodel.create_error_class_with_roles(name, roles)
        if not code:
            return
        self.editor_bar.error_classes.clear_new_name()  # closes the draft via textChanged
        self.editor_bar.error_classes.set_selected(code)
        self.editor_bar.error_classes.note_used(code)
        interval_id = viewmodel.selected_error.value
        if interval_id:
            # `apply_error_class` is JOINT-04's fast path and records the
            # joints as the class's *default*. Here they are not: somebody
            # just pointed at them on this repetition, so the origin is
            # `reviewed`. Using the fast path would have filed first-hand
            # evidence as inherited, which is the one distinction the record
            # exists to keep.
            viewmodel.label_error(
                interval_id,
                error_class=code,
                roles=tuple(roles),
                joint_status=JointStatus.SELECTED,
            )
            self._show_error(interval_id)
        self.show_message(
            Message(
                headline=f"'{name}' sınıfı {len(roles)} eklemle kaydedildi.",
                severity=Severity.INFO,
                detail="Bu sınıfı bundan sonra tek tıkla uygulayabilirsiniz.",
            )
        )

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

    def _error_class_chosen(self, code: str) -> None:
        """Pressing a known class applies it *and* the joints it declares.

        JOINT-04. The alternative - apply the class, then ask for the joints
        again - is the same anatomical question thirty times over. What is
        written records that the joints were inherited rather than judged for
        this repetition, so the two never become indistinguishable.
        """
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        interval_id = viewmodel.selected_error.value
        if not interval_id or not code:
            return
        viewmodel.apply_error_class(interval_id, code)

    def _commit_error(self, _index: int = 0, *, note: Optional[str] = None) -> None:
        viewmodel = self.viewmodel
        if viewmodel is None or self._suppress:
            return
        interval_id = viewmodel.selected_error.value
        code = self.editor_bar.error_classes.selected
        if not interval_id or not code:
            return
        row = viewmodel.error_row(interval_id)
        roles = tuple(row.roles) if row is not None else ()
        status = row.joint_status if row is not None else JointStatus.UNSPECIFIED
        if roles and status is not JointStatus.SELECTED:
            status = JointStatus.SELECTED
        viewmodel.label_error(
            interval_id,
            error_class=code,
            roles=roles,
            joint_status=status,
            note=note,
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
        # Icons are rendered with a colour baked in, so they are re-rendered
        # rather than left tinted for the theme we just left.
        size = tokens.metric("KcIconSize")
        for key, icon_key in (
            ("first", "first"),
            ("back", "step-back"),
            ("forward", "step-forward"),
            ("last", "last"),
        ):
            self._transport[key].setIcon(iconset.icon(icon_key, tokens, size=size))
        self._playing_changed(
            self.viewmodel.playing.value if self.viewmodel is not None else False
        )


__all__ = ["ReviewPage", "QUICK_SLOTS"]
