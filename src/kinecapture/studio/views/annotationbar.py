"""The contextual editor: one short, wide band, two modes, no scrolling.

The 20 September round put the movement and fault forms here, out of the
right-hand panel, and that part stands: the panel was scrolling by 319 px for
a movement while a band under the timeline sat empty.

What the 21 September review rejected was the *shape* they took here - four
hard vertical sections with a rule between each pair, so a band 1870 px wide
was read as four narrow cards. The "new fault class" box ended up in the
middle of the screen; a single "Eklemleri düzenle" button had a column of its
own that was otherwise empty; and the frame numbers were squeezed into
68-pixel spin boxes whose arrows clipped the digits.

The shape now follows what the work actually is, and it is the same shape in
both modes:

**Two horizontal lines, not four columns.**

* The **class line** comes first, because choosing a class is what this
  editor is mostly for. Creating one is at the far left in both modes, then
  the classes in use as chips, then - only when they do not all fit - one
  button named "Diğer sınıflar" holding the rest.
* The **interval line** carries what is selected, its frame range, and the
  actions that belong to it, left to right in one flow.

**The chips are bounded by measurement, not by a constant.** How many fit is
computed from this band's real width and these class names' real widths, so
six short names and six long ones do not produce the same answer. The strip
never wraps to a second row, never elides a name to fit one more in, and
never grows the band.

**Most recently used first.** A class that was just applied moves to the
front, so the second repetition of an exercise is one press at a known place.
Only an actual choice counts - hovering does not, and opening the picker and
closing it again does not.

**The two vocabularies never mix.** Movement classes and fault classes are
two strips with two histories; nothing crosses.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens, class_colour_token

from . import iconset
from .widgets import ElidedLabel, label, separator

#: A floor under how many class chips the strip offers, whatever the
#: measurement says. Below three the strip stops being a quick selection and
#: becomes a decorated version of the picker.
MIN_VISIBLE_CLASSES = 3

#: A ceiling. Past this the row is a wall of similar buttons that has to be
#: read rather than recognised, and the picker is the better tool.
MAX_VISIBLE_CLASSES = 12

#: Kept for callers that measured against the old fixed capacity. The strip
#: no longer uses a constant: see :meth:`ClassStrip.capacity`.
VISIBLE_CLASSES = 6

#: How wide the "new class" field is. Enough for a realistic Turkish class
#: name without becoming the widest thing on the screen.
NEW_NAME_WIDTH = 220

#: The longest class name drawn on a chip before it is elided. The full name
#: stays in the tooltip and the accessible name, and the picker always shows
#: it whole.
MAX_CHIP_CHARS = 22

#: What the overflow button is called. Named by the user, so it is a constant
#: rather than an f-string somebody can drift.
BROWSE_TEXT = "Diğer sınıflar"

#: Room kept at the end of the class row for the line that says what a draft
#: is still waiting for, and what the number keys do.
HINT_MIN_WIDTH = 84

#: The one label on the band that may give up almost all of its width. It is
#: a secondary note ("Bu harekette hata yok") beside two buttons whose words
#: have to stay readable, and at the narrowest window this screen supports the
#: three of them are competing for the same forty pixels.
NOTE_MIN_WIDTH = 32

#: A floor under the band's left block - the class field over the two frame
#: numbers. The real width is measured from those two rows; this stops a
#: theme with very narrow controls from producing a block too small to name a
#: class in.
LEFT_BLOCK_MIN_WIDTH = 290

#: Floors for the band's informational labels: the least they may be squeezed
#: to before the window is simply too narrow for this screen. What they
#: normally get is their *preferred* width, which is the full sentence - see
#: :class:`BandLabel`.
INFO_MIN_WIDTH = 48
DETAIL_MIN_WIDTH = 64

#: A ceiling on what one of those labels may ask for. Beyond this a long
#: sentence would push the actions off the end of the band rather than elide.
BAND_LABEL_MAX_WIDTH = 260


class FrameSpinBox(QSpinBox):
    """A frame number that is never clipped by its own arrows.

    ``setFixedWidth(68)`` is what the previous round used, and at that width
    Qt gave the arrows their full 16 px and took the remainder off the text -
    so 428 was drawn as "42" with the 8 cut, which is what the 21 September
    screenshots show. Frame numbers are the one thing on this band that must
    never be abbreviated: an interval is *defined* by them.

    The width is therefore measured: the widest value the range can hold, in
    the font the box actually has, plus the arrows and the frame. Re-measured
    on a font or range change, because the theme's stylesheet arrives after
    the widget is built and the range arrives when a version is opened.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self.setKeyboardTracking(False)
        self._reserve()

    #: A floor under the digits reserved. A recording long enough to need six
    #: is unusual; one long enough to need five is not, and a box that fits
    #: the *current* maximum would resize as the interval is dragged.
    MIN_DIGITS = 5

    def _chrome_width(self) -> int:
        """Everything in this box that is not the number, measured.

        Asked of the style for this very widget: the arrows, the frame and
        the text margin are all themed here, so guessing at them is how a box
        ends up 68 px wide with 40 px of digits in 24 px of room. Qt reports
        the edit field's rect inside the control, and the difference between
        that and the control is exactly what the number cannot use.
        """
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        # A generous reference rect, so the answer is the chrome's own width
        # rather than whatever is left at the widget's current size.
        option.rect = QRect(0, 0, 400, max(1, self.height() or 32))
        style = self.style()
        field = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxEditField,
            self,
        )
        chrome = 400 - field.width()
        # A style that declines to answer still must not produce a box with
        # no room for arrows.
        return max(chrome, 28)

    def _reserve(self) -> None:
        digits = max(
            len(str(abs(self.maximum()))),
            len(str(abs(self.minimum()))),
            self.MIN_DIGITS,
        )
        metrics = QFontMetrics(self.font())
        self.setMinimumWidth(
            metrics.horizontalAdvance("8" * digits) + self._chrome_width() + 4
        )

    def setRange(self, low: int, high: int) -> None:  # noqa: N802 - Qt naming
        super().setRange(low, high)
        self._reserve()

    def setMaximum(self, value: int) -> None:  # noqa: N802 - Qt naming
        super().setMaximum(value)
        self._reserve()

    def changeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        super().changeEvent(event)
        self._reserve()


class BandLabel(ElidedLabel):
    """An elided label that asks for its whole sentence and settles for less.

    :class:`ElidedLabel` reports an *ignored* width policy, which is right in
    a column that must not be widened by a long path and wrong in a row with
    a stretch in it: there it collapses to 24 px and prints two characters and
    an ellipsis. Giving it a preferred policy alone does not fix it either,
    because ``QLabel.sizeHint`` measures the text it is currently *showing* -
    which, once elided, is short, so it stays short.

    So the hint is taken from the full text, capped, and the floor is the
    small one above. At the supported size the whole sentence is drawn; on a
    narrower window the label gives width back and elides, which is what it
    was written to do.
    """

    def __init__(self, minimum: int, parent: Optional[QWidget] = None) -> None:
        super().__init__("", parent)
        self._minimum = int(minimum)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(self._minimum)

    def sizeHint(self):  # noqa: N802 - Qt naming
        size = super().sizeHint()
        wanted = QFontMetrics(self.font()).horizontalAdvance(self.fullText())
        size.setWidth(
            max(self._minimum, min(BAND_LABEL_MAX_WIDTH, wanted + 4))
        )
        return size

    def minimumSizeHint(self):  # noqa: N802 - Qt naming
        size = super().minimumSizeHint()
        size.setWidth(self._minimum)
        return size

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        super().setText(text)
        # The sentence changed, so what this label would like to be did too.
        self.updateGeometry()


class ClassCreator(QWidget):
    """The field a new class is named in, and the button that stores it.

    Its own widget because the 22 September layout puts it in the band's
    left-hand block, directly above the interval's frame numbers, while the
    classes to *choose* from stay on the right. Two different questions - what
    exists, and which one is this - so two different places, and creating one
    is in the same place in both the movement and the fault editor.
    """

    def __init__(
        self,
        tokens: ThemeTokens,
        *,
        placeholder: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.metric("KcSpacingSm"))

        self.new_name = QLineEdit(self)
        self.new_name.setPlaceholderText(placeholder)
        self.new_name.setAccessibleName(placeholder)
        # A floor, not a fixed width: the field fills whatever the left block
        # is, and the block is sized from the frame-number row underneath it
        # so the two line up on both edges.
        self.new_name.setMinimumWidth(NEW_NAME_WIDTH)
        self.new_name.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        row.addWidget(self.new_name, 1)

        self.add_button = QPushButton("Ekle", self)
        self.add_button.setProperty("kcVariant", "primary")
        self.add_button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.add_button.setEnabled(False)
        row.addWidget(self.add_button, 0)


class ClassStrip(QWidget):
    """The classes in use, as chips, with the rest one press away.

    One row, always. Not a dropdown: thirty repetitions is thirty choices and
    a dropdown costs an open, a read and a click each time. Not an unbounded
    row either - what does not fit goes behind "Diger siniflar", so a project
    with forty classes does not turn this band into a scrolling list or a
    second row of buttons.

    Creating a class is :class:`ClassCreator`, which this object builds and
    owns but does not lay out: the band puts it in the left block. The signals
    and the ``new_name`` / ``add_button`` attributes stay here, so everything
    that drives a class strip still has one place to talk to.
    """

    chosen = Signal(str)
    create_requested = Signal(str)
    browse_requested = Signal()
    draft_changed = Signal(str)

    def __init__(
        self,
        tokens: ThemeTokens,
        *,
        placeholder: str,
        fault: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._fault = fault
        self._options: tuple[tuple[str, str], ...] = ()
        self._selected = ""
        self._buttons: dict[str, QToolButton] = {}
        self._add_gate = True
        #: Codes newest-first. The strip's own memory of what has been
        #: applied, kept per strip so movement and fault histories never mix.
        self._recent: list[str] = []
        self._laying_out = False

        # Built here, placed by the band. Parented to the same parent so it
        # stands on its own once a layout takes it.
        self.creator = ClassCreator(tokens, placeholder=placeholder, parent=parent)
        self.new_name = self.creator.new_name
        self.add_button = self.creator.add_button
        self.new_name.textChanged.connect(self._name_typed)
        self.new_name.returnPressed.connect(self._create)
        self.add_button.clicked.connect(self._create)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.metric("KcSpacingMd"))

        # The classes in use. A plain container laid out by hand rather than a
        # flow layout, because the whole point is that it is one row and the
        # count is decided before anything is placed.
        self._holder = QWidget(self)
        self._holder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._chips = QHBoxLayout(self._holder)
        self._chips.setContentsMargins(0, 0, 0, 0)
        self._chips.setSpacing(tokens.metric("KcSpacingSm"))
        self._chips.addStretch(1)
        row.addWidget(self._holder, 1)

        # The ruler: one chip, never shown, used to ask the style what a chip
        # of a given name would really cost. Built exactly like the visible
        # ones so the answer is about them and not about a bare QToolButton.
        self._ruler = QToolButton(self)
        self._ruler.setProperty("kcRole", "classChip")
        self._ruler.setCheckable(True)
        self._ruler.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._ruler.setIcon(
            iconset.icon("circle", tokens, size=tokens.metric("KcIconSize"))
        )
        self._ruler.setIconSize(QSize(*([tokens.metric("KcIconSize")] * 2)))
        self._ruler.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self._ruler.setAccessibleName("Sinif olcum yardimcisi")
        self._ruler.setToolTip("Yalniz olcum icindir; bir sinifi temsil etmez.")
        # Never interactive, and never counted as a control: it exists to be
        # asked how wide a chip would be.
        self._ruler.setEnabled(False)
        self._ruler.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._ruler.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._ruler.hide()

        # Everything that did not fit, by the name the user gave it.
        self.browse_button = QPushButton(BROWSE_TEXT)
        self.browse_button.setAccessibleName(BROWSE_TEXT)
        self.browse_button.setToolTip(
            "Banda sigmayan siniflar. Aramali listede hepsine ulasilir."
        )
        self.browse_button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self.browse_button.clicked.connect(self.browse_requested.emit)
        self.browse_button.hide()
        row.addWidget(self.browse_button, 0)

        # Room kept for the hint, and kept *by the layout*. An ``ElidedLabel``
        # asks for an ignored width, and a layout that is ignoring a widget's
        # width does not count its minimum either - measured: the chips took
        # the whole row and this label was placed at x=1856 in a strip 1856
        # wide, which is to say off the end of the band. This line is where a
        # fault class says it is still waiting for a joint, and a message
        # nobody can see is not a message, so it gets a real policy.
        self.hint = BandLabel(HINT_MIN_WIDTH, self)
        self.hint.setProperty("kcRole", "pageSubtitle")
        row.addWidget(self.hint, 0)

    # ----------------------------------------------------------------- state
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._rebuild()

    def set_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._options = tuple(options)
        known = {code for code, _text in self._options}
        # A class that no longer exists must not hold a place in the history.
        self._recent = [code for code in self._recent if code in known]
        self._rebuild()

    def set_selected(self, code: str) -> None:
        """Show which class this interval carries. **Not** a use.

        Called whenever a movement or a fault is opened, which is not the
        annotator choosing anything - so it never reorders the strip. If it
        did, simply clicking along the timeline would shuffle the chips.
        """
        if code == self._selected:
            return
        self._selected = code
        self._rebuild()

    def note_used(self, code: str) -> None:
        """Record that ``code`` was actually applied, and move it to the front.

        The one way the order changes. Called from :meth:`_choose` and by the
        owner when a class arrives from the picker or has just been created -
        the user asked for a class chosen in "Diğer sınıflar" to be the first
        chip once the picker closes.
        """
        if not code or all(key != code for key, _text in self._options):
            return
        if self._recent[:1] == [code]:
            return
        self._recent = [code] + [key for key in self._recent if key != code]
        self._rebuild()

    @property
    def recent(self) -> tuple[str, ...]:
        """The history, newest first. For a measurement to read."""
        return tuple(self._recent)

    @property
    def selected(self) -> str:
        return self._selected

    @property
    def ordered(self) -> tuple[tuple[str, str], ...]:
        """Every class, most recently used first, then the vocabulary's order."""
        by_code = {code: (code, text) for code, text in self._options}
        head = [by_code[code] for code in self._recent if code in by_code]
        seen = {code for code, _text in head}
        return tuple(head + [pair for pair in self._options if pair[0] not in seen])

    @property
    def visible_codes(self) -> tuple[str, ...]:
        """Which classes have a chip right now, left to right."""
        return tuple(self._buttons)

    @property
    def hidden_count(self) -> int:
        """How many classes are behind the picker rather than on the band."""
        return max(0, len(self._options) - len(self._buttons))

    def set_add_enabled(self, enabled: bool) -> None:
        """An owner-imposed gate: a fault class also needs a joint."""
        self._add_gate = bool(enabled)
        self._name_typed(self.new_name.text())

    def typed_name(self) -> str:
        return " ".join(self.new_name.text().split())

    def clear_new_name(self) -> None:
        self.new_name.clear()

    def set_hint(self, text: str, *, warning: bool = False) -> None:
        self.hint.setText(text)
        self.hint.setToolTip(text)
        self.hint.setProperty("kcStatus", "warning" if warning else None)
        style = self.hint.style()
        if style is not None:
            style.unpolish(self.hint)
            style.polish(self.hint)

    # ----------------------------------------------------------------- build
    def _chip_text(self, text: str) -> str:
        """A name short enough to recognise without reading a paragraph."""
        clean = " ".join(str(text).split())
        if len(clean) <= MAX_CHIP_CHARS:
            return clean
        return clean[: MAX_CHIP_CHARS - 1].rstrip() + "…"

    def _chip_width(self, text: str) -> int:
        """What a chip for ``text`` would take. **Asked, not estimated.**

        A real ``QToolButton`` with the same style property, the same icon
        size and the same text, reporting its own ``sizeHint``. The estimate
        this replaced was a font measurement plus guessed padding, and it came
        out short: eight chips were placed in room for six and a half, so Qt
        shrank them to their minimum and each one elided its own name in the
        middle - "lateral...ayması...", which is exactly the squeezing the
        21 September review objects to.
        """
        button = self._ruler
        button.setText(self._chip_text(text))
        button.ensurePolished()
        return button.sizeHint().width()

    def _fit(self, options, available: int) -> int:
        """How many of ``options`` fit in ``available`` pixels, in order.

        Never more than fits: squeezing one extra name in is what makes a
        chip elide in the middle, which the user asked to stop.

        :data:`MIN_VISIBLE_CLASSES` is a floor under the answer, and it earns
        its keep in the degenerate case rather than the normal one. A strip
        that has been laid out on the target screen has room for seven or
        more; a strip Qt has not laid out yet reports its default 640 px, and
        from that the honest answer is "one", which would leave a real
        two-class project showing one button. At the size this screen is
        actually used the floor never binds.
        """
        spacing = self._chips.spacing()
        used = 0
        count = 0
        for _code, text in options:
            wanted = self._chip_width(text) + (spacing if count else 0)
            if count >= MAX_VISIBLE_CLASSES or (
                count >= MIN_VISIBLE_CLASSES and used + wanted > available
            ):
                break
            used += wanted
            count += 1
        return min(count, len(options))

    def capacity(self) -> int:
        """How many chips this band can hold, from its real width right now.

        Measured rather than declared. Six was a constant that suited six
        short names; with "Öne eğilme kompanzasyonu" three times over it
        produced a second row and the band grew into the timeline.

        The sum is taken from the **strip's** width rather than the chip
        holder's, because the holder's width is a *result* of the last answer
        this method gave: reading it back and subtracting the same fixed
        things again shrank the count on every pass.

        The overflow button is the one thing whose presence depends on the
        answer, so the sum is taken twice: once assuming everything fits, and
        - only if it did not - again with room kept for "Diğer sınıflar". That
        way the button can never be what pushes the last chip off the row, and
        its width is not reserved when there is nothing to hide behind it.
        """
        options = self.ordered
        if not options:
            return 0
        gap = self._tokens.metric("KcSpacingMd")
        # The strip *is* the chooser now: the name field and Ekle live in the
        # band's left block, not in this row. What shares the row with the
        # chips is the hint line and, when there is an overflow, the button
        # for it - and both are subtracted before anything is counted.
        available = self.width() - HINT_MIN_WIDTH - gap * 2
        if available <= 0:
            # The strip has not been given a real width yet - it is being
            # built, or it is off screen. There is nothing honest to measure
            # against, so show the floor and count again on the first resize;
            # answering "one" here would leave a strip that was never laid
            # out showing a single chip for good.
            return min(MIN_VISIBLE_CLASSES, len(options))
        count = self._fit(options, available)
        if count >= len(options):
            return count
        return self._fit(
            options, available - self.browse_button.sizeHint().width() - gap
        )

    def _shown(self) -> tuple[tuple[str, str], ...]:
        """Which classes get a chip.

        The selected one is always among them: a class applied to this
        interval that was not on the band would look like no class at all.
        """
        options = list(self.ordered)
        head = options[: self.capacity()]
        if self._selected and all(code != self._selected for code, _t in head):
            chosen = next(
                (pair for pair in options if pair[0] == self._selected), None
            )
            if chosen is not None:
                head = [chosen] + head[: max(0, len(head) - 1)]
        return tuple(head)

    def _rebuild(self) -> None:
        while self._chips.count() > 1:
            item = self._chips.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                # Hidden *before* it is unparented. A visible widget whose
                # parent becomes ``None`` is a top-level window, and Qt shows
                # it: a class chip appeared on the labelling screen as a small
                # floating window with its own title bar, and stayed there
                # until ``deleteLater`` got round to it.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._buttons.clear()
        for position, (code, text) in enumerate(self._shown()):
            button = QToolButton(self._holder)
            button.setText(self._chip_text(text))
            button.setCheckable(True)
            button.setChecked(code == self._selected)
            button.setAutoRaise(False)
            button.setProperty("kcRole", "classChip")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # The full name is always reachable, however short the chip is.
            button.setAccessibleName(text)
            button.setToolTip(text)
            button.setMinimumHeight(self._tokens.metric("KcControlHeightLarge"))
            # Never narrower than the name it carries. Without this the row's
            # layout is free to shrink a chip to its minimum when the sum is
            # tight, and a shrunk QToolButton elides its own text in the
            # middle rather than refusing - which is how a class name became
            # "lateral...ayması...".
            button.clicked.connect(
                lambda _checked=False, key=code: self._choose(key)
            )
            # The class's own colour, the same one the timeline paints it in.
            # Taken from the *vocabulary's* position, not the chip's, so a
            # class keeps its colour when the history reorders the row.
            index = next(
                (i for i, (key, _t) in enumerate(self._options) if key == code), -1
            )
            if index >= 0:
                button.setIcon(
                    iconset.icon(
                        "circle",
                        self._tokens,
                        colour_token=class_colour_token(index, fault=self._fault),
                        size=self._tokens.metric("KcIconSize"),
                    )
                )
                button.setIconSize(QSize(*([self._tokens.metric("KcIconSize")] * 2)))
            button.ensurePolished()
            button.setMinimumWidth(button.sizeHint().width())
            self._chips.insertWidget(position, button)
            self._buttons[code] = button
        hidden = self.hidden_count
        self.browse_button.setVisible(hidden > 0)
        if hidden:
            self.browse_button.setText(BROWSE_TEXT)
            self.browse_button.setToolTip(
                f"Banda sığmayan {hidden} sınıf. Aramalı listede hepsine ulaşılır."
            )

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        """Re-count the chips for the width the band actually got.

        Guarded: rebuilding changes the holder's contents, which can produce
        another resize, and two of those in a row is a loop.
        """
        super().resizeEvent(event)
        if self._laying_out:
            return
        self._laying_out = True
        try:
            if len(self._buttons) != len(self._shown()):
                self._rebuild()
        finally:
            self._laying_out = False

    # --------------------------------------------------------------- actions
    def _choose(self, code: str) -> None:
        """A class was applied. Tell the owner first, then reorder.

        Order matters. ``note_used`` deletes and rebuilds the chips, and the
        button that was clicked is one of them; emitting afterwards would be
        emitting from a widget that has just been scheduled for deletion.
        The class the owner receives is therefore always the one under the
        pointer, never whatever moved into that place.
        """
        self._selected = code
        self.chosen.emit(code)
        self.note_used(code)

    def _name_typed(self, text: str) -> None:
        self.add_button.setEnabled(bool(text.strip()) and self._add_gate)
        self.draft_changed.emit(text)

    def _create(self) -> None:
        if self.add_button.isEnabled():
            self.create_requested.emit(self.typed_name())


class AnnotationEditorBar(QWidget):
    """The band itself: the movement editor and the fault editor."""

    #: Which editor is showing: "movement" or "fault". There is no third
    #: state any more - the band opens on the movement editor.
    mode_changed = Signal(str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setProperty("kcSurface", "stage")
        outer = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingMd")
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(0)

        self.modes = QStackedWidget(self)
        self.modes.addWidget(self._build_movement())
        self.modes.addWidget(self._build_fault())
        outer.addWidget(self.modes)
        # Movement, from the first frame the screen is on. The 21 September
        # review is explicit: opening Etiketleme must not show an empty band
        # with one sentence in it. With nothing selected the interval line's
        # controls are disabled and say why, but the classes are there and
        # the shape of the editor is visible.
        self._mode = "movement"
        self.modes.setCurrentIndex(0)

        # Kept so callers written against the old empty state still resolve.
        # Nothing shows them.
        self.empty_note = ElidedLabel("", self)
        self.empty_note.hide()
        self.empty_next_button = QPushButton("Sonraki eksik", self)
        self.empty_next_button.hide()

    # ---------------------------------------------------------------- pieces
    def _line(self) -> QHBoxLayout:
        """One horizontal line of the band.

        Medium spacing rather than large: a line carries about a dozen items,
        so four extra pixels between each pair is fifty pixels of the band -
        and at the narrowest window this screen supports that is the
        difference between "Sınıfsızlara uygula" being readable and being
        clipped. The grouping is carried by the rules and by which things sit
        next to which, not by the size of the gaps.
        """
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self._tokens.metric("KcSpacingMd"))
        return row

    def _grid(self, page: QWidget) -> QGridLayout:
        """The band's two rows and three columns.

            col 0            col 1   col 2
            creator          rule    the classes in use
            frame numbers    rule    what is selected, and what to do with it

        A grid rather than two independent rows, because the 22 September
        request is about *alignment*: the frame numbers sit under the field a
        class is named in, sharing its left and right edges, and a row has one
        height across the whole band. Stacked layouts can approximate that; a
        grid is it by construction.
        """
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(self._tokens.metric("KcSpacingMd"))
        grid.setVerticalSpacing(self._tokens.metric("KcSpacingMd"))
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        return grid

    def _left_block(
        self, grid: QGridLayout, creator: QWidget, ranges: QWidget, page: QWidget
    ) -> None:
        """Put the creator over the frame numbers, both at one width.

        The width is the wider of the two rows and is taken *after* they are
        built, because the frame boxes measure themselves from the style and
        the name field only has a floor. Fixing it on both is what makes the
        block a block: one left edge, one right edge, two rows.
        """
        for widget in (creator, ranges):
            widget.setParent(page)
        creator.adjustSize()
        ranges.adjustSize()
        width = max(
            creator.sizeHint().width(),
            ranges.sizeHint().width(),
            LEFT_BLOCK_MIN_WIDTH,
        )
        creator.setFixedWidth(width)
        ranges.setFixedWidth(width)
        grid.addWidget(creator, 0, 0)
        grid.addWidget(ranges, 1, 0)
        rule = separator(Qt.Orientation.Vertical)
        rule.setParent(page)
        grid.addWidget(rule, 0, 1, 2, 1)

    def _ranges(self, page: QWidget, first: QSpinBox, second: QSpinBox) -> QWidget:
        """The two frame numbers on one row, filling the left block.

        The captions keep their natural width and the boxes share what is
        left in equal parts, so the row ends exactly where the field above it
        ends however wide the block turns out to be.
        """
        tokens = self._tokens
        holder = QWidget(page)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.metric("KcSpacingSm"))
        row.addWidget(label("Başlangıç"), 0)
        row.addWidget(first, 1)
        row.addSpacing(tokens.metric("KcSpacingMd"))
        row.addWidget(label("Bitiş"), 0)
        row.addWidget(second, 1)
        return holder

    def _context(self, title: str, context: str, parent: QWidget) -> QWidget:
        """The "what is selected" block: a caption over one line of detail."""
        holder = QWidget(parent)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        caption = label(title, role="sectionTitle")
        caption.setProperty("kcContext", context)
        column.addWidget(caption)
        return holder

    # ------------------------------------------------------------- the modes
    def _build_movement(self) -> QWidget:
        tokens = self._tokens
        page = QWidget()
        grid = self._grid(page)

        self.exercise_classes = ClassStrip(
            tokens, placeholder="Yeni hareket sınıfı", parent=page
        )
        self.exercise_classes.set_hint("1-9 tuşları ilk dokuz sınıfı atar.")

        self.movement_start = FrameSpinBox()
        self.movement_start.setAccessibleName("Hareket başlangıç karesi")
        self.movement_start.setToolTip("Değiştirirken görüntü o kareye gider")
        self.movement_end = FrameSpinBox()
        self.movement_end.setAccessibleName("Hareket bitiş karesi")
        self._left_block(
            grid,
            self.exercise_classes.creator,
            self._ranges(page, self.movement_start, self.movement_end),
            page,
        )

        # ---- right, row 0: the classes in use.
        grid.addWidget(self.exercise_classes, 0, 2)

        # ---- right, row 1: what is selected and what can be done to it.
        interval = self._line()
        which = self._context("SEÇİLİ HAREKET", "movement", page)
        self.movement_title = BandLabel(DETAIL_MIN_WIDTH, page)
        self.movement_title.setProperty("kcRole", "contextValue")
        which.layout().addWidget(self.movement_title)
        interval.addWidget(which, 0)

        self.movement_state = BandLabel(DETAIL_MIN_WIDTH, page)
        self.movement_state.setProperty("kcRole", "pageSubtitle")
        interval.addWidget(self.movement_state, 0)

        interval.addWidget(separator(Qt.Orientation.Vertical))

        self.exclude_box = QCheckBox("Veri setinin dışında tut")
        self.exclude_box.setToolTip("Kayıt silinmez; yalnızca dışa aktarıma girmez.")
        interval.addWidget(self.exclude_box, 0)

        self.movement_faults = BandLabel(NOTE_MIN_WIDTH, page)
        self.movement_faults.setProperty("kcRole", "pageSubtitle")
        interval.addWidget(self.movement_faults, 0)

        interval.addStretch(1)

        self.add_error_button = QPushButton("Hata aralığı ekle")
        self.add_error_button.setToolTip(
            "Oynatma çizgisinin çevresine bir hata aralığı koyar"
        )
        self.apply_all_button = QPushButton("Sınıfsızlara uygula")
        self.apply_all_button.setToolTip(
            "Bu sınıfı henüz sınıfı olmayan bütün hareketlere ver. "
            "Sınıfı olanlar değişmez."
        )
        self.delete_movement_button = QToolButton()
        self.delete_movement_button.setAccessibleName("Hareketi sil")
        self.delete_movement_button.setToolTip("Hareketi sil")
        self.delete_movement_button.setIcon(
            iconset.icon("delete", tokens, size=tokens.metric("KcIconSize"))
        )
        for button in (
            self.add_error_button,
            self.apply_all_button,
            self.delete_movement_button,
        ):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            interval.addWidget(button, 0)
        grid.addLayout(interval, 1, 2)

        self._movement_controls = (
            self.movement_start,
            self.movement_end,
            self.exclude_box,
            self.add_error_button,
            self.delete_movement_button,
        )
        return page

    def _build_fault(self) -> QWidget:
        tokens = self._tokens
        page = QWidget()
        grid = self._grid(page)

        self.error_classes = ClassStrip(
            tokens, placeholder="Yeni hata sınıfı", fault=True, parent=page
        )

        self.error_start = FrameSpinBox()
        self.error_start.setAccessibleName("Hata aralığı başlangıç karesi")
        self.error_end = FrameSpinBox()
        self.error_end.setAccessibleName("Hata aralığı bitiş karesi")
        # Deliberately the same block in the same place as the movement
        # editor's: the two modes share one shape, so moving between them does
        # not move anything the hand is already reaching for.
        self._left_block(
            grid,
            self.error_classes.creator,
            self._ranges(page, self.error_start, self.error_end),
            page,
        )

        grid.addWidget(self.error_classes, 0, 2)

        interval = self._line()
        which = self._context("SEÇİLİ HATA", "fault", page)
        self.error_title = BandLabel(DETAIL_MIN_WIDTH, page)
        self.error_title.setProperty("kcRole", "contextValue")
        which.layout().addWidget(self.error_title)
        interval.addWidget(which, 0)

        self.error_parent = BandLabel(INFO_MIN_WIDTH, page)
        self.error_parent.setProperty("kcRole", "pageSubtitle")
        interval.addWidget(self.error_parent, 0)

        interval.addWidget(separator(Qt.Orientation.Vertical))

        # The joints: a summary and one button, in the flow. They used to have
        # a column of their own roughly 900 px wide, holding one button and a
        # line saying "Eklem seçilmedi".
        self.joint_summary = BandLabel(DETAIL_MIN_WIDTH, page)
        self.joint_summary.setText("Eklem seçilmedi")
        self.joint_summary.setProperty("kcRole", "contextValue")
        self.joint_summary.setToolTip("Bu aralık için işaretlenen eklemler")
        interval.addWidget(self.joint_summary, 0)
        self.joint_origin = BandLabel(INFO_MIN_WIDTH, page)
        self.joint_origin.setProperty("kcRole", "pageSubtitle")
        interval.addWidget(self.joint_origin, 0)
        self.edit_joints_button = QPushButton("Eklemleri düzenle")
        self.edit_joints_button.setToolTip(
            "Yalnız bu aralık için eklem kanıtını değiştirir; sınıfın "
            "varsayılanı olduğu gibi kalır."
        )
        interval.addWidget(self.edit_joints_button, 0)

        interval.addStretch(1)

        self.back_to_movement_button = QPushButton("Harekete dön")
        self.error_note_button = QPushButton("Not…")
        self.error_note_button.setToolTip("Bu aralığın notunu ayrı pencerede aç")
        self.delete_error_button = QToolButton()
        self.delete_error_button.setAccessibleName("Hatayı sil")
        self.delete_error_button.setToolTip("Hatayı sil")
        self.delete_error_button.setIcon(
            iconset.icon("delete", tokens, size=tokens.metric("KcIconSize"))
        )
        for button in (
            self.edit_joints_button,
            self.back_to_movement_button,
            self.error_note_button,
            self.delete_error_button,
        ):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        for button in (
            self.back_to_movement_button,
            self.error_note_button,
            self.delete_error_button,
        ):
            interval.addWidget(button, 0)
        grid.addLayout(interval, 1, 2)
        return page

    # ----------------------------------------------------------------- state
    def show_mode(self, mode: str) -> None:
        """Open one of the two. Nothing else decides which.

        ``""`` is accepted and means the movement editor with nothing
        selected, which is what the band shows when the screen opens and when
        a selection is dropped. It is not a third page: the same controls are
        on screen, disabled, so the editor never disappears out from under
        somebody who was about to use it.
        """
        resolved = mode if mode in ("movement", "fault") else "movement"
        index = 0 if resolved == "movement" else 1
        if self.modes.currentIndex() == index and self._mode == mode:
            return
        self._mode = mode
        self.modes.setCurrentIndex(index)
        self.mode_changed.emit(mode)

    def set_movement_enabled(self, enabled: bool) -> None:
        """Whether a movement is selected, as the controls' own state.

        With nothing selected the class chips stay live - choosing one before
        drawing an interval is a reasonable order to work in and the strip is
        also how a class is created - while everything that edits *an
        interval* is off, because there is no interval.
        """
        for control in self._movement_controls:
            control.setEnabled(enabled)

    @property
    def mode(self) -> str:
        return self._mode

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.exercise_classes.set_tokens(tokens)
        self.error_classes.set_tokens(tokens)


__all__ = [
    "BROWSE_TEXT",
    "DETAIL_MIN_WIDTH",
    "HINT_MIN_WIDTH",
    "INFO_MIN_WIDTH",
    "LEFT_BLOCK_MIN_WIDTH",
    "MAX_VISIBLE_CLASSES",
    "NOTE_MIN_WIDTH",
    "MIN_VISIBLE_CLASSES",
    "NEW_NAME_WIDTH",
    "VISIBLE_CLASSES",
    "AnnotationEditorBar",
    "BandLabel",
    "ClassCreator",
    "ClassStrip",
    "FrameSpinBox",
]
