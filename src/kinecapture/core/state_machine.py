"""Capture lifecycle state machine.

Invalid transitions are never silently accepted: they raise
:class:`InvalidStateTransition`. The GUI derives which controls are enabled from
this state, so an incorrect state would mean lying to the user about what the
application is doing with their camera and their data.

```text
DISCONNECTED -> READY -> PREVIEWING -> RECORDING -> STOPPING -> REVIEWING
                                                             -> READY
ERROR is reachable from anywhere; recovery always returns through DISCONNECTED
so the backend is re-initialised cleanly rather than resumed from an unknown
hardware state.
```
"""

from __future__ import annotations

import threading
from typing import Callable, Iterable, Mapping

from kinecapture.domain.enums import CaptureState

StateListener = Callable[[CaptureState, CaptureState], None]


class InvalidStateTransition(RuntimeError):
    """Raised when a transition is not part of the allowed graph."""

    def __init__(self, current: CaptureState, requested: CaptureState) -> None:
        super().__init__(
            f"Geçersiz kamera durumu geçişi: {current.value} -> {requested.value}"
        )
        self.current = current
        self.requested = requested


#: The allowed transition graph. Anything not listed here is a bug.
ALLOWED_TRANSITIONS: Mapping[CaptureState, frozenset[CaptureState]] = {
    CaptureState.DISCONNECTED: frozenset({CaptureState.READY, CaptureState.ERROR}),
    CaptureState.READY: frozenset(
        {
            CaptureState.PREVIEWING,
            CaptureState.REVIEWING,
            CaptureState.DISCONNECTED,
            CaptureState.ERROR,
        }
    ),
    CaptureState.PREVIEWING: frozenset(
        {CaptureState.RECORDING, CaptureState.STOPPING, CaptureState.ERROR}
    ),
    CaptureState.RECORDING: frozenset({CaptureState.STOPPING, CaptureState.ERROR}),
    CaptureState.STOPPING: frozenset(
        {
            CaptureState.READY,
            CaptureState.PREVIEWING,
            CaptureState.REVIEWING,
            CaptureState.DISCONNECTED,
            CaptureState.ERROR,
        }
    ),
    CaptureState.REVIEWING: frozenset(
        {CaptureState.READY, CaptureState.DISCONNECTED, CaptureState.ERROR}
    ),
    CaptureState.ERROR: frozenset({CaptureState.DISCONNECTED}),
}

#: States in which the backend is actively producing frames.
LIVE_STATES = frozenset({CaptureState.PREVIEWING, CaptureState.RECORDING})


class CaptureStateMachine:
    """Thread-safe state machine with change notification.

    Listeners are invoked *outside* the lock so a slow Qt slot cannot stall the
    acquisition thread that triggered the transition.
    """

    def __init__(self, initial: CaptureState = CaptureState.DISCONNECTED) -> None:
        self._state = initial
        self._listeners: list[StateListener] = []
        self._lock = threading.RLock()

    @property
    def state(self) -> CaptureState:
        with self._lock:
            return self._state

    def add_listener(self, listener: StateListener) -> None:
        """Register a ``(previous, current)`` callback."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: StateListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def allowed_targets(self) -> frozenset[CaptureState]:
        return ALLOWED_TRANSITIONS[self.state]

    def can_transition(self, target: CaptureState) -> bool:
        return target in ALLOWED_TRANSITIONS[self.state]

    def transition(self, target: CaptureState) -> CaptureState:
        """Move to ``target`` or raise :class:`InvalidStateTransition`."""
        with self._lock:
            if target not in ALLOWED_TRANSITIONS[self._state]:
                raise InvalidStateTransition(self._state, target)
            previous, self._state = self._state, target
            listeners = list(self._listeners)
        for listener in listeners:
            listener(previous, target)
        return target

    def force(self, target: CaptureState) -> CaptureState:
        """Set the state without checking the graph.

        Only for recovery paths that must converge on a known state (shutdown,
        hardware disappearing mid-transition). Everything else uses
        :meth:`transition` so that a logic error surfaces instead of hiding.
        """
        with self._lock:
            previous, self._state = self._state, target
            listeners = list(self._listeners)
        for listener in listeners:
            listener(previous, target)
        return target

    def is_live(self) -> bool:
        return self.state in LIVE_STATES

    def is_in(self, states: Iterable[CaptureState]) -> bool:
        return self.state in set(states)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<CaptureStateMachine state={self.state.value}>"


__all__ = [
    "ALLOWED_TRANSITIONS",
    "LIVE_STATES",
    "CaptureStateMachine",
    "InvalidStateTransition",
    "StateListener",
]
