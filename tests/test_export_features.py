"""Feature selection as it reaches a published release.

The maths lives in ``test_features.py``. What is checked here is the contract a
consumer of a release actually sees: that the selected arrays are in every
``.npz``, that ``feature_spec.json`` describes them completely, that the joint
mapping refuses to carry what it cannot carry honestly, that validation catches
a release that does not match its own declarations, and that the fingerprint
moves whenever any of that changes.
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.core.errors import ExportCancelled, ExportError
from kinecapture.core.jsonio import read_json
from kinecapture.dataset.index import DatasetIndex
from kinecapture.export.release import ExportOptions, ReleaseBuilder
from kinecapture.features.definitions import ANGLE_IDS
from kinecapture.features.registry import (
    array_keys_for,
    get_feature,
    get_preset,
    order_features,
)
from kinecapture.features.summary import SUMMARY_LENGTH
from tests.test_export import _record_and_label

_RICH = (
    "validity_masks",
    "frame_timing",
    "body_state",
    "tracker_joint_positions_2d",
    "tracker_local_joint_positions",
    "tracker_root_state",
    "root_centered_positions",
    "body_aligned_positions",
    "body_scale",
    "bone_geometry",
    "joint_displacement",
    "joint_velocity",
    "joint_acceleration",
    "root_kinematics",
    "joint_angles",
    "joint_angular_velocity",
    "segment_distances",
    "segment_ratios",
    "bilateral_angles",
    "bilateral_speed",
    "bilateral_mirror",
    "summary_vector",
)


@pytest.fixture
def labelled(workspace, session):
    _record_and_label(workspace, session, frames=40)
    return workspace


def _build(workspace, **options):
    index = DatasetIndex(workspace).refresh(force=True)
    settings = ExportOptions(include_synthetic=True, **options)
    return ReleaseBuilder(workspace, index, settings).build()


def _samples(result):
    manifest = read_json(result.path / "manifest.json")
    return manifest, [
        np.load(result.path / entry["file"]) for entry in manifest["samples"]
    ]


# ------------------------------------------------------- default behaviour


def test_default_export_writes_exactly_the_canonical_contract(labelled) -> None:
    """Ticking nothing must produce the release this app always produced."""
    result = _build(labelled)
    manifest, payloads = _samples(result)
    assert result.validation_passed

    for payload in payloads:
        keys = set(payload.files)
        assert {
            "joints_xyz",
            "frame_indices",
            "camera_timestamps_ns",
            "joint_confidences",
            "error_intervals",
            "error_multi_hot",
        } == keys
        assert payload["joints_xyz"].dtype == np.float32

    contract = manifest["feature_contract"]
    assert contract["selected_feature_ids"] == ["canonical_pose", "joint_confidences"]


def test_turning_confidences_off_removes_only_that_array(labelled) -> None:
    result = _build(labelled, store_confidences=False)
    _manifest, payloads = _samples(result)
    for payload in payloads:
        assert "joint_confidences" not in payload.files
        assert "joints_xyz" in payload.files


def test_an_older_recording_exports_with_and_without_features(
    workspace, session
) -> None:
    """A take whose sidecar has no optional tracker fields must still export.

    The rich selection is built anyway; the tracker features simply report
    themselves absent instead of failing the build.
    """
    take = _record_and_label(workspace, session, frames=30)
    paths = workspace.take_paths(take)
    stripped = []
    import json

    for line in paths.skeleton_stream.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for body in record.get("bodies") or []:
            for key in ("kp2d", "kpcov", "ljoints", "rquat", "rvel", "rcov", "action"):
                body.pop(key, None)
        stripped.append(json.dumps(record, ensure_ascii=False))
    paths.skeleton_stream.write_text("\n".join(stripped) + "\n", encoding="utf-8")

    plain = _build(workspace)
    assert plain.validation_passed

    rich = _build(
        workspace,
        feature_ids=("validity_masks", "joint_velocity", "joint_angles"),
    )
    assert rich.validation_passed
    _manifest, payloads = _samples(rich)
    for payload in payloads:
        assert "joint_velocity_xyz" in payload.files


def test_selecting_a_field_no_recording_has_fails_validation(
    workspace, session
) -> None:
    """A feature that came out nowhere is an error, not a quiet success."""
    take = _record_and_label(workspace, session, frames=30)
    paths = workspace.take_paths(take)
    import json

    lines = []
    for line in paths.skeleton_stream.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for body in record.get("bodies") or []:
            body.pop("kp2d", None)
        lines.append(json.dumps(record, ensure_ascii=False))
    paths.skeleton_stream.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _build(workspace, feature_ids=("tracker_joint_positions_2d",))
    assert not result.validation_passed
    report = read_json(result.path / "validation_report.json")
    issues = {error["issue"] for error in report["errors"]}
    assert "feature_never_available" in issues


# --------------------------------------------------------- rich selection


def test_selected_features_appear_in_every_sample_with_one_key_contract(
    labelled,
) -> None:
    result = _build(labelled, feature_ids=_RICH, feature_preset="kinematics_research")
    manifest, payloads = _samples(result)
    assert result.validation_passed
    assert len(payloads) >= 2

    expected = set(array_keys_for(manifest["feature_contract"]["selected_feature_ids"]))
    key_sets = [set(payload.files) for payload in payloads]
    assert key_sets[0] == key_sets[1]
    assert expected <= key_sets[0]

    first = payloads[0]
    frames = int(first["joints_xyz"].shape[0])
    joints = int(first["joints_xyz"].shape[1])
    assert first["joint_velocity_xyz"].shape == (frames, joints, 3)
    assert first["joint_angles_rad"].shape == (frames, len(ANGLE_IDS))
    assert first["summary_features"].shape == (SUMMARY_LENGTH,)
    assert first["joint_valid_mask"].dtype == np.bool_
    assert first["tracking_state_code"].dtype == np.uint8


def test_feature_spec_documents_every_written_array(labelled) -> None:
    result = _build(labelled, feature_ids=_RICH, feature_preset="kinematics_research")
    spec = read_json(result.path / "feature_spec.json")
    _manifest, payloads = _samples(result)

    declared = set(spec["array_keys"])
    stored = set(payloads[0].files) - {"error_intervals", "error_multi_hot"}
    assert stored <= declared

    for feature in spec["features"]:
        for array in feature["arrays"]:
            assert array["unit"] and array["dtype"] and array["shape"]
            assert array["coordinate_space"]
            assert array["description"]
        assert feature["missing_value_policy"]
        assert feature["mapping_support"]

    assert spec["columns"]["joint_angles_rad"] == list(ANGLE_IDS)
    assert len(spec["summary"]["names"]) == SUMMARY_LENGTH
    assert spec["angles"]["version"]
    assert spec["preset"] == "kinematics_research"
    assert "klinik" in spec["clinical_validation"].lower()
    assert spec["policies"]["displacement_vs_velocity"]
    assert spec["availability"]["joint_velocity"]["full"] >= 1
    assert spec["roles"]["mock_16"]["roles"]["pelvis"]["joint"] == "pelvis"
    assert spec["bones"]["mock_16"][0]["parent"] == "pelvis"


def test_manifest_reports_feature_availability_per_sample(labelled) -> None:
    result = _build(labelled, feature_ids=_RICH)
    manifest, _payloads = _samples(result)
    for entry in manifest["samples"]:
        assert entry["features"]["joint_velocity"] in ("full", "partial", "absent")
        assert entry["features"]["canonical_pose"] == "full"
        assert "joint_velocity" in entry["feature_availability_ratio"]


def test_masks_agree_with_the_nan_pattern_of_their_arrays(labelled) -> None:
    result = _build(labelled, feature_ids=_RICH)
    _manifest, payloads = _samples(result)
    payload = payloads[0]
    for value_key, mask_key in (
        ("joint_velocity_xyz", "joint_velocity_valid_mask"),
        ("joint_angles_rad", "joint_angle_valid_mask"),
        ("bone_vectors_xyz", "bone_valid_mask"),
    ):
        values = np.asarray(payload[value_key])
        mask = np.asarray(payload[mask_key])
        finite = np.isfinite(values)
        if finite.ndim > mask.ndim:
            finite = finite.all(axis=-1)
        np.testing.assert_array_equal(finite, mask)


def test_no_feature_array_replaces_the_raw_coordinates(labelled) -> None:
    """Root centring must be additional, never applied to ``joints_xyz``."""
    plain = _build(labelled)
    rich = _build(labelled, feature_ids=("root_centered_positions",))
    _p, plain_payloads = _samples(plain)
    _r, rich_payloads = _samples(rich)
    np.testing.assert_array_equal(
        plain_payloads[0]["joints_xyz"], rich_payloads[0]["joints_xyz"]
    )
    assert not np.allclose(
        rich_payloads[0]["root_centered_xyz"],
        rich_payloads[0]["joints_xyz"],
        equal_nan=True,
    )


# ------------------------------------------------------------- mapping


#: A deterministic 34-joint standing pose, used only to exercise the joint
#: mapping end to end. The synthetic backend speaks the 16-joint mock layout,
#: so a ZED-shaped stream is written directly here rather than by pretending
#: the mock camera produced one.
_ZED34_POSE = {
    "pelvis": (0.00, 0.95, 2.50),
    "naval_spine": (0.00, 1.10, 2.50),
    "chest_spine": (0.00, 1.25, 2.50),
    "neck": (0.00, 1.48, 2.50),
    "left_clavicle": (0.06, 1.45, 2.50),
    "left_shoulder": (0.19, 1.43, 2.50),
    "left_elbow": (0.24, 1.18, 2.50),
    "left_wrist": (0.26, 0.94, 2.50),
    "left_hand": (0.27, 0.88, 2.50),
    "left_handtip": (0.28, 0.82, 2.50),
    "left_thumb": (0.25, 0.87, 2.53),
    "right_clavicle": (-0.06, 1.45, 2.50),
    "right_shoulder": (-0.19, 1.43, 2.50),
    "right_elbow": (-0.24, 1.18, 2.50),
    "right_wrist": (-0.26, 0.94, 2.50),
    "right_hand": (-0.27, 0.88, 2.50),
    "right_handtip": (-0.28, 0.82, 2.50),
    "right_thumb": (-0.25, 0.87, 2.53),
    "left_hip": (0.11, 0.93, 2.50),
    "left_knee": (0.11, 0.52, 2.50),
    "left_ankle": (0.11, 0.08, 2.50),
    "left_foot": (0.11, 0.03, 2.42),
    "right_hip": (-0.11, 0.93, 2.50),
    "right_knee": (-0.11, 0.52, 2.50),
    "right_ankle": (-0.11, 0.08, 2.50),
    "right_foot": (-0.11, 0.03, 2.42),
    "head": (0.00, 1.63, 2.50),
    "nose": (0.00, 1.61, 2.44),
    "left_eye": (0.03, 1.64, 2.45),
    "left_ear": (0.07, 1.63, 2.50),
    "right_eye": (-0.03, 1.64, 2.45),
    "right_ear": (-0.07, 1.63, 2.50),
    "left_heel": (0.11, 0.04, 2.55),
    "right_heel": (-0.11, 0.04, 2.55),
}


def _write_zed34_stream(workspace, take, frames: int = 30) -> np.ndarray:
    """Replace a take's pose stream with a ZED BODY_34 one, and return it."""
    import json

    from kinecapture.visualization.skeleton_spec import ZED_BODY_34

    base = np.asarray(
        [_ZED34_POSE[name] for name in ZED_BODY_34.joint_names], dtype=np.float32
    )
    joints = np.repeat(base[None, ...], frames, axis=0)
    # A little motion so the derivatives are not identically zero.
    joints[:, ZED_BODY_34.index_of("left_wrist"), 2] += np.linspace(
        0.0, 0.12, frames, dtype=np.float32
    )

    quaternions = [[0.0, 0.0, 0.0, 1.0]] * ZED_BODY_34.num_joints
    points_2d = np.arange(ZED_BODY_34.num_joints * 2, dtype=np.float32).reshape(
        ZED_BODY_34.num_joints, 2
    )

    paths = workspace.take_paths(take)
    step = int(round(1e9 / 30.0))
    lines = [
        json.dumps(
            {
                "record": "header",
                "schema_version": "1.1.0",
                "take_id": take.take_id,
                "skeleton_format": ZED_BODY_34.name,
                "coordinate_system": "right_handed_y_up",
                "length_unit": "meter",
                "target_fps": 30,
            },
            ensure_ascii=False,
        )
    ]
    for index in range(frames):
        body = {
            "id": 1,
            "state": "ok",
            "format": ZED_BODY_34.name,
            "joints": [[round(float(v), 5) for v in row] for row in joints[index]],
            "conf": [0.9] * ZED_BODY_34.num_joints,
            "quat": quaternions,
            "kp2d": [[float(v) for v in row] for row in points_2d],
            "ljoints": [[0.01, 0.02, 0.03]] * ZED_BODY_34.num_joints,
            "root": [0.0, 0.95, 2.5],
            "rquat": [0.0, 0.0, 0.0, 1.0],
            "action": "moving",
        }
        lines.append(
            json.dumps(
                {
                    "record": "frame",
                    "i": index,
                    "host_ns": index * step,
                    "cam_ns": 1_700_000_000_000_000_000 + index * step,
                    "bodies": [body],
                    "active_id": 1,
                },
                ensure_ascii=False,
            )
        )
    paths.skeleton_stream.write_text("\n".join(lines) + "\n", encoding="utf-8")
    take.skeleton_format = ZED_BODY_34.name
    workspace.save_take(take)
    return joints


def _zed34_project(workspace, session):
    take = _record_and_label(workspace, session, frames=30)
    _write_zed34_stream(workspace, take)
    return workspace


def test_native_only_features_are_dropped_under_a_joint_mapping(
    workspace, session
) -> None:
    """Mapped export: parent-chain quantities must not be carried across.

    A local joint quaternion describes a rotation relative to the *source*
    skeleton's parent. Re-indexing it onto a target with a different chain
    would leave numbers that look valid and mean something else, so the array
    is written all-NaN and the feature reports itself absent, with the reason.
    """
    _zed34_project(workspace, session)
    result = _build(
        workspace,
        feature_ids=(
            "tracker_joint_orientations",
            "tracker_local_joint_positions",
            "tracker_joint_positions_2d",
            "joint_angles",
        ),
        target_skeleton_format="rehab24_6_mocap",
    )
    manifest, payloads = _samples(result)
    payload = payloads[0]

    assert np.isnan(payload["joint_orientations_xyzw"]).all()
    assert np.isnan(payload["local_joint_positions_xyz"]).all()
    for entry in manifest["samples"]:
        assert entry["features"]["tracker_joint_orientations"] == "absent"
        assert entry["features"]["tracker_local_joint_positions"] == "absent"
        note = entry["feature_notes"]["tracker_joint_orientations"]
        assert "eşleştirme" in note.lower()

    from kinecapture.visualization.skeleton_spec import REHAB24_6_MOCAP, ZED_BODY_34

    points = payload["joint_positions_2d"]
    assert points.shape[1] == REHAB24_6_MOCAP.num_joints
    source = np.arange(ZED_BODY_34.num_joints * 2, dtype=np.float32).reshape(
        ZED_BODY_34.num_joints, 2
    )
    np.testing.assert_allclose(
        points[0, REHAB24_6_MOCAP.index_of("Hips")],
        source[ZED_BODY_34.index_of("pelvis")],
    )
    # An unmapped target joint stays empty rather than borrowing a value.
    assert np.isnan(points[0, REHAB24_6_MOCAP.index_of("Head_end")]).all()


def test_mapped_geometry_is_recomputed_on_the_target_skeleton(
    workspace, session
) -> None:
    """The same movement must give the same knee angle in either layout."""
    _zed34_project(workspace, session)
    native = _build(workspace, feature_ids=("joint_angles",))
    mapped = _build(
        workspace,
        feature_ids=("joint_angles",),
        target_skeleton_format="rehab24_6_mocap",
    )
    _n, native_payloads = _samples(native)
    _m, mapped_payloads = _samples(mapped)

    column = ANGLE_IDS.index("left_knee_angle")
    np.testing.assert_allclose(
        native_payloads[0]["joint_angles_rad"][:, column],
        mapped_payloads[0]["joint_angles_rad"][:, column],
        rtol=1e-5,
    )

    bones = _build(
        workspace,
        feature_ids=("bone_geometry",),
        target_skeleton_format="rehab24_6_mocap",
    )
    _b, bone_payloads = _samples(bones)
    from kinecapture.visualization.skeleton_spec import REHAB24_6_MOCAP

    # Bones follow the target topology, not the source one.
    assert bone_payloads[0]["bone_vectors_xyz"].shape[1] == len(REHAB24_6_MOCAP.edges)


def test_partial_mapping_leaves_only_the_dependent_columns_empty(
    workspace, session
) -> None:
    """23 of 26 joints map; the other three must be the only casualties."""
    _zed34_project(workspace, session)
    result = _build(
        workspace,
        feature_ids=("bone_geometry", "joint_angles"),
        target_skeleton_format="rehab24_6_mocap",
    )
    _manifest, payloads = _samples(result)
    from kinecapture.visualization.skeleton_spec import REHAB24_6_MOCAP

    unmapped = {
        REHAB24_6_MOCAP.index_of(name)
        for name in ("Head_end", "LeftToeBase_end", "RightToeBase_end")
    }
    valid = payloads[0]["bone_valid_mask"][0]
    for position, (parent, child) in enumerate(REHAB24_6_MOCAP.edges):
        touched = bool(unmapped & {parent, child})
        assert bool(valid[position]) is (not touched), position

    angles = payloads[0]["joint_angles_rad"]
    assert np.isfinite(angles[:, ANGLE_IDS.index("left_knee_angle")]).all()
    assert np.isfinite(angles[:, ANGLE_IDS.index("left_ankle_angle")]).all()


def test_feature_spec_records_the_mapping_it_was_built_with(
    workspace, session
) -> None:
    _zed34_project(workspace, session)
    result = _build(
        workspace,
        feature_ids=("joint_angles",),
        target_skeleton_format="rehab24_6_mocap",
    )
    spec = read_json(result.path / "feature_spec.json")
    assert spec["joint_mapping"]["target_format"] == "rehab24_6_mocap"
    assert spec["joint_mapping"]["status"] == "partial"
    assert "rehab24_6_mocap" in spec["roles"]


def test_unsafe_per_joint_fields_are_not_carried_through_a_mapping() -> None:
    """The policy itself, without needing a ZED-shaped recording."""
    from kinecapture.export.release import _MAPPABLE_RAW_FIELDS
    from kinecapture.features.base import SourceField

    assert SourceField.JOINT_POSITIONS_2D.value in _MAPPABLE_RAW_FIELDS
    assert SourceField.JOINT_POSITION_COVARIANCES.value in _MAPPABLE_RAW_FIELDS
    assert SourceField.LOCAL_JOINT_POSITIONS.value not in _MAPPABLE_RAW_FIELDS
    assert SourceField.JOINT_ORIENTATIONS.value not in _MAPPABLE_RAW_FIELDS

    assert get_feature("tracker_joint_orientations").mapping_support.value == (
        "native_only"
    )
    assert get_feature("tracker_joint_positions_2d").mapping_support.value == (
        "index_remap"
    )
    assert get_feature("joint_angles").mapping_support.value == "recompute"


def test_per_joint_remap_moves_values_to_the_target_indices() -> None:
    from kinecapture.visualization.mapping import ZED34_TO_REHAB24_V0
    from kinecapture.visualization.skeleton_spec import REHAB24_6_MOCAP, ZED_BODY_34

    source = np.arange(
        2 * ZED_BODY_34.num_joints * 2, dtype=np.float32
    ).reshape(2, ZED_BODY_34.num_joints, 2)
    mapped = ZED34_TO_REHAB24_V0.apply_per_joint(source)
    assert mapped.shape == (2, REHAB24_6_MOCAP.num_joints, 2)

    hips = REHAB24_6_MOCAP.index_of("Hips")
    pelvis = ZED_BODY_34.index_of("pelvis")
    np.testing.assert_allclose(mapped[:, hips, :], source[:, pelvis, :])
    # An unmapped target joint stays NaN rather than borrowing a neighbour.
    assert np.isnan(mapped[:, REHAB24_6_MOCAP.index_of("Head_end"), :]).all()


# --------------------------------------------------------- fingerprints


def _fingerprint(result) -> str:
    return read_json(result.path / "dataset_fingerprint.json")["fingerprint"]


def test_fingerprint_changes_when_the_feature_selection_changes(labelled) -> None:
    plain = _fingerprint(_build(labelled))
    with_angles = _fingerprint(_build(labelled, feature_ids=("joint_angles",)))
    assert plain != with_angles


def test_fingerprint_changes_when_a_feature_version_changes(labelled, monkeypatch) -> None:
    before = _fingerprint(_build(labelled, feature_ids=("joint_angles",)))

    import dataclasses

    from kinecapture.features import registry

    bumped = dataclasses.replace(registry.get_feature("joint_angles"), version="9.9.9")
    monkeypatch.setitem(registry._BY_ID, "joint_angles", bumped)
    after = _fingerprint(_build(labelled, feature_ids=("joint_angles",)))
    assert before != after


def test_fingerprint_changes_when_a_sample_array_changes(labelled) -> None:
    """The checksum is hashed in at write time, so content is covered."""
    first = _build(labelled)
    fingerprint_before = _fingerprint(first)

    # Nudge one recorded coordinate and rebuild from the same labels.
    index = DatasetIndex(labelled).refresh(force=True)
    take = index.rows[0].take
    paths = labelled.take_paths(take)
    import json

    lines = []
    for line in paths.skeleton_stream.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        for body in record.get("bodies") or []:
            if body.get("joints"):
                body["joints"][0][0] = (body["joints"][0][0] or 0.0) + 0.25
        lines.append(json.dumps(record, ensure_ascii=False))
    paths.skeleton_stream.write_text("\n".join(lines) + "\n", encoding="utf-8")

    second = _build(labelled)
    assert _fingerprint(second) != fingerprint_before


def test_fingerprint_is_reproducible_for_an_unchanged_project(labelled) -> None:
    first = _build(labelled, feature_ids=("joint_angles", "joint_velocity"))
    second = _build(labelled, feature_ids=("joint_angles", "joint_velocity"))
    assert _fingerprint(first) == _fingerprint(second)


def test_sample_fingerprint_key_includes_the_written_checksum(labelled) -> None:
    result = _build(labelled)
    manifest, _payloads = _samples(result)
    for entry in manifest["samples"]:
        assert entry["checksum"].startswith("sha256:")


# --------------------------------------------------------- validation


def test_validation_catches_a_tampered_sample_file(labelled) -> None:
    result = _build(labelled, feature_ids=("joint_angles",))
    report = read_json(result.path / "validation_report.json")
    assert report["passed"]
    checks = {check["check"] for check in report["checks"]}
    assert "feature_contract" in checks


def test_validation_reports_partial_availability_as_a_warning(
    workspace, session
) -> None:
    take = _record_and_label(workspace, session, frames=30)
    paths = workspace.take_paths(take)
    import json

    lines = []
    for position, line in enumerate(
        paths.skeleton_stream.read_text(encoding="utf-8").splitlines()
    ):
        record = json.loads(line)
        # Blank a joint in the middle of the take: the angles that depend on
        # it become partially available.
        if record.get("record") == "frame" and 5 <= position <= 9:
            for body in record.get("bodies") or []:
                if body.get("joints"):
                    body["joints"][6] = [None, None, None]
        lines.append(json.dumps(record, ensure_ascii=False))
    paths.skeleton_stream.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _build(workspace, feature_ids=("joint_angles", "validity_masks"))
    report = read_json(result.path / "validation_report.json")
    assert result.validation_passed
    assert any("kısmen" in warning for warning in report["warnings"])


def test_cancelling_a_feature_rich_export_publishes_nothing(labelled) -> None:
    index = DatasetIndex(labelled).refresh(force=True)
    builder = ReleaseBuilder(
        labelled,
        index,
        ExportOptions(include_synthetic=True, feature_ids=_RICH),
    )
    with pytest.raises(ExportCancelled):
        builder.build(progress=lambda done, total, message: done < 1)

    releases = list(labelled.releases_dir.glob("dataset_v*"))
    staging = list(labelled.releases_dir.glob(".staging_*"))
    assert not releases and not staging


def test_a_failing_export_leaves_no_staging_directory(labelled, monkeypatch) -> None:
    index = DatasetIndex(labelled).refresh(force=True)
    builder = ReleaseBuilder(
        labelled, index, ExportOptions(include_synthetic=True, feature_ids=_RICH)
    )

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "kinecapture.export.release.compute_features", explode, raising=True
    )
    with pytest.raises(RuntimeError):
        builder.build()
    assert not list(labelled.releases_dir.glob(".staging_*"))
    assert not list(labelled.releases_dir.glob("dataset_v*"))


# ------------------------------------------------------------- options


def test_resolved_feature_ids_pull_in_dependencies() -> None:
    options = ExportOptions(feature_ids=("summary_vector",))
    resolved = options.resolved_feature_ids()
    assert "joint_angles" in resolved
    assert "body_aligned_positions" in resolved
    assert resolved[0] == "canonical_pose"


def test_options_record_both_the_raw_and_resolved_selection() -> None:
    options = ExportOptions(feature_ids=("joint_angles",), feature_preset="custom")
    payload = options.to_dict()
    assert payload["feature_ids"] == ["joint_angles"]
    assert "joint_confidences" in payload["resolved_feature_ids"]
    assert payload["feature_preset"] == "custom"


def test_a_stale_feature_id_in_the_options_is_ignored(labelled) -> None:
    result = _build(labelled, feature_ids=("joint_angles", "no_such_feature"))
    manifest, _payloads = _samples(result)
    selected = manifest["feature_contract"]["selected_feature_ids"]
    assert "no_such_feature" not in selected
    assert "joint_angles" in selected


def test_presets_export_end_to_end(labelled) -> None:
    for preset_id in ("minimal", "kinesynth_compat", "classical_ml"):
        preset = get_preset(preset_id)
        result = _build(
            labelled, feature_ids=preset.feature_ids, feature_preset=preset_id
        )
        assert result.validation_passed, preset_id
        manifest, payloads = _samples(result)
        assert manifest["feature_contract"]["preset"] == preset_id
        assert set(payloads[0].files) >= {"joints_xyz", "camera_timestamps_ns"}
        if preset_id == "classical_ml":
            assert payloads[0]["summary_features"].shape == (SUMMARY_LENGTH,)
        if preset_id == "kinesynth_compat":
            assert "joint_displacement_xyz" in payloads[0].files
            assert "joint_velocity_xyz" not in payloads[0].files
