"""The shell's state: which page, what the context bar says, what to report.

Holds no widgets and imports no Qt, so the whole navigation and messaging
behaviour is testable in a plain ``pytest`` run - and portable to another front
end unchanged.
"""

from __future__ import annotations

from typing import Callable, Optional

from kinecapture.studio.services.context import ContextSnapshot
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.window_state import WindowState

from .capture import RecordingPhase, RecordingStatus
from .navigation import DEFAULT_DESTINATION, DESTINATIONS, Destination, destination, is_known
from .observable import Event, Observable


class ShellViewModel:
    """Navigation, context bar and the message channel."""

    def __init__(
        self, session: SessionService, window_state: Optional[WindowState] = None
    ) -> None:
        self._session = session
        state = (window_state or WindowState()).normalised()

        # Every launch starts on Projeler, whatever the last session was
        # doing. A remembered tab let the application open on a screen that
        # belongs to a project nobody had chosen yet in this session, which is
        # how a recording was aimed at the wrong place: the screens were all
        # there, so the choice never had to be made.
        self.destinations: tuple[Destination, ...] = DESTINATIONS
        self.active_page: Observable[str] = Observable(
            DEFAULT_DESTINATION, name="active_page"
        )
        self.inspector_open: Observable[bool] = Observable(
            state.inspector_open, name="inspector_open"
        )
        self.theme: Observable[str] = Observable(session.config.theme, name="theme")
        self.context: Observable[ContextSnapshot] = Observable(
            session.context(), name="context"
        )
        self.message: Event[Message] = Event()
        #: What the recording is doing, on every screen. Set from whichever
        #: viewmodel actually owns the camera; the shell only displays it.
        self.recording: Observable[RecordingStatus] = Observable(
            RecordingStatus(), name="recording"
        )
        self._read_recording: Optional[Callable[[], RecordingStatus]] = None
        self._stop_recording: Optional[Callable[[], bool]] = None

        self._unsubscribe_session = session.subscribe(self.refresh_context)

    # ------------------------------------------------------------ navigation
    #: The one screen that is always open. It is how a project gets chosen, so
    #: gating it would leave nowhere to recover from. Signing out lives in the
    #: context bar, which no gate touches.
    UNGATED: tuple[str, ...] = ("projects",)

    def gate_reason(self, key: str) -> str:
        """Why ``key`` cannot be entered right now, or an empty string.

        Two conditions, and they are not the same one:

        * **a project**, for every screen but Projeler. Without one there is
          no dataset for a screen to be about;
        * **a participant**, for Yakalama alone. A recording is written to a
          person's folder the moment it starts, so "which person" has to be a
          decision somebody made, not a default the application picked.

        The person chosen here is the *project participant* - the folder the
        take is written to. Which body in the camera image is being recorded
        is a separate question, answered on the Yakalama screen by clicking on
        them, and neither answer implies the other.
        """
        if key in self.UNGATED or not is_known(key):
            return ""
        if self._session.workspace is None:
            return "Önce bir proje seçin."
        if key == "capture" and not self._session.selected_participant_id:
            return "Kayıt için önce bir katılımcı seçin."
        return ""

    def can_enter(self, key: str) -> bool:
        return not self.gate_reason(key)

    def navigate(self, key: str) -> bool:
        """Switch page, if this session is allowed to.

        The refusal lives here rather than on the buttons because a button is
        only one of the ways in: there are ``Ctrl+1..8`` shortcuts, page-step
        shortcuts, actions on notification cards, and code that navigates
        directly after finishing a job. Disabling the bar would have left
        every one of those open.
        """
        if not is_known(key):
            return False
        reason = self.gate_reason(key)
        if reason:
            self.report(
                Message(
                    headline=reason,
                    severity=Severity.WARNING,
                    # One card, not one per attempt: the toast layer folds
                    # repeats of the same code into a single counted card.
                    code=(
                        "capture_needs_participant"
                        if key == "capture"
                        else "needs_project"
                    ),
                    detail=(
                        "Projeler ekranından katılımcıyı seçin; kayıt o "
                        "katılımcının klasörüne yazılır."
                        if key == "capture"
                        else "Projeler ekranından bir proje açın."
                    ),
                )
            )
            # Somewhere to act on it, rather than a refusal and a dead end.
            self.active_page.set(DEFAULT_DESTINATION)
            return False
        return self.active_page.set(key)

    def step(self, offset: int) -> None:
        """Move ``offset`` places along the workflow, clamped at both ends.

        Clamped rather than wrapping: the bar reads as a sequence, and jumping
        from Ayarlar back to Projeler would contradict that.
        """
        keys = [item.key for item in self.destinations]
        index = keys.index(self.active_page.value)
        target = keys[max(0, min(len(keys) - 1, index + offset))]
        # Stepping past a gated screen would otherwise bounce the user back to
        # Projeler and look like the shortcut jumping two places.
        if not self.can_enter(target):
            return
        self.navigate(target)

    @property
    def session(self) -> SessionService:
        """The one service the shell owns. Pages reach it through here."""
        return self._session

    @property
    def active_destination(self) -> Destination:
        found = destination(self.active_page.value)
        assert found is not None  # navigate() refuses unknown keys
        return found

    # ------------------------------------------------------------ recording
    def set_recording_source(
        self,
        read: Optional[Callable[[], RecordingStatus]],
        stop: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Say where the live recording state comes from, and how to stop it.

        The shell must be able to show a recording and end it from any screen,
        including screens that know nothing about a camera. It does that by
        asking whoever owns the camera, rather than by owning one itself.
        """
        self._read_recording = read
        self._stop_recording = stop
        self.refresh_recording()

    def refresh_recording(self) -> None:
        if self._read_recording is None:
            self.recording.set(RecordingStatus())
            return
        self.recording.set(self._read_recording())

    def stop_recording(self) -> bool:
        """Stop from anywhere. Ignored unless a take is genuinely open."""
        if self._stop_recording is None:
            return False
        if not self.recording.value.is_open:
            return False
        started = bool(self._stop_recording())
        self.refresh_recording()
        return started

    @property
    def is_recording(self) -> bool:
        return self.recording.value.phase is RecordingPhase.RECORDING

    # -------------------------------------------------------------- context
    def refresh_context(self) -> None:
        self.context.set(self._session.context())
        self.refresh_recording()

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
