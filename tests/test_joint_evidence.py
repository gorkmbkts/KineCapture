"""Which joints an error is about: storage, validation and history.

The field is node-level *evidence*, not a second classifier output, and the
rules that keep it honest live below the GUI: four distinct empty meanings that
must never collapse into each other, a legacy field that must survive being
opened by a version that cannot interpret it, and one undo step per decision.
"""

from __future__ import annotations

import json

import pytest

from kinecapture.annotations.repository import AnnotationRepository
from kinecapture.capture.service import CaptureService
from kinecapture.core.errors import ValidationError
from kinecapture.domain.enums import (
    Correctness,
    JointAnnotationStatus,
    SampleReadiness,
    SegmentStatus,
)
from kinecapture.domain.project import ErrorInterval, normalise_roles
from kinecapture.features.roles import ALL_ROLES
from kinecapture.playback.take_reader import load_take
from kinecapture.visualization.skeleton_spec import try_get_skeleton_spec
from tests.conftest import paced_backend, record_take


@pytest.fixture
def repository(workspace, session):
    service = CaptureService(paced_backend())
    service.connect()
    take = record_take(service, workspace, session, frames=40, exercise="squat")
    service.shutdown()
    loaded = load_take(workspace, take)

    schema = workspace.label_schema
    schema.add_exercise("Squat")
    schema.add_error_type("Diz içe çöküyor")
    schema.add_error_type("Sırt yuvarlanıyor")
    workspace.save_label_schema(schema)

    repo = AnnotationRepository(
        workspace, take, frame_count=loaded.frame_count, annotator="pytest"
    )
    yield repo
    loaded.close()


@pytest.fixture
def interval(repository):
    """One labelled movement holding one classified error interval."""
    sample = repository.create_sample(4, 30)
    repository.label_sample(sample.sample_id, exercise="squat", reviewed=True)
    return sample, repository.create_error_interval(
        sample.sample_id, 8, 18, error_code="diz-ice-cokuyor"
    )


def segments_path(repository):
    paths = repository.workspace.take_paths(repository.take)
    return paths.annotations_dir / "segments.json"


# ------------------------------------------------------- the four meanings


def test_a_fresh_interval_is_unreviewed_not_empty() -> None:
    """Nobody looked, and looked-found-nothing, are different facts."""
    fresh = ErrorInterval.create(0, 10, "k")
    assert fresh.joint_status is JointAnnotationStatus.UNREVIEWED
    assert fresh.affected_roles == ()
    assert not fresh.has_node_supervision


@pytest.mark.parametrize(
    "status, supervises, reviewed",
    [
        (JointAnnotationStatus.SELECTED, True, True),
        (JointAnnotationStatus.NOT_APPLICABLE, False, True),
        (JointAnnotationStatus.INDETERMINATE, False, True),
        (JointAnnotationStatus.UNREVIEWED, False, False),
    ],
)
def test_each_status_says_what_training_may_do_with_it(
    status, supervises, reviewed
) -> None:
    assert status.supervises_nodes is supervises
    assert status.is_reviewed is reviewed


def test_the_two_explicit_empties_stay_distinguishable_on_disk() -> None:
    """Both have no roles; only the status separates them."""
    nothing = ErrorInterval.create(0, 10, "k")
    nothing.set_affected_joints("not_applicable")
    unclear = ErrorInterval.create(0, 10, "k")
    unclear.set_affected_joints("indeterminate")

    assert nothing.affected_roles == unclear.affected_roles == ()
    assert nothing.to_dict()["joint_status"] == "not_applicable"
    assert unclear.to_dict()["joint_status"] == "indeterminate"
    assert (
        ErrorInterval.from_dict(nothing.to_dict()).joint_status
        is JointAnnotationStatus.NOT_APPLICABLE
    )
    assert (
        ErrorInterval.from_dict(unclear.to_dict()).joint_status
        is JointAnnotationStatus.INDETERMINATE
    )


def test_a_selection_without_joints_is_refused() -> None:
    interval = ErrorInterval.create(0, 10, "k")
    with pytest.raises(ValidationError) as excinfo:
        interval.set_affected_joints("selected", [])
    assert excinfo.value.code == "joint_status_without_roles"
    assert interval.joint_status is JointAnnotationStatus.UNREVIEWED, "unchanged"


@pytest.mark.parametrize("status", ["not_applicable", "indeterminate", "unreviewed"])
def test_joints_without_a_selection_are_refused(status) -> None:
    interval = ErrorInterval.create(0, 10, "k")
    with pytest.raises(ValidationError) as excinfo:
        interval.set_affected_joints(status, ["left_knee"])
    assert excinfo.value.code == "roles_without_selected_status"


def test_an_unknown_role_name_is_refused_rather_than_stored() -> None:
    with pytest.raises(ValidationError) as excinfo:
        normalise_roles(["left_knee", "elbow_ish"])
    assert excinfo.value.code == "unknown_anatomical_role"


def test_roles_are_deduped_and_ordered_canonically() -> None:
    """Two annotators clicking the same joints must produce one file."""
    assert normalise_roles(["left_knee", "chest", "left_knee"]) == (
        "chest",
        "left_knee",
    )
    assert normalise_roles(["right_ankle", "pelvis"]) == ("pelvis", "right_ankle")
    assert normalise_roles(list(reversed(ALL_ROLES))) == ALL_ROLES


# ----------------------------------------------------------- the round trip


def test_several_joints_survive_a_save_and_reload(repository, interval) -> None:
    sample, error = interval
    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="selected",
        affected_roles=["right_knee", "left_knee", "pelvis"],
    )
    repository.save()

    raw = json.loads(segments_path(repository).read_text(encoding="utf-8"))
    stored = raw["samples"][0]["error_intervals"][0]
    assert stored["joint_status"] == "selected"
    assert stored["affected_roles"] == ["pelvis", "left_knee", "right_knee"]

    reloaded = AnnotationRepository(
        repository.workspace, repository.take, frame_count=40, annotator="pytest"
    )
    back = reloaded.samples[0].error_intervals[0]
    assert back.joint_status is JointAnnotationStatus.SELECTED
    assert back.affected_roles == ("pelvis", "left_knee", "right_knee")
    assert back.has_node_supervision


def test_the_note_and_class_and_joints_are_one_undo_step(repository, interval) -> None:
    """One Save is one decision; three undo steps would misdescribe it."""
    sample, error = interval
    repository.save()

    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        error_code="sirt-yuvarlaniyor",
        note="sol tarafta belirgin",
        joint_status="selected",
        affected_roles=["left_knee"],
    )

    assert repository.can_undo
    assert repository.undo()
    restored = repository.samples[0].error_intervals[0]
    assert restored.error_code == "diz-ice-cokuyor"
    assert restored.note == ""
    assert restored.joint_status is JointAnnotationStatus.UNREVIEWED
    assert restored.affected_roles == ()

    assert repository.redo()
    again = repository.samples[0].error_intervals[0]
    assert again.error_code == "sirt-yuvarlaniyor"
    assert again.note == "sol tarafta belirgin"
    assert again.affected_roles == ("left_knee",)
    assert not repository.redo(), "exactly one step, not three"


def test_saving_the_same_answer_twice_makes_no_history(repository, interval) -> None:
    sample, error = interval
    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="selected",
        affected_roles=["left_knee"],
    )
    marker = repository.samples[0].error_intervals[0].updated_at

    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="selected",
        affected_roles=["left_knee"],
    )
    assert repository.samples[0].error_intervals[0].updated_at == marker
    assert repository.undo()
    assert repository.samples[0].error_intervals[0].affected_roles == ()


def test_a_rejected_edit_changes_nothing_at_all(repository, interval) -> None:
    """Validation runs on a copy, so a refusal cannot half-apply."""
    sample, error = interval
    with pytest.raises(ValidationError):
        repository.update_error_interval(
            sample.sample_id,
            error.interval_id,
            error_code="sirt-yuvarlaniyor",
            joint_status="selected",
            affected_roles=[],
        )
    unchanged = repository.samples[0].error_intervals[0]
    assert unchanged.error_code == "diz-ice-cokuyor"
    assert unchanged.joint_status is JointAnnotationStatus.UNREVIEWED


def test_a_role_the_take_does_not_have_is_refused(repository, interval) -> None:
    """mock_16 has no heel joint; storing one would point at no node."""
    sample, error = interval
    with pytest.raises(ValidationError) as excinfo:
        repository.update_error_interval(
            sample.sample_id,
            error.interval_id,
            joint_status="selected",
            affected_roles=["left_heel"],
            skeleton_spec=try_get_skeleton_spec("mock_16"),
        )
    assert excinfo.value.code == "role_not_in_skeleton"
    assert "mock_16" in str(excinfo.value)


def test_deleting_the_interval_takes_its_joints_with_it(repository, interval) -> None:
    sample, error = interval
    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="selected",
        affected_roles=["left_knee"],
    )
    repository.delete_error_interval(sample.sample_id, error.interval_id)
    assert repository.samples[0].error_intervals == []
    assert repository.undo()
    assert repository.samples[0].error_intervals[0].affected_roles == ("left_knee",)


# ------------------------------------------------------- backward compatible


def test_an_old_single_joint_file_is_read_without_being_rewritten() -> None:
    """The legacy field is interpreted *and* kept, verbatim."""
    legacy = {
        "interval_id": "e1",
        "start_frame": 3,
        "end_frame": 9,
        "error_code": "diz-ice-cokuyor",
        "affected_joints": ["left_knee"],
    }
    interval = ErrorInterval.from_dict(legacy)
    assert interval.affected_roles == ("left_knee",)
    assert interval.joint_status is JointAnnotationStatus.SELECTED

    written = interval.to_dict()
    assert written["legacy"]["affected_joints"] == ["left_knee"]
    assert ErrorInterval.from_dict(written).affected_roles == ("left_knee",)


def test_an_unmappable_legacy_value_is_preserved_not_guessed() -> None:
    """A half migration would look finished. All or nothing."""
    legacy = {
        "interval_id": "e2",
        "start_frame": 3,
        "end_frame": 9,
        "affected_joints": ["left_knee", "sol dizin biraz üstü"],
    }
    interval = ErrorInterval.from_dict(legacy)
    assert interval.joint_status is JointAnnotationStatus.UNREVIEWED
    assert interval.affected_roles == ()
    assert interval.to_dict()["legacy"]["affected_joints"] == [
        "left_knee",
        "sol dizin biraz üstü",
    ]


def test_opening_an_old_take_does_not_touch_its_file(repository, interval) -> None:
    """Reading is not editing: no autosave, no dirty flag, no rewrite."""
    repository.save()
    path = segments_path(repository)
    before = path.read_bytes()
    mtime = path.stat().st_mtime_ns

    reopened = AnnotationRepository(
        repository.workspace, repository.take, frame_count=40, annotator="pytest"
    )
    assert not reopened.is_dirty
    assert not reopened.can_undo
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_a_status_this_version_does_not_know_falls_back_to_unreviewed() -> None:
    """An unknown word must not be read as a decision somebody made."""
    interval = ErrorInterval.from_dict(
        {
            "interval_id": "e3",
            "start_frame": 1,
            "end_frame": 5,
            "joint_status": "probably_the_knee",
        }
    )
    assert interval.joint_status is JointAnnotationStatus.UNREVIEWED
    assert (
        JointAnnotationStatus.parse(JointAnnotationStatus.SELECTED)
        is JointAnnotationStatus.SELECTED
    )
    assert JointAnnotationStatus.parse(None) is JointAnnotationStatus.UNREVIEWED


# --------------------------------------------------- separate from readiness


def test_a_take_is_export_ready_with_no_joints_reviewed(repository, interval) -> None:
    """Node evidence is optional supervision, not a gate on temporal labels."""
    sample, _error = interval
    reviewed = repository.find(sample.sample_id)
    assert repository.readiness(reviewed) is SampleReadiness.READY
    assert reviewed.derived_correctness is Correctness.INCORRECT
    assert repository.joint_annotation_counts()["unreviewed"] == 1


def test_the_counts_report_coverage_per_status(repository) -> None:
    sample = repository.create_sample(2, 34)
    repository.label_sample(sample.sample_id, exercise="squat", reviewed=True)
    plan = [
        ("selected", ["left_knee"]),
        ("not_applicable", []),
        ("indeterminate", []),
        (None, []),
    ]
    for index, (status, roles) in enumerate(plan):
        error = repository.create_error_interval(
            sample.sample_id,
            3 + index * 6,
            6 + index * 6,
            error_code="diz-ice-cokuyor",
        )
        if status is not None:
            repository.update_error_interval(
                sample.sample_id,
                error.interval_id,
                joint_status=status,
                affected_roles=roles,
            )

    assert repository.joint_annotation_counts() == {
        "selected": 1,
        "not_applicable": 1,
        "indeterminate": 1,
        "unreviewed": 1,
    }


def test_an_excluded_movement_is_left_out_of_the_counts(repository) -> None:
    sample = repository.create_sample(2, 20)
    error = repository.create_error_interval(
        sample.sample_id, 4, 10, error_code="diz-ice-cokuyor"
    )
    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="selected",
        affected_roles=["left_knee"],
    )
    assert repository.joint_annotation_counts()["selected"] == 1

    repository.set_sample_status(sample.sample_id, SegmentStatus.EXCLUDED)
    assert repository.joint_annotation_counts()["selected"] == 0


# ------------------------------------------------------- dataset visibility


def test_the_dataset_summary_reports_joint_coverage(repository) -> None:
    """Coverage is a separate number, never folded into readiness."""
    from kinecapture.dataset.index import DatasetIndex

    sample = repository.create_sample(2, 34)
    repository.label_sample(sample.sample_id, exercise="squat", reviewed=True)
    for index, (status, roles) in enumerate(
        [("selected", ["left_knee"]), ("not_applicable", []), (None, [])]
    ):
        error = repository.create_error_interval(
            sample.sample_id,
            3 + index * 8,
            8 + index * 8,
            error_code="diz-ice-cokuyor",
        )
        if status is not None:
            repository.update_error_interval(
                sample.sample_id,
                error.interval_id,
                joint_status=status,
                affected_roles=roles,
            )
    repository.save()

    summary = DatasetIndex(repository.workspace).refresh(force=True).summary()
    assert summary.intervals_with_joints == 1
    assert summary.intervals_missing_joint_review == 1
    assert summary.takes_missing_joint_review == 1
    # All four keys are always present, zeros included: a dashboard that
    # simply omits a state cannot be read as "none in that state".
    assert summary.joint_status_counts == {
        "selected": 1,
        "not_applicable": 1,
        "indeterminate": 0,
        "unreviewed": 1,
    }


def test_a_take_with_every_interval_reviewed_is_not_counted_as_pending(
    repository,
) -> None:
    from kinecapture.dataset.index import DatasetIndex

    sample = repository.create_sample(2, 34)
    repository.label_sample(sample.sample_id, exercise="squat", reviewed=True)
    error = repository.create_error_interval(
        sample.sample_id, 4, 12, error_code="diz-ice-cokuyor"
    )
    repository.update_error_interval(
        sample.sample_id,
        error.interval_id,
        joint_status="indeterminate",
    )
    repository.save()

    summary = DatasetIndex(repository.workspace).refresh(force=True).summary()
    assert summary.takes_missing_joint_review == 0
    assert summary.intervals_missing_joint_review == 0
    # Reviewed but deliberately empty: it is not pending, and it is not
    # positive node evidence either.
    assert summary.intervals_with_joints == 0
    assert summary.joint_status_counts == {
        "selected": 0,
        "not_applicable": 0,
        "indeterminate": 1,
        "unreviewed": 0,
    }
