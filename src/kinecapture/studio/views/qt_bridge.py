"""The one place where a plain-Python viewmodel meets Qt.

Viewmodels publish :class:`~kinecapture.studio.viewmodels.observable.Observable`
values and callback lists. Widgets want signals and slots. This adapter is the
seam - thin on purpose, because everything in it is the part that would be
thrown away in a WinUI 3 port.

Two rules it enforces:

* a widget that subscribes must also unsubscribe, or the viewmodel keeps a
  reference to a deleted C++ object and the next notification crashes Qt;
* callbacks arriving from a worker thread are delivered on the GUI thread via a
  queued signal, never straight into a widget.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, Optional, TypeVar

from PySide6.QtCore import QObject, Qt, Signal

from kinecapture.studio.viewmodels.observable import Event, Observable, Subscriptions

T = TypeVar("T")


class ObservableBridge(QObject, Generic[T]):
    """Re-emits one :class:`Observable` as a Qt signal on the GUI thread."""

    changed = Signal(object)

    def __init__(
        self, observable: Observable[T], parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._observable = observable
        self._unsubscribe = observable.subscribe(self._forward)

    def _forward(self, value: T) -> None:
        # Emitting rather than calling the slot directly is what gets a
        # viewmodel change made on a worker thread onto the GUI thread before
        # any widget is touched.
        self.changed.emit(value)

    @property
    def value(self) -> T:
        return self._observable.value

    def detach(self) -> None:
        self._unsubscribe()


class EventBridge(QObject, Generic[T]):
    """Re-emits one :class:`Event` as a Qt signal."""

    fired = Signal(object)

    def __init__(self, event: Event[T], parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._unsubscribe = event.subscribe(self.fired.emit)

    def detach(self) -> None:
        self._unsubscribe()


class BoundView:
    """Mixin giving a widget one ``bind``/``unbind`` pair.

    ``bind(observable, slot)`` calls ``slot`` now with the current value and
    again on every change; ``unbind_all()`` in ``closeEvent``/``deleteLater``
    detaches everything at once. Forgetting the second half is the classic way
    a Qt/Python interface starts crashing on shutdown, so it is one call.
    """

    def __init__(self) -> None:
        self._subscriptions = Subscriptions()
        self._bridges: list[QObject] = []

    def bind(
        self,
        observable: Observable[Any],
        slot: Callable[[Any], None],
        *,
        immediate: bool = True,
    ) -> None:
        bridge = ObservableBridge(observable, parent=self if isinstance(self, QObject) else None)
        bridge.changed.connect(slot, Qt.ConnectionType.AutoConnection)
        self._bridges.append(bridge)
        self._subscriptions.add(bridge.detach)
        if immediate:
            slot(observable.value)

    def bind_event(self, event: Event[Any], slot: Callable[[Any], None]) -> None:
        bridge = EventBridge(event, parent=self if isinstance(self, QObject) else None)
        bridge.fired.connect(slot, Qt.ConnectionType.AutoConnection)
        self._bridges.append(bridge)
        self._subscriptions.add(bridge.detach)

    def unbind_all(self) -> None:
        self._subscriptions.close()
        self._bridges.clear()


__all__ = ["BoundView", "EventBridge", "ObservableBridge"]
