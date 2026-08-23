"""A fixed-length summary vector for models that cannot read a sequence.

Random forests, SVMs and gradient-boosted trees need one row per sample, not a
``[T, J, 3]`` tensor. This module produces that row - and its element names -
from the same context every other feature reads.

Three rules make it safe to hand to a classical model:

* **The length never changes.** Elements are generated from the fixed
  definition lists (roles, angles, distances, ratios, bilateral pairs), not
  from whatever joints a particular skeleton happens to have. A quantity this
  sample cannot produce is NaN in its slot; the slot itself is always there,
  so two samples from different skeleton formats still line up column for
  column.
* **Nothing looks outside the sample.** No class means, no distance to a
  "correct" template, no scaler fitted over the dataset, no participant
  statistics. Every one of those would move information across a train/test
  split, and a leaked feature is worse than a missing one.
* **Names travel with the numbers.** :func:`summary_names` is written into the
  release, in the same order as the vector.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from kinecapture.features.definitions import (
    ANGLE_IDS,
    BILATERAL_ANGLE_GROUPS,
    DISTANCE_IDS,
    RATIO_IDS,
)
from kinecapture.features.roles import ALL_ROLES, BILATERAL_ROLE_PAIRS
from kinecapture.features.temporal import path_length, seconds

if TYPE_CHECKING:  # pragma: no cover - typing only
    from kinecapture.features.compute import FeatureContext

#: Bumped whenever the element list or any element's meaning changes.
SUMMARY_VERSION = "1.0.0"

_GLOBAL_NAMES: tuple[str, ...] = (
    "duration_s",
    "num_frames",
    "measured_fps",
    "frame_valid_ratio",
    "joint_valid_ratio",
    "mean_joint_confidence",
    "body_scale",
    "root_path_length",
    "root_speed_mean",
    "root_speed_max",
)

_ANGLE_STATS: tuple[str, ...] = (
    "min",
    "max",
    "range",
    "mean",
    "std",
    "median",
    "iqr",
    "angular_speed_rms",
    "angular_speed_max",
)
_BILATERAL_ANGLE_STATS: tuple[str, ...] = (
    "abs_difference_mean",
    "abs_difference_max",
    "signed_difference_mean",
)
_PAIR_STATS: tuple[str, ...] = ("speed_abs_difference_mean", "mirror_distance_mean")
_DISTANCE_STATS: tuple[str, ...] = ("mean", "std", "min", "max")
_RATIO_STATS: tuple[str, ...] = ("mean", "std")
_ROLE_STATS: tuple[str, ...] = (
    "speed_mean",
    "speed_max",
    "path_length",
    "vertical_range",
)


def summary_names() -> tuple[str, ...]:
    """Element names, in vector order. Fixed for a given summary version."""
    names: list[str] = list(_GLOBAL_NAMES)
    names += [f"angle_{a}_{s}" for a in ANGLE_IDS for s in _ANGLE_STATS]
    names += [
        f"bilateral_angle_{group}_{s}"
        for group, _, _ in BILATERAL_ANGLE_GROUPS
        for s in _BILATERAL_ANGLE_STATS
    ]
    names += [
        f"bilateral_{role}_{s}" for role, _, _ in BILATERAL_ROLE_PAIRS for s in _PAIR_STATS
    ]
    names += [f"distance_{d}_{s}" for d in DISTANCE_IDS for s in _DISTANCE_STATS]
    names += [f"ratio_{r}_{s}" for r in RATIO_IDS for s in _RATIO_STATS]
    names += [f"joint_{role}_{s}" for role in ALL_ROLES for s in _ROLE_STATS]
    return tuple(names)


SUMMARY_LENGTH: int = len(summary_names())


def _finite(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64).ravel()
    return array[np.isfinite(array)]


def _mean(values: np.ndarray) -> float:
    finite = _finite(values)
    return float(finite.mean()) if finite.size else float("nan")


def _max(values: np.ndarray) -> float:
    finite = _finite(values)
    return float(finite.max()) if finite.size else float("nan")


def _rms(values: np.ndarray) -> float:
    finite = _finite(values)
    return float(np.sqrt((finite**2).mean())) if finite.size else float("nan")


def _distribution(values: np.ndarray) -> tuple[float, ...]:
    """``min, max, range, mean, std, median, iqr`` - NaN when nothing is finite."""
    finite = _finite(values)
    if finite.size == 0:
        return (float("nan"),) * 7
    low, high = float(finite.min()), float(finite.max())
    q25, q75 = np.percentile(finite, [25.0, 75.0])
    return (
        low,
        high,
        high - low,
        float(finite.mean()),
        float(finite.std()),
        float(np.median(finite)),
        float(q75 - q25),
    )


def _measured_fps(context: "FeatureContext") -> float:
    """Frames per second actually observed, from the camera timestamps."""
    stamps = seconds(context.timestamps_ns)
    finite = stamps[np.isfinite(stamps)]
    if finite.size < 2:
        return float("nan")
    span = float(finite[-1] - finite[0])
    return (finite.size - 1) / span if span > 0 else float("nan")


def summary_vector(context: "FeatureContext") -> np.ndarray:
    """``float32 [F]`` in :func:`summary_names` order."""
    from kinecapture.features.compute import BILATERAL_ANGLE_IDS  # noqa: F401

    values: list[float] = []
    joints = context.joints
    stamps = seconds(context.timestamps_ns)
    finite_stamps = stamps[np.isfinite(stamps)]
    duration = (
        float(finite_stamps[-1] - finite_stamps[0]) if finite_stamps.size >= 2 else float("nan")
    )
    angles, angle_mask = context.angles
    angular_velocity, angular_mask = context.angular_velocity
    distances, _distance_mask = context.distances
    speed = context.speed.copy()
    speed[~context.velocity[1]] = np.nan
    vertical_axis = int(np.argmax(np.abs(_vertical(context))))

    # ---- global ---------------------------------------------------------
    root = context.roles.get("pelvis")
    if root is None:
        root = context.spec.root_index
    root_trajectory = joints[:, root, :]
    root_speed = speed[:, root]
    values += [
        duration,
        float(context.frames),
        _measured_fps(context),
        float(context.frame_valid.mean()) if context.frames else float("nan"),
        float(context.joint_valid.mean()) if context.frames else float("nan"),
        _mean(context.confidences) if context.confidences is not None else float("nan"),
        context.body_scale,
        path_length(root_trajectory, context.joint_valid[:, root]),
        _mean(root_speed),
        _max(root_speed),
    ]

    # ---- angles ---------------------------------------------------------
    for column in range(len(ANGLE_IDS)):
        series = np.where(angle_mask[:, column], angles[:, column], np.nan)
        rates = np.where(angular_mask[:, column], angular_velocity[:, column], np.nan)
        values += list(_distribution(series))
        values += [_rms(rates), _max(np.abs(rates))]

    # ---- bilateral angle groups ----------------------------------------
    for _group, left, right in BILATERAL_ANGLE_GROUPS:
        pair_valid = angle_mask[:, left] & angle_mask[:, right]
        difference = np.where(pair_valid, angles[:, left] - angles[:, right], np.nan)
        values += [_mean(np.abs(difference)), _max(np.abs(difference)), _mean(difference)]

    # ---- bilateral joint pairs -----------------------------------------
    body_space = context.body_space
    mirror = np.asarray([-1.0, 1.0, 1.0])
    for _role, left_role, right_role in BILATERAL_ROLE_PAIRS:
        left = context.roles.get(left_role)
        right = context.roles.get(right_role)
        if left is None or right is None:
            values += [float("nan"), float("nan")]
            continue
        values.append(_mean(np.abs(speed[:, left] - speed[:, right])))
        with np.errstate(invalid="ignore"):
            distance = np.linalg.norm(
                body_space[:, left, :] - body_space[:, right, :] * mirror, axis=-1
            )
        values.append(_mean(distance))

    # ---- distances and ratios ------------------------------------------
    for column in range(len(DISTANCE_IDS)):
        series = distances[:, column]
        finite = _finite(series)
        if finite.size == 0:
            values += [float("nan")] * 4
        else:
            values += [
                float(finite.mean()),
                float(finite.std()),
                float(finite.min()),
                float(finite.max()),
            ]
    ratios = _ratios(distances)
    for column in range(len(RATIO_IDS)):
        finite = _finite(ratios[:, column])
        values += (
            [float(finite.mean()), float(finite.std())]
            if finite.size
            else [float("nan"), float("nan")]
        )

    # ---- per-role joint motion -----------------------------------------
    for role in ALL_ROLES:
        index = context.roles.get(role)
        if index is None:
            values += [float("nan")] * 4
            continue
        series = speed[:, index]
        values += [
            _mean(series),
            _max(series),
            path_length(joints[:, index, :], context.joint_valid[:, index]),
        ]
        vertical = joints[:, index, vertical_axis]
        finite = _finite(vertical)
        values.append(float(finite.max() - finite.min()) if finite.size else float("nan"))

    vector = np.asarray(values, dtype=np.float32)
    if vector.size != SUMMARY_LENGTH:  # pragma: no cover - guarded by a test
        raise AssertionError(
            f"summary vector length {vector.size} != contract {SUMMARY_LENGTH}"
        )
    return vector


def _vertical(context: "FeatureContext") -> np.ndarray:
    from kinecapture.features.roles import vertical_axis_vector

    return np.asarray(vertical_axis_vector(context.spec), dtype=np.float64)


def _ratios(distances: np.ndarray) -> np.ndarray:
    from kinecapture.features.definitions import RATIO_DEFINITIONS
    from kinecapture.features.geometry import EPSILON

    result = np.full((distances.shape[0], len(RATIO_DEFINITIONS)), np.nan, dtype=np.float64)
    for column, definition in enumerate(RATIO_DEFINITIONS):
        numerator = distances[:, DISTANCE_IDS.index(definition.numerator)]
        denominator = distances[:, DISTANCE_IDS.index(definition.denominator)]
        with np.errstate(invalid="ignore", divide="ignore"):
            result[:, column] = np.where(
                np.abs(denominator) > EPSILON, numerator / denominator, np.nan
            )
    return result


def summary_contract() -> dict[str, object]:
    """The block written into ``feature_spec.json``."""
    return {
        "version": SUMMARY_VERSION,
        "length": SUMMARY_LENGTH,
        "dtype": "float32",
        "names": list(summary_names()),
        "leakage_policy": (
            "Hiçbir eleman etikete, katılımcı kimliğine veya dataset genelinde "
            "hesaplanan bir istatistiğe bakmaz. Template mesafesi, sınıf "
            "ortalaması ve dataset scaler'ı bilinçli olarak yoktur; bunlar "
            "eğitim katmanına aittir."
        ),
        "missing_value_policy": (
            "Hesaplanamayan eleman NaN kalır; vektör uzunluğu örnekten örneğe "
            "değişmez."
        ),
        "units": (
            "Açı elemanları radyan, açısal hız rad/s, mesafe ve yol uzunluğu "
            "capture length_unit, hız length_unit/s, oranlar birimsizdir."
        ),
    }


__all__ = [
    "SUMMARY_LENGTH",
    "SUMMARY_VERSION",
    "summary_contract",
    "summary_names",
    "summary_vector",
]
