"""Backend-independent camera contract.

Every camera implementation - synthetic, ZED, and anything added later - lives
behind this interface. Nothing here may reference Qt or ``pyzed``: that is what
keeps the GUI testable and the SDK optional.

Capability reporting is part of the contract. A backend states what it can
actually do through :class:`BackendCapabilities`, and the UI disables what is
unavailable with an explanation rather than offering a control that silently
produces nothing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from kinecapture.domain.enums import DataOrigin, HealthLevel
from kinecapture.domain.models import CameraInfo, FramePacket
from kinecapture.visualization.skeleton_spec import SkeletonSpec


@dataclass(frozen=True)
class BackendCapabilities:
    """What a backend can do in this environment, right now."""

    color: bool = True
    depth: bool = False
    body_tracking: bool = False
    native_recording: bool = False
    multi_body: bool = False
    device_enumeration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class AvailabilityResult:
    """Result of a non-destructive "can I use this backend?" probe.

    ``code`` is a stable machine-readable reason; ``message`` is what the user
    reads and ``remedy`` is what they can do about it. Probing must never raise
    and must never open hardware.
    """

    available: bool
    code: str
    message: str
    remedy: str = ""
    level: HealthLevel = HealthLevel.UNKNOWN
    details: Mapping[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.available

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "code": self.code,
            "message": self.message,
            "remedy": self.remedy,
            "level": self.level.value,
            "details": dict(self.details),
        }

    @classmethod
    def ok(cls, message: str, **kwargs: Any) -> "AvailabilityResult":
        return cls(
            available=True,
            code="ok",
            message=message,
            level=HealthLevel.READY,
            **kwargs,
        )

    @classmethod
    def blocked(cls, code: str, message: str, remedy: str = "", **kwargs: Any):
        return cls(
            available=False,
            code=code,
            message=message,
            remedy=remedy,
            level=HealthLevel.BLOCKED,
            **kwargs,
        )


class CameraBackend(ABC):
    """Lifecycle contract: probe -> connect -> preview -> grab -> stop -> close.

    Implementations must be safe to ``disconnect`` twice and safe to
    ``disconnect`` from a state they never reached, because shutdown paths call
    it unconditionally.
    """

    #: Short identifier used in metadata and in the GUI.
    name: str = "base"

    #: Whether this backend produces real or synthetic data. Never guessed by
    #: the caller - it is written verbatim into every take's metadata.
    origin: DataOrigin = DataOrigin.REAL

    @abstractmethod
    def is_available(self) -> AvailabilityResult:
        """Report whether this backend can be used, without side effects."""

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """What this backend supports. Valid before connecting (best effort)."""

    @abstractmethod
    def connect(self) -> CameraInfo:
        """Open the device and return what it actually reported."""

    @abstractmethod
    def start_preview(self) -> None:
        """Begin producing frames. Must be idempotent."""

    @abstractmethod
    def grab_frame(self) -> Optional[FramePacket]:
        """Return the next frame, or ``None`` if none is ready.

        May block for at most one frame interval; it is called from a dedicated
        acquisition thread, never from the GUI thread.
        """

    @abstractmethod
    def stop_preview(self) -> None:
        """Stop producing frames. Must be idempotent."""

    @abstractmethod
    def disconnect(self) -> None:
        """Release the device. Must be idempotent and safe during shutdown."""

    @abstractmethod
    def get_camera_info(self) -> Optional[CameraInfo]:
        """Return the connected device description, or ``None`` if not connected."""

    @abstractmethod
    def skeleton_spec(self) -> Optional[SkeletonSpec]:
        """The skeleton topology this backend emits, if it emits one."""

    # ------------------------------------------------------ native recording
    def supports_native_recording(self) -> bool:
        return self.capabilities().native_recording

    def start_native_recording(self, path) -> bool:  # noqa: ANN001 - Path
        """Begin the backend's own recording, if it has one.

        Returns True when recording actually started. The default is a truthful
        "I cannot do that" rather than a silent no-op that looks like success.
        """
        return False

    @property
    def native_recording_path_limit(self) -> Optional[int]:
        """Longest target path this backend's recorder can actually open.

        ``None`` means "no limit of its own" - a backend that writes through
        Python, which handles a long Windows path through the extended-length
        prefix. A vendor library that takes a plain path string does have a
        limit, and it has to say so, because the caller is the only place that
        knows the path *before* a recording is attempted. Discovered on
        20 September: a 281-character target came back as ``SVO RECORDING
        ERROR`` and was reported to the user as a disk or permission problem.
        """
        return None

    def stop_native_recording(self) -> None:
        """Stop the backend's own recording. Idempotent."""
        return None

    def native_recording_stats(self) -> dict[str, Any]:
        return {}

    # ------------------------------------------------------------ diagnostics
    def diagnostics(self) -> dict[str, Any]:
        """Extra key/value detail for the health panel. Must never raise."""
        return {}

    # Context-manager sugar so tests and scripts cannot leak a device handle.
    def __enter__(self) -> "CameraBackend":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.disconnect()


__all__ = [
    "AvailabilityResult",
    "BackendCapabilities",
    "CameraBackend",
]
