"""The labelling screen's top band, solved as arithmetic.

No Qt here on purpose. The two facts that decide the widths - the recording's
own aspect ratio and the panel's readable minimum - are numbers, and a test
that had to open a window to check them would be slower and would measure the
platform as much as the rule.
"""

from __future__ import annotations

import math

import pytest

from kinecapture.studio.services.stage_layout import (
    StageGeometry,
    solve_stage,
    source_ratio_from,
)

#: A representative call. Individual tests override what they are about.
BASE = dict(
    available_width=1850,
    available_height=760,
    source_ratio=16 / 9,
    panel_min_width=300,
    timeline_min_height=148,
    toolbar_height=44,
    stage_min_height=260,
    divider_width=1,
)


def solve(**overrides) -> StageGeometry:  # noqa: ANN003
    return solve_stage(**{**BASE, **overrides})


# ----------------------------------------------------------------- LAYOUT-02


def test_the_three_regions_account_for_every_pixel() -> None:
    """Nothing is stretched to fill a remainder; it is reported instead."""
    geometry = solve()
    dividers = 2
    assert (
        geometry.total_width + geometry.spare_width
        == BASE["available_width"] - dividers
    )
    # And what is left over is a rounding remainder, not a gap.
    assert geometry.spare_width <= 3


def test_the_skeleton_viewport_is_square() -> None:
    """An orbit around a person is not a wider-than-tall thing."""
    for ratio in (16 / 9, 4 / 3, 1.0, 9 / 16, 2.39):
        geometry = solve(source_ratio=ratio)
        assert geometry.skeleton_width == geometry.height, ratio


@pytest.mark.parametrize("ratio", [16 / 9, 4 / 3, 1.0, 9 / 16, 2.39, 1.85])
def test_the_picture_keeps_the_source_ratio(ratio: float) -> None:
    """Never stretched, never cropped - whatever shape the camera recorded."""
    geometry = solve(source_ratio=ratio)
    assert geometry.height > 0
    assert geometry.aspect_of_video() == pytest.approx(ratio, rel=0.02)


def test_a_portrait_source_is_not_forced_landscape() -> None:
    geometry = solve(source_ratio=9 / 16)
    assert geometry.video_width < geometry.height


def test_nothing_assumes_sixteen_by_nine_unless_asked_to() -> None:
    """The fallback exists, and it is the only place that number appears."""
    declared = solve(source_ratio=4 / 3)
    assert declared.aspect_of_video() == pytest.approx(4 / 3, rel=0.02)
    # An undeclared ratio falls back, and says so by matching the fallback.
    for missing in (0.0, -1.0, float("nan")):
        fallback = solve(source_ratio=missing)
        assert fallback.aspect_of_video() == pytest.approx(16 / 9, rel=0.02)


def test_the_panel_never_goes_below_its_minimum() -> None:
    for width in (1850, 1600, 1366, 1120, 900):
        geometry = solve(available_width=width)
        assert geometry.panel_width >= BASE["panel_min_width"], width


def test_the_timeline_keeps_its_own_height() -> None:
    for height in (760, 620, 520, 430):
        geometry = solve(available_height=height)
        left = height - geometry.height - BASE["toolbar_height"]
        # Either the timeline has its minimum, or the band is already at its
        # own floor and the page is simply too short - never the timeline
        # squeezed to nothing so the picture can be bigger.
        assert (
            left >= BASE["timeline_min_height"]
            or geometry.height <= BASE["stage_min_height"]
        ), height


def test_scaled_fullscreen_bands_fit_without_overlap() -> None:
    geometry = solve(
        available_width=1232, available_height=533,
        timeline_min_height=202, toolbar_height=62,
        editor_min_height=113, editor_max_height=220, band_spacing=4,
    )
    assert geometry.height > 0
    assert geometry.editor_height >= 113
    assert geometry.height + geometry.editor_height + 202 + 62 + 3 * 4 <= 533
    assert geometry.aspect_of_video() == pytest.approx(16 / 9, rel=.01)


def test_the_band_grows_with_the_window() -> None:
    small = solve(available_width=1366, available_height=620)
    large = solve(available_width=2560, available_height=1300)
    assert large.height > small.height
    assert large.video_width > small.video_width


def test_freed_room_is_not_all_poured_into_the_picture() -> None:
    """The panel is where the work is done, and it is served first.

    At the narrowest supported window the panel has already given width back
    to keep the band above its floor; a step wider and it is at the width it
    actually wants. That is the rule: a wider window makes the labelling
    easier to do, not only the recording easier to watch.
    """
    tightest = solve(available_width=1120)
    roomier = solve(available_width=1366)
    assert roomier.panel_width > tightest.panel_width
    assert tightest.panel_width >= BASE["panel_min_width"]


def test_the_panel_stops_growing_once_it_is_comfortable() -> None:
    """Beyond this it is a column of short lines in a wide empty box."""
    huge = solve(available_width=4000)
    assert huge.panel_width <= int(BASE["panel_min_width"] * 2)
    # The width it could not use is reported rather than absorbed, so the
    # caller can centre the band instead of stretching something into it.
    assert huge.spare_width > 0
    assert huge.total_width + huge.spare_width == 4000 - 2


def test_a_window_too_small_to_satisfy_anything_answers_consistently() -> None:
    geometry = solve(available_width=320, available_height=200)
    assert geometry.video_width >= 0
    assert geometry.skeleton_width >= 0
    assert geometry.panel_width >= 0
    assert geometry.height >= 0


def test_the_geometry_is_not_tied_to_one_resolution() -> None:
    """The example in the brief is arithmetic, not a constant.

    1850 wide with a 16:9 source comes out near 890/500/460 - checked here as
    a sanity anchor, with room, rather than as a number to match exactly.
    """
    geometry = solve(available_width=1850, available_height=760)
    assert 840 <= geometry.video_width <= 940
    assert 470 <= geometry.skeleton_width <= 530
    assert 430 <= geometry.panel_width <= 500
    assert geometry.skeleton_width == geometry.height


def test_a_taller_window_is_limited_by_width_not_by_height() -> None:
    geometry = solve(available_width=1200, available_height=2000)
    assert geometry.constrained is True
    assert geometry.spare_width <= 3
    assert geometry.panel_width >= BASE["panel_min_width"]


# ------------------------------------------------------------- ratio reading


def test_a_recorded_resolution_becomes_a_ratio() -> None:
    assert source_ratio_from((1280, 720)) == pytest.approx(16 / 9)
    assert source_ratio_from([640, 480]) == pytest.approx(4 / 3)


def test_an_unrecorded_resolution_is_zero_not_a_guess() -> None:
    """Zero means *nothing said*, which is a different fact from 16:9."""
    for missing in (None, (), (0, 720), (1280, 0), "1280x720", (1280,)):
        assert source_ratio_from(missing) == 0.0


def test_the_solver_never_returns_a_nan_height() -> None:
    geometry = solve(source_ratio=float("nan"))
    assert not math.isnan(geometry.height)
    assert geometry.height > 0
