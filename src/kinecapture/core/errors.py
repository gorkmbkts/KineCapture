"""Application error types.

Every error the user can trigger carries two things: a stable machine-readable
``code`` used in diagnostics and logs, and a human sentence in Turkish shown in
the GUI. Tracebacks go to the log file, never to a dialog.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


class KineCaptureError(RuntimeError):
    """Base class for errors that are safe to show to the user."""

    #: Stable, machine-readable identifier. Subclasses override it.
    code: str = "kinecapture_error"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        remedy: str = "",
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message
        #: What the user can actually do about it. May be empty.
        self.remedy = remedy
        self.details: dict[str, Any] = dict(details or {})

    def user_text(self) -> str:
        """Message plus remedy, ready to render in a status bar or banner."""
        return f"{self.message} {self.remedy}".strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "remedy": self.remedy,
            "details": dict(self.details),
        }


class ConfigError(KineCaptureError):
    """A configuration file exists but cannot be used."""

    code = "config_invalid"


class CameraError(KineCaptureError):
    """A camera backend failed."""

    code = "camera_error"


class CameraUnavailableError(CameraError):
    """The backend cannot be used here (missing SDK, no device, no permission)."""

    code = "camera_unavailable"


class CameraNotConnectedError(CameraError):
    """An operation needed an open device that does not exist."""

    code = "camera_not_connected"


class StorageError(KineCaptureError):
    """Reading or writing project data failed."""

    code = "storage_error"


class OverwriteRefusedError(StorageError):
    """A write would have destroyed existing data, so it was refused."""

    code = "overwrite_refused"


class ValidationError(KineCaptureError):
    """User-supplied or on-disk data failed validation."""

    code = "validation_failed"

    def __init__(
        self,
        message: str,
        *,
        field: str = "",
        code: Optional[str] = None,
        remedy: str = "",
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message, code=code, remedy=remedy, details=details)
        #: Which form field or document key is wrong ("" when not field-specific).
        self.field = field


class ExportError(KineCaptureError):
    """A dataset release could not be produced."""

    code = "export_failed"


class ExportCancelled(ExportError):
    """The user cancelled an export. The staging directory is removed."""

    code = "export_cancelled"


__all__ = [
    "CameraError",
    "CameraNotConnectedError",
    "CameraUnavailableError",
    "ConfigError",
    "ExportCancelled",
    "ExportError",
    "KineCaptureError",
    "OverwriteRefusedError",
    "StorageError",
    "ValidationError",
]
