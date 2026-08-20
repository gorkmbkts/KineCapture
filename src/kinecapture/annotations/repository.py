"""Repetition and annotation editing, with undo/redo and autosave.

The repository owns the in-memory list of a take's repetitions, applies edits as
whole-state snapshots, and persists to the annotation sidecar. It never touches
``take.json``: curation and capture provenance stay in different files.

Autosave is *explicit* rather than magical. Every mutation marks the repository
dirty and returns; the caller (a Qt timer in the GUI, a direct call in tests)
decides when :meth:`save_if_dirty` runs. That keeps the persistence policy
visible and makes the behaviour identical with and without a GUI.

Undo history stores full snapshots. A take has tens of repetitions, not
thousands, so snapshotting is simpler and far less error-prone than an inverse
operation per command.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Iterable, Optional

from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.logging import get_logger
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import (
    AnnotationStatus,
    Correctness,
    SegmentSource,
    SegmentStatus,
)
from kinecapture.domain.project import (
    RepetitionSegment,
    Take,
    renumber_segments,
    validate_segments,
)

logger = get_logger(__name__)

#: How many undo steps to keep. Deep enough for a labelling session, shallow
#: enough that memory stays trivial.
MAX_HISTORY = 100

ChangeListener = Callable[[], None]


class AnnotationRepository:
    """Editable view of one take's repetitions."""

    def __init__(
        self,
        workspace: ProjectWorkspace,
        take: Take,
        *,
        frame_count: Optional[int] = None,
        annotator: str = "",
    ) -> None:
        self.workspace = workspace
        self.take = take
        self.frame_count = frame_count
        self.annotator = annotator
        self._segments: list[RepetitionSegment] = workspace.load_segments(take)
        renumber_segments(self._segments)
        self._undo: list[list[RepetitionSegment]] = []
        self._redo: list[list[RepetitionSegment]] = []
        self._dirty = False
        self._last_saved_at: Optional[str] = None
        self._listeners: list[ChangeListener] = []

    # ------------------------------------------------------------- exposure
    @property
    def segments(self) -> tuple[RepetitionSegment, ...]:
        return tuple(self._segments)

    @property
    def active_segments(self) -> tuple[RepetitionSegment, ...]:
        return tuple(s for s in self._segments if s.is_active)

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
    def labelled_count(self) -> int:
        return sum(1 for s in self.active_segments if s.annotation.is_labelled)

    def add_change_listener(self, listener: ChangeListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def find(self, segment_id: str) -> Optional[RepetitionSegment]:
        return next((s for s in self._segments if s.segment_id == segment_id), None)

    def index_of(self, segment_id: str) -> int:
        for position, segment in enumerate(self._segments):
            if segment.segment_id == segment_id:
                return position
        return -1

    def segment_at_frame(self, frame_position: int) -> Optional[RepetitionSegment]:
        for segment in self._segments:
            if segment.start_frame <= frame_position <= segment.end_frame:
                return segment
        return None

    def validation_problems(self) -> list[dict[str, Any]]:
        return validate_segments(self._segments, frame_count=self.frame_count)

    # -------------------------------------------------------------- history
    def _snapshot(self) -> None:
        """Push the current state onto the undo stack before mutating it."""
        self._undo.append(copy.deepcopy(self._segments))
        if len(self._undo) > MAX_HISTORY:
            del self._undo[0]
        self._redo.clear()

    def _changed(self) -> None:
        renumber_segments(self._segments)
        self._dirty = True
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Annotation dinleyicisi hata verdi")

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self._segments))
        self._segments = self._undo.pop()
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self._segments))
        self._segments = self._redo.pop()
        self._changed()
        return True

    # ------------------------------------------------------------ mutations
    def create_segment(
        self,
        start_frame: int,
        end_frame: int,
        *,
        source: SegmentSource = SegmentSource.MANUAL,
        start_timestamp_ns: Optional[int] = None,
        end_timestamp_ns: Optional[int] = None,
    ) -> RepetitionSegment:
        """Add a repetition interval, clamped to the take's real length."""
        start, end = self._clamp(start_frame, end_frame)
        segment = RepetitionSegment.create(
            take_id=self.take.take_id,
            start_frame=start,
            end_frame=end,
            source=source,
            start_timestamp_ns=start_timestamp_ns,
            end_timestamp_ns=end_timestamp_ns,
        )
        segment.annotation.annotator = self.annotator
        self._snapshot()
        self._segments.append(segment)
        self._changed()
        return segment

    def update_bounds(
        self, segment_id: str, start_frame: int, end_frame: int
    ) -> RepetitionSegment:
        """Move a repetition's boundaries."""
        segment = self._require(segment_id)
        start, end = self._clamp(start_frame, end_frame)
        if (segment.start_frame, segment.end_frame) == (start, end):
            return segment
        self._snapshot()
        segment.start_frame, segment.end_frame = start, end
        segment.touch()
        self._changed()
        return segment

    def split(self, segment_id: str, at_frame: int) -> tuple[RepetitionSegment, ...]:
        """Split one repetition into two at ``at_frame``."""
        segment = self._require(segment_id)
        if not segment.start_frame < at_frame <= segment.end_frame:
            raise ValidationError(
                "Bölme noktası tekrar aralığının içinde olmalıdır.",
                field="at_frame",
                code="split_out_of_range",
            )
        if at_frame - segment.start_frame < 1 or segment.end_frame - at_frame < 1:
            raise ValidationError(
                "Bölme sonrası her iki parça da en az 2 kare olmalıdır.",
                field="at_frame",
                code="split_too_short",
            )
        self._snapshot()
        tail = RepetitionSegment.create(
            take_id=self.take.take_id,
            start_frame=at_frame,
            end_frame=segment.end_frame,
            source=segment.source,
        )
        # The new half inherits the labels, because splitting a repetition is a
        # boundary correction, not a statement that the labels were wrong.
        tail.annotation = copy.deepcopy(segment.annotation)
        tail.annotation.touch()
        segment.end_frame = at_frame - 1
        segment.touch()
        self._segments.append(tail)
        self._changed()
        return segment, tail

    def merge(self, first_id: str, second_id: str) -> RepetitionSegment:
        """Merge two repetitions into the span covering both."""
        first, second = self._require(first_id), self._require(second_id)
        if first.segment_id == second.segment_id:
            raise ValidationError(
                "Bir tekrar kendisiyle birleştirilemez.",
                field="segment_id",
                code="merge_same_segment",
            )
        self._snapshot()
        keep, drop = (
            (first, second) if first.start_frame <= second.start_frame else (second, first)
        )
        keep.start_frame = min(first.start_frame, second.start_frame)
        keep.end_frame = max(first.end_frame, second.end_frame)
        keep.touch()
        self._segments = [s for s in self._segments if s.segment_id != drop.segment_id]
        self._changed()
        return keep

    def set_status(self, segment_id: str, status: SegmentStatus) -> RepetitionSegment:
        """Exclude a repetition from the dataset, or restore it."""
        segment = self._require(segment_id)
        if segment.status is status:
            return segment
        self._snapshot()
        segment.status = status
        segment.touch()
        self._changed()
        return segment

    def delete(self, segment_id: str) -> None:
        """Remove a repetition interval.

        This deletes curation, never capture data: the underlying frames are
        untouched and the interval can be recreated.
        """
        self._require(segment_id)
        self._snapshot()
        self._segments = [s for s in self._segments if s.segment_id != segment_id]
        self._changed()

    def annotate(
        self,
        segment_id: str,
        *,
        exercise: Optional[str] = None,
        correctness: Optional[Correctness] = None,
        error_types: Optional[Iterable[str]] = None,
        affected_joints: Optional[Iterable[str]] = None,
        movement_phase: Optional[str] = None,
        severity: Optional[float] = None,
        annotator_confidence: Optional[float] = None,
        note: Optional[str] = None,
        status: Optional[AnnotationStatus] = None,
    ) -> RepetitionSegment:
        """Apply label changes. Only the arguments that are not ``None`` change."""
        segment = self._require(segment_id)
        self._snapshot()
        annotation = segment.annotation
        if exercise is not None:
            annotation.exercise = exercise
        if correctness is not None:
            annotation.correctness = correctness
        if error_types is not None:
            annotation.error_types = tuple(error_types)
        if affected_joints is not None:
            annotation.affected_joints = tuple(affected_joints)
        if movement_phase is not None:
            annotation.movement_phase = movement_phase
        if severity is not None:
            annotation.severity = severity
        if annotator_confidence is not None:
            annotation.annotator_confidence = annotator_confidence
        if note is not None:
            annotation.note = note
        if status is not None:
            annotation.status = status
        if self.annotator:
            annotation.annotator = self.annotator
        annotation.touch()
        segment.updated_at = utc_now_iso()
        self._changed()
        return segment

    def copy_annotation_from(self, source_id: str, target_id: str) -> RepetitionSegment:
        """Reuse the previous repetition's labels - the fastest common action."""
        source, target = self._require(source_id), self._require(target_id)
        self._snapshot()
        target.annotation = copy.deepcopy(source.annotation)
        target.annotation.touch()
        if self.annotator:
            target.annotation.annotator = self.annotator
        target.updated_at = utc_now_iso()
        self._changed()
        return target

    def apply_to_all(
        self, *, exercise: Optional[str] = None, correctness: Optional[Correctness] = None
    ) -> int:
        """Bulk-label every active repetition. Returns how many changed."""
        if exercise is None and correctness is None:
            return 0
        targets = [segment for segment in self._segments if segment.is_active]
        if not targets:
            return 0
        self._snapshot()
        for segment in targets:
            if exercise is not None:
                segment.annotation.exercise = exercise
            if correctness is not None:
                segment.annotation.correctness = correctness
            if self.annotator:
                segment.annotation.annotator = self.annotator
            segment.annotation.touch()
        self._changed()
        return len(targets)

    def create_from_markers(
        self, marker_frames: Iterable[int], *, final_frame: Optional[int] = None
    ) -> list[RepetitionSegment]:
        """Turn operator markers into boundary suggestions.

        Markers become ``OPERATOR_MARKER`` segments, which stay distinguishable
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
        created: list[RepetitionSegment] = []
        for start, end in pairs:
            clamped_start, clamped_end = self._clamp(start, max(start + 1, end - 1))
            segment = RepetitionSegment.create(
                take_id=self.take.take_id,
                start_frame=clamped_start,
                end_frame=clamped_end,
                source=SegmentSource.OPERATOR_MARKER,
            )
            segment.annotation.annotator = self.annotator
            self._segments.append(segment)
            created.append(segment)
        self._changed()
        return created

    # ---------------------------------------------------------- persistence
    def save(self) -> tuple[RepetitionSegment, ...]:
        """Write the sidecar unconditionally."""
        saved = self.workspace.save_segments(self.take, self._segments)
        self._segments = list(saved)
        renumber_segments(self._segments)
        self._dirty = False
        self._last_saved_at = utc_now_iso()
        return tuple(self._segments)

    def save_if_dirty(self) -> bool:
        """Write only when something changed. Returns whether it wrote."""
        if not self._dirty:
            return False
        self.save()
        return True

    # -------------------------------------------------------------- helpers
    def _require(self, segment_id: str) -> RepetitionSegment:
        segment = self.find(segment_id)
        if segment is None:
            raise ValidationError(
                "Tekrar bulunamadı; listeyi yenileyin.",
                field="segment_id",
                code="segment_not_found",
            )
        return segment

    def _clamp(self, start_frame: int, end_frame: int) -> tuple[int, int]:
        """Keep an interval inside the take, ordered, and at least two frames."""
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


__all__ = ["MAX_HISTORY", "AnnotationRepository"]
