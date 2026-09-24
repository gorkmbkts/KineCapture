"""The synthetic chain the release gate drives: record, process, label.

Every step goes through the services the Studio screens call - the same
writer, the same offline processing, the same annotation and subject stores -
so a package built from these versions has travelled the road a real one does.
Mock camera only; nothing here opens hardware or touches the user's data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.jsonio import write_json
from kinecapture.dataset.workspace import ProjectWorkspace, TakePaths
from kinecapture.domain.enums import ConsentStatus
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import CaptureProfile, Session, Take
from kinecapture.processing import ProcessingConfig, process_take
from kinecapture.processing.annotations import JointStatus, RolesOrigin
from kinecapture.processing.sources import SyntheticSource
from kinecapture.processing.subject_review import (
    Verdict,
    load_subject_review,
    scan_candidates,
    scan_unsettled,
)
from kinecapture.recording.take_writer import TakeWriter
from kinecapture.studio.services.annotation_store import AnnotationStore
from kinecapture.studio.services.review import ReviewSession
from kinecapture.studio.services.subject_store import SubjectStore


def new_session(workspace: ProjectWorkspace) -> Session:
    """A fresh anonymous participant and a sitting for them."""
    participant = workspace.create_participant()
    return workspace.create_session(
        participant.participant_id,
        operator="release-gate",
        consent=ConsentStatus.GRANTED,
        capture_profile=CaptureProfile(fps=30, min_free_disk_minutes=0),
    )


def record(
    workspace: ProjectWorkspace,
    session: Session,
    *,
    frames: int = 60,
    seed: int = 7,
    low_confidence_every: int = 0,
) -> tuple[Take, TakePaths]:
    """Record ``frames`` synthetic frames exactly the way capture does."""
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(
        width=160,
        height=120,
        fps=30,
        seed=seed,
        profile=profile,
        low_confidence_every=low_confidence_every,
    )
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(frames):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()
    return take, paths


def process(
    paths: TakePaths,
    take: Take,
    *,
    body_format: str = "BODY_38",
    mark_subject: bool = True,
) -> Path:
    """Offline processing into a published ``run_<id>``.

    ``mark_subject`` puts the operator's click on the person in the first
    frame, the way capture does before recording. Without it the version is
    published with nobody tracked, which is its own refusal.
    """
    config = ProcessingConfig(body_format=body_format, store_depth=False, store_proxy=False)
    if mark_subject:
        source = SyntheticSource(paths, take, config.profile(take))
        packet = next(iter(source))
        points = packet.bodies[0].joint_positions_2d
        write_json(
            paths.raw_dir / "subject_anchors.json",
            [{
                "camera_timestamp_ns": packet.camera_timestamp_ns,
                "source_resolution": list(packet.resolution),
                "point_xy": np.nanmean(points, axis=0).tolist(),
                "bbox_xyxy": np.r_[np.nanmin(points, axis=0), np.nanmax(points, axis=0)].tolist(),
            }],
        )
        source.close()
    run = process_take(paths.root, config)
    assert not run.name.startswith("."), f"version was not published: {run}"
    return run


@dataclass
class Labeller:
    """The labelling screen, without the screen."""

    run_dir: Path
    schema: LabelSchema
    annotator: str = "Görkem Bektaş"
    review: ReviewSession = field(init=False)
    store: AnnotationStore = field(init=False)

    def __post_init__(self) -> None:
        self.review = ReviewSession.open(self.run_dir)
        self.store = AnnotationStore(
            take_dir=self.review.take_dir,
            document=self.review.dataset.load_annotations(),
            annotator=self.annotator,
            resolve=self.review.dataset.position_of_anchor,
            anchor_at=self.review.dataset.anchor_at,
            frames=self.review.frames,
            known_exercises=self.schema.exercise_codes(),
            known_error_classes=self.schema.error_type_codes(),
            skeleton=self.review.skeleton,
        )

    # ------------------------------------------------------------- movements
    def movement(
        self,
        start: int,
        end: int,
        exercise: str = "",
        *,
        reviewed: bool = True,
        note: str = "",
        excluded: bool = False,
    ) -> str:
        sample = self.store.add_movement(start, end)
        if exercise:
            self.store.label_movement(sample.sample_id, exercise, note=note, reviewed=reviewed)
        if excluded:
            self.store.set_excluded(sample.sample_id, True)
        return sample.sample_id

    def error(
        self,
        sample_id: str,
        start: int,
        end: int,
        error_class: str = "",
        *,
        roles: Sequence[str] = (),
        status: JointStatus = JointStatus.UNREVIEWED,
        origin: RolesOrigin = RolesOrigin.UNKNOWN,
        revision: int = 0,
        note: str = "",
    ) -> str:
        interval = self.store.add_error(sample_id, start, end)
        if error_class:
            self.store.label_error(
                sample_id,
                interval.interval_id,
                error_class=error_class,
                affected_roles=tuple(roles),
                joint_status=status,
                roles_origin=origin,
                roles_revision=revision,
                note=note,
            )
        return interval.interval_id

    # --------------------------------------------------------------- athlete
    def choose_athlete(self) -> None:
        frames = self.review.dataset.stream.frames
        subject = SubjectStore(
            take_dir=self.review.take_dir,
            document=load_subject_review(
                self.review.take_dir, self.review.run_id, self.review.source_fingerprint
            ),
            candidates=scan_candidates(frames),
            annotator=self.annotator,
        )
        subject.set_intervals(scan_unsettled(frames, self.review.dataset.anchor_at))
        subject.choose_athlete(subject.candidates[0].tracker_id)
        if subject.document.unanswered:
            subject.answer_all_remaining(Verdict.SAME_ATHLETE)
        subject.flush()

    def close(self) -> None:
        self.store.flush()
        self.review.close()

    def __enter__(self) -> "Labeller":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def schema_file(workspace: ProjectWorkspace) -> dict:
    import json

    return json.loads(Path(workspace.label_schema_file).read_text(encoding="utf-8"))


def project_file(workspace: ProjectWorkspace) -> dict:
    import json

    return json.loads(Path(workspace.project_file).read_text(encoding="utf-8"))


__all__ = [
    "Labeller",
    "new_session",
    "process",
    "project_file",
    "record",
    "schema_file",
]
