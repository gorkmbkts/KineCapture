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


class BodyActionState(str, Enum):
    """Coarse motion state the tracker reports for a body.

    The ZED SDK's ``sl.OBJECT_ACTION_STATE`` has exactly two meaningful members
    on this SDK version (``IDLE`` and ``MOVING``; ``LAST`` is an enum sentinel,
    not a state). Anything else - including a tracker that does not report the
    field at all - becomes :attr:`UNKNOWN` rather than being guessed at.

    This is a *tracker* output, not a biomechanical classification. It says the
    detector considered the body to be moving, nothing about movement quality.
    """

    IDLE = "idle"
    MOVING = "moving"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: object) -> "BodyActionState":
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().upper().rsplit(".", 1)[-1]
        if text == "IDLE":
            return cls.IDLE
        if text == "MOVING":
            return cls.MOVING
        return cls.UNKNOWN


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
    #: .. note::
    #:    Since the derived-correctness rule this is an **outcome**, not an
    #:    input. It is computed from a movement's classified error intervals
    #:    by :attr:`MovementSample.derived_correctness`; nothing asks a human
    #:    to choose it and no edit API accepts it.
    """Whether a movement sample was performed correctly.

    The judgement is **binary** once a human has made it. ``UNLABELLED`` is a
    working state, not a third kind of movement: it means nobody has decided
    yet, and such a sample is never exported.

    Legacy sidecars may contain ``uncertain`` or ``unknown``. Both are read back
    as :attr:`UNLABELLED` - an undecided label must never be silently promoted
    into a definite one - and the original value is preserved in the sample's
    ``legacy`` block.
    """

    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNLABELLED = "unlabelled"

    @property
    def is_decided(self) -> bool:
        return self is not Correctness.UNLABELLED

    @classmethod
    def parse(cls, value: object) -> "Correctness":
        """Read any historical value, defaulting to UNLABELLED."""
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        if text == "correct":
            return cls.CORRECT
        if text == "incorrect":
            return cls.INCORRECT
        # "uncertain", "unknown", "", anything unrecognised.
        return cls.UNLABELLED


class SampleReadiness(str, Enum):
    """Why a movement sample is, or is not, ready to be exported.

    This is *derived* from the sample's content rather than stored, so the
    screen's notion of "labelled" and the exporter's notion of "eligible" can
    never drift apart - there is exactly one rule, in
    :func:`kinecapture.domain.project.evaluate_sample`.
    """

    #: Fully labelled and internally consistent.
    READY = "ready"
    #: No exercise chosen, or correctness not decided.
    UNLABELLED = "unlabelled"
    #: Marked incorrect but no error interval has been localised yet.
    NEEDS_ERROR_INTERVAL = "needs_error_interval"
    #: Marked correct yet carries error intervals - a contradiction.
    CONTRADICTION = "contradiction"
    #: Has an interval that is reversed, empty, outside the sample, or whose
    #: error class is not in the project schema.
    INVALID_INTERVAL = "invalid_interval"
    #: A pre-derived-correctness file whose recorded verdict disagrees with its
    #: own error intervals. Never resolved silently - see
    #: :func:`kinecapture.domain.project.evaluate_sample`.
    LEGACY_CONFLICT = "legacy_conflict"
    #: Deliberately kept out of the dataset by the user.
    EXCLUDED = "excluded"

    @property
    def is_ready(self) -> bool:
        return self is SampleReadiness.READY


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
    "BackendKind",
    "BodyActionState",
    "CaptureMode",
    "CaptureState",
    "CaptureStatus",
    "ConsentStatus",
    "Correctness",
    "DataOrigin",
    "HealthLevel",
    "SampleReadiness",
    "SegmentSource",
    "SegmentStatus",
    "TakeQuality",
    "TakeState",
    "TrackingState",
]
