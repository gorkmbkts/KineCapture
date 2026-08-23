"""Versioned joint-mapping adapters between skeleton formats.

Why this is a separate, explicit module
---------------------------------------
MEMORY.md section 3 and PROMPT section 20 both say the same thing: the ZED
native body format must not be assumed to equal KineSynthV3's 26-joint layout,
and where a correspondence is unclear a joint must **not** be invented.

So a mapping here is a first-class, versioned object that states exactly which
target joints it can fill and which it cannot. A mapping with unmapped joints
reports :attr:`JointMapping.status` as ``"partial"``; the export screen shows
that status verbatim and the release manifest records the unmapped joint names.
Unmapped joints are written as NaN, never as a plausible-looking interpolation.

Adding a new mapping means adding a table here and bumping its ``version`` -
never editing an existing one in place, because a released dataset references
the mapping by ``mapping_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from kinecapture.core.errors import ValidationError
from kinecapture.visualization.skeleton_spec import (
    REHAB24_6_MOCAP,
    SkeletonSpec,
    ZED_BODY_34,
    get_skeleton_spec,
)


@dataclass(frozen=True)
class JointMapping:
    """A source-to-target joint correspondence.

    ``pairs`` maps a *target* joint name to a *source* joint name. Target joints
    absent from ``pairs`` are unmapped and become NaN.
    """

    mapping_id: str
    version: str
    source_format: str
    target_format: str
    pairs: Mapping[str, str]
    rationale: str = ""
    unmapped_reason: Mapping[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "unmapped_reason", dict(self.unmapped_reason or {}))
        source = get_skeleton_spec(self.source_format)
        target = get_skeleton_spec(self.target_format)
        for target_joint, source_joint in self.pairs.items():
            if target.find(target_joint) is None:
                raise ValueError(
                    f"{self.mapping_id}: '{target_joint}' is not a "
                    f"{self.target_format} joint"
                )
            if source.find(source_joint) is None:
                raise ValueError(
                    f"{self.mapping_id}: '{source_joint}' is not a "
                    f"{self.source_format} joint"
                )

    @property
    def source_spec(self) -> SkeletonSpec:
        return get_skeleton_spec(self.source_format)

    @property
    def target_spec(self) -> SkeletonSpec:
        return get_skeleton_spec(self.target_format)

    @property
    def unmapped_target_joints(self) -> tuple[str, ...]:
        """Target joints this mapping cannot fill, in target order."""
        return tuple(
            name for name in self.target_spec.joint_names if name not in self.pairs
        )

    @property
    def mapped_count(self) -> int:
        return len(self.pairs)

    @property
    def status(self) -> str:
        """``"complete"`` when every target joint is covered, else ``"partial"``."""
        return "complete" if not self.unmapped_target_joints else "partial"

    @property
    def coverage(self) -> float:
        return self.mapped_count / self.target_spec.num_joints

    def index_vector(self) -> np.ndarray:
        """``int32 [target_J]`` of source indices, ``-1`` where unmapped."""
        source, target = self.source_spec, self.target_spec
        indices = np.full(target.num_joints, -1, dtype=np.int32)
        for target_joint, source_joint in self.pairs.items():
            indices[target.index_of(target_joint)] = source.index_of(source_joint)
        return indices

    def apply(self, joints: np.ndarray) -> np.ndarray:
        """Remap ``[T, source_J, 3]`` (or ``[source_J, 3]``) onto the target order.

        Unmapped target joints become NaN. The values that *are* mapped are
        copied verbatim: no centring, no scaling, no interpolation.
        """
        array = np.asarray(joints, dtype=np.float32)
        squeeze = array.ndim == 2
        if squeeze:
            array = array[None, ...]
        if array.ndim != 3 or array.shape[2] != 3:
            raise ValidationError(
                f"Eklem dizisi [T, J, 3] olmalı, gelen: {array.shape}",
                field="joints",
                code="mapping_input_shape",
            )
        source_joints = self.source_spec.num_joints
        if array.shape[1] != source_joints:
            raise ValidationError(
                f"'{self.source_format}' {source_joints} eklem bekler, "
                f"gelen: {array.shape[1]}",
                field="joints",
                code="mapping_joint_count_mismatch",
            )
        indices = self.index_vector()
        frames = array.shape[0]
        result = np.full((frames, indices.size, 3), np.nan, dtype=np.float32)
        mapped = indices >= 0
        result[:, mapped, :] = array[:, indices[mapped], :]
        return result[0] if squeeze else result

    def apply_per_joint(self, values: np.ndarray) -> np.ndarray:
        """Remap any ``[T, source_J, ...]`` per-joint array onto the target order.

        This is a pure index permutation, so it is only correct for quantities
        whose meaning belongs to the *joint* rather than to the source
        skeleton's parent chain. Positions, image points and per-joint position
        covariances qualify; parent-relative positions and local joint
        quaternions do not, and the exporter refuses to send those through
        here. Unmapped target joints become NaN.
        """
        array = np.asarray(values, dtype=np.float32)
        if array.ndim < 2:
            raise ValidationError(
                f"Eklem dizisi en az [T, J] olmalı, gelen: {array.shape}",
                field="values",
                code="mapping_input_shape",
            )
        source_joints = self.source_spec.num_joints
        if array.shape[1] != source_joints:
            raise ValidationError(
                f"'{self.source_format}' {source_joints} eklem bekler, "
                f"gelen: {array.shape[1]}",
                field="values",
                code="mapping_joint_count_mismatch",
            )
        indices = self.index_vector()
        shape = (array.shape[0], indices.size, *array.shape[2:])
        result = np.full(shape, np.nan, dtype=np.float32)
        mapped = indices >= 0
        result[:, mapped, ...] = array[:, indices[mapped], ...]
        return result

    def apply_confidence(self, confidences: np.ndarray) -> np.ndarray:
        """Remap ``[T, source_J]`` confidences; unmapped joints become NaN."""
        array = np.asarray(confidences, dtype=np.float32)
        squeeze = array.ndim == 1
        if squeeze:
            array = array[None, :]
        indices = self.index_vector()
        result = np.full((array.shape[0], indices.size), np.nan, dtype=np.float32)
        mapped = indices >= 0
        result[:, mapped] = array[:, indices[mapped]]
        return result[0] if squeeze else result

    def to_dict(self) -> dict[str, Any]:
        """The block written into a dataset release manifest."""
        return {
            "mapping_id": self.mapping_id,
            "version": self.version,
            "source_format": self.source_format,
            "target_format": self.target_format,
            "status": self.status,
            "coverage": round(self.coverage, 4),
            "mapped_joints": self.mapped_count,
            "target_joints": self.target_spec.num_joints,
            "pairs": dict(sorted(self.pairs.items())),
            "unmapped_target_joints": list(self.unmapped_target_joints),
            "unmapped_reason": dict(self.unmapped_reason),
            "rationale": self.rationale,
            "unmapped_fill_value": "nan",
        }


#: ZED BODY_34 -> KineSynthV3 REHAB24-6 (26 joints).
#:
#: 23 of 26 target joints have a direct, unambiguous ZED counterpart. Three do
#: not, and are left unmapped rather than approximated:
#:
#: * ``Head_end`` - a mocap skull-tip marker. ZED's ``head`` is a head *centre*
#:   and ``nose`` is a face landmark; neither is the same point.
#: * ``LeftToeBase_end`` / ``RightToeBase_end`` - mocap toe-tip markers. ZED's
#:   ``left_foot`` / ``right_foot`` already correspond to ``*ToeBase``, and it
#:   has no further distal toe joint.
ZED34_TO_REHAB24_V0 = JointMapping(
    mapping_id="zed_body_34__to__rehab24_6_mocap",
    version="0.1.0-partial",
    source_format=ZED_BODY_34.name,
    target_format=REHAB24_6_MOCAP.name,
    pairs={
        "Hips": "pelvis",
        "Spine": "naval_spine",
        "Spine1": "chest_spine",
        "Neck": "neck",
        "Head": "head",
        "LeftShoulder": "left_clavicle",
        "LeftArm": "left_shoulder",
        "LeftForeArm": "left_elbow",
        "LeftHand": "left_wrist",
        "LeftHand_end": "left_handtip",
        "RightShoulder": "right_clavicle",
        "RightArm": "right_shoulder",
        "RightForeArm": "right_elbow",
        "RightHand": "right_wrist",
        "RightHand_end": "right_handtip",
        "LeftUpLeg": "left_hip",
        "LeftLeg": "left_knee",
        "LeftFoot": "left_ankle",
        "LeftToeBase": "left_foot",
        "RightUpLeg": "right_hip",
        "RightLeg": "right_knee",
        "RightFoot": "right_ankle",
        "RightToeBase": "right_foot",
    },
    unmapped_reason={
        "Head_end": (
            "Mocap kafa ucu işaretçisi. ZED 'head' bir kafa merkezi, 'nose' bir "
            "yüz noktasıdır; ikisi de aynı fiziksel nokta değildir."
        ),
        "LeftToeBase_end": (
            "Mocap ayak parmağı ucu işaretçisi. ZED'in en distal ayak eklemi "
            "'left_foot' zaten LeftToeBase'e karşılık gelir."
        ),
        "RightToeBase_end": (
            "Mocap ayak parmağı ucu işaretçisi. ZED'in en distal ayak eklemi "
            "'right_foot' zaten RightToeBase'e karşılık gelir."
        ),
    },
    rationale=(
        "Eşleştirme, yerel ZED SDK 5.4'ten okunan BODY_34 eklem sırası ile "
        "KineSynthV3 rehab24_6_mocap skeleton_spec.json karşılaştırılarak "
        "kuruldu. Anatomik karşılığı belirsiz olan eklemler doldurulmadı."
    ),
)


_MAPPINGS: dict[str, JointMapping] = {
    ZED34_TO_REHAB24_V0.mapping_id: ZED34_TO_REHAB24_V0,
}


def get_mapping(mapping_id: str) -> JointMapping:
    try:
        return _MAPPINGS[mapping_id]
    except KeyError:
        known = ", ".join(sorted(_MAPPINGS)) or "(yok)"
        raise KeyError(
            f"Bilinmeyen eklem eşleştirmesi '{mapping_id}'. Kayıtlı: {known}."
        ) from None


def find_mapping(source_format: str, target_format: str) -> Optional[JointMapping]:
    """Return the mapping between two formats, or ``None`` when none exists."""
    for mapping in _MAPPINGS.values():
        if (
            mapping.source_format == source_format
            and mapping.target_format == target_format
        ):
            return mapping
    return None


def available_mappings() -> Sequence[JointMapping]:
    return tuple(_MAPPINGS[key] for key in sorted(_MAPPINGS))


__all__ = [
    "JointMapping",
    "ZED34_TO_REHAB24_V0",
    "available_mappings",
    "find_mapping",
    "get_mapping",
]
