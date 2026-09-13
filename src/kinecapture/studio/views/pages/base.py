"""What every Studio page has in common.

A page owns a title strip, a message bar and a body. It does **not** own
application state: it is handed a viewmodel and binds to it. Anything a page
computes for itself is state the next front end would have to recompute.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget

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
        margin = tokens.metric("KcSpacingXl")
        self._outer.setContentsMargins(margin, margin, margin, margin)
        self._outer.setSpacing(tokens.metric("KcSpacingMd"))

        self._title = label(destination.title, role="pageTitle")
        self._subtitle = ElidedLabel(destination.subtitle)
        self._subtitle.setProperty("kcRole", "pageSubtitle")
        self.messages = MessageBar(tokens, self)

        self._outer.addWidget(self._title)
        self._outer.addWidget(self._subtitle)
        self._outer.addWidget(self.messages)

        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(tokens.metric("KcSpacingMd"))
        self._outer.addWidget(self.body, 1)

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
