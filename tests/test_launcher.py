"""How the application presents itself when a user starts it for real.

The maximise happens in the launcher, not in the window, and the difference
matters twice over: a window that maximised itself in its constructor could not
be resized by a viewport test, and a launcher that faked it with a resize to
the screen rectangle would cover the task bar and lose the user's restored
size. Both mistakes are easy, silent, and only visible on a real desktop.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.app import run_gui  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def config(tmp_path):
    return AppConfig(
        dataset_root=tmp_path / "data",
        log_dir=tmp_path / "logs",
        identity_db_path=tmp_path / "identity.sqlite3",
    )


def test_the_launcher_asks_for_a_maximised_window(qapp, config, monkeypatch):
    """``showMaximized``, not a resize: the OS owns the window state."""
    calls: list[str] = []
    monkeypatch.setattr(
        MainWindow, "showMaximized", lambda self: calls.append("maximized")
    )
    monkeypatch.setattr(MainWindow, "show", lambda self: calls.append("show"))
    monkeypatch.setattr(MainWindow, "isVisible", lambda self: True)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    assert run_gui(config) == 0
    assert calls == ["maximized"], "no plain show, no manual resize"


def test_a_platform_that_cannot_maximise_still_gets_a_window(
    qapp, config, monkeypatch
):
    """Better a normal window than an invisible one."""
    calls: list[str] = []
    monkeypatch.setattr(
        MainWindow, "showMaximized", lambda self: calls.append("maximized")
    )
    monkeypatch.setattr(MainWindow, "show", lambda self: calls.append("show"))
    monkeypatch.setattr(MainWindow, "isVisible", lambda self: False)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    assert run_gui(config) == 0
    assert calls == ["maximized", "show"]


def test_the_window_itself_opens_at_a_normal_size(qapp, config):
    """So a viewport test can resize it, and so the OS keeps a restore size."""
    window = MainWindow(config)
    try:
        window.show()
        qapp.processEvents()
        assert not window.isMaximized(), "the constructor must not maximise"

        window.resize(1120, 700)
        qapp.processEvents()
        assert window.width() == 1120 and window.height() == 700
    finally:
        window.close()
        window.deleteLater()


def test_the_declared_minimum_is_the_smallest_supported_viewport(qapp, config):
    """1120x700 is the floor every geometry test checks against."""
    window = MainWindow(config)
    try:
        assert window.minimumSize().width() == 1120
        assert window.minimumSize().height() == 700
    finally:
        window.close()
        window.deleteLater()
