"""What every Studio page has in common.

A page owns a title strip, a message bar and a body. It does **not** own
application state: it is handed a viewmodel and binds to it. Anything a page
computes for itself is state the next front end would have to recompute.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from kinecapture.studio.services.messages import Message
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination

from ..qt_bridge import BoundView
from ..widgets import ElidedLabel, MessageBar, label


class StudioPage(QWidget, BoundView):
    """Base for every destination."""

    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        QWidget.__init__(self, parent)
        BoundView.__init__(self)
        self.destination = destination
        self._tokens = tokens

        self._outer = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingXxl")
        self._outer.setContentsMargins(margin, margin, margin, margin)
        self._outer.setSpacing(tokens.metric("KcSpacingLg"))

        self._title = label(destination.title, role="pageTitle")
        self._subtitle = ElidedLabel(destination.subtitle)
        self._subtitle.setProperty("kcRole", "pageSubtitle")
        self.messages = MessageBar(tokens, self)

        # The heading, and room beside it for whatever this screen's one
        # top-level action is. A screen with no such action lays out exactly as
        # it did before: the stretch simply takes the whole right-hand side.
        self._header = QWidget(self)
        header_row = QHBoxLayout(self._header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(tokens.metric("KcSpacingLg"))
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(tokens.metric("KcSpacingXs"))
        heading.addWidget(self._title)
        heading.addWidget(self._subtitle)
        header_row.addLayout(heading, 1)
        self._header_actions = QHBoxLayout()
        self._header_actions.setContentsMargins(0, 0, 0, 0)
        self._header_actions.setSpacing(tokens.metric("KcSpacingMd"))
        header_row.addLayout(self._header_actions, 0)
        self._outer.addWidget(self._header)
        # Kept for a page used on its own (a test, a tool window). Inside the
        # shell every message goes to the floating layer instead, so this stays
        # hidden and costs no height - a notification must not resize the work.
        self._outer.addWidget(self.messages)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(tokens.metric("KcSpacingMd"))
        self._outer.addWidget(self.body, 1)

    #: True for a page that has an inspector of its own. The shell then keeps
    #: its own panel shut and points the toggle at the page's, so there is
    #: never a second, emptier inspector competing with the real one - which
    #: is exactly what the 15 September audit found on Etiketleme.
    owns_inspector = False

    #: True when that panel is not optional. The shell then never hides it and
    #: its toggle says so instead of pretending to control it. Etiketleme's
    #: panel carries the camera, the label summary and the athlete: it is not
    #: decoration beside the work, it is part of it. On 20 September the global
    #: toggle - a preference belonging to a panel that does not exist on that
    #: screen - hid it, and the button went on showing "open" while it was gone.
    inspector_is_permanent = False

    def add_header_action(self, widget: QWidget) -> QWidget:
        """Put ``widget`` on the heading's line, at the right-hand end.

        For the one control a screen is *about* rather than one of several it
        offers - Yakalama's "Bağlan", which belongs beside the word "Yakalama"
        and above the panel it affects, not down in the transport row with the
        record button it has nothing to do with.
        """
        self._header_actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return widget

    def bottom_reserve(self) -> int:
        """Height of an action bar this page pins to its own bottom edge.

        The floating message layer stacks from the bottom-right, which is
        table background on nearly every screen. On the one screen that keeps
        its Save button down there, a notification was drawn over it.
        """
        return 0

    # ------------------------------------------------------------ inspector
    def inspector_sections(self) -> tuple:
        """What the shell's inspector should show for this page right now.

        Returns ``Section`` rows built from whatever is selected. Empty means
        "nothing is selected", which the shell renders as a reason and a next
        step rather than as a blank panel.
        """
        return ()

    def set_inspector_visible(self, visible: bool) -> None:
        """Only called on a page that owns its inspector, and never with
        ``False`` on one whose panel is permanent."""

    # ------------------------------------------------------------ lifecycle
    def apply_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.messages.set_tokens(tokens)

    def page_activated(self) -> None:
        """Called when the page becomes visible.

        Pages do their loading here rather than in ``__init__`` so starting the
        application does not pay for seven screens the user has not opened.
        """

    def page_deactivated(self) -> None:
        """Called when the user leaves. Stop timers and workers here."""

    def show_message(self, message: Message) -> None:
        """Hand the message to the shell's floating layer if there is one.

        A page inside the shell never grows a message bar of its own: that is
        what changed the size of the video and the timeline in the audit.
        """
        layer = getattr(self.window(), "toasts", None)
        if layer is not None:
            layer.show_message(message)
            return
        self.messages.show_message(message)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self.unbind_all()
        super().closeEvent(event)


class PlaceholderPage(StudioPage):
    """A destination that exists in the workflow but is not built yet.

    Shown in its real position with the phase that delivers it, rather than
    hidden. A gap the user can see and name is better than a workflow that
    quietly looks shorter than it is.
    """

    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        text = (
            f"Bu ekran {destination.phase} fazında yapılacak."
            if destination.phase
            else "Bu ekran henüz yapılmadı."
        )
        note = label(text, role="sectionTitle")
        self.body_layout.addWidget(note)
        self.body_layout.addStretch(1)
        self.setAccessibleDescription(text)


__all__ = ["PlaceholderPage", "StudioPage"]
