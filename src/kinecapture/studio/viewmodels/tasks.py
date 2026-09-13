"""Running slow work somewhere other than the GUI thread, without importing Qt.

A viewmodel knows that scanning a project is slow. It must not know that the
answer is ``QThreadPool``. So it asks a :class:`TaskRunner` - an interface with
one method - and the view supplies the Qt implementation.

Two things fall out of that. Tests drive the real viewmodel with
:class:`InlineRunner` and get deterministic, synchronous behaviour with no
event loop. And a WinUI port swaps one small class instead of unpicking
threading from the logic.

The contract the Qt implementation must honour: ``work`` runs on some other
thread, and ``on_done``/``on_error`` are delivered back on the GUI thread.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol


class TaskRunner(Protocol):
    """Runs ``work`` off the calling thread and reports back on it."""

    def run(
        self,
        work: Callable[[], Any],
        on_done: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None: ...


class InlineRunner:
    """Runs the work immediately, on this thread.

    The default, and what tests use. Nothing about a viewmodel's behaviour may
    depend on whether the work was deferred - if it does, that is a bug the
    inline runner is meant to expose rather than hide.
    """

    def run(
        self,
        work: Callable[[], Any],
        on_done: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        try:
            result = work()
        except BaseException as exc:  # noqa: BLE001 - handed to the caller
            if on_error is None:
                raise
            on_error(exc)
            return
        on_done(result)


__all__ = ["InlineRunner", "TaskRunner"]
