"""Regression tests for creating a class without reopening a label dialog."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from kinecapture.domain.labels import LabelSchema  # noqa: E402
from kinecapture.domain.project import ErrorInterval, MovementSample  # noqa: E402
from kinecapture.gui.theme import build_stylesheet, get_theme  # noqa: E402
from kinecapture.gui.widgets.label_dialogs import (  # noqa: E402
    ErrorLabelDialog,
    MovementLabelDialog,
)
from kinecapture.visualization.skeleton_spec import (  # noqa: E402
    try_get_skeleton_spec,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def theme(qapp):
    selected = get_theme("dark")
    qapp.setStyleSheet(build_stylesheet(selected))
    return selected


def test_new_movement_class_can_be_saved_without_reopening(qapp, theme) -> None:
    dialog = MovementLabelDialog(
        theme,
        MovementSample.create("take_1", 0, 20),
        LabelSchema.default(),
    )
    dialog.show()
    qapp.processEvents()
    assert not dialog._save_button.isEnabled()

    dialog.picker._search.setText("Bulgar Split Squat")
    dialog.picker._create_button.click()
    qapp.processEvents()

    assert dialog.pending_new_class == "Bulgar Split Squat"
    assert dialog.requested_classes == ["Bulgar Split Squat"]
    assert dialog._save_button.isEnabled()
    dialog._save_button.click()
    assert dialog.result() == int(QDialog.DialogCode.Accepted)


def test_new_error_class_can_be_saved_without_reopening(qapp, theme) -> None:
    dialog = ErrorLabelDialog(
        theme,
        ErrorInterval.create(4, 16),
        LabelSchema.default(),
        skeleton_spec=try_get_skeleton_spec("zed_body_34"),
    )
    dialog.show()
    qapp.processEvents()
    assert not dialog._save_button.isEnabled()

    dialog.picker._search.setText("Topuk erken kalkıyor")
    dialog.picker._create_button.click()
    qapp.processEvents()

    assert dialog.pending_new_class == "Topuk erken kalkıyor"
    assert dialog.requested_classes == ["Topuk erken kalkıyor"]
    assert dialog._save_button.isEnabled()
    dialog._save_button.click()
    assert dialog.result() == int(QDialog.DialogCode.Accepted)
