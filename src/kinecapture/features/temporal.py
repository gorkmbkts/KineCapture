"""Time, and derivatives that respect it.

The single most misleading thing a skeleton dataset can contain is a "velocity"
that is really ``x[t] - x[t-1]``. That quantity changes when the frame rate
changes even though the movement did not, and it quietly bridges tracking gaps
as if the body had teleported. So this module keeps two ideas apart:

* **displacement** - the per-frame difference, in length units. Useful, and
  named so nobody mistakes it for a rate.
* **velocity** - the derivative with respect to the *camera timestamps*, in
  length units per second.

Gap policy
----------
A step between two consecutive samples is usable only when its ``dt`` is
positive and no larger than ``max_gap_s``. Anything else - a repeated
timestamp, a timestamp that went backwards, a dropped-frame hole - makes every
derivative that would have crossed it NaN, with the matching validity entry
``False``. A derivative is never computed across a hole and never falls back to
a nominal frame rate.

Boundary policy
---------------
First derivatives use a central difference in the interior and a one-sided
difference at the two ends; a one-sided estimate is a real estimate, unlike a
zero. Second derivatives need three samples, so the two ends are NaN rather
than being extrapolated.

No smoothing is applied anywhere. If a filter is ever added it must arrive as a
new feature version with its window in the parameters, because a silently
smoothed signal is not reproducible from the raw take.
"""

from __future__ import annotations

import numpy as np

#: A step longer than this many nominal frame intervals is treated as a gap.
DEFAULT_GAP_FACTOR: float = 2.5


def max_gap_seconds(target_fps: float, gap_factor: float = DEFAULT_GAP_FACTOR) -> float:
    """Longest inter-frame step still considered continuous, in seconds."""
    if not np.isfinite(target_fps) or target_fps <= 0:
        # With no declared frame rate there is nothing to compare a gap
        # against; only non-positive steps are rejected.
        return float("inf")
    return float(gap_factor) / float(target_fps)


def seconds(timestamps_ns: np.ndarray) -> np.ndarray:
    """Camera timestamps as float64 seconds.

    A zero is *not* special-cased into NaN. It cannot be: the synthetic backend
    legitimately starts its clock at zero. It does not need to be either - a
    stream where a real camera timestamp went missing shows up as a zero
    surrounded by epoch-scale values, and both the step into it (negative) and
    the step out of it (enormous) are rejected by :func:`step_valid` anyway.
    """
    return np.asarray(timestamps_ns, dtype=np.float64) / 1e9


def delta_time_s(timestamps_ns: np.ndarray) -> np.ndarray:
    """``[T]`` seconds since the previous frame; NaN for the first frame."""
    stamps = seconds(timestamps_ns)
    result = np.full(stamps.shape[0], np.nan, dtype=np.float32)
    if stamps.shape[0] > 1:
        result[1:] = (stamps[1:] - stamps[:-1]).astype(np.float32)
    return result


def step_valid(timestamps_ns: np.ndarray, max_gap_s: float) -> np.ndarray:
    """``[T-1]`` mask of usable steps between consecutive frames."""
    stamps = seconds(timestamps_ns)
    if stamps.shape[0] < 2:
        return np.zeros(max(0, stamps.shape[0] - 1), dtype=bool)
    step = stamps[1:] - stamps[:-1]
    with np.errstate(invalid="ignore"):
        return np.isfinite(step) & (step > 0.0) & (step <= max_gap_s)


def _finite_rows(values: np.ndarray, vector: bool) -> np.ndarray:
    """Validity mask for ``values``, one entry per quantity being differentiated.

    ``vector`` says whether the last axis is a coordinate axis. It cannot be
    inferred: ``[T, 3]`` is three scalar series to one caller and one 3-vector
    series to another, and guessing wrong silently produces a mask of the wrong
    rank. So every caller states it.
    """
    array = np.asarray(values, dtype=np.float64)
    if vector and array.ndim >= 2:
        return np.isfinite(array).all(axis=-1)
    return np.isfinite(array)


def central_difference(
    values: np.ndarray,
    timestamps_ns: np.ndarray,
    *,
    max_gap_s: float,
    vector: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """First derivative with respect to time, plus its validity mask.

    ``values`` is ``[T, ...]``. The result has the same shape; the mask drops
    the trailing coordinate axis, so ``[T, J, 3]`` yields a ``[T, J]`` mask.

    Interior samples use ``(x[t+1] - x[t-1]) / (s[t+1] - s[t-1])``, which is
    exact for constant velocity even when the sampling is irregular. The ends
    use the single adjacent step.
    """
    array = np.asarray(values, dtype=np.float64)
    frames = array.shape[0]
    result = np.full(array.shape, np.nan, dtype=np.float64)
    finite = _finite_rows(array, vector)
    mask = np.zeros(finite.shape, dtype=bool)
    if frames < 2:
        return result.astype(np.float32), mask

    stamps = seconds(timestamps_ns)
    usable = step_valid(timestamps_ns, max_gap_s)

    def _assign(target: int, left: int, right: int, allowed: np.ndarray) -> None:
        span = stamps[right] - stamps[left]
        if not np.isfinite(span) or span <= 0:
            return
        ok = allowed & finite[left] & finite[right]
        delta = array[right] - array[left]
        broadcast = ok[..., None] if array.ndim > mask.ndim else ok
        result[target] = np.where(broadcast, delta / span, np.nan)
        mask[target] = ok

    # Interior: central difference, requiring both adjacent steps.
    for position in range(1, frames - 1):
        if usable[position - 1] and usable[position]:
            _assign(position, position - 1, position + 1, np.ones_like(mask[0]))
    # Ends: one-sided.
    if usable[0]:
        _assign(0, 0, 1, np.ones_like(mask[0]))
    if usable[frames - 2]:
        _assign(frames - 1, frames - 2, frames - 1, np.ones_like(mask[0]))
    return result.astype(np.float32), mask


def second_difference(
    values: np.ndarray,
    timestamps_ns: np.ndarray,
    *,
    max_gap_s: float,
    vector: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Second derivative with respect to time, plus its validity mask.

    Uses the non-uniform three-point formula

    ``2 * ((x2 - x1)/dt1 - (x1 - x0)/dt0) / (dt0 + dt1)``

    which is exact for constant acceleration on an irregular grid. The first
    and last samples have no three-point stencil and stay NaN.
    """
    array = np.asarray(values, dtype=np.float64)
    frames = array.shape[0]
    result = np.full(array.shape, np.nan, dtype=np.float64)
    finite = _finite_rows(array, vector)
    mask = np.zeros(finite.shape, dtype=bool)
    if frames < 3:
        return result.astype(np.float32), mask

    stamps = seconds(timestamps_ns)
    usable = step_valid(timestamps_ns, max_gap_s)
    for position in range(1, frames - 1):
        if not (usable[position - 1] and usable[position]):
            continue
        dt0 = stamps[position] - stamps[position - 1]
        dt1 = stamps[position + 1] - stamps[position]
        if not (np.isfinite(dt0) and np.isfinite(dt1)) or dt0 <= 0 or dt1 <= 0:
            continue
        ok = finite[position - 1] & finite[position] & finite[position + 1]
        first = (array[position] - array[position - 1]) / dt0
        second = (array[position + 1] - array[position]) / dt1
        value = 2.0 * (second - first) / (dt0 + dt1)
        broadcast = ok[..., None] if array.ndim > mask.ndim else ok
        result[position] = np.where(broadcast, value, np.nan)
        mask[position] = ok
    return result.astype(np.float32), mask


def frame_difference(
    values: np.ndarray, *, vector: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """``x[t] - x[t-1]``: displacement, explicitly not a rate.

    The first frame has no predecessor and stays NaN. Filling it with zero
    would tell a model the body was stationary at the start of every sample.
    """
    array = np.asarray(values, dtype=np.float64)
    result = np.full(array.shape, np.nan, dtype=np.float64)
    finite = _finite_rows(array, vector)
    mask = np.zeros(finite.shape, dtype=bool)
    if array.shape[0] > 1:
        result[1:] = array[1:] - array[:-1]
        ok = finite[1:] & finite[:-1]
        broadcast = ok[..., None] if array.ndim > mask.ndim else ok
        result[1:] = np.where(broadcast, result[1:], np.nan)
        mask[1:] = ok
    return result.astype(np.float32), mask


def magnitude(vectors: np.ndarray) -> np.ndarray:
    """Euclidean norm over the last axis, NaN-preserving."""
    array = np.asarray(vectors, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        return np.sqrt((array**2).sum(axis=-1)).astype(np.float32)


def path_length(points: np.ndarray, valid: np.ndarray) -> float:
    """Total distance travelled along ``[T, 3]``, skipping invalid steps.

    Steps whose endpoints are not both valid are *skipped*, which understates
    the path rather than inventing motion across a gap. A sample with no valid
    step at all yields NaN, not zero.
    """
    array = np.asarray(points, dtype=np.float64)
    usable = np.asarray(valid, dtype=bool)
    if array.shape[0] < 2:
        return float("nan")
    steps = array[1:] - array[:-1]
    ok = usable[1:] & usable[:-1] & np.isfinite(steps).all(axis=-1)
    if not ok.any():
        return float("nan")
    return float(np.sqrt((steps[ok] ** 2).sum(axis=-1)).sum())


__all__ = [
    "DEFAULT_GAP_FACTOR",
    "central_difference",
    "delta_time_s",
    "frame_difference",
    "magnitude",
    "max_gap_seconds",
    "path_length",
    "seconds",
    "second_difference",
    "step_valid",
]
