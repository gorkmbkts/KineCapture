"""Services: the Studio's only entry point to the backend.

**Nothing here imports Qt.** ``tests/test_studio_layers.py`` imports this
package in a subprocess with PySide6 blocked and fails if it does. That rule is
what makes a later WinUI 3 front end a rewrite of one layer instead of three.
"""

from .context import ContextItem, ContextSnapshot, ContextState
from .messages import Action, Message, Severity, from_error
from .session import SessionService
from .window_state import WindowState, load_window_state, save_window_state

__all__ = [
    "Action",
    "ContextItem",
    "ContextSnapshot",
    "ContextState",
    "Message",
    "SessionService",
    "Severity",
    "WindowState",
    "from_error",
    "load_window_state",
    "save_window_state",
]
