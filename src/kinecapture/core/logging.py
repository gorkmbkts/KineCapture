"""Logging setup: console plus a rotating file log.

Policy:

* the user sees a short sentence; the traceback goes to the log file;
* logs carry environment, backend, session and take identifiers so a support
  question can be answered from the file alone;
* logs never carry personal data - participant *codes* (``P0001``) are fine,
  names and free-text notes are not written by the logging layer.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

_CONSOLE_FORMAT = "%(levelname)-7s %(name)s: %(message)s"
_FILE_FORMAT = (
    "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s "
    "%(filename)s:%(lineno)d - %(message)s"
)

#: Root logger name; every module logger hangs off this.
ROOT_LOGGER_NAME = "kinecapture"

_LOG_FILE_NAME = "kinecapture.log"
_MAX_BYTES = 4 * 1024 * 1024
_BACKUP_COUNT = 5

_configured = False
_log_file_path: Optional[Path] = None


def get_logger(name: str) -> logging.Logger:
    """Return a module logger under the application's root logger."""
    if name == ROOT_LOGGER_NAME or name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def log_file_path() -> Optional[Path]:
    """Path of the active log file, or ``None`` before setup."""
    return _log_file_path


def setup_logging(
    level: str = "INFO", log_dir: Optional[Path] = None, *, force: bool = False
) -> logging.Logger:
    """Configure console and rotating file handlers. Idempotent.

    A log directory that cannot be created is not fatal: the application still
    runs with console logging and says so, because losing the log is much less
    bad than refusing to start.
    """
    global _configured, _log_file_path

    root = logging.getLogger(ROOT_LOGGER_NAME)
    if _configured and not force:
        root.setLevel(level)
        return root

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(level)
    root.propagate = False

    # Started through ``pythonw.exe`` - the installed shortcut - there is no
    # console and ``sys.stderr`` is None. The file log below is then the only
    # log, which is the point of having one.
    if sys.stderr is not None:
        console = logging.StreamHandler(stream=sys.stderr)
        console.setLevel(level)
        console.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        root.addHandler(console)

    _log_file_path = None
    if log_dir is not None:
        try:
            directory = Path(log_dir).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / _LOG_FILE_NAME
            file_handler = logging.handlers.RotatingFileHandler(
                target,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
            root.addHandler(file_handler)
            _log_file_path = target
        except OSError as exc:
            root.warning("Log dosyası açılamadı (%s); yalnızca konsola yazılıyor.", exc)

    _configured = True
    return root


def install_excepthook() -> None:
    """Route otherwise-unhandled exceptions into the log instead of stderr noise.

    ``KeyboardInterrupt`` keeps the default behaviour so Ctrl+C still exits
    quietly.
    """
    logger = get_logger("unhandled")
    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):  # type: ignore[no-untyped-def]
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "Yakalanmamış hata: %s", exc_value, exc_info=(exc_type, exc_value, exc_tb)
        )

    sys.excepthook = _hook


__all__ = [
    "ROOT_LOGGER_NAME",
    "get_logger",
    "install_excepthook",
    "log_file_path",
    "setup_logging",
]
