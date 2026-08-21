"""Movement-sample and error-interval editing, with undo/redo and autosave.

The repository owns the in-memory labels of one take, applies edits as whole-
state snapshots, and persists to the annotation sidecar. It never touches
``take.json``: curation and capture provenance stay in different files.

Two levels, one owner
---------------------
Movement samples are top-level ranges in the take. Error intervals live *inside*
one sample. Every interval edit therefore goes through its parent sample, which
is what guarantees an interval can never drift outside its movement.

Edits that could lose work report what they did
-----------------------------------------------
Narrowing a sample and merging two samples can both destroy labels. Neither is
allowed to do so quietly: they return a report describing exactly what was
clamped, dropped or carried over, so the screen can tell the user and undo can
put it back.

Autosave is *explicit*. Every mutation marks the repository dirty and returns;
the caller (a Qt timer in the GUI, a direct call in tests) decides when
:meth:`save_if_dirty` runs. That keeps the persistence policy visible and makes
the behaviour identical with and without a GUI.

Undo history stores full snapshots of the sample list. A take has tens of
samples, not thousands, so snapshotting is simpler and far less error-prone
than an inverse operation per command.

**Undo does not un-define an error class.** Creating a class edits the
project's vocabulary, which is configuration shared by every take; undo works
on this take's annotations. Undoing an interval therefore removes the interval
and leaves the class available - the behaviour a user expects from a picker
that "adds to the list".
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.logging import get_logger
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import (
    Correctness,
    SampleReadiness,
    SegmentSource,
    SegmentStatus,
)
from kinecapture.domain.labels import LabelOption
from kinecapture.domain.project import (
    ErrorInterval,
    MovementSample,
    SampleProblem,
    evaluate_sample,
    renumber_samples,
    validate_samples,
)

logger = get_logger(__name__)

#: How many undo steps to keep. Deep enough for a labelling session, shallow
#: enough that memory stays trivial.
MAX_HISTORY = 100

ChangeListener = Callable[[], None]


@dataclass
class BoundsChangeReport:
    """What happened to a sample's error intervals when its bounds moved."""

    clamped: list[str] = field(default_factory=list)
    removed: list[ErrorInterval] = field(default_factory=list)

    @property
    def is_lossless(self) -> bool:
        return not self.removed

    @property
    def changed_anything(self) -> bool:
        return bool(self.clamped or self.removed)

    def message(self) -> str:
        """A sentence for the status bar, or ``""`` when nothing happened."""
        parts: list[str] = []
        if self.clamped:
            parts.append(f"{len(self.clamped)} hata aralığı hareketin içine kısaltıldı")
        if self.removed:
            parts.append(
                f"{len(self.removed)} hata aralığı hareket dışında kaldığı için kaldırıldı"
            )
        if not parts:
            return ""
        return " ve ".join(parts) + ". Geri almak için Ctrl+Z."


@dataclass
class MergeReport:
    """What happened to the labels of two samples that were merged."""

    kept_exercise: str = ""
    kept_correctness: str = ""
    dropped_exercise: str = ""
    dropped_correctness: str = ""
    merged_intervals: int = 0

    @property
    def had_conflict(self) -> bool:
        return bool(self.dropped_exercise or self.dropped_correctness)

    def message(self) -> str:
        if not self.had_conflict:
            return (
                f"Hareketler birleştirildi; {self.merged_intervals} hata aralığı korundu."
            )
        details: list[str] = []
        if self.dropped_exercise:
            details.append(f"egzersiz '{self.dropped_exercise}'")
        if self.dropped_correctness:
            details.append(f"karar '{self.dropped_correctness}'")
        return (
            "Hareketler birleştirildi. Farklı olan "
            + " ve ".join(details)
            + " kaydın geçmişine yazıldı, silinmedi. Geri almak için Ctrl+Z."
        )


class AnnotationRepository:
    """Editable view of one take's movement samples and their error intervals."""

    def __init__(
        self,
        workspace: ProjectWorkspace,
        take,  # kinecapture.domain.project.Take
        *,
        frame_count: Optional[int] = None,
        annotator: str = "",
    ) -> None:
        self.workspace = workspace
        self.take = take
        self.frame_count = frame_count
        self.annotator = annotator
        self._samples: list[MovementSample] = workspace.load_samples(take)
        renumber_samples(self._samples)
        self._undo: list[list[MovementSample]] = []
        self._redo: list[list[MovementSample]] = []
        self._dirty = False
        self._last_saved_at: Optional[str] = None
        self._listeners: list[ChangeListener] = []

    # ------------------------------------------------------------- exposure
    @property
    def samples(self) -> tuple[MovementSample, ...]:
        return tuple(self._samples)

    @property
    def active_samples(self) -> tuple[MovementSample, ...]:
        return tuple(s for s in self._samples if s.is_active)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def last_saved_at(self) -> Optional[str]:
        return self._last_saved_at

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def known_error_codes(self) -> tuple[str, ...]:
        return self.workspace.label_schema.error_type_codes()

    @property
    def ready_count(self) -> int:
        """Samples that would actually be exported."""
        return sum(1 for s in self.active_samples if self.readiness(s).is_ready)

    #: The screen says "labelled" for exactly the samples the exporter takes.
    labelled_count = ready_count

    def readiness(self, sample: MovementSample) -> SampleReadiness:
        return evaluate_sample(sample, known_error_codes=self.known_error_codes)[0]

    def problems(self, sample: MovementSample) -> list[SampleProblem]:
        return evaluate_sample(sample, known_error_codes=self.known_error_codes)[1]

    def add_change_listener(self, listener: ChangeListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def find(self, sample_id: str) -> Optional[MovementSample]:
        return next((s for s in self._samples if s.sample_id == sample_id), None)

    def sample_at_frame(self, frame: int) -> Optional[MovementSample]:
        for sample in self._samples:
            if sample.contains(frame):
                return sample
        return None

    def validation_problems(self) -> list[dict[str, Any]]:
        return validate_samples(self._samples, frame_count=self.frame_count)

    # -------------------------------------------------------------- history
    def _snapshot(self) -> None:
        """Push the current state onto the undo stack before mutating it."""
        self._undo.append(copy.deepcopy(self._samples))
        if len(self._undo) > MAX_HISTORY:
            del self._undo[0]
        self._redo.clear()

    def _changed(self) -> None:
        renumber_samples(self._samples)
        self._dirty = True
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Annotation dinleyicisi hata verdi")

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self._samples))
        self._samples = self._undo.pop()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self._samples))
        self._samples = self._redo.pop()
        self._changed()
        return True

    # ------------------------------------------------------ movement samples
    def create_sample(
        self,
        start_frame: int,
        end_frame: int,
        *,
        source: SegmentSource = SegmentSource.MANUAL,
        start_timestamp_ns: Optional[int] = None,
        end_timestamp_ns: Optional[int] = None,
        exercise: str = "",
    ) -> MovementSample:
        """Add a movement range, clamped to the take's real length."""
        start, end = self._clamp_to_take(start_frame, end_frame)
        sample = MovementSample.create(
            take_id=self.take.take_id,
            start_frame=start,
            end_frame=end,
            source=source,
            start_timestamp_ns=start_timestamp_ns,
            end_timestamp_ns=end_timestamp_ns,
            exercise=exercise,
            annotator=self.annotator,
        )
        self._snapshot()
        self._samples.append(sample)
        self._changed()
        return sample

    def update_sample_bounds(
        self, sample_id: str, start_frame: int, end_frame: int
    ) -> BoundsChangeReport:
        """Move a movement's boundaries, keeping its error intervals inside.

        Narrowing a sample can strand an error interval. Rather than letting an
        interval silently sit outside its parent - which would corrupt the
        export contract - overlapping intervals are clamped and fully-outside
        intervals are removed, and both are reported so the user is told and can
        undo.
        """
        sample = self._require(sample_id)
        start, end = self._clamp_to_take(start_frame, end_frame)
        if (sample.start_frame, sample.end_frame) == (start, end):
            return BoundsChangeReport()

        self._snapshot()
        sample.start_frame, sample.end_frame = start, end

        report = BoundsChangeReport()
        surviving: list[ErrorInterval] = []
        for interval in sample.error_intervals:
            if interval.end_frame < start or interval.start_frame > end:
                report.removed.append(interval)
                continue
            new_start, new_end = sample.clamp(interval.start_frame, interval.end_frame)
            if (new_start, new_end) != (interval.start_frame, interval.end_frame):
                interval.start_frame, interval.end_frame = new_start, new_end
                interval.touch()
                report.clamped.append(interval.interval_id)
            surviving.append(interval)
        sample.error_intervals = surviving

        sample.touch()
        self._changed()
        return report

    def split_sample(
        self, sample_id: str, at_frame: int
    ) -> tuple[MovementSample, MovementSample]:
        """Split one movement into two at ``at_frame``.

        Error intervals follow the half they fall in; an interval straddling the
        cut is divided so no localised error is lost. The label is inherited by
        both halves, because splitting is a boundary correction rather than a
        statement that the labels were wrong.
        """
        sample = self._require(sample_id)
        if not sample.start_frame < at_frame <= sample.end_frame:
            raise ValidationError(
                "Bölme noktası hareket aralığının içinde olmalıdır.",
                field="at_frame",
                code="split_out_of_range",
            )
        if at_frame - sample.start_frame < 1 or sample.end_frame - at_frame < 0:
            raise ValidationError(
                "Bölme sonrası her iki parça da en az 2 kare olmalıdır.",
                field="at_frame",
                code="split_too_short",
            )
        if (at_frame - 1) - sample.start_frame < 1 or sample.end_frame - at_frame < 1:
            raise ValidationError(
                "Bölme sonrası her iki parça da en az 2 kare olmalıdır.",
                field="at_frame",
                code="split_too_short",
            )

        self._snapshot()
        tail = MovementSample.create(
            take_id=self.take.take_id,
            start_frame=at_frame,
            end_frame=sample.end_frame,
            source=sample.source,
            exercise=sample.exercise,
            correctness=sample.correctness,
            note=sample.note,
            annotator=self.annotator or sample.annotator,
        )

        head_intervals: list[ErrorInterval] = []
        tail_intervals: list[ErrorInterval] = []
        for interval in sample.error_intervals:
            if interval.end_frame < at_frame:
                head_intervals.append(interval)
            elif interval.start_frame >= at_frame:
                tail_intervals.append(interval)
            else:
                # Straddles the cut: keep both halves rather than losing one.
                head_part = copy.deepcopy(interval)
                head_part.end_frame = at_frame - 1
                head_part.touch()
                head_intervals.append(head_part)

                tail_part = ErrorInterval.create(
                    at_frame,
                    interval.end_frame,
                    interval.error_code,
                    source=interval.source,
                    note=interval.note,
                )
                tail_intervals.append(tail_part)

        sample.end_frame = at_frame - 1
        sample.error_intervals = head_intervals
        sample.touch()
        tail.error_intervals = tail_intervals

        self._samples.append(tail)
        self._changed()
        return sample, tail

    def merge_samples(self, first_id: str, second_id: str) -> MergeReport:
        """Merge two movements into the span covering both.

        Conflicting labels are never dropped on the floor: the earlier sample's
        label wins, and the other's is written into the surviving sample's
        ``legacy`` block so the decision is recoverable and auditable.
        """
        first, second = self._require(first_id), self._require(second_id)
        if first.sample_id == second.sample_id:
            raise ValidationError(
                "Bir hareket kendisiyle birleştirilemez.",
                field="sample_id",
                code="merge_same_sample",
            )

        self._snapshot()
        keep, drop = (
            (first, second) if first.start_frame <= second.start_frame else (second, first)
        )
        report = MergeReport(
            kept_exercise=keep.exercise, kept_correctness=keep.correctness.value
        )

        if drop.exercise and drop.exercise != keep.exercise:
            report.dropped_exercise = drop.exercise
        if drop.correctness.is_decided and drop.correctness is not keep.correctness:
            report.dropped_correctness = drop.correctness.value
        if not keep.exercise and drop.exercise:
            # Nothing to conflict with - just adopt it.
            keep.exercise = drop.exercise
            report.kept_exercise = drop.exercise
            report.dropped_exercise = ""
        if not keep.correctness.is_decided and drop.correctness.is_decided:
            keep.correctness = drop.correctness
            report.kept_correctness = drop.correctness.value
            report.dropped_correctness = ""

        if report.had_conflict:
            history = list(keep.legacy.get("merged_from") or [])
            history.append(
                {
                    "sample_id": drop.sample_id,
                    "exercise": drop.exercise,
                    "correctness": drop.correctness.value,
                    "note": drop.note,
                    "merged_at": utc_now_iso(),
                }
            )
            keep.legacy["merged_from"] = history

        keep.start_frame = min(first.start_frame, second.start_frame)
        keep.end_frame = max(first.end_frame, second.end_frame)
        keep.error_intervals = keep.error_intervals + drop.error_intervals
        report.merged_intervals = len(keep.error_intervals)
        if drop.note and drop.note not in keep.note:
            keep.note = f"{keep.note}\n{drop.note}".strip()
        keep.touch()

        self._samples = [s for s in self._samples if s.sample_id != drop.sample_id]
        self._changed()
        return report

    def set_sample_status(
        self, sample_id: str, status: SegmentStatus
    ) -> MovementSample:
        """Exclude a movement from the dataset, or restore it."""
        sample = self._require(sample_id)
        if sample.status is status:
            return sample
        self._snapshot()
        sample.status = status
        sample.touch()
        self._changed()
        return sample

    def delete_sample(self, sample_id: str) -> None:
        """Remove a movement range.

        This deletes curation, never capture data: the underlying frames are
        untouched and the range can be recreated.
        """
        self._require(sample_id)
        self._snapshot()
        self._samples = [s for s in self._samples if s.sample_id != sample_id]
        self._changed()

    def create_samples_from_markers(
        self, marker_frames: Iterable[int], *, final_frame: Optional[int] = None
    ) -> list[MovementSample]:
        """Turn operator markers into movement boundary suggestions.

        Markers become ``OPERATOR_MARKER`` samples, which stay distinguishable
        from hand-drawn ones in the exported dataset.
        """
        boundaries = sorted({int(frame) for frame in marker_frames})
        if len(boundaries) < 2:
            end = final_frame if final_frame is not None else self.frame_count
            if not boundaries or end is None or end <= boundaries[0]:
                return []
            boundaries.append(int(end))

        pairs = [
            (start, end)
            for start, end in zip(boundaries, boundaries[1:])
            if end - start >= 2
        ]
        if not pairs:
            return []

        self._snapshot()
        created: list[MovementSample] = []
        for start, end in pairs:
            low, high = self._clamp_to_take(start, max(start + 1, end - 1))
            sample = MovementSample.create(
                take_id=self.take.take_id,
                start_frame=low,
                end_frame=high,
                source=SegmentSource.OPERATOR_MARKER,
                annotator=self.annotator,
            )
            self._samples.append(sample)
            created.append(sample)
        self._changed()
        return created

    # --------------------------------------------------------------- labels
    def label_sample(
        self,
        sample_id: str,
        *,
        exercise: Optional[str] = None,
        correctness: Optional[Correctness] = None,
        note: Optional[str] = None,
    ) -> MovementSample:
        """Apply label changes. Only the arguments that are not ``None`` change."""
        sample = self._require(sample_id)
        self._snapshot()
        if exercise is not None:
            sample.exercise = exercise
        if correctness is not None:
            sample.correctness = Correctness.parse(correctness)
        if note is not None:
            sample.note = note
        if self.annotator:
            sample.annotator = self.annotator
        sample.updated_at = utc_now_iso()
        self._changed()
        return sample

    def copy_label_from(self, source_id: str, target_id: str) -> MovementSample:
        """Reuse another movement's label - the fastest common action.

        Error intervals are *not* copied: they are timings specific to their own
        movement, and pasting them onto a different span would fabricate
        localisations nobody reviewed.
        """
        source, target = self._require(source_id), self._require(target_id)
        self._snapshot()
        target.exercise = source.exercise
        target.correctness = source.correctness
        target.note = source.note
        if self.annotator:
            target.annotator = self.annotator
        target.updated_at = utc_now_iso()
        self._changed()
        return target

    def apply_to_all(
        self,
        *,
        exercise: Optional[str] = None,
        correctness: Optional[Correctness] = None,
    ) -> int:
        """Bulk-label every active movement. Returns how many changed."""
        if exercise is None and correctness is None:
            return 0
        targets = [sample for sample in self._samples if sample.is_active]
        if not targets:
            return 0
        self._snapshot()
        for sample in targets:
            if exercise is not None:
                sample.exercise = exercise
            if correctness is not None:
                sample.correctness = Correctness.parse(correctness)
            if self.annotator:
                sample.annotator = self.annotator
            sample.updated_at = utc_now_iso()
        self._changed()
        return len(targets)

    # ------------------------------------------------------- error intervals
    def create_error_interval(
        self,
        sample_id: str,
        start_frame: int,
        end_frame: int,
        *,
        error_code: str = "",
        start_timestamp_ns: Optional[int] = None,
        end_timestamp_ns: Optional[int] = None,
        source: SegmentSource = SegmentSource.MANUAL,
    ) -> ErrorInterval:
        """Add an error range inside one movement.

        The range is clamped into the parent, so an interval can never be
        created outside the movement it belongs to.
        """
        sample = self._require(sample_id)
        start, end = sample.clamp(start_frame, end_frame)
        if end <= start:
            # A click rather than a drag: give it a minimum usable width inside
            # the parent instead of storing an empty interval.
            end = min(sample.end_frame, start + 1)
            start = max(sample.start_frame, min(start, end - 1))
        if end <= start:
            raise ValidationError(
                "Hata aralığı için hareket çok kısa.",
                field="end_frame",
                code="interval_no_room",
            )

        interval = ErrorInterval.create(
            start,
            end,
            error_code,
            start_timestamp_ns=start_timestamp_ns,
            end_timestamp_ns=end_timestamp_ns,
            source=source,
        )
        self._snapshot()
        sample.error_intervals.append(interval)
        sample.touch()
        self._changed()
        return interval

    def update_error_interval_bounds(
        self, sample_id: str, interval_id: str, start_frame: int, end_frame: int
    ) -> ErrorInterval:
        """Move or resize an error range, clamped to its parent movement."""
        sample = self._require(sample_id)
        interval = self._require_interval(sample, interval_id)
        start, end = sample.clamp(start_frame, end_frame)
        if end < start:
            start, end = end, start
        if (interval.start_frame, interval.end_frame) == (start, end):
            return interval
        self._snapshot()
        interval.start_frame, interval.end_frame = start, end
        interval.touch()
        sample.touch()
        self._changed()
        return interval

    def set_error_interval_class(
        self, sample_id: str, interval_id: str, error_code: str
    ) -> ErrorInterval:
        """Assign an error class to an interval."""
        sample = self._require(sample_id)
        interval = self._require_interval(sample, interval_id)
        if interval.error_code == error_code:
            return interval
        self._snapshot()
        interval.error_code = error_code
        interval.touch()
        sample.touch()
        self._changed()
        return interval

    def set_error_interval_note(
        self, sample_id: str, interval_id: str, note: str
    ) -> ErrorInterval:
        sample = self._require(sample_id)
        interval = self._require_interval(sample, interval_id)
        if interval.note == note:
            return interval
        self._snapshot()
        interval.note = note
        interval.touch()
        self._changed()
        return interval

    def delete_error_interval(self, sample_id: str, interval_id: str) -> None:
        sample = self._require(sample_id)
        self._require_interval(sample, interval_id)
        self._snapshot()
        sample.error_intervals = [
            i for i in sample.error_intervals if i.interval_id != interval_id
        ]
        sample.touch()
        self._changed()

    def intervals_at_frame(
        self, sample_id: str, frame: int
    ) -> list[ErrorInterval]:
        """Every error interval covering ``frame`` - overlaps included."""
        sample = self._require(sample_id)
        return [i for i in sample.error_intervals if i.start_frame <= frame <= i.end_frame]

    # -------------------------------------------------- project vocabulary
    def ensure_error_class(self, name: str, description: str = "") -> LabelOption:
        """Find or create an error class and persist it to the project.

        Creating a class is a *project* edit, not a take edit: it is written to
        ``label_schema.json`` immediately and atomically, survives a restart,
        and appears in every other take's picker. It is deliberately outside the
        undo history (see the module docstring).
        """
        cleaned = " ".join((name or "").split())
        if not cleaned:
            raise ValidationError(
                "Hata türü adı boş olamaz.",
                field="error_type",
                code="error_type_name_empty",
            )
        schema = self.workspace.label_schema
        existing = schema.match_error_type(cleaned)
        if existing is not None:
            return existing
        option = schema.add_error_type(cleaned, description)
        self.workspace.save_label_schema(schema)
        logger.info(
            "Hata türü eklendi: %s (%s)", option.label, option.code
        )
        return option

    def assign_new_error_class(
        self, sample_id: str, interval_id: str, name: str
    ) -> tuple[ErrorInterval, LabelOption]:
        """Create-or-reuse a class and assign it in one user action."""
        option = self.ensure_error_class(name)
        interval = self.set_error_interval_class(sample_id, interval_id, option.code)
        return interval, option

    def used_error_codes(self) -> set[str]:
        """Error classes referenced by this take's labels."""
        return {
            interval.error_code
            for sample in self._samples
            for interval in sample.error_intervals
            if interval.error_code
        }

    # ---------------------------------------------------------- persistence
    def save(self) -> tuple[MovementSample, ...]:
        """Write the sidecar unconditionally."""
        saved = self.workspace.save_samples(self.take, self._samples)
        self._samples = list(saved)
        renumber_samples(self._samples)
        self._dirty = False
        self._last_saved_at = utc_now_iso()
        return tuple(self._samples)

    def save_if_dirty(self) -> bool:
        """Write only when something changed. Returns whether it wrote."""
        if not self._dirty:
            return False
        self.save()
        return True

    # -------------------------------------------------------------- helpers
    def _require(self, sample_id: str) -> MovementSample:
        sample = self.find(sample_id)
        if sample is None:
            raise ValidationError(
                "Hareket bulunamadı; listeyi yenileyin.",
                field="sample_id",
                code="sample_not_found",
            )
        return sample

    @staticmethod
    def _require_interval(
        sample: MovementSample, interval_id: str
    ) -> ErrorInterval:
        interval = sample.interval(interval_id)
        if interval is None:
            raise ValidationError(
                "Hata aralığı bulunamadı; listeyi yenileyin.",
                field="interval_id",
                code="interval_not_found",
            )
        return interval

    def _clamp_to_take(self, start_frame: int, end_frame: int) -> tuple[int, int]:
        """Keep a range inside the take, ordered, and at least two frames."""
        start, end = int(start_frame), int(end_frame)
        if end < start:
            start, end = end, start
        start = max(0, start)
        if self.frame_count is not None and self.frame_count > 0:
            limit = self.frame_count - 1
            start = min(start, limit)
            end = min(end, limit)
            if end <= start:
                start = max(0, min(start, limit - 1)) if limit >= 1 else 0
                end = min(limit, start + 1)
        elif end <= start:
            end = start + 1
        return start, end


__all__ = [
    "MAX_HISTORY",
    "AnnotationRepository",
    "BoundsChangeReport",
    "MergeReport",
]
