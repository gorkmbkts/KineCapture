"""Stable identifier generation and validation.

Rules that the rest of the application depends on:

* identifiers are unique, filesystem-safe and contain no personal information;
* participant codes are sequential and pseudonymous (``P0001``), never a name;
* an identifier is never reused, and never derived from mutable metadata.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

#: Characters allowed in any identifier that becomes a directory name.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

#: Windows forbids these device names as path components regardless of extension.
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string used in every metadata stamp."""
    return utc_now().isoformat(timespec="milliseconds")


def compact_stamp(moment: datetime | None = None) -> str:
    """``20260820T141530`` - sortable, filesystem-safe, no separators."""
    return (moment or utc_now()).strftime("%Y%m%dT%H%M%S")


def new_id(prefix: str) -> str:
    """Return a unique identifier such as ``take_9f2c1d0a4b76``.

    The random part is a UUID4 fragment: 48 bits is plenty for a single
    workstation's dataset and keeps directory names readable.
    """
    if not prefix:
        raise ValueError("prefix must not be empty")
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def timestamped_id(prefix: str, moment: datetime | None = None) -> str:
    """Return a sortable identifier such as ``ses_20260820T141530_9f2c``.

    Used where humans browse the directory listing and chronological order is
    more useful than pure randomness.
    """
    return f"{prefix}_{compact_stamp(moment)}_{uuid.uuid4().hex[:4]}"


def participant_code(sequence: int) -> str:
    """``P0001`` style pseudonymous participant code."""
    if sequence < 1:
        raise ValueError("participant sequence must be >= 1")
    return f"P{sequence:04d}"


def is_safe_id(value: str) -> bool:
    """True when ``value`` can be used as a single path component."""
    if not _ID_PATTERN.match(value or ""):
        return False
    stem = value.split(".", 1)[0].upper()
    return stem not in _RESERVED_WINDOWS_NAMES


_TRANSLITERATION = str.maketrans(
    {
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
        "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
        "â": "a", "î": "i", "û": "u", "é": "e", "è": "e", "ñ": "n",
    }
)


def _full_slug(text: str) -> str:
    lowered = (text or "").translate(_TRANSLITERATION).lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


def slugify(text: str, *, fallback: str = "item", max_length: int = 48) -> str:
    """Turn free text into a safe, lowercase identifier fragment.

    Non-ASCII letters (Turkish included) are transliterated where an obvious
    ASCII equivalent exists, then anything else collapses to ``-``.
    """
    cleaned = _full_slug(text)[:max_length].strip("-")
    if not cleaned or not is_safe_id(cleaned):
        return fallback
    return cleaned


def slug_is_lossless(text: str, slug: str) -> bool:
    """True when ``slug`` is all of ``text`` - not cut short, not a fallback.

    Two names that differ only after the length cut, or that are made of
    symbols with no ASCII letter in them, produce the same slug without being
    the same thing. A caller that treats equal slugs as equal names has to ask
    this first.
    """
    full = _full_slug(text)
    return bool(full) and full == slug


__all__ = [
    "compact_stamp",
    "is_safe_id",
    "new_id",
    "participant_code",
    "slug_is_lossless",
    "slugify",
    "timestamped_id",
    "utc_now",
    "utc_now_iso",
]
