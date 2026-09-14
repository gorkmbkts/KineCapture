"""The six helper windows.

They exist to be believed: the usual reason to open one is that something
looks wrong and somebody needs to know exactly what the machine saw. So what
is tested is that they report what is really there, say "—" where there is
nothing rather than inventing a plausible value, and never block the work.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kinecapture.core.jsonio import read_json, write_json  # noqa: E402
from kinecapture.core.logging import ROOT_LOGGER_NAME  # noqa: E402
from kinecapture.studio.services.inspectors import (  # noqa: E402
    MISSING,
    LogBuffer,
    device_sections,
    diagnostics_sections,
    environment_sections,
    provenance_sections,
    raw_parameter_sections,
    sections_as_text,
    source_audit_sections,
)


# ------------------------------------------------------------------- log
def test_the_console_keeps_what_the_application_logged() -> None:
    buffer = LogBuffer(capacity=10).install()
    try:
        logging.getLogger(f"{ROOT_LOGGER_NAME}.test").warning("kamera bulunamadı")
        lines = buffer.lines()
        assert any("kamera bulunamadı" in line for line in lines)
        assert any("WARNING" in line for line in lines)
    finally:
        buffer.remove()


def test_the_console_filters_by_level_and_text() -> None:
    buffer = LogBuffer().install()
    log = logging.getLogger(f"{ROOT_LOGGER_NAME}.test")
    try:
        log.debug("ayrıntı")
        log.error("disk doldu")
        assert len(buffer.lines(minimum="ERROR")) == 1
        assert buffer.lines(contains="disk")
        assert not buffer.lines(contains="bulunmayan")
    finally:
        buffer.remove()


def test_the_console_forgets_the_oldest_rather_than_growing() -> None:
    """A window left open all day must not become the memory problem."""
    buffer = LogBuffer(capacity=5).install()
    root = logging.getLogger(ROOT_LOGGER_NAME)
    previous = root.level
    root.setLevel(logging.INFO)
    log = logging.getLogger(f"{ROOT_LOGGER_NAME}.test")
    try:
        for index in range(50):
            log.info("satır %d", index)
        assert len(buffer.records) == 5
        assert "satır 49" in buffer.lines()[-1]
    finally:
        root.setLevel(previous)
        buffer.remove()


def test_the_console_says_which_level_it_can_see() -> None:
    """An empty console must be explained, not mysterious: the application's
    own logging level decides what ever reaches this window."""
    from kinecapture.studio.services.inspectors import log_file_section

    root = logging.getLogger(ROOT_LOGGER_NAME)
    previous = root.level
    root.setLevel(logging.WARNING)
    try:
        rows = {r.label: r for r in log_file_section().rows}
        assert rows["Kayıt seviyesi"].value == "WARNING"
        assert rows["Kayıt seviyesi"].level == "warning"
        assert "seviyeyi değiştirmez" in rows["Kayıt seviyesi"].detail
    finally:
        root.setLevel(previous)


def test_a_broken_log_record_never_takes_the_application_down() -> None:
    buffer = LogBuffer().install()
    log = logging.getLogger(f"{ROOT_LOGGER_NAME}.test")
    try:
        log.info("%d ve %d", 1)   # deliberately wrong arity
    finally:
        buffer.remove()


# ---------------------------------------------------------------- device
def test_no_camera_says_so_rather_than_showing_blanks() -> None:
    sections = device_sections(None)
    assert sections[0].rows[0].value == "bağlı değil"
    assert sections[0].note


def test_the_device_window_reports_what_the_camera_declares() -> None:
    from kinecapture.camera.mock import MockCameraBackend

    backend = MockCameraBackend(width=160, height=120, fps=30, seed=1)
    info = backend.connect()
    try:
        sections = device_sections(info)
        rows = {r.label: r.value for section in sections for r in section.rows}
        assert rows["Model"] == info.model
        assert rows["Çözünürlük"] == "160 × 120"
        # Synthetic origin is carried, not hidden.
        assert rows["Köken"] == "synthetic"
    finally:
        backend.disconnect()


# ------------------------------------------------------------ parameters
def test_no_version_selected_is_stated(tmp_path: Path) -> None:
    sections = raw_parameter_sections(None)
    assert sections[0].rows[0].value == "seçilmedi"
    assert raw_parameter_sections(tmp_path)[0].rows[0].value == "seçilmedi"


def test_parameters_are_shown_verbatim(tmp_path: Path) -> None:
    write_json(tmp_path / "job.json", {
        "run_id": "run_1", "state": "complete", "schema_version": "1.1.0",
        "parameters": {"body_format": "BODY_38", "confidence_threshold": 40},
        "processing_camera": {"resolution": [1920, 1080], "target_fps": 60},
    })
    rows = {
        r.label: r.value
        for section in raw_parameter_sections(tmp_path)
        for r in section.rows
    }
    assert rows["run_id"] == "run_1"
    assert rows["body_format"] == "BODY_38"
    assert rows["confidence_threshold"] == "40"
    assert rows["target_fps"] == "60"


# ------------------------------------------------------------ provenance
def test_provenance_names_the_raw_source_the_labels_are_tied_to(tmp_path: Path) -> None:
    write_json(tmp_path / "job.json", {
        "run_id": "run_1", "state": "complete",
        "source": {"fingerprint": "sha256:abc"},
        "take_dir": str(tmp_path), "issues": [],
    })
    sections = provenance_sections(tmp_path)
    rows = {r.label: r for section in sections for r in section.rows}
    assert rows["Parmak izi"].value == "sha256:abc"
    assert "taşınmaz" in rows["Parmak izi"].detail


def test_provenance_lists_issues_as_warnings(tmp_path: Path) -> None:
    write_json(tmp_path / "job.json", {
        "run_id": "r", "state": "partial", "source": {"fingerprint": "x"},
        "issues": ["review_proxy_incomplete", "source_timestamp_gap"],
    })
    sections = provenance_sections(tmp_path)
    issues = next(s for s in sections if s.title == "Sorunlar")
    assert {r.label for r in issues.rows} == {
        "review_proxy_incomplete", "source_timestamp_gap"
    }
    assert all(r.level == "warning" for r in issues.rows)


def test_offline_depth_is_labelled_as_reconstructed(tmp_path: Path) -> None:
    """Replaying an SVO does not return the measured depth; saying otherwise
    would let somebody treat it as a measurement."""
    write_json(tmp_path / "job.json", {
        "run_id": "r", "state": "complete", "source": {"fingerprint": "x"}, "issues": [],
    })
    (tmp_path / "depth").mkdir()
    sections = provenance_sections(tmp_path)
    depth = next(s for s in sections if s.title == "Derinlik")
    assert depth.rows[0].value == "reconstructed_offline"
    assert depth.rows[0].level == "warning"


# ----------------------------------------------------------------- audit
def test_a_version_without_checksums_cannot_be_verified(tmp_path: Path) -> None:
    section = source_audit_sections(tmp_path)[0]
    assert section.rows[0].value == "yok"
    assert section.rows[0].level == "warning"
    assert "yeniden işlemek" in section.note


def test_the_audit_passes_on_untouched_files(tmp_path: Path) -> None:
    from kinecapture.core.fingerprint import checksum_manifest

    payload = tmp_path / "arrays.bin"
    payload.write_bytes(b"0123456789")
    write_json(tmp_path / "checksums.json", checksum_manifest({"arrays.bin": payload}))
    section = source_audit_sections(tmp_path)[0]
    rows = {r.label: r for r in section.rows}
    assert rows["Doğrulama"].value == "geçti"
    assert rows["Doğrulama"].level == "ready"


def test_the_audit_names_a_file_that_changed(tmp_path: Path) -> None:
    from kinecapture.core.fingerprint import checksum_manifest

    payload = tmp_path / "arrays.bin"
    payload.write_bytes(b"0123456789")
    write_json(tmp_path / "checksums.json", checksum_manifest({"arrays.bin": payload}))
    payload.write_bytes(b"tampered!!")

    section = source_audit_sections(tmp_path)[0]
    rows = {r.label: r for r in section.rows}
    assert rows["Doğrulama"].value == "başarısız"
    assert rows["Doğrulama"].level == "error"
    assert "arrays.bin" in rows


# ------------------------------------------------------------------ text
def test_a_window_can_be_copied_as_text() -> None:
    text = sections_as_text(environment_sections())
    assert "== Uygulama" in text
    assert "Sürüm:" in text


def test_missing_values_are_marked_not_blank() -> None:
    sections = raw_parameter_sections(None)
    text = sections_as_text(sections)
    assert text
    assert device_sections(None)[0].rows[0].value != MISSING


# --------------------------------------------------------------- windows
def test_the_windows_open_without_blocking_anything() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.views.windows import WINDOW_TITLES, ToolWindow

    app = QApplication.instance() or QApplication([])
    tokens = load_tokens("dark")
    opened = []
    try:
        for key in WINDOW_TITLES:
            if key == "log":
                continue
            window = ToolWindow(key, tokens, environment_sections)
            opened.append(window)
            window.refresh()
            # Modeless and top-level: it can go to another monitor.
            assert window.parent() is None
            assert not window.isModal()
            assert window.tree.topLevelItemCount() > 0
            assert window.as_text()
        app.processEvents()
    finally:
        for window in opened:
            window.close()


def test_the_log_window_shows_the_buffer() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from kinecapture.studio.theme import load_tokens
    from kinecapture.studio.views.windows import LogWindow

    app = QApplication.instance() or QApplication([])
    buffer = LogBuffer().install()
    logging.getLogger(f"{ROOT_LOGGER_NAME}.test").error("kayıt düştü")
    window = LogWindow(load_tokens("dark"), buffer, environment_sections)
    try:
        window.refresh()
        assert "kayıt düştü" in window.view.toPlainText()
        window.level_box.setCurrentText("ERROR")
        assert "kayıt düştü" in window.view.toPlainText()
        assert "kayıt düştü" in window.as_text()
    finally:
        window.close()
        buffer.remove()
