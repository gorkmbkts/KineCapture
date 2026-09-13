"""The one notification primitive the viewmodels are allowed to use.

A viewmodel must be testable without a Qt event loop, so it cannot inherit
``QObject`` or emit ``Signal``. Instead it holds :class:`Observable` values and
plain callback lists; ``views/qt_bridge.py`` adapts those to Qt signals at the
boundary.

Deliberately small - subscribe, set, get. Anything richer (computed chains,
async) would be a framework, and a framework is the thing that does not port to
WinUI.
"""

from __future__ import annotations

from typing import Callable, Generic, Iterable, Optional, TypeVar

T = TypeVar("T")

Unsubscribe = Callable[[], None]


class Observable(Generic[T]):
    """A value that tells its subscribers when it changes.

    Notification happens only on an actual change, compared with ``==``. That
    matters for the shell: the context bar is refreshed several times a second
    and must not repaint when nothing moved.
    """

    __slots__ = ("_value", "_listeners", "_name")

    def __init__(self, value: T, *, name: str = "") -> None:
        self._value = value
        self._listeners: list[Callable[[T], None]] = []
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def value(self) -> T:
        return self._value

    def get(self) -> T:
        return self._value

    def set(self, value: T) -> bool:
        """Set the value. Returns whether it actually changed."""
        if value == self._value:
            return False
        self._value = value
        for listener in list(self._listeners):
            listener(value)
        return True

    def force(self, value: T) -> None:
        """Set and notify even if the value compares equal.

        Needed for mutable payloads whose identity changed but whose ``==``
        does not - a rebuilt list with the same contents, for instance.
        """
        self._value = value
        for listener in list(self._listeners):
            listener(value)

    def subscribe(
        self, listener: Callable[[T], None], *, immediate: bool = False
    ) -> Unsubscribe:
        """Register ``listener``. With ``immediate`` it is called once now."""
        self._listeners.append(listener)
        if immediate:
            listener(self._value)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    @property
    def subscriber_count(self) -> int:
        return len(self._listeners)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        label = f" {self._name}" if self._name else ""
        return f"<Observable{label}={self._value!r}>"


class Event(Generic[T]):
    """A one-shot notification with no retained value.

    Used for things that *happen* rather than things that *are*: a message to
    show, a request to close a dialog. Keeping these out of :class:`Observable`
    stops a view from re-showing an old error when it reconnects.
    """

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: list[Callable[[T], None]] = []

    def subscribe(self, listener: Callable[[T], None]) -> Unsubscribe:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def emit(self, payload: T) -> None:
        for listener in list(self._listeners):
            listener(payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._listeners)


class Subscriptions:
    """Holds unsubscribe callables so a view can detach in one call."""

    def __init__(self, items: Optional[Iterable[Unsubscribe]] = None) -> None:
        self._items: list[Unsubscribe] = list(items or ())

    def add(self, unsubscribe: Unsubscribe) -> Unsubscribe:
        self._items.append(unsubscribe)
        return unsubscribe

    def close(self) -> None:
        for unsubscribe in reversed(self._items):
            unsubscribe()
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


__all__ = ["Event", "Observable", "Subscriptions", "Unsubscribe"]
