"""Choosing the athlete, and answering where the tracker was unsure.

Sits beside the labelling viewmodel and shares its version. Everything it
exposes is a question with a visible answer; nothing here decides anything on
the user's behalf, and an unanswered question is reported as unanswered rather
than filled in with the most likely body.

No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.processing.subject_review import (
    Candidate,
    Verdict,
    load_subject_review,
    scan_candidates,
    scan_unsettled,
)
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.review import ReviewSession
from kinecapture.studio.services.subject_store import SubjectStore

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

VERDICT_TEXT = {
    Verdict.SAME_ATHLETE: "Aynı sporcu",
    Verdict.OTHER_PERSON: "Diğer kişi",
    Verdict.NO_ATHLETE: "Bu bölümde sporcu yok",
    Verdict.UNANSWERED: "Yanıtlanmadı",
}

STATE_TEXT = {
    "ambiguous": "iki kişi ayırt edilemedi",
    "reidentifying": "kişi yeniden tanınmaya çalışıldı",
    "temporarily_lost": "kişi geçici olarak kayboldu",
}


@dataclass(frozen=True)
class CandidateRow:
    """One person to choose between, described for a human."""

    tracker_id: int
    title: str
    seconds_visible: float
    coverage: float
    breaks: int
    preview_positions: tuple[int, ...]
    is_chosen: bool
    was_tracked_subject: bool

    @property
    def detail(self) -> str:
        parts = [f"{self.seconds_visible:.1f} sn görüldü",
                 f"kaydın %{self.coverage * 100:.0f}'i"]
        if self.breaks:
            parts.append(f"{self.breaks} kez koptu")
        if self.was_tracked_subject:
            parts.append("çekimde seçilen kişi")
        return " · ".join(parts)


@dataclass(frozen=True)
class QuestionRow:
    """One stretch the tracker could not settle."""

    interval_id: str
    start: int
    end: int
    reason: str
    verdict: Verdict
    answer_text: str
    visible: tuple[int, ...]

    @property
    def is_answered(self) -> bool:
        return self.verdict is not Verdict.UNANSWERED


class SubjectViewModel:
    """The athlete choice for one opened version."""

    def __init__(self, runner: Optional[TaskRunner] = None) -> None:
        self._runner: TaskRunner = runner or InlineRunner()
        self.review: Optional[ReviewSession] = None
        self.store: Optional[SubjectStore] = None

        self.candidates: Observable[tuple[CandidateRow, ...]] = Observable(
            (), name="candidates"
        )
        self.questions: Observable[tuple[QuestionRow, ...]] = Observable(
            (), name="questions"
        )
        self.chosen: Observable[int] = Observable(-1, name="chosen")
        self.progress: Observable[str] = Observable("", name="progress")
        self.settled: Observable[bool] = Observable(False, name="settled")
        #: Empty when the version is usable; otherwise why choosing an athlete
        #: here cannot rescue it.
        self.blocker: Observable[str] = Observable("", name="blocker")
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.can_undo: Observable[bool] = Observable(False, name="can_undo")
        self.message: Event[Message] = Event()
        self.go_to: Event[int] = Event()

    # ------------------------------------------------------------------ open
    def open(self, review: ReviewSession, annotator: str = "") -> None:
        """Scan the version for candidates and questions, off the GUI thread.

        The scan reads the whole skeleton stream, which is the one place that
        genuinely needs every body in every frame. Labelling does not, which is
        why the stream is lazy everywhere else.
        """
        self.close()
        self.review = review
        self.busy.set(True)

        def work():  # noqa: ANN202
            frames = review.dataset.stream.frames
            return (
                scan_candidates(frames),
                scan_unsettled(frames, review.dataset.anchor_at),
            )

        def done(result) -> None:  # noqa: ANN001
            candidates, intervals = result
            self.busy.set(False)
            try:
                document = load_subject_review(
                    review.take_dir, review.run_id, review.source_fingerprint
                )
            except KineCaptureError as exc:
                self.message.emit(from_error(exc, headline="Kişi kararları açılamadı."))
                return
            self.store = SubjectStore(
                take_dir=review.take_dir,
                document=document,
                candidates=candidates,
                annotator=annotator,
            )
            self.store.set_intervals(intervals)
            self.store.subscribe(self._refresh)
            self._refresh()

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Kişiler taranamadı."))

        self._runner.run(work, done, failed)

    def close(self) -> None:
        if self.store is not None:
            try:
                self.store.flush()
            except (KineCaptureError, OSError) as exc:
                self.message.emit(from_error(exc, headline="Kişi kararları kaydedilemedi."))
        self.store = None
        self.review = None
        self.candidates.force(())
        self.questions.force(())

    # -------------------------------------------------------------- actions
    def choose(self, tracker_id: int) -> bool:
        return self._guarded(
            lambda: self.store.choose_athlete(tracker_id), "Sporcu seçilemedi."
        )

    def answer(
        self, interval_id: str, verdict: Verdict, *, tracker_id: Optional[int] = None
    ) -> bool:
        return self._guarded(
            lambda: self.store.answer(interval_id, verdict, tracker_id=tracker_id),
            "Yanıt kaydedilemedi.",
        )

    def answer_remaining(self, verdict: Verdict) -> int:
        if self.store is None:
            return 0
        try:
            count = self.store.answer_all_remaining(verdict)
        except (ValidationError, KineCaptureError) as exc:
            self.message.emit(from_error(exc, headline="Toplu yanıt verilemedi."))
            return 0
        if count:
            self.message.emit(
                Message(
                    headline=f"{count} aralık '{VERDICT_TEXT[verdict]}' olarak yanıtlandı.",
                    severity=Severity.INFO,
                    detail="Zaten yanıtlanmış aralıklar değiştirilmedi.",
                )
            )
        return count

    def clear_answer(self, interval_id: str) -> bool:
        return self._guarded(
            lambda: self.store.clear_answer(interval_id), "Yanıt geri alınamadı."
        )

    def undo(self) -> None:
        if self.store is not None and self.store.undo():
            self._refresh()

    def flush(self) -> None:
        if self.store is None:
            return
        try:
            self.store.flush()
        except (KineCaptureError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Kişi kararları kaydedilemedi."))

    def show_question(self, interval_id: str) -> None:
        """Take the labelling screen to the moment being asked about."""
        row = next(
            (q for q in self.questions.value if q.interval_id == interval_id), None
        )
        if row is not None:
            self.go_to.emit(row.start)

    def next_question(self, after: Optional[str] = None) -> Optional[str]:
        if self.store is None:
            return None
        interval = self.store.next_unanswered(after)
        if interval is None:
            return None
        self.show_question(interval.interval_id)
        return interval.interval_id

    # ------------------------------------------------------------ internals
    def _guarded(self, action, headline: str) -> bool:  # noqa: ANN001
        if self.store is None:
            return False
        try:
            action()
        except (ValidationError, KeyError, KineCaptureError) as exc:
            self.message.emit(from_error(exc, headline=headline))
            return False
        return True

    def _refresh(self) -> None:
        store, review = self.store, self.review
        if store is None or review is None:
            return
        fps = max(1.0, review.fps)
        frames = max(1, review.frames)
        chosen = store.document.athlete_tracker_id

        rows: list[CandidateRow] = []
        for index, candidate in enumerate(store.candidates, start=1):
            rows.append(
                CandidateRow(
                    tracker_id=candidate.tracker_id,
                    # Numbered for the person reading; the tracker id stays a
                    # technical detail rather than the headline.
                    title=f"Kişi {index}",
                    seconds_visible=candidate.frames_present / fps,
                    coverage=candidate.coverage(frames),
                    breaks=candidate.breaks,
                    preview_positions=candidate.preview_positions,
                    is_chosen=chosen is not None and candidate.tracker_id == chosen,
                    was_tracked_subject=candidate.frames_as_subject > 0,
                )
            )
        self.candidates.force(tuple(rows))

        by_tracker = {c.tracker_id: c.title for c in rows}
        questions: list[QuestionRow] = []
        for interval in store.document.intervals:
            decision = store.document.decision_for(interval.interval_id)
            verdict = decision.verdict if decision else Verdict.UNANSWERED
            text = VERDICT_TEXT[verdict]
            if verdict is Verdict.OTHER_PERSON and decision.tracker_id is not None:
                text = f"{text}: {by_tracker.get(decision.tracker_id, decision.tracker_id)}"
            try:
                start = review.dataset.position_of_anchor(interval.start)
                end = review.dataset.position_of_anchor(interval.end)
            except ValueError:
                continue
            questions.append(
                QuestionRow(
                    interval_id=interval.interval_id,
                    start=start,
                    end=end,
                    reason=" · ".join(
                        STATE_TEXT.get(state, state) for state in interval.states
                    ),
                    verdict=verdict,
                    answer_text=text,
                    visible=interval.visible,
                )
            )
        questions.sort(key=lambda q: q.start)
        self.questions.force(tuple(questions))

        self.chosen.set(-1 if chosen is None else chosen)
        answered, total = store.progress()

        # A version the tracker never locked onto has no joints at all. That is
        # not a question a person can answer here, so it is reported as a
        # blocker rather than left to look like an unfinished checklist.
        usable = review.has_subject_data
        self.blocker.set("" if usable else usable.reason)

        if not usable:
            self.progress.set("Bu sürümde iskelet verisi yok")
        elif chosen is None:
            self.progress.set("Sporcu seçilmedi")
        elif total:
            self.progress.set(f"{answered}/{total} belirsiz aralık yanıtlandı")
        else:
            self.progress.set("Belirsiz aralık yok")
        self.settled.set(bool(usable) and store.is_settled)
        self.can_undo.set(store.can_undo)

    def candidate_title(self, tracker_id: Optional[int]) -> str:
        if tracker_id is None:
            return "—"
        row = next(
            (c for c in self.candidates.value if c.tracker_id == tracker_id), None
        )
        return row.title if row else f"tracker {tracker_id}"


__all__ = ["CandidateRow", "QuestionRow", "STATE_TEXT", "SubjectViewModel", "VERDICT_TEXT"]
