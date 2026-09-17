"""Can the camera see all of you, and did it keep seeing all of you?

This exists because of one sentence from the person who uses the application:
there is nobody else in the room, so the only way to be sure the shot is right
is for the interface to say so. A live indicator on its own does not do that -
at the bottom of a squat, which is exactly where the feet leave the frame, the
screen is unreadable from where the athlete is. So the rule under test is that
the interface remembers.

The measurement is taken from the light preview pose, which is a detection in
the preview image. It is not an identity, it is not recorded, and nothing here
decides anything about the data - only about the picture.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.studio.services.framing import (
    LEFT_ANKLE,
    LEFT_FOOT,
    LEFT_HIP,
    LEFT_SHOULDER,
    NOSE,
    RIGHT_ANKLE,
    RIGHT_FOOT,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    Framing,
    FramingWatch,
    measure,
    subject_box,
)


WIDTH, HEIGHT = 1280, 720


class _Person:
    def __init__(self, points: np.ndarray) -> None:
        self.points = points
        finite = points[np.isfinite(points).all(axis=1)]
        self.bbox = np.array([finite.min(axis=0), finite.max(axis=0)], dtype=np.float32)
        self.confidence = np.ones(len(points), dtype=np.float32)


class _Packet:
    resolution = (WIDTH, HEIGHT)


class _Preview:
    def __init__(self, *people: _Person) -> None:
        self.people = tuple(people)
        self.packet = _Packet()


def _standing(*, head_y: float = 90.0, feet_y: float = 630.0, x: float = 640.0):
    """A whole person, comfortably inside a 1280x720 frame."""
    points = np.full((33, 2), np.nan, dtype=np.float32)
    points[NOSE] = (x, head_y)
    points[LEFT_SHOULDER] = (x - 60, head_y + 70)
    points[RIGHT_SHOULDER] = (x + 60, head_y + 70)
    points[LEFT_HIP] = (x - 40, (head_y + feet_y) / 2)
    points[RIGHT_HIP] = (x + 40, (head_y + feet_y) / 2)
    points[LEFT_ANKLE] = (x - 40, feet_y - 20)
    points[RIGHT_ANKLE] = (x + 40, feet_y - 20)
    points[LEFT_FOOT] = (x - 40, feet_y)
    points[RIGHT_FOOT] = (x + 40, feet_y)
    return _Person(points)


# ------------------------------------------------------------------ reading


def test_a_whole_person_in_the_middle_is_simply_ok() -> None:
    assert measure(_Preview(_standing())).state == "ok"


def test_feet_below_the_frame_are_named_with_what_to_do_about_it() -> None:
    """The one that matters: a squat pushes the feet towards the bottom edge."""
    framing = measure(_Preview(_standing(feet_y=HEIGHT + 5)))
    assert framing.state == "cut"
    assert "Ayaklar" in framing.text
    assert "geri" in framing.advice.casefold()
    assert framing.missing == ("ayaklar",)
    assert not framing.is_usable


def test_a_head_above_the_frame_says_so_too() -> None:
    framing = measure(_Preview(_standing(head_y=-3.0)))
    assert framing.state == "cut"
    assert "Baş" in framing.text


def test_standing_on_the_edge_is_called_tight_rather_than_fine() -> None:
    """Inside the picture with no room left is not the same as framed."""
    # Past the comfort band (7% of the shorter side) but not past the safe
    # one (2%): still in shot, with nothing left over for the next repetition.
    framing = measure(_Preview(_standing(feet_y=HEIGHT - 25)))
    assert framing.state == "tight"
    # Still recordable - it is a warning about the next repetition, not a stop.
    assert framing.is_usable


def test_an_empty_frame_and_a_crowded_one_are_different_answers() -> None:
    assert measure(_Preview()).state == "no_person"
    crowded = measure(_Preview(_standing(x=400.0), _standing(x=900.0)))
    assert crowded.state == "crowded"
    assert "2" in crowded.text


def test_without_the_overlay_it_says_it_cannot_tell_rather_than_ok() -> None:
    """A check that cannot run reports that, instead of reporting success."""
    framing = measure(None)
    assert framing.state == "no_overlay"
    assert not framing.is_usable


def test_a_part_the_detector_never_found_is_not_counted_as_present() -> None:
    person = _standing()
    person.points[LEFT_ANKLE] = np.nan
    person.points[RIGHT_ANKLE] = np.nan
    person.points[LEFT_FOOT] = np.nan
    person.points[RIGHT_FOOT] = np.nan
    framing = measure(_Preview(person))
    assert framing.state == "cut"
    assert "ayaklar" in framing.missing


# ---------------------------------------------------------------- the memory


def test_the_window_reports_the_worst_of_a_rehearsal_not_the_last_frame() -> None:
    """Stand up, walk over, read what happened while you could not look.

    Without this the interface can only describe the instant somebody is
    looking at it, which is never the instant that goes wrong.
    """
    watch = FramingWatch(window_s=15.0)
    now = 0.0
    for _ in range(20):  # standing, fine
        watch.observe(Framing(state="ok"), now=now)
        now += 0.1
    for _ in range(25):  # at the bottom of the squat the feet are gone
        watch.observe(Framing(state="cut", missing=("ayaklar",)), now=now)
        now += 0.1
    for _ in range(20):  # back up, fine again
        watch.observe(Framing(state="ok"), now=now)
        now += 0.1

    assert not watch.clean
    assert watch.seconds_out()["ayaklar"] == pytest.approx(2.5, abs=0.2)
    assert "ayaklar" in watch.verdict
    assert "2.5" in watch.verdict or "2,5" in watch.verdict


def test_a_clean_rehearsal_says_so_in_one_sentence() -> None:
    watch = FramingWatch(window_s=15.0)
    now = 0.0
    for _ in range(60):
        watch.observe(Framing(state="ok"), now=now)
        now += 0.1
    assert watch.clean
    assert watch.verdict == "Son 15 sn: kadraj tamam"


def test_nothing_is_claimed_before_there_is_anything_to_claim() -> None:
    """A fresh window says nothing rather than saying everything was fine."""
    watch = FramingWatch()
    assert watch.verdict == ""
    watch.observe(Framing(state="ok"), now=0.0)
    assert watch.verdict == ""


def test_the_window_forgets_and_a_gap_is_not_time_spent_in_a_state() -> None:
    """A preview that stalled for a minute did not spend a minute framed."""
    watch = FramingWatch(window_s=5.0)
    watch.observe(Framing(state="cut", missing=("ayaklar",)), now=0.0)
    watch.observe(Framing(state="cut", missing=("ayaklar",)), now=60.0)
    # The old sample fell out of the window, and the gap is capped rather than
    # counted as sixty seconds of being out of shot.
    assert watch.seconds_out().get("ayaklar", 0.0) <= 0.5
    for step in range(1, 12):
        watch.observe(Framing(state="ok"), now=60.0 + step * 0.5)
    assert watch.clean


# ------------------------------------------------------- who was picked


def test_the_click_is_matched_to_the_detection_that_contains_it() -> None:
    left, right = _standing(x=300.0), _standing(x=950.0)
    box = subject_box((left, right), (300.0, 400.0))
    assert box is not None
    assert box[0] <= 300.0 <= box[2]


def test_a_lone_person_owns_the_click_even_after_they_have_moved() -> None:
    """The click was about them; they are simply not standing there now."""
    box = subject_box((_standing(x=640.0),), (20.0, 20.0))
    assert box is not None


def test_two_candidates_and_no_containment_draws_nothing() -> None:
    """A box around the wrong person is worse than no box."""
    left, right = _standing(x=300.0), _standing(x=950.0)
    assert subject_box((left, right), (640.0, 10.0)) is None
    assert subject_box((), (1.0, 1.0)) is None
