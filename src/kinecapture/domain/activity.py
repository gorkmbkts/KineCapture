"""Labelling a whole take on a timeline, not just its repetitions.

The movement-sample model answers "was this repetition correct?". It cannot
answer "did the person start exercising, and when?" - because everything
between the repetitions, which is most of a real session, is simply not in the
dataset. Waiting, walking over, adjusting a shoe, tying a lace, sitting down:
all of it is thrown away, and a model trained on what is left has never seen
what "not exercising" looks like.

This module adds a second, optional layer over the same take: a strip of
mutually exclusive activity states covering time.

``background``
    Waiting, standing neutrally, sitting. Plainly not exercising.
``transition``
    Getting into or out of a starting position.
``target_exercise``
    The exercise that is to be recognised. Carries the exercise code, and may
    be linked to a :class:`MovementSample` so the two cannot drift apart.
``other_activity``
    Walking, bending down to pick something up, straightening clothing - real
    movement that is not the target exercise.

The rule that matters most
--------------------------
``unlabelled`` is **not** a class, and unlabelled time is **not** background.
A frame nobody has looked at says nothing; treating it as "not exercising"
would teach a model that the annotator's attention span is a feature of human
movement. Unlabelled time is therefore tracked separately, drawn differently,
excluded from targets by an explicit mask, and only ever converted to
background by a deliberate, confirmed action.

Boundaries follow the same convention as everything else in this project:
positions are 0-based indices into the take's recorded pose stream, and ranges
are inclusive at both ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

from kinecapture.core.ids import new_id, utc_now_iso
from kinecapture.domain.enums import SegmentSource


class ActivityState(str, Enum):
    """What the person was doing. Mutually exclusive over time."""

    BACKGROUND = "background"
    TRANSITION = "transition"
    TARGET_EXERCISE = "target_exercise"
    OTHER_ACTIVITY = "other_activity"

    @property
    def label(self) -> str:
        return {
            ActivityState.BACKGROUND: "Arka plan",
            ActivityState.TRANSITION: "Geçiş",
            ActivityState.TARGET_EXERCISE: "Hedef egzersiz",
            ActivityState.OTHER_ACTIVITY: "Diğer hareket",
        }[self]

    @property
    def description(self) -> str:
        return {
            ActivityState.BACKGROUND: "Bekleme, nötr duruş, oturma.",
            ActivityState.TRANSITION: (
                "Başlangıç pozisyonuna geçme veya oradan çıkma."
            ),
            ActivityState.TARGET_EXERCISE: "Tanınması istenen egzersiz.",
            ActivityState.OTHER_ACTIVITY: (
                "Yürüme, eğilme, kıyafet düzeltme gibi hedef dışı hareket."
            ),
        }[self]

    @property
    def code(self) -> int:
        """Stable integer written into ``activity_state_code``.

        ``-1`` is reserved for unlabelled and is never one of these.
        """
        return {
            ActivityState.BACKGROUND: 0,
            ActivityState.TRANSITION: 1,
            ActivityState.TARGET_EXERCISE: 2,
            ActivityState.OTHER_ACTIVITY: 3,
        }[self]

    @property
    def requires_exercise(self) -> bool:
        return self is ActivityState.TARGET_EXERCISE

    @classmethod
    def parse(cls, value: object) -> "ActivityState":
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        for member in cls:
            if member.value == text:
                return member
        return cls.BACKGROUND


#: Code used in exported arrays for a frame nobody has labelled. Deliberately
#: outside the state codes so no consumer can mistake it for background.
UNLABELLED_CODE = -1

#: The state code order, written into the release so an index is never guessed.
ACTIVITY_STATE_ORDER: tuple[ActivityState, ...] = (
    ActivityState.BACKGROUND,
    ActivityState.TRANSITION,
    ActivityState.TARGET_EXERCISE,
    ActivityState.OTHER_ACTIVITY,
)


@dataclass
class ActivityInterval:
    """One stretch of time in a single activity state.

    ``linked_sample_id`` ties a ``target_exercise`` stretch to the movement
    sample that describes the same repetition. When it is set, the *sample*
    owns the boundaries: editing them in one place moves the other, so the two
    can never quietly disagree about where the exercise was.
    """

    interval_id: str
    state: ActivityState = ActivityState.BACKGROUND
    start_frame: int = 0
    end_frame: int = 0
    exercise: str = ""
    linked_sample_id: str = ""
    note: str = ""
    source: SegmentSource = SegmentSource.MANUAL
    start_timestamp_ns: Optional[int] = None
    end_timestamp_ns: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    legacy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        start_frame: int,
        end_frame: int,
        *,
        state: ActivityState = ActivityState.BACKGROUND,
        exercise: str = "",
        linked_sample_id: str = "",
        source: SegmentSource = SegmentSource.MANUAL,
    ) -> "ActivityInterval":
        low, high = sorted((int(start_frame), int(end_frame)))
        return cls(
            interval_id=new_id("act"),
            state=state,
            start_frame=low,
            end_frame=high,
            exercise=exercise,
            linked_sample_id=linked_sample_id,
            source=source,
        )

    # ------------------------------------------------------------ geometry
    @property
    def frame_count(self) -> int:
        return max(0, self.end_frame - self.start_frame + 1)

    @property
    def is_well_formed(self) -> bool:
        return self.end_frame >= self.start_frame >= 0

    def contains(self, position: int) -> bool:
        return self.start_frame <= position <= self.end_frame

    def overlaps(self, other: "ActivityInterval") -> bool:
        return (
            self.start_frame <= other.end_frame
            and other.start_frame <= self.end_frame
        )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    # --------------------------------------------------------- validation
    def problems(self, *, frame_count: Optional[int] = None) -> list[str]:
        """Everything wrong with this interval, in Turkish, for the UI."""
        issues: list[str] = []
        if not self.is_well_formed:
            issues.append("Aralığın bitişi başlangıcından önce.")
        if frame_count is not None and self.end_frame >= frame_count:
            issues.append(
                f"Aralık kaydın dışına taşıyor (son kare {frame_count - 1})."
            )
        if self.state.requires_exercise and not self.exercise:
            issues.append("Hedef egzersiz aralığına egzersiz türü seçilmemiş.")
        if not self.state.requires_exercise and self.exercise:
            issues.append(
                "Yalnız hedef egzersiz aralıkları egzersiz türü taşıyabilir."
            )
        return issues

    # ------------------------------------------------------ serialisation
    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interval_id": self.interval_id,
            "state": self.state.value,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "source": self.source.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.exercise:
            payload["exercise"] = self.exercise
        if self.linked_sample_id:
            payload["linked_sample_id"] = self.linked_sample_id
        if self.note:
            payload["note"] = self.note
        if self.start_timestamp_ns is not None:
            payload["start_timestamp_ns"] = self.start_timestamp_ns
        if self.end_timestamp_ns is not None:
            payload["end_timestamp_ns"] = self.end_timestamp_ns
        if self.legacy:
            payload["legacy"] = dict(self.legacy)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActivityInterval":
        data = dict(payload)
        known = {
            "interval_id",
            "state",
            "start_frame",
            "end_frame",
            "exercise",
            "linked_sample_id",
            "note",
            "source",
            "start_timestamp_ns",
            "end_timestamp_ns",
            "created_at",
            "updated_at",
            "legacy",
        }
        legacy = dict(data.get("legacy") or {})
        for key, value in data.items():
            if key not in known:
                legacy[key] = value
        source = data.get("source", SegmentSource.MANUAL.value)
        try:
            parsed_source = SegmentSource(source)
        except ValueError:
            legacy["source"] = source
            parsed_source = SegmentSource.MANUAL
        return cls(
            interval_id=str(data.get("interval_id") or new_id("act")),
            state=ActivityState.parse(data.get("state")),
            start_frame=int(data.get("start_frame", 0)),
            end_frame=int(data.get("end_frame", 0)),
            exercise=str(data.get("exercise") or ""),
            linked_sample_id=str(data.get("linked_sample_id") or ""),
            note=str(data.get("note") or ""),
            source=parsed_source,
            start_timestamp_ns=data.get("start_timestamp_ns"),
            end_timestamp_ns=data.get("end_timestamp_ns"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            legacy=legacy,
        )


class ContinuousReadiness(str, Enum):
    """Whether a take can be exported as a continuous-activity example.

    Deliberately independent of movement-sample readiness. A take of somebody
    stretching and never performing the target exercise is worthless to the
    repetition dataset and valuable to the continuous one; a take with two
    perfectly labelled repetitions and no activity strip is the reverse.
    """

    READY = "ready"
    #: No activity interval at all - the layer was simply not used here.
    NOT_ANNOTATED = "not_annotated"
    #: Some frames carry no activity label. Exportable with a mask, or a
    #: blocker when the user demands full coverage.
    PARTIAL_COVERAGE = "partial_coverage"
    #: Two mutually exclusive states claim the same frame.
    OVERLAPPING = "overlapping"
    #: An interval is reversed, outside the take, or missing its exercise.
    INVALID_INTERVAL = "invalid_interval"

    @property
    def is_ready(self) -> bool:
        return self is ContinuousReadiness.READY

    @property
    def label(self) -> str:
        return {
            ContinuousReadiness.READY: "Hazır",
            ContinuousReadiness.NOT_ANNOTATED: "Aktivite etiketi yok",
            ContinuousReadiness.PARTIAL_COVERAGE: "Kısmi kapsam",
            ContinuousReadiness.OVERLAPPING: "Çakışan aralık",
            ContinuousReadiness.INVALID_INTERVAL: "Geçersiz aralık",
        }[self]


@dataclass
class ActivityCoverage:
    """How much of a take has an activity label, and what kind."""

    frame_count: int = 0
    labelled_frames: int = 0
    per_state: dict[str, int] = field(default_factory=dict)
    exercise_starts: int = 0
    exercise_ends: int = 0
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    invalid: list[tuple[str, str]] = field(default_factory=list)

    @property
    def unlabelled_frames(self) -> int:
        return max(0, self.frame_count - self.labelled_frames)

    @property
    def ratio(self) -> float:
        return self.labelled_frames / self.frame_count if self.frame_count else 0.0

    @property
    def is_complete(self) -> bool:
        return self.frame_count > 0 and self.unlabelled_frames == 0

    def seconds(self, state: ActivityState, fps: float) -> float:
        return self.per_state.get(state.value, 0) / fps if fps > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_count": self.frame_count,
            "labelled_frames": self.labelled_frames,
            "unlabelled_frames": self.unlabelled_frames,
            "ratio": round(self.ratio, 4),
            "per_state": dict(self.per_state),
            "exercise_starts": self.exercise_starts,
            "exercise_ends": self.exercise_ends,
            "overlaps": [list(pair) for pair in self.overlaps],
            "invalid": [list(pair) for pair in self.invalid],
        }


def sort_intervals(intervals: Iterable[ActivityInterval]) -> list[ActivityInterval]:
    return sorted(intervals, key=lambda item: (item.start_frame, item.end_frame))


def find_overlaps(
    intervals: Sequence[ActivityInterval],
) -> list[tuple[ActivityInterval, ActivityInterval]]:
    """Every pair of intervals claiming the same frame.

    The states are mutually exclusive by definition, so any overlap at all is a
    contradiction - unlike error intervals, where overlap is meaningful.
    """
    ordered = sort_intervals(intervals)
    clashes: list[tuple[ActivityInterval, ActivityInterval]] = []
    for position, first in enumerate(ordered):
        for second in ordered[position + 1 :]:
            if second.start_frame > first.end_frame:
                break
            if first.overlaps(second):
                clashes.append((first, second))
    return clashes


def unlabelled_gaps(
    intervals: Sequence[ActivityInterval], frame_count: int
) -> list[tuple[int, int]]:
    """Inclusive ranges nobody has labelled yet."""
    if frame_count <= 0:
        return []
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for interval in sort_intervals(intervals):
        if interval.start_frame > cursor:
            gaps.append((cursor, min(interval.start_frame - 1, frame_count - 1)))
        cursor = max(cursor, interval.end_frame + 1)
        if cursor >= frame_count:
            break
    if cursor < frame_count:
        gaps.append((cursor, frame_count - 1))
    return [(low, high) for low, high in gaps if high >= low]


def measure_coverage(
    intervals: Sequence[ActivityInterval],
    frame_count: int,
    *,
    known_exercises: Optional[Sequence[str]] = None,
) -> ActivityCoverage:
    """Summarise an activity strip without changing it."""
    coverage = ActivityCoverage(frame_count=max(0, int(frame_count)))
    covered: set[int] = set()
    vocabulary = set(known_exercises or ())
    for interval in sort_intervals(intervals):
        issues = interval.problems(frame_count=frame_count or None)
        if vocabulary and interval.exercise and interval.exercise not in vocabulary:
            issues.append(
                f"'{interval.exercise}' egzersizi proje şemasında yok."
            )
        for issue in issues:
            coverage.invalid.append((interval.interval_id, issue))
        if not interval.is_well_formed:
            continue
        low = max(0, interval.start_frame)
        high = min(interval.end_frame, coverage.frame_count - 1)
        if high < low:
            continue
        span = set(range(low, high + 1))
        covered |= span
        coverage.per_state[interval.state.value] = (
            coverage.per_state.get(interval.state.value, 0) + len(span)
        )
        if interval.state is ActivityState.TARGET_EXERCISE:
            coverage.exercise_starts += 1
            coverage.exercise_ends += 1
    coverage.labelled_frames = len(covered)
    coverage.overlaps = [
        (first.interval_id, second.interval_id)
        for first, second in find_overlaps(intervals)
    ]
    return coverage


def evaluate_continuous(
    intervals: Sequence[ActivityInterval],
    frame_count: int,
    *,
    known_exercises: Optional[Sequence[str]] = None,
    require_full_coverage: bool = False,
) -> tuple[ContinuousReadiness, ActivityCoverage]:
    """The single rule for "can this take be a continuous example?".

    Used by the review screen and by the exporter, for the same reason the
    movement-sample rule is shared: two definitions of ready would eventually
    disagree, and the user would be the one to find out.
    """
    coverage = measure_coverage(
        intervals, frame_count, known_exercises=known_exercises
    )
    if coverage.invalid:
        return ContinuousReadiness.INVALID_INTERVAL, coverage
    if coverage.overlaps:
        return ContinuousReadiness.OVERLAPPING, coverage
    if not intervals:
        return ContinuousReadiness.NOT_ANNOTATED, coverage
    if require_full_coverage and not coverage.is_complete:
        return ContinuousReadiness.PARTIAL_COVERAGE, coverage
    return ContinuousReadiness.READY, coverage


def activity_label_mapping() -> dict[str, Any]:
    """The block a release writes so an integer code is never guessed."""
    return {
        "version": "1.0.0",
        "classes": [state.value for state in ACTIVITY_STATE_ORDER],
        "code_to_state": {
            str(state.code): state.value for state in ACTIVITY_STATE_ORDER
        },
        "state_to_code": {state.value: state.code for state in ACTIVITY_STATE_ORDER},
        "labels": {state.value: state.label for state in ACTIVITY_STATE_ORDER},
        "descriptions": {
            state.value: state.description for state in ACTIVITY_STATE_ORDER
        },
        "unlabelled_code": UNLABELLED_CODE,
        "unlabelled_note": (
            "Etiketlenmemiş kare bir sınıf DEĞİLDİR ve background sayılmaz. "
            f"activity_state_code içinde {UNLABELLED_CODE} ile işaretlenir ve "
            "activity_label_mask içinde False'tur."
        ),
        "mutually_exclusive": True,
        "boundary_convention": (
            "start_frame ve end_frame, derived/skeleton.jsonl kare listesindeki "
            "0 tabanlı konumlardır ve her iki uç dahildir."
        ),
    }


__all__ = [
    "ACTIVITY_STATE_ORDER",
    "ActivityCoverage",
    "ActivityInterval",
    "ActivityState",
    "ContinuousReadiness",
    "UNLABELLED_CODE",
    "activity_label_mapping",
    "evaluate_continuous",
    "find_overlaps",
    "measure_coverage",
    "sort_intervals",
    "unlabelled_gaps",
]
