"""Labelling joints on every body format the pipeline can produce.

The concern is specific and it is about data, not looks: a fault class is
stored as **role names**, and the formats do not have the same joints.

* ``BODY_18`` has 18 joints and names 14 of them. It has no pelvis, no spine,
  no head centre, no hands, no feet, no heels, no clavicles.
* ``BODY_34`` has 34 and names 26 - every role - leaving the thumbs,
  fingertips, eyes and ears unnamed.
* ``BODY_38`` has 38 and names 23. It has no head centre and no hand joint,
  and fifteen of its joints are face landmarks, finger segments or small toes.

Two ways that can go wrong quietly, and both are checked here:

**Picking a joint the format does not name.** The view draws all 38; only 23
mean something. Selecting one and storing the rest would give a count the
record cannot keep.

**Applying a class across formats.** A class defined while a BODY_34
recording was open can name ``head`` and ``left_hand``. Written onto a
BODY_38 version, those are claims about joints that recording does not
contain.

Every format here is produced by really reprocessing the same take, which is
also the answer to "can old recordings be reprocessed into the other
formats" - if this file passes, they can.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.errors import ValidationError  # noqa: E402
from kinecapture.features.roles import ALL_ROLES, resolve_roles  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.annotations import (  # noqa: E402
    AnnotationDocument,
    JointStatus,
    RolesOrigin,
)
from kinecapture.studio.services.annotation_store import AnnotationStore  # noqa: E402
from kinecapture.visualization.skeleton_spec import (  # noqa: E402
    MOCK_SKELETON,
    REHAB24_6_MOCAP,
    ZED_BODY_18,
    ZED_BODY_34,
    ZED_BODY_38,
)

from _gui_harness import (  # noqa: E402
    double_click,
    joint_screen_position,
    open_review,
    record_and_process,
    use_known_pose,
)

#: Every skeleton the application knows how to draw.
ALL_SPECS = (ZED_BODY_18, ZED_BODY_34, ZED_BODY_38, MOCK_SKELETON, REHAB24_6_MOCAP)

#: The formats the capture and processing pipeline can actually produce.
PIPELINE_FORMATS = ("BODY_18", "BODY_34", "BODY_38")


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------- the tables alone


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.name)
def test_every_format_has_a_role_table(spec) -> None:
    """Falling back to name matching is a silent guess for a format whose
    joint names use another vocabulary."""
    from kinecapture.features.roles import _ROLE_TABLES

    assert spec.name in _ROLE_TABLES


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.name)
def test_a_role_points_at_a_joint_whose_name_agrees_with_it(spec) -> None:
    """The cheapest way to catch a mis-typed table.

    A role that resolved to the wrong joint would put the label on the wrong
    body part with nothing on screen to show it - the single worst outcome
    this file exists to prevent. Checked by side and by body part, because
    those are the two things a typo flips.
    """
    resolved = resolve_roles(spec)
    for role, index in resolved.items():
        if index is None:
            continue
        joint = spec.joint_names[index].lower()
        if role.startswith("left_"):
            assert "left" in joint or joint.startswith("l"), f"{spec.name}:{role}"
            assert "right" not in joint, f"{spec.name}:{role} -> {joint}"
        elif role.startswith("right_"):
            assert "right" in joint or joint.startswith("r"), f"{spec.name}:{role}"
            assert not joint.startswith("left"), f"{spec.name}:{role} -> {joint}"


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.name)
def test_two_roles_never_share_one_joint(spec) -> None:
    """Sharing would make the stored name ambiguous: reading it back could
    not say which of the two was meant."""
    resolved = resolve_roles(spec)
    used = [index for index in resolved.values() if index is not None]
    assert len(used) == len(set(used)), spec.name


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.name)
def test_the_left_and_right_of_a_pair_are_different_joints(spec) -> None:
    resolved = resolve_roles(spec)
    for role in ALL_ROLES:
        if not role.startswith("left_"):
            continue
        mirror = "right_" + role[len("left_"):]
        left, right = resolved.get(role), resolved.get(mirror)
        if left is None or right is None:
            continue
        assert left != right, f"{spec.name}:{role}/{mirror}"


# ------------------------------------------------------------ the store


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.name)
def test_the_store_refuses_a_role_this_format_does_not_have(spec, tmp_path) -> None:
    resolved = resolve_roles(spec)
    absent = [role for role, index in resolved.items() if index is None]
    if not absent:
        pytest.skip(f"{spec.name} has every role")
    store = AnnotationStore(
        take_dir=tmp_path,
        document=AnnotationDocument(processing_run="r", source_fingerprint="f"),
        skeleton=spec,
    )
    assert store.unavailable_roles(tuple(absent[:2])) == tuple(absent[:2])


def test_an_unknown_skeleton_makes_no_claim(tmp_path) -> None:
    """Rejecting on a version that never recorded its format would throw away
    good labels for a guess."""
    store = AnnotationStore(
        take_dir=tmp_path,
        document=AnnotationDocument(processing_run="r", source_fingerprint="f"),
    )
    assert store.unavailable_roles(("pelvis", "nonsense")) == ()
    assert store.available_roles() == ()


# --------------------------------------------------- really reprocessed


@pytest.fixture(scope="module")
def reprocessed(tmp_path_factory):
    """The same take, processed once per body format.

    This is the user's question answered directly: an existing recording, put
    through the pipeline again with each format, and labelled in each.
    """
    from kinecapture.camera.mock import MockCameraBackend
    from kinecapture.core.jsonio import write_json
    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.domain.enums import ConsentStatus
    from kinecapture.domain.project import CaptureProfile
    from kinecapture.processing.sources import SyntheticSource
    from kinecapture.recording.take_writer import TakeWriter

    root = tmp_path_factory.mktemp("formats") / "datasets"
    root.mkdir(parents=True)
    workspace = ProjectWorkspace.create(root, "Format Testi")
    participant = workspace.create_participant()
    session = workspace.create_session(
        participant.participant_id,
        operator="pytest",
        consent=ConsentStatus.GRANTED,
        capture_profile=CaptureProfile.legacy(),
    )
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile

    versions = {}
    for body_format in PIPELINE_FORMATS:
        from kinecapture.visualization.skeleton_spec import (
            spec_for_zed_body_format,
        )

        backend = MockCameraBackend(
            width=320, height=180, fps=30, seed=5, profile=profile,
            skeleton=spec_for_zed_body_format(body_format),
        )
        info = backend.connect()
        backend.start_preview()
        take, paths = workspace.prepare_take(
            session, origin=backend.origin, camera_info=info
        )
        writer = TakeWriter(workspace, take, paths, archive_color=True)
        for _ in range(20):
            writer.write_frame(backend.grab_frame())
        writer.finalize()
        backend.disconnect()

        config = ProcessingConfig(
            store_depth=False, store_proxy=False, body_format=body_format
        )
        source = SyntheticSource(paths, take, config.profile(take))
        packet = next(iter(source))
        points = packet.bodies[0].joint_positions_2d
        write_json(
            paths.raw_dir / "subject_anchors.json",
            [
                {
                    "camera_timestamp_ns": packet.camera_timestamp_ns,
                    "source_resolution": list(packet.resolution),
                    "point_xy": np.nanmean(points, axis=0).tolist(),
                    "bbox_xyxy": np.r_[
                        np.nanmin(points, axis=0), np.nanmax(points, axis=0)
                    ].tolist(),
                }
            ],
        )
        source.close()
        versions[body_format] = process_take(paths.root, config)
    return workspace, versions


@pytest.mark.parametrize("body_format", PIPELINE_FORMATS)
def test_the_pipeline_really_produces_this_format(reprocessed, body_format) -> None:
    from kinecapture.studio.services.review import ReviewSession

    _workspace, versions = reprocessed
    review = ReviewSession.open(versions[body_format])
    try:
        assert review.skeleton is not None
        assert review.skeleton.name == body_format.lower().replace("body", "zed_body")
        assert review.skeleton.num_joints == review.joints_3d(0).shape[0]
    finally:
        review.close()


@pytest.mark.parametrize("body_format", PIPELINE_FORMATS)
def test_a_double_click_stores_the_right_role_in_this_format(
    app, tmp_path, monkeypatch, reprocessed, body_format
) -> None:
    """The whole point: point at a joint, and the *name* that is written is
    the one this format calls that joint."""
    workspace, versions = reprocessed
    view, window, review = open_review(
        app, tmp_path / body_format, monkeypatch, versions[body_format], workspace
    )
    try:
        use_known_pose(view, app)
        spec = review.skeleton
        resolved = resolve_roles(spec)
        by_index = {
            index: role for role, index in resolved.items() if index is not None
        }

        view.viewmodel.add_movement(2, 8)
        interval = view.viewmodel.add_error(3, 5)
        view._timeline_selected(interval)
        view.editor_bar.error_classes.new_name.setText(f"{body_format} sınıfı")
        app.processEvents()

        aimed = _an_isolated_named_joint(view, by_index, app)
        index, x, y = aimed
        double_click(view.skeleton, x, y)
        app.processEvents()
        assert view._draft_joints == [index]

        view.editor_bar.error_classes.add_button.click()
        app.processEvents()

        row = view.viewmodel.error_row(interval)
        assert row.roles == (by_index[index],), (
            f"{body_format}: pointed at {spec.joint_names[index]}, stored {row.roles}"
        )
        assert row.roles_origin is RolesOrigin.REVIEWED
    finally:
        review.close()
        window.close()


@pytest.mark.parametrize("body_format", ("BODY_18", "BODY_38"))
def test_a_joint_this_format_does_not_name_is_refused(
    app, tmp_path, monkeypatch, reprocessed, body_format
) -> None:
    """Both of these draw joints they cannot name - the eyes and ears in
    BODY_18, those plus fingers and toes in BODY_38."""
    workspace, versions = reprocessed
    view, window, review = open_review(
        app, tmp_path / f"{body_format}-unnamed", monkeypatch,
        versions[body_format], workspace,
    )
    try:
        # The recording's own pose, not the harness body: `facing_pose` places
        # only the joints that have roles and leaves the rest NaN, so the very
        # joints this test is about would not be on screen. The generator
        # produces all of them.
        view.viewmodel.seek(2)
        app.processEvents()
        spec = review.skeleton
        named = {i for i in resolve_roles(spec).values() if i is not None}
        unnamed = [i for i in range(spec.num_joints) if i not in named]
        assert unnamed, f"{body_format} names every joint"

        view.viewmodel.add_movement(2, 8)
        interval = view.viewmodel.add_error(3, 5)
        view._timeline_selected(interval)
        view.editor_bar.error_classes.new_name.setText("deneme")
        app.processEvents()

        by_index = {index: spec.joint_names[index] for index in unnamed}
        index, x, y = _an_isolated_named_joint(
            view, by_index, app, clear_of=named
        )
        # A real double click, not a call: the whole question is what happens
        # when somebody points at one of these.
        double_click(view.skeleton, x, y)
        app.processEvents()
        assert view._draft_joints == [], (
            f"{spec.joint_names[index]} has no role and was selected anyway"
        )
        assert "eklem değil" in view.skeleton.picking_note
        assert not view.editor_bar.error_classes.add_button.isEnabled()
    finally:
        review.close()
        window.close()


def test_a_class_from_another_format_cannot_be_written_here(
    app, tmp_path, monkeypatch, reprocessed
) -> None:
    """A class defined on BODY_34 can name `head` and `left_hand`. BODY_38
    has neither, and writing them would be a claim about joints that
    recording does not contain."""
    workspace, versions = reprocessed
    view, window, review = open_review(
        app, tmp_path / "cross", monkeypatch, versions["BODY_38"], workspace
    )
    try:
        view.viewmodel.add_movement(2, 8)
        interval = view.viewmodel.add_error(3, 5)
        store = view.viewmodel.store
        assert store.skeleton is review.skeleton

        with pytest.raises(ValidationError) as caught:
            store.label_error(
                view.viewmodel.movements.value[0].sample_id,
                interval,
                error_class="",
                affected_roles=("head", "left_hand"),
                joint_status=JointStatus.SELECTED,
                roles_origin=RolesOrigin.CLASS_DEFAULT,
            )
        assert caught.value.code == "roles_not_in_skeleton"
        assert "head" in str(caught.value.details["unavailable"])
    finally:
        review.close()
        window.close()


def _an_isolated_named_joint(view, by_index, app=None, *, clear_of=None):
    """A joint on screen, alone there, and named in this format.

    Zooms in until one is, which is what a person does before pointing at a
    particular joint - BODY_38 packs 38 joints into the same body, and at a
    whole-body framing several of them land inside one pick radius of each
    other. Ambiguity there is correct behaviour, not a defect, so the fixture
    removes it the same way a user would rather than pretending it is absent.
    """
    from kinecapture.studio.views.skeleton3d import PICK_RADIUS_PX

    for _step in range(6):
        positions = {}
        for index in range(len(view.skeleton.projected_joints())):
            found = joint_screen_position(view, index)
            if found is not None:
                positions[index] = found
        # By default a joint has to be clear of every other joint. When the
        # question is only "does clicking here select nothing", being clear of
        # the *named* ones is enough - the eyes, ears and fingertips sit in
        # clusters by nature and separating them is not the point.
        avoid = positions if clear_of is None else {
            i: pos for i, pos in positions.items() if i in clear_of
        }
        for index, (x, y) in positions.items():
            if index not in by_index:
                continue
            if all(
                (ox - x) ** 2 + (oy - y) ** 2 > (2 * PICK_RADIUS_PX) ** 2
                for other, (ox, oy) in avoid.items() if other != index
            ):
                return index, x, y
        # Look at the joints in question before zooming, or the ones near the
        # head simply leave the frame. Orbiting and zooming to bring a joint
        # close is what a person does before pointing at it.
        pose = view.skeleton._joints
        if pose is not None:
            wanted = [
                pose[i] for i in by_index
                if i < len(pose) and bool(np.isfinite(pose[i]).all())
            ]
            if wanted:
                centre = np.mean(np.asarray(wanted, dtype=float), axis=0)
                view.skeleton.camera = view.skeleton.camera.with_target(centre)
        view.skeleton.camera = view.skeleton.camera.zoom(0.7)
        if app is not None:
            app.processEvents()
    raise AssertionError("no isolated joint even after looking at them")
