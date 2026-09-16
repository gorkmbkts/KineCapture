"""How a stored value is written down for a person to read.

Two rules, both from the 15 September audit.

*Time is shown where the user is.* Every stamp on disk is UTC, because that is
the only sane thing to store. Slicing the first sixteen characters off it and
putting that in a table showed a recording made at 23:13 as 20:13 - a wrong
answer that looks exactly like a right one. Conversion happens here, once.

*A row names the thing, not the file.* ``take_20260914T201308_f645`` is a real
and useful identifier, and it belongs in the detail panel and the clipboard.
The row itself says the participant, the local time and the take's number in
its session, because that is what a person recognises.

No Qt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

#: What an empty value looks like. One dash everywhere, never a blank cell that
#: reads as "zero" or as a failure to load.
MISSING = "—"


def parse_stamp(value: str) -> Optional[datetime]:
    """Read an ISO-8601 stamp. Returns ``None`` rather than raising.

    A stamp with no timezone is read as UTC: that is what this application
    writes, and guessing local would move every historical row by the offset.
    """
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def to_local(value: str) -> Optional[datetime]:
    moment = parse_stamp(value)
    return moment.astimezone() if moment is not None else None


def local_datetime(value: str, *, seconds: bool = False) -> str:
    """``2026-09-14 23:13`` in the machine's own timezone."""
    moment = to_local(value)
    if moment is None:
        return MISSING
    pattern = "%Y-%m-%d %H:%M:%S" if seconds else "%Y-%m-%d %H:%M"
    return moment.strftime(pattern)


def local_date(value: str) -> str:
    moment = to_local(value)
    return moment.strftime("%Y-%m-%d") if moment is not None else MISSING


def local_time(value: str) -> str:
    moment = to_local(value)
    return moment.strftime("%H:%M") if moment is not None else MISSING


def timezone_note(value: str = "") -> str:
    """What the tooltip says, so the conversion is visible rather than assumed."""
    moment = to_local(value) if value else datetime.now().astimezone()
    if moment is None:
        return "Saat yerel saat diliminde gösterilir."
    offset = moment.strftime("%z")
    pretty = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
    stored = parse_stamp(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""
    suffix = f" · kayıtta {stored} UTC" if stored else ""
    return f"Yerel saat ({pretty}){suffix}"


def duration(seconds: float) -> str:
    """``1:23`` for anything under an hour, ``1:02:03`` above it."""
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return MISSING
    if total < 0:
        return MISSING
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def short_id(value: str) -> str:
    """The tail of an identifier, for a column that cannot hold all of it."""
    text = (value or "").strip()
    if not text:
        return MISSING
    return text.rsplit("_", 1)[-1] if "_" in text else text


__all__ = [
    "MISSING",
    "duration",
    "local_date",
    "local_datetime",
    "local_time",
    "parse_stamp",
    "short_id",
    "timezone_note",
    "to_local",
]
