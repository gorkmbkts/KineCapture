"""Anatomical roles: the bridge between a feature and a skeleton format.

An angle definition must not say "joint 19". It says ``left_knee``, and this
module answers what index that is in ``zed_body_34``, in ``rehab24_6_mocap`` or
in the synthetic ``mock_16`` - or that the skeleton has no such joint, in which
case every feature depending on it stays NaN instead of borrowing a neighbour.

The tables below were written against the joint-name tuples in
:mod:`kinecapture.visualization.skeleton_spec`, which were themselves read from
the installed ZED SDK. Where a role has no honest counterpart it is simply
absent: ``zed_body_18`` has no pelvis and ``zed_body_38`` has no single head
joint, and neither gap is papered over.

Roles are also how bilateral pairs are defined, so left/right correspondence is
declared once rather than re-derived by string surgery in five places.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Roles without a side. Order is fixed: it drives column order downstream.
CENTRE_ROLES: tuple[str, ...] = (
    "pelvis",
    "spine_mid",
    "chest",
    "neck",
    "head",
    "nose",
)

#: Roles that exist once per side. Order is fixed for the same reason.
SIDED_ROLES: tuple[str, ...] = (
    "clavicle",
    "shoulder",
    "elbow",
    "wrist",
    "hand",
    "hip",
    "knee",
    "ankle",
    "foot",
    "heel",
)

SIDES: tuple[str, ...] = ("left", "right")


def _sided(role: str, side: str) -> str:
    return f"{side}_{role}"


#: Every role name, in a fixed order.
ALL_ROLES: tuple[str, ...] = CENTRE_ROLES + tuple(
    _sided(role, side) for role in SIDED_ROLES for side in SIDES
)

#: Left/right role pairs, in a fixed order.
BILATERAL_ROLE_PAIRS: tuple[tuple[str, str, str], ...] = tuple(
    (role, _sided(role, "left"), _sided(role, "right")) for role in SIDED_ROLES
)


def _mirror(prefixed: Mapping[str, str]) -> dict[str, str]:
    """Expand a ``left_*`` table into both sides by substituting the prefix."""
    table: dict[str, str] = {}
    for role, joint in prefixed.items():
        table[_sided(role, "left")] = joint
        table[_sided(role, "right")] = joint.replace("left", "right").replace(
            "Left", "Right"
        )
    return table


#: Role -> joint name, per registered skeleton. A role that a format genuinely
#: does not have is left out of its table.
_ROLE_TABLES: dict[str, dict[str, str]] = {
    "zed_body_34": {
        "pelvis": "pelvis",
        "spine_mid": "naval_spine",
        "chest": "chest_spine",
        "neck": "neck",
        "head": "head",
        "nose": "nose",
        **_mirror(
            {
                "clavicle": "left_clavicle",
                "shoulder": "left_shoulder",
                "elbow": "left_elbow",
                "wrist": "left_wrist",
                "hand": "left_hand",
                "hip": "left_hip",
                "knee": "left_knee",
                "ankle": "left_ankle",
                "foot": "left_foot",
                "heel": "left_heel",
            }
        ),
    },
    "zed_body_38": {
        "pelvis": "pelvis",
        "spine_mid": "spine_2",
        "chest": "spine_3",
        "neck": "neck",
        # BODY_38 has no head-centre joint, only face landmarks. Left out.
        "nose": "nose",
        **_mirror(
            {
                "clavicle": "left_clavicle",
                "shoulder": "left_shoulder",
                "elbow": "left_elbow",
                "wrist": "left_wrist",
                "hip": "left_hip",
                "knee": "left_knee",
                "ankle": "left_ankle",
                # The most distal foot joint of this format.
                "foot": "left_big_toe",
                "heel": "left_heel",
            }
        ),
    },
    "zed_body_18": {
        # No pelvis, spine or head joint in this format.
        "neck": "neck",
        "nose": "nose",
        **_mirror(
            {
                "shoulder": "left_shoulder",
                "elbow": "left_elbow",
                "wrist": "left_wrist",
                "hip": "left_hip",
                "knee": "left_knee",
                "ankle": "left_ankle",
            }
        ),
    },
    "mock_16": {
        "pelvis": "pelvis",
        "chest": "chest_spine",
        "neck": "neck",
        "head": "head",
        **_mirror(
            {
                "shoulder": "left_shoulder",
                "elbow": "left_elbow",
                "wrist": "left_wrist",
                "hip": "left_hip",
                "knee": "left_knee",
                "ankle": "left_ankle",
            }
        ),
    },
    "rehab24_6_mocap": {
        "pelvis": "Hips",
        "spine_mid": "Spine",
        "chest": "Spine1",
        "neck": "Neck",
        "head": "Head",
        **_mirror(
            {
                # This layout's "Shoulder" is the clavicle and "Arm" is the
                # gleno-humeral joint; naming them by role keeps every angle
                # definition honest across both conventions.
                "clavicle": "LeftShoulder",
                "shoulder": "LeftArm",
                "elbow": "LeftForeArm",
                "wrist": "LeftHand",
                "hand": "LeftHand_end",
                "hip": "LeftUpLeg",
                "knee": "LeftLeg",
                "ankle": "LeftFoot",
                "foot": "LeftToeBase",
            }
        ),
    },
}


def resolve_roles(spec: SkeletonSpec) -> dict[str, Optional[int]]:
    """Map every role onto a joint index of ``spec``, or ``None``.

    A skeleton with no table falls back to matching the role name against the
    joint names directly, which is exactly right for formats that already use
    this vocabulary and harmlessly finds nothing for those that do not.
    """
    table = _ROLE_TABLES.get(spec.name)
    resolved: dict[str, Optional[int]] = {}
    for role in ALL_ROLES:
        joint_name = table.get(role) if table is not None else role
        resolved[role] = spec.find(joint_name) if joint_name else None
    return resolved


def missing_roles(spec: SkeletonSpec, roles: tuple[str, ...]) -> tuple[str, ...]:
    """Which of ``roles`` this skeleton cannot provide."""
    resolved = resolve_roles(spec)
    return tuple(role for role in roles if resolved.get(role) is None)


def first_available(
    resolved: Mapping[str, Optional[int]], chain: tuple[str, ...]
) -> Optional[int]:
    """First role of ``chain`` this skeleton has, or ``None``.

    Used for proximal references where more than one joint is an acceptable
    stand-in *by definition* (a hip angle may be measured against the chest,
    the mid spine or the neck). Which one was used is written into the release,
    so the choice is never invisible.
    """
    for role in chain:
        index = resolved.get(role)
        if index is not None:
            return index
    return None


def first_available_role(
    resolved: Mapping[str, Optional[int]], chain: tuple[str, ...]
) -> Optional[str]:
    for role in chain:
        if resolved.get(role) is not None:
            return role
    return None


def available_bilateral_pairs(
    spec: SkeletonSpec,
) -> tuple[tuple[str, int, int], ...]:
    """``(role, left index, right index)`` for every pair the skeleton has."""
    resolved = resolve_roles(spec)
    pairs: list[tuple[str, int, int]] = []
    for role, left, right in BILATERAL_ROLE_PAIRS:
        left_index, right_index = resolved.get(left), resolved.get(right)
        if left_index is not None and right_index is not None:
            pairs.append((role, left_index, right_index))
    return tuple(pairs)


def vertical_axis_vector(spec: SkeletonSpec) -> tuple[float, float, float]:
    """Unit vector of the skeleton's configured vertical axis."""
    axis = (spec.vertical_axis or "y").strip().lower()
    return {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}.get(
        axis, (0.0, 1.0, 0.0)
    )


def role_table(spec: SkeletonSpec) -> dict[str, Any]:
    """The resolved role table, as written into ``feature_spec.json``."""
    resolved = resolve_roles(spec)
    return {
        "skeleton_format": spec.name,
        "roles": {
            role: (
                {"index": index, "joint": spec.joint_names[index]}
                if index is not None
                else None
            )
            for role, index in resolved.items()
        },
        "note": (
            "Rolü bulunmayan iskelet biçimlerinde, o role bağlı özellik sütunu "
            "NaN kalır; komşu eklem yerine geçmez."
        ),
    }


__all__ = [
    "ALL_ROLES",
    "BILATERAL_ROLE_PAIRS",
    "CENTRE_ROLES",
    "SIDED_ROLES",
    "SIDES",
    "available_bilateral_pairs",
    "first_available",
    "first_available_role",
    "missing_roles",
    "resolve_roles",
    "role_table",
    "vertical_axis_vector",
]
