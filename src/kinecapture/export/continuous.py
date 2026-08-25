"""The continuous-activity dataset: a whole take as one example.

The movement-sample release answers "was this repetition correct?". It is
built by cutting the repetitions out of a recording and throwing the rest away
- which means a model trained on it has literally never seen a person standing
still, walking over, or tying a shoelace. Such a model cannot decide *when*
somebody started exercising, because nothing in its training data was ever "not
exercising".

This module is the other half. One example is one take, at its real length,
with a label for every frame:

* what the person was doing (``activity_state_code``),
* whether anybody had labelled that frame at all (``activity_label_mask``),
* whether the person being recorded was even visible
  (``subject_present_mask``),
* where an exercise starts and ends (``exercise_start_target`` /
  ``exercise_end_target``).

Three distinctions this contract refuses to blur
------------------------------------------------
**Unlabelled is not background.** A frame nobody looked at carries the sentinel
``-1`` and a ``False`` label mask. Treating it as "not exercising" would train
a model on the annotator's attention span.

**Absent is not still.** ``subject_present_mask`` is ``False`` when the person
was not found. That is not the same as a person standing motionless, and the
coordinates are NaN rather than a stranger's.

**No error label is not "no error".** ``error_label_mask`` marks the frames
where an error annotation could even apply - inside a labelled target-exercise
sample. Outside it, the absence of an error means nothing.

Nothing here resamples, pads or interpolates. The array is exactly as long as
the recording was; making every example the same length is the training
loader's decision, not the archive's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from kinecapture.domain.activity import (
    ACTIVITY_STATE_ORDER,
    ActivityInterval,
    ActivityState,
    UNLABELLED_CODE,
    activity_label_mapping,
    measure_coverage,
)
from kinecapture.domain.enums import Correctness
from kinecapture.domain.project import MovementSample

#: Bumped when any array below changes shape, dtype or meaning.
CONTINUOUS_CONTRACT_VERSION = "1.0.0"

#: Sentinel for "this frame has no exercise class". Never a valid index.
NO_CLASS = -1
#: ``correctness_code`` values. ``-1`` means the question does not apply here.
CORRECTNESS_CODES: dict[str, int] = {
    Correctness.CORRECT.value: 0,
    Correctness.INCORRECT.value: 1,
}
CORRECTNESS_NOT_APPLICABLE = -1


@dataclass
class ContinuousTargets:
    """The frame-level label arrays of one continuous example."""

    activity_state_code: np.ndarray
    activity_label_mask: np.ndarray
    exercise_active: np.ndarray
    exercise_class_index: np.ndarray
    exercise_class_valid_mask: np.ndarray
    exercise_start_target: np.ndarray
    exercise_end_target: np.ndarray
    correctness_code: np.ndarray
    error_label_mask: np.ndarray
    error_multi_hot: Optional[np.ndarray] = None
    intervals: list[dict[str, Any]] = field(default_factory=list)

    def arrays(self) -> dict[str, np.ndarray]:
        payload = {
            "activity_state_code": self.activity_state_code,
            "activity_label_mask": self.activity_label_mask,
            "exercise_active": self.exercise_active,
            "exercise_class_index": self.exercise_class_index,
            "exercise_class_valid_mask": self.exercise_class_valid_mask,
            "exercise_start_target": self.exercise_start_target,
            "exercise_end_target": self.exercise_end_target,
            "correctness_code": self.correctness_code,
            "error_label_mask": self.error_label_mask,
        }
        if self.error_multi_hot is not None:
            payload["error_multi_hot"] = self.error_multi_hot
        return payload


def build_targets(
    *,
    frames: int,
    intervals: Sequence[ActivityInterval],
    samples: Sequence[MovementSample],
    exercise_index: Mapping[str, int],
    error_index: Mapping[str, int],
    store_error_arrays: bool = True,
) -> ContinuousTargets:
    """Turn a take's annotations into per-frame targets.

    ``intervals`` bounds are inclusive stream positions, so an exercise that
    occupies positions 10..19 sets ``exercise_start_target[10]`` and
    ``exercise_end_target[19]``. A one-frame exercise sets both on the same
    frame, which is why the two are separate arrays rather than a single
    transition channel.
    """
    length = max(0, int(frames))
    state_code = np.full(length, UNLABELLED_CODE, dtype=np.int16)
    label_mask = np.zeros(length, dtype=bool)
    exercise_active = np.zeros(length, dtype=bool)
    class_index = np.full(length, NO_CLASS, dtype=np.int32)
    class_valid = np.zeros(length, dtype=bool)
    start_target = np.zeros(length, dtype=np.uint8)
    end_target = np.zeros(length, dtype=np.uint8)
    correctness = np.full(length, CORRECTNESS_NOT_APPLICABLE, dtype=np.int8)
    error_mask = np.zeros(length, dtype=bool)

    records: list[dict[str, Any]] = []
    for interval in sorted(intervals, key=lambda i: (i.start_frame, i.end_frame)):
        if not interval.is_well_formed or length == 0:
            continue
        low = max(0, interval.start_frame)
        high = min(interval.end_frame, length - 1)
        if high < low:
            continue
        state_code[low : high + 1] = interval.state.code
        label_mask[low : high + 1] = True
        record: dict[str, Any] = {
            "interval_id": interval.interval_id,
            "state": interval.state.value,
            "state_code": interval.state.code,
            "start_position": low,
            "end_position": high,
            "num_frames": high - low + 1,
            "source": interval.source.value,
        }
        if interval.state is ActivityState.TARGET_EXERCISE:
            exercise_active[low : high + 1] = True
            start_target[low] = 1
            end_target[high] = 1
            record["exercise"] = interval.exercise
            record["linked_sample_id"] = interval.linked_sample_id
            index = exercise_index.get(interval.exercise)
            if index is not None:
                class_index[low : high + 1] = int(index)
                class_valid[low : high + 1] = True
                record["exercise_class_index"] = int(index)
            else:
                # An exercise code the project schema does not know cannot be
                # given an index; the span stays active but unclassified.
                record["exercise_class_index"] = None
                record["warning"] = "exercise_not_in_schema"
        if interval.note:
            record["note"] = interval.note
        records.append(record)

    # --- error and correctness, only where they can mean anything --------
    classes = len(error_index)
    multi_hot = (
        np.zeros((length, classes), dtype=np.uint8)
        if store_error_arrays and classes
        else None
    )
    for sample in samples:
        if not sample.is_active or not sample.correctness.is_decided:
            continue
        low = max(0, sample.start_frame)
        high = min(sample.end_frame, length - 1)
        if high < low:
            continue
        # An error annotation is only meaningful inside a movement somebody
        # actually judged. Everywhere else the mask stays False, so "no error"
        # and "not asked" stay distinguishable.
        error_mask[low : high + 1] = True
        correctness[low : high + 1] = CORRECTNESS_CODES.get(
            sample.correctness.value, CORRECTNESS_NOT_APPLICABLE
        )
        if multi_hot is None:
            continue
        for interval in sample.sorted_intervals():
            column = error_index.get(interval.error_code)
            if column is None or not interval.is_well_formed:
                continue
            first = max(low, interval.start_frame)
            last = min(high, interval.end_frame)
            if last >= first:
                multi_hot[first : last + 1, column] = 1

    return ContinuousTargets(
        activity_state_code=state_code,
        activity_label_mask=label_mask,
        exercise_active=exercise_active,
        exercise_class_index=class_index,
        exercise_class_valid_mask=class_valid,
        exercise_start_target=start_target,
        exercise_end_target=end_target,
        correctness_code=correctness,
        error_label_mask=error_mask,
        error_multi_hot=multi_hot,
        intervals=records,
    )


def array_contract(*, store_error_arrays: bool) -> dict[str, Any]:
    """The block a release writes so nothing about these arrays is guessed."""
    contract: dict[str, Any] = {
        "version": CONTINUOUS_CONTRACT_VERSION,
        "example": "Bir örnek = bir kaydın tamamı. T gerçek kayıt uzunluğudur.",
        "not_applied": (
            "Interpolation, padding, sabit uzunluğa resampling ve augmentation "
            "bu katmanda uygulanmaz."
        ),
        "arrays": {
            "joints_xyz": {
                "shape": "[T, J, 3]",
                "dtype": "float32",
                "unit": "length_unit",
                "description": (
                    "SEÇİLİ kişinin ham koordinatları. Kişi bulunamayan karede "
                    "NaN; başka bir gövdeyle doldurulmaz."
                ),
            },
            "frame_indices": {"shape": "[T]", "dtype": "int64",
                              "description": "Kameranın kendi kare numaraları."},
            "camera_timestamps_ns": {"shape": "[T]", "dtype": "int64",
                                     "description": "Kamera zaman damgaları."},
            "subject_present_mask": {
                "shape": "[T]", "dtype": "bool",
                "description": (
                    "Seçili kişinin o karede bulunup bulunmadığı. False, "
                    "'kişi hareketsiz' DEĞİL 'kişi yok' demektir."
                ),
            },
            "subject_source_tracking_id": {
                "shape": "[T]", "dtype": "int64",
                "description": (
                    f"O karede eşlenen SDK tracker kimliği; yoksa {NO_CLASS}."
                ),
            },
            "subject_association_confidence": {
                "shape": "[T]", "dtype": "float32",
                "description": (
                    "Eşleştirme güveni. Aynı tracker kimliği sürerken 1.0, "
                    "yeniden eşleştirmede skor, kişi yokken NaN."
                ),
            },
            "activity_state_code": {
                "shape": "[T]", "dtype": "int16",
                "description": (
                    "0=background, 1=transition, 2=target_exercise, "
                    f"3=other_activity, {UNLABELLED_CODE}=ETİKETLENMEMİŞ. "
                    "Etiketlenmemiş kare background DEĞİLDİR."
                ),
            },
            "activity_label_mask": {
                "shape": "[T]", "dtype": "bool",
                "description": "Aktivite etiketi bulunan kareler.",
            },
            "exercise_active": {
                "shape": "[T]", "dtype": "bool",
                "description": "Hedef egzersizin yapıldığı kareler.",
            },
            "exercise_class_index": {
                "shape": "[T]", "dtype": "int32",
                "description": (
                    f"label_mapping.exercise.code_to_index; yoksa {NO_CLASS}."
                ),
            },
            "exercise_class_valid_mask": {
                "shape": "[T]", "dtype": "bool",
                "description": "Egzersiz sınıfının bilindiği kareler.",
            },
            "exercise_start_target": {
                "shape": "[T]", "dtype": "uint8",
                "description": (
                    "Bir hedef egzersiz aralığının ilk karesinde 1. Tek karelik "
                    "egzersizde start ve end aynı karede 1 olabilir."
                ),
            },
            "exercise_end_target": {
                "shape": "[T]", "dtype": "uint8",
                "description": "Bir hedef egzersiz aralığının son karesinde 1.",
            },
            "correctness_code": {
                "shape": "[T]", "dtype": "int8",
                "description": (
                    "0=correct, 1=incorrect, "
                    f"{CORRECTNESS_NOT_APPLICABLE}=uygulanamaz. Yalnız karar "
                    "verilmiş hareket sample'ının sınırları içinde anlamlıdır."
                ),
            },
            "error_label_mask": {
                "shape": "[T]", "dtype": "bool",
                "description": (
                    "Hata etiketinin UYGULANABİLİR olduğu kareler. False olması "
                    "'hata yok' değil 'bu kareye hata etiketi sorulmadı' "
                    "demektir."
                ),
            },
        },
        "activity": activity_label_mapping(),
        "correctness_codes": dict(CORRECTNESS_CODES),
        "correctness_not_applicable": CORRECTNESS_NOT_APPLICABLE,
        "no_class_sentinel": NO_CLASS,
        "boundary_convention": (
            "Aralık sınırları derived/skeleton.jsonl kare listesindeki 0 tabanlı "
            "konumlardır ve her iki uç dahildir. Kamera kare numarası ayrı "
            "dizidir."
        ),
    }
    if store_error_arrays:
        contract["arrays"]["error_multi_hot"] = {
            "shape": "[T, C]",
            "dtype": "uint8",
            "description": (
                "Sütun sırası label_mapping.error_types.code_to_index. Yalnız "
                "error_label_mask True olan karelerde yorumlanmalıdır."
            ),
        }
    return contract


def summarise(
    *,
    intervals: Sequence[ActivityInterval],
    frames: int,
    fps: float,
    known_exercises: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    """Per-take numbers the dataset screen and the manifest both show."""
    coverage = measure_coverage(intervals, frames, known_exercises=known_exercises)
    per_state_seconds = {
        state.value: round(coverage.seconds(state, fps), 3)
        for state in ACTIVITY_STATE_ORDER
    }
    return {
        "frames": frames,
        "fps": round(float(fps), 3),
        "labelled_frames": coverage.labelled_frames,
        "unlabelled_frames": coverage.unlabelled_frames,
        "coverage_ratio": round(coverage.ratio, 4),
        "seconds_per_state": per_state_seconds,
        "unlabelled_seconds": round(
            coverage.unlabelled_frames / fps if fps > 0 else 0.0, 3
        ),
        "exercise_starts": coverage.exercise_starts,
        "exercise_ends": coverage.exercise_ends,
        "has_target_exercise": bool(
            coverage.per_state.get(ActivityState.TARGET_EXERCISE.value, 0)
        ),
    }


__all__ = [
    "CONTINUOUS_CONTRACT_VERSION",
    "CORRECTNESS_CODES",
    "CORRECTNESS_NOT_APPLICABLE",
    "ContinuousTargets",
    "NO_CLASS",
    "array_contract",
    "build_targets",
    "summarise",
]
