"""ZED body-data conversion, exercised without hardware.

``ZedCameraBackend._retrieve_bodies`` is the riskiest few lines in the project:
it turns SDK objects into domain objects, and a mistake there corrupts every
recorded joint without raising anything. A live camera only exercises it when a
person is actually standing in front of the lens, which no automated test can
arrange.

So the conversion is tested here against stub objects shaped like the SDK's,
covering the parts that would silently produce wrong data:

* confidence is rescaled from the SDK's 0..100 to the domain's 0..1;
* a body whose joint count disagrees with the configured body format is
  **dropped, not reshaped** - reshaping would silently re-index every joint;
* the SDK tracking-state enum is mapped explicitly, not assumed to match;
* missing joints stay non-finite.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.domain.enums import TrackingState
from kinecapture.visualization.skeleton_spec import ZED_BODY_34


class _FakeBodies:
    def __init__(self, body_list):
        self.body_list = body_list


def _fake_body(
    *,
    tracking_id: int = 1,
    joints: np.ndarray | None = None,
    confidences: np.ndarray | None = None,
    orientations: np.ndarray | None = None,
    state_name: str = "OK",
    confidence: float = 88.0,
):
    count = ZED_BODY_34.num_joints
    if joints is None:
        joints = np.arange(count * 3, dtype=np.float32).reshape(count, 3) / 100.0
    if confidences is None:
        confidences = np.full(count, 75.0, dtype=np.float32)
    if orientations is None:
        orientations = np.zeros((count, 4), dtype=np.float32)
    return SimpleNamespace(
        id=tracking_id,
        keypoint=joints,
        keypoint_confidence=confidences,
        local_orientation_per_joint=orientations,
        position=np.array([0.1, 0.9, 2.4], dtype=np.float32),
        tracking_state=SimpleNamespace(name=state_name),
        confidence=confidence,
    )


@pytest.fixture
def backend() -> ZedCameraBackend:
    """A backend wired to BODY_34 without opening any hardware."""
    instance = ZedCameraBackend()
    instance._spec = ZED_BODY_34
    instance._body_tracking_enabled = True
    instance._body_runtime = SimpleNamespace(detection_confidence_threshold=40)
    return instance


class _Camera:
    def __init__(self, bodies):
        self._bodies = bodies

    def retrieve_bodies(self, target, runtime):  # noqa: ARG002
        target.body_list = self._bodies.body_list


def _convert(backend: ZedCameraBackend, bodies):
    backend._bodies = _FakeBodies([])
    return backend._retrieve_bodies(object(), _Camera(_FakeBodies(bodies)))


def test_confidence_is_rescaled_to_unit_range(backend) -> None:
    """The SDK reports 0..100; the domain contract is 0..1."""
    poses = _convert(backend, [_fake_body()])
    assert len(poses) == 1
    np.testing.assert_allclose(poses[0].joint_confidences, 0.75, atol=1e-6)
    assert poses[0].mean_confidence() == pytest.approx(0.75)


def test_joints_are_copied_verbatim(backend) -> None:
    count = ZED_BODY_34.num_joints
    joints = np.random.default_rng(0).normal(size=(count, 3)).astype(np.float32)
    poses = _convert(backend, [_fake_body(joints=joints)])
    np.testing.assert_array_equal(poses[0].joint_positions_xyz, joints)
    assert poses[0].body_format == "zed_body_34"
    assert poses[0].num_joints == count


def test_wrong_joint_count_is_dropped_not_reshaped(backend) -> None:
    """A format mismatch must lose the body, never silently re-index it."""
    wrong = np.zeros((18, 3), dtype=np.float32)
    poses = _convert(
        backend,
        [_fake_body(joints=wrong, confidences=np.full(18, 50.0, dtype=np.float32))],
    )
    assert poses == ()


def test_mismatched_confidence_length_becomes_nan(backend) -> None:
    """Unknown confidence is NaN, never a fabricated default."""
    poses = _convert(
        backend, [_fake_body(confidences=np.full(5, 50.0, dtype=np.float32))]
    )
    assert len(poses) == 1
    assert np.isnan(poses[0].joint_confidences).all()


def test_missing_joints_stay_non_finite(backend) -> None:
    count = ZED_BODY_34.num_joints
    joints = np.zeros((count, 3), dtype=np.float32)
    joints[7] = np.nan
    poses = _convert(backend, [_fake_body(joints=joints)])
    assert not poses[0].valid_joint_mask[7]
    assert poses[0].valid_joint_ratio == pytest.approx((count - 1) / count)


@pytest.mark.parametrize(
    "sdk_name,expected",
    [
        ("OK", TrackingState.OK),
        ("SEARCHING", TrackingState.SEARCHING),
        ("OFF", TrackingState.OFF),
        ("TERMINATE", TrackingState.TERMINATE),
        ("OBJECT_TRACKING_STATE.OK", TrackingState.OK),
        ("SOMETHING_NEW", TrackingState.OFF),  # unknown maps to a safe value
    ],
)
def test_tracking_state_mapping_is_explicit(backend, sdk_name, expected) -> None:
    poses = _convert(backend, [_fake_body(state_name=sdk_name)])
    assert poses[0].tracking_state is expected


def test_orientations_are_kept_when_well_shaped(backend) -> None:
    count = ZED_BODY_34.num_joints
    orientations = np.tile(np.array([0, 0, 0, 1], dtype=np.float32), (count, 1))
    poses = _convert(backend, [_fake_body(orientations=orientations)])
    assert poses[0].joint_orientations is not None
    assert poses[0].joint_orientations.shape == (count, 4)


def test_badly_shaped_orientations_are_discarded(backend) -> None:
    poses = _convert(
        backend, [_fake_body(orientations=np.zeros((3, 4), dtype=np.float32))]
    )
    assert poses[0].joint_orientations is None


def test_multiple_bodies_are_all_converted(backend) -> None:
    poses = _convert(
        backend, [_fake_body(tracking_id=3), _fake_body(tracking_id=9)]
    )
    assert {p.tracking_id for p in poses} == {3, 9}


def test_no_bodies_yields_empty_tuple(backend) -> None:
    assert _convert(backend, []) == ()


def test_body_tracking_disabled_yields_nothing() -> None:
    instance = ZedCameraBackend()
    instance._body_tracking_enabled = False
    assert instance._retrieve_bodies(object(), _Camera(_FakeBodies([]))) == ()


def test_recorded_body_survives_the_sidecar_roundtrip(backend) -> None:
    """The conversion output must round-trip through skeleton.jsonl unchanged."""
    from kinecapture.domain.models import BodyPose

    count = ZED_BODY_34.num_joints
    joints = np.random.default_rng(1).normal(size=(count, 3)).astype(np.float32)
    joints[2] = np.nan
    poses = _convert(backend, [_fake_body(joints=joints, tracking_id=4)])
    restored = BodyPose.from_record(poses[0].to_record())

    assert restored.tracking_id == 4
    assert restored.body_format == "zed_body_34"
    assert restored.num_joints == count
    assert np.isnan(restored.joint_positions_xyz[2]).all()
    finite = np.isfinite(joints).all(axis=1)
    np.testing.assert_allclose(
        restored.joint_positions_xyz[finite], joints[finite], atol=1e-4
    )
