"""Release gate A3: what was fixed for scale must stay fixed - and stay right.

The scale measurements themselves live in ``scripts/measure/scale_*.py``;
they take tens of minutes and write gigabytes. These are the small, exact
regression tests for the bottlenecks they found, each one also checking that
the faster path still gives the same answer as the slow one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from release_chain import Labeller, new_session, process, record

from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.studio.viewmodels import dataset as dataset_vm
from kinecapture.studio.viewmodels.dataset import DatasetViewModel

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "measure"))


@pytest.fixture
def labelled(tmp_path):
    workspace = ProjectWorkspace.create(tmp_path / "datasets", "Ölçek")
    schema = workspace.label_schema
    squat = schema.ensure_exercise("Squat").code
    workspace.save_label_schema(schema)
    session = new_session(workspace)
    take, paths = record(workspace, session, frames=40, seed=5)
    run = process(paths, take, body_format="BODY_18")
    with Labeller(run, workspace.label_schema) as labeller:
        labeller.choose_athlete()
        labeller.movement(2, 10, squat)
    return SimpleNamespace(workspace=workspace, run=run, squat=squat)


def _counting(monkeypatch) -> list[str]:
    calls: list[str] = []
    real = dataset_vm._summarise

    def counted(row, schema):  # noqa: ANN001, ANN202
        calls.append(row.run_id)
        return real(row, schema)

    monkeypatch.setattr(dataset_vm, "_summarise", counted)
    return calls


def test_an_unchanged_version_is_not_read_again(labelled, monkeypatch) -> None:
    calls = _counting(monkeypatch)
    model = DatasetViewModel(SimpleNamespace(workspace=labelled.workspace))
    model.reload()
    first = model.rows.value
    model.reload()
    assert len(calls) == 1, "the second visit re-read a version nothing had touched"
    assert model.rows.value == first


def test_a_label_change_is_seen_on_the_next_visit(labelled, monkeypatch) -> None:
    calls = _counting(monkeypatch)
    model = DatasetViewModel(SimpleNamespace(workspace=labelled.workspace))
    model.reload()
    assert model.rows.value[0].movements == 1
    with Labeller(labelled.run, labelled.workspace.label_schema) as labeller:
        labeller.movement(20, 30, labelled.squat)
    model.reload()
    assert len(calls) == 2
    assert model.rows.value[0].movements == 2
    assert model.totals.value.movements == 2


def test_a_renamed_class_is_seen_on_the_next_visit(labelled) -> None:
    model = DatasetViewModel(SimpleNamespace(workspace=labelled.workspace))
    model.reload()
    assert model.rows.value[0].class_labels[labelled.squat] == "Squat"
    schema = labelled.workspace.label_schema
    schema.exercises = [
        type(o)(code=o.code, label="Çömelme (squat)", description=o.description)
        if o.code == labelled.squat else o
        for o in schema.exercises
    ]
    labelled.workspace.save_label_schema(schema)
    model.reload()
    assert model.rows.value[0].class_labels[labelled.squat] == "Çömelme (squat)"


def test_the_cached_rows_equal_a_fresh_read(labelled) -> None:
    """Whatever the cache hands back must be exactly what reading gives."""
    cached = DatasetViewModel(SimpleNamespace(workspace=labelled.workspace))
    cached.reload()
    cached.reload()
    fresh = DatasetViewModel(SimpleNamespace(workspace=labelled.workspace))
    fresh.reload()
    assert cached.rows.value == fresh.rows.value
    assert cached.totals.value == fresh.totals.value


# ------------------------------------------------- the finished-job rescan
def _new_version_without_moving_the_clock(take_dir: Path, run_id: str) -> None:
    """A version appears, and the folder's clock does not say so.

    What a coarse-grained file system (FAT32: two seconds) does to a rename
    that lands inside the same tick as the previous scan.
    """
    import json
    import os

    from kinecapture.core.paths import extended_path

    processing = extended_path(take_dir / "derived" / "processing")
    before = os.stat(processing)
    run = os.path.join(processing, run_id)
    os.mkdir(run)
    with open(os.path.join(run, "job.json"), "w", encoding="utf-8") as stream:
        stream.write(json.dumps({"run_id": run_id, "state": "complete", "frames_processed": 5}))
    os.utime(processing, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_a_named_take_is_reread_whatever_its_clock_says(labelled) -> None:
    from kinecapture.dataset.summary_index import build_index

    root = labelled.workspace.root
    take_dir = labelled.run.parents[2]
    build_index(root, force=True)
    _new_version_without_moving_the_clock(take_dir, "run_ffffffffffffffff")

    blind = build_index(root)
    assert len(blind.by_id(take_dir.name).runs) == 1, "the clock did not move, so a plain refresh cannot see it"
    seen = build_index(root, reread=(str(take_dir),))
    assert seen.rescanned == 1
    assert "run_ffffffffffffffff" in [r.run_id for r in seen.by_id(take_dir.name).runs]
    assert len(seen.by_id(take_dir.name).runs) == 2


def test_a_finished_job_rereads_its_take_not_the_project(labelled, monkeypatch, tmp_path) -> None:
    from kinecapture.core.config import AppConfig
    from kinecapture.dataset.summary_index import build_index
    from kinecapture.studio.services.processing import Job, JobProgress, JobState
    from kinecapture.studio.viewmodels.processing import ProcessingViewModel

    session = SimpleNamespace(
        workspace=labelled.workspace, config=AppConfig.sandboxed(tmp_path / "state")
    )
    model = ProcessingViewModel(session)
    calls = []
    monkeypatch.setattr(model, "reload", lambda **kwargs: calls.append(kwargs))
    take = next(iter(build_index(labelled.workspace.root)))
    model._report_if_finished(Job(take=take, progress=JobProgress(state=JobState.COMPLETE)))
    assert calls == [{"reread": (take.directory,)}]


# --------------------------------------------------------- the generator
def test_the_scale_generator_refuses_a_real_location(tmp_path) -> None:
    import scale_dataset

    with pytest.raises(SystemExit):
        scale_dataset.generate(Path.home() / "KineCapture-olcek-denemesi", runs=1, segments=1, classes=1)


def test_the_scale_generator_is_seeded_and_exportable(tmp_path) -> None:
    """Same seed, same labels; and every version it writes is a real one."""
    import json

    import release_oracle as oracle
    import scale_dataset

    from kinecapture.domain.labels import LabelSchema
    from kinecapture.export.canonical import build_release

    first = scale_dataset.generate(tmp_path / "a", runs=12, segments=30, classes=100, awaiting=2)
    second = scale_dataset.generate(tmp_path / "b", runs=12, segments=30, classes=100, awaiting=2)

    def labels(result):  # noqa: ANN001, ANN202
        out = []
        for run in result["run_dirs"]:
            run = Path(run)
            sidecar = run.parents[2] / "annotations" / "processing" / f"{run.name}.json"
            if sidecar.is_file():
                out.append(json.loads(sidecar.read_text("utf-8"))["samples"])
        return out

    assert labels(first) == labels(second)
    root = Path(first["project_root"])
    schema = json.loads((root / "label_schema.json").read_text("utf-8"))
    report = build_release(
        [Path(p) for p in first["run_dirs"]], tmp_path / "releases", LabelSchema.from_dict(schema)
    )
    assert report.samples > 0
    assert oracle.verify(
        report.release_dir, [Path(p) for p in first["run_dirs"]], schema,
        project=json.loads((root / "project.json").read_text("utf-8")),
    ) == []


# ------------------------------------------------------------ list screens
@pytest.fixture(scope="module")
def qapp():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_export_search_box_filters_the_list(qapp) -> None:
    """Found while measuring the screen: the box was wired to Qt's own filter
    string, which ``SearchProxy`` does not read, so typing changed nothing."""
    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.viewmodels.export import PreflightRow
    from kinecapture.studio.viewmodels.navigation import destination
    from kinecapture.studio.views.pages.export import ExportPage

    page = ExportPage(destination("export"), load_tokens("dark"))
    page.model.set_rows([
        PreflightRow(run_id=f"run_{i:04d}", take_id=f"take_{i:04d}", directory="",
                     accepted=True, samples=1, reasons=(), detail=())
        for i in range(10)
    ])
    page.search.setText("run_0003")
    assert page.proxy.rowCount() == 1
    page.search.setText("")
    assert page.proxy.rowCount() == 10


def test_content_sized_columns_measure_a_screenful_not_a_thousand_rows(qapp) -> None:
    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.viewmodels.navigation import destination
    from kinecapture.studio.views.models import CONTENT_SIZING_ROWS
    from kinecapture.studio.views.pages.dataset import DatasetPage
    from kinecapture.studio.views.pages.export import ExportPage
    from kinecapture.studio.views.pages.library import LibraryPage

    tokens = load_tokens("dark")
    for page, view in (
        (DatasetPage(destination("dataset"), tokens), "table"),
        (ExportPage(destination("export"), tokens), "table"),
        (LibraryPage(destination("library"), tokens), "view"),
    ):
        header = getattr(page, view).horizontalHeader()
        assert header.resizeContentsPrecision() == CONTENT_SIZING_ROWS, type(page).__name__


# ------------------------------------------------ Projects: reads off the GUI
class _Deferred:
    """A worker thread, slowed right down: work waits until it is drained."""

    def __init__(self) -> None:
        self.queue: list = []

    def run(self, work, on_done, on_error=None) -> None:  # noqa: ANN001
        self.queue.append((work, on_done))

    def drain(self) -> None:
        while self.queue:
            work, on_done = self.queue.pop(0)
            on_done(work())


def test_a_participant_chosen_during_a_scan_gets_the_scans_counts(tmp_path, monkeypatch) -> None:
    """S12: the participant and session lists are read on the runner. A
    selection made while the project was still being scanned must end up with
    the new scan's counts, not the old index's."""
    import json

    from kinecapture.core.config import AppConfig
    from kinecapture.studio.services.projects import ProjectService
    from kinecapture.studio.services.session import SessionService
    from kinecapture.studio.viewmodels.auth import AuthViewModel
    from kinecapture.studio.viewmodels.projects import ProjectsViewModel

    monkeypatch.setattr("kinecapture.studio.services.session.save_user_state", lambda _c: None)
    session = SessionService.open(AppConfig.sandboxed(tmp_path / "state"))
    assert AuthViewModel(session).create_owner(
        first_name="Test", last_name="Kişi", title="", username="deneme",
        password="yalniz-test-9x", password_confirm="yalniz-test-9x",
    )
    service = ProjectService(session.identity, session.user)
    workspace = service.create_project(session.config.dataset_root, "Ölçek")
    participant = service.create_participant(workspace)
    sitting = workspace.create_session(participant.participant_id, operator="deneme")
    directory = workspace.take_dir(participant.participant_id, sitting.session_id, "take_x")
    (directory / "derived" / "processing" / "run_a").mkdir(parents=True)
    (directory / "take.json").write_text(json.dumps({
        "take_id": "take_x", "started_at": "2026-09-24T01:00:00+00:00", "state": "finalized",
        "processing_status": "awaiting_processing", "metrics": {"frames_written": 10, "duration_s": 1.0},
    }), encoding="utf-8")
    (directory / "derived" / "processing" / "run_a" / "job.json").write_text(
        json.dumps({"run_id": "run_a", "state": "complete", "frames_processed": 10}), encoding="utf-8")

    runner = _Deferred()
    model = ProjectsViewModel(session, runner)
    model.reload_projects()          # opens the project; the scan is queued
    assert runner.queue, "the scan must go through the runner"
    model.select_participant(participant.participant_id)   # before the scan lands
    runner.drain()
    rows = model.participants.value
    assert [row.participant_id for row in rows] == [participant.participant_id]
    assert rows[0].take_count == 1 and rows[0].processed_count == 1
    assert [row.session_id for row in model.sessions.value] == [sitting.session_id]


class _Manual:
    """Work and completion as separate steps: a pool that finishes out of order."""

    def __init__(self) -> None:
        self.tasks: list = []

    def run(self, work, on_done, on_error=None) -> None:  # noqa: ANN001
        self.tasks.append({"work": work, "done": on_done, "result": None})

    def work(self, index: int) -> None:
        self.tasks[index]["result"] = self.tasks[index]["work"]()

    def done(self, index: int) -> None:
        self.tasks[index]["done"](self.tasks[index]["result"])


def test_an_older_scan_finishing_last_does_not_undo_a_newer_one(tmp_path, monkeypatch) -> None:
    """Found by the full run on 24 September: four participants added in a row
    showed three, because a rescan that started earlier finished later."""
    from kinecapture.core.config import AppConfig
    from kinecapture.studio.services.projects import ProjectService
    from kinecapture.studio.services.session import SessionService
    from kinecapture.studio.viewmodels.auth import AuthViewModel
    from kinecapture.studio.viewmodels.projects import ProjectsViewModel

    monkeypatch.setattr("kinecapture.studio.services.session.save_user_state", lambda _c: None)
    session = SessionService.open(AppConfig.sandboxed(tmp_path / "state"))
    assert AuthViewModel(session).create_owner(
        first_name="Test", last_name="Kişi", title="", username="deneme",
        password="yalniz-test-9x", password_confirm="yalniz-test-9x",
    )
    service = ProjectService(session.identity, session.user)
    workspace = service.create_project(session.config.dataset_root, "Sıra")
    service.create_participant(workspace)

    runner = _Manual()
    model = ProjectsViewModel(session, runner)
    model.reload_projects()
    runner.work(0)
    runner.done(0)
    assert len(model.participants.value) == 1

    model.refresh_index(force=True)          # the older scan: reads one participant
    runner.work(1)
    service.create_participant(workspace)
    model.refresh_index(force=True)          # the newer scan: reads two
    runner.work(2)
    runner.done(2)
    assert [row.code for row in model.participants.value] == ["P0001", "P0002"]
    runner.done(1)                           # the older one lands last
    assert [row.code for row in model.participants.value] == ["P0001", "P0002"]
    assert model.busy.value is False
