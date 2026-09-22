"""Window geometry, panel widths and the open tab, remembered between runs.

Written through :mod:`kinecapture.core.jsonio`, so the same atomic-write rule
that protects recordings protects this file too: a power cut during a save
leaves the previous state, never a truncated one.

A corrupt or unreadable file is *not* an error. Losing the remembered window
size must never stop the application from starting, so the reader falls back to
defaults and says so.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from kinecapture.core.jsonio import read_json_mapping, write_json
from kinecapture.core.paths import ensure_dir, path_exists

logger = logging.getLogger(__name__)

WINDOW_STATE_SCHEMA_VERSION = "1.0.0"

#: Guard against a state file written on a monitor that no longer exists.
_MIN_WIDTH = 1120
_MIN_HEIGHT = 700
_MAX_DIMENSION = 16384


def default_window_state_path() -> Path:
    return Path.home() / ".kinecapture" / "window_state.json"


@dataclass
class WindowState:
    """What the shell restores on the next run."""

    width: int = _MIN_WIDTH
    height: int = _MIN_HEIGHT
    maximised: bool = True
    #: Where the window was when it closed. **Recorded, never restored**: from
    #: 20 September every launch starts on Projeler, so that the project this
    #: session works in is a choice somebody makes rather than one the last
    #: session made for them. Kept because it says what the last session was
    #: doing, which is worth having in a support conversation.
    active_page: str = "projects"
    inspector_open: bool = False
    inspector_width: int = 320
    theme: str = "dark"

    def normalised(self) -> "WindowState":
        """Clamp to something that can actually be shown on this machine."""
        return WindowState(
            width=_clamp(self.width, _MIN_WIDTH, _MAX_DIMENSION),
            height=_clamp(self.height, _MIN_HEIGHT, _MAX_DIMENSION),
            maximised=bool(self.maximised),
            active_page=str(self.active_page or "projects"),
            inspector_open=bool(self.inspector_open),
            inspector_width=_clamp(self.inspector_width, 240, 1200),
            theme=str(self.theme or "dark"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = WINDOW_STATE_SCHEMA_VERSION
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WindowState":
        known = {f for f in cls().__dict__}
        return cls(**{k: v for k, v in payload.items() if k in known}).normalised()


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def load_window_state(path: Optional[Path] = None) -> WindowState:
    target = path or default_window_state_path()
    if not path_exists(target):
        return WindowState()
    try:
        return WindowState.from_dict(dict(read_json_mapping(target)))
    except Exception as exc:  # noqa: BLE001 - never block startup on a preference
        logger.warning("Pencere durumu okunamadı (%s); varsayılan kullanılıyor", exc)
        return WindowState()


def save_window_state(state: WindowState, path: Optional[Path] = None) -> Optional[Path]:
    """Persist the state. Returns the path, or ``None`` if it could not be written.

    Failing to remember a window size is not worth an error dialog on the way
    out of the application, so this reports rather than raises.
    """
    target = path or default_window_state_path()
    try:
        ensure_dir(target.parent)
        return write_json(target, state.normalised().to_dict(), overwrite=True)
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("Pencere durumu yazılamadı: %s", exc)
        return None


__all__ = [
    "WINDOW_STATE_SCHEMA_VERSION",
    "WindowState",
    "default_window_state_path",
    "load_window_state",
    "save_window_state",
]
