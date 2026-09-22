"""Messages that float over the work instead of pushing it around.

The 15 September audit watched a notification insert a container into the page
and squeeze the video, the 3-D view and the timeline: every splitter ratio
changed, and the control under the pointer moved. A message is not worth that.

So a message is drawn in a layer *on top of* the page. The layer has no place
in any layout, so the main rectangles keep their geometry to the pixel whether
a message is showing or not - which is the property
``tests/test_studio_toasts.py`` measures.

The other rules the audit asked for, all of them here:

* a short, compact card in a safe corner - never a full-width coloured block;
* information disappears by itself, quietly; anything the user has to act on
  does not;
* hovering keeps a message alive, so it cannot vanish mid-sentence;
* the same event twice updates one card and counts it, instead of stacking;
* a continuous state (recording, a running job, unsaved labels) is *not* a
  toast - those live in the fixed strip in the context bar.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from kinecapture.studio.services.messages import Message, Severity
from kinecapture.studio.theme import ThemeTokens

from .widgets import MessageBar, _restyle

#: How long an informational message stays. Long enough to read a sentence,
#: short enough that it is gone before it is in the way.
INFO_LIFETIME_MS = 6000

#: Warnings linger noticeably longer; errors do not go away at all.
WARNING_LIFETIME_MS = 12000

#: More than this and the corner becomes a wall. The oldest goes first.
MAX_TOASTS = 4

#: Opening and closing motion. Short and unshowy on purpose: this must not
#: pull the eye away from the frame the user is looking at.
FADE_MS = 120


class Toast(MessageBar):
    """One message card: the message bar, with a life of its own."""

    def __init__(
        self, tokens: ThemeTokens, key: str, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(tokens, parent)
        self.key = key
        self._count = 1
        self._hovered = False
        self._lifetime = 0
        self._fading = False

        # Sits beside the headline; empty until the same thing happens twice.
        self._count_label = QLabel(self)
        self._count_label.setProperty("kcStatus", "neutral")
        self._count_label.hide()
        row = self.layout().itemAt(0)
        if isinstance(row, QHBoxLayout):
            row.insertWidget(2, self._count_label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def preferred_width(self) -> int:
        """The width at which this card's buttons stop needing a second row.

        Not a demand: :class:`ToastLayer` clamps it to what the window has.
        Asked so that a card with three actions is a little wider rather than
        two rows tall, which is easier to read and easier to aim at.
        """
        row = self.layout().itemAt(self.layout().count() - 1)
        buttons = [
            row.itemAt(i).widget()
            for i in range(row.count())
            if row.itemAt(i).widget() is not None
        ]
        visible = [b for b in buttons if not b.isHidden()]
        if not visible:
            return 0
        spacing = row.spacing() if hasattr(row, "spacing") else 6
        margins = self.layout().contentsMargins()
        return (
            sum(max(b.minimumWidth(), b.sizeHint().width()) for b in visible)
            + spacing * (len(visible) - 1)
            + margins.left()
            + margins.right()
            # A couple of pixels of slack. Asking for exactly the width the
            # row needs leaves the flow one rounding error away from wrapping,
            # and a wrapped row is a card twice as tall for no reason.
            + 4
        )

    # --------------------------------------------------------------- content
    def present(self, message: Message, *, repeated: bool = False) -> None:
        self.show_message(message)
        if repeated:
            self._count += 1
            self._count_label.setText(f"×{self._count}")
            self._count_label.show()
            _restyle(self._count_label)
        self._lifetime = _lifetime_for(message.severity)
        self._restart()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _restart(self) -> None:
        self._timer.stop()
        if self._lifetime and not self._hovered:
            self._timer.start(self._lifetime)

    @property
    def is_persistent(self) -> bool:
        """True when this message waits for a person rather than a clock."""
        return self._lifetime == 0

    @property
    def count(self) -> int:
        return self._count

    # ---------------------------------------------------------------- events
    def enterEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self._hovered = True
        self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self._hovered = False
        self._restart()
        super().leaveEvent(event)

    def dismiss(self) -> None:
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        if not self._fading:
            self._fading = True
            self._fade.finished.connect(self._finish_dismiss)
        self._fade.start()

    def _finish_dismiss(self) -> None:
        if self._fading:
            self._fading = False
            try:
                self._fade.finished.disconnect(self._finish_dismiss)
            except (RuntimeError, TypeError):  # pragma: no cover - already gone
                pass
        layer = self.parent()
        if isinstance(layer, ToastLayer):
            layer.remove(self)
        else:  # pragma: no cover - a toast always has a layer
            self.hide()

    def clear(self) -> None:
        """"Kapat" on the card.

        Immediate, not faded: the user asked for it gone, and watching it
        linger for a tenth of a second reads as the click not registering.
        """
        super().clear()
        self._timer.stop()
        self._fade.stop()
        self._finish_dismiss()


def _lifetime_for(severity: Severity) -> int:
    if severity is Severity.ERROR:
        # Something needs a decision. It waits for one.
        return 0
    if severity is Severity.WARNING:
        return WARNING_LIFETIME_MS
    return INFO_LIFETIME_MS


class ToastLayer(QWidget):
    """The transparent layer messages are drawn on.

    Has no place in a layout and is positioned by hand over its host, which is
    what keeps the page underneath exactly the size it was.
    """

    #: The key of an action pressed on one of the cards.
    action_triggered = Signal(str)

    def __init__(self, tokens: ThemeTokens, host: QWidget) -> None:
        super().__init__(host)
        self._tokens = tokens
        self._host = host
        #: Pixels to keep clear along the bottom of the host. A page with an
        #: action bar pinned there sets this, because a message that covers
        #: "Kaydet" is worse than no message at all.
        self._bottom_reserve = 0
        self._toasts: list[Toast] = []
        self._laying_out = False
        # NOT transparent for mouse events: that attribute takes the whole
        # subtree out of hit-testing, which left "Ayrıntılar" and "Kapat"
        # painted but dead. Instead the layer is only ever as big as the cards
        # it holds, so everywhere else the page underneath is what gets
        # clicked - the same result, without disabling the buttons.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        host.installEventFilter(self)
        self.hide()

    # ---------------------------------------------------------------- tokens
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        for toast in self._toasts:
            toast.set_tokens(tokens)

    # --------------------------------------------------------------- content
    def show_message(self, message: Message) -> Toast:
        """Show one message, folding a repeat into the card already there."""
        key = message.code or message.headline
        existing = next((t for t in self._toasts if t.key == key), None)
        if existing is not None:
            existing.present(message, repeated=True)
            self._relayout()
            return existing

        toast = Toast(self._tokens, key, self)
        toast.setFixedWidth(self._card_width())
        toast.action_triggered.connect(self._action)
        # A card that grows - because its actions wrapped onto a second line -
        # has to be measured again. Without this the extra line was drawn
        # outside the rectangle the layer had given it, which is how a
        # sentence arrived on screen cut off halfway through a word.
        toast.resized.connect(self._relayout)
        self._toasts.append(toast)
        while len(self._toasts) > MAX_TOASTS:
            self._toasts.pop(0).setParent(None)
        toast.present(message)
        self.show()
        self.raise_()
        self._relayout()
        return toast

    def _action(self, key: str) -> None:
        """A message's action was taken, so the message has done its job."""
        sender = self.sender()
        if isinstance(sender, Toast):
            sender.clear()
        self.action_triggered.emit(key)

    def remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.setParent(None)
        toast.deleteLater()
        if not self._toasts:
            self.hide()
        else:
            self._relayout()

    def clear(self) -> None:
        for toast in list(self._toasts):
            self.remove(toast)

    @property
    def toasts(self) -> tuple[Toast, ...]:
        return tuple(self._toasts)

    @property
    def current(self) -> Optional[Message]:
        """The newest message on screen, for anything that needs just one."""
        return self._toasts[-1].current if self._toasts else None

    # -------------------------------------------------------------- geometry
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._host and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            self._resize_to_host()
        return False

    def set_bottom_reserve(self, pixels: int) -> None:
        """Say how much of the host's bottom edge belongs to the page."""
        pixels = max(0, int(pixels))
        if pixels == self._bottom_reserve:
            return
        self._bottom_reserve = pixels
        self._relayout()

    def _card_width(self) -> int:
        """How wide a card is, and why it is not simply the token.

        The token is a *starting* width. A card carrying several actions can
        need more than that before its buttons start clipping, and a host too
        narrow to hold even the token needs less. Between those, the cards all
        share one width, because a corner of cards at four different widths
        reads as four different things.
        """
        wanted = self._tokens.metric("KcToastWidth")
        for toast in self._toasts:
            wanted = max(wanted, toast.preferred_width())
        room = self._host.width() - 2 * self._tokens.metric("KcSpacingXl")
        return max(240, min(wanted, room if room > 0 else wanted))

    def _resize_to_host(self) -> None:
        self._relayout()

    def _relayout(self) -> None:
        """Stack the cards in the bottom-right corner, newest lowest.

        Re-entrant calls are ignored. A card emits ``resized`` while it is
        being filled, which arrives in the middle of this - and measuring a
        card whose width has not been set yet returned the height it would
        need if its buttons wrapped onto three rows. That number then became
        the card's height, and the card was twice as tall as its content.

        Not the top-right: that is where every screen keeps its action
        buttons, and a message there covered "Etiketle" and "Yeni sürüm
        hesapla". The bottom-right is table background on most screens and
        the far end of the timeline on the labelling screen, so a message
        never sits on the video, the inspector or a control.
        """
        if self._laying_out:
            return
        if not self._toasts:
            self.hide()
            return
        self._laying_out = True
        try:
            self._lay_out_cards()
        finally:
            self._laying_out = False

    def _lay_out_cards(self) -> None:
        margin = self._tokens.metric("KcSpacingXl")
        gap = self._tokens.metric("KcSpacingMd")
        width = self._card_width()

        # Width first, for every card, then heights. Asking one card for its
        # height while another still has last pass's width is how a card
        # measured itself as three rows of buttons tall.
        for toast in self._toasts:
            toast.setFixedWidth(width)
            layout = toast.layout()
            if layout is not None:
                layout.invalidate()
                layout.activate()

        heights: list[int] = []
        for toast in self._toasts:
            layout = toast.layout()
            # The *layout's* hint, not the widget's. A widget caches its own
            # size hint and hands back the cached one; a card that had once
            # been measured while its buttons wrapped onto three rows kept
            # reporting that height afterwards, and was drawn twice as tall
            # as anything in it.
            hint = (
                layout.sizeHint().height()
                if layout is not None
                else toast.sizeHint().height()
            )
            heights.append(
                max(
                    toast.heightForWidth(width) if toast.hasHeightForWidth() else 0,
                    hint,
                    toast.minimumSizeHint().height(),
                )
            )
        total = sum(heights) + gap * (len(heights) - 1)

        host = self._host.rect()
        self.setGeometry(
            max(0, host.width() - width - margin),
            max(0, host.height() - total - margin - self._bottom_reserve),
            width,
            total,
        )
        # Newest lowest, so a burst reads top-to-bottom in arrival order.
        y = 0
        for toast, height in zip(self._toasts, heights):
            toast.setGeometry(0, y, width, height)
            toast.show()
            toast.raise_()
            y += height + gap


__all__ = ["INFO_LIFETIME_MS", "MAX_TOASTS", "WARNING_LIFETIME_MS", "Toast", "ToastLayer"]
