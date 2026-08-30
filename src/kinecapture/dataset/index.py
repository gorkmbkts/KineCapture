"""Dataset index: the queryable summary behind the dashboard and export.

Reads *metadata only* - ``take.json``, the label sidecar, ``quality.json``. It
never opens a skeleton stream or a video, so it stays fast as the dataset grows.
The result is cached against the newest metadata modification time, so repeated
dashboard refreshes are nearly free while an edit still invalidates the cache.

"Labelled" here means exactly what the exporter means by "eligible": both ask
:func:`kinecapture.domain.project.evaluate_sample`. There is no second rule that
could drift.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from kinecapture.core.logging import get_logger
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.activity import (
    ActivityCoverage,
    ActivityInterval,
    ActivityState,
    ContinuousReadiness,
    evaluate_continuous,
    measure_coverage,
)
from kinecapture.domain.enums import (
    Correctness,
    DataOrigin,
    SampleReadiness,
    SegmentStatus,
    TakeQuality,
    TakeState,
)
from kinecapture.domain.project import (
    MovementSample,
    Participant,
    Session,
    Take,
    evaluate_sample,
)

logger = get_logger(__name__)


@dataclass
class TakeRow:
    """One take plus everything the list views need, already resolved."""

    take: Take
    participant_code: str
    session_id: str
    samples: list[MovementSample] = field(default_factory=list)
    #: The project's error vocabulary at the time the row was built, so
    #: readiness can be judged without another disk read.
    known_error_codes: tuple[str, ...] = ()
    #: The optional activity strip. Empty for a take nobody labelled that way,
    #: which is a normal state rather than a defect.
    activity_intervals: list[ActivityInterval] = field(default_factory=list)
    known_exercise_codes: tuple[str, ...] = ()

    # Pre-redesign attribute name, kept so older call sites keep working.
    @property
    def segments(self) -> list[MovementSample]:
        return self.samples

    @property
    def active_samples(self) -> list[MovementSample]:
        return [s for s in self.samples if s.is_active]

    @property
    def movement_count(self) -> int:
        return len(self.active_samples)

    #: Pre-redesign name.
    @property
    def repetition_count(self) -> int:
        return self.movement_count

    def readiness(self, sample: MovementSample) -> SampleReadiness:
        return evaluate_sample(sample, known_error_codes=self.known_error_codes)[0]

    # ----------------------------------------------------- continuous layer
    def continuous_readiness(
        self, *, require_full_coverage: bool = False
    ) -> ContinuousReadiness:
        """Whether this take can be a continuous example.

        Independent of movement-sample readiness on purpose: a recording of
        somebody who never performed the exercise is useless to one dataset and
        valuable to the other.
        """
        return evaluate_continuous(
            self.activity_intervals,
            self.take.metrics.frames_written,
            known_exercises=self.known_exercise_codes,
            require_full_coverage=require_full_coverage,
        )[0]

    def activity_coverage(self) -> ActivityCoverage:
        return measure_coverage(
            self.activity_intervals,
            self.take.metrics.frames_written,
            known_exercises=self.known_exercise_codes,
        )

    @property
    def has_target_exercise(self) -> bool:
        return any(
            interval.state is ActivityState.TARGET_EXERCISE
            for interval in self.activity_intervals
        )

    @property
    def subject_coverage(self) -> float:
        """Fraction of recorded frames where the selected person was found."""
        return self.take.metrics.subject_coverage

    @property
    def ready_samples(self) -> list[MovementSample]:
        """Samples that would actually be exported."""
        return [s for s in self.active_samples if self.readiness(s).is_ready]

    @property
    def labelled_count(self) -> int:
        return len(self.ready_samples)

    @property
    def error_interval_count(self) -> int:
        return sum(len(s.error_intervals) for s in self.active_samples)

    @property
    def is_fully_labelled(self) -> bool:
        return self.movement_count > 0 and self.labelled_count == self.movement_count

    @property
    def needs_review(self) -> bool:
        """Finalised, usable, but not yet completely labelled."""
        return self.take.usable_for_export and not self.is_fully_labelled

    @property
    def exercises(self) -> tuple[str, ...]:
        values = {s.exercise for s in self.active_samples if s.exercise}
        if self.take.exercise:
            values.add(self.take.exercise)
        return tuple(sorted(values))

    @property
    def error_codes(self) -> tuple[str, ...]:
        values: set[str] = set()
        for sample in self.active_samples:
            values.update(sample.error_codes)
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
    error_codes: tuple[str, ...] = ()
    readiness: tuple[SampleReadiness, ...] = ()
    take_quality: tuple[TakeQuality, ...] = ()
    take_states: tuple[TakeState, ...] = ()
    origin: Optional[DataOrigin] = None
    only_ready: bool = False
    only_unready: bool = False

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
        if self.only_ready and row.labelled_count == 0:
            return False
        if self.only_unready and row.is_fully_labelled:
            return False
        if self.exercises and not set(self.exercises) & set(row.exercises):
            return False
        if self.error_codes and not set(self.error_codes) & set(row.error_codes):
            return False
        if self.correctness:
            values = {s.derived_correctness for s in row.active_samples}
            if not values & set(self.correctness):
                return False
        if self.readiness:
            values = {row.readiness(s) for s in row.active_samples}
            if not values & set(self.readiness):
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

    movement_samples: int = 0
    ready_samples: int = 0
    unready_samples: int = 0
    excluded_samples: int = 0
    error_intervals: int = 0
    takes_needing_review: int = 0

    # --- continuous activity, counted apart from repetition counts ------
    # "Ready movements" and "takes ready for continuous export" answer two
    # different questions and are never added together.
    continuous_ready_takes: int = 0
    continuous_unlabelled_takes: int = 0
    negative_takes: int = 0
    activity_seconds: dict[str, float] = field(default_factory=dict)
    unlabelled_activity_seconds: float = 0.0
    exercise_start_events: int = 0
    takes_with_subject_lock: int = 0
    takes_with_raw_archive_loss: int = 0
    mean_subject_coverage: float = 0.0

    correctness_counts: dict[str, int] = field(default_factory=dict)
    exercise_counts: dict[str, int] = field(default_factory=dict)
    readiness_counts: dict[str, int] = field(default_factory=dict)
    error_class_counts: dict[str, int] = field(default_factory=dict)

    total_duration_s: float = 0.0
    mean_tracking_coverage: float = 0.0
    takes_with_capture_loss: int = 0

    # Pre-redesign aliases so older dashboards keep reading.
    @property
    def repetitions(self) -> int:
        return self.movement_samples

    @property
    def labelled_repetitions(self) -> int:
        return self.ready_samples

    @property
    def unlabelled_repetitions(self) -> int:
        return self.unready_samples

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
        error_codes = self.workspace.label_schema.error_type_codes()
        exercise_codes = self.workspace.label_schema.exercise_codes()

        rows: list[TakeRow] = []
        for take in self.workspace.list_takes():
            rows.append(
                TakeRow(
                    take=take,
                    participant_code=codes.get(take.participant_id, take.participant_id),
                    session_id=take.session_id,
                    samples=self.workspace.load_samples(take),
                    known_error_codes=error_codes,
                    activity_intervals=self.workspace.load_activity_intervals(take),
                    known_exercise_codes=exercise_codes,
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
        """(file count, newest mtime) over the metadata files only.

        The project's own ``label_schema.json`` counts too: adding an error class
        can change whether existing samples are considered ready.
        """
        count = 0
        newest = 0.0
        candidates: list = []
        base = self.workspace.participants_dir
        if base.is_dir():
            candidates = list(base.rglob("*.json"))
        schema_path = self.workspace.label_schema_file
        if schema_path.is_file():
            candidates.append(schema_path)
        for path in candidates:
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

    def used_error_codes(self) -> tuple[str, ...]:
        """Error classes referenced anywhere in the project's labels."""
        values: set[str] = set()
        for row in self._rows:
            values.update(row.error_codes)
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
        readiness: Counter[str] = Counter()
        error_classes: Counter[str] = Counter()
        coverage_total = 0.0
        coverage_count = 0
        subject_total = 0.0
        subject_count = 0

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

            # --- the continuous layer, kept separate on purpose ------
            fps = float(take.capture_profile.fps or 30.0)
            activity_coverage = row.activity_coverage()
            for state, frames in activity_coverage.per_state.items():
                summary.activity_seconds[state] = summary.activity_seconds.get(
                    state, 0.0
                ) + (frames / fps if fps > 0 else 0.0)
            summary.unlabelled_activity_seconds += (
                activity_coverage.unlabelled_frames / fps if fps > 0 else 0.0
            )
            summary.exercise_start_events += activity_coverage.exercise_starts
            if row.activity_intervals:
                if row.continuous_readiness().is_ready:
                    summary.continuous_ready_takes += 1
                if not row.has_target_exercise:
                    summary.negative_takes += 1
            else:
                summary.continuous_unlabelled_takes += 1
            if take.metrics.subject_locked_frames or take.metrics.subject_lost_frames:
                summary.takes_with_subject_lock += 1
                subject_total += take.metrics.subject_coverage
                subject_count += 1
            if take.metrics.has_raw_archive_loss:
                summary.takes_with_raw_archive_loss += 1

            for sample in row.samples:
                if sample.status is SegmentStatus.EXCLUDED:
                    summary.excluded_samples += 1
                    continue
                summary.movement_samples += 1
                state = row.readiness(sample)
                readiness[state.value] += 1
                if state.is_ready:
                    summary.ready_samples += 1
                else:
                    summary.unready_samples += 1
                correctness[sample.derived_correctness.value] += 1
                if sample.exercise:
                    exercises[sample.exercise] += 1
                summary.error_intervals += len(sample.error_intervals)
                for interval in sample.error_intervals:
                    if interval.error_code:
                        error_classes[interval.error_code] += 1

        summary.correctness_counts = dict(sorted(correctness.items()))
        summary.exercise_counts = dict(sorted(exercises.items()))
        summary.readiness_counts = dict(sorted(readiness.items()))
        summary.error_class_counts = dict(sorted(error_classes.items()))
        summary.mean_tracking_coverage = (
            coverage_total / coverage_count if coverage_count else 0.0
        )
        summary.mean_subject_coverage = (
            subject_total / subject_count if subject_count else 0.0
        )
        summary.activity_seconds = {
            key: round(value, 2)
            for key, value in sorted(summary.activity_seconds.items())
        }
        summary.unlabelled_activity_seconds = round(
            summary.unlabelled_activity_seconds, 2
        )
        return summary

    # ------------------------------------------------------------------- QA
    def quality_issues(
        self, rows: Optional[Sequence[TakeRow]] = None
    ) -> list[dict[str, Any]]:
        """Problems worth a researcher's attention, most severe first.

        Structural failures (missing files, capture loss) come before label
        problems, which come before statistical concerns (class imbalance),
        because one makes data unusable and the others make it awkward.
        """
        selected = list(rows) if rows is not None else self._rows
        issues: list[dict[str, Any]] = []

        for row in selected:
            take = row.take
            paths = self.workspace.take_paths(take)
            label = f"{row.participant_code} / kayıt {take.index_in_session}"
            if take.is_finalized and not paths.skeleton_stream.is_file():
                issues.append(
                    {
                        "severity": "blocked",
                        "issue": "missing_skeleton_stream",
                        "take_id": take.take_id,
                        "message": f"{label}: iskelet akışı dosyası yok.",
                    }
                )
            if take.is_recoverable_partial:
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "partial_take",
                        "take_id": take.take_id,
                        "message": f"{label}: kayıt yarım kalmış, kurtarma bekliyor.",
                    }
                )
            if take.metrics.has_capture_loss:
                issues.append(
                    {
                        "severity": "warning",
                        "issue": "capture_loss",
                        "take_id": take.take_id,
                        "message": (
                            f"{label}: {take.metrics.frames_dropped_recording} kare "
                            f"diske yazılamadı, "
                            f"{take.metrics.missing_frame_indices} kare eksik."
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
                            f"{label}: takip kapsamı düşük "
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
                            f"{label}: ölçülen FPS "
                            f"{take.metrics.measured_fps:.1f}, hedef "
                            f"{take.metrics.target_fps:.0f}."
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
                            f"{label}: takip kimliği "
                            f"{len(take.body_id_events)} kez değişti."
                        ),
                    }
                )

        issues.extend(self._label_issues(selected))
        issues.extend(self._balance_issues(selected))
        order = {"blocked": 0, "warning": 1, "info": 2}
        return sorted(issues, key=lambda item: order.get(item["severity"], 3))

    def _label_issues(self, rows: Sequence[TakeRow]) -> list[dict[str, Any]]:
        """Label problems, using the same rule the exporter applies."""
        severity_by_readiness = {
            SampleReadiness.LEGACY_CONFLICT: "warning",
            SampleReadiness.CONTRADICTION: "warning",
            SampleReadiness.INVALID_INTERVAL: "warning",
            SampleReadiness.NEEDS_ERROR_INTERVAL: "info",
            SampleReadiness.UNLABELLED: "info",
        }
        issues: list[dict[str, Any]] = []
        for row in rows:
            for sample in row.active_samples:
                state, problems = evaluate_sample(
                    sample, known_error_codes=row.known_error_codes
                )
                if state.is_ready:
                    continue
                severity = severity_by_readiness.get(state, "info")
                for problem in problems:
                    issues.append(
                        {
                            "severity": severity,
                            "issue": problem.code,
                            "take_id": row.take.take_id,
                            "message": (
                                f"{row.participant_code} / hareket {sample.index}: "
                                f"{problem.message}"
                            ),
                        }
                    )
        return issues

    def _balance_issues(self, rows: Sequence[TakeRow]) -> list[dict[str, Any]]:
        """Class imbalance, coverage and error-class rarity warnings."""
        issues: list[dict[str, Any]] = []
        per_exercise_participants: dict[str, set[str]] = {}
        correctness: Counter[str] = Counter()
        error_classes: Counter[str] = Counter()

        for row in rows:
            for sample in row.active_samples:
                if not row.readiness(sample).is_ready:
                    continue
                correctness[sample.derived_correctness.value] += 1
                if sample.exercise:
                    per_exercise_participants.setdefault(sample.exercise, set()).add(
                        row.take.participant_id
                    )
                for interval in sample.error_intervals:
                    if interval.error_code:
                        error_classes[interval.error_code] += 1

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

        schema = self.workspace.label_schema
        for code, count in sorted(error_classes.items()):
            if count < 3:
                issues.append(
                    {
                        "severity": "info",
                        "issue": "rare_error_class",
                        "take_id": "",
                        "message": (
                            f"'{schema.label_for_error(code)}' yalnızca {count} "
                            "aralıkta geçiyor; zamansal yerelleştirme için az olabilir."
                        ),
                    }
                )
        return issues


def exportable_rows(rows: Iterable[TakeRow]) -> list[TakeRow]:
    """Takes eligible for a dataset release: finalised, not excluded, ready."""
    return [
        row
        for row in rows
        if row.take.usable_for_export and row.ready_samples
    ]


__all__ = [
    "DatasetIndex",
    "DatasetQuery",
    "DatasetSummary",
    "TakeRow",
    "exportable_rows",
]
