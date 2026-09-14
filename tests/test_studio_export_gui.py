"""Veri Seti and Dışa Aktarım, against versions that were really labelled.

The question both screens have to answer honestly is "what is in the dataset
and what is not". A version that is missing must be visible as missing, with
the reason, on the screen *and* in the written package.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.jsonio import read_json, write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.processing.subject_review import (  # noqa: E402
    Verdict,
    load_subject_review,
    scan_candidates,
    scan_unsettled,
)
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.annotation_store import AnnotationStore  # noqa: E402
from kinecapture.studio.services.library import LibraryService  # noqa: E402
from kinecapture.studio.services.review import ReviewSession  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.services.subject_store import SubjectStore  # noqa: E402
from kinecapture.studio.theme import load_tokens  # noqa: E402
from kinecapture.studio.viewmodels.dataset import DatasetViewModel  # noqa: E402
from kinecapture.studio.viewmodels.export import ExportViewModel  # noqa: E402
from kinecapture.studio.viewmodels.library import LibraryViewModel  # noqa: E402
from kinecapture.studio.viewmodels.navigation import destination  # noqa: E402
from kinecapture.studio.views.pages.dataset import DatasetPage  # noqa: E402
from kinecapture.studio.views.pages.export import ExportPage  # noqa: E402

FRAMES = 32


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _record(workspace, session, seed: int) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=seed, profile=profile)
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(session, origin=backend.origin, camera_info=info)
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
    source = SyntheticSource(paths, take, config.profile(take))
    packet = next(iter(source))
    points = packet.bodies[0].joint_positions_2d
    write_json(paths.raw_dir / "subject_anchors.json", [{
        "camera_timestamp_ns": packet.camera_timestamp_ns,
        "source_resolution": list(packet.resolution),
        "point_xy": np.nanmean(points, axis=0).tolist(),
        "bbox_xyxy": np.r_[np.nanmin(points, axis=0), np.nanmax(points, axis=0)].tolist(),
    }])
    source.close()
    return process_take(paths.root, config)


def _label(version: Path, schema) -> None:  # noqa: ANN001
    review = ReviewSession.open(version)
    store = AnnotationStore(
        take_dir=review.take_dir,
        document=review.empty_document(),
        annotator="koc",
        resolve=review.dataset.position_of_anchor,
        anchor_at=review.dataset.anchor_at,
        frames=review.frames,
        known_exercises=schema.exercise_codes(),
        known_error_classes=schema.error_type_codes(),
    )
    sample = store.add_movement(4, 18)
    store.label_movement(sample.sample_id, schema.exercise_codes()[0])
    store.flush()

    frames = review.dataset.stream.frames
    subject = SubjectStore(
        take_dir=review.take_dir,
        document=load_subject_review(
            review.take_dir, review.run_id, review.source_fingerprint
        ),
        candidates=scan_candidates(frames),
        annotator="koc",
    )
    subject.set_intervals(scan_unsettled(frames, review.dataset.anchor_at))
    subject.choose_athlete(subject.candidates[0].tracker_id)
    if subject.document.unanswered:
        subject.answer_all_remaining(Verdict.SAME_ATHLETE)
    subject.flush()
    review.close()


@pytest.fixture
def project(workspace, session):
    """Two versions: one fully labelled, one untouched."""
    schema = workspace.label_schema
    schema.ensure_exercise("Squat")
    schema.ensure_error_type("Knee valgus")
    workspace.save_label_schema(schema)

    done = _record(workspace, session, seed=31)
    _label(done, schema)
    untouched = _record(workspace, session, seed=32)
    return SessionService(config=None, identity=None, workspace=workspace), done, untouched


# --------------------------------------------------------------- veri seti
def test_the_overview_separates_what_is_ready_from_what_is_waiting(project) -> None:
    session, done, untouched = project
    model = DatasetViewModel(session)
    model.reload(force=True)

    rows = {r.run_id: r for r in model.rows.value}
    assert len(rows) == 2
    labelled = rows[Path(done).name]
    blank = rows[Path(untouched).name]

    assert labelled.looks_ready and labelled.ready == 1
    assert not blank.looks_ready and blank.movements == 0
    assert "athlete" in blank.blockers or "unlabelled" in blank.blockers
    assert blank.text  # and it says what it is waiting on


def test_the_overview_totals_count_every_version(project) -> None:
    session, _done, _untouched = project
    model = DatasetViewModel(session)
    model.reload(force=True)
    totals = model.totals.value
    assert totals.versions == 2
    assert totals.looks_ready == 1
    assert totals.ready_movements == 1
    assert "1/1 hareket" in totals.text


def test_the_overview_page_filters_without_reloading(qapp, project) -> None:
    session, _done, _untouched = project
    page = DatasetPage(destination("dataset"), load_tokens("dark"))
    model = DatasetViewModel(session)
    page.attach(model)
    try:
        model.reload(force=True)
        assert page.model.rowCount() == 2
        page.filter_box.setCurrentIndex(1)          # "Hazır görünüyor"
        assert page.model.rowCount() == 1
        page.filter_box.setCurrentIndex(0)
        assert page.model.rowCount() == 2
    finally:
        page.close()


# ------------------------------------------------------------ dışa aktarım
def test_the_check_runs_before_anything_is_written(qapp, project, tmp_path) -> None:
    session, _done, _untouched = project
    library = LibraryViewModel(session)
    library.reload(force=True)

    model = ExportViewModel(session)
    model.check(tuple(library.all_rows))

    rows = model.rows.value
    assert len(rows) == 2
    ready = [r for r in rows if r.accepted]
    blocked = [r for r in rows if not r.accepted]
    assert len(ready) == 1 and len(blocked) == 1
    assert blocked[0].reasons, "neden yazılmadan reddedilmiş"
    assert model.can_build.value


def test_building_writes_the_ready_version_and_records_the_other(
    qapp, project
) -> None:
    session, _done, _untouched = project
    library = LibraryViewModel(session)
    library.reload(force=True)

    model = ExportViewModel(session)
    model.check(tuple(library.all_rows))
    reports = []
    model.finished.subscribe(reports.append)
    model.build()

    assert reports, "dışa aktarım tamamlanmadı"
    report = reports[0]
    assert report.samples == 1
    assert report.release_dir is not None

    manifest = read_json(report.release_dir / "manifest.json")
    assert manifest["counts"]["versions_accepted"] == 1
    assert manifest["counts"]["versions_refused"] == 1
    assert manifest["refused_versions"][0]["refusal_text"]


def test_nothing_is_written_when_nothing_passes(qapp, workspace, session) -> None:
    schema = workspace.label_schema
    schema.ensure_exercise("Squat")
    workspace.save_label_schema(schema)
    _record(workspace, session, seed=44)   # recorded, never labelled

    service = SessionService(config=None, identity=None, workspace=workspace)
    library = LibraryViewModel(service)
    library.reload(force=True)
    model = ExportViewModel(service)
    model.check(tuple(library.all_rows))

    assert not model.can_build.value
    seen = []
    model.message.subscribe(seen.append)
    model.build()
    assert seen and "hazır sürüm yok" in seen[0].headline
    assert not model.last_release.value


def test_the_export_page_shows_every_version_including_the_refused(
    qapp, project
) -> None:
    session, _done, _untouched = project
    page = ExportPage(destination("export"), load_tokens("dark"))
    model = ExportViewModel(session)
    library = LibraryViewModel(session)
    page.attach(model)
    page.use_library(library)
    try:
        library.reload(force=True)
        page._check()
        assert page.model.rowCount() == 2, "reddedilen sürüm listeden düşmemeli"
        texts = [
            page.model.data(page.model.index(row, 4))
            for row in range(page.model.rowCount())
        ]
        assert all(texts), "her satır bir şey söylemeli"
    finally:
        page.close()
