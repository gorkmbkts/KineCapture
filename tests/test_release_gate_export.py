"""Release gate A2: the canonical package, checked by an independent reader.

The chain is the real one - mock camera, the take writer, offline processing
in all three ZED body formats, the annotation and subject stores the labelling
screen uses - and the package it produces is compared field by field and array
by array with what :mod:`release_oracle` derives from the project's own files.
The oracle shares no code with the exporter, so a mistake cannot hide by being
made twice.

Labels, project and class names deliberately carry Turkish letters, spaces and
punctuation; the dataset root does too. Movements touch the first and the last
frame, one is a single frame, movements and error intervals overlap, and one
error class is defined but never used.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import release_oracle as oracle
from release_chain import (
    Labeller,
    new_session,
    process,
    project_file,
    record,
    schema_file,
)

from kinecapture.core.errors import ValidationError
from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import long_path, path_exists
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.labels import LabelSchema
from kinecapture.export.canonical import Refusal, build_release, inspect_version
from kinecapture.processing.annotations import JointStatus, RolesOrigin

FRAMES = 60
OPERATOR = "Görkem Bektaş"


def _ids(root: Path) -> list[Path]:
    return sorted(Path(long_path(root)).iterdir())


@pytest.fixture(scope="module")
def gate(tmp_path_factory) -> SimpleNamespace:
    """One project, six takes, every body format, every refusal worth having."""
    base = tmp_path_factory.mktemp("gate") / "Veri Kökü Ğüşiöç Şahin" / "datasets"
    base.mkdir(parents=True)
    workspace = ProjectWorkspace.create(base, "Diz Rehabilitasyonu — Çalışma 1 (ğüşıöç)")

    schema = workspace.label_schema
    squat = schema.ensure_exercise("Squat").code
    lunge = schema.ensure_exercise("Lunge (sağ bacak)").code
    bridge = schema.ensure_exercise("Köprü / Glute Bridge").code
    deep = schema.ensure_exercise("Çömelme %50 — derin").code
    jump = schema.ensure_exercise("Sıçrama: tek-ayak [test]").code
    valgus = schema.ensure_error_type("Diz içe çöküyor").code
    heel = schema.ensure_error_type("Topuk kalkıyor").code
    trunk = schema.ensure_error_type("Gövde öne eğik (>30°)").code
    hip = schema.add_error_type_with_roles("Kalça düşüyor – sol", ("left_hip",)).code
    schema.ensure_error_type("Hiç kullanılmayan sınıf")
    workspace.save_label_schema(schema)
    schema = workspace.label_schema
    hip_revision = schema.find_error_type(hip).roles_revision

    runs: list[Path] = []
    participants: dict[str, str] = {}

    # P0001 - BODY_18. Every edge case the contract has an opinion about.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=11)
    run = process(paths, take, body_format="BODY_18")
    with Labeller(run, schema) as labeller:
        labeller.choose_athlete()
        first = labeller.movement(0, 9, squat, note='Not: sağ diz ağrısı; "tırnak"\nyeni satır')
        labeller.error(first, 2, 6, valgus, roles=("left_knee",),
                       status=JointStatus.SELECTED, origin=RolesOrigin.REVIEWED,
                       note="erken başlıyor")
        labeller.error(first, 4, 9, heel, status=JointStatus.NOT_APPLICABLE)
        labeller.movement(10, 10, lunge)                       # a single frame
        last = labeller.movement(50, FRAMES - 1, bridge)       # touches the end
        labeller.error(last, FRAMES - 1, FRAMES - 1, trunk, status=JointStatus.INDETERMINATE)
        labeller.movement(20, 30, squat, reviewed=False)       # never reviewed
        labeller.movement(31, 35)                              # no class
        labeller.movement(36, 40, squat, excluded=True)        # kept out
        overlap = labeller.movement(15, 25, jump)              # overlaps 20..30
        labeller.error(overlap, 15, 15, hip, roles=("left_hip",),
                       status=JointStatus.SELECTED, origin=RolesOrigin.CLASS_DEFAULT,
                       revision=hip_revision)
    runs.append(run)
    participants[run.name] = session.participant_id

    # P0002 - BODY_34, wrists and ankles blanked for most frames: NaN must
    # arrive in the package exactly where the version has it.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=12, low_confidence_every=20)
    run = process(paths, take, body_format="BODY_34")
    with Labeller(run, schema) as labeller:
        labeller.choose_athlete()
        whole = labeller.movement(0, FRAMES - 1, deep)
        labeller.error(whole, 5, 54, valgus, roles=("left_knee", "right_knee"),
                       status=JointStatus.SELECTED, origin=RolesOrigin.REVIEWED)
    runs.append(run)
    participants[run.name] = session.participant_id

    # P0003 - BODY_38, two plain repetitions.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=13)
    run = process(paths, take, body_format="BODY_38")
    with Labeller(run, schema) as labeller:
        labeller.choose_athlete()
        labeller.movement(3, 17, squat)
        rep = labeller.movement(18, 40, squat)
        labeller.error(rep, 18, 40, heel, status=JointStatus.NOT_APPLICABLE)
    runs.append(run)
    participants[run.name] = session.participant_id

    # P0004 - labelled, but nobody said who the athlete is.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=14)
    run = process(paths, take, body_format="BODY_38")
    with Labeller(run, schema) as labeller:
        labeller.movement(5, 20, squat)
    runs.append(run)
    participants[run.name] = session.participant_id

    # P0005 - one repetition carries an error that was drawn and never classed.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=15)
    run = process(paths, take, body_format="BODY_18")
    with Labeller(run, schema) as labeller:
        labeller.choose_athlete()
        labeller.movement(2, 12, squat)
        open_rep = labeller.movement(20, 30, lunge)
        labeller.error(open_rep, 22, 24)
    runs.append(run)
    participants[run.name] = session.participant_id

    # P0006 - processed with nobody marked: every array is NaN.
    session = new_session(workspace)
    take, paths = record(workspace, session, seed=16)
    run = process(paths, take, body_format="BODY_34", mark_subject=False)
    runs.append(run)
    participants[run.name] = session.participant_id

    return SimpleNamespace(
        workspace=workspace,
        schema=schema,
        runs=runs,
        participants=participants,
        codes=SimpleNamespace(
            squat=squat, lunge=lunge, bridge=bridge, deep=deep, jump=jump,
            valgus=valgus, heel=heel, trunk=trunk, hip=hip,
        ),
    )


def _build(gate, releases: Path, **kwargs):
    return build_release(
        gate.runs, releases, gate.workspace.label_schema, operator=OPERATOR, **kwargs
    )


@pytest.fixture(scope="module")
def package(gate, tmp_path_factory):
    releases = tmp_path_factory.mktemp("releases")
    report = _build(gate, releases)
    return SimpleNamespace(report=report, path=report.release_dir)


# ----------------------------------------------------------------- content
def test_the_package_is_exactly_what_the_labels_say(gate, package) -> None:
    problems = oracle.verify(
        package.path,
        gate.runs,
        schema_file(gate.workspace),
        project=project_file(gate.workspace),
    )
    assert problems == []


def test_the_expected_versions_are_in_and_out(gate, package) -> None:
    """The oracle agrees with itself; this pins down *what* it agreed on."""
    manifest = read_json(package.path / "manifest.json")
    refused = {v["run_id"]: v["refusals"] for v in manifest["refused_versions"]}
    runs = [r.name for r in gate.runs]
    assert [v["run_id"] for v in manifest["versions"]] == runs[:3]
    assert refused[runs[3]] == [Refusal.ATHLETE_NOT_CHOSEN.value]
    assert refused[runs[4]] == [Refusal.OPEN_ERRORS.value]
    assert Refusal.NO_SUBJECT_DATA.value in refused[runs[5]]
    samples = read_json(package.path / "samples.json")["samples"]
    # P0001: 4 ready of 7 drawn; P0002: 1; P0003: 2.
    assert len(samples) == 7


def test_every_body_format_keeps_its_own_joint_layout(gate, package) -> None:
    manifest = read_json(package.path / "manifest.json")
    samples = read_json(package.path / "samples.json")["samples"]
    expected = {"zed_body_18": 18, "zed_body_34": 34, "zed_body_38": 38}
    assert {s["skeleton_format"] for s in samples} == set(expected)
    for sample in samples:
        joints = np.load(long_path(package.path / sample["directory"] / "joints.npy"))
        count = expected[sample["skeleton_format"]]
        assert joints.shape[1:] == (count, 3)
        layout = manifest["skeletons"][sample["skeleton_format"]]
        assert layout["num_joints"] == count and len(layout["joints"]) == count


def test_missing_measurements_stay_nan(gate, package) -> None:
    samples = read_json(package.path / "samples.json")["samples"]
    blanked = next(s for s in samples if s["run_id"] == gate.runs[1].name)
    joints = np.load(long_path(package.path / blanked["directory"] / "joints.npy"))
    version = np.load(long_path(gate.runs[1] / "arrays" / "joints.npy"))
    assert np.isnan(version).any(), "the scenario must actually contain gaps"
    assert np.array_equal(np.isnan(joints), np.isnan(version[0:FRAMES]))


def test_participants_never_mix(gate, package) -> None:
    samples = read_json(package.path / "samples.json")["samples"]
    for sample in samples:
        assert sample["participant_id"] == gate.participants[sample["run_id"]]
        take = read_json(Path(gate.runs[[r.name for r in gate.runs].index(sample["run_id"])]).parents[2] / "take.json")
        assert take["participant_id"] == sample["participant_id"]
        assert sample["project_id"] == gate.workspace.project.project_id
    in_package = {s["participant_id"] for s in samples}
    assert in_package == {gate.participants[r.name] for r in gate.runs[:3]}


def test_synthetic_data_says_so(package) -> None:
    samples = read_json(package.path / "samples.json")["samples"]
    manifest = read_json(package.path / "manifest.json")
    assert {s["origin"] for s in samples} == {"synthetic"}
    assert manifest["counts"]["samples_synthetic"] == len(samples)


def test_an_unused_class_keeps_its_column(gate, package) -> None:
    manifest = read_json(package.path / "manifest.json")
    unused = gate.workspace.label_schema.match_error_type("Hiç kullanılmayan sınıf").code
    column = manifest["error_mapping"]["code_to_index"][unused]
    for sample in read_json(package.path / "samples.json")["samples"]:
        dense = np.load(long_path(package.path / sample["directory"] / "error_per_frame.npy"))
        assert dense.shape[1] == len(manifest["error_mapping"]["classes"])
        assert not dense[:, column].any()


def test_the_two_options_the_screen_offers_change_only_what_they_say(gate, tmp_path) -> None:
    """Dışa Aktarım offers two switches: confidences and dense error targets."""
    from kinecapture.export.canonical import CanonicalExportOptions

    report = _build(
        gate, tmp_path / "lean",
        options=CanonicalExportOptions(store_confidences=False, store_dense_error_targets=False),
    )
    assert oracle.verify(
        report.release_dir, gate.runs, schema_file(gate.workspace),
        project=project_file(gate.workspace),
        store_confidences=False, store_dense=False,
    ) == []
    manifest = read_json(report.release_dir / "manifest.json")
    assert manifest["options"]["store_confidences"] is False
    assert manifest["options"]["store_dense_error_targets"] is False


def test_the_build_says_how_far_it_has_got(gate, tmp_path) -> None:
    """Every version is counted once, refused or not, and the last call is n/n."""
    seen: list[tuple[int, int]] = []
    _build(gate, tmp_path / "counted", progress=lambda done, total: seen.append((done, total)))
    assert seen == [(i, len(gate.runs)) for i in range(1, len(gate.runs) + 1)]


def test_the_export_screen_reports_progress_and_then_the_result(gate) -> None:
    from kinecapture.studio.services.library import LibraryService
    from kinecapture.studio.viewmodels.export import ExportViewModel
    from kinecapture.dataset.summary_index import build_index

    session = SimpleNamespace(workspace=gate.workspace, user=None)
    model = ExportViewModel(session)
    lines: list[str] = []
    model.summary.subscribe(lines.append)
    rows = LibraryService().versions(build_index(gate.workspace.root))
    model.check(rows)
    assert any(line.endswith(f"{len(rows)}/{len(rows)} sürüm") for line in lines)
    assert "sürüm hazır" in lines[-1]


# ------------------------------------------------------------- determinism
def test_two_builds_of_the_same_input_are_identical(gate, tmp_path) -> None:
    first = _build(gate, tmp_path / "a")
    second = _build(gate, tmp_path / "b")
    a = oracle.package_bytes(first.release_dir)
    b = oracle.package_bytes(second.release_dir)
    assert sorted(a) == sorted(b)
    differing = [name for name in a if a[name] != b[name]]
    assert differing == []


# ----------------------------------------------------------- interruption
_KILLED_BUILD = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path

    import kinecapture.export.canonical as canonical
    from kinecapture.domain.labels import LabelSchema

    runs = [Path(p) for p in json.loads(sys.argv[1])]
    releases, marker = Path(sys.argv[2]), Path(sys.argv[3])
    schema = LabelSchema.from_dict(json.loads(Path(sys.argv[4]).read_text("utf-8")))
    real = canonical._write_version
    calls = []

    def slow(*args, **kwargs):
        written = real(*args, **kwargs)
        calls.append(written)
        if len(calls) == 2:
            marker.write_text("mid-build", encoding="utf-8")
            time.sleep(120)
        return written

    canonical._write_version = slow
    canonical.build_release(runs, releases, schema)
    """
)


@pytest.mark.slow
def test_a_killed_export_leaves_nothing_that_looks_like_a_release(gate, tmp_path) -> None:
    releases = tmp_path / "releases"
    marker = tmp_path / "marker"
    script = tmp_path / "killed_build.py"
    script.write_text(_KILLED_BUILD, encoding="utf-8")
    child = subprocess.Popen(
        [
            sys.executable, str(script), json.dumps([str(r) for r in gate.runs]),
            str(releases), str(marker), str(gate.workspace.label_schema_file),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 120
        while not marker.exists() and time.time() < deadline:
            assert child.poll() is None, child.stdout.read().decode("utf-8", "replace")
            time.sleep(0.05)
        assert marker.exists(), "the build never reached the middle"
        child.kill()                      # TerminateProcess: no cleanup runs
        child.wait(timeout=30)
    finally:
        if child.poll() is None:
            child.kill()
        if child.stdout:
            child.stdout.close()

    left = [p.name for p in _ids(releases)]
    # Only the hidden staging folder may remain, and it is not a release: it
    # has samples in it but no manifest, no index and no checksums.
    assert all(name.startswith(".") and name.endswith(".partial") for name in left), left
    staging = releases / left[0]
    assert path_exists(staging / "samples")
    assert not path_exists(staging / "manifest.json")
    assert not path_exists(staging / "checksums.json")

    # The next build takes the same name, clears the debris and is whole.
    report = _build(gate, releases)
    assert report.release_dir.name == "v0001"
    assert [p.name for p in _ids(releases)] == ["v0001"]
    assert oracle.verify(
        report.release_dir, gate.runs, schema_file(gate.workspace),
        project=project_file(gate.workspace),
    ) == []


# -------------------------------------------------------------- long paths
def test_a_release_deeper_than_max_path_is_whole(gate, tmp_path) -> None:
    releases = tmp_path
    while len(str(releases)) < 230:
        releases = releases / ("derin klasör ğüş " + "x" * 12)
    report = _build(gate, releases)
    deepest = max(
        (str(p) for p in Path(long_path(report.release_dir)).rglob("*")), key=len
    ).removeprefix("\\\\?\\")
    assert len(deepest) > 259, "the test did not actually go past MAX_PATH"
    assert oracle.verify(
        report.release_dir, gate.runs, schema_file(gate.workspace),
        project=project_file(gate.workspace),
    ) == []


def test_the_checksums_cover_files_that_only_their_folder_keeps_short(gate, tmp_path) -> None:
    """A releases folder short enough to be opened unprefixed, with sample
    files more than MAX_PATH deep: the walk that lists them for
    ``checksums.json`` must still see every one. Found by the A3 scale run,
    where a 200-character root left 588 of 4706 files out of the list.
    """
    releases = tmp_path
    while len(str(releases)) < 200:
        releases = releases / "k"
    releases = Path(str(releases)[:205].rstrip("\\/"))
    report = _build(gate, releases)
    staging = releases / f".{report.release_dir.name}.partial"
    assert len(str(staging)) < 227, "the staging folder must be one long_path leaves alone"
    deepest = max(
        len(str(p).removeprefix("\\\\?\\"))
        for p in Path("\\\\?\\" + str(report.release_dir)).rglob("*")
    )
    assert deepest > 259
    assert oracle.verify_checksums(report.release_dir) == []


# ------------------------------------------------------------ moved projects
def _extended(path: Path) -> str:
    """Always the ``\\\\?\\`` form: ``copytree`` recurses past MAX_PATH here."""
    text = os.path.abspath(str(path))
    return text if text.startswith("\\\\?\\") else "\\\\?\\" + text


def _copy_project(workspace: ProjectWorkspace, target: Path) -> ProjectWorkspace:
    shutil.copytree(_extended(workspace.root), _extended(target))
    return ProjectWorkspace.open(target)


def _runs_in(workspace: ProjectWorkspace) -> list[Path]:
    root = Path(long_path(workspace.root))
    return sorted(
        (p for p in root.glob("participants/*/sessions/*/takes/*/derived/processing/run_*")),
        key=lambda p: p.parents[2].name,
    )


def test_a_moved_project_exports_its_own_labels(gate, tmp_path) -> None:
    """``job.json`` records where a take *was*; the labels live where it *is*.

    Copy the project, then take the labels away from the original. The copy
    still has every one of its labels and must export all of them - not the
    empty original, and not whatever the original says after an edit.
    """
    copy = _copy_project(gate.workspace, tmp_path / "taşınan proje")
    for run in gate.runs:
        sidecar = run.parents[2] / "annotations" / "processing" / f"{run.name}.json"
        backup = tmp_path / f"{run.name}.bak"
        if path_exists(sidecar):
            shutil.copy2(long_path(sidecar), long_path(backup))
    try:
        for run in gate.runs:
            sidecar = run.parents[2] / "annotations" / "processing" / f"{run.name}.json"
            if path_exists(sidecar):
                os.remove(long_path(sidecar))
        runs = _runs_in(copy)
        order = {r.name: i for i, r in enumerate(gate.runs)}
        runs.sort(key=lambda p: order[p.name])
        report = build_release(runs, tmp_path / "releases", copy.label_schema)
        assert report.samples == 7
        assert oracle.verify(
            report.release_dir, runs, schema_file(copy), project=project_file(copy)
        ) == []
    finally:
        for run in gate.runs:
            sidecar = run.parents[2] / "annotations" / "processing" / f"{run.name}.json"
            backup = tmp_path / f"{run.name}.bak"
            if path_exists(backup):
                shutil.copy2(long_path(backup), long_path(sidecar))


def test_labelling_a_copied_project_writes_into_the_copy(gate, tmp_path) -> None:
    copy = _copy_project(gate.workspace, tmp_path / "kopya")
    original = gate.runs[2]
    original_sidecar = original.parents[2] / "annotations" / "processing" / f"{original.name}.json"
    before = Path(long_path(original_sidecar)).read_bytes()

    copied_run = next(r for r in _runs_in(copy) if r.name == original.name)
    with Labeller(copied_run, copy.label_schema) as labeller:
        assert labeller.review.take_dir == copied_run.parents[2]
        labeller.movement(45, 50, gate.codes.squat)

    assert Path(long_path(original_sidecar)).read_bytes() == before
    copied = read_json(copied_run.parents[2] / "annotations" / "processing" / f"{copied_run.name}.json")
    assert len(copied["samples"]) == 3


# ----------------------------------------------------------- sample identity
def _rewrite_sample_id(run: Path, new_id: str) -> tuple[Path, bytes]:
    sidecar = run.parents[2] / "annotations" / "processing" / f"{run.name}.json"
    before = Path(long_path(sidecar)).read_bytes()
    document = json.loads(before.decode("utf-8"))
    document["samples"][0]["sample_id"] = new_id
    write_json(sidecar, document, overwrite=True)
    return sidecar, before


def test_a_sample_id_that_is_not_a_folder_name_is_refused(gate, tmp_path) -> None:
    """A hand-edited id must never become a path outside the package."""
    run = gate.runs[2]
    sidecar, before = _rewrite_sample_id(run, "..\\..\\kaçak")
    try:
        report, opened = inspect_version(run, gate.workspace.label_schema)
        assert opened is None
        assert Refusal.ANNOTATION_INVALID in report.refusals
        built = build_release([run], tmp_path / "releases", gate.workspace.label_schema)
        assert built.samples == 0
        assert not any(p.name == "kaçak" for p in tmp_path.rglob("*"))
    finally:
        Path(long_path(sidecar)).write_bytes(before)


def test_two_versions_sharing_a_sample_id_do_not_overwrite_each_other(gate, tmp_path) -> None:
    """Otherwise the second version's arrays silently replace the first's."""
    first = read_json(
        gate.runs[0].parents[2] / "annotations" / "processing" / f"{gate.runs[0].name}.json"
    )["samples"][0]["sample_id"]
    sidecar, before = _rewrite_sample_id(gate.runs[2], first)
    try:
        report = build_release(gate.runs[:3], tmp_path / "releases", gate.workspace.label_schema)
        refused = {v.run_id: v.refusals for v in report.refused}
        assert Refusal.DUPLICATE_SAMPLE in refused[gate.runs[2].name]
        written = read_json(report.release_dir / "samples.json")["samples"]
        owner = [s for s in written if s["sample_id"] == first]
        assert len(owner) == 1 and owner[0]["run_id"] == gate.runs[0].name
        joints = np.load(long_path(report.release_dir / owner[0]["directory"] / "joints.npy"))
        assert joints.shape[1] == 18, "the BODY_38 version overwrote the BODY_18 sample"
    finally:
        Path(long_path(sidecar)).write_bytes(before)


# -------------------------------------------------------------- class names
def test_long_class_names_that_share_a_prefix_stay_distinct() -> None:
    schema = LabelSchema.default()
    stem = "Squat sırasında sol diz içe çöküyor ve topuk yerden "
    first = schema.add_error_type(stem + "kalkıyor")
    second = schema.add_error_type(stem + "kalkmıyor")
    assert first.code != second.code
    assert schema.match_error_type(stem + "kalkmıyor").code == second.code
    mapping = schema.label_mapping()["error_types"]
    assert len(mapping["classes"]) == 2
    assert mapping["labels"][second.code] == stem + "kalkmıyor"


def test_class_names_made_of_symbols_stay_distinct() -> None:
    schema = LabelSchema.default()
    plus = schema.add_exercise("+")
    times = schema.add_exercise("×")
    assert plus.code != times.code
    assert schema.match_exercise("×").code == times.code
    # A real name that happens to slug to the fallback is its own class too.
    assert schema.ensure_exercise("Label").code not in (plus.code, times.code)


def test_the_same_class_typed_differently_is_still_one_class() -> None:
    schema = LabelSchema.default()
    knee = schema.add_error_type("Diz içe çöküyor")
    assert schema.ensure_error_type("  DİZ İÇE ÇÖKÜYOR ").code == knee.code
    with pytest.raises(ValidationError):
        schema.add_error_type("diz içe  çöküyor")


#: ZED SDK BODY_34 joint order and the KineSynthV3 REHAB24-6 26-joint order,
#: written out here from the two specifications rather than imported, so the
#: check below cannot inherit a mistake from the exporter's own tables.
_BODY_34 = (
    "pelvis", "naval_spine", "chest_spine", "neck", "left_clavicle",
    "left_shoulder", "left_elbow", "left_wrist", "left_hand", "left_handtip",
    "left_thumb", "right_clavicle", "right_shoulder", "right_elbow",
    "right_wrist", "right_hand", "right_handtip", "right_thumb", "left_hip",
    "left_knee", "left_ankle", "left_foot", "right_hip", "right_knee",
    "right_ankle", "right_foot", "head", "nose", "left_eye", "left_ear",
    "right_eye", "right_ear", "left_heel", "right_heel",
)
_REHAB24 = (
    "Hips", "Spine", "Spine1", "Neck", "Head", "Head_end",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "LeftHand_end",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand", "RightHand_end",
    "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase", "LeftToeBase_end",
    "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase", "RightToeBase_end",
)
_REHAB24_FROM_BODY_34 = {
    "Hips": "pelvis", "Spine": "naval_spine", "Spine1": "chest_spine",
    "Neck": "neck", "Head": "head",
    "LeftShoulder": "left_clavicle", "LeftArm": "left_shoulder",
    "LeftForeArm": "left_elbow", "LeftHand": "left_wrist",
    "LeftHand_end": "left_handtip",
    "RightShoulder": "right_clavicle", "RightArm": "right_shoulder",
    "RightForeArm": "right_elbow", "RightHand": "right_wrist",
    "RightHand_end": "right_handtip",
    "LeftUpLeg": "left_hip", "LeftLeg": "left_knee", "LeftFoot": "left_ankle",
    "LeftToeBase": "left_foot",
    "RightUpLeg": "right_hip", "RightLeg": "right_knee",
    "RightFoot": "right_ankle", "RightToeBase": "right_foot",
}


def test_the_rehab24_target_moves_every_joint_by_name(workspace, session) -> None:
    """``rehab24_6_mocap`` is an export target only - and only in the legacy
    release builder (``--legacy-gui``); the Studio package has no joint
    mapping. Every source joint carries its own index as its x coordinate, so
    a permutation mistake shows up as a wrong number, not a plausible one.
    """
    from kinecapture.dataset.index import DatasetIndex
    from kinecapture.export.release import ExportOptions, ReleaseBuilder
    from tests.test_export import _record_and_label
    from tests.test_export_features import _write_zed34_stream

    take = _record_and_label(workspace, session, frames=30)
    _write_zed34_stream(workspace, take)
    stream_path = workspace.take_paths(take).skeleton_stream
    lines = []
    for line in stream_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("record") == "frame":
            frame = int(row["i"])
            row["bodies"][0]["joints"] = [[float(j), float(frame), 7.0] for j in range(34)]
        lines.append(json.dumps(row, ensure_ascii=False))
    stream_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    index = DatasetIndex(workspace).refresh(force=True)
    result = ReleaseBuilder(
        workspace, index,
        ExportOptions(include_synthetic=True, target_skeleton_format="rehab24_6_mocap"),
    ).build()

    spec = read_json(result.path / "skeleton_spec.json")["formats"]["rehab24_6_mocap"]
    assert tuple(spec["joints"]) == _REHAB24
    manifest = read_json(result.path / "manifest.json")
    assert manifest["samples"], "the scenario must export something"
    for sample in manifest["samples"]:
        assert sample["skeleton_format"] == "rehab24_6_mocap"
        assert sample["participant_id"] == session.participant_id
        payload = np.load(result.path / sample["file"])
        joints, frames = payload["joints_xyz"], payload["frame_indices"]
        assert joints.shape == (sample["num_frames"], 26, 3)
        assert list(frames) == list(range(sample["start_position"], sample["end_position"] + 1))
        for column, target in enumerate(_REHAB24):
            source = _REHAB24_FROM_BODY_34.get(target)
            if source is None:
                assert np.isnan(joints[:, column]).all(), target
                continue
            np.testing.assert_array_equal(joints[:, column, 0], _BODY_34.index(source))
            np.testing.assert_array_equal(joints[:, column, 1], frames)
            np.testing.assert_array_equal(joints[:, column, 2], 7.0)


def test_a_hundred_and_fifty_classes_keep_a_stable_mapping() -> None:
    schema = LabelSchema.default()
    for n in range(150):
        schema.add_exercise(f"Egzersiz {n:03d} — çeşit ğüş")
        schema.add_error_type(f"Hata sınıfı {n:03d} (sağ/sol) %{n}")
    mapping = schema.label_mapping()
    assert len(mapping["exercise"]["classes"]) == 150
    assert len(mapping["error_types"]["classes"]) == 150
    assert mapping == LabelSchema.from_dict(schema.to_dict()).label_mapping()
