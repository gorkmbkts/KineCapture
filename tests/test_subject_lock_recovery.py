"""Losing the subject for a moment must not lose the rest of the recording.

The 20 September take, replayed through the real lock, produced 625 locked
frames and then 843 ambiguous ones. The athlete never left the frame; tracker
id 0 was reported in every single one of those 843 frames. Two separate
defects had to line up:

* the veto that gave up on the id was reading a **posture** measurement as an
  identity measurement. The limb-length score - the one that actually says
  which person this is - held at **0.992** for every frame of the incident,
  while the joint-cloud height slid from 1.376 m to 1.288 m as the athlete
  bent forward and took the stature score under the 0.3 threshold;
* and ``AMBIGUOUS`` was a **terminal** state: :meth:`update` returned on its
  first line from then on, so the only way back was an operator pressing a
  button. Offline processing has no operator.

These tests hold both shut, and hold shut the thing they must not break: the
lock still never moves to a different person on its own.
"""

from __future__ import annotations

import numpy as np

from kinecapture.capture.subject_lock import (
    AssociationPolicy,
    SubjectLock,
    SubjectLockState,
    SubjectSignature,
    _proportions_contradict,
)
from kinecapture.domain.enums import TrackingState
from kinecapture.domain.models import BodyPose
from kinecapture.visualization.skeleton_spec import MOCK_SKELETON

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
    crouch: float = 0.0,
    state: TrackingState = TrackingState.OK,
) -> BodyPose:
    """One person. ``crouch`` folds them without changing any bone length.

    A rigid rotation of the whole body about the pelvis, in the plane that
    contains "up": every segment keeps its length **exactly**, and the height
    of the joint cloud falls. That is the distinction the whole fix rests on -
    limb lengths are bones, joint-cloud height is posture - so the fixture has
    to honour it rather than just scaling the person down.
    """
    pelvis = np.asarray(_REST["pelvis"], dtype=np.float64) * np.asarray(
        [scale, scale, 1.0]
    )
    rows = []
    for name in MOCK_SKELETON.joint_names:
        point = np.asarray(_REST[name], dtype=np.float64) * np.asarray(
            [scale, scale, 1.0]
        )
        offset = point - pelvis
        if crouch:
            angle = float(crouch)
            y, z = offset[1], offset[2]
            offset = np.asarray(
                [
                    offset[0],
                    y * np.cos(angle) - z * np.sin(angle),
                    y * np.sin(angle) + z * np.cos(angle),
                ]
            )
        point = pelvis + offset
        point[0] += dx
        rows.append(point)
    joints = np.asarray(rows, dtype=np.float32)
    return BodyPose(
        tracking_id=tracking_id,
        tracking_state=state,
        body_format=MOCK_SKELETON.name,
        joint_positions_xyz=joints,
        joint_confidences=np.full(MOCK_SKELETON.num_joints, 0.9, dtype=np.float32),
    )


def _locked(**policy) -> SubjectLock:
    lock = SubjectLock(MOCK_SKELETON, policy=AssociationPolicy(**policy))
    lock.select(_body(1), frame_index=0, timestamp_ns=0)
    # Blend a few agreeing frames so the signature is a real description,
    # which is what arms the veto at all.
    _run(lock, [[_body(1)]] * 10)
    return lock


def _run(lock, frames, first_frame: int = 1, fps: float = 60.0):
    step = int(1e9 / fps)
    result = None
    for offset, bodies in enumerate(frames):
        index = first_frame + offset
        result = lock.update(bodies, frame_index=index, timestamp_ns=index * step)
    return result


# --------------------------------------------------- the posture false alarm


def test_bending_over_is_not_evidence_of_a_different_person() -> None:
    """The exact shape of the 20 September incident, in miniature."""
    lock = _locked()
    mirror = _body(2, dx=1.4)  # a second body, which is what arms the veto
    _run(lock, [[_body(1), mirror]] * 5)
    assert lock.state is SubjectLockState.LOCKED

    # Fold forward over half a second. No bone changes length.
    bent = [[_body(1, crouch=angle), mirror] for angle in np.linspace(0.0, 1.2, 30)]
    _run(lock, bent, first_frame=20)

    assert lock.state is SubjectLockState.LOCKED
    assert lock.provenance()["counters"]["ambiguous_frames"] == 0


def test_the_crouch_fixture_really_does_shorten_without_changing_bones() -> None:
    """Otherwise the test above would be proving nothing."""
    upright = SubjectSignature.measure(_body(1), MOCK_SKELETON)
    bent = SubjectSignature.measure(_body(1, crouch=1.2), MOCK_SKELETON)

    assert bent.stature < upright.stature * 0.8, "the fixture does not fold"
    for name, length in upright.limb_lengths.items():
        assert abs(bent.limb_lengths[name] - length) < 1e-3, name
    limb, stature = upright.similarity(bent)
    assert limb > 0.99
    assert stature < 0.3, "this is what used to veto"
    assert not _proportions_contradict(limb, stature)


def test_proportions_still_veto_when_the_limbs_disagree() -> None:
    """The protection the veto exists for is untouched."""
    assert _proportions_contradict(0.1, 1.0)
    # And with no proportion evidence at all, stature is all there is.
    assert _proportions_contradict(float("nan"), 0.1)
    assert not _proportions_contradict(float("nan"), 0.9)


def test_a_genuinely_different_body_on_the_same_id_still_ends_the_lock() -> None:
    lock = _locked()
    other = _body(2, dx=1.4)
    # Tracker id 1 starts reporting somebody of quite different build.
    impostor = [[_body(1, scale=0.55), other]] * 6
    _run(lock, impostor, first_frame=20)

    assert lock.state is SubjectLockState.AMBIGUOUS


# ------------------------------------------------------------- the recovery


def test_an_ambiguous_lock_resumes_on_its_own_id_when_the_evidence_returns() -> None:
    lock = _locked(recovery_frames=5)
    other = _body(2, dx=1.4)
    _run(lock, [[_body(1, scale=0.55), other]] * 6, first_frame=20)
    assert lock.state is SubjectLockState.AMBIGUOUS

    result = _run(lock, [[_body(1), other]] * 5, first_frame=40)

    assert lock.state is SubjectLockState.LOCKED
    assert lock.tracking_id == 1
    assert result.reason == "recovered_same_id"
    assert lock.provenance()["counters"]["recoveries"] == 1
    events = [e["event"] for e in lock.provenance()["events"]]
    assert "subject_recovered_same_id" in events


def test_recovery_needs_sustained_agreement_not_one_good_frame() -> None:
    lock = _locked(recovery_frames=10)
    other = _body(2, dx=1.4)
    _run(lock, [[_body(1, scale=0.55), other]] * 6, first_frame=20)

    result = _run(lock, [[_body(1), other]] * 4, first_frame=40)

    assert lock.state is SubjectLockState.AMBIGUOUS
    assert result.reason == "recovery_pending"


def test_a_run_of_agreement_broken_in_the_middle_starts_again() -> None:
    lock = _locked(recovery_frames=6)
    other = _body(2, dx=1.4)
    _run(lock, [[_body(1, scale=0.55), other]] * 6, first_frame=20)

    _run(lock, [[_body(1), other]] * 4, first_frame=40)
    _run(lock, [[_body(1, scale=0.55), other]], first_frame=50)  # disagrees again
    _run(lock, [[_body(1), other]] * 4, first_frame=60)

    assert lock.state is SubjectLockState.AMBIGUOUS


def test_recovery_never_moves_to_another_person() -> None:
    """The guarantee the module exists for. An ambiguous lock with somebody
    else standing there must stay ambiguous, however agreeable they look."""
    lock = _locked(recovery_frames=3)
    twin = _body(2, dx=0.02)  # same build, same place, different id
    _run(lock, [[_body(1), twin]] * 4, first_frame=20)  # makes id 2 co-visible
    _run(lock, [[_body(1, scale=0.55), twin]] * 6, first_frame=30)
    assert lock.state is SubjectLockState.AMBIGUOUS

    # Now the subject's own id disappears and only the twin remains.
    _run(lock, [[twin]] * 60, first_frame=40)

    assert lock.state is SubjectLockState.AMBIGUOUS
    assert lock.tracking_id != 2


def test_recovery_refuses_an_id_that_was_ever_seen_beside_the_subject() -> None:
    lock = SubjectLock(MOCK_SKELETON, policy=AssociationPolicy(recovery_frames=3))
    lock.select(_body(1), frame_index=0, timestamp_ns=0)
    _run(lock, [[_body(1), _body(2, dx=1.4)]] * 10)
    assert 2 in lock.provenance()["disqualified_tracker_ids"]

    # Force ambiguity, then hand it id 2 alone under its own tracking id.
    _run(lock, [[_body(1, scale=0.55), _body(2, dx=1.4)]] * 6, first_frame=20)
    lock.tracking_id = 2  # what a buggy caller might do
    _run(lock, [[_body(2, dx=1.4)]] * 30, first_frame=40)

    assert lock.state is SubjectLockState.AMBIGUOUS


def test_an_unresolved_body_does_not_count_towards_recovery() -> None:
    lock = _locked(recovery_frames=3)
    other = _body(2, dx=1.4)
    _run(lock, [[_body(1, scale=0.55), other]] * 6, first_frame=20)

    unresolved = [[_body(1, state=TrackingState.SEARCHING), other]] * 30
    _run(lock, unresolved, first_frame=40)

    assert lock.state is SubjectLockState.AMBIGUOUS


# --------------------------------------------------- the self-feeding gap


def test_a_conflicting_frame_still_counts_as_having_seen_the_id() -> None:
    """The second half of the 20 September trap.

    ``_remember`` used to be skipped whenever the evidence disagreed, so the
    recorded "last seen" time stopped advancing while the subject stayed on
    screen. After ``give_up_seconds`` the very first line of the check made
    every later frame a contradiction on its own - a disagreement feeding
    itself, with nothing left that could settle it.
    """
    lock = _locked(contradiction_frames=1000, give_up_seconds=1.0)
    other = _body(2, dx=1.4)
    # Four seconds of disagreement, well past `give_up_seconds`.
    _run(lock, [[_body(1, scale=0.55), other]] * 240, first_frame=20)

    provenance = lock.provenance()
    assert provenance["state"] != "ambiguous"
    # The run counts frames, so the gap never became a second reason to give up.
    assert lock._contradiction_run == 240
    # Seeing the id keeps time fresh, but rejected geometry must not move the
    # trusted position. The original body can return immediately, even after
    # a contradiction lasting longer than give_up_seconds.
    result = _run(lock, [[_body(1), other]], first_frame=260)
    assert result.state is SubjectLockState.LOCKED
    assert result.tracking_id == 1
