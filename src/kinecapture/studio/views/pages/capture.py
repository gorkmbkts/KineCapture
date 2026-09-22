"""The Capture screen: one scene, one console beside it, one transport below.

The shape is an operator's desk, not a form. The camera image is the work, so
it takes the whole left side and every pixel left over. Everything that
*configures* the shot stands in a column beside it, at a readable width, and
everything that *starts and stops* the shot is one bar along the bottom where
a hand can find it without reading.

Three things this layout exists to get right:

* **The console stays one column.** A short logical desktop must not turn the
  settings card into two columns and take the camera's width. On the supported
  full-screen layout the column fits; at unusually large display scaling only
  the console may scroll vertically.
* **The person in the frame is chosen by clicking on them.** There is no
  dropdown for it and there never should be: the operator is looking at the
  image, and the thing they want is under the pointer.
* **Who owns the data is shown, never asked for here.** The participant is a
  property of the project and is chosen on Projeler. This screen states it
  plainly so a recording can never go somewhere the operator did not expect,
  which is what the 15 September audit caught it doing.

Recording is said in three places at once - the button, a red border on the
image, and the shell's recording strip - because an operator looking at the
participant rather than the screen needs more than one chance to notice.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.capture_layout import (
    DEFAULT_SOURCE_RATIO,
    solve_capture_stage,
)
from kinecapture.studio.services.framing import subject_box
from kinecapture.studio.services.capture import CaptureMetrics
from kinecapture.studio.services.session import WorkTarget
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.capture import (
    COUNTDOWN_CHOICES,
    DURATION_CHOICES,
    RECORDING_MODES,
    Alert,
    CaptureViewModel,
)
from kinecapture.studio.viewmodels.navigation import Destination

from .. import iconset
from ..labelwindows import DetailWindow
from ..preview import PreviewView
from ..widgets import ElidedLabel, _restyle, label, mono_label, separator
from .base import StudioPage

#: Metrics refresh rate. Two to four times a second, never per frame: a number
#: that changes faster than it can be read costs paint time and gives nothing.
_METRICS_INTERVAL_MS = 300
#: Preview repaint rate, matched to the capture profile's preview target.
_PREVIEW_INTERVAL_MS = 66


class _ModeState(QLabel):
    """Reserve every mode wording using the current font and pill padding."""

    def __init__(self, tokens: ThemeTokens) -> None:
        super().__init__("—")
        self._tokens = tokens
        self.setIndent(0)  # Padding comes entirely from the status-pill style.
        self.setProperty("kcRole", "contextValue")
        self.setProperty("kcStatus", "neutral")

    def sizeHint(self):  # noqa: N802 - Qt naming
        size = super().sizeHint()
        metrics = self.fontMetrics()
        text_width = max(
            metrics.horizontalAdvance(text)
            for text in ("kamera bağlı değil", "seçildi · etkin değil", "etkin")
        )
        padding = 2 * (
            self._tokens.metric("KcSpacingLg") + self._tokens.metric("KcBorderWidth")
        )
        size.setWidth(max(size.width(), text_width + padding))
        return size

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        return self.sizeHint()



class _Metric(QWidget):
    """One labelled number, on one line with everything else in the row.

    Caption and value sit side by side rather than stacked. Stacked, the five
    readouts formed a second row of their own under the transport, and the
    height that cost came out of the camera image - which is the only thing on
    this screen anybody is actually looking at.

    The value is in the mono face and has a floor under its width, so a 9 that
    becomes a 10 does not shove the next readout sideways while it is being
    read.
    """

    def __init__(
        self,
        caption: str,
        tokens: ThemeTokens,
        parent=None,  # noqa: ANN001
        *,
        digits: int = 5,
        sample: str = "",
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.metric("KcSpacingSm"))
        self._caption = label(caption, role="contextKey")
        self._value = mono_label("—")
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._digits = int(digits)
        #: The widest reading this metric will ever show, *including its
        #: unit*. Counting digits alone left the disk readout reserving room
        #: for "123456" and then drawing "  137 dk", which is wider - so the
        #: widget grew and pushed "İşaret koy" fourteen pixels along the
        #: transport row while somebody was reaching for it.
        self._sample = sample or "0" * self._digits
        self._reserved_height = 0
        self._reserve_width()
        self._reserve_height()
        layout.addWidget(self._caption, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._value, 0, Qt.AlignmentFlag.AlignVCenter)
        self.setAccessibleName(caption)

    def _reserve_width(self) -> None:
        """Room for the widest reading, in the font the label actually has.

        Measured again whenever the font changes, because at construction time
        it has not got one yet: the theme's stylesheet is applied to the
        application after the widgets are built, so a floor measured here from
        the default face is too narrow for the mono one. The symptom was a
        four-pixel shove of the next readout when a count reached four digits -
        which is precisely what a fixed slot exists to prevent, and which an
        offscreen run can never catch because every glyph there is the same
        width.

        The floor is a *floor*: a reading wider than the reserved sample still
        grows rather than being elided. Losing a digit off a dropped-frame
        count would be worse than the shove.
        """
        metrics = QFontMetrics(self._value.font())
        self._value.setMinimumWidth(metrics.horizontalAdvance(self._sample))

    def _reserve_height(self) -> None:
        """A row of readouts whose height does not depend on its readings.

        The transport row sits under the picture, so a readout that grows by
        two pixels when it gets a value moves the picture, the console and
        everything in it by two pixels. Measured at 150% scaling on
        21 September: connecting the camera shifted fourteen controls down by
        two, for no reason anybody could see.
        """
        wanted = (
            max(
                QFontMetrics(self._value.font()).height(),
                QFontMetrics(self._caption.font()).height(),
            )
            + 8
        )
        self._reserved_height = max(self._reserved_height, wanted)
        self.setFixedHeight(self._reserved_height)

    def changeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self._reserve_width()
            self._reserve_height()

    def set_value(self, text: str, *, status: str = "", detail: str = "") -> None:
        self._value.setText(text)
        self._value.setProperty("kcStatus", status or None)
        style = self._value.style()
        style.unpolish(self._value)
        style.polish(self._value)
        if detail:
            self.setToolTip(detail)
        self.setAccessibleDescription(f"{self._caption.text()}: {text}")


class _StatusLine(ElidedLabel):
    """One line of the status pane, at a height styling cannot change.

    A status property going from neutral to warning re-runs the stylesheet,
    and the polished label came back a pixel taller. One pixel is enough to
    move the line under it, and moving lines is the whole complaint about this
    screen. The height is taken from the font and re-taken whenever the font
    changes, so it follows a DPI or theme change but not a colour.
    """

    def __init__(self, role: str, parent=None) -> None:  # noqa: ANN001
        super().__init__("", parent)
        self.setProperty("kcRole", role)
        self._reserved = 0
        self._reserve_height()

    def _reserve_height(self) -> None:
        """The tallest this line has ever needed, and never less again.

        Monotonic on purpose. The height is measured whenever the font or the
        style changes, and the theme's stylesheet arrives *after* the widget
        is built - so the first measurement is of the default face and the
        second of the real one. Taking the larger of the two settles at the
        tallest and stops there; taking the latest let the line shrink by
        three pixels when a status property was applied, and everything under
        it moved by three pixels.
        """
        wanted = QFontMetrics(self.font()).height() + 4
        # Monotonic over what the *font* has asked for, never over the
        # widget's current height. A widget that has not been laid out yet
        # reports whatever Qt gave it - 2000 pixels, in one measured case -
        # and taking the maximum against that locked the line at that height
        # for good, which took the whole status block with it.
        self._reserved = max(getattr(self, "_reserved", 0), wanted)
        self.setFixedHeight(self._reserved)

    def changeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self._reserve_height()


class _ConsoleGroup(QWidget):
    """One titled block in the console column."""

    def __init__(self, title: str, tokens: ThemeTokens, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(0, 0, 0, 0)
        # Medium, not small. Four pixels between a caption and the control it
        # names reads as one smudged shape; the column has the height to be
        # generous and, since the 22 September revision, is asked to be.
        self.column.setSpacing(tokens.metric("KcSpacingMd"))
        self.column.addWidget(label(title, role="sectionTitle"))

    def add(self, widget: QWidget) -> QWidget:
        self.column.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:  # noqa: ANN001
        self.column.addLayout(layout)

    def reserve(self) -> None:
        """Freeze this block at the height it needs now.

        Called once the block is built and filled with its widest expected
        content. Afterwards the words inside can change freely and nothing
        below moves - which is the whole complaint about this screen: the
        framing verdict changing mid-shot and taking the record button with
        it.

        A height hint is not enough here: ``QVBoxLayout`` grows a block when
        a wrapped label needs a third line, and the blocks under it slide. An
        explicit minimum is what the parent layout actually consults.
        """
        self.column.activate()
        height = self.sizeHint().height()
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)


class CapturePage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[CaptureViewModel] = None
        #: idle | counting | recording | stopping. Drives the button's shape
        #: and its accessible description, so the state is never colour alone.
        self._record_state = ""

        # Nothing on this screen reports the camera's changing state in
        # place: no strip above the picture, no status block in the console,
        # no badge on the image. The one thing it still says out loud is the
        # refusal to record with nobody chosen, which arrives as a message
        # card and is the only notification the 21 September review kept.

        # The scene and its console, side by side. The picture is given the
        # width its own ratio can use and no more; the console takes the rest,
        # up to a readable limit. See `services/capture_layout.py`.
        self.stage_row = QHBoxLayout()
        self.stage_row.setSpacing(tokens.metric("KcSpacingXl"))
        self.preview = PreviewView(tokens, self)
        self.preview.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.stage_row.addStretch(1)
        self.stage_row.addWidget(
            self.preview, 0, Qt.AlignmentFlag.AlignTop
        )
        # The same box as the picture: same top, same bottom, same height.
        # It briefly hugged its own content instead, which left the console
        # ending two hundred pixels above the image beside it - and a panel
        # that stops in mid-air next to a full-height picture reads as
        # unfinished rather than as tidy. The room inside it is spent on the
        # blocks instead; see :meth:`_spread_console`.
        self.stage_row.addWidget(
            self._build_console(tokens), 0, Qt.AlignmentFlag.AlignTop
        )
        self.stage_row.addStretch(1)
        self.body_layout.addLayout(self.stage_row, 1)
        #: The source's width / height. Zero until a frame arrives, which the
        #: solver reads as "assume the usual camera" rather than as a square.
        self._source_ratio = 0.0
        self._stage = None

        rule = separator()
        self.body_layout.addWidget(rule)
        #: What the rule under the stage costs. Part of the stage-height sum,
        #: so it is asked for rather than assumed to be one pixel.
        self._separator_height = max(1, rule.sizeHint().height())
        # One row, not two. The height the second row used to take is given
        # back to the camera image and the console beside it.
        self._transport_row = self._build_transport(tokens)
        self.body_layout.addLayout(self._transport_row)

        self._metrics_timer = QTimer(self)
        self._metrics_timer.setInterval(_METRICS_INTERVAL_MS)
        self._metrics_timer.timeout.connect(self._tick_metrics)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(_PREVIEW_INTERVAL_MS)
        self._preview_timer.timeout.connect(self._tick_preview)
        # The countdown and the optional timed stop both live on one second,
        # which is the only clock this screen needs and the viewmodel has none.
        self._second = QTimer(self)
        self._second.setInterval(1000)
        self._second.timeout.connect(self._tick_second)

        # Reachable from the frame: somebody standing in the shot cannot aim
        # at a button, and pressing the wrong one of two is worse than one key
        # that does the right thing whatever the state is.
        for sequence in ("Space", "F5"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._toggle_recording)

    # ------------------------------------------------------------- assembly
    def _build_console(self, tokens: ThemeTokens) -> QWidget:
        """Everything that configures the shot, in one readable column.

        The settings never reflow into a second column. That reflow doubled the
        panel's requested width at 150% display scaling and reduced the RGB
        preview to a narrow strip. A vertical scrollbar is the predictable
        fallback when a large text/display scale leaves less height than the
        column needs; at the normal full-screen size it is absent.
        """
        panel = QFrame()
        panel.setProperty("kcSurface", "raised")
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        # No margins here: ``QFrame[kcSurface="raised"]`` carries the inset, so
        # the gap between a border and what it holds is decided in one place.
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(panel)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        holder = QWidget(scroll)
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        # A separator is its own layout item, so the layout adds spacing on
        # both sides of it. Medium spacing yields the intended 16 px gap
        # between groups without making the normal-height console scroll.
        box.setSpacing(tokens.metric("KcSpacingMd"))
        scroll.setWidget(holder)
        outer.addWidget(scroll)
        self._console_scroll = scroll
        self._console_columns = [(holder, box)]

        # Controls only. The former DURUM block - the framing verdict, its
        # advice, the worst alert and the preview model's note - is gone from
        # this column by the 21 September user decision: it was four lines of
        # changing text in the middle of a settings panel, saying the same
        # things the badge over the picture was saying. None of it was
        # deleted; it is gathered by :meth:`status_sections` and opened from
        # Araçlar › Yakalama Durumu, which is where a diagnosis belongs.
        self._groups = [
            self._build_target_group(tokens),
            self._build_subject_group(tokens),
            self._build_mode_group(tokens),
            self._build_solo_group(tokens),
        ]
        self._build_status_sink(tokens)
        self.console = panel
        # Kept as an alias for callers that knew the old panel name.
        self.console_frame = panel
        self._console_layout_columns = 0
        self._console_reserved = False
        self._reflow_console(1)
        return panel

    def _reserve_console(self) -> None:
        """Freeze every block at the height it needs, once there is geometry.

        Done here rather than in the builders because a widget that has never
        been laid out has no useful ``sizeHint``: the status block measured two
        thousand pixels that way. By the first real layout pass every block
        has its fonts, its width and its stylesheet, so what it reports is what
        it will need.

        The one block whose content can genuinely change height is the mode
        block, whose "Modu uygula" button appears when the camera is running a
        mode other than the chosen one. It is made visible for the
        measurement, so the row keeps room for it either way.
        """
        if self._console_reserved:
            return
        was_visible = self.apply_mode_button.isVisible()
        self.apply_mode_button.setVisible(True)
        for group in self._groups:
            group.reserve()
        self.apply_mode_button.setVisible(was_visible)
        self._console_reserved = True

    def _group_heights(self) -> list[int]:
        """What each block needs. Its reservation once it has one."""
        return [
            max(group.minimumHeight(), group.sizeHint().height())
            for group in self._groups
        ]

    def _console_height_needed(self, columns: int) -> int:
        """How tall the console's single column wants to be.

        Counts the separators between blocks as well as the blocks: they are a
        pixel each plus a gap, and leaving them out is how a column that did
        not fit was reported as fitting.
        """
        del columns  # Compatibility for measurement callers from the old layout.
        spacing = self._console_columns[0][1].spacing() * 2 + 1
        heights = self._group_heights()
        return sum(heights) + spacing * max(0, len(heights) - 1)

    def _console_inset(self) -> int:
        """The raised surface's own vertical padding, from the stylesheet.

        Asked of the widget rather than assumed: the inset lives in
        ``QFrame[kcSurface="raised"]`` so it can be changed in one place, and
        a height computed from the blocks alone would clip the last checkbox
        by exactly that much.
        """
        margins = self.console.contentsMargins()
        return margins.top() + margins.bottom()

    #: The most a gap between two blocks may grow when the column has height
    #: to spare. Past this the blocks stop reading as a list of settings and
    #: start reading as four unrelated cards; whatever is left over after
    #: every gap has taken its share stays at the foot of the column.
    CONSOLE_GAP_MAX = 44

    def _reflow_console(self, columns: int) -> None:
        """Keep every block in one stable, vertically scrollable column.

        A spacer is kept beside every rule so the column's spare height can be
        handed to the gaps between blocks rather than collecting at the
        bottom. It is sized in :meth:`_spread_console`, once the height the
        column actually got is known.
        """
        del columns  # The view deliberately has no multi-column state.
        if self._console_layout_columns == 1:
            return
        self._console_layout_columns = 1
        for _holder, box in self._console_columns:
            while box.count():
                item = box.takeAt(0)
                widget = item.widget()
                if widget is not None and widget not in self._groups:
                    widget.deleteLater()
                elif widget is not None:
                    widget.setParent(None)

        #: Two per gap between two blocks - one above the rule and one below
        #: it - so the spare height lands on both sides and the rule stays in
        #: the middle of the gap rather than hugging the block above it.
        self._console_gaps: list[QSpacerItem] = []
        for holder, box in self._console_columns:
            for index, group in enumerate(self._groups):
                if index:
                    for position in (0, 1):
                        spacer = QSpacerItem(
                            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
                        )
                        box.addSpacerItem(spacer)
                        self._console_gaps.append(spacer)
                        if not position:
                            box.addWidget(separator())
                group.setParent(holder)
                box.addWidget(group)
                group.show()
            box.addStretch(1)
            holder.setVisible(True)

    def _spread_console(self, height: int) -> None:
        """Give the column's spare height to the gaps between its blocks.

        Asked for on 22 September: with the console back to the picture's
        height its four blocks sat crammed against the top. The room is spent
        between them rather than inside them - a block is a caption and the
        controls it names, and pushing *those* apart would be the opposite of
        an improvement - and each gap takes at most
        :attr:`CONSOLE_GAP_MAX`, so a very tall window does not turn the
        column into four islands.
        """
        gaps = getattr(self, "_console_gaps", None)
        if not gaps:
            return
        holder, box = self._console_columns[0]
        for spacer in gaps:
            spacer.changeSize(
                0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
        box.invalidate()
        box.activate()
        # What the blocks and rules really take with every gap at zero, asked
        # of the layout rather than re-derived from the tokens.
        packed = holder.sizeHint().height()
        spare = max(0, height - self._console_inset() - packed)
        # Each gap is two spacers, and the cap is on the gap rather than on
        # one half of it.
        extra = min(self.CONSOLE_GAP_MAX, 2 * spare // len(gaps)) // 2
        if extra <= 0:
            return
        for spacer in gaps:
            spacer.changeSize(
                0, extra, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )
        box.invalidate()

    def _build_target_group(self, tokens: ThemeTokens) -> QWidget:
        """Who the take is written to. Stated here, chosen on Projeler.

        Deliberately not a control: the participant belongs to the project, and
        a second place to change it is a second answer to the same question -
        which is how a take ended up under P0001 with P0002 selected.
        """
        group = _ConsoleGroup("KAYIT HEDEFİ", tokens, self)
        self.target_value = ElidedLabel("—")
        self.target_value.setProperty("kcRole", "fieldLabel")
        group.add(self.target_value)
        self.target_detail = ElidedLabel("")
        self.target_detail.setProperty("kcRole", "pageSubtitle")
        group.add(self.target_detail)
        self.target_detail.setText("")
        return group

    def _build_subject_group(self, tokens: ThemeTokens) -> QWidget:
        """The person in the frame, picked by clicking on them."""
        group = _ConsoleGroup("GÖRÜNTÜDEKİ KİŞİ", tokens, self)
        # A different question from KAYIT HEDEFİ above it: that one is the
        # project participant whose folder the take is written to, this one is
        # which body in the camera image is being recorded. Neither implies
        # the other, and they are answered in different places.
        self.subject_label = ElidedLabel("Kişi seçilmedi")
        self.subject_label.setProperty("kcRole", "fieldLabel")
        group.add(self.subject_label)
        # One elided line, with the whole sentence in the tooltip. Wrapped, it
        # needed two lines before a person was chosen and three afterwards,
        # and the blocks below it moved by the difference.
        self.subject_hint = ElidedLabel(
            "Kaydedilecek kişiyi görüntüde üzerine tıklayarak seçin."
        )
        self.subject_hint.setProperty("kcRole", "pageSubtitle")
        group.add(self.subject_hint)
        self.clear_subject_button = QPushButton("Kişi seçimini kaldır")
        self.clear_subject_button.setProperty("kcVariant", "quiet")
        self.clear_subject_button.setEnabled(False)
        self.clear_subject_button.clicked.connect(self._clear_subject)
        group.add(self.clear_subject_button)
        return group

    def _build_mode_group(self, tokens: ThemeTokens) -> QWidget:
        group = _ConsoleGroup("KAYIT MODU", tokens, self)
        self._mode_group = QButtonGroup(self)
        self._mode_buttons: dict[str, QRadioButton] = {}
        for mode in RECORDING_MODES:
            button = QRadioButton(mode.label)
            tip = mode.detail + (f"  ({mode.cost})" if mode.cost else "")
            button.setToolTip(tip)
            button.setAccessibleDescription(tip)
            button.toggled.connect(
                lambda checked, key=mode.key: self._mode_chosen(key, checked)
            )
            self._mode_group.addButton(button)
            self._mode_buttons[mode.key] = button
            group.add(button)
            if mode.cost:
                cost = label(mode.cost, role="fieldCost")
                cost.setWordWrap(True)
                group.add(cost)

        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingMd"))
        # The "etkin" / "kamera bağlı değil" pill used to stand here. It is a
        # *status*, not a control, and the user asked for the variable camera
        # state to leave this column - the connection is now said by the
        # connect button in the transport row, which turns green, and the
        # detail is in Araçlar › Yakalama Durumu. The widget itself is kept
        # (never parented into the column) because it is what the status
        # window and the tests read the wording from.
        self.mode_state = _ModeState(tokens)
        self.mode_state.setToolTip(
            "Seçilen mod ile kameranın gerçekten çalıştığı mod ayrı gösterilir."
        )
        self.mode_state.setParent(self)
        self.mode_state.hide()
        self.apply_mode_button = QPushButton("Modu uygula")
        self.apply_mode_button.setProperty("kcVariant", "quiet")
        self.apply_mode_button.setToolTip(
            "Kamerayı seçilen kayıt moduyla yeniden bağlar."
        )
        self.apply_mode_button.setVisible(False)
        self.apply_mode_button.clicked.connect(self._apply_mode)
        row.addWidget(self.apply_mode_button)
        row.addStretch(1)
        group.add_layout(row)
        self.apply_mode_button.setVisible(False)
        return group

    def _build_solo_group(self, tokens: ThemeTokens) -> QWidget:
        """Everything needed to record without a second person in the room."""
        group = _ConsoleGroup("TEK BAŞINA", tokens, self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.metric("KcSpacingLg"))
        grid.setVerticalSpacing(tokens.metric("KcSpacingLg"))
        grid.setColumnStretch(1, 1)

        grid.addWidget(label("Geri sayım"), 0, 0)
        self.countdown_box = QComboBox()
        self.countdown_box.setAccessibleName("Geri sayım süresi")
        self.countdown_box.setToolTip(
            "Kayıt bu kadar saniye sonra başlar. Kadraja girmek için süre bırakır."
        )
        for seconds in COUNTDOWN_CHOICES:
            self.countdown_box.addItem(
                "kapalı" if not seconds else f"{seconds} sn", seconds
            )
        self.countdown_box.activated.connect(self._countdown_chosen)
        grid.addWidget(self.countdown_box, 0, 1)

        grid.addWidget(label("Süre sonunda dur"), 1, 0)
        self.duration_box = QComboBox()
        self.duration_box.setAccessibleName("Kayıt süresi sınırı")
        self.duration_box.setToolTip("Bu süre dolunca kayıt kendiliğinden kapanır.")
        for seconds in DURATION_CHOICES:
            self.duration_box.addItem(
                "sınırsız" if not seconds else f"{seconds} sn", seconds
            )
        self.duration_box.activated.connect(self._duration_chosen)
        grid.addWidget(self.duration_box, 1, 1)
        group.add_layout(grid)

        self.mirror_box = QCheckBox("Önizlemeyi aynala")
        self.mirror_box.setToolTip(
            "Önizlemeyi yatay çevirir. Kaydedilen görüntü değişmez."
        )
        self.mirror_box.toggled.connect(self._mirror_toggled)
        group.add(self.mirror_box)
        self.guides_box = QCheckBox("Kadraj kılavuzu")
        self.guides_box.setToolTip(
            "Üçte bir çizgileri ve baş/ayak payı. Yalnız çerçeveleme yardımıdır; "
            "kişinin kadrajda olduğunu ölçmez."
        )
        self.guides_box.toggled.connect(self._guides_toggled)
        group.add(self.guides_box)

        return group

    def _build_status_sink(self, tokens: ThemeTokens) -> None:
        """Where the camera's changing state is kept now that it is not shown.

        Until 21 September these four lines were a DURUM block in the console:
        the framing verdict, its advice, the worst alert and the preview
        model's own note. The user's decision is that none of them belongs on
        this screen - they changed while somebody was standing in front of the
        camera, and the screen's job there is the picture and the record
        button.

        Nothing was switched off. The viewmodel still measures framing, still
        raises alerts and still reports what the pose model can and cannot
        see; the bindings below still receive all of it. It lands in widgets
        that are never laid out, so the wording has exactly one definition,
        and :meth:`status_sections` hands that wording to Araçlar › Yakalama
        Durumu. Removing the *display* of a diagnosis is not removing the
        diagnosis, and the recording guards are untouched: refusing to record
        without a chosen person still happens, and still says so.
        """
        sink = QWidget(self)
        sink.setVisible(False)
        column = QVBoxLayout(sink)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        self.framing_label = _StatusLine("fieldLabel", sink)
        self.framing_label.setToolTip(
            "Tüm vücudun kadrajda olup olmadığı. Canlı önizleme pozundan "
            "ölçülür; kaydedilen veriyi etkilemez."
        )
        column.addWidget(self.framing_label)

        self.framing_advice = _StatusLine("pageSubtitle", sink)
        column.addWidget(self.framing_advice)

        self.alert_label = _StatusLine("fieldLabel", sink)
        self.alert_label.setAccessibleName("Uyarı")
        column.addWidget(self.alert_label)

        self.pose_note = _StatusLine("pageSubtitle", sink)
        column.addWidget(self.pose_note)

        self.status_details_button = QPushButton("Ayrıntılar", sink)
        self.status_details_button.setProperty("kcVariant", "quiet")
        self.status_details_button.setToolTip("Bütün uyarıları tam metniyle aç")
        self.status_details_button.clicked.connect(self._open_status_details)
        self.status_details_button.setEnabled(False)
        column.addWidget(self.status_details_button)

        self.status_group = sink
        #: Everything the details window would show, newest first.
        self._status_details: list[tuple[str, str]] = []

    def _open_status_details(self) -> None:
        """The full text of everything the pane could only summarise."""
        window = getattr(self, "_status_window", None)
        if window is None:
            window = DetailWindow("Yakalama · durum ayrıntıları", self._tokens, self)
            self._status_window = window
        window.show_rows(self._status_details)
        window.show()
        window.raise_()
        window.activateWindow()

    #: Framing / alert level -> the colour a status row is printed in.
    _STATUS_LEVELS = {
        "ok": "ready",
        "live": "ready",
        "tight": "warning",
        "crowded": "warning",
        "warning": "warning",
        "cut": "error",
        "error": "error",
    }

    def status_sections(self) -> tuple:
        """The camera and framing state, for Araçlar › Yakalama Durumu.

        Read live from the same values the screen itself holds, so the window
        and the screen cannot disagree, and gathered rather than cached so a
        window left open on a second monitor is current whenever it refreshes.
        """
        from kinecapture.studio.services.inspectors import Row, Section

        viewmodel = self.viewmodel
        metrics = viewmodel.metrics.value if viewmodel is not None else None
        connecting = bool(viewmodel and viewmodel.connecting.value)
        connected = bool(metrics and metrics.connected)
        camera = [
            Row(
                "Bağlantı",
                "bağlanıyor…" if connecting else ("bağlı" if connected else "bağlı değil"),
                detail="Kameranın açık olup olmadığı.",
                level="ready" if connected else "neutral",
            ),
            Row(
                "Kayıt modu",
                self.mode_state.text(),
                detail="Seçilen mod ile kameranın gerçekten çalıştığı mod.",
            ),
        ]
        if metrics is not None:
            camera += [
                Row("Kare hızı", f"{metrics.acquisition_fps:.1f}"),
                Row(
                    "Kayıt kaybı",
                    str(metrics.recording_dropped),
                    detail="Kaydedilemeyen kare sayısı. Bu veri hiç var olmayacak.",
                    level="error" if metrics.recording_dropped else "neutral",
                ),
                Row(
                    "Önizleme kaybı",
                    str(metrics.preview_dropped),
                    detail="Arayüzün yetişemediği önizleme karesi. Kaydı etkilemez.",
                ),
            ]

        framing = getattr(self, "_framing", None)
        framing_rows = []
        if framing is not None and framing.text:
            framing_rows.append(
                Row(
                    "Kadraj",
                    framing.text,
                    detail=framing.advice,
                    level=self._STATUS_LEVELS.get(framing.state, "neutral"),
                )
            )
            if framing.advice:
                framing_rows.append(Row("Öneri", framing.advice))
        note = self.pose_note.fullText()
        if note:
            framing_rows.append(Row("Önizleme modeli", note))
        if not framing_rows:
            framing_rows.append(Row("Kadraj", "ölçüm yok"))

        alert_rows = [
            Row(
                alert.level.value.upper(),
                alert.text,
                level=self._STATUS_LEVELS.get(alert.level.value, "neutral"),
            )
            for alert in getattr(self, "_alerts", ())
        ]
        return (
            Section("Kamera", tuple(camera)),
            Section(
                "Kadraj",
                tuple(framing_rows),
                note=(
                    "Kadraj ölçümü canlı önizleme pozundan gelir ve kaydedilen "
                    "veriyi etkilemez."
                ),
            ),
            Section(
                "Uyarılar",
                tuple(alert_rows) or (Row("Uyarı", "yok", level="ready"),),
            ),
        )

    def _build_connect(self, tokens: ThemeTokens) -> QPushButton:
        """The camera, connected from beside the record button.

        Put back into the transport row on 21 September, immediately after
        "Kayda başla". The previous round had moved it into the page header on
        the argument that connecting is a property of the machine rather than
        a step; the user's answer is that in practice it *is* the step before
        recording, and the hand that is about to press record is already here.

        Green while connected, and the wording changes with it, so the state
        is never carried by colour alone - and so nothing else has to say
        "etkin" in a panel somewhere.
        """
        button = QPushButton("Bağlan")
        button.setIcon(
            iconset.icon("connect", tokens, size=tokens.metric("KcIconSize"))
        )
        button.setAccessibleName("Kameraya bağlan")
        button.clicked.connect(self._toggle_connection)
        # Its label changes - "Bağlan", "Bağlanıyor…", "Bağlantıyı kes" - and
        # it stands at the head of a row of fixed-width readouts, so a widening
        # on connect would push Süre, FPS and everything after them sideways.
        # Both dimensions are reserved for the longest wording.
        metrics = QFontMetrics(button.font())
        widest = max(
            metrics.horizontalAdvance(text)
            for text in ("Bağlan", "Bağlanıyor…", "Bağlantıyı kes")
        )
        button.setMinimumWidth(
            max(150, widest + tokens.metric("KcIconSize") + 48)
        )
        # Matched to the record button beside it, in QSS as well as on the
        # widget: repolishing the connected state otherwise resets the height
        # from the application-wide button rule, which is a two-pixel shove of
        # the whole row every time the camera opens or closes.
        height = tokens.metric("KcControlHeightLarge")
        button.setStyleSheet(f"min-height: {height}px; max-height: {height}px;")
        button.setFixedHeight(max(height, metrics.height() + 20))
        self.connect_button = button
        return button

    def _set_connection_state(self, state: str) -> None:
        """idle | connecting | connected - as wording, icon and colour."""
        if getattr(self, "_connection_state", "") == state:
            return
        self._connection_state = state
        self.connect_button.setProperty("kcConnected", state)
        style = self.connect_button.style()
        if style is not None:
            style.unpolish(self.connect_button)
            style.polish(self.connect_button)

    def _build_transport(self, tokens: ThemeTokens) -> QHBoxLayout:
        """One row: what you press, and what you need to see while pressing it.

        The order is fixed by the 21 September user decision, left to right:

            Kayda başla · Bağlan/Bağlantıyı kes · Süre · FPS · Kayıt kaybı ·
            Önizleme kaybı · Diskte kalan · İşaret koy

        Everything on it is vertically centred on one line. The recorded frame
        count is no longer a column of its own - it is the detail on the
        duration, which is the same fact told in the unit an operator thinks
        in.
        """
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingXl"))
        row.setContentsMargins(0, 0, 0, 0)

        # 1. Kayıt. Red, and shaped: a dot to start, a square to stop, so the
        #    state is legible to someone who cannot separate the hues.
        self.record_button = QPushButton("Kayda başla")
        self.record_button.setProperty("kcVariant", "record")
        self.record_button.setMinimumWidth(190)
        # The content height plus the stylesheet's vertical padding/border is
        # reserved in every state. At fractional DPI the stop icon otherwise
        # makes the native hint two pixels taller than the start icon.
        # Keep the constraint in QSS too: repolishing a state otherwise resets
        # QWidget's minimum height from the application-wide button rule.
        self.record_button.setStyleSheet(
            f"min-height: {tokens.metric('KcControlHeightLarge')}px;"
            f"max-height: {tokens.metric('KcControlHeightLarge')}px;"
        )
        self.record_button.setEnabled(False)
        self.record_button.setAccessibleName("Kaydı başlat veya durdur")
        row.addWidget(self.record_button, 0, Qt.AlignmentFlag.AlignVCenter)

        # 2. The camera. Directly after the record button, because it is what
        #    has to be true before that button does anything.
        row.addWidget(
            self._build_connect(tokens), 0, Qt.AlignmentFlag.AlignVCenter
        )

        # 3. Süre, with the countdown in the same place so neither moves the
        #    other. The frame count rides along as this readout's detail.
        self.elapsed = _Metric("Süre", tokens, self, digits=6)
        self.elapsed.setToolTip("Açık kaydın süresi")
        row.addWidget(self.elapsed, 0, Qt.AlignmentFlag.AlignVCenter)
        # The countdown appears and disappears, so it is given a slot of a
        # fixed width rather than being inserted into the row. Otherwise
        # starting a countdown pushes FPS and both loss counters sideways -
        # exactly the kind of movement UI-01 rules out.
        self.countdown_label = mono_label("")
        self.countdown_label.setProperty("kcStatus", "warning")
        self.countdown_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.countdown_slot = QWidget(self)
        slot = QHBoxLayout(self.countdown_slot)
        slot.setContentsMargins(0, 0, 0, 0)
        slot.setSpacing(0)
        slot.addWidget(self.countdown_label)
        self._size_countdown_slot()
        row.addWidget(self.countdown_slot, 0, Qt.AlignmentFlag.AlignVCenter)

        # 4-7. Telemetry, each from its own source. The two loss counters are
        #      never merged: one is the interface keeping up, the other is data
        #      that will not exist.
        self.metrics_widgets = {
            "elapsed": self.elapsed,
            "acquisition": _Metric("FPS", tokens, self, sample="000.0"),
            "recording_loss": _Metric("Kayıt kaybı", tokens, self, digits=4),
            "preview_loss": _Metric("Önizleme kaybı", tokens, self, digits=4),
            # The unit travels with the number, so it is reserved with it.
            "disk": _Metric("Diskte kalan", tokens, self, sample="00000 dk"),
        }
        for key in ("acquisition", "recording_loss", "preview_loss", "disk"):
            row.addWidget(
                self.metrics_widgets[key], 0, Qt.AlignmentFlag.AlignVCenter
            )

        # 8. İşaret koy.
        self.marker_button = QPushButton("İşaret koy")
        self.marker_button.setProperty("kcVariant", "quiet")
        self.marker_button.setIcon(
            iconset.icon("marker", tokens, size=tokens.metric("KcIconSize"))
        )
        self.marker_button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.marker_button.setEnabled(False)
        row.addWidget(self.marker_button, 0, Qt.AlignmentFlag.AlignVCenter)

        row.addStretch(1)
        # A reminder, not a control. It is the one thing in this row that may
        # give up its width: at 150% on a 1366-wide laptop the row wanted
        # 1053 px against 911 available, and 165 of those were this sentence.
        # It elides, and its tooltip keeps the full text, so nothing is lost
        # that was not already written on the keyboard.
        self.shortcut_hint = ElidedLabel("Boşluk veya F5: başlat / durdur")
        self.shortcut_hint.setProperty("kcRole", "pageSubtitle")
        self.shortcut_hint.setMinimumWidth(0)
        self.shortcut_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self.shortcut_hint, 0, Qt.AlignmentFlag.AlignVCenter)

        self.record_button.clicked.connect(self._toggle_recording)
        self.marker_button.clicked.connect(self._add_marker)
        self.preview.clicked.connect(self._preview_clicked)
        return row

    #: The order the 21 September decision fixes for the control row, left
    #: to right. The connection sits between starting a take and the readouts
    #: that describe one.
    CONTROL_ORDER = (
        "record",
        "connect",
        "elapsed",
        "acquisition",
        "recording_loss",
        "preview_loss",
        "disk",
        "marker",
    )

    def control_row_order(self) -> tuple[str, ...]:
        """What is actually on the row, left to right. Measured, for a test."""
        widgets = {
            id(self.record_button): "record",
            id(self.connect_button): "connect",
            id(self.marker_button): "marker",
            **{id(w): key for key, w in self.metrics_widgets.items()},
        }
        found: list[tuple[int, str]] = []
        for index in range(self._transport_row.count()):
            widget = self._transport_row.itemAt(index).widget()
            name = widgets.get(id(widget)) if widget is not None else None
            if name is not None:
                found.append((widget.x(), name))
        return tuple(name for _x, name in sorted(found))

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: CaptureViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.metrics, self._show_metrics)
        self.bind(viewmodel.alerts, self._show_alerts)
        self.bind(viewmodel.anchor, self._show_anchor)
        self.bind(viewmodel.pose_note, self._show_pose_note)
        self.bind(viewmodel.framing, self._show_framing)
        self.bind_event(viewmodel.notice, self._show_notice)
        self.bind(viewmodel.mode, self._show_mode)
        self.bind(viewmodel.active_mode, lambda _m: self._show_mode_state())
        self.bind(viewmodel.mode_pending, lambda _p: self._show_mode_state())
        self.bind(viewmodel.target, self._show_target)
        self.bind(viewmodel.countdown, self._show_countdown)
        self.bind(viewmodel.countdown_seconds, self._show_countdown_choice)
        self.bind(viewmodel.auto_stop_seconds, self._show_duration_choice)
        self.bind(viewmodel.mirrored, self._show_mirror)
        self.bind(viewmodel.guides, self._show_guides)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        self._metrics_timer.start()
        self._preview_timer.start()
        self._second.start()
        if self.viewmodel is not None:
            self.viewmodel.refresh_target()
            self.viewmodel.refresh()

    def page_deactivated(self) -> None:
        """Stop the timers. A screen nobody is looking at costs nothing.

        The camera is deliberately *not* closed: leaving Capture to change a
        setting and coming back should not mean waiting for the SDK to open
        again, which on a cold start is measured in minutes.
        """
        self._metrics_timer.stop()
        self._preview_timer.stop()
        self._second.stop()
        # A countdown belongs to the screen the operator is looking at. Leaving
        # it must not start a recording behind their back.
        if self.viewmodel is not None:
            self.viewmodel.cancel_countdown()

    # ----------------------------------------------------------------- ticks
    def _tick_metrics(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.refresh()

    def _tick_second(self) -> None:
        if self.viewmodel is None:
            return
        self.viewmodel.tick_countdown()
        self.viewmodel.tick_auto_stop()

    def _note_source_shape(self, size) -> None:  # noqa: ANN001 - (w, h)
        """Remember the camera's own shape. **Never re-split on it.**

        It used to call :meth:`apply_stage_geometry` here, so the outer
        preview box was a function of the frame that had just arrived: the
        black rectangle before Bağlan was one size, the picture after it
        another, and disconnecting moved everything back. That is the
        21 September complaint, and the fix is structural - the box is solved
        from the page, the picture is letterboxed inside it by
        :meth:`PreviewView._target_rect`, and the source's exact ratio is
        still honoured to the pixel *within* a box that does not move.

        The value is still kept: the layout no longer consults it, but a
        measurement and the status window both want to know what the camera
        actually sent.
        """
        width, height = (int(size[0]), int(size[1])) if size else (0, 0)
        ratio = (width / height) if width > 0 and height > 0 else 0.0
        if ratio:
            self._source_ratio = ratio

    def _tick_preview(self) -> None:
        if self.viewmodel is None:
            return
        packet = self.viewmodel.service.latest_frame()
        if packet is None or packet.color_frame is None:
            return
        self.preview.set_frame(packet.color_frame, tuple(packet.resolution))
        self._note_source_shape(tuple(packet.resolution))
        preview = self.viewmodel.service.pose_preview()
        if preview is not None and preview.packet is packet:
            from kinecapture.preview.pose import BONES

            self.preview.set_people(preview.people, BONES)
        # Still measured per frame. It is no longer *said* per frame: the
        # verdict and the last-fifteen-seconds summary were a badge across the
        # top of the picture, over the person the operator was trying to click
        # on, and the 21 September decision takes them off the image. The
        # measurement is handed to the view, which keeps it for
        # Araçlar > Yakalama Durumu and paints nothing.
        framing = self.viewmodel.observe_framing()
        self.preview.set_framing(
            framing.text, framing.state, self.viewmodel.framing_history.value
        )
        # And the box around whoever was picked, resolved against *this* frame
        # rather than the one the click happened on - the person has moved
        # since, and a box left where they used to be is a lie.
        anchor = self.viewmodel.anchor.value
        self.preview.set_subject_box(
            subject_box(preview.people, anchor.point_xy)
            if (preview is not None and anchor is not None)
            else None
        )

    # ----------------------------------------------------------------- slots
    def _size_countdown_slot(self) -> None:
        """Fixed room for the countdown, measured in the font it will use.

        Same trap as `_Metric._reserve_width`: at construction the label has
        the default face, not the theme's, so a width taken here is wrong by
        the time anything is drawn. A *fixed* width makes it worse than a
        floor - the text is clipped rather than shoving - so this is
        re-measured whenever the font changes.
        """
        metrics = QFontMetrics(self.countdown_label.font())
        self.countdown_slot.setFixedWidth(metrics.horizontalAdvance("00 sn"))

    def changeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self._size_countdown_slot()

    def _stage_height(self) -> int:
        """How much height the picture-and-console row has, from the page.

        Derived rather than read back. ``stage_row.geometry()`` is zero before
        the first layout pass and, once the preview has a fixed size, it is
        partly a *consequence* of the last solve - feeding it back in let a
        DPI or screen change keep the preview at its old height. Here the
        answer is the body minus the things under it, which depends on nothing
        this method sets.
        """
        spacing = self.body_layout.spacing()
        below = (
            self._transport_row.sizeHint().height()
            + self._separator_height
            + spacing * 2
        )
        return max(0, self.body.height() - below)

    def apply_stage_geometry(self) -> None:
        """Split the width between the picture's box and the console.

        **The box does not depend on the camera.** It is solved from the page
        and a fixed reference ratio, so the black rectangle before Bağlan, the
        live image after it, and the rectangle again after Bağlantıyı kes all
        occupy exactly the same place - which is what the 21 September review
        asked for. Connecting, disconnecting and reconnecting move nothing:
        not the console beside it, not the transport row under it.

        The image's own aspect ratio is still exact. It is letterboxed inside
        this fixed box by :meth:`PreviewView._target_rect`, which scales by
        ``min`` of the two axes and centres - so a 4:3 camera in a 16:9 box
        gets bars at the sides rather than a stretched body.
        """
        if self.body.width() <= 0:
            return
        self._reserve_console()
        height = self._stage_height() or self.body.height()
        # The console is always one column. A former height-based reflow made
        # it two columns at 150% scaling, which doubled its minimum width and
        # squeezed the camera image into a narrow strip.
        self._reflow_console(1)
        stage = solve_capture_stage(
            available_width=self.body.width(),
            stage_height=height,
            # Deliberately the constant, never ``self._source_ratio``: see the
            # docstring. This is the *box*, not the image.
            source_ratio=DEFAULT_SOURCE_RATIO,
            spacing=self.stage_row.spacing(),
            console_columns=1,
        )
        self._stage = stage
        preview_height = min(
            height, int(round(stage.preview_width / DEFAULT_SOURCE_RATIO))
        )
        preview_height = max(0, preview_height)
        self.preview.setFixedSize(stage.preview_width, preview_height)
        self.console.setFixedWidth(stage.console_width)
        # Exactly the picture's height. Both are top-aligned in the row, so
        # the two boxes start and end on the same two lines.
        self.console.setFixedHeight(preview_height)
        self._spread_console(preview_height)

    @property
    def stage_geometry(self):  # noqa: ANN201 - CaptureStage | None
        """The last split, for a measurement to read rather than re-derive."""
        return self._stage

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().resizeEvent(event)
        self.apply_stage_geometry()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().showEvent(event)
        # A page-level font change does not always reach a child that is
        # repolished separately, and the label's real face is only settled
        # once it has been shown. Measuring again here is cheap and is the
        # first moment the answer is certainly right.
        self._size_countdown_slot()

    def _show_metrics(self, metrics: CaptureMetrics) -> None:
        widgets = self.metrics_widgets
        # Each number from its own source. The frame rate is the acquisition
        # thread's, the two losses are two different counters, and the disk is
        # the volume's - none of them is derived from another.
        widgets["acquisition"].set_value(
            f"{metrics.acquisition_fps:5.1f}",
            detail="Kameradan gerçekten gelen kare hızı.",
        )
        widgets["recording_loss"].set_value(
            f"{metrics.recording_dropped}",
            status="error" if metrics.recording_dropped else "",
            detail="Kaydedilemeyen kare sayısı. Bu veri hiç var olmayacak.",
        )
        widgets["preview_loss"].set_value(
            f"{metrics.preview_dropped}",
            detail=(
                "Arayüzün yetişemediği önizleme karesi. Kaydı etkilemez."
            ),
        )
        widgets["disk"].set_value(
            f"{metrics.free_minutes:5.0f} dk" if metrics.free_bytes else "—",
            status="warning" if 0 < metrics.free_minutes < 10 else "",
            detail="Bu ayarlarla kalan yaklaşık kayıt süresi.",
        )
        # The recorded frame count is the duration's detail rather than a
        # column of its own: the same fact, in the unit the operator thinks in,
        # without adding a seventh thing to the row.
        widgets["elapsed"].set_value(
            metrics.elapsed_text,
            detail=f"{metrics.recorded_frames} kare kaydedildi",
        )
        self.preview.set_recording(metrics.recording)

        stopping = bool(self.viewmodel and self.viewmodel.stopping.value)
        connecting = bool(self.viewmodel and self.viewmodel.connecting.value)
        counting = bool(self.viewmodel and self.viewmodel.countdown.value)

        # Enabled whenever there is a camera to record from. A missing
        # participant is answered when the button is pressed, with a sentence
        # saying what to do - never by a button that silently does nothing,
        # which is what made the ZED impossible to record with.
        self.record_button.setEnabled(
            counting or (metrics.connected and not stopping)
        )
        # Four states, four different things said. STOPPING is its own: the
        # take is still being closed and pressing again must not look like it
        # would start another one.
        if stopping:
            self._set_record_state("Kapatılıyor…", "busy", "stopping")
        elif counting:
            self._set_record_state("Geri sayımı iptal et", "record-stop", "counting")
        elif metrics.recording:
            self._set_record_state("Kaydı durdur", "record-stop", "recording")
        else:
            self._set_record_state("Kayda başla", "record-start", "idle")
        self.marker_button.setEnabled(metrics.recording)
        self.connect_button.setEnabled(
            not metrics.recording and not stopping and not connecting
        )
        # Green, and saying what pressing it would do. Both, because colour
        # alone is not a state - and because this button is now the only place
        # the screen says whether the camera is open at all.
        if connecting:
            state, text, icon = "connecting", "Bağlanıyor…", "connect"
        elif metrics.connected:
            state, text, icon = "connected", "Bağlantıyı kes", "disconnect"
        else:
            state, text, icon = "idle", "Bağlan", "connect"
        self.connect_button.setText(text)
        self.connect_button.setAccessibleDescription(text)
        self.connect_button.setIcon(
            iconset.icon(
                icon,
                self._tokens,
                colour_token=(
                    "KcTextOnAccent" if state == "connected" else "KcTextSecondary"
                ),
                size=self._tokens.metric("KcIconSize"),
            )
        )
        self._set_connection_state(state)
        self.preview.set_placeholder(
            "" if metrics.connected else "Kamera bağlı değil"
        )

    def _set_record_state(self, text: str, icon_key: str, state: str) -> None:
        """Text, shape and a named state - never colour alone."""
        if self.record_button.text() != text:
            self.record_button.setText(text)
        if self._record_state != state:
            self._record_state = state
            self.record_button.setIcon(
                iconset.icon(
                    icon_key,
                    self._tokens,
                    colour_token="KcTextOnAccent",
                    size=self._tokens.metric("KcIconSize"),
                )
            )
            self.record_button.setProperty("kcRecording", state)
            self.record_button.setAccessibleDescription(text)
            style = self.record_button.style()
            if style is not None:
                style.unpolish(self.record_button)
                style.polish(self.record_button)

    @property
    def record_state(self) -> str:
        """Which of idle/counting/recording/stopping the button is showing."""
        return self._record_state
        # The window title is the shell's: it has to keep saying RECORDING on
        # the seven screens that are not this one.

    def _show_alerts(self, alerts: tuple[Alert, ...]) -> None:
        """The most urgent one on the line; all of them in the details window.

        One line, always the same height. A list that grows with the number of
        alerts is a list that moves the controls under it, and on this screen
        the control under it is the record button.
        """
        self._alerts = alerts
        worst = alerts[0] if alerts else None
        self.alert_label.setText(worst.text if worst else "")
        self.alert_label.setToolTip(worst.text if worst else "")
        self.alert_label.setProperty("kcStatus", worst.level.value if worst else None)
        _restyle(self.alert_label)
        if worst is not None:
            self.alert_label.setAccessibleName(f"{worst.level.value}: {worst.text}")
        self._refresh_status_details()

    def _show_anchor(self, anchor) -> None:  # noqa: ANN001
        if anchor is None:
            self.subject_label.setText("Kişi seçilmedi")
            self.subject_label.setToolTip("")
            self.subject_hint.setText(
                "Kaydedilecek kişiyi görüntüde üzerine tıklayarak seçin."
            )
            self.subject_hint.setToolTip(self.subject_hint.fullText())
            self.clear_subject_button.setEnabled(False)
            return
        self.subject_label.setText("Kişi seçildi")
        self.subject_hint.setText(
            "Seçim bu karenin zaman damgasına bağlandı; değiştirmek için "
            "başka birine tıklayın."
        )
        self.subject_hint.setToolTip(
            "Seçim gösterilen karenin zaman damgasına bağlandı; eşleştirme "
            "kayıttan sonra yapılır. Değiştirmek için başka birine tıklayın."
        )
        self.subject_label.setToolTip(
            f"kare zaman damgası {anchor.camera_timestamp_ns} ns"
        )
        self.clear_subject_button.setEnabled(True)

    def _show_notice(self, notice: tuple[str, str]) -> None:
        """Deliberately does nothing with the text any more.

        A refusal used to be drawn on the picture *and* raised as a message
        card, so the operator was told to click on themselves twice at once,
        in two different places, with the picture-side copy sitting across the
        image they were trying to click on. The card is the one that stays:
        it can be dismissed, it stacks properly with everything else the
        window has to say, and it does not cover the subject.

        The signal is still connected so that a viewmodel emitting one is not
        an error, and so the last refusal can be read back in a test.
        """
        self._last_notice = notice

    def _show_framing(self, framing) -> None:  # noqa: ANN001 - Framing
        """The verdict in the console, on its own reserved line."""
        self._framing = framing
        self.framing_label.setText(framing.text)
        self.framing_label.setToolTip(framing.text)
        self.framing_label.setProperty(
            "kcStatus",
            {"ok": "live", "tight": "warning", "cut": "error", "crowded": "warning"}.get(
                framing.state, ""
            ),
        )
        _restyle(self.framing_label)
        self.framing_advice.setText(framing.advice)
        self.framing_advice.setToolTip(framing.advice)
        self._refresh_status_details()

    def _refresh_status_details(self) -> None:
        """Collect the full texts, and say whether there are any."""
        rows: list[tuple[str, str]] = []
        for alert in getattr(self, "_alerts", ()):  # noqa: B009 - set in _show_alerts
            rows.append((alert.level.value.upper(), alert.text))
        framing = getattr(self, "_framing", None)
        if framing is not None and framing.advice:
            rows.append(("KADRAJ", framing.advice))
        note = self.pose_note.fullText()
        if note:
            rows.append(("ÖNİZLEME", note))
        self._status_details = rows
        self.status_details_button.setEnabled(bool(rows))
        window = getattr(self, "_status_window", None)
        if window is not None and window.isVisible():
            window.show_rows(rows)

    def _show_pose_note(self, text: str) -> None:
        """One reserved line. Hiding it would give the height back and move
        everything under it, which is the thing this screen must stop doing."""
        self.pose_note.setText(text)
        self.pose_note.setToolTip(text)
        self._refresh_status_details()

    def _show_mode(self, key: str) -> None:
        button = self._mode_buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._show_mode_state()

    def _show_mode_state(self) -> None:
        """Say which mode is in force, which is not the same as which is ticked."""
        viewmodel = self.viewmodel
        if viewmodel is None:
            return
        active = viewmodel.active_mode.value
        pending = viewmodel.mode_pending.value
        if not active:
            text, status = "kamera bağlı değil", "neutral"
        elif pending:
            text, status = "seçildi · etkin değil", "warning"
        else:
            text, status = "etkin", "live"
        self.mode_state.setText(text)
        self.mode_state.setProperty("kcStatus", status)
        style = self.mode_state.style()
        style.unpolish(self.mode_state)
        style.polish(self.mode_state)
        self.apply_mode_button.setVisible(pending)
        self.apply_mode_button.setEnabled(
            pending and not viewmodel.metrics.value.recording
        )

    def _show_target(self, target: WorkTarget) -> None:
        if not target.is_set:
            self.target_value.setText("Seçilmedi")
            self.target_detail.setText(
                "Kayıt hedefi Projeler ekranında seçilir. Seçilmemişse kayda "
                "başlarken bu proje için bir katılımcı hazırlanır."
            )
            return
        self.target_value.setText(target.participant_code)
        if target.session_open:
            self.target_detail.setText(
                f"{target.project_name} · açık oturum {target.session_id}"
            )
        else:
            self.target_detail.setText(
                f"{target.project_name} · kayda başlayınca yeni oturum açılır"
            )

    def _show_countdown(self, seconds: int) -> None:
        self.preview.set_countdown(seconds)
        self.countdown_label.setText(f"{seconds} sn" if seconds else "")
        self.countdown_label.setVisible(bool(seconds))

    def _show_countdown_choice(self, seconds: int) -> None:
        index = self.countdown_box.findData(seconds)
        if index >= 0:
            self.countdown_box.setCurrentIndex(index)

    def _show_duration_choice(self, seconds: int) -> None:
        index = self.duration_box.findData(seconds)
        if index >= 0:
            self.duration_box.setCurrentIndex(index)

    def _show_mirror(self, mirrored: bool) -> None:
        self.preview.set_mirrored(mirrored)
        if self.mirror_box.isChecked() != mirrored:
            self.mirror_box.setChecked(mirrored)

    def _show_guides(self, shown: bool) -> None:
        self.preview.set_guides(shown)
        if self.guides_box.isChecked() != shown:
            self.guides_box.setChecked(shown)

    # --------------------------------------------------------------- actions
    def _mode_chosen(self, key: str, checked: bool) -> None:
        if checked and self.viewmodel is not None:
            self.viewmodel.set_mode(key)

    def _apply_mode(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.apply_mode()

    def _countdown_chosen(self, _index: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_countdown_seconds(self.countdown_box.currentData())

    def _duration_chosen(self, _index: int) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_auto_stop_seconds(self.duration_box.currentData())

    def _mirror_toggled(self, mirrored: bool) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_mirrored(mirrored)

    def _guides_toggled(self, shown: bool) -> None:
        if self.viewmodel is not None:
            self.viewmodel.set_guides(shown)

    def _toggle_connection(self) -> None:
        if self.viewmodel is None:
            return
        if self.viewmodel.service.is_connected:
            self.viewmodel.disconnect()
        else:
            self.viewmodel.connect()

    def _toggle_recording(self) -> None:
        """Start, cancel the countdown, or stop - whichever applies now."""
        if self.viewmodel is not None:
            self.viewmodel.toggle_recording()

    def _add_marker(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.add_marker()

    def _clear_subject(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.clear_subject()

    def _preview_clicked(self, x: float, y: float) -> None:
        if self.viewmodel is not None:
            self.viewmodel.select_subject(x, y)


__all__ = ["CapturePage"]
