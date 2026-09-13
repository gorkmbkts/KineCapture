"""The Qt half of :mod:`kinecapture.studio.viewmodels.tasks`.

Runs work on ``QThreadPool`` and delivers the result back on the GUI thread.
The delivery is the part that matters: a callback that ran on the worker thread
and touched a widget would corrupt Qt's state in a way that usually shows up
much later, somewhere else.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

logger = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, work: Callable[[], Any], signals: _Signals) -> None:
        super().__init__()
        self._work = work
        self._signals = signals

    def run(self) -> None:  # noqa: D401 - Qt entry point
        try:
            result = self._work()
        except BaseException as exc:  # noqa: BLE001 - reported to the GUI thread
            logger.debug("Arka plan işi hata verdi", exc_info=True)
            self._signals.failed.emit(exc)
            return
        self._signals.done.emit(result)


class QtTaskRunner:
    """A :class:`TaskRunner` backed by ``QThreadPool``."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        self._parent = parent
        self._pool = QThreadPool.globalInstance()
        # Kept so a task in flight cannot have its signal object collected
        # while the worker still holds a reference to it.
        self._live: list[_Signals] = []

    def run(
        self,
        work: Callable[[], Any],
        on_done: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> None:
        signals = _Signals(self._parent)
        self._live.append(signals)

        def finish(callback, payload) -> None:  # noqa: ANN001
            if signals in self._live:
                self._live.remove(signals)
            callback(payload)

        signals.done.connect(
            lambda payload: finish(on_done, payload), Qt.ConnectionType.QueuedConnection
        )
        signals.failed.connect(
            lambda exc: finish(on_error or _reraise, exc),
            Qt.ConnectionType.QueuedConnection,
        )
        self._pool.start(_Task(work, signals))

    def wait(self, timeout_ms: int = 30_000) -> bool:
        """Block until every queued task has finished. Used on shutdown."""
        return self._pool.waitForDone(timeout_ms)


def _reraise(exc: BaseException) -> None:
    raise exc


__all__ = ["QtTaskRunner"]
