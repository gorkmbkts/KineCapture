"""Who the recording is about.

A wrong exercise label teaches the model the wrong name for a movement. A
wrong *athlete* teaches it a bystander's movement under the athlete's name,
and the coordinates look perfectly healthy either way - no later check can
catch it. So these tests are mostly about what the code refuses to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

from kinecapture.core.errors import ValidationError
from kinecapture.processing.annotations import Anchor
from kinecapture.processing.subject_review import (
    Candidate,
    Decision,
    SubjectReview,
    UnsettledInterval,
    Verdict,
    load_subject_review,
    save_subject_review,
    scan_candidates,
    scan_unsettled,
    validate_subject_review,
)
from kinecapture.studio.services.subject_store import SubjectStore

FINGERPRINT = "sha256:" + "cd" * 32


@dataclass
class FakeBody:
    tracking_id: int


@dataclass
class FakeFrame:
    bodies: tuple[FakeBody, ...] = ()
    subject: Optional[dict[str, Any]] = None


def anchor_at(position: int) -> Anchor:
    return Anchor(
        source_fingerprint=FINGERPRINT,
        source_position=position,
        camera_timestamp_ns=1_000_000 * position,
    )


def stream(spec: str) -> list[FakeFrame]:
    """One character per frame: digits are the settled subject, "?" ambiguous.

    "." is a frame with bodies but no subject, "-" a frame with nobody at all.
    """
    frames: list[FakeFrame] = []
    for char in spec:
        if char == "-":
            frames.append(FakeFrame((), {"state": "absent"}))
        elif char == "?":
            frames.append(
                FakeFrame((FakeBody(1), FakeBody(2)), {"state": "ambiguous"})
            )
        elif char == ".":
            frames.append(FakeFrame((FakeBody(1),), {"state": "searching"}))
        else:
            tid = int(char)
            frames.append(
                FakeFrame((FakeBody(1), FakeBody(2)), {"state": "locked", "tracker_id": tid})
            )
    return frames


# ------------------------------------------------------------- candidates
def test_candidates_describe_each_body_so_a_person_can_recognise_it() -> None:
    candidates = scan_candidates(stream("11111222"))
    assert [c.tracker_id for c in candidates] == [1, 2]
    first = candidates[0]
    assert first.frames_present == 8      # body 1 is in every frame
    assert first.frames_as_subject == 5   # ...but only the subject for five
    assert first.first_position == 0 and first.last_position == 7
    assert first.preview_positions  # something to show, not just a number


def test_a_body_that_disappears_and_returns_is_reported_as_broken() -> None:
    frames = [FakeFrame((FakeBody(1),))] * 3
    frames += [FakeFrame(())] * 2
    frames += [FakeFrame((FakeBody(1),))] * 3
    candidates = scan_candidates(frames)
    assert candidates[0].breaks == 1
    assert candidates[0].frames_present == 6
    assert candidates[0].span == 8  # first..last, gap included


def test_previews_come_from_the_bodys_own_span_not_the_takes() -> None:
    frames = [FakeFrame(())] * 10 + [FakeFrame((FakeBody(7),))] * 4
    previews = scan_candidates(frames)[0].preview_positions
    assert previews and min(previews) >= 10


# --------------------------------------------------------------- questions
def test_consecutive_unsettled_frames_become_one_question() -> None:
    intervals = scan_unsettled(stream("111???111"), anchor_at)
    assert len(intervals) == 1
    assert intervals[0].start.source_position == 3
    assert intervals[0].end.source_position == 5
    assert "ambiguous" in intervals[0].states
    assert set(intervals[0].visible) == {1, 2}


def test_separate_unsettled_stretches_stay_separate_questions() -> None:
    intervals = scan_unsettled(stream("1?11?1"), anchor_at)
    assert [(i.start.source_position, i.end.source_position) for i in intervals] == [
        (1, 1), (4, 4)
    ]


def test_a_single_unsettled_frame_is_still_asked_about() -> None:
    """One swapped frame is one wrong label; it does not get rounded away."""
    assert len(scan_unsettled(stream("11?11"), anchor_at)) == 1


def test_an_unsettled_run_reaching_the_end_is_closed() -> None:
    intervals = scan_unsettled(stream("111??"), anchor_at)
    assert len(intervals) == 1 and intervals[0].end.source_position == 4


def test_a_settled_take_asks_nothing() -> None:
    assert scan_unsettled(stream("11111"), anchor_at) == ()


# ------------------------------------------------------------------ store
@pytest.fixture
def store(tmp_path: Path) -> SubjectStore:
    document = SubjectReview(
        processing_run="run_x", source_fingerprint=FINGERPRINT
    )
    store = SubjectStore(
        take_dir=tmp_path,
        document=document,
        candidates=(
            Candidate(tracker_id=1, frames_present=90, first_position=0,
                      last_position=99, breaks=1),
            Candidate(tracker_id=2, frames_present=20, first_position=30,
                      last_position=60, breaks=0),
        ),
        annotator="koc",
    )
    store.set_intervals(scan_unsettled(stream("111???111??1"), anchor_at))
    return store


def test_nothing_is_settled_until_a_person_chooses(store: SubjectStore) -> None:
    assert store.document.athlete_tracker_id is None
    assert not store.is_settled
    assert store.progress() == (0, 2)


def test_answering_same_athlete_needs_an_athlete_first(store: SubjectStore) -> None:
    interval = store.document.intervals[0]
    with pytest.raises(ValidationError) as caught:
        store.answer(interval.interval_id, Verdict.SAME_ATHLETE)
    assert caught.value.code == "athlete_not_chosen"


def test_an_answer_records_who_and_when(store: SubjectStore) -> None:
    store.choose_athlete(1)
    interval = store.document.intervals[0]
    store.answer(interval.interval_id, Verdict.SAME_ATHLETE)

    decision = store.document.decision_for(interval.interval_id)
    assert decision.verdict is Verdict.SAME_ATHLETE
    assert decision.tracker_id == 1       # resolved, not left implicit
    assert decision.decided_at            # and stamped
    assert decision.annotator == "koc"


def test_nobody_here_names_nobody(store: SubjectStore) -> None:
    store.choose_athlete(1)
    interval = store.document.intervals[0]
    store.answer(interval.interval_id, Verdict.NO_ATHLETE)
    assert store.document.decision_for(interval.interval_id).tracker_id is None


def test_saying_other_person_without_saying_who_is_refused(store: SubjectStore) -> None:
    store.choose_athlete(1)
    interval = store.document.intervals[0]
    with pytest.raises(ValidationError) as caught:
        store.answer(interval.interval_id, Verdict.OTHER_PERSON)
    assert caught.value.code == "other_person_without_tracker"
    assert store.document.decision_for(interval.interval_id) is None


def test_choosing_a_body_that_is_not_in_this_version_is_refused(
    store: SubjectStore,
) -> None:
    with pytest.raises(ValidationError) as caught:
        store.choose_athlete(99)
    assert caught.value.code == "unknown_athlete_tracker"
    assert store.document.athlete_tracker_id is None


def test_a_refused_answer_leaves_no_undo_step(store: SubjectStore) -> None:
    store.choose_athlete(1)
    depth = len(store._undo)
    with pytest.raises(ValidationError):
        store.answer(store.document.intervals[0].interval_id, Verdict.OTHER_PERSON)
    assert len(store._undo) == depth


def test_one_answer_is_one_undo(store: SubjectStore) -> None:
    store.choose_athlete(1)
    store.answer(store.document.intervals[0].interval_id, Verdict.SAME_ATHLETE)
    assert store.progress() == (1, 2)
    store.undo()
    assert store.progress() == (0, 2)
    assert store.document.athlete_tracker_id == 1  # only the answer came back off


def test_a_version_is_settled_only_when_every_question_is_answered(
    store: SubjectStore,
) -> None:
    store.choose_athlete(1)
    assert not store.is_settled
    answered = store.answer_all_remaining(Verdict.SAME_ATHLETE)
    assert answered == 2
    assert store.is_settled


def test_bulk_answering_cannot_name_a_different_person(store: SubjectStore) -> None:
    """Applying "someone else" in bulk would attribute frames nobody looked at."""
    store.choose_athlete(1)
    with pytest.raises(ValidationError) as caught:
        store.answer_all_remaining(Verdict.OTHER_PERSON)
    assert caught.value.code == "bulk_verdict_not_allowed"


def test_rescanning_drops_answers_whose_question_is_gone(store: SubjectStore) -> None:
    """An old answer must never land on a different stretch of time."""
    store.choose_athlete(1)
    first = store.document.intervals[0]
    store.answer(first.interval_id, Verdict.SAME_ATHLETE)

    store.set_intervals(scan_unsettled(stream("1?1"), anchor_at))
    assert store.document.decisions == ()
    assert store.progress() == (0, 1)


def test_next_unanswered_walks_the_open_questions(store: SubjectStore) -> None:
    store.choose_athlete(1)
    first = store.next_unanswered()
    assert first is not None
    store.answer(first.interval_id, Verdict.NO_ATHLETE)
    second = store.next_unanswered(first.interval_id)
    assert second is not None and second.interval_id != first.interval_id
    store.answer(second.interval_id, Verdict.NO_ATHLETE)
    assert store.next_unanswered() is None


# ---------------------------------------------------------------- storage
def test_decisions_survive_save_and_reload(store: SubjectStore, tmp_path: Path) -> None:
    store.choose_athlete(2)
    interval = store.document.intervals[0]
    store.answer(interval.interval_id, Verdict.OTHER_PERSON, tracker_id=1, note="komşu")
    path = store.flush()
    assert path is not None

    reloaded = load_subject_review(tmp_path, "run_x", FINGERPRINT)
    assert reloaded.athlete_tracker_id == 2
    decision = reloaded.decision_for(interval.interval_id)
    assert decision.verdict is Verdict.OTHER_PERSON
    assert decision.tracker_id == 1 and decision.note == "komşu"
    assert reloaded.interval(interval.interval_id).start.source_position == 3


def test_a_record_from_another_recording_is_refused(
    store: SubjectStore, tmp_path: Path
) -> None:
    store.choose_athlete(1)
    store.flush()
    with pytest.raises(ValidationError) as caught:
        load_subject_review(tmp_path, "run_x", "sha256:" + "00" * 32)
    assert caught.value.code == "subject_review_source_mismatch"


def test_a_missing_record_is_empty_not_an_error(tmp_path: Path) -> None:
    document = load_subject_review(tmp_path, "run_none", FINGERPRINT)
    assert document.athlete_tracker_id is None and document.intervals == ()


def test_validation_names_a_decision_with_no_question() -> None:
    document = SubjectReview(
        processing_run="r",
        source_fingerprint=FINGERPRINT,
        decisions=(Decision("ghost", Verdict.NO_ATHLETE, decided_at="now"),),
    )
    codes = {p["code"] for p in validate_subject_review(document)}
    assert "decision_without_interval" in codes
