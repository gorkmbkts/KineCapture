"""Node-level evidence in the release: what a graph-temporal model trains on.

The point of this contract is that a downstream loader can build a node
relevance target **without inferring anything**. So these tests do what such a
loader would: read the arrays, read the mapping, and check that the two agree
with the annotation a coach actually made - including the three different ways
of saying "no joints", which must never become "every node is negative".
"""

from __future__ import annotations

import numpy as np
import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.capture.service import CaptureService
from kinecapture.core.jsonio import read_json_mapping as read_json
from kinecapture.dataset.index import DatasetIndex
from kinecapture.domain.enums import JointAnnotationStatus, TakeQuality
from kinecapture.export.release import ExportOptions, ReleaseBuilder
from kinecapture.features.roles import ALL_ROLES
from kinecapture.playback.take_reader import load_take
from tests.conftest import paced_backend, record_take

CLASS_A = "diz-ice-cokuyor"
CLASS_B = "sirt-yuvarlaniyor"


@pytest.fixture
def annotated(workspace, session):
    """One take whose intervals cover all four joint annotation states."""
    schema = workspace.label_schema
    schema.add_exercise("Squat")
    schema.add_error_type("Diz içe çöküyor")
    schema.add_error_type("Sırt yuvarlanıyor")
    workspace.save_label_schema(schema)

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=90, exercise="squat")
    service.shutdown()
    take.quality = TakeQuality.GOOD
    workspace.save_take(take)

    loaded = load_take(workspace, take, with_video=False)
    repo = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    spec = loaded.spec

    sample = repo.create_sample(2, 80)
    repo.label_sample(sample.sample_id, exercise="squat", reviewed=True)

    # 1. Two joints, one class.
    first = repo.create_error_interval(sample.sample_id, 10, 20, error_code=CLASS_A)
    repo.update_error_interval(
        sample.sample_id,
        first.interval_id,
        joint_status=JointAnnotationStatus.SELECTED,
        affected_roles=["left_knee", "right_knee"],
        skeleton_spec=spec,
    )
    # 2. Overlapping, different class, one joint.
    second = repo.create_error_interval(sample.sample_id, 16, 30, error_code=CLASS_B)
    repo.update_error_interval(
        sample.sample_id,
        second.interval_id,
        joint_status=JointAnnotationStatus.SELECTED,
        affected_roles=["chest"],
        skeleton_spec=spec,
    )
    # 3. Same class again later, explicitly not about one joint.
    third = repo.create_error_interval(sample.sample_id, 40, 50, error_code=CLASS_A)
    repo.update_error_interval(
        sample.sample_id,
        third.interval_id,
        joint_status=JointAnnotationStatus.NOT_APPLICABLE,
    )
    # 4. Cannot be told from the footage.
    fourth = repo.create_error_interval(sample.sample_id, 55, 62, error_code=CLASS_B)
    repo.update_error_interval(
        sample.sample_id,
        fourth.interval_id,
        joint_status=JointAnnotationStatus.INDETERMINATE,
    )
    # 5. Never reviewed for joints - the state every older interval is in.
    repo.create_error_interval(sample.sample_id, 66, 74, error_code=CLASS_A)
    repo.save()
    return workspace, take, spec


@pytest.fixture
def release(annotated):
    workspace, _take, spec = annotated
    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index, ExportOptions(include_synthetic=True)
    ).build()
    manifest = read_json(result.path / "manifest.json")
    payload = np.load(
        next((result.path / "samples").glob("*.npz")), allow_pickle=False
    )
    return result, manifest, payload, spec


# ------------------------------------------------------------ round trip


def test_multi_joint_selection_survives_the_round_trip(release) -> None:
    _result, manifest, payload, _spec = release
    entry = manifest["samples"][0]
    by_class: dict[str, list] = {}
    for interval in entry["error_intervals"]:
        by_class.setdefault(interval["error_code"], []).append(interval)

    first = min(by_class[CLASS_A], key=lambda i: i["relative_start"])
    assert first["affected_roles"] == ["left_knee", "right_knee"], (
        "order is ALL_ROLES order, so two annotators produce identical files"
    )
    assert first["joint_status"] == "selected"
    assert first["has_node_supervision"] is True

    chest = by_class[CLASS_B][0]
    assert chest["affected_roles"] == ["chest"]


def test_every_status_reaches_the_manifest_distinctly(release) -> None:
    _result, manifest, _payload, _spec = release
    statuses = {
        interval["joint_status"]
        for interval in manifest["samples"][0]["error_intervals"]
    }
    assert statuses == {
        "selected",
        "not_applicable",
        "indeterminate",
        "unreviewed",
    }, "the four meanings must stay four meanings"


# --------------------------------------------------- interval-space arrays


def test_the_interval_arrays_line_up_with_the_manifest(release) -> None:
    _result, manifest, payload, _spec = release
    intervals = manifest["samples"][0]["error_intervals"]

    multi_hot = payload["error_interval_joint_multi_hot"]
    mask = payload["error_interval_joint_mask"]
    status = payload["error_interval_joint_status"]

    assert multi_hot.shape == (len(intervals), len(ALL_ROLES))
    assert multi_hot.dtype == np.uint8
    assert mask.shape == (len(intervals),)
    assert status.shape == (len(intervals),)

    index = {role: column for column, role in enumerate(ALL_ROLES)}
    codes = manifest["label_contract"]["joint_evidence"]["status_codes"]
    for row, interval in enumerate(intervals):
        expected = {index[role] for role in interval["affected_roles"]}
        assert set(np.flatnonzero(multi_hot[row]).tolist()) == expected
        assert bool(mask[row]) is bool(interval["has_node_supervision"])
        assert int(status[row]) == codes[interval["joint_status"]]


def test_an_unreviewed_interval_is_masked_not_negative(release) -> None:
    """The whole point of the mask: silence is not a negative label."""
    _result, manifest, payload, _spec = release
    intervals = manifest["samples"][0]["error_intervals"]
    multi_hot = payload["error_interval_joint_multi_hot"]
    mask = payload["error_interval_joint_mask"]

    for row, interval in enumerate(intervals):
        if interval["joint_status"] in (
            "unreviewed",
            "not_applicable",
            "indeterminate",
        ):
            assert mask[row] == 0, "not supervision"
            assert multi_hot[row].sum() == 0
        else:
            assert mask[row] == 1


# ------------------------------------------------------ dense node target


def test_the_dense_target_matches_the_intervals_frame_by_frame(release) -> None:
    _result, manifest, payload, _spec = release
    entry = manifest["samples"][0]
    evidence = manifest["label_contract"]["joint_evidence"]
    role_to_node = evidence["role_to_native_node"][entry["skeleton_format"]]

    target = payload["error_joint_target"]
    label_mask = payload["error_joint_label_mask"]
    frames = entry["num_frames"]
    classes = len(manifest["label_contract"]["error_classes"])
    joints = entry["num_joints"]

    assert target.shape == (frames, classes, joints)
    assert label_mask.shape == (frames, classes)
    assert target.dtype == np.uint8 and label_mask.dtype == np.uint8

    # Rebuild exactly what the documented recipe says, then compare.
    expected = np.zeros_like(target)
    expected_mask = np.zeros_like(label_mask)
    for interval in entry["error_intervals"]:
        if not interval["has_node_supervision"]:
            continue
        column = interval["class_index"]
        low, high = interval["relative_start"], interval["relative_end"] + 1
        expected_mask[low:high, column] = 1
        for role in interval["affected_roles"]:
            node = role_to_node[role]
            if node is not None:
                expected[low:high, column, node] = 1

    assert np.array_equal(target, expected)
    assert np.array_equal(label_mask, expected_mask)


def test_masked_frames_carry_no_positive_target(release) -> None:
    _result, _manifest, payload, _spec = release
    target = payload["error_joint_target"]
    mask = payload["error_joint_label_mask"]
    unmasked = target[mask == 0]
    assert unmasked.size == 0 or unmasked.max() == 0, (
        "a frame/class with no supervision must not claim node evidence"
    )


def test_overlapping_classes_keep_their_own_joints(release) -> None:
    """Two errors at one instant must not blur into one joint set."""
    _result, manifest, payload, _spec = release
    entry = manifest["samples"][0]
    evidence = manifest["label_contract"]["joint_evidence"]
    role_to_node = evidence["role_to_native_node"][entry["skeleton_format"]]
    classes = manifest["label_contract"]["error_classes"]
    target = payload["error_joint_target"]

    a, b = classes.index(CLASS_A), classes.index(CLASS_B)
    # Frame 18 (relative) sits inside both the knee interval and the chest one.
    overlap = 18 - entry["start_position"]
    knee_nodes = {role_to_node["left_knee"], role_to_node["right_knee"]}
    assert set(np.flatnonzero(target[overlap, a]).tolist()) == knee_nodes
    assert set(np.flatnonzero(target[overlap, b]).tolist()) == {
        role_to_node["chest"]
    }


def test_inclusive_bounds_at_both_ends(release) -> None:
    _result, manifest, payload, _spec = release
    entry = manifest["samples"][0]
    classes = manifest["label_contract"]["error_classes"]
    mask = payload["error_joint_label_mask"]

    interval = min(
        (i for i in entry["error_intervals"] if i["has_node_supervision"]),
        key=lambda i: i["relative_start"],
    )
    column = classes.index(interval["error_code"])
    low, high = interval["relative_start"], interval["relative_end"]
    assert mask[low, column] == 1, "the first frame is included"
    assert mask[high, column] == 1, "and so is the last"
    if low > 0:
        assert mask[low - 1, column] == 0
    if high + 1 < mask.shape[0]:
        assert mask[high + 1, column] == 0


# ------------------------------------------------------------- the mapping


def test_the_role_mapping_is_published_and_deterministic(release) -> None:
    _result, manifest, _payload, spec = release
    evidence = manifest["label_contract"]["joint_evidence"]

    assert evidence["roles"] == list(ALL_ROLES)
    assert evidence["role_mapping_version"]
    assert "features.roles" in evidence["role_mapping_source"]

    table = evidence["role_to_native_node"][spec.name]
    # Every published node index is real, and every role appears exactly once.
    assert set(table) == set(ALL_ROLES)
    for role, node in table.items():
        assert node is None or 0 <= node < spec.num_joints
        if node is not None:
            assert spec.joint_names[node]


def test_the_contract_says_it_keeps_every_native_node(release) -> None:
    """The supervision is about *which* nodes matter, not which ones survive."""
    _result, manifest, payload, spec = release
    evidence = manifest["label_contract"]["joint_evidence"]
    assert "DEĞİLDİR" in evidence["purpose"], "not a joint classifier product"
    assert "joints_xyz" in evidence["purpose"]
    assert payload["joints_xyz"].shape[1] == spec.num_joints, (
        "no joint is dropped from the model input"
    )


def test_the_recipe_is_documented_well_enough_to_follow(release) -> None:
    _result, manifest, _payload, _spec = release
    evidence = manifest["label_contract"]["joint_evidence"]
    recipe = evidence["dense_target_recipe"]
    for token in (
        "error_joint_target",
        "error_interval_joint_mask",
        "role_to_native_node",
        "error_joint_label_mask",
    ):
        assert token in recipe
    meanings = evidence["status_meaning"]
    assert set(meanings) == {
        "selected",
        "not_applicable",
        "indeterminate",
        "unreviewed",
    }
    assert "MASKELEN" in meanings["unreviewed"]
    assert "ETKİLENMEZ" in meanings["unreviewed"]


# ------------------------------------------------------------- validation


def test_the_release_validates(release) -> None:
    result, _manifest, _payload, _spec = release
    assert result.validation_passed, result.validation


def test_the_validator_rejects_a_corrupt_joint_annotation(release) -> None:
    """A status that disagrees with its own roles must not ship.

    Driven through a real manifest entry rather than a hand-built one, so the
    validator is exercised exactly as it runs during a build.
    """
    result, manifest, _payload, _spec = release
    builder = ReleaseBuilder(None, None, ExportOptions())  # validation only

    entry = dict(manifest["samples"][0])
    corruptions = [
        {"affected_roles": ["left_knee"], "joint_status": "not_applicable",
         "has_node_supervision": False},
        {"affected_roles": [], "joint_status": "selected",
         "has_node_supervision": True},
        {"affected_roles": ["left_kneecap"], "joint_status": "selected",
         "has_node_supervision": True},
        {"affected_roles": ["left_knee"], "joint_status": "moon_phase",
         "has_node_supervision": True},
    ]
    intervals = []
    for original, damage in zip(entry["error_intervals"], corruptions):
        broken = dict(original)
        broken.update(damage)
        intervals.append(broken)
    assert len(intervals) == len(corruptions), "fixture needs four intervals"
    entry["error_intervals"] = intervals
    report = builder._validate(
        result.path, [entry], [], list(manifest["label_contract"]["error_classes"])
    )
    issues = {problem["issue"] for problem in report["errors"]}
    assert "roles_without_selected_status" in issues
    assert "selected_without_roles" in issues
    assert "unknown_anatomical_role" in issues
    assert "unknown_joint_status" in issues
    assert not report["passed"]


# ----------------------------------------------------------- fingerprint


def test_changing_the_affected_joints_changes_the_fingerprint(annotated) -> None:
    """An old release must not be reused after the joint labels change."""
    workspace, take, spec = annotated

    def build() -> str:
        index = DatasetIndex(workspace).refresh(force=True)
        result = ReleaseBuilder(
            workspace, index, ExportOptions(include_synthetic=True)
        ).build()
        return read_json(result.path / "dataset_fingerprint.json")["fingerprint"]

    before = build()

    loaded = load_take(workspace, take, with_video=False)
    repo = AnnotationRepository(workspace, take, frame_count=loaded.frame_count)
    sample = repo.samples[0]
    interval = min(sample.error_intervals, key=lambda i: i.start_frame)
    repo.update_error_interval(
        sample.sample_id,
        interval.interval_id,
        joint_status=JointAnnotationStatus.SELECTED,
        affected_roles=["left_knee"],  # was left_knee + right_knee
        skeleton_spec=spec,
    )
    repo.save()

    assert build() != before
