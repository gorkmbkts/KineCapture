"""The subject lock: does it ever put the wrong person in the dataset?

Every test here is a rehearsal of a way that could happen. A physiotherapist
steps into frame; the participant walks out; the tracker recycles an id; two
people of similar build stand side by side. The product guarantee is not "the
person is always recognised" - no body tracker can promise that - it is that
the system never silently follows somebody else.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from kinecapture.capture.service import CaptureService
from kinecapture.capture.subject_lock import (
    AssociationPolicy,
    SubjectLock,
    SubjectLockState,
    SubjectSignature,
    is_ambiguous_pick,
    pick_body_at_pixel,
)
from kinecapture.domain.enums import TrackingState
from kinecapture.domain.models import BodyPose
from kinecapture.playback.take_reader import load_take
from kinecapture.visualization.skeleton_spec import MOCK_SKELETON
from tests.conftest import paced_backend, record_take

_REST = {
    "pelvis": (0.00, 0.95, 2.50),
    "chest_spine": (0.00, 1.25, 2.50),
    "neck": (0.00, 1.48, 2.50),
    "head": (0.00, 1.63, 2.50),
    "left_shoulder": (0.19, 1.43, 2.50),
    "left_elbow": (0.24, 1.18, 2.50),
    "left_wrist": (0.26, 0.94, 2.50),
    "right_shoulder": (-0.19, 1.43, 2.50),
    "right_elbow": (-0.24, 1.18, 2.50),
    "right_wrist": (-0.26, 0.94, 2.50),
    "left_hip": (0.11, 0.93, 2.50),
    "left_knee": (0.11, 0.52, 2.50),
    "left_ankle": (0.11, 0.08, 2.50),
    "right_hip": (-0.11, 0.93, 2.50),
    "right_knee": (-0.11, 0.52, 2.50),
    "right_ankle": (-0.11, 0.08, 2.50),
}


def _body(
    tracking_id: int,
    *,
    dx: float = 0.0,
    scale: float = 1.0,
    points_2d: np.ndarray | None = None,
) -> BodyPose:
    joints = np.asarray(
        [
            [_REST[name][0] * scale + dx, _REST[name][1] * scale, _REST[name][2]]
            for name in MOCK_SKELETON.joint_names
        ],
        dtype=np.float32,
    )
    return BodyPose(
        tracking_id=tracking_id,
        tracking_state=TrackingState.OK,
        body_format=MOCK_SKELETON.name,
        joint_positions_xyz=joints,
        joint_confidences=np.full(MOCK_SKELETON.num_joints, 0.9, dtype=np.float32),
        joint_positions_2d=points_2d,
    )


def _points(x: float, y: float) -> np.ndarray:
    return np.tile(
        np.asarray([x, y], dtype=np.float32), (MOCK_SKELETON.num_joints, 1)
    )


def _locked(**policy) -> SubjectLock:
    lock = SubjectLock(MOCK_SKELETON, policy=AssociationPolicy(**policy))
    lock.select(_body(1), frame_index=0, timestamp_ns=0)
    return lock


def _run(lock: SubjectLock, bodies, first_frame: int = 1, fps: float = 30.0):
    step = int(1e9 / fps)
    result = None
    for offset, frame_bodies in enumerate(bodies):
        frame = first_frame + offset
        result = lock.update(
            frame_bodies, frame_index=frame, timestamp_ns=frame * step
        )
    return result


# ------------------------------------------------------------- selection


def test_selecting_creates_a_logical_identity_separate_from_the_tracker() -> None:
    lock = SubjectLock(MOCK_SKELETON)
    subject_id = lock.select(_body(7), frame_index=4, timestamp_ns=133_000_000)

    assert subject_id.startswith("subj_")
    assert lock.tracking_id == 7
    assert lock.state is SubjectLockState.LOCKED
    provenance = lock.provenance()
    assert provenance["selection"]["initial_tracker_id"] == 7
    assert provenance["selection"]["frame_index"] == 4
    assert provenance["selection"]["method"] == "click"
    assert provenance["policy"]["version"]


def test_the_logical_id_survives_a_tracker_id_change() -> None:
    lock = _locked()
    _run(lock, [[_body(1)]] * 4)
    subject_id = lock.subject_id

    # Away for a moment, back with a new tracker id and nobody else around.
    result = lock.update([_body(9)], frame_index=30, timestamp_ns=1_000_000_000)
    assert result.state is SubjectLockState.LOCKED
    assert result.tracking_id == 9
    assert lock.subject_id == subject_id  # the identity did not change
    events = [e["event"] for e in lock.events]
    assert "reassociated" in events


# ----------------------------------------------------- refusing to switch


def test_another_person_alone_does_not_capture_the_lock() -> None:
    """The trainer case, and the reason this module exists."""
    lock = _locked()
    _run(lock, [[_body(1), _body(2, dx=1.0)]] * 5)
    assert 2 in lock.provenance()["disqualified_tracker_ids"]

    result = lock.update([_body(2, dx=1.0)], frame_index=60, timestamp_ns=2_000_000_000)
    assert result.state is SubjectLockState.AMBIGUOUS
    assert result.tracking_id is None
    assert lock.counters["reassociations"] == 0
    refusal = [e for e in lock.events if e["event"] == "reassociation_refused"]
    assert refusal and "aynı karede görülmüştü" in refusal[-1]["reason"]


def test_a_more_confident_stranger_never_wins_while_the_subject_is_present() -> None:
    lock = _locked()
    stranger = _body(2, dx=0.8)
    stranger.joint_confidences[:] = 1.0
    result = _run(lock, [[stranger, _body(1)]] * 3)
    assert result.tracking_id == 1
    assert result.reason == "same_tracker_id"


def test_two_similar_candidates_leave_the_lock_ambiguous() -> None:
    lock = _locked()
    _run(lock, [[_body(1)]] * 3)
    result = lock.update(
        [_body(8, dx=0.05), _body(9, dx=-0.05)],
        frame_index=40,
        timestamp_ns=1_300_000_000,
    )
    assert result.state is SubjectLockState.AMBIGUOUS
    assert result.reason == "insufficient_evidence"
    assert lock.tracking_id != 8 and lock.tracking_id != 9


def test_a_long_absence_stops_automatic_reassociation() -> None:
    lock = _locked(give_up_seconds=2.0)
    _run(lock, [[_body(1)]] * 3)
    result = lock.update([_body(5)], frame_index=900, timestamp_ns=30_000_000_000)
    assert result.state is SubjectLockState.AMBIGUOUS
    assert result.reason == "gap_too_long"


def test_once_ambiguous_the_lock_waits_instead_of_re_deciding() -> None:
    lock = _locked()
    _run(lock, [[_body(1), _body(2, dx=1.0)]] * 3)
    lock.update([_body(2, dx=1.0)], frame_index=60, timestamp_ns=2_000_000_000)
    for frame in range(61, 70):
        result = lock.update(
            [_body(2, dx=1.0)], frame_index=frame, timestamp_ns=frame * 33_000_000
        )
    assert result.state is SubjectLockState.AMBIGUOUS
    assert result.reason == "awaiting_confirmation"


def test_a_reused_tracker_id_is_accepted_only_on_evidence_and_flagged() -> None:
    """The SDK may hand out a number this take already retired."""
    lock = _locked()
    _run(lock, [[_body(1)]] * 3)
    # Subject leaves; a different id appears and is accepted on evidence.
    lock.update([_body(4)], frame_index=40, timestamp_ns=1_300_000_000)
    assert lock.tracking_id == 4
    # Now id 1 comes back - the number this take retired earlier.
    lock.update([_body(1)], frame_index=80, timestamp_ns=2_600_000_000)
    assert lock.counters["unexpected_id_reuse"] >= 1
    assert lock.provenance()["counters"]["unexpected_id_reuse"] >= 1


# -------------------------------------------------------- lost and back


def test_a_brief_blink_stays_lost_rather_than_hunting() -> None:
    lock = _locked()
    _run(lock, [[_body(1)]] * 3)
    result = lock.update([], frame_index=5, timestamp_ns=166_000_000)
    assert result.state is SubjectLockState.TEMPORARILY_LOST
    assert result.tracking_id is None
    assert lock.counters["lost_frames"] >= 1


def test_the_same_id_returning_simply_resumes() -> None:
    lock = _locked()
    _run(lock, [[_body(1)]] * 3)
    lock.update([], frame_index=5, timestamp_ns=166_000_000)
    result = lock.update([_body(1)], frame_index=6, timestamp_ns=200_000_000)
    assert result.state is SubjectLockState.LOCKED
    assert result.reason == "same_tracker_id"
    assert lock.counters["reassociations"] == 0


def test_manual_confirmation_is_recorded_as_an_event() -> None:
    lock = _locked()
    _run(lock, [[_body(1), _body(2, dx=1.0)]] * 3)
    lock.update([_body(2, dx=1.0)], frame_index=60, timestamp_ns=2_000_000_000)
    assert lock.state is SubjectLockState.AMBIGUOUS

    lock.confirm(_body(2, dx=1.0), frame_index=61, timestamp_ns=2_033_000_000)
    assert lock.state is SubjectLockState.LOCKED
    assert lock.tracking_id == 2
    assert lock.counters["manual_confirmations"] == 1
    events = [e for e in lock.events if e["event"] == "manual_confirmation"]
    assert events and events[-1]["method"] == "manual"


def test_the_audit_trail_records_scores_and_reasons() -> None:
    lock = _locked()
    _run(lock, [[_body(1)]] * 3)
    lock.update([_body(6)], frame_index=40, timestamp_ns=1_300_000_000)
    event = [e for e in lock.events if e["event"] == "reassociated"][-1]
    assert event["previous_tracker_id"] == 1
    assert event["new_tracker_id"] == 6
    assert 0.0 <= event["score"] <= 1.0
    assert event["reason"]
    assert event["algorithm_version"]
    assert event["candidates"]


def test_privacy_scope_is_stated_and_narrow() -> None:
    lock = _locked()
    provenance = lock.provenance()
    assert "Yüz tanıma" in provenance["privacy"]
    signature = provenance["signature"]
    # Limb ratios only - nothing that could identify a person elsewhere.
    assert set(signature) == {"limb_lengths", "stature", "samples", "scope"}
    assert "biyometrik" not in " ".join(signature["limb_lengths"])


def test_signature_similarity_separates_different_builds() -> None:
    small = SubjectSignature.measure(_body(1, scale=0.8), MOCK_SKELETON)
    same = SubjectSignature.measure(_body(2, scale=0.8), MOCK_SKELETON)
    large = SubjectSignature.measure(_body(3, scale=1.2), MOCK_SKELETON)

    limb_same, stature_same = small.similarity(same)
    limb_diff, stature_diff = small.similarity(large)
    assert limb_same == pytest.approx(1.0, abs=1e-6)
    assert limb_diff < 0.4
    assert stature_same > stature_diff


# ------------------------------------------------------------- picking


def test_clicking_picks_the_nearest_body_by_its_own_2d_keypoints() -> None:
    left = _body(1, points_2d=_points(100.0, 200.0))
    right = _body(2, points_2d=_points(500.0, 200.0))
    chosen, candidates = pick_body_at_pixel([left, right], 110.0, 205.0)
    assert chosen is left
    assert [c[0].tracking_id for c in candidates] == [1, 2]


def test_clicking_empty_space_picks_nobody() -> None:
    body = _body(1, points_2d=_points(100.0, 200.0))
    chosen, _candidates = pick_body_at_pixel([body], 900.0, 900.0, radius=40.0)
    assert chosen is None


def test_two_overlapping_people_are_reported_ambiguous_not_guessed() -> None:
    first = _body(1, points_2d=_points(300.0, 200.0))
    second = _body(2, points_2d=_points(310.0, 200.0))
    _chosen, candidates = pick_body_at_pixel([first, second], 305.0, 200.0)
    assert is_ambiguous_pick(candidates)


def test_well_separated_people_are_not_ambiguous() -> None:
    first = _body(1, points_2d=_points(100.0, 200.0))
    second = _body(2, points_2d=_points(600.0, 200.0))
    _chosen, candidates = pick_body_at_pixel([first, second], 105.0, 200.0)
    assert not is_ambiguous_pick(candidates)


def test_a_body_without_2d_keypoints_is_skipped_rather_than_guessed() -> None:
    chosen, candidates = pick_body_at_pixel([_body(1)], 100.0, 100.0)
    assert chosen is None
    assert candidates == []


# ------------------------------------------------- through the pipeline


def test_a_recorded_take_carries_the_authoritative_association(
    workspace, session
) -> None:
    service = CaptureService(paced_backend())
    service.connect()
    service.start_preview()
    deadline = time.time() + 10
    packet = service.peek_frame()
    while (packet is None or not packet.bodies) and time.time() < deadline:
        time.sleep(0.01)
        packet = service.peek_frame()
    assert packet is not None and packet.bodies
    service.select_subject(packet.bodies[0])
    subject_id = service.subject_lock.subject_id

    take = record_take(service, workspace, session, frames=20)
    service.shutdown()

    loaded = load_take(workspace, take, with_video=False)
    stream = loaded.stream
    assert stream.has_subject_lock
    assert stream.subject_id == subject_id
    for frame in stream.frames:
        assert frame.subject is not None
        body = frame.subject_body()
        if body is not None:
            assert body.tracking_id == frame.subject["tracker_id"]

    arrays = stream.subject_arrays(num_joints=MOCK_SKELETON.num_joints)
    assert arrays["subject_present_mask"].all()
    assert np.isfinite(arrays["joints_xyz"]).any()
    assert take.metrics.subject_coverage == pytest.approx(1.0)


def test_absent_subject_frames_are_nan_not_borrowed() -> None:
    """A frame without the subject must never carry somebody else's pose."""
    from kinecapture.playback.take_reader import SkeletonFrame, SkeletonStream

    stream = SkeletonStream()
    stream.frames = [
        SkeletonFrame(
            frame_index=0,
            host_timestamp_ns=0,
            camera_timestamp_ns=0,
            bodies=(_body(1),),
            subject={"state": "locked", "tracker_id": 1},
        ),
        SkeletonFrame(
            frame_index=1,
            host_timestamp_ns=0,
            camera_timestamp_ns=33_000_000,
            # Somebody else is here, and the lock refused to follow them.
            bodies=(_body(2, dx=1.0),),
            subject={"state": "ambiguous"},
        ),
    ]
    arrays = stream.subject_arrays(num_joints=MOCK_SKELETON.num_joints)
    assert arrays["subject_present_mask"].tolist() == [True, False]
    assert np.isfinite(arrays["joints_xyz"][0]).all()
    assert np.isnan(arrays["joints_xyz"][1]).all()
    assert arrays["subject_source_tracking_id"].tolist() == [1, -1]

    # The display helper would have happily returned the stranger; the
    # dataset helper does not.
    assert stream.frames[1].body(None) is not None
    assert stream.frames[1].subject_body() is None


def test_clicking_during_recording_does_not_move_the_lock(workspace, session) -> None:
    service = CaptureService(paced_backend())
    service.connect()
    service.start_preview()
    deadline = time.time() + 10
    packet = service.peek_frame()
    while (packet is None or not packet.bodies) and time.time() < deadline:
        time.sleep(0.01)
        packet = service.peek_frame()
    service.select_subject(packet.bodies[0])
    original = service.subject_lock.tracking_id

    take = service.start_recording(workspace, session)
    deadline = time.time() + 10
    while service.recorded_frame_count < 6 and time.time() < deadline:
        time.sleep(0.005)
    # The capture page refuses the click; the service still holds the lock.
    assert service.is_recording
    assert service.subject_lock.tracking_id == original
    service.stop_recording()
    service.shutdown()
