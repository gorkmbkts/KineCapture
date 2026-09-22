"""Which colour each joint and each bone is. No Qt, no OpenGL.

The rule the design review fixed: colour belongs to the **athlete's anatomy**,
not to the screen. The right arm is amber whether the virtual camera is in
front of the person or behind them. A viewer whose left and right swapped as
they orbited would be worse than one with no colour at all, because it would
look authoritative while being wrong.

So the mapping is resolved through the skeleton's own role table
(:mod:`kinecapture.features.roles`), never from joint indices. Index 5 is a
left shoulder in ``zed_body_34`` and a right shoulder in ``zed_body_18``;
anything keyed on the number would silently mislabel one of them.

A joint whose role the format does not declare gets the neutral colour and is
*named* unknown. That is the honest answer: this file will not guess a side
from a position in space.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from kinecapture.features.roles import resolve_roles
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: The five anatomical groups, and the token each is drawn in.
GROUP_TOKENS = {
    "right_arm": "KcAnatomyRightArm",
    "right_leg": "KcAnatomyRightLeg",
    "left_arm": "KcAnatomyLeftArm",
    "left_leg": "KcAnatomyLeftLeg",
    "torso": "KcAnatomyTorso",
    "unknown": "KcAnatomyUnknown",
}

#: Which limb a sided role belongs to. Centre roles are the torso.
_ARM_ROLES = frozenset({"clavicle", "shoulder", "elbow", "wrist", "hand"})
_LEG_ROLES = frozenset({"hip", "knee", "ankle", "foot", "heel"})


def group_for_role(role: str) -> str:
    """``right_arm`` / ``left_leg`` / ``torso`` / ``unknown`` for one role."""
    if not role:
        return "unknown"
    side, _, rest = role.partition("_")
    if side in ("left", "right") and rest:
        if rest in _ARM_ROLES:
            return f"{side}_arm"
        if rest in _LEG_ROLES:
            return f"{side}_leg"
        return "unknown"
    # Centre roles: pelvis, spine_mid, chest, neck, head, nose.
    return "torso"


def joint_groups(spec: Optional[SkeletonSpec]) -> tuple[str, ...]:
    """One group name per joint of ``spec``, in the spec's own joint order.

    Resolved through the role table. A joint no role maps onto comes back as
    ``"unknown"`` rather than being assigned a side by its name or its
    neighbours - a format this project has not mapped is a format whose sides
    it does not know.
    """
    if spec is None:
        return ()
    groups = ["unknown"] * spec.num_joints
    for role, index in resolve_roles(spec).items():
        if index is None or not 0 <= index < len(groups):
            continue
        groups[index] = group_for_role(role)
    return tuple(groups)


def bone_groups(
    spec: Optional[SkeletonSpec], edges: Optional[Sequence[tuple[int, int]]] = None
) -> tuple[str, ...]:
    """One group per bone, from the two joints it joins.

    A bone between two joints of the same group is that group's. A bone that
    crosses groups - a clavicle reaching from the chest to a shoulder - takes
    the *limb's* colour rather than the torso's, because what a reader is
    tracing along it is the limb. A bone touching an unmapped joint is
    unknown, and drawn neutral.
    """
    if spec is None:
        return ()
    groups = joint_groups(spec)
    pairs = tuple(edges if edges is not None else spec.edges)
    out: list[str] = []
    for a, b in pairs:
        if not (0 <= a < len(groups) and 0 <= b < len(groups)):
            out.append("unknown")
            continue
        first, second = groups[a], groups[b]
        if first == second:
            out.append(first)
        elif "unknown" in (first, second):
            out.append("unknown")
        elif first == "torso":
            out.append(second)
        elif second == "torso":
            out.append(first)
        else:
            # Two different limbs joined directly: nothing sensible to claim.
            out.append("unknown")
    return tuple(out)


def token_for(group: str) -> str:
    return GROUP_TOKENS.get(group, GROUP_TOKENS["unknown"])


def joint_tokens(spec: Optional[SkeletonSpec]) -> tuple[str, ...]:
    return tuple(token_for(group) for group in joint_groups(spec))


def bone_tokens(
    spec: Optional[SkeletonSpec], edges: Optional[Sequence[tuple[int, int]]] = None
) -> tuple[str, ...]:
    return tuple(token_for(group) for group in bone_groups(spec, edges))


def role_names(spec: Optional[SkeletonSpec]) -> tuple[str, ...]:
    """The anatomical role of each joint, or ``""`` where none is declared.

    Used for the hover readout. The joint's *own* name is a better label when
    a role is missing, and the caller has that from the spec.
    """
    if spec is None:
        return ()
    names = [""] * spec.num_joints
    for role, index in resolve_roles(spec).items():
        if index is not None and 0 <= index < len(names):
            names[index] = role
    return tuple(names)


def joint_labels(spec: Optional[SkeletonSpec]) -> tuple[str, ...]:
    """What to show when the pointer is over a joint.

    The anatomical role where there is one - it is what a coach says out loud -
    and the format's own joint name where there is not. Never a bare index.
    """
    if spec is None:
        return ()
    roles = role_names(spec)
    return tuple(
        (role.replace("_", " ") if role else spec.joint_names[index])
        for index, role in enumerate(roles)
    )


def colours_for(
    spec: Optional[SkeletonSpec], resolve: Mapping[str, str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(joint colours, bone colours)`` as resolved colour strings."""
    joints = tuple(resolve[token] for token in joint_tokens(spec))
    bones = tuple(resolve[token] for token in bone_tokens(spec))
    return joints, bones


__all__ = [
    "GROUP_TOKENS",
    "bone_groups",
    "bone_tokens",
    "colours_for",
    "group_for_role",
    "joint_groups",
    "joint_labels",
    "joint_tokens",
    "role_names",
    "token_for",
]
