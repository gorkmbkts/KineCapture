"""Open the real GUI TEST version in a real maximised window.

Read-only on the user's data: ``ReviewSession.open`` verifies and reads; it
writes nothing, and nothing here saves an annotation. The application's own
state - preferences, identity, window geometry - is sandboxed, so running this
cannot change what the user's own copy is configured to do.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtWidgets import QApplication

from kinecapture.core.config import AppConfig
from kinecapture.studio.app import build_window
from kinecapture.studio.services.review import ReviewSession

TAKE = Path(
    r"C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4"
    r"\participants\P0001\sessions\ses_20260916T151622_57a9"
    r"\takes\take_20260920T195059_c183"
)
BEFORE = TAKE / "derived" / "processing" / "run_4b8fd122e2c44eee"


def newest_run() -> Path:
    runs = sorted(
        (TAKE / "derived" / "processing").glob("run_*"),
        key=lambda p: (p / "job.json").stat().st_mtime,
    )
    return runs[-1]


def settle(app, seconds: float = 0.4) -> None:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()


def open_window(scratch: Path, *, window_state: str = ""):
    """A signed-in, maximised StudioWindow whose own state is sandboxed."""
    app = QApplication.instance() or QApplication([])
    config = AppConfig.sandboxed(scratch)
    config.dataset_root.mkdir(parents=True, exist_ok=True)
    state = scratch / "window.json"
    if window_state:
        state.write_text(window_state, encoding="utf-8")
    window = build_window(config, state_path=state)
    window.show()
    app.processEvents()
    if window.viewmodel.session.needs_initial_setup:
        assert window.auth_viewmodel.create_owner(
            first_name="Gercek", last_name="Kontrol", title="",
            username="gercek-kontrol", password="kinecapture1",
            password_confirm="kinecapture1",
        )
    else:
        assert window.auth_viewmodel.sign_in("gercek-kontrol", "kinecapture1")
    settle(app, 0.6)
    return app, window


def open_version(app, window, run: Path):
    """Put a real processed version on the labelling screen.

    A project first: every screen but Projeler is gated on one, so without it
    `navigate` refuses and the page is never laid out - which looks exactly
    like a broken layout when you go measuring one.
    """
    if window.viewmodel.session.workspace is None:
        projects = window.viewmodel_for["projects"]
        projects.reload_projects()
        assert projects.create_project("Olcum")
        settle(app, 0.6)
    assert window.viewmodel.navigate("review")
    settle(app, 0.4)
    page = window.page("review")
    review = ReviewSession.open(run, verify=False)
    page.viewmodel._attach(review)
    page._after_open()
    page._loading_changed(False)
    settle(app, 0.5)
    page._apply_stage_geometry()
    settle(app, 0.4)
    return page, review
