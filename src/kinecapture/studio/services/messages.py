"""The two-layer error and status language.

The visible layer says what happened and what to do about it, in plain Turkish
with no technical vocabulary, and offers one primary action. Everything
technical - the error code, the exception text, the paths - lives behind
"Ayrıntılar", where it is available to anyone who wants it but never in the way
of someone who does not.

No Qt here: a message is data. The view decides whether it becomes a banner, a
dialog or a line in the context bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

from kinecapture.core.errors import KineCaptureError


class Severity(str, Enum):
    """How loud a message is. Maps to exactly one colour token in the view."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Action:
    """One offered action. ``key`` is what the viewmodel receives back."""

    key: str
    label: str
    primary: bool = False


@dataclass(frozen=True)
class Message:
    """One thing to tell the user.

    ``headline`` and ``detail`` are the visible layer. ``code`` and
    ``technical`` are what "Ayrıntılar" opens; they are never shown first.
    """

    headline: str
    severity: Severity = Severity.INFO
    detail: str = ""
    code: str = ""
    technical: Mapping[str, Any] = field(default_factory=dict)
    actions: tuple[Action, ...] = ()

    @property
    def has_details(self) -> bool:
        return bool(self.code or self.technical)

    def technical_text(self) -> str:
        """The details pane content: one ``key: value`` per line."""
        lines: list[str] = []
        if self.code:
            lines.append(f"kod: {self.code}")
        for key, value in self.technical.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)


def from_error(
    error: BaseException, *, headline: Optional[str] = None
) -> Message:
    """Turn an exception into a message without losing anything.

    A :class:`KineCaptureError` already carries the two layers - its text is
    written for the user and its ``remedy`` says what to do - so it is used as
    given. Anything else is an unexpected failure: the user gets a plain
    sentence and the exception type goes into the details, because a raw
    ``KeyError: 'p'`` on screen tells them nothing.
    """
    if isinstance(error, KineCaptureError):
        technical: dict[str, Any] = {"tip": type(error).__name__}
        technical.update(dict(getattr(error, "details", {}) or {}))
        return Message(
            headline=headline or str(error),
            severity=Severity.ERROR,
            detail=getattr(error, "remedy", "") or "",
            code=getattr(error, "code", "") or "",
            technical=technical,
        )
    return Message(
        headline=headline or "Beklenmeyen bir hata oluştu.",
        severity=Severity.ERROR,
        detail="İşlem tamamlanmadı. Ayrıntılar teknik açıklamayı içerir.",
        code="unexpected_error",
        technical={"tip": type(error).__name__, "mesaj": str(error)},
    )


__all__ = ["Action", "Message", "Severity", "from_error"]
