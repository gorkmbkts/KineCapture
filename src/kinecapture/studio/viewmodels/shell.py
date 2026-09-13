"""The shell's state: which page, what the context bar says, what to report.

Holds no widgets and imports no Qt, so the whole navigation and messaging
behaviour is testable in a plain ``pytest`` run - and portable to another front
end unchanged.
"""

from __future__ import annotations

from typing import Optional

from kinecapture.studio.services.context import ContextSnapshot
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.window_state import WindowState

from .navigation import DEFAULT_DESTINATION, DESTINATIONS, Destination, destination, is_known
from .observable import Event, Observable


class ShellViewModel:
    """Navigation, context bar and the message channel."""

    def __init__(
        self, session: SessionService, window_state: Optional[WindowState] = None
    ) -> None:
        self._session = session
        state = (window_state or WindowState()).normalised()

        start = state.active_page if is_known(state.active_page) else DEFAULT_DESTINATION
        self.destinations: tuple[Destination, ...] = DESTINATIONS
        self.active_page: Observable[str] = Observable(start, name="active_page")
        self.inspector_open: Observable[bool] = Observable(
            state.inspector_open, name="inspector_open"
        )
        self.theme: Observable[str] = Observable(session.config.theme, name="theme")
        self.context: Observable[ContextSnapshot] = Observable(
            session.context(), name="context"
        )
        self.message: Event[Message] = Event()

        self._unsubscribe_session = session.subscribe(self.refresh_context)

    # ------------------------------------------------------------ navigation
    def navigate(self, key: str) -> bool:
        """Switch page. An unknown key is ignored rather than crashing the shell."""
        if not is_known(key):
            return False
        return self.active_page.set(key)

    def step(self, offset: int) -> None:
        """Move ``offset`` places along the workflow, clamped at both ends.

        Clamped rather than wrapping: the bar reads as a sequence, and jumping
        from Ayarlar back to Projeler would contradict that.
        """
        keys = [item.key for item in self.destinations]
        index = keys.index(self.active_page.value)
        self.navigate(keys[max(0, min(len(keys) - 1, index + offset))])

    @property
    def active_destination(self) -> Destination:
        found = destination(self.active_page.value)
        assert found is not None  # navigate() refuses unknown keys
        return found

    # -------------------------------------------------------------- context
    def refresh_context(self) -> None:
        self.context.set(self._session.context())

    def toggle_inspector(self) -> bool:
        self.inspector_open.set(not self.inspector_open.value)
        return self.inspector_open.value

    # -------------------------------------------------------------- theming
    def set_theme(self, name: str) -> None:
        self._session.set_theme(name)
        self.theme.set(name)

    def toggle_theme(self) -> str:
        self.set_theme("light" if self.theme.value == "dark" else "dark")
        return self.theme.value

    # ------------------------------------------------------------- messages
    def report(self, message: Message) -> None:
        self.message.emit(message)

    def report_error(self, error: BaseException, *, headline: str = "") -> None:
        self.report(from_error(error, headline=headline or None))

    def notify(self, headline: str, *, detail: str = "") -> None:
        self.report(Message(headline=headline, severity=Severity.INFO, detail=detail))

    # ---------------------------------------------------------------- state
    def window_state(self, base: WindowState) -> WindowState:
        """``base`` with the parts this viewmodel owns written into it."""
        return WindowState(
            width=base.width,
            height=base.height,
            maximised=base.maximised,
            active_page=self.active_page.value,
            inspector_open=self.inspector_open.value,
            inspector_width=base.inspector_width,
            theme=self.theme.value,
        ).normalised()

    def close(self) -> None:
        self._unsubscribe_session()


__all__ = ["ShellViewModel"]
