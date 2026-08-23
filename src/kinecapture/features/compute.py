"""Turning one exported movement sample into its selected feature arrays.

Everything a feature needs arrives in a :class:`FeatureContext`: the pose array
*after* any joint mapping, the camera timestamps, the optional tracker arrays
that survived that mapping, and the skeleton the result is expressed in. Each
feature is a small function that reads the context and returns named arrays.

Two properties this file is built around:

* **Same input, same output.** No randomness, no wall clock, no dependence on
  other samples in the release. A feature that needed the dataset's mean would
  leak the split into the data, so no such feature exists here.
* **Unavailable is a first-class answer.** A feature that cannot be computed -
  the skeleton has no such joint, the tracker never recorded that field, the
  joint mapping makes it meaningless - still emits arrays of the right shape
  filled with NaN or ``False``, and reports itself absent with a reason. That
  keeps every ``.npz`` in a release carrying the same keys while never dressing
  a hole up as a measurement.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np

from kinecapture.features.base import Availability, MappingSupport, SourceField
from kinecapture.features.definitions import (
    ANGLE_DEFINITIONS,
    ANGLE_IDS,
    BILATERAL_ANGLE_GROUPS,
    DISTANCE_DEFINITIONS,
    DISTANCE_IDS,
    RATIO_DEFINITIONS,
    RATIO_IDS,
)
from kinecapture.features.geometry import (
    EPSILON,
    axis_angle,
    body_frame,
    bone_table,
    bone_vectors,
    line_tilt,
    sequence_body_scale,
    three_point_angle,
    to_body_space,
    unit,
)
from kinecapture.features.roles import (
    BILATERAL_ROLE_PAIRS,
    first_available,
    first_available_role,
    resolve_roles,
    vertical_axis_vector,
)
from kinecapture.features.temporal import (
    DEFAULT_GAP_FACTOR,
    central_difference,
    delta_time_s,
    frame_difference,
    magnitude,
    max_gap_seconds,
    path_length,
    second_difference,
)
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Fixed column count of the bilateral joint-pair arrays.
BILATERAL_PAIR_IDS: tuple[str, ...] = tuple(role for role, _, _ in BILATERAL_ROLE_PAIRS)
#: Fixed column ids of the bilateral angle arrays.
BILATERAL_ANGLE_IDS: tuple[str, ...] = tuple(
    group for group, _, _ in BILATERAL_ANGLE_GROUPS
)

_TRACKING_STATE_CODES: dict[str, int] = {
    "ok": 1,
    "searching": 2,
    "off": 3,
    "terminate": 4,
}
_ACTION_STATE_CODES: dict[str, int] = {"idle": 1, "moving": 2}


@dataclass
class FeatureOutput:
    """What one feature produced for one sample."""

    arrays: dict[str, np.ndarray]
    computed: bool = True
    reason: str = ""


@dataclass
class FeatureContext:
    """Everything the feature functions may read, and nothing else.

    ``joints`` is already in the *output* skeleton's joint order, so a mapped
    export computes its geometry on the target skeleton rather than remapping
    numbers that were derived from a different topology.
    """

    spec: SkeletonSpec
    joints: np.ndarray
    timestamps_ns: np.ndarray
    frame_indices: np.ndarray
    target_fps: float = 30.0
    confidences: Optional[np.ndarray] = None
    #: Optional tracker arrays keyed by :class:`SourceField` value. Entries that
    #: a mapping made unsafe have already been removed by the caller.
    raw: Mapping[str, Optional[np.ndarray]] = field(default_factory=dict)
    body_present: Optional[np.ndarray] = None
    tracking_state: Optional[np.ndarray] = None
    body_confidence: Optional[np.ndarray] = None
    action_state: Optional[np.ndarray] = None
    mapping_active: bool = False
    gap_factor: float = DEFAULT_GAP_FACTOR

    # ------------------------------------------------------------- basics
    @property
    def frames(self) -> int:
        return int(self.joints.shape[0])

    @property
    def num_joints(self) -> int:
        return int(self.joints.shape[1])

    @cached_property
    def roles(self) -> dict[str, Optional[int]]:
        return resolve_roles(self.spec)

    @cached_property
    def max_gap_s(self) -> float:
        return max_gap_seconds(self.target_fps, self.gap_factor)

    @cached_property
    def joint_valid(self) -> np.ndarray:
        """``[T, J]`` joints whose three coordinates are all finite."""
        return np.isfinite(self.joints).all(axis=2)

    @cached_property
    def frame_valid(self) -> np.ndarray:
        """``[T]`` frames with at least one usable joint."""
        return self.joint_valid.any(axis=1)

    @cached_property
    def velocity(self) -> tuple[np.ndarray, np.ndarray]:
        return central_difference(
            self.joints, self.timestamps_ns, max_gap_s=self.max_gap_s
        )

    @cached_property
    def speed(self) -> np.ndarray:
        return magnitude(self.velocity[0])

    @cached_property
    def body_frame(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
        return body_frame(self.joints, self.spec)

    @cached_property
    def body_space(self) -> np.ndarray:
        rotation, origin, valid, _ = self.body_frame
        result = to_body_space(self.joints, rotation, origin)
        result[~valid] = np.nan
        return result

    @cached_property
    def body_scale(self) -> float:
        return sequence_body_scale(self.joints, self.roles)

    @cached_property
    def resolved_angles(self) -> list[dict[str, Any]]:
        """Which joint each angle definition actually resolved to."""
        resolved: list[dict[str, Any]] = []
        for definition in ANGLE_DEFINITIONS:
            entry: dict[str, Any] = {"angle_id": definition.angle_id, "points": []}
            usable = True
            for chain in definition.points:
                role = first_available_role(self.roles, chain)
                index = first_available(self.roles, chain)
                entry["points"].append(
                    {"role": role, "index": index, "chain": list(chain)}
                )
                if index is None:
                    usable = False
            entry["available"] = usable
            resolved.append(entry)
        return resolved

    @cached_property
    def angles(self) -> tuple[np.ndarray, np.ndarray]:
        """``([T, A] radians, [T, A] mask)`` in :data:`ANGLE_IDS` order."""
        frames = self.frames
        count = len(ANGLE_DEFINITIONS)
        values = np.full((frames, count), np.nan, dtype=np.float32)
        axis = vertical_axis_vector(self.spec)
        for column, (definition, resolved) in enumerate(
            zip(ANGLE_DEFINITIONS, self.resolved_angles)
        ):
            if not resolved["available"]:
                continue
            indices = [point["index"] for point in resolved["points"]]
            points = [self.joints[:, index, :] for index in indices]
            if definition.kind == "three_point":
                values[:, column] = three_point_angle(*points)
            elif definition.kind == "vector_axis":
                values[:, column] = axis_angle(points[0], points[1], axis)
            elif definition.kind == "line_tilt":
                values[:, column] = line_tilt(points[0], points[1], axis)
        return values, np.isfinite(values)

    @cached_property
    def angular_velocity(self) -> tuple[np.ndarray, np.ndarray]:
        values, _ = self.angles
        # Angles are A independent scalar series, not one A-vector, so each
        # column gets its own validity entry.
        return central_difference(
            values, self.timestamps_ns, max_gap_s=self.max_gap_s, vector=False
        )

    @cached_property
    def distances(self) -> tuple[np.ndarray, np.ndarray]:
        frames = self.frames
        values = np.full((frames, len(DISTANCE_DEFINITIONS)), np.nan, dtype=np.float32)
        for column, definition in enumerate(DISTANCE_DEFINITIONS):
            a = self.roles.get(definition.role_a)
            b = self.roles.get(definition.role_b)
            if a is None or b is None:
                continue
            with np.errstate(invalid="ignore"):
                values[:, column] = np.linalg.norm(
                    self.joints[:, a, :] - self.joints[:, b, :], axis=-1
                )
        return values, np.isfinite(values)

    @cached_property
    def bilateral_pairs(self) -> list[tuple[str, Optional[int], Optional[int]]]:
        return [
            (role, self.roles.get(left), self.roles.get(right))
            for role, left, right in BILATERAL_ROLE_PAIRS
        ]

    def available(self, source: SourceField) -> Optional[np.ndarray]:
        return self.raw.get(source.value)


# ---------------------------------------------------------------------------
# Feature implementations
# ---------------------------------------------------------------------------


def _nan(*shape: int) -> np.ndarray:
    return np.full(shape, np.nan, dtype=np.float32)


def _false(*shape: int) -> np.ndarray:
    return np.zeros(shape, dtype=bool)


def _f_canonical_pose(ctx: FeatureContext) -> FeatureOutput:
    """The canonical arrays, restated through the same path as everything else.

    The exporter also writes these keys directly; producing them here as well
    means the availability report, the array-key contract and the feature spec
    describe the whole ``.npz`` rather than everything except its core.
    """
    return FeatureOutput(
        {
            "joints_xyz": np.asarray(ctx.joints, dtype=np.float32),
            "frame_indices": np.asarray(ctx.frame_indices, dtype=np.int64),
            "camera_timestamps_ns": np.asarray(ctx.timestamps_ns, dtype=np.int64),
        }
    )


def _f_joint_confidences(ctx: FeatureContext) -> FeatureOutput:
    values = ctx.confidences
    if values is None:
        return FeatureOutput(
            {"joint_confidences": _nan(ctx.frames, ctx.num_joints)},
            computed=False,
            reason="Bu kayıtta eklem güven değeri yok.",
        )
    return FeatureOutput({"joint_confidences": np.asarray(values, dtype=np.float32)})


def _f_validity_masks(ctx: FeatureContext) -> FeatureOutput:
    return FeatureOutput(
        {
            "joint_valid_mask": ctx.joint_valid,
            "frame_valid_mask": ctx.frame_valid,
        }
    )


def _f_frame_timing(ctx: FeatureContext) -> FeatureOutput:
    return FeatureOutput({"delta_time_s": delta_time_s(ctx.timestamps_ns)})


def _f_body_state(ctx: FeatureContext) -> FeatureOutput:
    frames = ctx.frames
    present = (
        np.asarray(ctx.body_present, dtype=bool)
        if ctx.body_present is not None
        else ctx.frame_valid
    )
    confidence = (
        np.asarray(ctx.body_confidence, dtype=np.float32)
        if ctx.body_confidence is not None
        else _nan(frames)
    )
    tracking = (
        np.asarray(ctx.tracking_state, dtype=np.uint8)
        if ctx.tracking_state is not None
        else np.zeros(frames, dtype=np.uint8)
    )
    action = (
        np.asarray(ctx.action_state, dtype=np.uint8)
        if ctx.action_state is not None
        else np.zeros(frames, dtype=np.uint8)
    )
    return FeatureOutput(
        {
            "body_present_mask": present,
            "body_confidence": confidence,
            "tracking_state_code": tracking,
            "action_state_code": action,
        }
    )


def _raw_passthrough(
    ctx: FeatureContext, source: SourceField, key: str, *shape_tail: int
) -> FeatureOutput:
    values = ctx.available(source)
    if values is None:
        return FeatureOutput(
            {key: _nan(ctx.frames, *shape_tail)},
            computed=False,
            reason=(
                "Bu kayıtta bu tracker alanı yok "
                "(eski kayıt, desteklemeyen iskelet biçimi veya eşleştirme "
                "nedeniyle devre dışı)."
            ),
        )
    return FeatureOutput({key: np.asarray(values, dtype=np.float32)})


def _f_tracker_joint_orientations(ctx: FeatureContext) -> FeatureOutput:
    return _raw_passthrough(
        ctx,
        SourceField.JOINT_ORIENTATIONS,
        "joint_orientations_xyzw",
        ctx.num_joints,
        4,
    )


def _f_tracker_joint_positions_2d(ctx: FeatureContext) -> FeatureOutput:
    return _raw_passthrough(
        ctx, SourceField.JOINT_POSITIONS_2D, "joint_positions_2d", ctx.num_joints, 2
    )


def _f_tracker_joint_covariances(ctx: FeatureContext) -> FeatureOutput:
    return _raw_passthrough(
        ctx,
        SourceField.JOINT_POSITION_COVARIANCES,
        "joint_position_covariances_raw",
        ctx.num_joints,
        6,
    )


def _f_tracker_local_joint_positions(ctx: FeatureContext) -> FeatureOutput:
    return _raw_passthrough(
        ctx,
        SourceField.LOCAL_JOINT_POSITIONS,
        "local_joint_positions_xyz",
        ctx.num_joints,
        3,
    )


def _f_tracker_root_state(ctx: FeatureContext) -> FeatureOutput:
    frames = ctx.frames
    arrays: dict[str, np.ndarray] = {}
    present = 0
    for source, key, width in (
        (SourceField.ROOT_POSITION, "root_position_xyz", 3),
        (SourceField.ROOT_ORIENTATION, "root_orientation_xyzw", 4),
        (SourceField.ROOT_VELOCITY, "tracker_root_velocity_xyz", 3),
        (SourceField.ROOT_POSITION_COVARIANCE, "root_position_covariance_raw", 6),
    ):
        values = ctx.available(source)
        if values is None:
            arrays[key] = _nan(frames, width)
        else:
            arrays[key] = np.asarray(values, dtype=np.float32)
            present += 1
    return FeatureOutput(
        arrays,
        computed=present > 0,
        reason="" if present else "Bu kayıtta tracker kök alanları yok.",
    )


def _f_root_centered(ctx: FeatureContext) -> FeatureOutput:
    root = ctx.roles.get("pelvis")
    if root is None:
        root = ctx.spec.root_index
    centred = ctx.joints - ctx.joints[:, root : root + 1, :]
    return FeatureOutput({"root_centered_xyz": centred.astype(np.float32)})


def _f_body_aligned(ctx: FeatureContext) -> FeatureOutput:
    rotation, _origin, valid, provenance = ctx.body_frame
    arrays = {
        "body_aligned_xyz": ctx.body_space,
        "body_frame_rotation": rotation,
        "body_frame_valid_mask": valid,
    }
    if not valid.any():
        return FeatureOutput(
            arrays,
            computed=False,
            reason=str(
                provenance.get(
                    "unavailable_reason",
                    "Hiçbir karede gövde çerçevesi kurulamadı.",
                )
            ),
        )
    return FeatureOutput(arrays)


def _f_body_scale(ctx: FeatureContext) -> FeatureOutput:
    value = np.asarray([ctx.body_scale], dtype=np.float32)
    return FeatureOutput(
        {"body_scale": value},
        computed=bool(np.isfinite(value).all()),
        reason=(
            ""
            if np.isfinite(value).all()
            else "Gövde ölçeği için gereken eklemler bu kayıtta yok."
        ),
    )


def _f_scale_normalized(ctx: FeatureContext) -> FeatureOutput:
    scale = ctx.body_scale
    root = ctx.roles.get("pelvis")
    if root is None:
        root = ctx.spec.root_index
    centred = ctx.joints - ctx.joints[:, root : root + 1, :]
    if not np.isfinite(scale) or scale <= EPSILON:
        return FeatureOutput(
            {"scale_normalized_xyz": _nan(ctx.frames, ctx.num_joints, 3)},
            computed=False,
            reason="Gövde ölçeği hesaplanamadığı için normalize koordinat yok.",
        )
    return FeatureOutput(
        {"scale_normalized_xyz": (centred / scale).astype(np.float32)}
    )


def _f_bone_geometry(ctx: FeatureContext) -> FeatureOutput:
    vectors = bone_vectors(ctx.joints, ctx.spec)
    lengths = magnitude(vectors)
    units = unit(vectors).astype(np.float32)
    valid = np.isfinite(vectors).all(axis=2)
    return FeatureOutput(
        {
            "bone_vectors_xyz": vectors,
            "bone_lengths": lengths,
            "bone_unit_vectors_xyz": units,
            "bone_valid_mask": valid,
        },
        computed=bool(len(ctx.spec.edges)),
        reason="" if ctx.spec.edges else "İskelet tanımında kemik listesi yok.",
    )


def _f_segment_distances(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.distances
    return FeatureOutput(
        {"segment_distances": values, "segment_distance_valid_mask": mask},
        computed=bool(mask.any()),
        reason="" if mask.any() else "Tanımlı mesafelerin hiçbiri bu iskelette yok.",
    )


def _f_segment_ratios(ctx: FeatureContext) -> FeatureOutput:
    values, _ = ctx.distances
    ratios = np.full((ctx.frames, len(RATIO_DEFINITIONS)), np.nan, dtype=np.float32)
    for column, definition in enumerate(RATIO_DEFINITIONS):
        numerator = values[:, DISTANCE_IDS.index(definition.numerator)]
        denominator = values[:, DISTANCE_IDS.index(definition.denominator)]
        with np.errstate(invalid="ignore", divide="ignore"):
            ratios[:, column] = np.where(
                np.abs(denominator) > EPSILON, numerator / denominator, np.nan
            )
    finite = np.isfinite(ratios)
    return FeatureOutput(
        {"segment_ratios": ratios},
        computed=bool(finite.any()),
        reason="" if finite.any() else "Oranlar için gereken mesafeler yok.",
    )


def _f_joint_centroid(ctx: FeatureContext) -> FeatureOutput:
    """Mean of the visible joints - explicitly *not* a centre of mass.

    A real COM needs validated segment masses and centroid ratios, which this
    project does not have, so the array is named for what it is.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        centroid = np.nanmean(ctx.joints, axis=1)
    valid = ctx.joint_valid.any(axis=1)
    centroid[~valid] = np.nan
    return FeatureOutput(
        {
            "joint_centroid_proxy_xyz": centroid.astype(np.float32),
            "joint_centroid_valid_mask": valid,
        }
    )


def _f_joint_displacement(ctx: FeatureContext) -> FeatureOutput:
    values, mask = frame_difference(ctx.joints)
    return FeatureOutput(
        {"joint_displacement_xyz": values, "joint_displacement_valid_mask": mask}
    )


def _f_joint_velocity(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.velocity
    speed = ctx.speed.copy()
    speed[~mask] = np.nan
    return FeatureOutput(
        {
            "joint_velocity_xyz": values,
            "joint_speed": speed,
            "joint_velocity_valid_mask": mask,
        }
    )


def _f_joint_acceleration(ctx: FeatureContext) -> FeatureOutput:
    values, mask = second_difference(
        ctx.joints, ctx.timestamps_ns, max_gap_s=ctx.max_gap_s
    )
    magnitudes = magnitude(values)
    magnitudes[~mask] = np.nan
    return FeatureOutput(
        {
            "joint_acceleration_xyz": values,
            "joint_acceleration_magnitude": magnitudes,
            "joint_acceleration_valid_mask": mask,
        }
    )


def _f_root_kinematics(ctx: FeatureContext) -> FeatureOutput:
    root = ctx.roles.get("pelvis")
    if root is None:
        root = ctx.spec.root_index
    trajectory = ctx.joints[:, root, :].astype(np.float32)
    velocity, mask = central_difference(
        trajectory, ctx.timestamps_ns, max_gap_s=ctx.max_gap_s
    )
    speed = magnitude(velocity)
    speed[~mask] = np.nan
    length = path_length(trajectory, ctx.joint_valid[:, root])
    return FeatureOutput(
        {
            "root_trajectory_xyz": trajectory,
            "root_velocity_derived_xyz": velocity,
            "root_speed": speed,
            "root_path_length": np.asarray([length], dtype=np.float32),
        }
    )


def _f_joint_jerk(ctx: FeatureContext) -> FeatureOutput:
    acceleration, _ = second_difference(
        ctx.joints, ctx.timestamps_ns, max_gap_s=ctx.max_gap_s
    )
    jerk, mask = central_difference(
        acceleration, ctx.timestamps_ns, max_gap_s=ctx.max_gap_s
    )
    magnitudes = magnitude(jerk)
    magnitudes[~mask] = np.nan
    return FeatureOutput(
        {"joint_jerk_magnitude": magnitudes, "joint_jerk_valid_mask": mask}
    )


def _f_joint_angles(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.angles
    return FeatureOutput(
        {"joint_angles_rad": values, "joint_angle_valid_mask": mask},
        computed=bool(mask.any()),
        reason="" if mask.any() else "Bu iskelette tanımlı açı hesaplanamıyor.",
    )


def _f_joint_angles_degrees(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.angles
    return FeatureOutput(
        {"joint_angles_deg": np.degrees(values).astype(np.float32)},
        computed=bool(mask.any()),
        reason="" if mask.any() else "Bu iskelette tanımlı açı hesaplanamıyor.",
    )


def _f_joint_angular_velocity(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.angular_velocity
    return FeatureOutput(
        {
            "joint_angular_velocity_rad_s": values,
            "joint_angular_velocity_valid_mask": mask,
        },
        computed=bool(mask.any()),
        reason="" if mask.any() else "Açısal hız için yeterli açı verisi yok.",
    )


def _f_quaternion_angular_speed(ctx: FeatureContext) -> FeatureOutput:
    """Angular speed straight from the tracker's joint quaternions.

    The relative rotation angle between two unit quaternions is
    ``2 * arccos(|<qa, qb>|)``. Taking the absolute value of the inner product
    is what handles the ``q`` / ``-q`` double cover: a sign flip between two
    frames leaves the angle untouched instead of producing a spurious 2*pi
    jump. Euler angles are never differenced, for the same reason.

    Deliberately named apart from :func:`_f_joint_angular_velocity`: one is the
    rate of a defined anatomical angle, the other is the total rotation rate of
    a tracker-estimated joint frame. They are not interchangeable.
    """
    quaternions = ctx.available(SourceField.JOINT_ORIENTATIONS)
    frames, joints = ctx.frames, ctx.num_joints
    if quaternions is None:
        return FeatureOutput(
            {
                "quaternion_angular_speed_rad_s": _nan(frames, joints),
                "quaternion_angular_speed_valid_mask": _false(frames, joints),
            },
            computed=False,
            reason="Bu kayıtta eklem quaternionları yok.",
        )
    array = np.asarray(quaternions, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        norms = np.linalg.norm(array, axis=-1)
        normalised = np.where(
            (norms > EPSILON)[..., None], array / norms[..., None], np.nan
        )
    speeds = _nan(frames, joints)
    mask = _false(frames, joints)
    if frames >= 2:
        from kinecapture.features.temporal import seconds, step_valid

        stamps = seconds(ctx.timestamps_ns)
        usable = step_valid(ctx.timestamps_ns, ctx.max_gap_s)
        for position in range(frames):
            left = max(0, position - 1)
            right = min(frames - 1, position + 1)
            if position == 0:
                left, right = 0, 1
            elif position == frames - 1:
                left, right = frames - 2, frames - 1
            if not all(usable[step] for step in range(left, right)):
                continue
            span = stamps[right] - stamps[left]
            if not np.isfinite(span) or span <= 0:
                continue
            dot = np.abs((normalised[left] * normalised[right]).sum(axis=-1))
            with np.errstate(invalid="ignore"):
                angle = 2.0 * np.arccos(np.clip(dot, -1.0, 1.0))
            ok = np.isfinite(angle)
            speeds[position] = np.where(ok, angle / span, np.nan)
            mask[position] = ok
    finite = np.isfinite(speeds)
    return FeatureOutput(
        {
            "quaternion_angular_speed_rad_s": speeds,
            "quaternion_angular_speed_valid_mask": mask,
        },
        computed=bool(finite.any()),
        reason="" if finite.any() else "Quaternionların hiçbiri kullanılabilir değil.",
    )


def _f_bilateral_angles(ctx: FeatureContext) -> FeatureOutput:
    values, mask = ctx.angles
    count = len(BILATERAL_ANGLE_GROUPS)
    signed = np.full((ctx.frames, count), np.nan, dtype=np.float32)
    absolute = np.full((ctx.frames, count), np.nan, dtype=np.float32)
    valid = _false(ctx.frames, count)
    for column, (_group, left, right) in enumerate(BILATERAL_ANGLE_GROUPS):
        pair_valid = mask[:, left] & mask[:, right]
        difference = values[:, left] - values[:, right]
        signed[:, column] = np.where(pair_valid, difference, np.nan)
        absolute[:, column] = np.abs(signed[:, column])
        valid[:, column] = pair_valid
    return FeatureOutput(
        {
            "bilateral_angle_difference_rad": signed,
            "bilateral_angle_absolute_difference_rad": absolute,
            "bilateral_angle_valid_mask": valid,
        },
        computed=bool(valid.any()),
        reason="" if valid.any() else "Karşılaştırılabilir sol/sağ açı çifti yok.",
    )


def _f_bilateral_speed(ctx: FeatureContext) -> FeatureOutput:
    _, velocity_mask = ctx.velocity
    speed = ctx.speed
    count = len(BILATERAL_ROLE_PAIRS)
    signed = np.full((ctx.frames, count), np.nan, dtype=np.float32)
    absolute = np.full((ctx.frames, count), np.nan, dtype=np.float32)
    valid = _false(ctx.frames, count)
    for column, (_role, left, right) in enumerate(ctx.bilateral_pairs):
        if left is None or right is None:
            continue
        pair_valid = velocity_mask[:, left] & velocity_mask[:, right]
        difference = speed[:, left] - speed[:, right]
        signed[:, column] = np.where(pair_valid, difference, np.nan)
        absolute[:, column] = np.abs(signed[:, column])
        valid[:, column] = pair_valid
    return FeatureOutput(
        {
            "bilateral_speed_difference": signed,
            "bilateral_speed_absolute_difference": absolute,
            "bilateral_speed_valid_mask": valid,
        },
        computed=bool(valid.any()),
        reason="" if valid.any() else "Karşılaştırılabilir sol/sağ eklem çifti yok.",
    )


def _f_bilateral_mirror(ctx: FeatureContext) -> FeatureOutput:
    """Distance between a left joint and its mirrored right counterpart.

    Computed in **body space**, where the sagittal plane is the ``x = 0`` plane
    of the frame built from the pelvis. Doing this in camera coordinates would
    turn "the person is standing at an angle to the lens" into an apparent
    asymmetry, which is exactly the confound this feature must not create.

    This is a geometric difference, not an asymmetry diagnosis.
    """
    space = ctx.body_space
    _rotation, _origin, frame_valid, provenance = ctx.body_frame
    count = len(BILATERAL_ROLE_PAIRS)
    distances = np.full((ctx.frames, count), np.nan, dtype=np.float32)
    valid = _false(ctx.frames, count)
    if not frame_valid.any():
        return FeatureOutput(
            {
                "bilateral_mirror_distance": distances,
                "bilateral_mirror_valid_mask": valid,
            },
            computed=False,
            reason=str(
                provenance.get(
                    "unavailable_reason",
                    "Gövde çerçevesi kurulamadığı için ayna mesafesi yok.",
                )
            ),
        )
    mirror = np.asarray([-1.0, 1.0, 1.0], dtype=np.float32)
    for column, (_role, left, right) in enumerate(ctx.bilateral_pairs):
        if left is None or right is None:
            continue
        with np.errstate(invalid="ignore"):
            difference = space[:, left, :] - space[:, right, :] * mirror
            distance = np.linalg.norm(difference, axis=-1)
        ok = np.isfinite(distance) & frame_valid
        distances[:, column] = np.where(ok, distance, np.nan)
        valid[:, column] = ok
    return FeatureOutput(
        {
            "bilateral_mirror_distance": distances,
            "bilateral_mirror_valid_mask": valid,
        },
        computed=bool(valid.any()),
        reason="" if valid.any() else "Karşılaştırılabilir sol/sağ eklem çifti yok.",
    )


def _f_summary_vector(ctx: FeatureContext) -> FeatureOutput:
    from kinecapture.features.summary import summary_vector

    values = summary_vector(ctx)
    finite = np.isfinite(values)
    return FeatureOutput(
        {"summary_features": values},
        computed=bool(finite.any()),
        reason="" if finite.any() else "Özet vektörünün hiçbir elemanı hesaplanamadı.",
    )


#: feature_id -> implementation. Kept apart from the registry so a definition
#: and its maths can be reviewed side by side without circular imports.
FEATURE_FUNCTIONS: dict[str, Callable[[FeatureContext], FeatureOutput]] = {
    "canonical_pose": _f_canonical_pose,
    "joint_confidences": _f_joint_confidences,
    "validity_masks": _f_validity_masks,
    "frame_timing": _f_frame_timing,
    "body_state": _f_body_state,
    "tracker_joint_orientations": _f_tracker_joint_orientations,
    "tracker_joint_positions_2d": _f_tracker_joint_positions_2d,
    "tracker_joint_covariances": _f_tracker_joint_covariances,
    "tracker_local_joint_positions": _f_tracker_local_joint_positions,
    "tracker_root_state": _f_tracker_root_state,
    "root_centered_positions": _f_root_centered,
    "body_aligned_positions": _f_body_aligned,
    "body_scale": _f_body_scale,
    "scale_normalized_positions": _f_scale_normalized,
    "bone_geometry": _f_bone_geometry,
    "segment_distances": _f_segment_distances,
    "segment_ratios": _f_segment_ratios,
    "joint_centroid_proxy": _f_joint_centroid,
    "joint_displacement": _f_joint_displacement,
    "joint_velocity": _f_joint_velocity,
    "joint_acceleration": _f_joint_acceleration,
    "root_kinematics": _f_root_kinematics,
    "joint_jerk": _f_joint_jerk,
    "joint_angles": _f_joint_angles,
    "joint_angles_degrees": _f_joint_angles_degrees,
    "joint_angular_velocity": _f_joint_angular_velocity,
    "quaternion_angular_speed": _f_quaternion_angular_speed,
    "bilateral_angles": _f_bilateral_angles,
    "bilateral_speed": _f_bilateral_speed,
    "bilateral_mirror": _f_bilateral_mirror,
    "summary_vector": _f_summary_vector,
}


@dataclass
class ComputedFeatures:
    """Result of computing a selection of features for one sample."""

    arrays: dict[str, np.ndarray] = field(default_factory=dict)
    availability: dict[str, Availability] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)
    ratios: dict[str, float] = field(default_factory=dict)

    def availability_dict(self) -> dict[str, str]:
        return {key: value.value for key, value in sorted(self.availability.items())}


def _availability_ratio(array: np.ndarray) -> float:
    """Fraction of entries that carry a usable value."""
    if array.dtype == np.bool_:
        return 1.0
    if not np.issubdtype(array.dtype, np.floating):
        return 1.0
    if array.size == 0:
        return 0.0
    return float(np.isfinite(array).mean())


def compute_features(
    context: FeatureContext, feature_ids: Sequence[str]
) -> ComputedFeatures:
    """Run the requested features, in the order given.

    Unknown ids are ignored here rather than raising: the registry is the place
    that validates a selection, and an export must not die halfway through a
    release because one option went stale.
    """
    result = ComputedFeatures()
    for feature_id in feature_ids:
        function = FEATURE_FUNCTIONS.get(feature_id)
        if function is None:
            continue
        output = function(context)
        result.arrays.update(output.arrays)
        primary = next(iter(output.arrays.values()), None)
        ratio = _availability_ratio(primary) if primary is not None else 0.0
        if not output.computed or ratio <= 0.0:
            availability = Availability.ABSENT
        elif ratio >= 0.999:
            availability = Availability.FULL
        else:
            availability = Availability.PARTIAL
        result.availability[feature_id] = availability
        result.ratios[feature_id] = round(ratio, 4)
        if output.reason:
            result.reasons[feature_id] = output.reason
    return result


def column_names(spec: SkeletonSpec) -> dict[str, list[str]]:
    """Every fixed column vocabulary, for ``feature_spec.json``."""
    return {
        "joint_angles_rad": list(ANGLE_IDS),
        "joint_angles_deg": list(ANGLE_IDS),
        "joint_angular_velocity_rad_s": list(ANGLE_IDS),
        "segment_distances": list(DISTANCE_IDS),
        "segment_ratios": list(RATIO_IDS),
        "bilateral_angle_difference_rad": list(BILATERAL_ANGLE_IDS),
        "bilateral_angle_absolute_difference_rad": list(BILATERAL_ANGLE_IDS),
        "bilateral_speed_difference": list(BILATERAL_PAIR_IDS),
        "bilateral_speed_absolute_difference": list(BILATERAL_PAIR_IDS),
        "bilateral_mirror_distance": list(BILATERAL_PAIR_IDS),
        "joints": list(spec.joint_names),
        "bones": [str(entry["name"]) for entry in bone_table(spec)],
    }


__all__ = [
    "BILATERAL_ANGLE_IDS",
    "BILATERAL_PAIR_IDS",
    "ComputedFeatures",
    "FEATURE_FUNCTIONS",
    "FeatureContext",
    "FeatureOutput",
    "column_names",
    "compute_features",
]
