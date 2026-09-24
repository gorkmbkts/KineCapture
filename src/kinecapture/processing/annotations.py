"""Canonical annotations: labels bound to the raw source, not to a frame number.

This is the file that decides whether a labelled dataset can be trusted, so it
is deliberately strict and deliberately verbose about why.

**An interval is stored as two anchors, never as an index.** An anchor is
``(source_fingerprint, source_position, camera_timestamp_ns)`` - the raw
recording's own identity plus an exact position and time inside it. A frame
index means nothing across two processing runs: if a version is reprocessed
with a different model, or a frame that was unreadable last time decodes this
time, index 412 is a different moment. Re-anchoring on load would silently move
every label a coach ever drew. So a label that cannot be resolved exactly is
**refused**, loudly, and the operator is told which version it belongs to.

**Both ends are inclusive.** Stated once, checked everywhere, and written into
the document as ``contract``. Half-open and closed intervals differ by exactly
one frame, which is invisible on screen and fatal in a training target.

**Correctness is derived, never chosen.** A movement with at least one
classified error interval is incorrect; one with none is correct. An unreviewed
movement is neither. Asking the annotator for a verdict *as well* invites the
two to disagree, and a stored verdict that contradicts its own evidence is
worse than no verdict at all.

No Qt, no SDK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import is_safe_id, new_id
from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, path_exists

logger = logging.getLogger(__name__)

#: 1.1.0 adds the label itself - exercise class, error class, affected
#: anatomical roles, review stamp - to the 1.0.0 document, which carried only
#: interval boundaries. Additive: a 1.0.0 document loads with empty classes and
#: is reported as unreviewed rather than being guessed at.
#:
#: 1.2.0 adds ``roles_origin`` and ``roles_revision`` to an error interval:
#: whether the affected joints were inherited from the class definition or
#: chosen for this repetition, and which revision of the definition was
#: copied. Additive, and deliberately not defaulted: an interval written
#: before this reads back as ``unknown``, which is neither of the two - it is
#: the honest statement that nothing recorded how those joints were arrived
#: at. Back-filling them would be inventing provenance.
CANONICAL_ANNOTATION_SCHEMA_VERSION = "1.2.0"

#: Written into every document. Read it before writing a tool against one.
BOUNDARY_CONTRACT = "canonical_source_boundaries_inclusive"


class Correctness(str, Enum):
    """The verdict on one movement. Derived from the error intervals."""

    UNREVIEWED = "unreviewed"
    CORRECT = "correct"
    INCORRECT = "incorrect"


class JointStatus(str, Enum):
    """Why an error interval's affected-role list is empty, when it is.

    Four distinct meanings. Collapsing them into one "empty" would silently
    produce false negatives in node-level supervision: *not looked at* is not
    the same claim as *looked at, no particular joint*.
    """

    UNREVIEWED = "unreviewed"          # nobody has looked
    SELECTED = "selected"              # one or more roles marked
    NOT_APPLICABLE = "not_applicable"  # looked; no specific joint target
    INDETERMINATE = "indeterminate"    # looked; cannot be determined reliably

    @property
    def supervises_nodes(self) -> bool:
        return self is JointStatus.SELECTED

    @property
    def is_reviewed(self) -> bool:
        return self is not JointStatus.UNREVIEWED


class Readiness(str, Enum):
    """Whether a movement may be exported, and if not, what is missing."""

    READY = "ready"
    UNREVIEWED = "unreviewed"
    NO_EXERCISE = "no_exercise"
    UNCLASSIFIED_ERROR = "unclassified_error"
    INVALID_INTERVAL = "invalid_interval"

    @property
    def is_exportable(self) -> bool:
        return self is Readiness.READY


@dataclass(frozen=True)
class Anchor:
    """One moment in the raw recording, identified so it cannot drift."""

    source_fingerprint: str
    source_position: int
    camera_timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_fingerprint": self.source_fingerprint,
            "source_position": int(self.source_position),
            "camera_timestamp_ns": int(self.camera_timestamp_ns),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Anchor":
        try:
            return cls(
                source_fingerprint=str(payload["source_fingerprint"]),
                source_position=int(payload["source_position"]),
                camera_timestamp_ns=int(payload["camera_timestamp_ns"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                "Etiket sınırı eksik veya bozuk.",
                code="anchor_malformed",
                details={"anchor": dict(payload)},
            ) from exc


class RolesOrigin(str, Enum):
    """Where an interval's affected-joint list came from.

    This is the distinction JOINT-04 exists for. A class defines the joints it
    is about once; applying that definition to a new interval is convenient
    and correct, and it is **not** the same claim as a person having looked at
    that repetition and chosen those joints. A release that confused the two
    would present inherited defaults as per-repetition evidence.

    ``UNKNOWN`` is for intervals written before this was recorded. It is not a
    synonym for either of the other two: nothing is known about how those
    joints were arrived at, and that is what it says.
    """

    UNKNOWN = "unknown"
    CLASS_DEFAULT = "class_default"
    REVIEWED = "reviewed"


@dataclass(frozen=True)
class ErrorInterval:
    """One error, localised in time, inside one movement.

    Exactly one class per interval. Two errors visible at the same moment are
    two overlapping intervals, so every interval stays a clean
    ``(class, start, end)`` and the temporal target never becomes ambiguous.
    """

    interval_id: str
    start: Anchor
    end: Anchor
    error_class: str = ""
    affected_roles: tuple[str, ...] = ()
    joint_status: JointStatus = JointStatus.UNREVIEWED
    note: str = ""
    #: How ``affected_roles`` was arrived at. See :class:`RolesOrigin`.
    roles_origin: RolesOrigin = RolesOrigin.UNKNOWN
    #: Which revision of the class definition was copied, when it was. Zero
    #: when the roles did not come from a class definition. This is what lets
    #: a class be edited later without silently rewriting earlier decisions.
    roles_revision: int = 0

    @property
    def is_classified(self) -> bool:
        return bool(self.error_class)

    @property
    def roles_were_reviewed(self) -> bool:
        """True only when a person chose these joints for *this* interval."""
        return self.roles_origin is RolesOrigin.REVIEWED

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "interval_id": self.interval_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "error_class": self.error_class,
            "affected_roles": list(self.affected_roles),
            "joint_status": self.joint_status.value,
            "note": self.note,
        }
        if self.roles_origin is not RolesOrigin.UNKNOWN or self.roles_revision:
            # Written only when there is something to say, so a document with
            # no joint provenance is byte-identical to a 1.1.0 one.
            payload["roles_origin"] = self.roles_origin.value
            payload["roles_revision"] = int(self.roles_revision)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ErrorInterval":
        raw_status = str(payload.get("joint_status", JointStatus.UNREVIEWED.value))
        try:
            status = JointStatus(raw_status)
        except ValueError:
            # An unrecognised word is not a decision somebody made. Treating it
            # as one would invent a review that never happened.
            logger.warning("Bilinmeyen eklem durumu '%s'; unreviewed sayıldı", raw_status)
            status = JointStatus.UNREVIEWED
        raw_origin = str(payload.get("roles_origin", RolesOrigin.UNKNOWN.value))
        try:
            origin = RolesOrigin(raw_origin)
        except ValueError:
            # An unrecognised word is not a provenance somebody recorded.
            # Treating it as "reviewed" would manufacture evidence.
            logger.warning(
                "Bilinmeyen eklem kökeni '%s'; unknown sayıldı", raw_origin
            )
            origin = RolesOrigin.UNKNOWN
        return cls(
            interval_id=str(payload.get("interval_id") or new_id("err")),
            start=Anchor.from_dict(payload["start"]),
            end=Anchor.from_dict(payload["end"]),
            error_class=str(payload.get("error_class", "")),
            affected_roles=tuple(str(r) for r in payload.get("affected_roles") or ()),
            joint_status=status,
            note=str(payload.get("note", "")),
            roles_origin=origin,
            roles_revision=int(payload.get("roles_revision") or 0),
        )


@dataclass(frozen=True)
class MovementSample:
    """One repetition: the unit that becomes a training example."""

    sample_id: str
    start: Anchor
    end: Anchor
    exercise: str = ""
    errors: tuple[ErrorInterval, ...] = ()
    #: When a human last said "this movement is finished". The one thing the
    #: intervals cannot say on their own: no error intervals means *correct*
    #: only if somebody actually looked.
    reviewed_at: str = ""
    note: str = ""
    excluded: bool = False

    # ----------------------------------------------------------------- rules
    @property
    def classified_errors(self) -> tuple[ErrorInterval, ...]:
        return tuple(interval for interval in self.errors if interval.is_classified)

    @property
    def correctness(self) -> Correctness:
        """Derived, never stored as an independent choice."""
        if not self.reviewed_at:
            return Correctness.UNREVIEWED
        return Correctness.INCORRECT if self.classified_errors else Correctness.CORRECT

    def readiness(self, known_exercises: Sequence[str] = ()) -> Readiness:
        """Whether this movement may be exported, and what is missing if not."""
        if not self.exercise:
            return Readiness.NO_EXERCISE
        if known_exercises and self.exercise not in known_exercises:
            return Readiness.NO_EXERCISE
        if any(not interval.is_classified for interval in self.errors):
            # A half-finished interval makes the whole movement unusable:
            # dropping just that interval would tell the model "no error here",
            # which is a wrong label rather than a missing one.
            return Readiness.UNCLASSIFIED_ERROR
        if not self.reviewed_at:
            return Readiness.UNREVIEWED
        return Readiness.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "exercise": self.exercise,
            "errors": [interval.to_dict() for interval in self.errors],
            "reviewed_at": self.reviewed_at,
            "note": self.note,
            "excluded": self.excluded,
            # Written for readers, never read back as authority: loading
            # recomputes it from the intervals.
            "derived_correctness": self.correctness.value,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MovementSample":
        return cls(
            sample_id=str(payload.get("sample_id") or new_id("mov")),
            start=Anchor.from_dict(payload["start"]),
            end=Anchor.from_dict(payload["end"]),
            exercise=str(payload.get("exercise", "")),
            errors=tuple(
                ErrorInterval.from_dict(entry) for entry in payload.get("errors") or ()
            ),
            reviewed_at=str(payload.get("reviewed_at", "")),
            note=str(payload.get("note", "")),
            excluded=bool(payload.get("excluded", False)),
        )


@dataclass
class AnnotationDocument:
    """Every label for one processing version."""

    processing_run: str
    source_fingerprint: str
    samples: tuple[MovementSample, ...] = ()
    revision: int = 1
    annotator: str = ""
    updated_at: str = ""
    schema_version: str = CANONICAL_ANNOTATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANONICAL_ANNOTATION_SCHEMA_VERSION,
            "contract": BOUNDARY_CONTRACT,
            "processing_run": self.processing_run,
            "source_fingerprint": self.source_fingerprint,
            "revision": int(self.revision),
            "annotator": self.annotator,
            "updated_at": self.updated_at,
            "samples": [sample.to_dict() for sample in self.samples],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AnnotationDocument":
        contract = str(payload.get("contract", ""))
        if contract and contract != BOUNDARY_CONTRACT:
            # Refused rather than guessed at. A document written under a
            # different boundary rule is off by a frame everywhere, and that
            # is exactly the kind of error nobody would notice.
            raise ValidationError(
                "Bu etiket dosyası farklı bir sınır sözleşmesiyle yazılmış.",
                code="annotation_contract_mismatch",
                details={"contract": contract, "expected": BOUNDARY_CONTRACT},
            )
        return cls(
            processing_run=str(payload.get("processing_run", "")),
            source_fingerprint=str(payload.get("source_fingerprint", "")),
            samples=tuple(
                MovementSample.from_dict(entry) for entry in payload.get("samples") or ()
            ),
            revision=int(payload.get("revision", 1) or 1),
            annotator=str(payload.get("annotator", "")),
            updated_at=str(payload.get("updated_at", "")),
            schema_version=str(
                payload.get("schema_version", CANONICAL_ANNOTATION_SCHEMA_VERSION)
            ),
        )

    # ------------------------------------------------------------- summaries
    def sample(self, sample_id: str) -> Optional[MovementSample]:
        return next((s for s in self.samples if s.sample_id == sample_id), None)

    def readiness_counts(self, known_exercises: Sequence[str] = ()) -> dict[str, int]:
        counts: dict[str, int] = {state.value: 0 for state in Readiness}
        for sample in self.samples:
            if sample.excluded:
                continue
            counts[sample.readiness(known_exercises).value] += 1
        return counts

    @property
    def error_interval_count(self) -> int:
        return sum(len(sample.errors) for sample in self.samples)


def annotation_path(take_dir: Path, run_id: str) -> Path:
    return Path(take_dir) / "annotations" / "processing" / f"{run_id}.json"


def load_annotations(
    take_dir: Path, run_id: str, source_fingerprint: str
) -> AnnotationDocument:
    """Read the sidecar for one version, or return an empty document.

    A document that belongs to a different raw source is refused. It is not
    re-anchored and it is not partially accepted: those labels describe a
    different recording.
    """
    path = annotation_path(take_dir, run_id)
    if not path_exists(path):
        return AnnotationDocument(
            processing_run=run_id, source_fingerprint=source_fingerprint
        )
    document = AnnotationDocument.from_dict(dict(read_json(path)))
    if document.source_fingerprint and document.source_fingerprint != source_fingerprint:
        raise ValidationError(
            "Bu etiket dosyası başka bir ham kayda ait.",
            code="annotation_source_mismatch",
            remedy="Doğru sürümü açın; etiketler taşınmaz.",
            details={
                "document": document.source_fingerprint,
                "version": source_fingerprint,
            },
        )
    document.source_fingerprint = source_fingerprint
    document.processing_run = run_id
    return document


def save_annotations(take_dir: Path, document: AnnotationDocument) -> Path:
    """Write the sidecar atomically. Validation has already happened."""
    path = annotation_path(take_dir, document.processing_run)
    ensure_dir(path.parent)
    return write_json(path, document.to_dict(), overwrite=True)


def validate_document(
    document: AnnotationDocument,
    *,
    resolve: Any,
    frames: int,
    known_exercises: Sequence[str] = (),
    known_error_classes: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Check every rule that could produce a wrong training label.

    ``resolve`` turns an :class:`Anchor` into a frame position and raises if it
    cannot. Passing it in keeps this function independent of how a version is
    opened, and makes the "unresolvable anchor" case directly testable.

    Returns a list of problems; an empty list means the document is sound.
    Nothing is silently corrected.
    """
    problems: list[dict[str, Any]] = []

    def note(code: str, message: str, **extra: Any) -> None:
        problems.append({"code": code, "message": message, **extra})

    seen_samples: set[str] = set()
    for sample in document.samples:
        if sample.sample_id in seen_samples:
            note("duplicate_sample_id", "Aynı hareket kimliği iki kez var.",
                 sample=sample.sample_id)
        seen_samples.add(sample.sample_id)
        if not is_safe_id(sample.sample_id):
            # The id becomes a folder name in the dataset package. One that
            # is not a plain name - a hand-edited ``..\\..\\x`` - would put a
            # training example outside the package, or on top of another.
            note("sample_id_unsafe", "Hareket kimliği geçerli bir klasör adı değil.",
                 sample=sample.sample_id)

        try:
            start = resolve(sample.start)
            end = resolve(sample.end)
        except Exception as exc:  # noqa: BLE001 - reported, never repaired
            note(
                "sample_anchor_unresolved",
                f"Hareket sınırı bu sürümde bulunamadı: {exc}",
                sample=sample.sample_id,
            )
            continue

        if start > end:
            note("sample_reversed", "Hareketin bitişi başlangıcından önce.",
                 sample=sample.sample_id)
        if not (0 <= start < frames and 0 <= end < frames):
            note("sample_outside_source", "Hareket sınırı kaydın dışında.",
                 sample=sample.sample_id)
        if sample.exercise and known_exercises and sample.exercise not in known_exercises:
            note(
                "unknown_exercise",
                f"'{sample.exercise}' hareket sınıfı proje sözlüğünde yok.",
                sample=sample.sample_id,
            )

        seen_intervals: set[str] = set()
        for interval in sample.errors:
            if interval.interval_id in seen_intervals:
                note("duplicate_interval_id", "Aynı hata aralığı kimliği iki kez var.",
                     sample=sample.sample_id, interval=interval.interval_id)
            seen_intervals.add(interval.interval_id)

            try:
                first = resolve(interval.start)
                last = resolve(interval.end)
            except Exception as exc:  # noqa: BLE001
                note(
                    "interval_anchor_unresolved",
                    f"Hata aralığı sınırı bu sürümde bulunamadı: {exc}",
                    sample=sample.sample_id,
                    interval=interval.interval_id,
                )
                continue

            if first > last:
                note("interval_reversed", "Hata aralığının bitişi başlangıcından önce.",
                     sample=sample.sample_id, interval=interval.interval_id)
            if not (start <= first <= last <= end):
                note(
                    "interval_outside_sample",
                    "Hata aralığı ait olduğu hareketin dışına taşıyor.",
                    sample=sample.sample_id,
                    interval=interval.interval_id,
                )
            if (
                interval.error_class
                and known_error_classes
                and interval.error_class not in known_error_classes
            ):
                note(
                    "unknown_error_class",
                    f"'{interval.error_class}' hata sınıfı proje sözlüğünde yok.",
                    sample=sample.sample_id,
                    interval=interval.interval_id,
                )
            if interval.joint_status is JointStatus.SELECTED and not interval.affected_roles:
                note(
                    "selected_without_roles",
                    "Eklem durumu 'seçildi' ama hiçbir eklem işaretlenmemiş.",
                    sample=sample.sample_id,
                    interval=interval.interval_id,
                )
            if interval.affected_roles and interval.joint_status is not JointStatus.SELECTED:
                note(
                    "roles_without_selected_status",
                    "Eklem işaretli ama durum 'seçildi' değil.",
                    sample=sample.sample_id,
                    interval=interval.interval_id,
                )
    return problems


__all__ = [
    "BOUNDARY_CONTRACT",
    "CANONICAL_ANNOTATION_SCHEMA_VERSION",
    "Anchor",
    "AnnotationDocument",
    "Correctness",
    "ErrorInterval",
    "JointStatus",
    "MovementSample",
    "Readiness",
    "RolesOrigin",
    "annotation_path",
    "load_annotations",
    "save_annotations",
    "validate_document",
]
