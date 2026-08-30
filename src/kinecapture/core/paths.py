"""Windows long-path handling.

The dataset layout is deliberately deep - project, participant, session, take,
and a sub-directory per data kind - because that is what keeps raw capture,
derived data and human curation separate. Combined with a user-chosen dataset
root, that easily exceeds the legacy 260-character ``MAX_PATH`` limit, and the
failure mode is ugly: ``FileNotFoundError`` on a directory that visibly exists.

Windows supports longer paths through the ``\\\\?\\`` prefix on the Win32 file
APIs, which CPython's ``open``, ``os`` and ``tempfile`` all use. So every file
operation that writes user data goes through :func:`long_path`.

Two caveats the callers rely on:

* the prefix requires an *absolute, normalised* path (no ``..``, no forward
  slashes), which :func:`long_path` guarantees;
* not every third-party library accepts a prefixed path. OpenCV in particular
  does not, so :func:`safe_external_path` returns a plain string and callers
  treat a too-long path as a degraded-feature case rather than data loss.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Legacy Win32 limit. Paths at or above this need the extended prefix.
MAX_PATH = 259
# Atomic writers create a short temporary child next to the target. Prefix the
# parent early enough that the child cannot cross MAX_PATH after the decision.
_TEMPORARY_CHILD_MARGIN = 32

_EXTENDED_PREFIX = "\\\\?\\"
_UNC_PREFIX = "\\\\?\\UNC\\"

IS_WINDOWS = os.name == "nt"


def long_path(path: Path | str) -> str:
    """Return a string safe to hand to the OS, however long it is.

    On non-Windows platforms this is just ``str(path)``. On Windows a long path
    gains the extended-length prefix; a short one is left alone so that error
    messages and logs stay readable.
    """
    text = str(path)
    if not IS_WINDOWS:
        return text
    if text.startswith(_EXTENDED_PREFIX):
        return text
    absolute = os.path.abspath(text)
    if len(absolute) < MAX_PATH - _TEMPORARY_CHILD_MARGIN:
        return absolute
    if absolute.startswith("\\\\"):
        # \\server\share\... -> \\?\UNC\server\share\...
        return _UNC_PREFIX + absolute[2:]
    return _EXTENDED_PREFIX + absolute


def is_too_long_for_external_tools(path: Path | str) -> bool:
    """True when a library that cannot take the extended prefix would fail."""
    return IS_WINDOWS and len(os.path.abspath(str(path))) >= MAX_PATH


def safe_external_path(path: Path | str) -> str:
    """Plain path string for libraries that reject the extended prefix."""
    return os.path.abspath(str(path)) if IS_WINDOWS else str(path)


def ensure_dir(path: Path) -> Path:
    """``mkdir -p`` that works past ``MAX_PATH``."""
    os.makedirs(long_path(path), exist_ok=True)
    return path


def path_exists(path: Path | str) -> bool:
    return os.path.exists(long_path(path))


__all__ = [
    "IS_WINDOWS",
    "MAX_PATH",
    "ensure_dir",
    "is_too_long_for_external_tools",
    "long_path",
    "path_exists",
    "safe_external_path",
]
