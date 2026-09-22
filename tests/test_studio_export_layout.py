"""Dışa Aktarım: two halves, six states, and a result that can go stale.

The screen's job is to let somebody answer "what will be in this package, and
what will not" before anything is written. Two things this file guards.

**A state is named, not implied.** "Not checked yet" and "checked and every
version refused" are different answers to the same question. A screen with one
boolean shows the same thing for both, which is how a reader concludes that a
project with nothing exportable simply has not been checked.

**A green result can stop being true.** The package itself is never in danger -
``build_release`` re-inspects every version on the way in, so a stale preflight
cannot produce a wrong package. What can go wrong is the *screen*: labels
change, the row still says "Hazır", and somebody presses a button believing
something that is no longer so. So the result is compared against the revision
counters on disk, and the write is refused while it is out of date.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.jsonio import read_json, write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.export.canonical import current_revisions  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.annotations import annotation_path  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.viewmodels.export import (  # noqa: E402
    CHECK_STATE_TEXT,
    CheckState,
    ExportViewModel,
)
from kinecapture.studio.viewmodels.library import LibraryViewModel  # noqa: E402

FRAMES = 20


def _record(workspace, session, *, seed: int) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(
        width=160, height=120, fps=30, seed=seed, profile=profile
    )
    info = backend.connect()
    backend.start_preview()
    take, paths = workspace.prepare_take(
        session, origin=backend.origin, camera_info=info
    )
    writer = TakeWriter(workspace, take, paths, archive_color=True)
    for _ in range(FRAMES):
        writer.write_frame(backend.grab_frame())
    writer.finalize()
    backend.disconnect()

    config = ProcessingConfig(store_depth=False, store_proxy=False)
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
    return process_take(paths.root, config)


@pytest.fixture
def model(workspace, session) -> ExportViewModel:
    _record(workspace, session, seed=71)
    service = SessionService(config=None, identity=None, workspace=workspace)
    library = LibraryViewModel(service)
    library.reload(force=True)
    export = ExportViewModel(service)
    export.check(tuple(library.all_rows))
    return export


# ------------------------------------------------------------------ the states


def test_every_state_has_a_line_of_its_own() -> None:
    """A state with no wording is a state the screen cannot show."""
    for state in CheckState:
        assert CHECK_STATE_TEXT[state].strip()
    assert len(set(CHECK_STATE_TEXT.values())) == len(CheckState)


def test_an_unchecked_screen_says_so_rather_than_showing_a_verdict() -> None:
    service = SessionService(config=None, identity=None, workspace=None)
    export = ExportViewModel(service)
    assert export.state.value is CheckState.NOT_CHECKED
    assert not export.can_build.value


def test_nothing_to_check_is_not_the_same_as_not_checked() -> None:
    service = SessionService(config=None, identity=None, workspace=None)
    export = ExportViewModel(service)
    export.check(())
    assert export.state.value is CheckState.EMPTY


def test_every_version_refused_reads_as_blocked(model) -> None:
    """Nothing here is labelled, so nothing can go in - and the screen says
    that, instead of leaving the reader to infer it from an empty summary."""
    assert model.state.value is CheckState.BLOCKED
    assert not model.can_build.value


# ------------------------------------------------------------------ staleness


def test_a_result_survives_a_revisit_when_nothing_changed(model) -> None:
    assert model.recheck_freshness()
    assert model.state.value is CheckState.BLOCKED


def test_a_result_goes_stale_when_the_labels_underneath_it_change(
    model, workspace
) -> None:
    directory = Path(model.rows.value[0].directory)
    job = read_json(directory / "job.json")
    path = annotation_path(Path(job["take_dir"]), directory.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {"processing_run": directory.name, "revision": 9, "samples": []},
        overwrite=True,
    )

    assert not model.recheck_freshness()
    assert model.state.value is CheckState.STALE
    assert not model.can_build.value


def test_a_stale_result_refuses_the_write_and_says_why(model) -> None:
    directory = Path(model.rows.value[0].directory)
    job = read_json(directory / "job.json")
    path = annotation_path(Path(job["take_dir"]), directory.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        path,
        {"processing_run": directory.name, "revision": 4, "samples": []},
        overwrite=True,
    )

    seen = []
    model.message.subscribe(seen.append)
    model.build()
    assert seen and "değişti" in seen[0].headline


# --------------------------------------------------------- the narrow read


def test_an_unlabelled_version_is_revision_one_not_zero(model) -> None:
    """The absent sidecar has to report what the empty document reports, or a
    version nobody touched looks changed the moment it is checked."""
    directory = Path(model.rows.value[0].directory)
    assert current_revisions(directory) == (1, 1)


def test_an_unreadable_version_counts_as_changed(tmp_path) -> None:
    """The safe direction: it sends the reader back to the real check."""
    assert current_revisions(tmp_path / "nowhere") == (-1, -1)


def test_the_narrow_read_never_opens_the_dataset(model, monkeypatch) -> None:
    """It costs three small JSON reads. Opening the arrays would make it the
    expensive check it is explicitly not."""
    import kinecapture.export.canonical as canonical

    def refuse(*_args, **_kwargs):
        raise AssertionError("current_revisions must not open the dataset")

    monkeypatch.setattr(canonical, "ReviewDataset", refuse)
    directory = Path(model.rows.value[0].directory)
    assert current_revisions(directory) == (1, 1)
