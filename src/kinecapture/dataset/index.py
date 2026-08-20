"""Dataset index: the queryable summary behind the dashboard and export.

Reads *metadata only* - ``take.json``, ``segments.json``, ``quality.json``. It
never opens a skeleton stream or a video, so it stays fast as the dataset grows.
The result is cached against the newest metadata modification time, so repeated
dashboard refreshes are nearly free while an edit still invalidates the cache.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from kinecapture.core.logging import get_logger
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import (
    AnnotationStatus,
    Correctness,
    DataOrigin,
    SegmentStatus,
    TakeQuality,
    TakeState,
)
from kinecapture.domain.project import Participant, RepetitionSegment, Session, Take

logger = get_logger(__name__)


@dataclass
class TakeRow:
    """One take plus everything the list views need, already resolved."""

    take: Take
    participant_code: str
    session_id: str
    segments: list[RepetitionSegment] = field(default_factory=list)

    @property
    def repetition_count(self) -> int:
        return sum(1 for s in self.segments if s.is_active)

    @property
    def labelled_count(self) -> int:
        return sum(
            1 for s in self.segments if s.is_active and s.annotation.is_labelled
        )

    @property
    def is_fully_labelled(self) -> bool:
        return self.repetition_count > 0 and self.labelled_count == self.repetition_count

    @property
    def needs_review(self) -> bool:
        """Finalised, usable, but not yet completely labelled."""
        return self.take.usable_for_export and not self.is_fully_labelled

    @property
    def exercises(self) -> tuple[str, ...]:
        values = {s.annotation.exercise for s in self.segments if s.annotation.exercise}
        if self.take.exercise:
            values.add(self.take.exercise)
        return tuple(sorted(values))

    def matches(self, query: "DatasetQuery") -> bool:
        return query.matches(self)


@dataclass
class DatasetQuery:
    """Filter criteria shared by the dataset screen and the export screen."""

    participant_ids: tuple[str, ...] = ()
    session_ids: tuple[str, ...] = ()
    exercises: tuple[str, ...] = ()
    correctness: tuple[Correctness, ...] = ()
    annotation_status: tuple[AnnotationStatus, ...] = ()
    take_quality: tuple[TakeQuality, ...] = ()
    take_states: tuple[TakeState, ...] = ()
    origin: Optional[DataOrigin] = None
    only_labelled: bool = False
    only_unlabelled: bool = False

    def matches(self, row: TakeRow) -> bool:
        take = row.take
        if self.participant_ids and take.participant_id not in self.participant_ids:
            return False
        if self.session_ids and take.session_id not in self.session_ids:
            return False
        if self.take_states and take.state not in self.take_states:
            return False
        if self.take_quality and take.quality not in self.take_quality:
            return False
        if self.origin is not None and take.origin is not self.origin:
            return False
        if self.only_labelled and row.labelled_count == 0:
            return False
        if self.only_unlabelled and row.labelled_count == row.repetition_count and row.repetition_count > 0:
            return False
        if self.exercises and not set(self.exercises) & set(row.exercises):
            return False
        if self.correctness:
            values = {
                s.annotation.correctness for s in row.segments if s.is_active
            }
            if not values & set(self.correctness):
                return False
        if self.annotation_status:
            values = {s.annotation.status for s in row.segments if s.is_active}
            if not values & set(self.annotation_status):
                return False
        return True

    @property
    def is_empty(self) -> bool:
        return self == DatasetQuery()


@dataclass
class DatasetSummary:
    """Aggregate counts for the dashboard and the dataset screen."""

    participants: int = 0
    sessions: int = 0
    takes: int = 0
    finalized_takes: int = 0
    partial_takes: int = 0
    excluded_takes: int = 0
    synthetic_takes: int = 0
    real_takes: int = 0
    repetitions: int = 0
    labelled_repetitions: int = 0
    unlabelled_repetitions: int = 0
    excluded_repetitions: int = 0
    takes_needing_review: int = 0
    correctness_counts: dict[str, int] = field(default_factory=dict)
    exercise_counts: dict[str, int] = field(default_factory=dict)
    annotation_status_counts: dict[str, int] = field(default_factory=dict)
    total_duration_s: float = 0.0
    mean_tracking_coverage: float = 0.0
    takes_with_capture_loss: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (round(value, 3) if isinstance(value, float) else value)
            for key, value in self.__dict__.items()
        }


class DatasetIndex:
    """Cached, metadata-only view of a project."""

    def __init__(self, workspace: ProjectWorkspace) -> None:
        self.workspace = workspace
        self._rows: list[TakeRow] = []
        self._participants: list[Participant] = []
        self._sessions: list[Session] = []
        self._built_at: float = 0.0
        self._signature: Optional[tuple[int, float]] = None

    # ------------------------------------------------------------- building
    def refresh(self, *, force: bool = False) -> "DatasetIndex":
        """Rebuild if the on-disk metadata changed since the last build."""
        signature = self._metadata_signature()
        if not force and self._signature == signature and self._rows:
            return self

        started = time.perf_counter()
        self._participants = self.workspace.list_participants()
        codes = {p.participant_id: p.code for p in self._participants}
        self._sessions = self.workspace.list_sessions()

        rows: list[TakeRow] = []
        for take in self.workspace.list_takes():
            rows.append(
                TakeRow(
                    take=take,
                    participant_code=codes.get(take.participant_id, take.participant_id),
                    session_id=take.session_id,
                    segments=self.workspace.load_segments(take),
                )
            )
        self._rows = sorted(rows, key=lambda r: r.take.started_at, reverse=True)
        self._signature = signature
        self._built_at = time.perf_counter()
        logger.debug(
            "Dataset index yenilendi: %d kayıt, %.0f ms",
            len(self._rows),
            (self._built_at - started) * 1000,
        )
        return self

    def _metadata_signature(self) -> tuple[int, float]:
        """(file count, newest mtime) over the metadata files only."""
        count = 0
        newest = 0.0
        base = self.workspace.participants_dir
        if not base.is_dir():
            return (0, 0.0)
        for path in base.rglob("*.json"):
            try:
                stat = path.stat()
            except OSError:  # pragma: no cover - file vanished mid-scan
                continue
            count += 1
            newest = max(newest, stat.st_mtime)
        return (count, newest)

    # -------------------------------------------------------------- queries
    @property
    def rows(self) -> tuple[TakeRow, ...]:
        return tuple(self._rows)

    @property
    def participants(self) -> tuple[Participant, ...]:
        return tuple(self._participants)

    @property
    def sessions(self) -> tuple[Session, ...]:
        return tuple(self._sessions)

    def filter(self, query: DatasetQuery) -> list[TakeRow]:
        return [row for row in self._rows if row.matches(query)]

    def row_for(self, take_id: str) -> Optional[TakeRow]:
        return next((r for r in self._rows if r.take.take_id == take_id), None)

    def recent(self, limit: int = 10) -> list[TakeRow]:
        return self._rows[:limit]

    def needing_review(self, limit: Optional[int] = None) -> list[TakeRow]:
        rows = [row for row in self._rows if row.needs_review]
        return rows[:limit] if limit else rows

    def partial_takes(self) -> list[TakeRow]:
        return [row for row in self._rows if row.take.is_recoverable_partial]

    def open_sessions(self) -> list[Session]:
        return [s for s in self._sessions if s.is_open]

    def known_exercises(self) -> tuple[str, ...]:
        values: set[str] = set()
        for row in self._rows:
            values.update(row.exercises)
        return tuple(sorted(values))

    # -------------------------------------------------------------- summary
    def summary(self, rows: Optional[Sequence[TakeRow]] = None) -> DatasetSummary:
        """Aggregate ``rows`` (or everything) into dashboard counts."""
        selected = list(rows) if rows is not None else self._rows
        summary = DatasetSummary(
            participants=len(self._participants),
            sessions=len(self._sessions),
            takes=len(selected),
        )
        correctness: Counter[str] = Counter()
        exercises: Counter[str] = Counter()
        statuses: Counter[str] = Counter()
        coverage_total = 0.0
        coverage_count = 0

        for row in selected:
            take = row.take
            if take.is_finalized:
                summary.finalized_takes += 1
            if take.is_recoverable_partial:
                summary.partial_takes += 1
            if take.quality in (TakeQuality.EXCLUDED, TakeQuality.TECHNICAL_ISSUE):
                summary.excluded_takes += 1
            if take.is_synthetic:
                summary.synthetic_takes += 1
            else:
                summary.real_takes += 1
            if row.needs_review:
                summary.takes_needing_review += 1
            if take.metrics.has_capture_loss:
                summary.takes_with_capture_loss += 1
            summary.total_duration_s += float(take.metrics.duration_s or 0.0)
            if take.metrics.tracking_coverage:
                coverage_total += float(take.metrics.tracking_coverage)
                coverage_count += 1

            for segment in row.segments:
                if segment.status is SegmentStatus.EXCLUDED:
                    summary.excluded_repetitions += 1
                    continue
                summary.repetitions += 1
                annotation = segment.annotation
                if annotation.is_labelled:
                    summary.labelled_repetitions += 1
                else:
                    summary.unlabelled_repetitions += 1
                correctness[annotation.correctness.value] += 1
                statuses[annotation.status.value] += 1
                if annotation.exercise:
                    exercises[annotation.exercise] += 1

        summary.correctness_counts = dict(sorted(correctness.items()))
        summary.exercise_counts = dict(sorted(exercises.items()))
        summary.annotation_status_counts = dict(sorted(statuses.items()))
        summary.mean_tracking_coverage = (
            coverage_total / coverage_count if coverage_count else 0.0
        )
        return summary

    # ------------------------------------------------------------------- QA
    def quality_issues(self, rows: Optional[Sequence[TakeRow]] = None) -> list[dict[str, Any]]:
        """Problems worth a researcher's attention, most severe first.

        Structural failures (missing files, capture loss) come before statistical
        concerns (class imbalance), because one makes data unusable and the
        other makes it awkward.
        """
        selected = list(rows) if rows is not None else self._rows
        issues: list[dict[str, Any]] = []

        for row in selected:
            take = row.take
            paths = self.workspace.take_paths(take)
            if take.is_finalized and not paths.skeleton_stream.is_file():
                issues.append(
                    {
                        "severity": "blocked",
                        "issue": "missing_skeleton_stream",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            "iskelet akışı dosyası yok."
                        ),
                    }
                )
            if take.is_recoverable_partial:
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "partial_take",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            "kayıt yarım kalmış, kurtarma bekliyor."
                        ),
                    }
                )
            if take.metrics.has_capture_loss:
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "capture_loss",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            f"{take.metrics.frames_dropped_recording} kare diske "
                            f"yazılamadı, {take.metrics.missing_frame_indices} kare eksik."
                        ),
                    }
                )
            if take.is_finalized and take.metrics.tracking_coverage < 0.5:
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "low_tracking_coverage",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            f"takip kapsamı düşük "
                            f"(%{take.metrics.tracking_coverage * 100:.0f})."
                        ),
                    }
                )
            if (
                take.is_finalized
                and take.metrics.target_fps > 0
                and take.metrics.measured_fps > 0
                and take.metrics.measured_fps < 0.8 * take.metrics.target_fps
            ):
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "low_fps",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            f"ölçülen FPS {take.metrics.measured_fps:.1f}, "
                            f"hedef {take.metrics.target_fps:.0f}."
                        ),
                    }
                )
            if take.body_id_events:
                issues.append(
                    {
                        "severity": "info",
                        "issue": "body_id_change",
                        "take_id": take.take_id,
                        "message": (
                            f"{row.participant_code} / kayıt {take.index_in_session}: "
                            f"takip kimliği {len(take.body_id_events)} kez değişti."
                        ),
                    }
                )

        issues.extend(self._label_issues(selected))
        issues.extend(self._balance_issues(selected))
        order = {"blocked": 0, "warning": 1, "info": 2}
        return sorted(issues, key=lambda item: order.get(item["severity"], 3))

    def _label_issues(self, rows: Sequence[TakeRow]) -> list[dict[str, Any]]:
        schema = self.workspace.label_schema
        issues: list[dict[str, Any]] = []
        for row in rows:
            for segment in row.segments:
                if not segment.is_active:
                    continue
                problems = schema.validate_annotation_values(
                    exercise=segment.annotation.exercise,
                    error_types=segment.annotation.error_types,
                )
                for problem in problems:
                    issues.append(
                        {
                            "severity": "warning",
                            "issue": problem["issue"],
                            "take_id": row.take.take_id,
                            "message": (
                                f"{row.participant_code} / tekrar {segment.index}: "
                                f"{problem['message']}"
                            ),
                        }
                    )
        return issues

    def _balance_issues(self, rows: Sequence[TakeRow]) -> list[dict[str, Any]]:
        """Class imbalance and single-participant coverage warnings."""
        issues: list[dict[str, Any]] = []
        per_exercise_participants: dict[str, set[str]] = {}
        correctness: Counter[str] = Counter()
        for row in rows:
            for segment in row.segments:
                if not segment.is_active or not segment.annotation.is_labelled:
                    continue
                exercise = segment.annotation.exercise
                correctness[segment.annotation.correctness.value] += 1
                if exercise:
                    per_exercise_participants.setdefault(exercise, set()).add(
                        row.take.participant_id
                    )

        for exercise, participants in sorted(per_exercise_participants.items()):
            if len(participants) < 2:
                issues.append(
                    {
                        "severity": "info",
                        "issue": "single_participant_exercise",
                        "take_id": "",
                        "message": (
                            f"'{exercise}' yalnızca {len(participants)} katılımcıdan "
                            "geliyor; katılımcı bazlı ayrım anlamlı olmayabilir."
                        ),
                    }
                )

        correct = correctness.get(Correctness.CORRECT.value, 0)
        incorrect = correctness.get(Correctness.INCORRECT.value, 0)
        if correct and incorrect:
            ratio = max(correct, incorrect) / min(correct, incorrect)
            if ratio >= 3.0:
                issues.append(
                    {
                        "severity": "info",
                        "issue": "class_imbalance",
                        "take_id": "",
                        "message": (
                            f"Doğru/hatalı dengesizliği {ratio:.1f}:1 "
                            f"(doğru {correct}, hatalı {incorrect})."
                        ),
                    }
                )
        return issues


def exportable_rows(rows: Iterable[TakeRow]) -> list[TakeRow]:
    """Takes eligible for a dataset release: finalised, not excluded, labelled."""
    return [
        row
        for row in rows
        if row.take.usable_for_export
        and any(s.is_active and s.annotation.is_labelled for s in row.segments)
    ]


__all__ = [
    "DatasetIndex",
    "DatasetQuery",
    "DatasetSummary",
    "TakeRow",
    "exportable_rows",
]
