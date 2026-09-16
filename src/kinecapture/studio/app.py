"""Starting the Studio.

Kept thin on purpose: wire the three layers together, install a last-resort
exception hook, show the window. Everything with behaviour lives in a service
or a viewmodel where it can be tested without a display.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.config import AppConfig
from kinecapture.studio.services.messages import from_error
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.window_state import (
    WindowState,
    default_window_state_path,
    load_window_state,
)
from kinecapture.studio.theme import stylesheet_for  # noqa: F401 - re-exported for tests
from kinecapture.studio.viewmodels.shell import ShellViewModel

logger = logging.getLogger(__name__)


def build_window(
    config: AppConfig,
    *,
    window_state: Optional[WindowState] = None,
    state_path: Optional[Path] = None,
):
    """Construct the whole object graph. Returns the window.

    Separate from :func:`run_studio` so tests can build the real shell,
    offscreen, without starting an event loop.
    """
    from .views.shell import StudioWindow  # local: keeps Qt out of import time

    session = SessionService.open(config)
    state = window_state if window_state is not None else load_window_state(state_path)
    if state.theme and state.theme != config.theme:
        # The window remembers the theme the user was last looking at; the
        # preference file is the fallback, not the other way round.
        config.theme = state.theme
    viewmodel = ShellViewModel(session, state)
    window = StudioWindow(viewmodel, state)
    window.set_state_path(state_path or default_window_state_path())
    return window


def install_exception_hook(window) -> None:  # noqa: ANN001 - StudioWindow
    """An unexpected exception must not take the interface with it.

    Qt would otherwise let a Python exception escape a slot and abort the
    process, losing whatever the user was in the middle of. Here it becomes a
    message they can read and a log line someone can act on.
    """
    previous = sys.excepthook

    def hook(kind, value, traceback):  # noqa: ANN001
        logger.exception("Yakalanmamış istisna", exc_info=(kind, value, traceback))
        try:
            window.viewmodel.report(from_error(value))
        except Exception:  # noqa: BLE001 - the reporter must never re-raise
            pass
        previous(kind, value, traceback)

    sys.excepthook = hook


def run_studio(config: AppConfig) -> int:
    """Open the Studio window and run the event loop."""
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication

    from .views.skeleton3d import default_surface_format
    from .views.theming import apply_application_theme

    # Must be set before the first GL context exists: the 3D skeleton view
    # needs a depth buffer, and asking for one afterwards is ignored.
    QSurfaceFormat.setDefaultFormat(default_surface_format())

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName(APP_NAME)
    application.setApplicationVersion(APP_VERSION)
    # Style, palette and stylesheet together, before the first widget exists,
    # so nothing is ever built against the platform's colours.
    apply_application_theme(config.theme)

    window = build_window(config)
    install_exception_hook(window)
    if window.current_window_state().maximised:
        window.showMaximized()
    else:
        window.show()
    return application.exec()


__all__ = ["build_window", "install_exception_hook", "run_studio"]
