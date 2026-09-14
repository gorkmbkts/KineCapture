"""The single writer for who a version is about.

Same shape as the annotation store, and for the same reason: one decision is
one step, the whole record is validated before anything is applied, and a
refused decision leaves nothing behind.

The difference is what a wrong answer costs. A wrong exercise label teaches
the model the wrong name for a movement. A wrong athlete teaches it the wrong
*person's* movement under the right name, and the coordinates look perfectly
healthy either way. So nothing here has a default: no athlete is pre-selected,
no question is pre-answered, and "probably the same person" is not an option
the code can take on the user's behalf.

No Qt.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture.core.errors import ValidationError
from kinecapture.processing.subject_review import (
    Candidate,
    Decision,
    SubjectReview,
    UnsettledInterval,
    Verdict,
    save_subject_review,
    validate_subject_review,
)

UNDO_DEPTH = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SubjectStore:
    """Holds one version's athlete decisions and the history of them."""

    take_dir: Path
    document: SubjectReview
    candidates: tuple[Candidate, ...] = ()
    annotator: str = ""

    _undo: list[SubjectReview] = field(default_factory=list, repr=False)
    _redo: list[SubjectReview] = field(default_factory=list, repr=False)
    _dirty: bool = False
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------ notification
    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _changed(self) -> None:
        self._dirty = True
        for listener in tuple(self._listeners):
            listener()

    # ------------------------------------------------------------- history
    def _begin(self) -> None:
        self._undo.append(copy.deepcopy(self.document))
        if len(self._undo) > UNDO_DEPTH:
            del self._undo[0]
        self._redo.clear()

    def _commit(self, candidate: SubjectReview) -> None:
        problems = validate_subject_review(
            candidate, known_trackers=[c.tracker_id for c in self.candidates]
        )
        if problems:
            self._undo.pop()
            raise ValidationError(
                problems[0]["message"],
                code=problems[0]["code"],
                details={"problems": problems},
            )
        candidate.revision = self.document.revision + 1
        candidate.annotator = self.annotator or self.document.annotator
        self.document = candidate
        self._changed()

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

    # -------------------------------------------------------------- athlete
    def choose_athlete(self, tracker_id: int) -> None:
        """Say which tracked body this version is about."""
        self._begin()
        self._commit(
            replace(
                copy.deepcopy(self.document),
                athlete_tracker_id=int(tracker_id),
                chosen_at=_now(),
            )
        )

    def clear_athlete(self) -> None:
        self._begin()
        self._commit(
            replace(copy.deepcopy(self.document), athlete_tracker_id=None, chosen_at="")
        )

    # ------------------------------------------------------------ questions
    def set_intervals(self, intervals: tuple[UnsettledInterval, ...]) -> None:
        """Record the questions this version poses.

        Answers already given are kept **only** for intervals that still exist
        with the same id; a re-scan that changes the questions must not carry
        an old answer onto a different stretch of time.
        """
        keep = {i.interval_id for i in intervals}
        self.document.intervals = tuple(intervals)
        self.document.decisions = tuple(
            d for d in self.document.decisions if d.interval_id in keep
        )

    def answer(
        self,
        interval_id: str,
        verdict: Verdict,
        *,
        tracker_id: Optional[int] = None,
        note: str = "",
    ) -> None:
        """Answer one question. Verdict, who, and when, in one step."""
        if self.document.interval(interval_id) is None:
            raise KeyError(interval_id)
        if verdict is Verdict.SAME_ATHLETE:
            # "The same athlete" means the chosen one. Storing it explicitly
            # keeps the answer meaningful if the athlete choice is revisited.
            tracker_id = self.document.athlete_tracker_id
            if tracker_id is None:
                raise ValidationError(
                    "Önce bu sürümün sporcusunu seçin.",
                    code="athlete_not_chosen",
                    remedy="Aday listesinden sporcuyu seçtikten sonra aralıkları yanıtlayın.",
                )
        elif verdict is Verdict.NO_ATHLETE:
            tracker_id = None

        decision = Decision(
            interval_id=interval_id,
            verdict=verdict,
            tracker_id=None if tracker_id is None else int(tracker_id),
            decided_at=_now() if verdict is not Verdict.UNANSWERED else "",
            annotator=self.annotator,
            note=note,
        )
        others = tuple(
            d for d in self.document.decisions if d.interval_id != interval_id
        )
        self._begin()
        self._commit(
            replace(copy.deepcopy(self.document), decisions=(*others, decision))
        )

    def answer_all_remaining(self, verdict: Verdict) -> int:
        """Answer every open question the same way, as one undo step.

        Offered only for "the same athlete" and "nobody", because those are the
        two answers that do not name a different person. It is still an
        explicit act by the annotator, applied to questions they can see.
        """
        if verdict not in (Verdict.SAME_ATHLETE, Verdict.NO_ATHLETE):
            raise ValidationError(
                "Toplu yanıt yalnız 'aynı sporcu' veya 'sporcu yok' için verilebilir.",
                code="bulk_verdict_not_allowed",
            )
        open_ids = [i.interval_id for i in self.document.unanswered]
        if not open_ids:
            return 0
        tracker = (
            self.document.athlete_tracker_id
            if verdict is Verdict.SAME_ATHLETE
            else None
        )
        if verdict is Verdict.SAME_ATHLETE and tracker is None:
            raise ValidationError(
                "Önce bu sürümün sporcusunu seçin.",
                code="athlete_not_chosen",
            )
        stamp = _now()
        new = tuple(
            Decision(
                interval_id=interval_id,
                verdict=verdict,
                tracker_id=tracker,
                decided_at=stamp,
                annotator=self.annotator,
            )
            for interval_id in open_ids
        )
        others = tuple(
            d for d in self.document.decisions if d.interval_id not in set(open_ids)
        )
        self._begin()
        self._commit(replace(copy.deepcopy(self.document), decisions=(*others, *new)))
        return len(new)

    def clear_answer(self, interval_id: str) -> None:
        self._begin()
        self._commit(
            replace(
                copy.deepcopy(self.document),
                decisions=tuple(
                    d for d in self.document.decisions if d.interval_id != interval_id
                ),
            )
        )

    # ------------------------------------------------------------- querying
    def candidate(self, tracker_id: Optional[int]) -> Optional[Candidate]:
        if tracker_id is None:
            return None
        return next(
            (c for c in self.candidates if c.tracker_id == int(tracker_id)), None
        )

    def progress(self) -> tuple[int, int]:
        return self.document.progress()

    @property
    def is_settled(self) -> bool:
        return self.document.is_settled

    def next_unanswered(
        self, after: Optional[str] = None
    ) -> Optional[UnsettledInterval]:
        open_intervals = self.document.unanswered
        if not open_intervals:
            return None
        if after is None:
            return open_intervals[0]
        ids = [i.interval_id for i in self.document.intervals]
        try:
            start = ids.index(after) + 1
        except ValueError:
            return open_intervals[0]
        ordered = ids[start:] + ids[:start]
        for interval_id in ordered:
            match = next(
                (i for i in open_intervals if i.interval_id == interval_id), None
            )
            if match is not None:
                return match
        return None

    # -------------------------------------------------------------- storage
    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def flush(self) -> Optional[Path]:
        if not self._dirty:
            return None
        path = save_subject_review(self.take_dir, self.document)
        self._dirty = False
        return path


__all__ = ["SubjectStore", "UNDO_DEPTH"]
