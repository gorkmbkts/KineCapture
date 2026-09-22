"""A labelling screen that can be driven the way a person drives it.

Every acceptance claim in this round has to survive one question: *was that
checked through the interface, or through a method call?* The 20 September
audit found the previous round's joint-selection tests calling
``_joint_picked(index)`` directly - which proves the data path and says
nothing about whether a double click on a node reaches it, lands on the right
joint, or survives a high DPI ratio.

So this module builds the real window and sends real Qt input events. What it
adds over a plain fixture:

* an **asymmetric body whose facing is known by construction**, so "in front
  of the athlete" is a checkable claim rather than a matter of opinion;
* helpers that click where a widget actually is, in its own coordinates,
  through ``QTest`` - press, double click, drag;
* a scroll census, because "no scrolling in the top panel" is a measurement.

The recording is synthetic and lives in a temporary directory. No user
recording, label, identity database or setting is read or written.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QWidget  # noqa: E402

from kinecapture.camera.mock import MockCameraBackend  # noqa: E402
from kinecapture.core.config import AppConfig  # noqa: E402
from kinecapture.core.jsonio import write_json  # noqa: E402
from kinecapture.domain.project import CaptureProfile  # noqa: E402
from kinecapture.processing import ProcessingConfig, process_take  # noqa: E402
from kinecapture.processing.sources import SyntheticSource  # noqa: E402
from kinecapture.recording.take_writer import TakeWriter  # noqa: E402
from kinecapture.studio.app import build_window  # noqa: E402
from kinecapture.studio.services.review import ReviewSession  # noqa: E402

FRAMES = 24

#: The direction the harness's body faces, in its own ground plane, as an
#: orbit azimuth. Ninety degrees is ``+z`` for a y-up recording.
KNOWN_FACING = math.pi / 2


# --------------------------------------------------------------- a real take


def record_and_process(workspace, session, *, width: int = 320, height: int = 180) -> Path:
    """One short synthetic take, processed, anchored the way capture anchors.

    The resolution is a parameter because the layout is solved from the
    recording's own aspect ratio, and a screen that only works at 16:9 is a
    screen that assumes rather than reads.
    """
    profile = CaptureProfile(fps=30, min_free_disk_minutes=0)
    session.capture_profile = profile
    backend = MockCameraBackend(
        width=width, height=height, fps=30, seed=11, profile=profile
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


# ------------------------------------------------------- a body with a front


def facing_pose(spec, *, up_axis: int = 1, facing: float = KNOWN_FACING) -> np.ndarray:
    """A standing body facing a known direction, in this skeleton's own order.

    Built from the anatomy: the shoulders and hips are placed across the
    facing direction, the head above, the feet below. Deliberately asymmetric
    left to right - a symmetric pose would pass a left/right check that has
    the sign backwards.

    Joints this skeleton does not have a role for are left NaN. They are not
    filled in: an invented joint would be a pickable point that means nothing.
    """
    from kinecapture.features.roles import resolve_roles

    roles = resolve_roles(spec)
    joints = np.full((spec.num_joints, 3), np.nan, dtype=np.float32)
    a, b = [i for i in (0, 1, 2) if i != up_axis]

    forward = np.zeros(3, dtype=np.float64)
    forward[a] = math.cos(facing)
    forward[b] = math.sin(facing)
    up = np.zeros(3, dtype=np.float64)
    up[up_axis] = 1.0
    left = np.cross(up, forward)

    def place(role: str, side: float, height: float, ahead: float = 0.0) -> None:
        index = roles.get(role)
        if index is None:
            return
        joints[index] = (left * side + forward * ahead).astype(np.float32)
        joints[index, up_axis] = np.float32(height)

    place("left_shoulder", 0.20, 1.42)
    place("right_shoulder", -0.20, 1.40)     # asymmetric on purpose
    place("left_hip", 0.12, 0.96)
    place("right_hip", -0.12, 0.95)
    place("left_elbow", 0.26, 1.12, 0.04)
    place("right_elbow", -0.24, 1.10, -0.02)
    place("left_wrist", 0.30, 0.86, 0.08)
    place("right_wrist", -0.28, 0.84, -0.04)
    place("left_knee", 0.13, 0.52, 0.03)
    place("right_knee", -0.13, 0.50, 0.01)
    place("left_ankle", 0.13, 0.08)
    place("right_ankle", -0.13, 0.08)
    place("pelvis", 0.0, 0.98)
    place("chest", 0.0, 1.25)
    place("neck", 0.0, 1.50)
    place("head", 0.0, 1.68)
    place("nose", 0.0, 1.66, 0.10)
    return joints


# ------------------------------------------------------------ the real window


def sign_in(window, app, *, username: str = "harness") -> None:
    session = window.viewmodel.session
    if session.needs_initial_setup:
        assert window.auth_viewmodel.create_owner(
            first_name="Test", last_name="Harness", title="",
            username=username, password="kinecapture1",
            password_confirm="kinecapture1",
        )
    else:
        assert window.auth_viewmodel.sign_in(username, "kinecapture1")
    app.processEvents()


def open_review(
    app: QApplication,
    tmp_path: Path,
    monkeypatch,
    processed: Path,
    workspace,
    *,
    size: tuple[int, int] = (1600, 900),
):
    """The labelling screen, on a real version, ready to be driven.

    Returns ``(view, window, app)``. The caller closes the window.
    """
    # Every location moves together, including the preference file. The
    # harness deliberately does *not* stub ``save_user_state`` any more: the
    # real function now refuses a sandboxed configuration that would land in
    # the user's own settings, and running it for real is what proves it.
    config = AppConfig.sandboxed(tmp_path / "harness")
    config.dataset_root.mkdir(parents=True, exist_ok=True)

    window = build_window(config, state_path=tmp_path / "harness-window.json")
    window.resize(*size)
    window.show()
    app.processEvents()
    sign_in(window, app)
    window.viewmodel.session.workspace = workspace
    window.viewmodel.navigate("review")
    app.processEvents()

    view = window.page("review")
    review = ReviewSession.open(processed)
    view.viewmodel._attach(review)
    view._after_open()
    # The editor is only laid out once the loading surface steps aside; the
    # attach path above bypasses the worker that normally does that.
    view._loading_changed(False)
    app.processEvents()
    view._apply_stage_geometry()
    app.processEvents()
    return view, window, review


def use_known_pose(view, app, *, zoom: float = 0.7) -> np.ndarray:
    """Put the harness body on screen and re-derive the front from it.

    Zoomed in a little by default. At the whole-body framing the joints
    project within a pick radius of each other, so aiming at one is genuinely
    ambiguous - which is correct behaviour and useless for a test that wants
    to check *where* a click lands. Zooming is also what a person does before
    pointing at a particular joint.
    """
    review = view.viewmodel.review
    spec = review.skeleton
    pose = facing_pose(spec)
    view.skeleton.set_joints(pose)
    view.skeleton.frame_on(pose[None, :, :])
    if zoom != 1.0:
        view.skeleton.camera = view.skeleton.camera.zoom(zoom)
    view._set_anatomical_front(pose[None, :, :], _camera_system(review))
    app.processEvents()
    return pose


def _camera_system(review) -> str:
    return (review.job.get("processing_camera") or {}).get("coordinate_system", "")


# ------------------------------------------------------------- input events


def widget_point(widget: QWidget, x: float, y: float) -> QPoint:
    """A point inside ``widget``, in the widget's own coordinates."""
    return QPoint(int(round(x)), int(round(y)))


def click(widget: QWidget, x: float, y: float, *, button=Qt.MouseButton.LeftButton) -> None:
    QTest.mouseClick(widget, button, Qt.KeyboardModifier.NoModifier, widget_point(widget, x, y))


def double_click(
    widget: QWidget, x: float, y: float, *, button=Qt.MouseButton.LeftButton
) -> None:
    """A real double click, through the same path a person's would take.

    ``QTest.mouseDClick`` delivers press/release/double-click/release, which
    is what the widget's own handlers see. Calling the slot directly would
    skip exactly the part that can be broken - the hit test.
    """
    QTest.mouseDClick(
        widget, button, Qt.KeyboardModifier.NoModifier, widget_point(widget, x, y)
    )


def drag(
    widget: QWidget,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    button=Qt.MouseButton.LeftButton,
    steps: int = 6,
) -> None:
    """Press, move in several steps, release. One step is not a drag."""
    begin = widget_point(widget, *start)
    QTest.mousePress(widget, button, Qt.KeyboardModifier.NoModifier, begin)
    for step in range(1, steps + 1):
        fraction = step / steps
        QTest.mouseMove(
            widget,
            widget_point(
                widget,
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            ),
        )
    QTest.mouseRelease(
        widget, button, Qt.KeyboardModifier.NoModifier, widget_point(widget, *end)
    )


def joint_screen_position(view, index: int) -> Optional[tuple[float, float]]:
    """Where a joint is on the 3-D widget right now, or ``None`` if off view."""
    projected = view.skeleton.projected_joints()
    if projected is None or index >= len(projected):
        return None
    x, y = float(projected[index][0]), float(projected[index][1])
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not (0 <= x < view.skeleton.width() and 0 <= y < view.skeleton.height()):
        return None
    return x, y


def aim_at_joint(view, wanted, app=None, *, clear_of=None, steps: int = 6):
    """A joint from ``wanted`` that can be clicked without ambiguity.

    `pick_joint` returns the joint *nearest the camera* among those under the
    pointer, so two nodes within a pick radius of each other are ambiguous by
    design. BODY_38 puts 38 joints on one body and several land that close at
    a whole-body framing. The fixture removes the ambiguity the way a person
    does - look at the joints, zoom in - rather than pretending it is absent.

    ``clear_of`` narrows which joints count as blockers. When the question is
    only "does clicking here select nothing", being clear of the joints that
    *can* be selected is enough.

    Returns ``(index, x, y)`` or raises.
    """
    from kinecapture.studio.views.skeleton3d import PICK_RADIUS_PX

    for _step in range(steps):
        positions = {}
        for index in range(len(view.skeleton.projected_joints())):
            found = joint_screen_position(view, index)
            if found is not None:
                positions[index] = found
        blockers = positions if clear_of is None else {
            i: pos for i, pos in positions.items() if i in clear_of
        }
        for index, (x, y) in positions.items():
            if index not in wanted:
                continue
            if all(
                (ox - x) ** 2 + (oy - y) ** 2 > (2 * PICK_RADIUS_PX) ** 2
                for other, (ox, oy) in blockers.items() if other != index
            ):
                return index, x, y
        pose = view.skeleton._joints
        if pose is not None:
            usable = [
                pose[i] for i in wanted
                if i < len(pose) and bool(np.isfinite(pose[i]).all())
            ]
            if usable:
                centre = np.mean(np.asarray(usable, dtype=float), axis=0)
                view.skeleton.camera = view.skeleton.camera.with_target(centre)
        view.skeleton.camera = view.skeleton.camera.zoom(0.7)
        if app is not None:
            app.processEvents()
    raise AssertionError("no joint can be aimed at unambiguously")


def named_joints(view) -> dict:
    """Joint index -> the role this recording's format calls it."""
    from kinecapture.features.roles import resolve_roles

    review = view.viewmodel.review
    spec = review.skeleton if review is not None else None
    if spec is None:
        return {}
    return {
        index: role
        for role, index in resolve_roles(spec).items()
        if index is not None
    }


def timeline_position(view, frame: int, lane: str) -> tuple[float, float]:
    """The pixel on the timeline for a frame in a lane, for a real click.

    Asked of the widget's own geometry rather than reproduced here. A helper
    that computed the position independently could agree with a broken
    widget, which is the failure mode this whole module exists to avoid.
    """
    timeline = view.timeline
    rect = timeline._lane_rects()[lane]
    return float(timeline._frame_to_x(frame)), float(rect.center().y())


# ---------------------------------------------------------------- measuring


def scroll_census(widget: QWidget) -> list[dict]:
    """Every visible scroll area that actually has somewhere to scroll.

    A hidden scrollbar is not the same as a panel that fits: what matters is
    whether content is out of reach, which is what a non-zero range means.
    """
    found: list[dict] = []
    for area in widget.findChildren(QAbstractScrollArea):
        if not area.isVisible():
            continue
        for name, bar in (
            ("vertical", area.verticalScrollBar()),
            ("horizontal", area.horizontalScrollBar()),
        ):
            if bar is not None and bar.maximum() > 0:
                inner = area.widget() if hasattr(area, "widget") else None
                found.append(
                    {
                        "widget": type(area).__name__,
                        "content": type(inner).__name__ if inner else "",
                        "axis": name,
                        "range": int(bar.maximum()),
                        "size": [area.width(), area.height()],
                    }
                )
    return found


def overlaps(root: QWidget) -> list[str]:
    """Visible widgets drawn on top of each other when they should not be.

    Only *siblings* - two children of the same parent - because a child
    covering its own parent is how every layout works. What this catches is a
    band that grew past the space it was given and now sits over the one above
    it, which is what a reader sees as text on top of a picture.

    Compared in the shared parent's coordinates, and asked of the widgets
    themselves rather than derived from a sum of heights: the first attempt
    here added the band heights plus an assumed spacing and reported an
    overlap of 66 px that was partly its own arithmetic.
    """
    found: list[str] = []
    seen: set[int] = set()
    stack: list[QWidget] = [root]
    while stack:
        parent = stack.pop()
        children = [
            child
            for child in parent.findChildren(
                QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
            )
            if child.isVisible() and child.width() > 0 and child.height() > 0
        ]
        stack.extend(children)
        for index, first in enumerate(children):
            for second in children[index + 1:]:
                key = id(first) * 1000003 + id(second)
                if key in seen:
                    continue
                seen.add(key)
                a, b = first.geometry(), second.geometry()
                hit = a.intersected(b)
                # A pixel of shared border is a rounding, not an overlap.
                if hit.width() > 1 and hit.height() > 1:
                    found.append(
                        f"{type(first).__name__} {a.getRect()} over "
                        f"{type(second).__name__} {b.getRect()} "
                        f"by {hit.width()}x{hit.height()}"
                    )
    return found


def clipped_controls(widget: QWidget) -> list[str]:
    """Visible labels and buttons whose text does not fit their box."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QLabel, QPushButton, QToolButton

    from kinecapture.studio.views.widgets import ElidedLabel

    bad: list[str] = []
    children: list[QWidget] = []
    for kind in (QLabel, QPushButton, QToolButton):
        children.extend(widget.findChildren(kind))
    for child in children:
        if not child.isVisible() or not child.text().strip():
            continue
        if child.width() <= 0 or child.height() <= 0:
            continue
        wrapping = isinstance(child, QLabel) and child.wordWrap()
        if wrapping:
            needed_w = child.width()
            needed_h = child.heightForWidth(child.width())
        elif isinstance(child, ElidedLabel):
            # An eliding label shortens itself to whatever width it is given,
            # so "does the text fit" is a question about the text it is
            # *drawing*, not about the sentence it would prefer to draw. Its
            # size hint is deliberately the full sentence - that is how the
            # layout knows to give it room when there is room - and measuring
            # against that would report every elision as a clipping.
            metrics = QFontMetrics(child.font())
            needed_w = metrics.horizontalAdvance(child.text())
            needed_h = metrics.height()
        else:
            hint = child.sizeHint()
            needed_w, needed_h = hint.width(), hint.height()
        if needed_w > child.width() + 2 or needed_h > child.height() + 2:
            bad.append(
                f"{type(child).__name__}('{child.text()[:30]}') "
                f"{child.width()}x{child.height()} needs {needed_w}x{needed_h}"
            )
    return bad


__all__ = [
    "FRAMES",
    "KNOWN_FACING",
    "aim_at_joint",
    "click",
    "clipped_controls",
    "double_click",
    "drag",
    "facing_pose",
    "joint_screen_position",
    "named_joints",
    "open_review",
    "overlaps",
    "record_and_process",
    "scroll_census",
    "sign_in",
    "timeline_position",
    "use_known_pose",
    "widget_point",
]
