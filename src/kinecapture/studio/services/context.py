"""What the context bar shows, computed without Qt.

The context bar answers one question at a glance: *where am I working, and is
this machine ready?* Each field is a :class:`ContextItem` carrying its own
state, so the view can render colour **and** icon **and** text without deciding
anything for itself - colour alone must never be the only signal.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from kinecapture.core.diagnostics import estimate_recording_minutes
from kinecapture.core.paths import path_exists


class ContextState(str, Enum):
    """The four states a context field can be in.

    Mapped by the view to exactly one status token each. ``UNKNOWN`` is not a
    failure: it means nothing has been selected yet, and it must not be painted
    like a problem.
    """

    UNKNOWN = "unknown"
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class ContextItem:
    key: str
    label: str
    value: str
    state: ContextState = ContextState.UNKNOWN
    #: The long form for the tooltip - a full path, an exact byte count.
    detail: str = ""
    #: True when the value is a number that should be set in the mono face so
    #: the bar does not jump as it changes.
    numeric: bool = False


@dataclass(frozen=True)
class ContextSnapshot:
    """One complete reading of the context bar."""

    items: tuple[ContextItem, ...] = ()

    def item(self, key: str) -> Optional[ContextItem]:
        return next((item for item in self.items if item.key == key), None)

    @property
    def worst_state(self) -> ContextState:
        order = [
            ContextState.ERROR,
            ContextState.WARNING,
            ContextState.OK,
            ContextState.UNKNOWN,
        ]
        for state in order:
            if any(item.state is state for item in self.items):
                return state
        return ContextState.UNKNOWN


def _format_gb(value: int) -> str:
    return f"{value / 1_000_000_000:.0f} GB"


def _nearest_existing(path: Path) -> Optional[Path]:
    """``path`` or the closest ancestor that exists, for a disk-space query."""
    for candidate in (path, *path.parents):
        if path_exists(candidate):
            return candidate
    return None


def disk_item(path: Optional[Path], *, warn_gb: float = 25.0) -> ContextItem:
    """Free space on the data volume, plus what that means in recording time.

    The number on its own is not actionable - "203 GB" does not say whether the
    session that is about to start fits. The estimate does.
    """
    if path is None:
        return ContextItem("disk", "Disk", "—", ContextState.UNKNOWN)
    # The data folder may not exist yet - it is created on first use. The
    # volume it will live on still has a free-space figure, and that is the
    # number the operator needs before starting a session, so ask the nearest
    # parent that does exist rather than reporting a failure.
    probe = _nearest_existing(path)
    if probe is None:
        return ContextItem(
            "disk",
            "Disk",
            "—",
            ContextState.UNKNOWN,
            detail=f"{path} için birim belirlenemedi.",
        )
    try:
        usage = shutil.disk_usage(str(probe))
    except OSError as exc:
        return ContextItem(
            "disk", "Disk", "okunamadı", ContextState.ERROR, detail=str(exc)
        )
    free_gb = usage.free / 1_000_000_000
    minutes = estimate_recording_minutes(usage.free)
    state = ContextState.OK if free_gb >= warn_gb else ContextState.WARNING
    return ContextItem(
        key="disk",
        label="Disk",
        value=_format_gb(usage.free),
        state=state,
        detail=f"{_format_gb(usage.free)} boş · yaklaşık {minutes:.0f} dakika kayıt",
        numeric=True,
    )


def data_root_item(path: Optional[Path]) -> ContextItem:
    """Whether the configured data folder is actually usable.

    A missing folder is a warning, never a reason to treat the recordings it
    should contain as lost: the drive may simply not be plugged in.
    """
    if path is None:
        return ContextItem("data", "Veri klasörü", "seçilmedi", ContextState.WARNING)
    if not path_exists(path):
        return ContextItem(
            key="data",
            label="Veri klasörü",
            value="bulunamadı",
            state=ContextState.WARNING,
            detail=f"{path} bulunamadı. Yeni kayıt için bir veri klasörü seçin.",
        )
    return ContextItem(
        key="data",
        label="Veri klasörü",
        value=path.name or str(path),
        state=ContextState.OK,
        detail=str(path),
    )


def simple_item(
    key: str,
    label: str,
    value: Optional[str],
    *,
    detail: str = "",
    numeric: bool = False,
) -> ContextItem:
    if not value:
        return ContextItem(key, label, "—", ContextState.UNKNOWN, detail=detail)
    return ContextItem(key, label, value, ContextState.OK, detail=detail, numeric=numeric)


__all__ = [
    "ContextItem",
    "ContextSnapshot",
    "ContextState",
    "data_root_item",
    "disk_item",
    "simple_item",
]
