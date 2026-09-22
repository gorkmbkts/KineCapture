"""The harness has to be trustworthy before anything is checked with it.

A test helper that silently does nothing is worse than no helper: every test
built on it goes green while proving nothing. So this file checks the harness
itself - that the double click really reaches the widget's handler, that the
body it builds faces the direction it claims, and that the scroll census sees
a scroll when there is one.
"""

from __future__ import annotations

import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kinecapture.features.roles import resolve_roles  # noqa: E402
from kinecapture.studio.services.skeleton3d import (  # noqa: E402
    FACING_SHOULDERS,
    facing_azimuth,
)

from _gui_harness import (  # noqa: E402
    KNOWN_FACING,
    clipped_controls,
    double_click,
    drag,
    facing_pose,
    scroll_census,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(params=["mock", "zed_body_34"])
def spec(request):
    """Both the shape the fixtures record and a real ZED one.

    A helper that only works for the synthetic skeleton would be a helper that
    quietly stops working on a real recording.
    """
    from kinecapture.visualization.skeleton_spec import MOCK_SKELETON, ZED_BODY_34

    return MOCK_SKELETON if request.param == "mock" else ZED_BODY_34


# ------------------------------------------------------------- the body


def test_the_harness_body_faces_the_direction_it_claims(spec) -> None:
    """Otherwise 'in front of the athlete' is untestable."""
    roles = resolve_roles(spec)
    pose = facing_pose(spec)
    angle, source = facing_azimuth(
        pose,
        left_shoulder=roles.get("left_shoulder"),
        right_shoulder=roles.get("right_shoulder"),
        left_hip=roles.get("left_hip"),
        right_hip=roles.get("right_hip"),
    )
    assert source == FACING_SHOULDERS
    assert angle == pytest.approx(KNOWN_FACING, abs=0.02)


def test_the_harness_body_is_asymmetric(spec) -> None:
    """A symmetric pose passes a left/right check with the sign backwards."""
    roles = resolve_roles(spec)
    pose = facing_pose(spec)
    left = pose[roles["left_shoulder"]]
    right = pose[roles["right_shoulder"]]
    assert not np.allclose(np.abs(left), np.abs(right))


def test_only_joints_the_pose_places_are_finite(spec) -> None:
    """An invented joint is a pickable point that means nothing.

    Stated as a correspondence rather than "something is NaN": the 16-joint
    mock has a role for every joint it has, so nothing is left over there,
    while ZED's 34 include fingers and feet the pose says nothing about.
    """
    roles = resolve_roles(spec)
    placed = {
        roles[name]
        for name in (
            "left_shoulder", "right_shoulder", "left_hip", "right_hip",
            "left_elbow", "right_elbow", "left_wrist", "right_wrist",
            "left_knee", "right_knee", "left_ankle", "right_ankle",
            "pelvis", "chest", "neck", "head", "nose",
        )
        if roles.get(name) is not None
    }
    pose = facing_pose(spec)
    assert placed, "the fixture must place something"
    for index in range(spec.num_joints):
        finite = bool(np.isfinite(pose[index]).all())
        assert finite is (index in placed), spec.joint_names[index]


@pytest.mark.parametrize("facing_degrees", [0.0, 90.0, 180.0, 270.0])
def test_any_facing_can_be_built_and_recovered(spec, facing_degrees) -> None:
    roles = resolve_roles(spec)
    wanted = math.radians(facing_degrees)
    pose = facing_pose(spec, facing=wanted)
    angle, _source = facing_azimuth(
        pose,
        left_shoulder=roles.get("left_shoulder"),
        right_shoulder=roles.get("right_shoulder"),
    )
    assert (angle - wanted) % (2 * math.pi) == pytest.approx(0.0, abs=0.02)


# ------------------------------------------------------------ input events


class _Spy(QWidget):
    """A widget that records the events the harness claims to send."""

    def __init__(self) -> None:
        super().__init__()
        self.resize(200, 200)
        self.double_clicks: list[tuple[int, int]] = []
        self.presses = 0
        self.moves = 0

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: ANN001, N802
        position = event.position()
        self.double_clicks.append((int(position.x()), int(position.y())))

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802, ARG002
        self.presses += 1

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802, ARG002
        self.moves += 1


def test_the_double_click_helper_reaches_the_widgets_own_handler(app) -> None:
    """The point of the helper. Calling a slot would skip the hit test."""
    spy = _Spy()
    spy.show()
    app.processEvents()
    double_click(spy, 60, 90)
    app.processEvents()
    assert spy.double_clicks == [(60, 90)]
    spy.close()


def test_the_drag_helper_sends_moves_not_a_teleport(app) -> None:
    """One press and one release at a different point is not a drag, and the
    3-D view separates turning from selecting by how far the pointer went."""
    spy = _Spy()
    spy.setMouseTracking(True)
    spy.show()
    app.processEvents()
    drag(spy, (20, 20), (120, 60), steps=5)
    app.processEvents()
    assert spy.presses == 1
    assert spy.moves >= 5


# --------------------------------------------------------------- measuring


def _scrolling_panel() -> QScrollArea:
    area = QScrollArea()
    inner = QWidget()
    column = QVBoxLayout(inner)
    for index in range(40):
        column.addWidget(QLabel(f"satır {index}"))
    area.setWidget(inner)
    area.setWidgetResizable(True)
    area.resize(120, 80)
    return area


def test_the_scroll_census_sees_a_scroll_that_is_there(app) -> None:
    holder = QWidget()
    column = QVBoxLayout(holder)
    column.addWidget(_scrolling_panel())
    holder.resize(140, 100)
    holder.show()
    app.processEvents()
    found = scroll_census(holder)
    assert any(entry["axis"] == "vertical" and entry["range"] > 0 for entry in found)
    holder.close()


def test_the_scroll_census_is_quiet_when_everything_fits(app) -> None:
    holder = QWidget()
    column = QVBoxLayout(holder)
    area = QScrollArea()
    inner = QWidget()
    QVBoxLayout(inner).addWidget(QLabel("tek satır"))
    area.setWidget(inner)
    area.setWidgetResizable(True)
    column.addWidget(area)
    holder.resize(400, 300)
    holder.show()
    app.processEvents()
    assert scroll_census(holder) == []
    holder.close()


def test_the_clipping_check_notices_text_that_does_not_fit(app) -> None:
    holder = QWidget()
    column = QVBoxLayout(holder)
    label = QLabel("çok uzun bir Türkçe etiket metni burada duruyor")
    label.setFixedWidth(30)
    column.addWidget(label)
    holder.resize(60, 60)
    holder.show()
    app.processEvents()
    assert clipped_controls(holder)
    holder.close()
