"""The optional tracker fields, from the SDK boundary to the sidecar and back.

These fields cannot be re-derived from coordinates later, so if they are lost
at capture time they are lost for good. The tests here cover the three places
that could lose them silently: the conversion out of the SDK's objects, the
JSON projection, and reading an older recording that never had them.

The rule everywhere is the same one: a field that is missing or the wrong shape
becomes *absent*, never a reshaped or padded value.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from kinecapture import SKELETON_STREAM_SCHEMA_VERSION
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import BodyActionState, TrackingState
from kinecapture.domain.models import BodyPose
from kinecapture.playback.take_reader import load_skeleton_stream
from kinecapture.visualization.skeleton_spec import MOCK_SKELETON, ZED_BODY_34


def _pose(**overrides) -> BodyPose:
    joints = MOCK_SKELETON.num_joints
    payload = {
        "tracking_id": 3,
        "tracking_state": TrackingState.OK,
        "body_format": MOCK_SKELETON.name,
        "joint_positions_xyz": np.arange(joints * 3, dtype=np.float32).reshape(
            joints, 3
        )
        / 10.0,
        "joint_confidences": np.full(joints, 0.8, dtype=np.float32),
    }
    payload.update(overrides)
    return BodyPose(**payload)


def _full_pose() -> BodyPose:
    joints = MOCK_SKELETON.num_joints
    return _pose(
        joint_orientations=np.tile(
            np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32), (joints, 1)
        ),
        joint_positions_2d=np.arange(joints * 2, dtype=np.float32).reshape(joints, 2),
        joint_position_covariances=np.full((joints, 6), 0.002, dtype=np.float32),
        local_joint_positions_xyz=np.full((joints, 3), 0.05, dtype=np.float32),
        root_position=np.asarray([0.1, 0.9, 2.4], dtype=np.float32),
        root_orientation=np.asarray([0.0, 0.7071, 0.0, 0.7071], dtype=np.float32),
        tracker_root_velocity_xyz=np.asarray([0.2, -0.1, 0.0], dtype=np.float32),
        root_position_covariance=np.arange(6, dtype=np.float32) / 1000.0,
        body_confidence=87.5,
        action_state=BodyActionState.MOVING,
    )


# --------------------------------------------------------------- round trip


def test_every_optional_field_survives_a_json_round_trip() -> None:
    pose = _full_pose()
    restored = BodyPose.from_record(json.loads(json.dumps(pose.to_record())))

    assert restored.available_fields() == pose.available_fields()
    assert restored.action_state is BodyActionState.MOVING
    for name in (
        "joint_orientations",
        "joint_positions_2d",
        "joint_position_covariances",
        "local_joint_positions_xyz",
        "root_position",
        "root_orientation",
        "tracker_root_velocity_xyz",
        "root_position_covariance",
    ):
        np.testing.assert_allclose(
            getattr(restored, name), getattr(pose, name), atol=1e-4
        )


def test_root_orientation_is_no_longer_dropped_by_serialisation() -> None:
    """It used to exist on the model and vanish on the way to disk."""
    pose = _pose(root_orientation=np.asarray([0.1, 0.2, 0.3, 0.9], dtype=np.float32))
    record = pose.to_record()
    assert "rquat" in record
    restored = BodyPose.from_record(record)
    assert restored.root_orientation is not None
    np.testing.assert_allclose(
        restored.root_orientation, pose.root_orientation, atol=1e-4
    )


def test_a_record_without_the_optional_fields_is_read_unchanged() -> None:
    """A v1 sidecar line: fewer keys, no migration, nothing invented."""
    legacy = {
        "id": 1,
        "state": "ok",
        "format": MOCK_SKELETON.name,
        "joints": [[0.0, 1.0, 2.0]] * MOCK_SKELETON.num_joints,
        "conf": [0.5] * MOCK_SKELETON.num_joints,
    }
    pose = BodyPose.from_record(legacy)
    assert pose.available_fields() == ()
    assert pose.action_state is BodyActionState.UNKNOWN
    assert pose.joint_positions_2d is None
    assert pose.root_orientation is None
    assert pose.num_joints == MOCK_SKELETON.num_joints


def test_optional_fields_are_omitted_when_absent() -> None:
    record = _pose().to_record()
    for key in ("kp2d", "kpcov", "ljoints", "rquat", "rvel", "rcov", "action"):
        assert key not in record


def test_missing_values_round_trip_as_nan_not_zero() -> None:
    joints = MOCK_SKELETON.num_joints
    points = np.full((joints, 2), np.nan, dtype=np.float32)
    points[0] = (12.0, 34.0)
    restored = BodyPose.from_record(_pose(joint_positions_2d=points).to_record())
    assert np.isnan(restored.joint_positions_2d[1:]).all()
    np.testing.assert_allclose(restored.joint_positions_2d[0], [12.0, 34.0])


@pytest.mark.parametrize(
    ("field", "shape"),
    [
        ("joint_positions_2d", (4, 2)),
        ("joint_position_covariances", (16, 5)),
        ("local_joint_positions_xyz", (16, 2)),
        ("root_orientation", (3,)),
        ("tracker_root_velocity_xyz", (4,)),
        ("root_position_covariance", (5,)),
    ],
)
def test_a_wrong_shape_is_refused_rather_than_reshaped(field, shape) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _pose(**{field: np.zeros(shape, dtype=np.float32)})
    assert excinfo.value.code == f"{field}_shape_invalid"


def test_a_record_whose_stored_shape_disagrees_drops_only_that_field() -> None:
    record = _full_pose().to_record()
    record["kp2d"] = [[1.0, 2.0], [3.0, 4.0]]  # too few rows for this skeleton
    pose = BodyPose.from_record(record)
    assert pose.joint_positions_2d is None
    # Everything else still arrived.
    assert pose.root_orientation is not None
    assert pose.local_joint_positions_xyz is not None


# ----------------------------------------------------------- ZED adapter


def _fake_zed_body(**overrides):
    count = ZED_BODY_34.num_joints
    payload = {
        "id": 2,
        "keypoint": np.zeros((count, 3), dtype=np.float32),
        "keypoint_confidence": np.full(count, 60.0, dtype=np.float32),
        "local_orientation_per_joint": np.tile(
            np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float32), (count, 1)
        ),
        "local_position_per_joint": np.full((count, 3), 0.01, dtype=np.float32),
        "keypoint_2d": np.arange(count * 2, dtype=np.float64).reshape(count, 2),
        "keypoints_covariance": np.full((count, 6), 0.003, dtype=np.float32),
        "position": np.asarray([0.0, 0.9, 2.0], dtype=np.float64),
        "global_root_orientation": np.asarray([0.0, 0.0, 0.0, 1.0], dtype=np.float64),
        "velocity": np.asarray([0.3, 0.0, -0.1], dtype=np.float64),
        "position_covariance": np.arange(6, dtype=np.float64),
        "tracking_state": SimpleNamespace(name="OK"),
        "action_state": SimpleNamespace(name="MOVING"),
        "confidence": 91.0,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _Bodies:
    def __init__(self, body_list):
        self.body_list = body_list


#: Minimal stand-in for the ``sl`` module. The adapter checks every retrieval
#: against ``sl.ERROR_CODE.SUCCESS``; handing it a bare ``object()`` would make
#: these tests pass through a code path the real SDK never takes.
_SL = SimpleNamespace(ERROR_CODE=SimpleNamespace(SUCCESS="SUCCESS"))


class _Camera:
    def __init__(self, bodies, status=_SL.ERROR_CODE.SUCCESS):
        self._bodies = bodies
        self._status = status

    def retrieve_bodies(self, target, runtime):  # noqa: ARG002
        target.body_list = self._bodies
        return self._status


@pytest.fixture
def zed_backend() -> ZedCameraBackend:
    backend = ZedCameraBackend()
    backend._spec = ZED_BODY_34
    backend._body_tracking_enabled = True
    backend._body_runtime = SimpleNamespace(detection_confidence_threshold=40)
    backend._bodies = _Bodies([])
    return backend


def _convert(backend, bodies):
    return backend._retrieve_bodies(_SL, _Camera(bodies))


def test_adapter_refuses_to_convert_a_failed_retrieval(zed_backend) -> None:
    """A failed retrieval must raise, never return the previous body list."""
    from kinecapture.core.errors import CameraError

    with pytest.raises(CameraError) as excinfo:
        zed_backend._retrieve_bodies(
            _SL, _Camera([_fake_zed_body()], status="CAMERA_NOT_DETECTED")
        )
    assert excinfo.value.code == "zed_retrieval_failed"


def test_adapter_carries_every_verified_sdk_field(zed_backend) -> None:
    poses = _convert(zed_backend, [_fake_zed_body()])
    assert len(poses) == 1
    pose = poses[0]
    assert pose.joint_positions_2d.shape == (ZED_BODY_34.num_joints, 2)
    assert pose.joint_positions_2d.dtype == np.float32
    assert pose.joint_position_covariances.shape == (ZED_BODY_34.num_joints, 6)
    assert pose.local_joint_positions_xyz.shape == (ZED_BODY_34.num_joints, 3)
    assert pose.root_orientation.shape == (4,)
    assert pose.tracker_root_velocity_xyz.shape == (3,)
    assert pose.root_position_covariance.shape == (6,)
    assert pose.action_state is BodyActionState.MOVING


def test_adapter_drops_a_field_the_body_format_does_not_produce(zed_backend) -> None:
    """Empty fitting arrays are normal for some body formats, not an error."""
    empty = np.zeros((0, 3), dtype=np.float32)
    poses = _convert(
        zed_backend,
        [_fake_zed_body(local_position_per_joint=empty, keypoint_2d=np.zeros((0, 2)))],
    )
    pose = poses[0]
    assert pose.local_joint_positions_xyz is None
    assert pose.joint_positions_2d is None
    # The joints themselves are untouched.
    assert pose.num_joints == ZED_BODY_34.num_joints


def test_adapter_drops_a_wrong_shaped_field_instead_of_reshaping(zed_backend) -> None:
    poses = _convert(
        zed_backend,
        [_fake_zed_body(keypoints_covariance=np.zeros((ZED_BODY_34.num_joints, 3)))],
    )
    assert poses[0].joint_position_covariances is None


def test_adapter_maps_an_unknown_action_state_to_unknown(zed_backend) -> None:
    poses = _convert(
        zed_backend, [_fake_zed_body(action_state=SimpleNamespace(name="LAST"))]
    )
    assert poses[0].action_state is BodyActionState.UNKNOWN


def test_adapter_handles_a_body_with_no_action_state_attribute(zed_backend) -> None:
    body = _fake_zed_body()
    del body.action_state
    poses = _convert(zed_backend, [body])
    assert poses[0].action_state is BodyActionState.UNKNOWN


# --------------------------------------------------------- mock backend


def test_mock_backend_emits_only_fields_it_can_honestly_derive() -> None:
    backend = MockCameraBackend(width=160, height=120, seed=7)
    backend.connect()
    backend.start_preview()
    backend.grab_frame()
    body = backend.grab_frame().bodies[0]

    # Derived from the backend's own geometry and motion model.
    assert np.isfinite(body.joint_positions_2d).any()
    assert np.isfinite(body.local_joint_positions_xyz).all()
    assert np.isfinite(body.tracker_root_velocity_xyz).all()
    assert body.action_state in (BodyActionState.IDLE, BodyActionState.MOVING)
    # Not modelled at all: NaN says "not measured" rather than faking one.
    assert np.isnan(body.joint_orientations).all()
    assert np.isnan(body.joint_position_covariances).all()
    assert np.isnan(body.root_orientation).all()
    backend.disconnect()


def test_mock_optional_fields_are_deterministic() -> None:
    def sample():
        backend = MockCameraBackend(width=160, height=120, seed=7)
        backend.connect()
        backend.start_preview()
        for _ in range(3):
            packet = backend.grab_frame()
        backend.disconnect()
        return packet.bodies[0]

    first, second = sample(), sample()
    np.testing.assert_array_equal(
        first.joint_positions_2d, second.joint_positions_2d
    )
    np.testing.assert_array_equal(
        first.local_joint_positions_xyz, second.local_joint_positions_xyz
    )
    np.testing.assert_array_equal(
        first.tracker_root_velocity_xyz, second.tracker_root_velocity_xyz
    )
    assert first.action_state is second.action_state


def test_mock_local_positions_are_parent_relative() -> None:
    backend = MockCameraBackend(width=160, height=120)
    backend.connect()
    backend.start_preview()
    body = backend.grab_frame().bodies[0]
    backend.disconnect()

    parents = {child: parent for parent, child in MOCK_SKELETON.edges}
    for child, parent in parents.items():
        expected = (
            body.joint_positions_xyz[child] - body.joint_positions_xyz[parent]
        )
        np.testing.assert_allclose(
            body.local_joint_positions_xyz[child], expected, atol=1e-5
        )
    np.testing.assert_allclose(
        body.local_joint_positions_xyz[MOCK_SKELETON.root_index], 0.0, atol=0
    )


# ------------------------------------------------------ recorded stream


def test_recorded_stream_carries_the_new_fields_and_declares_its_version(
    workspace, session, tmp_path
) -> None:
    from kinecapture.capture.service import CaptureService
    from tests.conftest import paced_backend, record_take

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=12)
    service.shutdown()

    stream = load_skeleton_stream(workspace.take_paths(take).skeleton_stream)
    assert stream.header["schema_version"] == SKELETON_STREAM_SCHEMA_VERSION

    tracking_id = stream.tracking_ids[0]
    names = stream.optional_field_names(tracking_id)
    assert "joint_positions_2d" in names
    assert "local_joint_positions_xyz" in names
    assert "tracker_root_velocity_xyz" in names

    points = stream.optional_body_array(tracking_id, "joint_positions_2d")
    assert points is not None
    assert points.shape == (stream.frame_count, MOCK_SKELETON.num_joints, 2)

    states = stream.body_state_arrays(tracking_id)
    assert states["body_present"].all()
    assert set(np.unique(states["action_state"])) <= {0, 1, 2}


def test_optional_array_is_none_when_no_frame_carries_it(
    workspace, session
) -> None:
    from kinecapture.capture.service import CaptureService
    from tests.conftest import paced_backend, record_take

    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=8)
    service.shutdown()

    stream = load_skeleton_stream(workspace.take_paths(take).skeleton_stream)
    tracking_id = stream.tracking_ids[0]
    # Nothing in this project records a field by this name.
    assert stream.optional_body_array(tracking_id, "not_a_field") is None
