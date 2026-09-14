"""What happens when things go wrong.

The expensive failures in this application are quiet ones: an hour of
labelling lost to a crash, a half-written package that looks finished, a save
that failed while the screen said "kaydedildi". Each test below makes one of
those happen on purpose and checks that the work survives and that the user is
told.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.errors import StorageError  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.annotations import load_annotations  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.services.review import ReviewSession  # noqa: E402
from kinecapture.studio.services.session import SessionService  # noqa: E402
from kinecapture.studio.viewmodels.review import ReviewViewModel  # noqa: E402

FRAMES = 24


@pytest.fixture
def version(workspace, session) -> Path:
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(width=160, height=120, fps=30, seed=17, profile=profile)
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


@pytest.fixture
def labelling(workspace, version):
    model = ReviewViewModel(
        SessionService(config=None, identity=None, workspace=workspace)
    )
    model._attach(ReviewSession.open(version))
    model.store.known_exercises = ("squat",)
    yield model
    model.close()


# ------------------------------------------------------- labels are not lost
def test_a_failed_save_keeps_the_labels_and_says_so(labelling, monkeypatch) -> None:
    """The worst outcome is a lost edit that the screen reported as saved."""
    labelling.add_movement(2, 8)
    seen = []
    labelling.message.subscribe(seen.append)

    import kinecapture.studio.services.annotation_store as store_module

    def full(*_args, **_kwargs):
        raise StorageError("Diskte yer kalmadı.", code="disk_full")

    monkeypatch.setattr(store_module, "save_annotations", full)
    assert labelling.flush() is False
    assert seen and "kaydedilemedi" in seen[0].headline.lower()

    # Still in memory, still marked unsaved, so the next attempt writes it.
    assert labelling.store.is_dirty
    assert labelling.dirty.value
    assert len(labelling.movements.value) == 1


def test_the_labels_are_written_on_the_next_attempt(labelling, monkeypatch) -> None:
    labelling.add_movement(3, 9)
    import kinecapture.studio.services.annotation_store as store_module

    real = store_module.save_annotations
    calls = {"n": 0}

    def flaky(take_dir, document):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("geçici hata")
        return real(take_dir, document)

    monkeypatch.setattr(store_module, "save_annotations", flaky)
    assert labelling.flush() is False
    assert labelling.flush() is True
    assert not labelling.dirty.value

    review = labelling.review
    document = load_annotations(
        review.take_dir, review.run_id, review.source_fingerprint
    )
    assert len(document.samples) == 1


def test_labels_written_before_a_crash_are_there_afterwards(labelling) -> None:
    """Simulates the process dying: nothing is closed, nothing is flushed."""
    sample_id = labelling.add_movement(4, 12)
    labelling.label_movement(sample_id, "squat")
    labelling.flush()   # what autosave would have done

    review = labelling.review
    take_dir, run_id, fingerprint = (
        review.take_dir, review.run_id, review.source_fingerprint
    )
    # The viewmodel is abandoned without close(), as a crash would.
    labelling.store = None
    labelling.review = None

    document = load_annotations(take_dir, run_id, fingerprint)
    assert len(document.samples) == 1
    assert document.samples[0].exercise == "squat"
    assert document.samples[0].reviewed_at


def test_the_screen_reports_unsaved_work(qapp_free=None) -> None:
    """The indicator must follow the store, not the last user action."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.viewmodels.navigation import destination
    from kinecapture.studio.views.pages.review import ReviewPage

    QApplication.instance() or QApplication([])
    page = ReviewPage(destination("review"), load_tokens("dark"))
    try:
        page._changes_pending(True)
        assert page.save_state.text() == "kaydedilmedi"
        assert page._autosave.isActive()
        page._changes_pending(False)
        assert page.save_state.text() == "kaydedildi"
        assert not page._autosave.isActive()
    finally:
        page.close()


# ---------------------------------------------------- a broken sidecar
def test_a_corrupt_sidecar_does_not_stop_the_screen_opening(
    workspace, version
) -> None:
    """A file that cannot be parsed is reported; the version still opens."""
    review = ReviewSession.open(version)
    path = review.dataset.annotation_file
    path.parent.mkdir(parents=True, exist_ok=True)
    from kinecapture.core.paths import long_path

    with open(long_path(path), "w", encoding="utf-8") as stream:
        stream.write("{ this is not json")
    review.close()

    model = ReviewViewModel(
        SessionService(config=None, identity=None, workspace=workspace)
    )
    seen = []
    model.message.subscribe(seen.append)
    try:
        model._attach(ReviewSession.open(version))
        assert model.review is not None       # the screen is usable
        assert model.store is not None
        assert model.movements.value == ()    # ...and starts empty, not wrong
        # Silently starting empty would look exactly like "no labels yet",
        # which is the one thing a damaged file must not be mistaken for.
        assert seen, "bozuk etiket dosyası sessizce yutuldu"
        assert "açılamadı" in seen[0].headline.lower()
    finally:
        model.close()


def test_an_existing_sidecar_is_never_silently_replaced(labelling) -> None:
    """Opening a version must not blank labels that are already on disk."""
    sample_id = labelling.add_movement(6, 14)
    labelling.label_movement(sample_id, "squat")
    labelling.flush()
    review = labelling.review
    directory = Path(review.dataset.directory)
    labelling.close()

    again = ReviewViewModel(
        SessionService(config=None, identity=None, workspace=None)
    )
    try:
        again._attach(ReviewSession.open(directory))
        assert len(again.movements.value) == 1
        assert again.movements.value[0].start == 6
    finally:
        again.close()


# --------------------------------------------------- unexpected exceptions
def test_an_unexpected_exception_becomes_a_message_not_a_dead_window() -> None:
    """Qt would otherwise let an exception escape a slot and abort the
    process, losing whatever the user was in the middle of."""
    import sys
    import types

    from kinecapture.studio.app import install_exception_hook

    reported = []
    window = types.SimpleNamespace(
        viewmodel=types.SimpleNamespace(report=reported.append)
    )
    original = sys.excepthook
    chained = []
    sys.excepthook = lambda *args: chained.append(args)
    try:
        install_exception_hook(window)
        try:
            raise RuntimeError("beklenmeyen")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)

        assert reported, "kullanıcıya bir şey söylenmedi"
        assert reported[0].headline
        assert reported[0].technical.get("tip") == "RuntimeError"
        # The previous hook still runs, so nothing swallows the traceback.
        assert chained
    finally:
        sys.excepthook = original


def test_a_reporter_that_itself_fails_does_not_re_raise() -> None:
    """The last line of defence must not be the thing that crashes."""
    import sys
    import types

    from kinecapture.studio.app import install_exception_hook

    def broken(_message):  # noqa: ANN001
        raise RuntimeError("raporlayıcı da bozuk")

    window = types.SimpleNamespace(viewmodel=types.SimpleNamespace(report=broken))
    original = sys.excepthook
    sys.excepthook = lambda *_args: None
    try:
        install_exception_hook(window)
        try:
            raise ValueError("asıl hata")
        except ValueError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)   # must not raise
    finally:
        sys.excepthook = original


# ------------------------------------------------------------ long paths
def test_a_long_path_is_handled_before_it_reaches_the_user(tmp_path) -> None:
    """Windows' 260-character limit must not surface as WinError 3."""
    from kinecapture.core.paths import ensure_dir, long_path, path_exists

    deep = tmp_path
    for index in range(12):
        deep = deep / f"klasor-{index}-{'x' * 20}"
    ensure_dir(deep)
    target = deep / "veri.json"
    write_json(target, {"ok": True})

    assert len(str(target)) > 260
    assert path_exists(target)
    # The plain pathlib answer is wrong here, which is exactly why the
    # application never asks it.
    assert not target.exists()
    assert Path(long_path(target)).exists()
