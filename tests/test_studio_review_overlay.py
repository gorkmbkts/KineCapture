"""The 2-D overlay draws what was measured, and nothing else.

On the 20 September recording, four white bones ran from the athlete's
shoulders to just off the top-left corner of the picture in every frame where
a face landmark was hidden. The joints were not missing from the array: the
ZED writes ``(-1, -1)`` for a joint it cannot place in the image, and ``-1``
is a perfectly finite number, so the painter's ``isfinite`` check let it
through and drew a bone to it.

The array keeps the sentinel - it is a raw passthrough and it should stay one.
What changed is that the reader says which of those pixels were measured,
using the run's own validity mask, and refuses a negative pixel on its own
terms: a negative coordinate is not a place in an image.
"""

from __future__ import annotations

import numpy as np

from kinecapture.studio.services.review import ReviewSession


class _Dataset:
    """Just enough of a dataset to answer two window() calls."""

    def __init__(self, points, valid=None) -> None:
        self.points = np.asarray(points, dtype=np.float32)
        self.valid = None if valid is None else np.asarray(valid, dtype=bool)

    def window(self, key: str, start: int, end: int):  # noqa: ANN201
        if key == "joint_positions_2d":
            return self.points[start:end]
        if key == "joint_valid_mask":
            if self.valid is None:
                raise KeyError(key)
            return self.valid[start:end]
        raise KeyError(key)


def _session(points, valid=None) -> ReviewSession:
    session = ReviewSession.__new__(ReviewSession)
    session.dataset = _Dataset(points, valid)
    session._has_joints_2d = True
    session._joints_2d_reason = ""
    session._frames = len(points)
    return session


def _joints_2d(session, position: int):
    """The real method, with the frames/size questions answered inline."""
    return ReviewSession.joints_2d(session, position)


def test_the_minus_one_sentinel_never_reaches_the_painter(monkeypatch) -> None:
    points = [[[10.0, 20.0], [-1.0, -1.0], [30.0, 40.0]]]
    session = _session(points, valid=[[True, False, True]])
    monkeypatch.setattr(type(session), "frames", property(lambda _s: 1))
    monkeypatch.setattr(
        type(session), "joints_2d_available", property(lambda _s: True)
    )

    drawn = _joints_2d(session, 0)

    assert np.isfinite(drawn[0]).all()
    assert not np.isfinite(drawn[1]).any(), "the sentinel is still drawable"
    assert np.isfinite(drawn[2]).all()


def test_a_run_without_a_validity_mask_still_refuses_a_negative_pixel(
    monkeypatch,
) -> None:
    """An older version has no mask. The coordinate answers for itself."""
    points = [[[10.0, 20.0], [-1.0, -1.0], [0.0, 0.0]]]
    session = _session(points, valid=None)
    monkeypatch.setattr(type(session), "frames", property(lambda _s: 1))
    monkeypatch.setattr(
        type(session), "joints_2d_available", property(lambda _s: True)
    )

    drawn = _joints_2d(session, 0)

    assert np.isfinite(drawn[0]).all()
    assert not np.isfinite(drawn[1]).any()
    # (0, 0) is the corner pixel and a legitimate, if unlikely, location.
    # Nothing here invents a second sentinel.
    assert np.isfinite(drawn[2]).all()


def test_the_mask_can_veto_a_pixel_that_looks_fine(monkeypatch) -> None:
    """The tracker's own answer outranks how plausible the number looks."""
    points = [[[10.0, 20.0], [640.0, 360.0]]]
    session = _session(points, valid=[[True, False]])
    monkeypatch.setattr(type(session), "frames", property(lambda _s: 1))
    monkeypatch.setattr(
        type(session), "joints_2d_available", property(lambda _s: True)
    )

    drawn = _joints_2d(session, 0)

    assert np.isfinite(drawn[0]).all()
    assert not np.isfinite(drawn[1]).any()


def test_the_stored_array_is_not_rewritten(monkeypatch) -> None:
    """The raw passthrough stays raw; only what is read out is masked."""
    points = [[[10.0, 20.0], [-1.0, -1.0]]]
    session = _session(points, valid=[[True, False]])
    monkeypatch.setattr(type(session), "frames", property(lambda _s: 1))
    monkeypatch.setattr(
        type(session), "joints_2d_available", property(lambda _s: True)
    )

    _joints_2d(session, 0)

    assert session.dataset.points[0][1].tolist() == [-1.0, -1.0]
