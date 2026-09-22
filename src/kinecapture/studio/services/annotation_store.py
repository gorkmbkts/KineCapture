"""The one place labels are edited, undone and written.

Every change goes through a single method that takes the whole document from
one valid state to the next, then records one undo step. That is not tidiness:
an edit split across three setters can leave a half-applied interval on disk -
a new class with the old joints, say - and it costs the annotator three undos
to take back one decision they made.

Writing is debounced but never lost: :meth:`flush` is called on close, on
leaving the screen, and before switching versions.

No Qt.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from kinecapture.features.roles import missing_roles, resolve_roles
from kinecapture.visualization.skeleton_spec import SkeletonSpec
from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import new_id
from kinecapture.processing.annotations import (
    Anchor,
    AnnotationDocument,
    ErrorInterval,
    JointStatus,
    MovementSample,
    Readiness,
    RolesOrigin,
    save_annotations,
    validate_document,
)

logger = logging.getLogger(__name__)

#: How many steps back the annotator can go. Generous: an hour of labelling is
#: a lot of small decisions and "I have gone too far back to fix this" is a
#: worse failure than a few megabytes of held documents.
UNDO_DEPTH = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AnnotationStore:
    """Holds one version's labels and the history of how they got there."""

    take_dir: Path
    document: AnnotationDocument
    annotator: str = ""
    #: Resolves an anchor to a frame position; raises when it cannot.
    resolve: Optional[Callable[[Anchor], int]] = None
    #: Builds an anchor for a frame position.
    anchor_at: Optional[Callable[[int], Anchor]] = None
    frames: int = 0
    known_exercises: tuple[str, ...] = ()
    known_error_classes: tuple[str, ...] = ()
    #: This version's skeleton. Roles are checked against it, because a role
    #: is a claim about a joint and the formats do not have the same joints:
    #: BODY_18 has no pelvis, spine or head; BODY_38 has no head-centre or
    #: hand. ``None`` means the skeleton is unknown and no such check is made
    #: - the honest position when the version did not record one, rather than
    #: a guess that would reject good labels.
    skeleton: Optional[SkeletonSpec] = None

    _undo: list[AnnotationDocument] = field(default_factory=list, repr=False)
    _redo: list[AnnotationDocument] = field(default_factory=list, repr=False)
    _dirty: bool = False
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------- skeleton
    def unavailable_roles(self, roles: Sequence[str]) -> tuple[str, ...]:
        """Which of ``roles`` this version's skeleton cannot provide."""
        if self.skeleton is None or not roles:
            return ()
        return missing_roles(self.skeleton, tuple(roles))

    def available_roles(self) -> tuple[str, ...]:
        """The roles this version can actually carry, in a stable order."""
        if self.skeleton is None:
            return ()
        resolved = resolve_roles(self.skeleton)
        return tuple(sorted(r for r, index in resolved.items() if index is not None))

    # -------------------------------------------------------- notification
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _changed(self) -> None:
        self._dirty = True
        for listener in list(self._listeners):
            listener()

    # --------------------------------------------------------------- history
    def _begin(self) -> AnnotationDocument:
        """Snapshot before a change. One call per user decision."""
        snapshot = copy.deepcopy(self.document)
        self._undo.append(snapshot)
        if len(self._undo) > UNDO_DEPTH:
            del self._undo[0]
        self._redo.clear()
        return snapshot

    def _commit(self, samples: Sequence[MovementSample]) -> None:
        """Apply a new sample list, after checking it produces no bad label."""
        candidate = replace(
            self.document,
            samples=tuple(samples),
            revision=self.document.revision + 1,
            annotator=self.annotator or self.document.annotator,
            updated_at=_now(),
        )
        problems = self._validate(candidate)
        if problems:
            # Rejected whole. A partially applied edit is a state the annotator
            # never chose, and on disk it is indistinguishable from one they did.
            self._undo.pop()
            raise ValidationError(
                problems[0]["message"],
                code=problems[0]["code"],
                details={"problems": problems},
            )
        self.document = candidate
        self._changed()

    def _validate(self, document: AnnotationDocument) -> list[dict[str, Any]]:
        if self.resolve is None:
            return []
        return validate_document(
            document,
            resolve=self.resolve,
            frames=self.frames,
            known_exercises=self.known_exercises,
            known_error_classes=self.known_error_classes,
        )

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self.document))
        self.document = self._undo.pop()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self.document))
        self.document = self._redo.pop()
        self._changed()
        return True

    # ------------------------------------------------------------ movements
    def add_movement(self, start: int, end: int) -> MovementSample:
        """Draw a new movement between two frame positions, both inclusive."""
        first, last = (start, end) if start <= end else (end, start)
        sample = MovementSample(
            sample_id=new_id("mov"),
            start=self._anchor(first),
            end=self._anchor(last),
        )
        self._begin()
        self._commit([*self.document.samples, sample])
        return sample

    def set_movement_bounds(self, sample_id: str, start: int, end: int) -> None:
        """Move a movement's edges, carrying its error intervals with it.

        An interval that would fall outside the new bounds is **clipped**, and
        one that falls outside entirely is removed - both reported through the
        normal undo step, so a drag that ate an interval can be taken back.
        """
        sample = self._require(sample_id)
        first, last = (start, end) if start <= end else (end, start)
        kept: list[ErrorInterval] = []
        for interval in sample.errors:
            low = max(first, self._position(interval.start))
            high = min(last, self._position(interval.end))
            if low > high:
                continue
            kept.append(
                replace(interval, start=self._anchor(low), end=self._anchor(high))
            )
        updated = replace(
            sample,
            start=self._anchor(first),
            end=self._anchor(last),
            errors=tuple(kept),
        )
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))

    def label_movement(
        self, sample_id: str, exercise: str, *, note: str = "", reviewed: bool = True
    ) -> None:
        """Assign the exercise class and stamp the review, in one step.

        The stamp is what separates "correct" from "nobody looked yet": with no
        error intervals, those two states are identical in the data and only
        the stamp tells them apart.
        """
        sample = self._require(sample_id)
        updated = replace(
            sample,
            exercise=exercise,
            note=note or sample.note,
            reviewed_at=_now() if reviewed else "",
        )
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))

    def set_excluded(self, sample_id: str, excluded: bool) -> None:
        sample = self._require(sample_id)
        self._begin()
        self._commit(
            self._replace_sample(sample_id, replace(sample, excluded=excluded))
        )

    def remove_movement(self, sample_id: str) -> None:
        self._require(sample_id)
        self._begin()
        self._commit([s for s in self.document.samples if s.sample_id != sample_id])

    # --------------------------------------------------------------- errors
    def add_error(self, sample_id: str, start: int, end: int) -> ErrorInterval:
        """Draw an error interval inside a movement.

        A range that overhangs the movement is trimmed to it - dragging a
        little past the edge is a normal thing to do with a mouse. A range that
        misses the movement entirely is refused: clipping it would plant a
        zero-length error on the boundary frame, which is a label the annotator
        never made and cannot see they made.
        """
        sample = self._require(sample_id)
        low = self._position(sample.start)
        high = self._position(sample.end)
        first, last = (start, end) if start <= end else (end, start)
        first, last = self._clip_into(first, last, low, high, sample_id)
        interval = ErrorInterval(
            interval_id=new_id("err"),
            start=self._anchor(first),
            end=self._anchor(last),
        )
        updated = replace(sample, errors=(*sample.errors, interval))
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))
        return interval

    def set_error_bounds(self, sample_id: str, interval_id: str, start: int, end: int) -> None:
        sample = self._require(sample_id)
        low = self._position(sample.start)
        high = self._position(sample.end)
        first, last = (start, end) if start <= end else (end, start)
        first, last = self._clip_into(first, last, low, high, sample_id)
        updated = self._replace_interval(
            sample,
            interval_id,
            lambda interval: replace(
                interval, start=self._anchor(first), end=self._anchor(last)
            ),
        )
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))

    def label_error(
        self,
        sample_id: str,
        interval_id: str,
        *,
        error_class: str,
        affected_roles: Sequence[str] = (),
        joint_status: JointStatus = JointStatus.UNREVIEWED,
        note: str = "",
        roles_origin: RolesOrigin = RolesOrigin.UNKNOWN,
        roles_revision: int = 0,
    ) -> None:
        """Class, joints, status, provenance and note in **one** operation.

        One operation and one undo step, because they are one decision.
        Applying them separately could leave an interval carrying a new class
        with the previous interval's joints - a wrong label that looks
        complete - and it would let the joints and the record of *where they
        came from* disagree, which is worse: an inherited default would then
        be indistinguishable from a reviewed one.
        """
        sample = self._require(sample_id)
        roles = tuple(affected_roles)
        unavailable = self.unavailable_roles(roles)
        if unavailable:
            # Refused rather than dropped. Silently keeping the roles this
            # format does have would store a *different* claim from the one
            # that was made, and nothing downstream could tell.
            raise ValidationError(
                "Bu kaydın iskeleti şu eklemleri içermiyor: "
                + ", ".join(role.replace("_", " ") for role in unavailable),
                field="affected_roles",
                code="roles_not_in_skeleton",
                remedy=(
                    "Bu sürümde bulunan eklemleri seçin ya da kaydı bu "
                    "eklemleri içeren bir gövde biçimiyle yeniden işleyin."
                ),
                details={
                    "roles": list(roles),
                    "unavailable": list(unavailable),
                    "skeleton": self.skeleton.name if self.skeleton else "",
                },
            )
        if roles and roles_origin is RolesOrigin.UNKNOWN:
            raise ValidationError(
                "Eklem listesi kökeni bildirilmeden yazılamaz.",
                code="roles_without_origin",
                details={"roles": list(roles)},
            )
        if roles and joint_status is not JointStatus.SELECTED:
            # Not silently promoted to SELECTED. That status means a person
            # looked at the skeleton and picked those joints; inferring it from
            # the presence of a list would record a review that never happened.
            raise ValidationError(
                "Eklem işaretlendiyse eklem durumu 'seçildi' olmalıdır.",
                code="roles_without_selected_status",
                details={"joint_status": joint_status.value, "roles": list(roles)},
            )
        if joint_status is JointStatus.SELECTED and not roles:
            raise ValidationError(
                "Eklem durumu 'seçildi' ise en az bir eklem işaretlenmelidir.",
                code="selected_without_roles",
            )
        updated = self._replace_interval(
            sample,
            interval_id,
            lambda interval: replace(
                interval,
                error_class=error_class,
                affected_roles=roles,
                joint_status=joint_status,
                note=note,
                roles_origin=roles_origin if roles else RolesOrigin.UNKNOWN,
                roles_revision=int(roles_revision) if roles else 0,
            ),
        )
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))

    def apply_class_defaults(
        self,
        sample_id: str,
        interval_id: str,
        *,
        error_class: str,
        default_roles: Sequence[str],
        revision: int,
        note: str = "",
    ) -> None:
        """Label an interval with a class and the joints that class declares.

        This is the fast path JOINT-04 asks for: choosing a class the project
        already knows applies its joints without asking again. What it records
        is that the joints were *inherited* - ``roles_origin`` is
        ``class_default`` and the revision copied is written down - so nothing
        downstream can mistake them for a per-repetition judgement, and a
        later edit to the class leaves this interval untouched.
        """
        roles = tuple(dict.fromkeys(str(role) for role in default_roles if role))
        self.label_error(
            sample_id,
            interval_id,
            error_class=error_class,
            affected_roles=roles,
            joint_status=(
                JointStatus.SELECTED if roles else JointStatus.UNREVIEWED
            ),
            note=note,
            roles_origin=RolesOrigin.CLASS_DEFAULT if roles else RolesOrigin.UNKNOWN,
            roles_revision=int(revision) if roles else 0,
        )

    def remove_error(self, sample_id: str, interval_id: str) -> None:
        sample = self._require(sample_id)
        updated = replace(
            sample,
            errors=tuple(i for i in sample.errors if i.interval_id != interval_id),
        )
        self._begin()
        self._commit(self._replace_sample(sample_id, updated))

    # ------------------------------------------------------------- querying
    def position_of(self, anchor: Anchor) -> int:
        return self._position(anchor)

    def sample_bounds(self, sample_id: str) -> tuple[int, int]:
        sample = self._require(sample_id)
        return self._position(sample.start), self._position(sample.end)

    def error_bounds(self, sample_id: str, interval_id: str) -> tuple[int, int]:
        sample = self._require(sample_id)
        interval = next(
            (i for i in sample.errors if i.interval_id == interval_id), None
        )
        if interval is None:
            raise KeyError(interval_id)
        return self._position(interval.start), self._position(interval.end)

    def sample_at(self, position: int) -> Optional[MovementSample]:
        for sample in self.document.samples:
            if self._position(sample.start) <= position <= self._position(sample.end):
                return sample
        return None

    def readiness(self, sample_id: str) -> Readiness:
        return self._require(sample_id).readiness(self.known_exercises)

    def progress(self) -> tuple[int, int]:
        """``(ready, total)`` over the movements that are not excluded."""
        active = [s for s in self.document.samples if not s.excluded]
        ready = sum(
            1 for s in active if s.readiness(self.known_exercises).is_exportable
        )
        return ready, len(active)

    def next_unfinished(self, after: Optional[str] = None) -> Optional[MovementSample]:
        """The next movement that still needs something, for "Sonraki eksik"."""
        ordered = sorted(
            (s for s in self.document.samples if not s.excluded),
            key=lambda s: self._position(s.start),
        )
        keys = [s.sample_id for s in ordered]
        start = (keys.index(after) + 1) if after in keys else 0
        for sample in [*ordered[start:], *ordered[:start]]:
            if not sample.readiness(self.known_exercises).is_exportable:
                return sample
        return None

    # -------------------------------------------------------------- writing
    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def flush(self) -> Optional[Path]:
        """Write if anything changed. Called on close and on version switch."""
        if not self._dirty:
            return None
        path = save_annotations(self.take_dir, self.document)
        self._dirty = False
        return path

    # ------------------------------------------------------------- internals
    def _require(self, sample_id: str) -> MovementSample:
        sample = self.document.sample(sample_id)
        if sample is None:
            raise KeyError(sample_id)
        return sample

    def _replace_sample(
        self, sample_id: str, updated: MovementSample
    ) -> list[MovementSample]:
        return [
            updated if s.sample_id == sample_id else s for s in self.document.samples
        ]

    @staticmethod
    def _replace_interval(
        sample: MovementSample, interval_id: str, change: Callable[[ErrorInterval], ErrorInterval]
    ) -> MovementSample:
        intervals = [
            change(i) if i.interval_id == interval_id else i for i in sample.errors
        ]
        if not any(i.interval_id == interval_id for i in sample.errors):
            raise KeyError(interval_id)
        return replace(sample, errors=tuple(intervals))

    def _clip_into(
        self, first: int, last: int, low: int, high: int, sample_id: str
    ) -> tuple[int, int]:
        """Trim an overlapping range to ``low..high``; refuse one that misses."""
        if last < low or first > high:
            raise ValidationError(
                "Hata aralığı hareketin dışında.",
                code="interval_outside_sample",
                details={"sample_id": sample_id, "sample": [low, high],
                         "interval": [first, last]},
            )
        return max(low, first), min(high, last)

    def _anchor(self, position: int) -> Anchor:
        if self.anchor_at is None:
            raise RuntimeError("Anchor üretici verilmedi.")
        return self.anchor_at(max(0, min(self.frames - 1, int(position))))

    def _position(self, anchor: Anchor) -> int:
        if self.resolve is None:
            raise RuntimeError("Anchor çözücü verilmedi.")
        return self.resolve(anchor)


__all__ = ["UNDO_DEPTH", "AnnotationStore"]
