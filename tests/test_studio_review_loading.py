"""Getting into Etiketleme: the window, the wait, and what is claimed about it.

Three measured failures are pinned here.

**The window was being recreated.** Qt composites a ``QOpenGLWidget`` through a
QRhi-backed surface and the top-level has to be created that way, so adding the
first one to a window already on screen destroys and rebuilds the native
window. Measured on 19 September: winId 983812 -> 1049348. The shell now
creates a one-pixel primer before ``show()``.

**The wait said nothing.** 99.7% of opening a version is re-hashing its derived
files - 6.8 s on a 2.7 GB version - and the screen reported none of it, then
cleared "busy" before the editor had been built.

**A percentage was not available, so none may be invented.** Only the checksum
walk has a denominator. Everything else reports as a step.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtOpenGLWidgets import QOpenGLWidget  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.core.fingerprint import (  # noqa: E402
    checksum_manifest,
    verify_checksum_manifest,
)
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.review import STAGE_TEXT, LoadStage  # noqa: E402
from kinecapture.studio.viewmodels.review import LoadProgress  # noqa: E402

from conftest import enter_the_workspace  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    config.log_dir = tmp_path / "logs"
    config.dataset_root.mkdir(parents=True)
    built = build_window(config, state_path=tmp_path / "window.json")
    built.resize(1600, 900)
    built.show()
    assert built.auth_viewmodel.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    app.processEvents()
    # Past the project/participant gate: from 20 September every screen but
    # Projeler needs a project open in this session.
    enter_the_workspace(built, app)
    yield built
    built.close()


# ------------------------------------------------------------------ LOAD-01


def test_the_window_is_gl_capable_before_it_is_shown(window) -> None:
    """The fix, stated as the property it guarantees."""
    primers = [
        child
        for child in window.centralWidget().findChildren(QOpenGLWidget)
        if child.objectName() == "kcGlPrimer"
    ]
    assert primers, "no GL primer: the window will be recreated on first 3-D use"
    primer = primers[0]
    assert primer.width() == 1 and primer.height() == 1
    assert not primer.isVisibleTo(window)


def test_entering_labelling_does_not_replace_the_native_window(window, app) -> None:
    before = int(window.winId())
    window.viewmodel.navigate("review")
    app.processEvents()
    page = window.page("review")
    assert page is not None
    after = int(window.winId())
    assert after == before, (
        f"native window replaced: {before} -> {after}; the primer is not working"
    )


def test_repeated_visits_do_not_replace_it_either(window, app) -> None:
    before = int(window.winId())
    for _ in range(3):
        for key in ("review", "library", "review", "projects"):
            window.viewmodel.navigate(key)
            app.processEvents()
    assert int(window.winId()) == before


def test_the_window_keeps_its_size_across_the_first_visit(window, app) -> None:
    size = (window.width(), window.height())
    window.viewmodel.navigate("review")
    app.processEvents()
    assert (window.width(), window.height()) == size


# ------------------------------------------------------------------ LOAD-02


def test_the_checksum_walk_reports_real_bytes(tmp_path) -> None:
    files = {}
    for index, size in enumerate((100, 2000, 30000)):
        path = tmp_path / f"f{index}.bin"
        path.write_bytes(b"x" * size)
        files[path.name] = path
    manifest = checksum_manifest(files)

    readings: list[tuple[int, int]] = []
    problems = verify_checksum_manifest(
        manifest, tmp_path, progress=lambda done, total: readings.append((done, total))
    )
    assert problems == []
    assert readings, "no progress was reported"
    totals = {total for _done, total in readings}
    # One total, and it is the real number of bytes on disk.
    assert totals == {100 + 2000 + 30000}
    assert readings[0][0] == 0
    assert readings[-1][0] == 32100
    # Monotonic: a progress bar that goes backwards is worse than none.
    assert [done for done, _t in readings] == sorted(done for done, _t in readings)


def test_the_walk_stops_when_the_caller_has_moved_on(tmp_path) -> None:
    for index in range(6):
        (tmp_path / f"f{index}.bin").write_bytes(b"x" * 1000)
    manifest = checksum_manifest(
        {p.name: p for p in sorted(tmp_path.glob("*.bin"))}
    )
    hashed: list[int] = []

    def progress(done: int, _total: int) -> None:
        hashed.append(done)

    verify_checksum_manifest(
        manifest,
        tmp_path,
        progress=progress,
        cancelled=lambda: len(hashed) >= 3,
    )
    # Stopped early rather than running the whole walk out.
    assert len(hashed) < 7


def test_a_stage_with_no_denominator_has_no_percentage() -> None:
    step = LoadProgress(stage=LoadStage.VIDEO.value, text="Video hazırlanıyor")
    assert step.fraction is None
    assert step.percent_text == ""
    assert step.eta_text == ""


def test_a_measured_stage_reads_as_a_percentage_and_a_time() -> None:
    measured = LoadProgress(
        stage=LoadStage.VERIFY.value, text="x", fraction=0.42, eta_s=95.0
    )
    assert measured.percent_text == "%42"
    assert measured.eta_text == "yaklaşık 01:35"


def test_every_stage_has_a_sentence() -> None:
    for stage in LoadStage:
        assert STAGE_TEXT[stage], stage


def test_the_surface_shows_an_indeterminate_bar_without_a_fraction(
    window, app
) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    page = window.page("review")
    page.loading.show_progress(
        LoadProgress(stage="video", text="Video hazırlanıyor", fraction=None)
    )
    app.processEvents()
    assert page.loading.bar.minimum() == 0 and page.loading.bar.maximum() == 0
    assert page.loading.detail.text() == ""
    assert page.loading.stage.text() == "Video hazırlanıyor"


def test_the_surface_shows_the_real_number_when_there_is_one(window, app) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    page = window.page("review")
    page.loading.show_progress(
        LoadProgress(stage="verify", text="x", fraction=0.5, eta_s=12.0)
    )
    app.processEvents()
    assert page.loading.bar.maximum() == 100
    assert page.loading.bar.value() == 50
    assert "%50" in page.loading.detail.text()
    assert "00:12" in page.loading.detail.text()


# ------------------------------------------------------------------ LOAD-03


def test_the_editor_is_hidden_until_there_is_something_to_edit(window, app) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    page = window.page("review")
    viewmodel = window.viewmodel_for["review"]
    # Nothing open: the preparation surface is what is showing.
    assert page.surface.currentWidget() is page.loading

    viewmodel.busy.set(True)
    app.processEvents()
    assert page.surface.currentWidget() is page.loading

    # Not busy is not the same as ready. An open that was cancelled or that
    # failed also stops being busy, and the editor must not appear for either
    # of them - an empty editor with live drawing tools on it is exactly the
    # state that produced a 0-0 movement in the September audit.
    viewmodel.busy.set(False)
    app.processEvents()
    assert viewmodel.review is None
    assert page.surface.currentWidget() is page.loading
    assert page._editing_enabled is False


def test_busy_is_only_cleared_by_the_screen(window, app) -> None:
    """The viewmodel no longer clears it when the worker returns."""
    import inspect

    from kinecapture.studio.viewmodels import review as module

    source = inspect.getsource(module.ReviewViewModel.open_version)
    # The success path does not touch busy; `ready()` does.
    assert "self.busy.set(False)" in source  # the failure path still does
    assert source.count("self.busy.set(False)") == 1
    ready = inspect.getsource(module.ReviewViewModel.ready)
    assert "self.busy.set(False)" in ready


def test_ready_is_idempotent(window, app) -> None:
    viewmodel = window.viewmodel_for.get("review")
    if viewmodel is None:
        window.viewmodel.navigate("review")
        app.processEvents()
        viewmodel = window.viewmodel_for["review"]
    viewmodel.busy.set(True)
    viewmodel.ready()
    assert viewmodel.busy.value is False
    # A second call on an idle screen changes nothing.
    viewmodel.ready()
    assert viewmodel.busy.value is False


# ------------------------------------------------------------------ LOAD-04


def test_cancelling_an_open_leaves_a_clean_empty_state(window, app) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    page = window.page("review")
    viewmodel = window.viewmodel_for["review"]
    viewmodel.busy.set(True)
    viewmodel._directory = "somewhere"
    app.processEvents()

    assert viewmodel.cancel_open() is True
    app.processEvents()
    assert viewmodel.busy.value is False
    assert viewmodel.review is None
    assert page.surface.currentWidget() is page.loading
    assert page._editing_enabled is False
    # And there is nothing left to retry, so the way out is the library.
    assert viewmodel.retry_open() is False


def test_cancelling_when_nothing_is_loading_does_nothing(window, app) -> None:
    window.viewmodel.navigate("review")
    app.processEvents()
    viewmodel = window.viewmodel_for["review"]
    assert viewmodel.cancel_open() is False


def test_a_cancelled_open_invalidates_its_own_result(window, app) -> None:
    """The token moves, so a late worker result is dropped rather than shown."""
    window.viewmodel.navigate("review")
    app.processEvents()
    viewmodel = window.viewmodel_for["review"]
    viewmodel.busy.set(True)
    before = viewmodel._open_token
    viewmodel.cancel_open()
    assert viewmodel._open_token != before
