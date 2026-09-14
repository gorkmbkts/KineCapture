"""Who the recording is about, and what to do where that is unclear.

Every number a model trains on is attributed to a person. If the tracker
swapped to a bystander for two seconds and nobody noticed, those two seconds
are labelled with the athlete's name and are simply wrong - and nothing
downstream can detect it, because the coordinates are perfectly valid.

So this module does two things and refuses a third.

* It **lists the candidates** a version actually contains: how long each was
  tracked, how often they were lost, and which frames show them, so a person
  can recognise the athlete instead of guessing from a tracker id.
* It **finds the moments the tracker was not sure** and turns them into
  questions with three honest answers: the same athlete, someone else, or
  nobody.
* It never picks the nearest or the biggest or the longest-seen person on its
  own. An unanswered question stays unanswered and blocks export.

Decisions are written beside the labels as their own revision - the raw
recording and the processing run are untouched.

No Qt, no SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from kinecapture.core.errors import ValidationError
from kinecapture.core.ids import new_id
from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, path_exists

from .annotations import Anchor

SUBJECT_REVIEW_SCHEMA_VERSION = "1.0.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

#: Tracker states that mean "this frame is not settled". They come from the
#: subject lock; a frame in any of them is a question, not an answer.
UNSETTLED_STATES = frozenset({"ambiguous", "reidentifying", "temporarily_lost"})


class Verdict(str, Enum):
    """What a person said about one unsettled stretch."""

    UNANSWERED = "unanswered"
    SAME_ATHLETE = "same_athlete"
    OTHER_PERSON = "other_person"
    NO_ATHLETE = "no_athlete"


@dataclass(frozen=True)
class Candidate:
    """One tracked body in a version, described so a human can recognise it."""

    tracker_id: int
    frames_present: int
    first_position: int
    last_position: int
    #: Times the body disappeared and came back. A high count usually means the
    #: tracker was struggling, not that the person left.
    breaks: int
    #: Frames worth showing: start, middle, end of this body's own span.
    preview_positions: tuple[int, ...] = ()
    #: Frames where this body was the chosen subject.
    frames_as_subject: int = 0

    @property
    def span(self) -> int:
        return self.last_position - self.first_position + 1

    def coverage(self, frames: int) -> float:
        return self.frames_present / frames if frames else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracker_id": self.tracker_id,
            "frames_present": self.frames_present,
            "first_position": self.first_position,
            "last_position": self.last_position,
            "breaks": self.breaks,
            "preview_positions": list(self.preview_positions),
            "frames_as_subject": self.frames_as_subject,
        }


@dataclass(frozen=True)
class UnsettledInterval:
    """A stretch of frames the tracker could not settle, as one question."""

    interval_id: str
    start: Anchor
    end: Anchor
    #: The states seen inside, for the "why is this being asked" line.
    states: tuple[str, ...] = ()
    #: Tracker ids visible during the stretch, most-seen first.
    visible: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "states": list(self.states),
            "visible": list(self.visible),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnsettledInterval":
        return cls(
            interval_id=str(payload["interval_id"]),
            start=Anchor.from_dict(payload["start"]),
            end=Anchor.from_dict(payload["end"]),
            states=tuple(str(s) for s in payload.get("states") or ()),
            visible=tuple(int(i) for i in payload.get("visible") or ()),
        )


@dataclass(frozen=True)
class Decision:
    """One answer. ``tracker_id`` is required only when a body was chosen."""

    interval_id: str
    verdict: Verdict = Verdict.UNANSWERED
    tracker_id: Optional[int] = None
    decided_at: str = ""
    annotator: str = ""
    note: str = ""

    @property
    def is_answered(self) -> bool:
        return self.verdict is not Verdict.UNANSWERED and bool(self.decided_at)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interval_id": self.interval_id,
            "verdict": self.verdict.value,
            "decided_at": self.decided_at,
        }
        if self.tracker_id is not None:
            payload["tracker_id"] = int(self.tracker_id)
        if self.annotator:
            payload["annotator"] = self.annotator
        if self.note:
            payload["note"] = self.note
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Decision":
        raw = payload.get("tracker_id")
        return cls(
            interval_id=str(payload["interval_id"]),
            verdict=Verdict(str(payload.get("verdict", "unanswered"))),
            tracker_id=None if raw is None else int(raw),
            decided_at=str(payload.get("decided_at", "")),
            annotator=str(payload.get("annotator", "")),
            note=str(payload.get("note", "")),
        )


@dataclass
class SubjectReview:
    """The athlete choice and the answers, for one processing version."""

    processing_run: str
    source_fingerprint: str
    #: The tracker id the whole version is attributed to. ``None`` until a
    #: person chooses; nothing guesses it.
    athlete_tracker_id: Optional[int] = None
    chosen_at: str = ""
    intervals: tuple[UnsettledInterval, ...] = ()
    decisions: tuple[Decision, ...] = ()
    annotator: str = ""
    updated_at: str = ""
    revision: int = 1
    schema_version: str = SUBJECT_REVIEW_SCHEMA_VERSION

    # ------------------------------------------------------------- lookups
    def decision_for(self, interval_id: str) -> Optional[Decision]:
        return next((d for d in self.decisions if d.interval_id == interval_id), None)

    def interval(self, interval_id: str) -> Optional[UnsettledInterval]:
        return next((i for i in self.intervals if i.interval_id == interval_id), None)

    @property
    def unanswered(self) -> tuple[UnsettledInterval, ...]:
        return tuple(
            interval
            for interval in self.intervals
            if not (self.decision_for(interval.interval_id) or Decision("")).is_answered
        )

    @property
    def is_settled(self) -> bool:
        """Ready to export: an athlete is chosen and no question is open."""
        return self.athlete_tracker_id is not None and not self.unanswered

    def progress(self) -> tuple[int, int]:
        answered = len(self.intervals) - len(self.unanswered)
        return answered, len(self.intervals)

    # ------------------------------------------------------------- storage
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "processing_run": self.processing_run,
            "source_fingerprint": self.source_fingerprint,
            "athlete_tracker_id": self.athlete_tracker_id,
            "chosen_at": self.chosen_at,
            "annotator": self.annotator,
            "updated_at": self.updated_at,
            "revision": self.revision,
            "intervals": [i.to_dict() for i in self.intervals],
            "decisions": [d.to_dict() for d in self.decisions],
            "policy": (
                "Belirsiz aralıklar yalnız insana sorulur. En yakın, en büyük "
                "veya en uzun görülen kişiye sessizce geçilmez; cevaplanmamış "
                "aralık dışa aktarımı durdurur."
            ),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SubjectReview":
        raw = payload.get("athlete_tracker_id")
        return cls(
            processing_run=str(payload.get("processing_run", "")),
            source_fingerprint=str(payload.get("source_fingerprint", "")),
            athlete_tracker_id=None if raw is None else int(raw),
            chosen_at=str(payload.get("chosen_at", "")),
            intervals=tuple(
                UnsettledInterval.from_dict(i) for i in payload.get("intervals") or ()
            ),
            decisions=tuple(Decision.from_dict(d) for d in payload.get("decisions") or ()),
            annotator=str(payload.get("annotator", "")),
            updated_at=str(payload.get("updated_at", "")),
            revision=int(payload.get("revision", 1)),
            schema_version=str(
                payload.get("schema_version", SUBJECT_REVIEW_SCHEMA_VERSION)
            ),
        )


# --------------------------------------------------------------------- scan
def scan_candidates(
    frames: Sequence[Any], *, max_previews: int = 3
) -> tuple[Candidate, ...]:
    """Describe every body the version contains, longest-tracked first.

    ``frames`` is the run's skeleton stream. Tracker ids are *per recording*:
    they identify a body within this take and nothing beyond it.
    """
    seen: dict[int, dict[str, Any]] = {}
    for position, frame in enumerate(frames):
        subject = frame.subject or {}
        chosen = subject.get("tracker_id")
        for body in frame.bodies:
            entry = seen.setdefault(
                int(body.tracking_id),
                {"positions": [], "as_subject": 0},
            )
            entry["positions"].append(position)
            if chosen is not None and int(chosen) == int(body.tracking_id):
                entry["as_subject"] += 1

    candidates: list[Candidate] = []
    for tracker_id, entry in seen.items():
        positions: list[int] = entry["positions"]
        breaks = sum(
            1
            for previous, current in zip(positions, positions[1:])
            if current != previous + 1
        )
        candidates.append(
            Candidate(
                tracker_id=tracker_id,
                frames_present=len(positions),
                first_position=positions[0],
                last_position=positions[-1],
                breaks=breaks,
                preview_positions=_previews(positions, max_previews),
                frames_as_subject=int(entry["as_subject"]),
            )
        )
    candidates.sort(key=lambda c: (-c.frames_present, c.first_position))
    return tuple(candidates)


def _previews(positions: Sequence[int], count: int) -> tuple[int, ...]:
    """Start, middle and end of a body's own span - not of the whole take."""
    if not positions:
        return ()
    if len(positions) <= count:
        return tuple(positions)
    picks = {positions[0], positions[len(positions) // 2], positions[-1]}
    return tuple(sorted(picks))


def scan_unsettled(
    frames: Sequence[Any], anchor_at, *, min_frames: int = 1
) -> tuple[UnsettledInterval, ...]:
    """Group consecutive unsettled frames into one question each.

    Frames are grouped so a coach answers "this two-second stretch" once
    instead of eighty times. A stretch shorter than ``min_frames`` is still
    reported: a single swapped frame is a single wrong label.
    """
    intervals: list[UnsettledInterval] = []
    run_start: Optional[int] = None
    states: list[str] = []
    visible: dict[int, int] = {}

    def close(end: int) -> None:
        if run_start is None or (end - run_start + 1) < min_frames:
            return
        ordered = sorted(visible.items(), key=lambda kv: -kv[1])
        intervals.append(
            UnsettledInterval(
                interval_id=new_id("amb"),
                start=anchor_at(run_start),
                end=anchor_at(end),
                states=tuple(sorted(set(states))),
                visible=tuple(int(i) for i, _ in ordered),
            )
        )

    for position, frame in enumerate(frames):
        subject = frame.subject or {}
        state = str(subject.get("state", ""))
        unsettled = state in UNSETTLED_STATES
        if unsettled:
            if run_start is None:
                run_start, states, visible = position, [], {}
            states.append(state)
            for body in frame.bodies:
                visible[int(body.tracking_id)] = visible.get(int(body.tracking_id), 0) + 1
        elif run_start is not None:
            close(position - 1)
            run_start = None
    if run_start is not None:
        close(len(frames) - 1)
    return tuple(intervals)


# ------------------------------------------------------------------ storage
def subject_review_path(take_dir: Path, run_id: str) -> Path:
    return Path(take_dir) / "annotations" / "processing" / f"{run_id}.subject.json"


def load_subject_review(
    take_dir: Path, run_id: str, source_fingerprint: str
) -> SubjectReview:
    """This version's athlete decisions, or an empty record. Never another's."""
    path = subject_review_path(take_dir, run_id)
    if not path_exists(path):
        return SubjectReview(
            processing_run=run_id, source_fingerprint=source_fingerprint
        )
    document = SubjectReview.from_dict(dict(read_json(path)))
    if (
        document.source_fingerprint
        and document.source_fingerprint != source_fingerprint
    ):
        raise ValidationError(
            "Bu kişi kararı dosyası başka bir ham kayda ait.",
            code="subject_review_source_mismatch",
            remedy="Doğru sürümü açın; kararlar taşınmaz.",
            details={
                "document": document.source_fingerprint,
                "version": source_fingerprint,
            },
        )
    return document


def save_subject_review(take_dir: Path, document: SubjectReview) -> Path:
    path = subject_review_path(take_dir, document.processing_run)
    ensure_dir(path.parent)
    document.updated_at = _utc_now()
    write_json(path, document.to_dict(), overwrite=True)
    return path


def validate_subject_review(
    document: SubjectReview, *, known_trackers: Iterable[int] = ()
) -> list[dict[str, Any]]:
    """Problems that must be fixed before this version can be exported."""
    problems: list[dict[str, Any]] = []
    trackers = {int(i) for i in known_trackers}
    ids = [i.interval_id for i in document.intervals]
    if len(ids) != len(set(ids)):
        problems.append({
            "code": "duplicate_interval_id",
            "message": "Aynı belirsiz aralık kimliği birden fazla kez geçiyor.",
        })
    if document.athlete_tracker_id is not None and trackers:
        if document.athlete_tracker_id not in trackers:
            problems.append({
                "code": "unknown_athlete_tracker",
                "message": "Seçilen kişi bu sürümde bulunamadı.",
                "tracker_id": document.athlete_tracker_id,
            })
    for decision in document.decisions:
        if document.interval(decision.interval_id) is None:
            problems.append({
                "code": "decision_without_interval",
                "message": "Bir karar, var olmayan bir aralığa ait.",
                "interval_id": decision.interval_id,
            })
        if decision.verdict is Verdict.OTHER_PERSON and decision.tracker_id is None:
            # "Someone else" without saying who leaves the stretch attributed
            # to nobody, which is not an answer.
            problems.append({
                "code": "other_person_without_tracker",
                "message": "'Diğer kişi' denildiğinde hangi kişi olduğu seçilmelidir.",
                "interval_id": decision.interval_id,
            })
        if decision.verdict is not Verdict.UNANSWERED and not decision.decided_at:
            problems.append({
                "code": "decision_without_timestamp",
                "message": "Karar, ne zaman verildiği yazılmadan kaydedilemez.",
                "interval_id": decision.interval_id,
            })
    return problems


__all__ = [
    "SUBJECT_REVIEW_SCHEMA_VERSION",
    "UNSETTLED_STATES",
    "Candidate",
    "Decision",
    "SubjectReview",
    "UnsettledInterval",
    "Verdict",
    "load_subject_review",
    "save_subject_review",
    "scan_candidates",
    "scan_unsettled",
    "subject_review_path",
    "validate_subject_review",
]
