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

from dataclasses import dataclass
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
    for sample in document.samples:
        errors += len(sample.errors)
        if sample.excluded:
            excluded += 1
            continue
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
    )


__all__ = ["BLOCKER_TEXT", "DatasetRow", "DatasetTotals", "DatasetViewModel"]
