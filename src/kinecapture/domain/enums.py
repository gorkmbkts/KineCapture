"""Enumerations shared across layers.

These values are part of the on-disk contract: they are serialised by value, so
renaming a member is a breaking change that must bump a schema version. Every
enum here derives from ``str`` so JSON round-trips are lossless.
"""

from __future__ import annotations

from enum import Enum


class BackendKind(str, Enum):
    """Which camera backend implementation to use."""

    MOCK = "mock"
    ZED = "zed"


class DataOrigin(str, Enum):
    """Where a recording actually came from.

    Synthetic data must be distinguishable from real capture everywhere it
    appears - in the GUI, in metadata and in an exported release.
    """

    REAL = "real"
    SYNTHETIC = "synthetic"


class CaptureState(str, Enum):
    """Lifecycle states of the capture pipeline.

    Allowed transitions live in :mod:`kinecapture.core.state_machine`.
    """

    DISCONNECTED = "DISCONNECTED"
    READY = "READY"
    PREVIEWING = "PREVIEWING"
    RECORDING = "RECORDING"
    STOPPING = "STOPPING"
    REVIEWING = "REVIEWING"
    ERROR = "ERROR"


class CaptureStatus(str, Enum):
    """Per-frame delivery status."""

    OK = "ok"
    STALE = "stale"
    DROPPED = "dropped"
    ERROR = "error"


class TrackingState(str, Enum):
    """Tracking state of a detected body.

    The ZED adapter maps ``sl.OBJECT_TRACKING_STATE`` onto these values
    explicitly; the mapping is not assumed to be an identity.
    """

    OK = "ok"
    SEARCHING = "searching"
    OFF = "off"
    TERMINATE = "terminate"


class CaptureMode(str, Enum):
    """How a take was driven."""

    GUIDED = "guided"
    FREE = "free"


class TakeState(str, Enum):
    """Finalisation state of a take on disk.

    ``RECORDING`` means a writer currently owns the directory. ``PARTIAL`` means
    the writer never finished - the frames written so far are still readable and
    the take can be recovered or discarded, but it is never silently treated as
    complete.
    """

    RECORDING = "recording"
    PARTIAL = "partial"
    FINALIZED = "finalized"
    FAILED = "failed"


class TakeQuality(str, Enum):
    """The operator's immediate verdict after a take."""

    UNDECIDED = "undecided"
    GOOD = "good"
    RETAKE = "retake"
    TECHNICAL_ISSUE = "technical_issue"
    EXCLUDED = "excluded"
    UNCERTAIN = "uncertain"


class SegmentSource(str, Enum):
    """Where a repetition boundary came from.

    Model suggestions never silently become ground truth: they keep this source
    until a human edits or approves them.
    """

    MANUAL = "manual"
    OPERATOR_MARKER = "operator_marker"
    MODEL_SUGGESTION = "model_suggestion"


class SegmentStatus(str, Enum):
    """Whether a repetition participates in a dataset release."""

    ACTIVE = "active"
    EXCLUDED = "excluded"


class Correctness(str, Enum):
    """Coarse correctness judgement for a repetition."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


class AnnotationStatus(str, Enum):
    """Review state of an annotation record."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    EXCLUDED = "excluded"


class ConsentStatus(str, Enum):
    """Recorded consent state for a session."""

    UNKNOWN = "unknown"
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class HealthLevel(str, Enum):
    """Traffic-light level used by the pre-capture health panel.

    Always rendered with an icon *and* a word, never colour alone.
    """

    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


__all__ = [
    "AnnotationStatus",
    "BackendKind",
    "CaptureMode",
    "CaptureState",
    "CaptureStatus",
    "ConsentStatus",
    "Correctness",
    "DataOrigin",
    "HealthLevel",
    "SegmentSource",
    "SegmentStatus",
    "TakeQuality",
    "TakeState",
    "TrackingState",
]
