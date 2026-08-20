"""Skeleton topology definitions.

The GUI never hard-codes a joint count. Every renderer, writer and exporter
takes a :class:`SkeletonSpec`, so switching body formats is a data change rather
than a widget rewrite.

Provenance of the ZED definitions
---------------------------------
The ``zed_body_18`` / ``zed_body_34`` / ``zed_body_38`` joint orders and bone
lists below were **read from the ZED SDK installed on this machine**
(``pyzed`` 5.4, SDK 5.4.1) by enumerating ``sl.BODY_*_PARTS`` in value order and
``sl.BODY_*_BONES``. They are not reproduced from memory or documentation. If
the SDK is upgraded, re-run ``scripts/diagnose.ps1``, which compares the live
SDK enumeration against these tables and reports any drift instead of silently
writing mislabelled joints.

``rehab24_6_mocap`` is the 26-joint layout used by the existing KineSynthV3
dataset. It is included as a *target* definition for the export adapter, not
because ZED produces it - see :mod:`kinecapture.visualization.mapping`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

#: Joints whose name starts with these prefixes are drawn in the side colours.
_LEFT_PREFIXES = ("left_", "l_")
_RIGHT_PREFIXES = ("right_", "r_")


@dataclass(frozen=True)
class SkeletonSpec:
    """Joint names, drawing topology and the source coordinate convention."""

    name: str
    joint_names: tuple[str, ...]
    edges: tuple[tuple[int, int], ...]
    root_index: int = 0
    vertical_axis: str = "y"
    length_unit: str = "meter"
    coordinate_system: str = "right_handed_y_up"
    source: str = "unspecified"

    def __post_init__(self) -> None:
        count = len(self.joint_names)
        if count == 0:
            raise ValueError("SkeletonSpec needs at least one joint")
        if len(set(self.joint_names)) != count:
            raise ValueError(f"{self.name}: joint names must be unique")
        if not 0 <= self.root_index < count:
            raise ValueError(
                f"{self.name}: root_index {self.root_index} out of range for {count} joints"
            )
        for a, b in self.edges:
            if not (0 <= a < count and 0 <= b < count):
                raise ValueError(
                    f"{self.name}: edge ({a}, {b}) out of range for {count} joints"
                )

    @property
    def num_joints(self) -> int:
        return len(self.joint_names)

    def index_of(self, joint_name: str) -> int:
        return self.joint_names.index(joint_name)

    def find(self, joint_name: str) -> Optional[int]:
        try:
            return self.joint_names.index(joint_name)
        except ValueError:
            return None

    def side_of(self, index: int) -> str:
        """``"left"``, ``"right"`` or ``"center"`` - used only for drawing."""
        name = self.joint_names[index]
        if name.startswith(_LEFT_PREFIXES):
            return "left"
        if name.startswith(_RIGHT_PREFIXES):
            return "right"
        return "center"

    def to_dict(self) -> dict[str, Any]:
        """The exact block written into a dataset release."""
        return {
            "identifier": self.name,
            "num_joints": self.num_joints,
            "joints": list(self.joint_names),
            "edges": [list(edge) for edge in self.edges],
            "root_joint": self.root_index,
            "vertical_axis": self.vertical_axis,
            "length_unit": self.length_unit,
            "coordinate_system": self.coordinate_system,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkeletonSpec":
        return cls(
            name=str(payload["identifier"]),
            joint_names=tuple(payload["joints"]),
            edges=tuple((int(a), int(b)) for a, b in payload.get("edges") or ()),
            root_index=int(payload.get("root_joint", 0)),
            vertical_axis=str(payload.get("vertical_axis", "y")),
            length_unit=str(payload.get("length_unit", "meter")),
            coordinate_system=str(
                payload.get("coordinate_system", "right_handed_y_up")
            ),
            source=str(payload.get("source", "unspecified")),
        )


# ---------------------------------------------------------------------------
# ZED native body formats - read from the locally installed SDK
# ---------------------------------------------------------------------------

_ZED_SOURCE = "stereolabs_zed_sdk_5.4 (enumerated from local pyzed install)"

ZED_BODY_18 = SkeletonSpec(
    name="zed_body_18",
    joint_names=(
        "nose", "neck",
        "right_shoulder", "right_elbow", "right_wrist",
        "left_shoulder", "left_elbow", "left_wrist",
        "right_hip", "right_knee", "right_ankle",
        "left_hip", "left_knee", "left_ankle",
        "right_eye", "left_eye", "right_ear", "left_ear",
    ),
    edges=(
        (0, 1), (1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (6, 7), (2, 8),
        (8, 9), (9, 10), (5, 11), (11, 12), (12, 13), (2, 5), (8, 11),
        (0, 14), (14, 16), (0, 15), (15, 17),
    ),
    root_index=1,
    source=_ZED_SOURCE,
)

ZED_BODY_34 = SkeletonSpec(
    name="zed_body_34",
    joint_names=(
        "pelvis", "naval_spine", "chest_spine", "neck",
        "left_clavicle", "left_shoulder", "left_elbow", "left_wrist",
        "left_hand", "left_handtip", "left_thumb",
        "right_clavicle", "right_shoulder", "right_elbow", "right_wrist",
        "right_hand", "right_handtip", "right_thumb",
        "left_hip", "left_knee", "left_ankle", "left_foot",
        "right_hip", "right_knee", "right_ankle", "right_foot",
        "head", "nose",
        "left_eye", "left_ear", "right_eye", "right_ear",
        "left_heel", "right_heel",
    ),
    edges=(
        (0, 1), (1, 2), (2, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9),
        (7, 10), (2, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16),
        (14, 17), (0, 18), (18, 19), (19, 20), (20, 21), (0, 22), (22, 23),
        (23, 24), (24, 25), (2, 3), (3, 26), (26, 27), (27, 28), (28, 29),
        (27, 30), (30, 31), (20, 32), (24, 33), (32, 21), (33, 25),
    ),
    root_index=0,
    source=_ZED_SOURCE,
)

ZED_BODY_38 = SkeletonSpec(
    name="zed_body_38",
    joint_names=(
        "pelvis", "spine_1", "spine_2", "spine_3", "neck", "nose",
        "left_eye", "right_eye", "left_ear", "right_ear",
        "left_clavicle", "right_clavicle",
        "left_shoulder", "right_shoulder",
        "left_elbow", "right_elbow",
        "left_wrist", "right_wrist",
        "left_hip", "right_hip",
        "left_knee", "right_knee",
        "left_ankle", "right_ankle",
        "left_big_toe", "right_big_toe",
        "left_small_toe", "right_small_toe",
        "left_heel", "right_heel",
        "left_hand_thumb_4", "right_hand_thumb_4",
        "left_hand_index_1", "right_hand_index_1",
        "left_hand_middle_4", "right_hand_middle_4",
        "left_hand_pinky_1", "right_hand_pinky_1",
    ),
    edges=(
        (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 8), (5, 7),
        (7, 9), (3, 10), (10, 12), (12, 14), (14, 16), (16, 30), (16, 32),
        (16, 34), (16, 36), (3, 11), (11, 13), (13, 15), (15, 17), (17, 31),
        (17, 33), (17, 35), (17, 37), (0, 18), (18, 20), (20, 22), (22, 28),
        (22, 24), (22, 26), (0, 19), (19, 21), (21, 23), (23, 29), (23, 25),
        (23, 27),
    ),
    root_index=0,
    source=_ZED_SOURCE,
)

#: Maps the SDK's ``BODY_FORMAT`` member name onto our specification.
ZED_BODY_FORMAT_SPECS: Mapping[str, SkeletonSpec] = {
    "BODY_18": ZED_BODY_18,
    "BODY_34": ZED_BODY_34,
    "BODY_38": ZED_BODY_38,
}


# ---------------------------------------------------------------------------
# Mock skeleton
# ---------------------------------------------------------------------------

#: Minimal humanoid used by the synthetic backend and by the tests. Its joint
#: names intentionally mirror a subset of the ZED BODY_34 vocabulary so the same
#: rendering and quality code paths exercise both.
MOCK_SKELETON = SkeletonSpec(
    name="mock_16",
    joint_names=(
        "pelvis", "chest_spine", "neck", "head",
        "left_shoulder", "left_elbow", "left_wrist",
        "right_shoulder", "right_elbow", "right_wrist",
        "left_hip", "left_knee", "left_ankle",
        "right_hip", "right_knee", "right_ankle",
    ),
    edges=(
        (0, 1), (1, 2), (2, 3), (2, 4), (4, 5), (5, 6), (2, 7), (7, 8),
        (8, 9), (0, 10), (10, 11), (11, 12), (0, 13), (13, 14), (14, 15),
    ),
    root_index=0,
    source="synthetic",
)


# ---------------------------------------------------------------------------
# KineSynthV3 target layout
# ---------------------------------------------------------------------------

#: The 26-joint mocap layout of the existing REHAB24-6 dataset, read from
#: ``KineSynthV3/colab/dataset/processed/kinesynth_rehab24_v1/skeleton_spec.json``.
#: Present as an export *target*; ZED does not produce this layout natively.
REHAB24_6_MOCAP = SkeletonSpec(
    name="rehab24_6_mocap",
    joint_names=(
        "Hips", "Spine", "Spine1", "Neck", "Head", "Head_end",
        "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "LeftHand_end",
        "RightShoulder", "RightArm", "RightForeArm", "RightHand", "RightHand_end",
        "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase", "LeftToeBase_end",
        "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase", "RightToeBase_end",
    ),
    edges=(
        (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (3, 6), (6, 7), (7, 8),
        (8, 9), (9, 10), (3, 11), (11, 12), (12, 13), (13, 14), (14, 15),
        (0, 16), (16, 17), (17, 18), (18, 19), (19, 20), (0, 21), (21, 22),
        (22, 23), (23, 24), (24, 25),
    ),
    root_index=0,
    source="kinesynthv3_rehab24_6",
)


_REGISTRY: dict[str, SkeletonSpec] = {
    spec.name: spec
    for spec in (
        MOCK_SKELETON,
        ZED_BODY_18,
        ZED_BODY_34,
        ZED_BODY_38,
        REHAB24_6_MOCAP,
    )
}


def get_skeleton_spec(name: str) -> SkeletonSpec:
    """Look up a registered specification by ``body_format`` name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            f"Bilinmeyen iskelet biçimi '{name}'. Kayıtlı biçimler: {known}."
        ) from None


def try_get_skeleton_spec(name: str) -> Optional[SkeletonSpec]:
    """Lookup that returns ``None`` instead of raising, for display code."""
    return _REGISTRY.get(name)


def available_skeleton_specs() -> Sequence[str]:
    return tuple(sorted(_REGISTRY))


def spec_for_zed_body_format(body_format_name: str) -> SkeletonSpec:
    """Translate an SDK ``BODY_FORMAT`` member name into a specification."""
    try:
        return ZED_BODY_FORMAT_SPECS[body_format_name]
    except KeyError:
        known = ", ".join(sorted(ZED_BODY_FORMAT_SPECS))
        raise KeyError(
            f"Desteklenmeyen ZED body formatı '{body_format_name}'. "
            f"Desteklenenler: {known}."
        ) from None


__all__ = [
    "MOCK_SKELETON",
    "REHAB24_6_MOCAP",
    "SkeletonSpec",
    "ZED_BODY_18",
    "ZED_BODY_34",
    "ZED_BODY_38",
    "ZED_BODY_FORMAT_SPECS",
    "available_skeleton_specs",
    "get_skeleton_spec",
    "spec_for_zed_body_format",
    "try_get_skeleton_spec",
]
