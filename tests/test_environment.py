"""Environment, import and configuration guarantees."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.config import AppConfig, load_config
from kinecapture.core.errors import ConfigError
from kinecapture.domain.enums import BackendKind


def test_interpreter_is_kinesynth() -> None:
    """The suite must run in the project's environment, not a stray one.

    A warning rather than a failure: the code is environment-agnostic, but a
    result produced elsewhere does not prove anything about the machine the
    application actually runs on.
    """
    executable = Path(sys.executable)
    if "kinesynth" not in str(executable).lower():
        pytest.skip(
            f"Testler KineSynth disinda calisiyor ({executable}). "
            "scripts\\run_tests.ps1 kullanin."
        )
    assert executable.is_file()


def test_package_imports_without_zed_sdk() -> None:
    """Importing the application must never pull in ``pyzed``.

    Checked in a subprocess so this test's own import history cannot mask a
    module-level import that only happens on a cold start.
    """
    code = (
        "import sys\n"
        "import kinecapture, kinecapture.app, kinecapture.camera\n"
        "import kinecapture.capture.service, kinecapture.dataset.workspace\n"
        "import kinecapture.export.release, kinecapture.playback.take_reader\n"
        "import kinecapture.annotations.repository\n"
        "loaded = [m for m in sys.modules if m.startswith('pyzed')]\n"
        "print('PYZED_LOADED' if loaded else 'PYZED_ABSENT')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "PYZED_ABSENT" in result.stdout, result.stdout


def test_zed_backend_module_imports_without_sdk() -> None:
    """The ZED module itself imports cleanly and reports availability instead."""
    from kinecapture.camera.zed import ZedCameraBackend

    backend = ZedCameraBackend()
    result = backend.is_available()
    # Either outcome is valid; what matters is that probing never raises and
    # always yields a machine-readable code.
    assert isinstance(result.available, bool)
    assert result.code in {
        "ok",
        "pyzed_missing",
        "no_camera_detected",
        "camera_busy",
    }


def test_default_config_loads() -> None:
    config = load_config(include_user_state=False)
    assert config.app_name == APP_NAME
    assert config.preview_fps > 0
    assert config.capture.fps > 0
    assert config.capture.body_format in {"BODY_18", "BODY_34", "BODY_38"}


def test_config_rejects_unknown_backend() -> None:
    with pytest.raises(ConfigError, match="Bilinmeyen backend"):
        AppConfig(backend="webcam")


def test_config_rejects_invalid_values() -> None:
    with pytest.raises(ConfigError):
        AppConfig(preview_fps=0)
    with pytest.raises(ConfigError):
        AppConfig(log_level="TRACE")
    with pytest.raises(ConfigError):
        AppConfig(theme="neon")


def test_config_roundtrip_preserves_values(tmp_path: Path) -> None:
    config = AppConfig(backend=BackendKind.ZED, theme="light", preview_fps=24)
    restored = AppConfig.from_mapping(config.to_dict())
    assert restored.backend is BackendKind.ZED
    assert restored.theme == "light"
    assert restored.preview_fps == 24
    assert restored.capture.body_format == config.capture.body_format


def test_config_keeps_unknown_keys() -> None:
    """A newer config file must not lose information when read by this build."""
    config = AppConfig.from_mapping({"app_name": "X", "future_option": 42})
    assert config.extra["future_option"] == 42
    assert config.to_dict()["future_option"] == 42


def test_diagnostics_never_raises(tmp_path: Path) -> None:
    from kinecapture.core.diagnostics import collect_diagnostics

    report = collect_diagnostics(
        dataset_root=tmp_path / "data", backend=BackendKind.MOCK
    )
    assert report.checks
    assert report.app_version == APP_VERSION
    text = report.as_text()
    assert "ortam tanılaması" in text
    # The report is meant to be pasteable into a support message.
    assert "Traceback" not in text


def test_cli_self_test_succeeds() -> None:
    """The shipped ``--self-test`` really exercises the pipeline end to end."""
    from kinecapture.app import main

    assert main(["--self-test", "--log-level", "ERROR"]) == 0


def test_offline_layer_imports_without_qt_or_the_sdk() -> None:
    """The offline layer must stay usable while a recording is running.

    ``processing`` and the project index are what a review screen reads. If
    either pulled in Qt or ``pyzed`` at import time, opening a finished version
    would mean loading a GUI toolkit into a headless job, or touching the SDK
    while the camera is busy with a capture.
    """
    code = (
        "import sys\n"
        "import kinecapture.processing\n"
        "from kinecapture.processing.review import ReviewDataset\n"
        "from kinecapture.processing.arrays import ArrayStore\n"
        "from kinecapture.processing.summary import TimelineSummary\n"
        "from kinecapture.processing.thumbnails import ThumbnailIndex\n"
        "from kinecapture.processing.depth import DepthReader\n"
        "from kinecapture.dataset.summary_index import build_index\n"
        "loaded = sorted(m for m in sys.modules "
        "if m.split('.')[0] in ('pyzed', 'PySide6', 'shiboken6'))\n"
        "print('CLEAN' if not loaded else 'LOADED:' + ','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout
