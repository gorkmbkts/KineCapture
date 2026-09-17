"""From a real recording to a version somebody can label.

On 16 September two ZED recordings were made, processed, and then could not be
found anywhere in the application. Everything about them was intact: the SVO
held 455 MB and 1.6 GB of lossless stereo, the offline pass produced a proxy
video, a skeleton stream, arrays, previews and checksums, and 99.6% and 99.8%
of the recorded frames were matched frame-for-frame against the replayed
source. The screens showed an empty list.

Four separate rules had to be wrong at once for that to happen, and each one is
checked here.

1. **Publication follows usability, not perfection.** A version with recorded
   caveats is still a version; only a fault that would make annotation *wrong*
   keeps one in staging.
2. **A subject chosen before the recording started is still the chosen
   subject.** The operator picks the person, then presses record - by 3.7 s in
   one take and 1.6 s in the other.
3. **The tracker's warm-up frames do not define who the subject is.** The ZED
   reports a partial skeleton until its body fitter converges.
4. **Body proportions can only overrule the tracker when there is another
   person to be confused with.** They move with posture, and a squat is a
   posture.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.capture.subject_lock import (
    ASSOCIATION_ALGORITHM_VERSION,
    SubjectLock,
    SubjectLockState,
    SubjectSignature,
)
from kinecapture.domain.enums import TakeState, TrackingState
from kinecapture.processing.jobs import BLOCKING_ISSUES
from kinecapture.recording.take_writer import TakeWriter


# --------------------------------------------------------------- publication


def test_only_a_fault_that_would_make_annotation_wrong_blocks_a_version():
    """The blocking set is deliberately tiny, and says why in its own name.

    Coverage shortfalls, timestamp gaps, a missing preview video and an anchor
    taken early are all things to *tell* the annotator. None of them makes the
    frames they are about to label the wrong frames.
    """
    assert BLOCKING_ISSUES == {
        "source_empty",
        "source_position_discontinuity",
        "review_proxy_desynchronised",
    }
    for advisory in (
        "capture_frames_unmatched",
        "capture_timestamp_duplicated",
        "source_frame_count_mismatch",
        "source_timestamp_gap",
        "subject_anchor_before_recording",
        "review_proxy_unavailable",
    ):
        assert advisory not in BLOCKING_ISSUES


# ------------------------------------------------------------- subject lock


@pytest.fixture
def tracked():
    """One real mock body, plus the spec that explains its joint order."""
    backend = MockCameraBackend(width=160, height=120)
    backend.connect()
    backend.start_preview()
    body = backend.grab_frame().bodies[0]
    spec = backend.skeleton
    yield body, spec
    backend.disconnect()


def _warming_up(body):
    """The tracker's first frames: it has not resolved the body yet.

    Modelled on what the ZED actually produced - ``OFF``, and most of the
    skeleton missing, so the few segments that can be measured describe a
    fragment rather than a person. The joints that *are* present keep their
    real positions: the fitter was converging, not looking somewhere else.
    """
    joints = np.array(body.joint_positions_xyz, dtype=np.float32)
    joints[6:] = np.nan
    return replace(body, tracking_state=TrackingState.OFF, joint_positions_xyz=joints)


def _crouched(body, factor=0.6):
    """The same person, folded up, without moving where they stand.

    Every joint is drawn towards the pelvis, which is what a squat does to the
    numbers the ZED reports: shorter limbs and a much shorter joint extent, at
    the same place on the floor.
    """
    joints = np.array(body.joint_positions_xyz, dtype=np.float32)
    root = joints[0].copy()
    return replace(body, joint_positions_xyz=root + (joints - root) * factor)


def test_a_warm_up_frame_does_not_get_to_define_the_subject(tracked):
    """Six half-resolved frames, then the real body. Same person throughout.

    In the 16 September take the fitter reported a 0.877 m body for six frames
    and a 1.740 m body on the seventh, 17 ms later. Averaging the first six
    into the subject's proportions made the seventh score 0.0 against them, and
    the lock recorded the remaining 1638 frames with nobody in them.
    """
    body, spec = tracked
    lock = SubjectLock()
    lock.select(_warming_up(body), frame_index=0, timestamp_ns=0, spec=spec)
    for index in range(6):
        lock.update(
            [_warming_up(body)], frame_index=index, timestamp_ns=index * 16_666_666
        )
    settled = lock.update([body], frame_index=6, timestamp_ns=6 * 16_666_666)
    assert settled.state is SubjectLockState.LOCKED
    assert settled.tracking_id == int(body.tracking_id)


def test_the_signature_is_only_built_from_frames_the_tracker_resolved(tracked):
    """An unresolved frame contributes nothing, so it cannot poison the average."""
    body, spec = tracked
    lock = SubjectLock()
    lock.select(_warming_up(body), frame_index=0, timestamp_ns=0, spec=spec)
    assert not lock.signature.is_usable
    lock.update([body], frame_index=1, timestamp_ns=16_666_666)
    measured = SubjectSignature.measure(body, spec)
    if measured.is_usable:
        assert lock.signature.limb_lengths == pytest.approx(measured.limb_lengths)


def test_proportions_cannot_overrule_the_tracker_with_nobody_else_in_frame(tracked):
    """A squat is a posture, and the ZED re-fits its model every frame.

    The same person measured a 1.709 m joint extent standing and 1.064 m at the
    bottom of a squat, with thigh length moving 25%. With one body in the frame
    carrying the subject's own id there is no competing hypothesis for that
    disagreement to support.
    """
    body, spec = tracked
    lock = SubjectLock()
    lock.select(body, frame_index=0, timestamp_ns=0, spec=spec)
    # Fold in enough agreeing frames that the signature is well established.
    for index in range(1, 30):
        lock.update([body], frame_index=index, timestamp_ns=index * 16_666_666)
    crouched = _crouched(body)
    for index in range(30, 40):
        association = lock.update(
            [crouched], frame_index=index, timestamp_ns=index * 16_666_666
        )
    assert association.state is SubjectLockState.LOCKED
    assert association.tracking_id == int(body.tracking_id)


def test_proportions_still_decide_when_there_is_somebody_to_confuse(tracked):
    """Two bodies at once is exactly where the check earns its keep."""
    body, spec = tracked
    lock = SubjectLock()
    lock.select(body, frame_index=0, timestamp_ns=0, spec=spec)
    for index in range(1, 30):
        lock.update([body], frame_index=index, timestamp_ns=index * 16_666_666)
    impostor = _crouched(body, factor=0.5)
    other = replace(body, tracking_id=int(body.tracking_id) + 1)
    for index in range(30, 40):
        association = lock.update(
            [impostor, other], frame_index=index, timestamp_ns=index * 16_666_666
        )
    assert association.tracking_id is None


def test_the_algorithm_version_records_that_the_decisions_changed():
    """Provenance has to be able to tell a 1.1.0 association from a 1.2.0 one."""
    assert ASSOCIATION_ALGORITHM_VERSION == "1.2.0"


# ------------------------------------------------------------- capture side


def test_a_repeated_camera_timestamp_does_not_demote_an_intact_recording(
    workspace, session
):
    """One microsecond reported twice is a camera quirk, not a lost frame.

    The ZED did it once in 524 frames and twice in 1648. The old test was
    ``gap <= 0``, which called it "non-monotonic" and left both recordings
    PARTIAL with a note about an RGB-D archive that had been switched off on
    purpose. Every frame was on disk.
    """
    backend = MockCameraBackend(width=160, height=120)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(
        session, origin=backend.origin, camera_info=info
    )
    writer = TakeWriter(workspace, take, paths, write_proxy_video=False)
    first = backend.grab_frame()
    writer.write_frame(first)
    # The same camera timestamp again, which is exactly what was recorded.
    writer.write_frame(replace(backend.grab_frame(), camera_timestamp_ns=first.camera_timestamp_ns))
    writer.write_frame(backend.grab_frame())
    finished = writer.finalize()
    backend.disconnect()

    assert finished.state is TakeState.FINALIZED
    assert not finished.metrics.has_raw_archive_loss
    # Written down, not swept away.
    assert "tekrarladı" in finished.notes
