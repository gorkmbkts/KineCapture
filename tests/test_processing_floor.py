"""The floor plane: what it may claim, and what it must not.

The distinction this file defends is between a plane the sensor *measured* and
a line drawn under the lowest foot. Both put a grid on the screen; only one is
evidence. A reader that cannot tell them apart would let "the athlete left the
ground" be asserted from a drawing aid.
"""

from __future__ import annotations

import pytest

from kinecapture.processing.floor import (
    CAMERA_SPACE,
    DETECTED,
    FLOOR_SCHEMA_VERSION,
    NOT_ATTEMPTED,
    NOT_FOUND,
    FloorPlane,
    camera_moved,
    detect_floor,
)

#: The plane this project's own recording really produced, measured on
#: 19 September 2026 from take_20260917T220755_c97c through the offline
#: pipeline's own code path. Kept here so the arithmetic below is exercised
#: against a real answer rather than a tidy invented one.
REAL = FloorPlane(
    status=DETECTED,
    equation=(-0.01802663691341877, 0.9975785613059998, 0.06717188656330109, 1.187995195388794),
    normal=(-0.01802663691341877, 0.9975785613059998, 0.06717188656330109),
    point=(-0.5239985585212708, -0.9714937806129456, -3.39898681640625),
    source_position=0,
    coordinate_system="right_handed_y_up",
    length_unit="meter",
    reference_space=CAMERA_SPACE,
    extra={"plane_type": "PLANE_TYPE.HORIZONTAL"},
)


# ------------------------------------------------------------------ FLOOR-03


def test_a_measured_plane_solves_for_a_height() -> None:
    height = REAL.height_at(-0.36, -3.10, up_axis=1)
    assert height is not None
    # The athlete's lowest measured foot in that window was -1.01 m, and the
    # SDK's plane agrees with it to a couple of centimetres - which is the
    # whole reason this is worth storing.
    assert height == pytest.approx(-1.00, abs=0.05)


def test_the_point_on_the_plane_satisfies_the_equation() -> None:
    a, b, c, d = REAL.equation
    x, y, z = REAL.point
    assert a * x + b * y + c * z + d == pytest.approx(0.0, abs=1e-4)


def test_the_normal_is_a_unit_vector() -> None:
    length = sum(component * component for component in REAL.normal) ** 0.5
    assert length == pytest.approx(1.0, abs=1e-4)


def test_the_reference_space_travels_with_the_plane() -> None:
    """A plane with no space attached is a plane nobody can place."""
    assert REAL.reference_space == CAMERA_SPACE
    assert REAL.coordinate_system == "right_handed_y_up"
    assert REAL.length_unit == "meter"
    stored = REAL.to_dict()
    for key in ("reference_space", "coordinate_system", "length_unit"):
        assert stored[key]
    assert "camera space" in stored["note"]


def test_a_wall_is_not_solved_for_a_floor_height() -> None:
    """A vertical plane has no height, and none is invented for it."""
    wall = FloorPlane(status=DETECTED, equation=(1.0, 0.0, 0.0, -2.0))
    assert wall.height_at(0.0, 0.0, up_axis=1) is None


def test_the_plane_round_trips_through_its_stored_form() -> None:
    again = FloorPlane.from_dict(REAL.to_dict())
    assert again.status == REAL.status
    assert again.equation == REAL.equation
    assert again.normal == REAL.normal
    assert again.point == REAL.point
    assert again.source_position == REAL.source_position
    assert again.reference_space == REAL.reference_space


def test_the_stored_form_carries_its_own_version() -> None:
    assert REAL.to_dict()["schema_version"] == FLOOR_SCHEMA_VERSION


# ------------------------------------------------------------------ FLOOR-04


def test_a_version_produced_before_floors_existed_reads_as_not_attempted() -> None:
    """An older run has no block. That is a fact about the run."""
    absent = FloorPlane.from_dict(None)
    assert absent.status == NOT_ATTEMPTED
    assert absent.is_measured is False
    assert absent.height_at(0.0, 0.0) is None


def test_a_damaged_block_never_becomes_a_floor_at_zero() -> None:
    for broken in ({}, {"status": "detected"}, {"equation": [1, 2]},
                   {"equation": "no", "normal": None}):
        plane = FloorPlane.from_dict(broken)
        assert plane.is_measured is False
        assert plane.height_at(0.0, 0.0) is None


def test_a_failed_detection_keeps_its_reason() -> None:
    failed = FloorPlane(status=NOT_FOUND, reason="konum takibi hazır değil")
    assert failed.is_measured is False
    assert "konum" in failed.to_dict()["reason"]
    # And reading it back keeps the distinction from "never tried".
    assert FloorPlane.from_dict(failed.to_dict()).status == NOT_FOUND


def test_the_three_states_are_three_different_answers() -> None:
    assert DETECTED != NOT_FOUND != NOT_ATTEMPTED
    assert FloorPlane(status=NOT_FOUND).is_measured is False
    assert FloorPlane(status=NOT_ATTEMPTED).is_measured is False
    assert REAL.is_measured is True


def test_detection_on_a_source_that_is_not_a_zed_says_so() -> None:
    """Processing a synthetic take must not fail for want of a floor."""
    class _Mock:
        pass

    plane = detect_floor(_Mock())
    assert plane.status == NOT_ATTEMPTED
    assert "ZED" in plane.reason
    assert plane.is_measured is False


def test_detection_never_raises_into_the_pipeline() -> None:
    class _Exploding:
        @property
        def _camera(self):  # noqa: ANN202
            raise RuntimeError("no camera here")

    # Reaching the attribute is what raises, and a viewing aid must never be
    # able to fail a version that is otherwise complete.
    try:
        plane = detect_floor(_Exploding())
    except RuntimeError:
        pytest.fail("detect_floor let an exception reach the pipeline")
    assert plane.is_measured is False


# -------------------------------------------------------- a moving camera


def test_a_still_camera_is_reported_as_still() -> None:
    assert camera_moved([(0.0, 0.0, 0.0), (0.001, 0.0, 0.0)]) is False


def test_a_camera_that_moved_is_reported_as_moved() -> None:
    assert camera_moved([(0.0, 0.0, 0.0), (0.5, 0.0, 0.0)]) is True


def test_no_poses_is_not_the_same_as_a_still_camera() -> None:
    """The caller stores None for unknown; this only answers what it was asked."""
    assert camera_moved([]) is False


def test_the_pipeline_writes_the_block_with_its_schema_version() -> None:
    from kinecapture.processing.jobs import (
        FLOOR_AFTER_FRAMES,
        PROCESSING_SCHEMA_VERSION,
    )

    # The block is additive, so the run schema had to move with it.
    assert PROCESSING_SCHEMA_VERSION == "1.3.0"
    # And the detection window is small: a viewing aid must not slow a run.
    assert 0 < FLOOR_AFTER_FRAMES <= 60
