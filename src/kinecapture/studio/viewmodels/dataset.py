"""Veri Seti: what the project actually contains.

One table over every finished version, answering the questions a coach asks
before an export rather than after it: how much is labelled, how much is
waiting on a person, and what exactly is missing.

Everything here is read from the derived index and from each version's own
sidecars. Nothing opens a version, because this is a list - the expensive,
authoritative check belongs to Dışa Aktarım, and the two are deliberately not
the same thing. A row here says "looks ready"; only the export check says
"is ready", and the wording keeps that distinction.

No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kinecapture.core.errors import KineCaptureError
from kinecapture.core.jsonio import read_json
from kinecapture.core.paths import path_exists
from kinecapture.dataset.summary_index import build_index
from kinecapture.domain.labels import LabelSchema
from kinecapture.processing.annotations import AnnotationDocument, Readiness
from kinecapture.processing.subject_review import SubjectReview
from kinecapture.studio.services.library import LibraryService, VersionRow
from kinecapture.studio.services.messages import Message, from_error
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

#: What a row is waiting on, in the order it has to be dealt with.
#: The bucket a repetition or an interval with no class of its own falls in.
#: Kept as a real entry rather than dropped: "how much is still unclassified"
#: is the most useful thing a distribution can say about a dataset in
#: progress, and leaving it out would make the chart look finished.
UNCLASSED = "__unclassed__"
UNCLASSED_TEXT = "sınıfsız"

BLOCKER_TEXT = {
    "no_subject_data": "kişi seçilmeden işlenmiş",
    "athlete": "sporcu seçilmemiş",
    "questions": "belirsiz aralık yanıtsız",
    "unlabelled": "hareket işaretlenmemiş",
    "unreviewed": "onay bekliyor",
    "no_exercise": "hareket sınıfı yok",
    "open_error": "sınıfsız hata aralığı",
}


@dataclass(frozen=True)
class DatasetRow:
    """One finished version, summarised."""

    run_id: str
    take_id: str
    participant_id: str
    started_at: str
    directory: str
    frames: int
    duration_s: float
    movements: int
    ready: int
    excluded: int
    error_intervals: int
    athlete_chosen: bool
    open_questions: int
    has_subject_data: bool
    blockers: tuple[str, ...]
    #: Movement class -> how many repetitions of it this version holds, and
    #: fault class -> how many intervals. Counted here rather than on the
    #: screen because this is the one place the sidecars are read at all, and
    #: reading them again per chart would be the same disk work twice.
    #: Excluded repetitions are left out of both: a repetition kept out of the
    #: dataset is not part of the dataset's distribution.
    exercise_counts: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)
    #: Display names for whatever codes appear above, so a chart can print a
    #: class without a second look at the schema.
    class_labels: dict[str, str] = field(default_factory=dict)
    #: Each class's place in the project's own vocabulary. A chart ranks by
    #: count, so without this a class's colour would change with its rank -
    #: and a class keeps its colour for the life of the project.
    class_order: dict[str, int] = field(default_factory=dict)

    @property
    def looks_ready(self) -> bool:
        return not self.blockers and self.ready > 0

    @property
    def status(self) -> str:
        if self.looks_ready:
            return "ready"
        return "warning" if self.movements else "neutral"

    @property
    def text(self) -> str:
        if self.looks_ready:
            return f"{self.ready} hareket hazır"
        if not self.movements:
            return "etiketlenmemiş"
        return " · ".join(BLOCKER_TEXT.get(b, b) for b in self.blockers)


@dataclass(frozen=True)
class DatasetTotals:
    versions: int = 0
    looks_ready: int = 0
    movements: int = 0
    ready_movements: int = 0
    error_intervals: int = 0
    seconds: float = 0.0

    @property
    def text(self) -> str:
        minutes = self.seconds / 60.0
        return (
            f"{self.versions} sürüm · {self.looks_ready} hazır görünüyor · "
            f"{self.ready_movements}/{self.movements} hareket · "
            f"{self.error_intervals} hata aralığı · {minutes:.1f} dk"
        )


class DatasetViewModel:
    """The project-wide quality and coverage view."""

    def __init__(
        self, session: SessionService, runner: Optional[TaskRunner] = None
    ) -> None:
        self._session = session
        self._runner: TaskRunner = runner or InlineRunner()
        self._service = LibraryService()

        self.rows: Observable[tuple[DatasetRow, ...]] = Observable((), name="rows")
        self.totals: Observable[DatasetTotals] = Observable(
            DatasetTotals(), name="totals"
        )
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.message: Event[Message] = Event()

    def reload(self, *, force: bool = False) -> None:
        workspace = self._session.workspace
        if workspace is None:
            self.rows.force(())
            self.totals.force(DatasetTotals())
            return
        self.busy.set(True)
        schema = workspace.label_schema
        root = Path(workspace.root)

        def work() -> tuple[DatasetRow, ...]:
            index = build_index(root, force=force)
            versions = self._service.versions(index)
            return tuple(_summarise(row, schema) for row in versions)

        def done(rows: tuple[DatasetRow, ...]) -> None:
            self.busy.set(False)
            self.rows.force(rows)
            self.totals.force(
                DatasetTotals(
                    versions=len(rows),
                    looks_ready=sum(1 for r in rows if r.looks_ready),
                    movements=sum(r.movements for r in rows),
                    ready_movements=sum(r.ready for r in rows),
                    error_intervals=sum(r.error_intervals for r in rows),
                    seconds=sum(r.duration_s for r in rows),
                )
            )

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Veri seti okunamadı."))

        self._runner.run(work, done, failed)


def _position(codes: tuple[str, ...], code: str) -> int:
    """Where ``code`` sits in its vocabulary, or -1 for the unclassed bucket.

    A class the schema has forgotten still gets a place rather than an error:
    the annotation is on disk either way, and refusing to chart it would be
    hiding it.
    """
    try:
        return codes.index(code)
    except ValueError:
        return -1


def _summarise(row: VersionRow, schema: LabelSchema) -> DatasetRow:
    """Read one version's sidecars. Never opens the version itself."""
    take_dir = Path(row.take_directory)
    annotations = take_dir / "annotations" / "processing" / f"{row.run_id}.json"
    subject_path = take_dir / "annotations" / "processing" / f"{row.run_id}.subject.json"

    document = AnnotationDocument(processing_run=row.run_id, source_fingerprint="")
    if path_exists(annotations):
        try:
            document = AnnotationDocument.from_dict(dict(read_json(annotations)))
        except (KineCaptureError, OSError, KeyError, ValueError):
            pass

    subject = SubjectReview(processing_run=row.run_id, source_fingerprint="")
    if path_exists(subject_path):
        try:
            subject = SubjectReview.from_dict(dict(read_json(subject_path)))
        except (KineCaptureError, OSError, KeyError, ValueError):
            pass

    known = schema.exercise_codes()
    ready = excluded = errors = 0
    states: set[str] = set()
    fault_codes = schema.error_type_codes()
    exercise_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    orders: dict[str, int] = {}
    for sample in document.samples:
        errors += len(sample.errors)
        if sample.excluded:
            excluded += 1
            continue
        code = sample.exercise or UNCLASSED
        exercise_counts[code] = exercise_counts.get(code, 0) + 1
        labels.setdefault(
            code, UNCLASSED_TEXT if code == UNCLASSED else schema.label_for_exercise(code)
        )
        orders.setdefault(code, _position(known, code))
        for error in sample.errors:
            fault = error.error_class or UNCLASSED
            error_counts[fault] = error_counts.get(fault, 0) + 1
            labels.setdefault(
                fault,
                UNCLASSED_TEXT if fault == UNCLASSED else schema.label_for_error(fault),
            )
            orders.setdefault(fault, _position(fault_codes, fault))
        readiness = sample.readiness(known)
        if readiness is Readiness.READY:
            ready += 1
        elif readiness is Readiness.UNCLASSIFIED_ERROR:
            states.add("open_error")
        elif readiness is Readiness.NO_EXERCISE:
            states.add("no_exercise")
        elif readiness is Readiness.UNREVIEWED:
            states.add("unreviewed")

    has_data = row.subject_status != "needs_subject_selection"
    blockers: list[str] = []
    if not has_data:
        blockers.append("no_subject_data")
    if subject.athlete_tracker_id is None:
        blockers.append("athlete")
    if subject.unanswered:
        blockers.append("questions")
    if not document.samples:
        blockers.append("unlabelled")
    blockers.extend(sorted(states))

    return DatasetRow(
        run_id=row.run_id,
        take_id=row.take_id,
        participant_id=row.participant_id,
        started_at=row.started_at,
        directory=row.directory,
        frames=row.frames,
        duration_s=row.duration_s,
        movements=len(document.samples),
        ready=ready,
        excluded=excluded,
        error_intervals=errors,
        athlete_chosen=subject.athlete_tracker_id is not None,
        open_questions=len(subject.unanswered),
        has_subject_data=has_data,
        blockers=tuple(dict.fromkeys(blockers)),
        exercise_counts=exercise_counts,
        error_counts=error_counts,
        class_labels=labels,
        class_order=orders,
    )


def aggregate(rows) -> "DatasetStats":
    """Roll a list of versions up into the numbers the charts draw.

    A plain function over the rows the screen already has, so what is on a
    chart and what is in the table can never disagree, and filtering the list
    is all it takes to re-draw the charts for a subset.
    """
    exercises: dict[str, int] = {}
    errors: dict[str, int] = {}
    labels: dict[str, str] = {}
    orders: dict[str, int] = {}
    people: dict[str, list[int]] = {}
    ready = blocked = unlabelled = 0
    for row in rows:
        labels.update(row.class_labels)
        orders.update(row.class_order)
        for code, count in row.exercise_counts.items():
            exercises[code] = exercises.get(code, 0) + count
        for code, count in row.error_counts.items():
            errors[code] = errors.get(code, 0) + count
        if not row.movements:
            unlabelled += 1
        elif row.looks_ready:
            ready += 1
        else:
            blocked += 1
        seen = people.setdefault(row.participant_id or "—", [0, 0, 0])
        seen[0] += 1
        seen[1] += row.movements
        seen[2] += int(row.duration_s)
    return DatasetStats(
        exercises=exercises,
        errors=errors,
        labels=labels,
        orders=orders,
        ready=ready,
        blocked=blocked,
        unlabelled=unlabelled,
        participants={name: tuple(values) for name, values in sorted(people.items())},
    )


@dataclass(frozen=True)
class DatasetStats:
    """What the whole (filtered) dataset looks like, in numbers."""

    exercises: dict[str, int] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    orders: dict[str, int] = field(default_factory=dict)
    ready: int = 0
    blocked: int = 0
    unlabelled: int = 0
    #: participant -> (versions, movements, seconds)
    participants: dict[str, tuple[int, int, int]] = field(default_factory=dict)

    def label_for(self, code: str) -> str:
        return self.labels.get(code, code)

    def order_of(self, code: str) -> int:
        """The class's place in the project vocabulary, or -1."""
        return self.orders.get(code, -1)

    def ranked(self, counts: dict[str, int]) -> tuple[tuple[str, int], ...]:
        """Largest first, with the unclassed bucket always last.

        It is not a class, so it does not compete for the top of the chart -
        but it is never hidden either, because how much is unclassified is
        the number somebody labelling a dataset most wants to see.
        """
        named = sorted(
            ((c, n) for c, n in counts.items() if c != UNCLASSED),
            key=lambda pair: (-pair[1], self.label_for(pair[0])),
        )
        rest = counts.get(UNCLASSED, 0)
        return tuple(named + ([(UNCLASSED, rest)] if rest else []))

    @property
    def is_empty(self) -> bool:
        return not (self.exercises or self.errors or self.participants)


__all__ = [
    "BLOCKER_TEXT",
    "UNCLASSED",
    "UNCLASSED_TEXT",
    "DatasetRow",
    "DatasetStats",
    "DatasetTotals",
    "DatasetViewModel",
    "aggregate",
]
