"""Keeping the recording on the person the operator chose.

The problem
-----------
A ZED ``BodyData.id`` is a *tracker* identity. It is stable while the tracker
keeps the track, and it says nothing at all after the person walks out of frame
and back in. Meanwhile a physiotherapist may step into the shot, and they are
often the better-lit, better-tracked body. Anything that follows "the most
confident body" will therefore, sooner or later, write the wrong person's
skeleton into the ground truth - silently.

So this module separates two things that the existing code conflated:

``subject_id``
    A take-local logical identity for the person the operator selected. It is
    created once, at selection, and never changes for the rest of the take.
``tracker_body_id``
    Which SDK body that logical person is matched to *right now*, or nothing.

The guarantee
-------------
This is deliberately not "the person is always re-identified". No such
guarantee can be made from a body tracker. What is guaranteed is:

* the lock never moves to another person on its own;
* an automatic re-association happens only when the evidence clears an explicit
  threshold *and* beats the runner-up by an explicit margin;
* when it cannot decide, it says :attr:`SubjectLockState.AMBIGUOUS` and asks,
  rather than picking;
* every decision - and every refusal - is written to an audit trail with the
  frame, the timestamp, the scores and the reason.

Evidence
--------
Association uses only geometry and size, computed inside this take:

* whether the candidate was ever on screen *at the same time* as the subject.
  If it was, it is somebody else - no similarity score can outrank that, and it
  is what stops the lock sliding onto a physiotherapist of similar build;
* how far the candidate's root is from where the subject was last seen, given
  how long ago that was and a plausible walking speed;
* how well the candidate's limb lengths match the subject's, which is a body
  proportion rather than an appearance;
* how much the candidate's stature matches.

No face recognition, no appearance embedding, no database that outlives the
take. That is a privacy boundary, not an oversight: a descriptor able to
recognise a person across recordings is a biometric identifier, and this
application has no consent model for one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

from kinecapture.core.ids import new_id, utc_now_iso
from kinecapture.domain.models import BodyPose
from kinecapture.features.roles import resolve_roles
from kinecapture.visualization.skeleton_spec import SkeletonSpec

#: Bumped whenever the scoring below could produce a different decision.
#:
#: 1.2.0: the subject's body signature is measured only from frames the
#: tracker reports as resolved, and a single contradicting frame no longer
#: ends the association. Both come from the 16 September recordings, where the
#: ZED reported a 0.88 m body for six frames and a 1.74 m body on the seventh -
#: the same person, 17 ms apart - and the lock treated the difference as a
#: person swap for the remaining 1638 frames.
ASSOCIATION_ALGORITHM_VERSION = "1.2.0"


class SubjectLockState(str, Enum):
    """Where the lock is in its life cycle.

    ``UNSELECTED -> LOCKED -> TEMPORARILY_LOST -> REIDENTIFYING -> LOCKED``
    with ``AMBIGUOUS`` as the honest dead end when the evidence does not decide.
    """

    UNSELECTED = "unselected"
    LOCKED = "locked"
    TEMPORARILY_LOST = "temporarily_lost"
    REIDENTIFYING = "reidentifying"
    AMBIGUOUS = "ambiguous"

    @property
    def label(self) -> str:
        return {
            SubjectLockState.UNSELECTED: "Kişi seçilmedi",
            SubjectLockState.LOCKED: "Kilitli",
            SubjectLockState.TEMPORARILY_LOST: "Kayıp",
            SubjectLockState.REIDENTIFYING: "Yeniden aranıyor",
            SubjectLockState.AMBIGUOUS: "Belirsiz - doğrulama gerekiyor",
        }[self]

    @property
    def is_tracking(self) -> bool:
        return self is SubjectLockState.LOCKED


@dataclass(frozen=True)
class AssociationPolicy:
    """The thresholds. Versioned, written into the take, never implicit."""

    version: str = ASSOCIATION_ALGORITHM_VERSION
    #: A candidate scoring below this is never accepted automatically.
    min_score: float = 0.62
    #: The best candidate must beat the runner-up by at least this much.
    min_margin: float = 0.15
    #: After this long without the subject, position continuity stops being
    #: evidence at all - somebody else could be standing there by now.
    position_evidence_seconds: float = 2.0
    #: Plausible displacement per second while out of view, in length units.
    plausible_speed: float = 2.5
    #: Beyond this gap the lock stops trying and waits for the operator.
    give_up_seconds: float = 20.0
    #: A brief blink before any re-association is attempted. Trackers routinely
    #: drop a body for a frame or two and come back with the same id, and
    #: scoring candidates during that blink only manufactures ambiguity.
    lost_grace_seconds: float = 0.5
    #: Consecutive frames whose evidence has to contradict the signature before
    #: the lock gives up on an id the tracker is still reporting. One frame is
    #: noise; on 16 September one frame cost 1638.
    contradiction_frames: int = 3
    #: Weights of the three evidence terms; they sum to 1.
    weight_position: float = 0.4
    weight_limb_ratio: float = 0.4
    weight_stature: float = 0.2

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class SubjectSignature:
    """The take-local body description used to recognise the subject again.

    Limb lengths and stature only. Deliberately too coarse to identify a person
    outside this recording, which is the point.
    """

    limb_lengths: dict[str, float] = field(default_factory=dict)
    stature: float = float("nan")
    samples: int = 0

    @classmethod
    def measure(cls, body: BodyPose, spec: SkeletonSpec) -> "SubjectSignature":
        roles = resolve_roles(spec)
        joints = body.joint_positions_xyz

        def segment(a: str, b: str) -> Optional[float]:
            ia, ib = roles.get(a), roles.get(b)
            if ia is None or ib is None:
                return None
            first, second = joints[ia], joints[ib]
            if not (np.isfinite(first).all() and np.isfinite(second).all()):
                return None
            return float(np.linalg.norm(first - second))

        lengths: dict[str, float] = {}
        for name, (a, b) in {
            "left_upper_arm": ("left_shoulder", "left_elbow"),
            "right_upper_arm": ("right_shoulder", "right_elbow"),
            "left_forearm": ("left_elbow", "left_wrist"),
            "right_forearm": ("right_elbow", "right_wrist"),
            "left_thigh": ("left_hip", "left_knee"),
            "right_thigh": ("right_hip", "right_knee"),
            "left_shank": ("left_knee", "left_ankle"),
            "right_shank": ("right_knee", "right_ankle"),
            "shoulder_width": ("left_shoulder", "right_shoulder"),
            "hip_width": ("left_hip", "right_hip"),
            "trunk": ("pelvis", "neck"),
        }.items():
            value = segment(a, b)
            if value is not None and value > 1e-4:
                lengths[name] = value

        vertical = _vertical_axis_index(spec)
        finite = joints[np.isfinite(joints).all(axis=1)]
        stature = (
            float(finite[:, vertical].max() - finite[:, vertical].min())
            if finite.shape[0] >= 2
            else float("nan")
        )
        return cls(limb_lengths=lengths, stature=stature, samples=1)

    def blend(self, other: "SubjectSignature") -> "SubjectSignature":
        """Running average, so one noisy frame cannot redefine the subject."""
        total = self.samples + other.samples
        if total == 0:
            return self
        merged: dict[str, float] = {}
        for key in set(self.limb_lengths) | set(other.limb_lengths):
            mine = self.limb_lengths.get(key)
            theirs = other.limb_lengths.get(key)
            if mine is None:
                merged[key] = float(theirs)  # type: ignore[arg-type]
            elif theirs is None:
                merged[key] = mine
            else:
                merged[key] = (mine * self.samples + theirs * other.samples) / total
        stature = self.stature
        if math.isnan(stature):
            stature = other.stature
        elif not math.isnan(other.stature):
            stature = (
                self.stature * self.samples + other.stature * other.samples
            ) / total
        return SubjectSignature(
            limb_lengths=merged, stature=stature, samples=min(total, 300)
        )

    #: Segments a measurement needs before it describes a person rather than
    #: whatever the tracker has resolved so far.
    MIN_SEGMENTS = 6

    @property
    def is_usable(self) -> bool:
        """Enough of a body to be a description of a person.

        Three segments is not. The ZED body fitter takes a few frames to
        converge and reports a fragment until it does: in the 16 September
        take the first six frames measured three segments and a 0.475 m
        stature, and the seventh - same person, same tracking id, 17 ms later -
        measured eleven segments and 1.621 m. With the fragment enshrined as
        the subject's proportions, the real body scored 0.0 against it, the
        lock called that a contradiction, and the remaining 516 frames were
        recorded with no subject at all.
        """
        return len(self.limb_lengths) >= self.MIN_SEGMENTS and math.isfinite(self.stature)

    def similarity(self, other: "SubjectSignature") -> tuple[float, float]:
        """``(limb ratio score, stature score)``, each 0..1 or NaN."""
        shared = set(self.limb_lengths) & set(other.limb_lengths)
        if len(shared) < 3:
            limb = float("nan")
        else:
            errors = [
                abs(self.limb_lengths[key] - other.limb_lengths[key])
                / max(1e-3, self.limb_lengths[key])
                for key in shared
            ]
            # 15% mean relative error scores zero; identical proportions score 1.
            limb = float(max(0.0, 1.0 - (sum(errors) / len(errors)) / 0.15))
        if math.isnan(self.stature) or math.isnan(other.stature):
            stature = float("nan")
        else:
            error = abs(self.stature - other.stature) / max(1e-3, self.stature)
            stature = float(max(0.0, 1.0 - error / 0.15))
        return limb, stature

    def to_dict(self) -> dict[str, Any]:
        return {
            "limb_lengths": {k: round(v, 5) for k, v in sorted(self.limb_lengths.items())},
            "stature": None if math.isnan(self.stature) else round(self.stature, 5),
            "samples": self.samples,
            "scope": (
                "take-local vücut oranları. Yüz biyometrisi değildir ve bu "
                "kaydın dışında kişi tanımak için kullanılamaz."
            ),
        }


def _vertical_axis_index(spec: SkeletonSpec) -> int:
    return {"x": 0, "y": 1, "z": 2}.get((spec.vertical_axis or "y").lower(), 1)


def _is_resolved(body: BodyPose) -> bool:
    """Whether the tracker says it has actually resolved this body.

    The ZED reports ``OFF`` for the first frames of a detection while the body
    fitter converges, and the skeleton it hands over meanwhile is a partial
    one: in the 16 September squat take, frames 0-5 came back ``off`` with 27
    valid joints and a 0.877 m stature, and frame 6 came back ``ok`` with 38
    joints and 1.740 m. Those first frames are perfectly good *poses* - they
    are kept and annotated like any other - but they are not a description of
    who the person is, and measuring the subject's proportions from them made
    the real body look like a stranger.
    """
    state = getattr(body.tracking_state, "value", body.tracking_state)
    return str(state).lower() == "ok"


def _root_position(body: BodyPose, spec: SkeletonSpec) -> Optional[np.ndarray]:
    roles = resolve_roles(spec)
    index = roles.get("pelvis")
    if index is None:
        index = spec.root_index
    point = body.joint_positions_xyz[index]
    if np.isfinite(point).all():
        return np.asarray(point, dtype=np.float64)
    finite = body.joint_positions_xyz[np.isfinite(body.joint_positions_xyz).all(axis=1)]
    return finite.mean(axis=0).astype(np.float64) if finite.shape[0] else None


@dataclass
class CandidateScore:
    """Why one body was or was not accepted as the subject."""

    tracking_id: int
    score: float
    position_score: float
    limb_score: float
    stature_score: float
    distance: float
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracking_id": self.tracking_id,
            "score": round(self.score, 4),
            "position": round(self.position_score, 4),
            "limb_ratio": round(self.limb_score, 4),
            "stature": round(self.stature_score, 4),
            "distance": round(self.distance, 4),
            "reason": self.reason,
        }


@dataclass
class FrameAssociation:
    """The authoritative answer for one frame: which body is the subject."""

    state: SubjectLockState
    tracking_id: Optional[int] = None
    confidence: float = float("nan")
    reason: str = ""

    @property
    def is_present(self) -> bool:
        return self.tracking_id is not None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {"state": self.state.value}
        if self.tracking_id is not None:
            record["tracker_id"] = int(self.tracking_id)
        if np.isfinite(self.confidence):
            record["confidence"] = round(float(self.confidence), 4)
        if self.reason:
            record["reason"] = self.reason
        return record


class SubjectLock:
    """Follows one chosen person through a take.

    Free of Qt and of the SDK, driven only by :class:`BodyPose` objects, so the
    whole state machine is testable without a camera and behaves identically in
    the GUI and in the tests.
    """

    def __init__(
        self,
        spec: Optional[SkeletonSpec] = None,
        *,
        policy: Optional[AssociationPolicy] = None,
        subject_id: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self.policy = policy or AssociationPolicy()
        self.subject_id: Optional[str] = subject_id
        self.state = SubjectLockState.UNSELECTED
        self.tracking_id: Optional[int] = None
        self.signature = SubjectSignature()
        self.events: list[dict[str, Any]] = []
        self.candidates: list[CandidateScore] = []

        self._last_seen_position: Optional[np.ndarray] = None
        self._last_seen_timestamp_ns: Optional[int] = None
        #: How many frames in a row have disagreed with the signature while the
        #: tracker kept reporting the same id. Reset by any frame that agrees.
        self._contradiction_run = 0
        self._selection: dict[str, Any] = {}
        self._counters = {
            "locked_frames": 0,
            "lost_frames": 0,
            "ambiguous_frames": 0,
            "reassociations": 0,
            "manual_confirmations": 0,
            "multi_person_frames": 0,
            "unexpected_id_reuse": 0,
        }
        self._seen_ids: set[int] = set()
        self._retired_ids: set[int] = set()
        # Tracker ids observed in the same frame as the locked subject. Two
        # bodies visible at once are two people, so such an id can never later
        # *be* the subject. This is the cheapest and strongest evidence
        # available, and it is the one that keeps a similarly built trainer out
        # of the subject's data.
        self._covisible_ids: set[int] = set()

    # ------------------------------------------------------------ selection
    @property
    def is_selected(self) -> bool:
        return self.subject_id is not None

    def select(
        self,
        body: BodyPose,
        *,
        frame_index: int,
        timestamp_ns: int,
        method: str = "click",
        spec: Optional[SkeletonSpec] = None,
    ) -> str:
        """Lock onto ``body``. Returns the take-local subject id."""
        if spec is not None:
            self.spec = spec
        if self.subject_id is None:
            self.subject_id = new_id("subj")
        self.tracking_id = int(body.tracking_id)
        self.state = SubjectLockState.LOCKED
        self._contradiction_run = 0
        if self.spec is not None:
            # Only a resolved measurement is adopted. Taking the tracker's
            # first, half-converged frame would define the subject as a
            # fragment; the signature stays empty until a real one arrives,
            # and an empty signature simply vetoes nothing.
            measured = SubjectSignature.measure(body, self.spec)
            usable = _is_resolved(body) and measured.is_usable
            self.signature = measured if usable else SubjectSignature()
        self._remember(body, timestamp_ns)
        self._seen_ids.add(int(body.tracking_id))
        # A deliberate operator choice overrides an earlier co-visibility
        # observation: they can see who is who better than this code can.
        self._covisible_ids.discard(int(body.tracking_id))
        self._selection = {
            "subject_id": self.subject_id,
            "selected_at": utc_now_iso(),
            "frame_index": int(frame_index),
            "timestamp_ns": int(timestamp_ns),
            "initial_tracker_id": int(body.tracking_id),
            "method": method,
            "algorithm_version": self.policy.version,
        }
        self._log(
            "subject_selected",
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            new_tracker_id=int(body.tracking_id),
            method=method,
            reason="Kullanıcı kişiyi seçti.",
        )
        return self.subject_id

    def confirm(
        self, body: BodyPose, *, frame_index: int, timestamp_ns: int
    ) -> None:
        """Operator re-confirms the subject after an ambiguous stretch."""
        previous = self.tracking_id
        self.tracking_id = int(body.tracking_id)
        self.state = SubjectLockState.LOCKED
        if self.spec is not None:
            self.signature = self.signature.blend(
                SubjectSignature.measure(body, self.spec)
            )
        self._remember(body, timestamp_ns)
        self._covisible_ids.discard(int(body.tracking_id))
        self._counters["manual_confirmations"] += 1
        self._log(
            "manual_confirmation",
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            previous_tracker_id=previous,
            new_tracker_id=int(body.tracking_id),
            method="manual",
            reason="Kullanıcı kimliği elle doğruladı.",
        )

    def clear(self, *, frame_index: int = -1, timestamp_ns: int = 0) -> None:
        """Drop the selection entirely. Only ever an explicit operator action."""
        if self.subject_id is not None:
            self._log(
                "subject_cleared",
                frame_index=frame_index,
                timestamp_ns=timestamp_ns,
                previous_tracker_id=self.tracking_id,
                method="manual",
                reason="Seçim kaldırıldı.",
            )
        self.subject_id = None
        self.tracking_id = None
        self.state = SubjectLockState.UNSELECTED
        self.signature = SubjectSignature()
        self._last_seen_position = None
        self._last_seen_timestamp_ns = None
        self._selection = {}

    # -------------------------------------------------------------- update
    def update(
        self,
        bodies: Sequence[BodyPose],
        *,
        frame_index: int,
        timestamp_ns: int,
    ) -> FrameAssociation:
        """Decide, for this frame, which body is the subject.

        Never returns a body the lock is not confident about. When it cannot
        decide it returns no body at all, and the frame is recorded as
        subject-absent - which is a truthful gap, unlike a plausible stranger.
        """
        self.candidates = []
        if len(bodies) > 1:
            self._counters["multi_person_frames"] += 1
        if not self.is_selected:
            return FrameAssociation(SubjectLockState.UNSELECTED)

        present = {int(body.tracking_id): body for body in bodies}
        self._seen_ids.update(present)
        if self.state is SubjectLockState.AMBIGUOUS:
            self._counters["ambiguous_frames"] += 1
            return FrameAssociation(SubjectLockState.AMBIGUOUS, None, float("nan"), "awaiting_confirmation")

        # --- the easy, overwhelmingly common case ----------------------
        if self.tracking_id is not None and self.tracking_id in present:
            body = present[self.tracking_id]
            gap = self._gap_seconds(timestamp_ns)
            point = _root_position(body, self.spec) if self.spec is not None else None
            contradiction = gap > self.policy.give_up_seconds
            if point is not None and self._last_seen_position is not None:
                contradiction |= float(np.linalg.norm(point-self._last_seen_position)) > max(0.5, self.policy.plausible_speed*gap)
            # Body proportions are evidence about *which person* this is, so
            # they can only overrule the tracker when there is another person
            # for it to be. One body in the frame, carrying the subject's own
            # id, leaves no competing hypothesis - and what did change is the
            # measurement, not the person: the ZED re-fits its model every
            # frame and its output moves with posture. In the 16 September
            # squat take the same person measured a 1.709 m joint extent
            # standing and 1.064 m at the bottom of a squat, with thigh length
            # moving 25%. Vetoing there protected nobody and cost 1409 frames
            # of the exercise the recording exists to capture.
            if (
                len(present) > 1
                and self.spec is not None
                and self.signature.is_usable
                and _is_resolved(body)
            ):
                limb, stature = self.signature.similarity(SubjectSignature.measure(body, self.spec))
                contradiction |= any(math.isfinite(v) and v < 0.3 for v in (limb, stature))
            if contradiction:
                self._contradiction_run += 1
                if self._contradiction_run < self.policy.contradiction_frames:
                    # One frame that disagrees is tracker noise, not a person
                    # swapping places with another. The frame is still recorded
                    # as subject-absent - nothing is guessed - but the lock is
                    # kept so the next frame can settle it. Giving up here is
                    # what turned one bad frame into 1638 unusable ones.
                    self.state = SubjectLockState.TEMPORARILY_LOST
                    self._counters["lost_frames"] += 1
                    return FrameAssociation(
                        self.state, None, float("nan"), "evidence_conflict_pending"
                    )
                self.state = SubjectLockState.AMBIGUOUS
                self._counters["ambiguous_frames"] += 1
                self._log("same_id_evidence_conflict", frame_index=frame_index, timestamp_ns=timestamp_ns)
                return FrameAssociation(self.state, None, float("nan"), "same_id_evidence_conflict")
            self._contradiction_run = 0
            if body.tracking_state.value not in ("ok", "off") or not body.valid_joint_mask.any():
                self.state = SubjectLockState.TEMPORARILY_LOST
                self._counters["lost_frames"] += 1
                return FrameAssociation(self.state, None, float("nan"), "tracking_unusable")
            if self.state is not SubjectLockState.LOCKED:
                self._log(
                    "subject_reacquired_same_id",
                    frame_index=frame_index,
                    timestamp_ns=timestamp_ns,
                    new_tracker_id=self.tracking_id,
                    method="same_tracker_id",
                    reason=(
                        "Aynı tracker kimliği geri döndü; SDK track'i sürdürdü."
                    ),
                )
            self.state = SubjectLockState.LOCKED
            if self.spec is not None and _is_resolved(body):
                measured = SubjectSignature.measure(body, self.spec)
                # An unconverged frame contributes nothing: averaging it in
                # would drag the subject's proportions towards a fragment.
                if measured.is_usable:
                    self.signature = self.signature.blend(measured)
            self._remember(body, timestamp_ns)
            # Everyone else on screen right now is, provably, not the subject.
            self._covisible_ids.update(
                identity for identity in present if identity != self.tracking_id
            )
            self._counters["locked_frames"] += 1
            return FrameAssociation(
                SubjectLockState.LOCKED, self.tracking_id, 1.0, "same_tracker_id"
            )

        # --- the subject's id is not on screen -------------------------
        if self.tracking_id is not None:
            self._retired_ids.add(self.tracking_id)
        gap = self._gap_seconds(timestamp_ns)

        if not bodies:
            self.state = SubjectLockState.TEMPORARILY_LOST
            self._counters["lost_frames"] += 1
            return FrameAssociation(
                SubjectLockState.TEMPORARILY_LOST, None, float("nan"), "no_body"
            )

        if self.state is SubjectLockState.AMBIGUOUS:
            # Do not keep re-deciding; wait for the operator.
            self._counters["ambiguous_frames"] += 1
            return FrameAssociation(
                SubjectLockState.AMBIGUOUS, None, float("nan"), "awaiting_confirmation"
            )

        if gap <= self.policy.lost_grace_seconds:
            # Give the tracker its usual chance to come back with the same id.
            self.state = SubjectLockState.TEMPORARILY_LOST
            self._counters["lost_frames"] += 1
            return FrameAssociation(
                SubjectLockState.TEMPORARILY_LOST, None, float("nan"), "grace_period"
            )

        self.state = SubjectLockState.REIDENTIFYING
        scored = self._score_candidates(bodies, gap)
        self.candidates = scored
        if not scored:
            self._counters["lost_frames"] += 1
            return FrameAssociation(
                SubjectLockState.TEMPORARILY_LOST, None, float("nan"), "no_evidence"
            )

        eligible = [c for c in scored if c.tracking_id not in self._covisible_ids]
        if not eligible:
            self.state = SubjectLockState.AMBIGUOUS
            self._counters["ambiguous_frames"] += 1
            self._log(
                "reassociation_refused",
                frame_index=frame_index,
                timestamp_ns=timestamp_ns,
                method="auto",
                reason=(
                    "Kadraftaki bütün adaylar daha önce seçili kişiyle aynı "
                    "karede görülmüştü; tanım gereği başka kişilerdir."
                ),
                candidates=[c.to_dict() for c in scored[:3]],
            )
            return FrameAssociation(
                SubjectLockState.AMBIGUOUS, None, float("nan"), "only_other_people"
            )

        best = eligible[0]
        runner_up = eligible[1].score if len(eligible) > 1 else 0.0
        margin = best.score - runner_up

        if gap > self.policy.give_up_seconds:
            self.state = SubjectLockState.AMBIGUOUS
            self._counters["ambiguous_frames"] += 1
            self._log(
                "reassociation_refused",
                frame_index=frame_index,
                timestamp_ns=timestamp_ns,
                method="auto",
                score=best.score,
                margin=margin,
                reason=(
                    f"Kişi {gap:.1f} sn görünmedi; bu süre sonunda konum ve "
                    "oran kanıtı tek başına yeterli sayılmıyor."
                ),
                candidates=[c.to_dict() for c in scored[:3]],
            )
            return FrameAssociation(
                SubjectLockState.AMBIGUOUS, None, float("nan"), "gap_too_long"
            )

        if best.score < self.policy.min_score or margin < self.policy.min_margin:
            self.state = SubjectLockState.AMBIGUOUS
            self._counters["ambiguous_frames"] += 1
            self._log(
                "reassociation_refused",
                frame_index=frame_index,
                timestamp_ns=timestamp_ns,
                method="auto",
                score=best.score,
                margin=margin,
                reason=(
                    "Kanıt yetersiz veya iki aday birbirine çok yakın; "
                    "yanlış kişiye geçmemek için beklendi."
                ),
                candidates=[c.to_dict() for c in eligible[:3]],
            )
            return FrameAssociation(
                SubjectLockState.AMBIGUOUS, None, float("nan"), "insufficient_evidence"
            )

        previous = self.tracking_id
        if best.tracking_id in self._retired_ids and best.tracking_id != previous:
            # The SDK reused a number this take had already retired. Accept it
            # only because the evidence carried it, and say so.
            self._counters["unexpected_id_reuse"] += 1
        self.tracking_id = best.tracking_id
        self.state = SubjectLockState.LOCKED
        body = present[best.tracking_id]
        if self.spec is not None:
            self.signature = self.signature.blend(
                SubjectSignature.measure(body, self.spec)
            )
        self._remember(body, timestamp_ns)
        self._counters["reassociations"] += 1
        self._counters["locked_frames"] += 1
        self._log(
            "reassociated",
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            previous_tracker_id=previous,
            new_tracker_id=best.tracking_id,
            method="auto",
            score=best.score,
            margin=margin,
            reason=(
                f"{gap:.2f} sn boşluktan sonra konum, uzuv oranı ve boy "
                "kanıtı eşiği ve farkı geçti; aday daha önce seçili kişiyle "
                "aynı karede görülmemişti."
            ),
            candidates=[c.to_dict() for c in eligible[:3]],
        )
        return FrameAssociation(
            SubjectLockState.LOCKED, best.tracking_id, best.score, "reassociated"
        )

    # ------------------------------------------------------------- scoring
    def _score_candidates(
        self, bodies: Sequence[BodyPose], gap_seconds: float
    ) -> list[CandidateScore]:
        policy = self.policy
        scored: list[CandidateScore] = []
        for body in bodies:
            position_score = float("nan")
            distance = float("nan")
            if (
                self._last_seen_position is not None
                and gap_seconds <= policy.position_evidence_seconds
                and self.spec is not None
            ):
                point = _root_position(body, self.spec)
                if point is not None:
                    distance = float(
                        np.linalg.norm(point - self._last_seen_position)
                    )
                    reach = max(0.05, policy.plausible_speed * max(gap_seconds, 1 / 30))
                    position_score = float(max(0.0, 1.0 - distance / reach))

            limb_score, stature_score = float("nan"), float("nan")
            if self.spec is not None and self.signature.is_usable:
                limb_score, stature_score = self.signature.similarity(
                    SubjectSignature.measure(body, self.spec)
                )

            terms = [
                (position_score, policy.weight_position),
                (limb_score, policy.weight_limb_ratio),
                (stature_score, policy.weight_stature),
            ]
            usable = [(value, weight) for value, weight in terms if not math.isnan(value)]
            if not usable:
                continue
            total_weight = sum(weight for _value, weight in usable)
            score = sum(value * weight for value, weight in usable) / total_weight
            # Evidence that is missing is not evidence in favour: a candidate
            # judged on one term alone is discounted rather than trusted.
            coverage = total_weight / (
                policy.weight_position + policy.weight_limb_ratio + policy.weight_stature
            )
            scored.append(
                CandidateScore(
                    tracking_id=int(body.tracking_id),
                    score=float(score * coverage),
                    position_score=position_score,
                    limb_score=limb_score,
                    stature_score=stature_score,
                    distance=distance,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored

    # ------------------------------------------------------------- helpers
    def _remember(self, body: BodyPose, timestamp_ns: int) -> None:
        if self.spec is not None:
            point = _root_position(body, self.spec)
            if point is not None:
                self._last_seen_position = point
        self._last_seen_timestamp_ns = int(timestamp_ns)

    def _gap_seconds(self, timestamp_ns: int) -> float:
        if self._last_seen_timestamp_ns is None:
            return float("inf")
        return max(0.0, (int(timestamp_ns) - self._last_seen_timestamp_ns) / 1e9)

    def _log(self, event: str, **payload: Any) -> None:
        record = {
            "event": event,
            "subject_id": self.subject_id,
            "at": utc_now_iso(),
            "algorithm_version": self.policy.version,
        }
        record.update({k: v for k, v in payload.items() if v is not None})
        self.events.append(record)

    # -------------------------------------------------------------- report
    @property
    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def provenance(self) -> dict[str, Any]:
        """Everything a consumer needs to judge how the subject was followed."""
        return {
            "subject_id": self.subject_id,
            "state": self.state.value,
            "current_tracker_id": self.tracking_id,
            "selection": dict(self._selection),
            "policy": self.policy.to_dict(),
            "signature": self.signature.to_dict(),
            "counters": self.counters,
            "events": list(self.events),
            "distinct_tracker_ids_seen": sorted(self._seen_ids),
            "disqualified_tracker_ids": sorted(self._covisible_ids),
            "privacy": (
                "Kişi eşleştirmesi yalnız bu kayıt içinde geçerlidir. Yüz "
                "tanıma, görünüm gömülmesi veya kayıtlar arası biyometrik "
                "kimlik veritabanı kullanılmaz."
            ),
            "guarantee": (
                "Sistem belirsizken başka kişiye geçmez. Seçili kişiyle aynı "
                "karede görülmüş bir tracker kimliği bir daha seçili kişi "
                "olamaz. Otomatik yeniden eşleştirme yalnız eşik ve fark "
                "koşulunu sağlayan kanıtla yapılır; aksi hâlde kareler "
                "subject-absent kalır."
            ),
        }


def pick_body_at_pixel(
    bodies: Iterable[BodyPose],
    x: float,
    y: float,
    *,
    radius: float = 60.0,
    spec: Optional[SkeletonSpec] = None,
    projector: Optional[Any] = None,
) -> tuple[Optional[BodyPose], list[tuple[BodyPose, float]]]:
    """Which detected person is at image pixel ``(x, y)``?

    Uses the tracker's own 2D keypoints when the recording has them, which is
    exact. Otherwise a caller-supplied projector is used and the result is an
    approximation - the caller is expected to say so in the UI.

    Returns the best body and every candidate with its distance, so a caller
    facing two people standing on top of each other can present a choice
    instead of guessing.
    """
    candidates: list[tuple[BodyPose, float]] = []
    for body in bodies:
        points = body.joint_positions_2d
        if points is None and projector is not None and spec is not None:
            points = projector(body)
        if points is None:
            continue
        array = np.asarray(points, dtype=np.float64)
        finite = array[np.isfinite(array).all(axis=1)]
        if finite.shape[0] == 0:
            continue
        distances = np.linalg.norm(finite - np.asarray([x, y]), axis=1)
        candidates.append((body, float(distances.min())))
    candidates.sort(key=lambda item: item[1])
    if not candidates or candidates[0][1] > radius:
        return None, candidates
    return candidates[0][0], candidates


def is_ambiguous_pick(
    candidates: Sequence[tuple[BodyPose, float]], *, separation: float = 25.0
) -> bool:
    """True when two people are too close together to pick by clicking.

    Rather than taking the nearest by a pixel or two, the caller is expected to
    ask which one was meant.
    """
    if len(candidates) < 2:
        return False
    return abs(candidates[1][1] - candidates[0][1]) < separation


__all__ = [
    "ASSOCIATION_ALGORITHM_VERSION",
    "AssociationPolicy",
    "CandidateScore",
    "FrameAssociation",
    "SubjectLock",
    "SubjectLockState",
    "SubjectSignature",
    "is_ambiguous_pick",
    "pick_body_at_pixel",
]
