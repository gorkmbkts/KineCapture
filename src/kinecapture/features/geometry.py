"""Spatial primitives shared by every geometric feature.

One implementation of "angle between three points", one of "body frame", one of
"bone vector" - so a bug is fixed once and the release's description of a
quantity matches what the code actually did.

Conventions, all of them recorded in the release:

* A vector shorter than :data:`EPSILON` has no direction, so anything derived
  from it is NaN rather than an arbitrary number.
* The body frame's axes are ``x`` = the horizontal pelvis right-to-left axis,
  ``y`` = the skeleton's configured vertical axis, ``z`` = the right-handed
  completion. Whether ``z`` points anteriorly is decided **once per sequence**
  from an anatomical reference when the skeleton has one, never per frame,
  because a per-frame decision could flicker on tracker noise.
* Nothing here modifies ``joints_xyz``. Every function returns new arrays.
"""

from __future__ import annotations

import warnings
from typing import Mapping, Optional

import numpy as np

from kinecapture.features.roles import resolve_roles, vertical_axis_vector
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Vectors shorter than this carry no usable direction (length units).
EPSILON: float = 1e-6


def unit(vectors: np.ndarray) -> np.ndarray:
    """Normalise along the last axis; too-short vectors become NaN."""
    array = np.asarray(vectors, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        norm = np.sqrt((array**2).sum(axis=-1, keepdims=True))
        result = np.where(norm > EPSILON, array / norm, np.nan)
    return result


def three_point_angle(
    proximal: np.ndarray, vertex: np.ndarray, distal: np.ndarray
) -> np.ndarray:
    """Interior angle at ``vertex``, in radians, over the leading axes.

    Uses ``atan2(|u x v|, u . v)``, which keeps full precision at both ends of
    the range where an ``arccos`` formulation degrades. Missing points and
    degenerate (near-zero-length) segments give NaN.
    """
    u = np.asarray(proximal, dtype=np.float64) - np.asarray(vertex, dtype=np.float64)
    v = np.asarray(distal, dtype=np.float64) - np.asarray(vertex, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        cross = np.linalg.norm(np.cross(u, v), axis=-1)
        dot = (u * v).sum(axis=-1)
        lengths = np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
        angle = np.arctan2(cross, dot)
        return np.where(lengths > EPSILON * EPSILON, angle, np.nan)


def axis_angle(
    start: np.ndarray, end: np.ndarray, axis: tuple[float, float, float]
) -> np.ndarray:
    """Angle between the segment ``start -> end`` and a fixed axis, in radians."""
    direction = np.asarray(end, dtype=np.float64) - np.asarray(start, dtype=np.float64)
    reference = np.asarray(axis, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        cross = np.linalg.norm(np.cross(direction, reference), axis=-1)
        dot = (direction * reference).sum(axis=-1)
        length = np.linalg.norm(direction, axis=-1)
        return np.where(length > EPSILON, np.arctan2(cross, dot), np.nan)


def line_tilt(
    left: np.ndarray, right: np.ndarray, axis: tuple[float, float, float]
) -> np.ndarray:
    """Signed inclination of the right-to-left line out of the horizontal plane.

    Positive when the left joint is higher along ``axis`` than the right one.
    """
    direction = np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64)
    reference = np.asarray(axis, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        length = np.linalg.norm(direction, axis=-1)
        ratio = (direction * reference).sum(axis=-1) / np.where(
            length > EPSILON, length, np.nan
        )
        return np.arcsin(np.clip(ratio, -1.0, 1.0))


def bone_table(spec: SkeletonSpec) -> list[dict[str, object]]:
    """Parent/child indices and names for every bone, in ``spec.edges`` order."""
    return [
        {
            "index": position,
            "parent_index": int(parent),
            "child_index": int(child),
            "parent": spec.joint_names[parent],
            "child": spec.joint_names[child],
            "name": f"{spec.joint_names[parent]}__{spec.joint_names[child]}",
        }
        for position, (parent, child) in enumerate(spec.edges)
    ]


def bone_vectors(joints: np.ndarray, spec: SkeletonSpec) -> np.ndarray:
    """``[T, B, 3]`` child-minus-parent vectors aligned with ``spec.edges``."""
    array = np.asarray(joints, dtype=np.float32)
    frames = array.shape[0]
    bones = len(spec.edges)
    result = np.full((frames, bones, 3), np.nan, dtype=np.float32)
    for position, (parent, child) in enumerate(spec.edges):
        if parent < array.shape[1] and child < array.shape[1]:
            result[:, position, :] = array[:, child, :] - array[:, parent, :]
    return result


def sequence_body_scale(
    joints: np.ndarray, roles: Mapping[str, Optional[int]]
) -> float:
    """A single length that scales with the person, in capture length units.

    Defined as the median over frames of ``trunk + mean(thigh) + mean(shank)``,
    where trunk is pelvis-to-neck. It is a *body size proxy*, not a stature
    measurement: it ignores the head, the feet and any soft-tissue offset, and
    a tracker's joint centres are not anatomical landmarks.

    Returns NaN when the skeleton lacks the joints or no frame has all of them,
    which is the honest answer - a fallback constant would silently rescale
    every ratio derived from it.
    """
    array = np.asarray(joints, dtype=np.float64)

    def _segment(a: str, b: str) -> Optional[np.ndarray]:
        ia, ib = roles.get(a), roles.get(b)
        if ia is None or ib is None:
            return None
        with np.errstate(invalid="ignore"):
            return np.linalg.norm(array[:, ia, :] - array[:, ib, :], axis=-1)

    trunk = _segment("pelvis", "neck")
    thighs = [_segment(f"{s}_hip", f"{s}_knee") for s in ("left", "right")]
    shanks = [_segment(f"{s}_knee", f"{s}_ankle") for s in ("left", "right")]
    if trunk is None or all(t is None for t in thighs) or all(s is None for s in shanks):
        return float("nan")

    def _mean(parts: list[Optional[np.ndarray]]) -> np.ndarray:
        present = [p for p in parts if p is not None]
        with warnings.catch_warnings():
            # An all-NaN frame is an expected input here - the person was not
            # tracked - and NaN is the answer we want, not a warning.
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(np.stack(present, axis=0), axis=0)

    with np.errstate(invalid="ignore"):
        total = trunk + _mean(thighs) + _mean(shanks)
        finite = total[np.isfinite(total)]
    return float(np.median(finite)) if finite.size else float("nan")


def body_frame(
    joints: np.ndarray, spec: SkeletonSpec
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object]]:
    """Per-frame body rotation, origin and validity.

    Returns ``(rotation [T, 3, 3], origin [T, 3], valid [T], provenance)``.
    Rows of the rotation are the body axes expressed in capture coordinates, so
    ``(p - origin) @ rotation.transpose(0, 2, 1)`` puts a point into body space.

    A frame without both hips has no left-right axis, so it is marked invalid
    rather than falling back to the shoulders - the two are not the same axis
    and mixing them would make the resulting coordinates mean two things.
    """
    array = np.asarray(joints, dtype=np.float64)
    frames = array.shape[0]
    roles = resolve_roles(spec)
    up = np.asarray(vertical_axis_vector(spec), dtype=np.float64)

    rotation = np.full((frames, 3, 3), np.nan, dtype=np.float32)
    origin = np.full((frames, 3), np.nan, dtype=np.float32)
    valid = np.zeros(frames, dtype=bool)
    provenance: dict[str, object] = {
        "origin_role": None,
        "left_right_axis": "right_hip -> left_hip, dikey bileşeni çıkarılmış",
        "vertical_axis": spec.vertical_axis,
        "forward_axis": "cross(x, y) (sağ el kuralı)",
        "forward_source": "handedness_only",
        "forward_sign": 1.0,
    }

    left_hip, right_hip = roles.get("left_hip"), roles.get("right_hip")
    root_role = "pelvis" if roles.get("pelvis") is not None else None
    root_index = roles["pelvis"] if root_role else spec.root_index
    provenance["origin_role"] = root_role or f"spec.root_index={spec.root_index}"
    if left_hip is None or right_hip is None:
        provenance["unavailable_reason"] = (
            "İskelette sol/sağ kalça eklemi yok; gövde ekseni tanımlanamıyor."
        )
        return rotation, origin, valid, provenance

    lateral = array[:, left_hip, :] - array[:, right_hip, :]
    horizontal = lateral - (lateral @ up)[:, None] * up[None, :]
    with np.errstate(invalid="ignore"):
        norm = np.linalg.norm(horizontal, axis=-1)
        x_axis = np.where(
            (norm > EPSILON)[:, None], horizontal / norm[:, None], np.nan
        )
    y_axis = np.broadcast_to(up, (frames, 3))
    z_axis = np.cross(x_axis, y_axis)

    # Resolve the anterior sign once for the whole sequence, from an anatomical
    # reference if the skeleton has one. Deciding per frame could flip mid-take.
    anterior_index = roles.get("nose")
    if anterior_index is None:
        anterior_index = roles.get("head")
    sign = 1.0
    if anterior_index is not None and roles.get("neck") is not None:
        forward = array[:, anterior_index, :] - array[:, roles["neck"], :]
        projection = (forward * z_axis).sum(axis=-1)
        finite = projection[np.isfinite(projection)]
        if finite.size:
            median = float(np.median(finite))
            if abs(median) > EPSILON:
                sign = 1.0 if median > 0 else -1.0
                provenance["forward_source"] = (
                    "anatomik referans (boyun -> burun/kafa), sekans boyunca sabit"
                )
                provenance["forward_sign"] = sign
    z_axis = z_axis * sign

    stack = np.stack([x_axis, y_axis, z_axis], axis=1)
    usable = np.isfinite(stack).all(axis=(1, 2)) & np.isfinite(
        array[:, root_index, :]
    ).all(axis=-1)
    rotation[usable] = stack[usable].astype(np.float32)
    origin[usable] = array[usable, root_index, :].astype(np.float32)
    valid[:] = usable
    return rotation, origin, valid, provenance


def to_body_space(
    joints: np.ndarray, rotation: np.ndarray, origin: np.ndarray
) -> np.ndarray:
    """``[T, J, 3]`` coordinates expressed in the per-frame body frame."""
    array = np.asarray(joints, dtype=np.float64)
    rot = np.asarray(rotation, dtype=np.float64)
    centred = array - np.asarray(origin, dtype=np.float64)[:, None, :]
    # rows of `rot` are the body axes, so a projection is a plain dot product.
    return np.einsum("tab,tjb->tja", rot, centred).astype(np.float32)


__all__ = [
    "EPSILON",
    "axis_angle",
    "body_frame",
    "bone_table",
    "bone_vectors",
    "line_tilt",
    "sequence_body_scale",
    "three_point_angle",
    "to_body_space",
    "unit",
]
