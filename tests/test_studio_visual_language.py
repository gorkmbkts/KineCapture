"""The shared visual language: tokens, icons and what the context bar says.

These are the guarantees the 19 September refinement rests on. Everything
below it - the capture row, the labelling bands, the 3-D colours - reads its
sizes and its meanings from here, so a regression in this file is a regression
everywhere at once.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from kinecapture.studio.services.context import (  # noqa: E402
    ContextItem,
    ContextState,
)
from kinecapture.studio.theme import load_tokens, theme_names  # noqa: E402
from kinecapture.studio.views import iconset  # noqa: E402
from kinecapture.studio.views.widgets import ContextField  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------- UI-01

#: Every size the refinement introduced. A missing one is a widget that went
#: back to writing its own number.
REQUIRED_METRICS = (
    "KcControlHeightSmall",
    "KcIconButtonSize",
    "KcIconStripWidth",
    "KcLabelPanelMinWidth",
    "KcTimelineMinHeight",
    "KcStageMinHeight",
    "KcCrestSizeAuth",
    "KcAuthFieldWidth",
    "KcIntervalFillAlpha",
    "KcIntervalFillAlphaSelected",
    "KcIntervalFillAlphaDimmed",
    "KcIntervalEdgeAlpha",
    "KcJointNodeSize",
    "KcJointNodeSelectedSize",
    "KcBoneWidth",
    "KcCameraTransitionMs",
)


@pytest.mark.parametrize("token", REQUIRED_METRICS)
def test_every_shared_measure_is_a_token(token: str) -> None:
    assert load_tokens("dark").metric(token) > 0


def test_the_control_heights_are_a_ladder_not_three_unrelated_numbers() -> None:
    tokens = load_tokens("dark")
    small = tokens.metric("KcControlHeightSmall")
    normal = tokens.metric("KcControlHeight")
    large = tokens.metric("KcControlHeightLarge")
    assert small < normal < large


def test_an_icon_button_is_square_and_fits_its_icon() -> None:
    tokens = load_tokens("dark")
    side = tokens.metric("KcIconButtonSize")
    assert side >= tokens.metric("KcIconSize") + tokens.metric("KcSpacingMd")
    assert tokens.metric("KcIconStripWidth") >= side


def test_interval_fills_are_translucent_and_ordered() -> None:
    """A block of solid colour is what the design review asked to remove."""
    tokens = load_tokens("dark")
    dimmed = tokens.metric("KcIntervalFillAlphaDimmed")
    normal = tokens.metric("KcIntervalFillAlpha")
    selected = tokens.metric("KcIntervalFillAlphaSelected")
    assert dimmed < normal < selected
    # Well under half opaque: the ruler, the grid and the label underneath all
    # have to stay readable through the fill.
    assert selected < 128
    # The edge is what a light fill leans on, so it is nearly opaque.
    assert tokens.metric("KcIntervalEdgeAlpha") > 200


# --------------------------------------------------------------------- UI-02


@pytest.mark.parametrize("theme", theme_names())
def test_the_anatomical_palette_exists_in_both_themes(theme: str) -> None:
    tokens = load_tokens(theme)
    for token in (
        "KcAnatomyRightArm",
        "KcAnatomyRightLeg",
        "KcAnatomyLeftArm",
        "KcAnatomyLeftLeg",
        "KcAnatomyTorso",
        "KcAnatomyUnknown",
    ):
        assert tokens.colour(token).startswith("#")


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _distance(first: str, second: str) -> float:
    a, b = _rgb(first), _rgb(second)
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


@pytest.mark.parametrize("theme", theme_names())
def test_the_four_limbs_are_told_apart_by_colour(theme: str) -> None:
    """Right arm, right leg, left arm and left leg are four answers."""
    tokens = load_tokens(theme)
    limbs = (
        "KcAnatomyRightArm",
        "KcAnatomyRightLeg",
        "KcAnatomyLeftArm",
        "KcAnatomyLeftLeg",
    )
    for index, first in enumerate(limbs):
        for second in limbs[index + 1 :]:
            found = _distance(tokens.colour(first), tokens.colour(second))
            assert found >= 60.0, f"{theme}: {first} vs {second} = {found:.0f}"


@pytest.mark.parametrize("theme", theme_names())
def test_the_torso_is_neutral_rather_than_a_fifth_hue(theme: str) -> None:
    tokens = load_tokens(theme)
    red, green, blue = _rgb(tokens.colour("KcAnatomyTorso"))
    assert max(red, green, blue) - min(red, green, blue) <= 30


@pytest.mark.parametrize("theme", theme_names())
def test_the_three_panel_contexts_are_distinguishable(theme: str) -> None:
    tokens = load_tokens(theme)
    summary = tokens.colour("KcContextSummary")
    movement = tokens.colour("KcContextMovement")
    fault = tokens.colour("KcContextFault")
    assert _distance(movement, fault) >= 60.0
    assert _distance(movement, summary) >= 40.0
    assert _distance(fault, summary) >= 40.0


# --------------------------------------------------------------------- UI-03

#: Icons the refinement's screens ask for by name. A missing file raises, so
#: this is the cheapest possible guard against a button with no picture.
REQUIRED_ICONS = (
    "record-start",
    "record-stop",
    "marker",
    "connect",
    "disconnect",
    "navigate",
    "draw-movement",
    "draw-fault",
    "snap",
    "zoom-in",
    "zoom-out",
    "zoom-all",
    "undo",
    "redo",
    "save",
    "saved",
    "loop",
    "speed",
    "more",
    "camera-tools",
    "labels",
    "people",
    "summary",
    "compass",
    "centre",
    "fit",
    "floor",
    "overlay-on",
    "overlay-off",
    "save-view",
    "previous-view",
    "joints",
    "add",
    "delete",
    "edit",
    "back",
    "next",
    "filter",
    "layers",
    "busy",
    "clock",
    "collapse",
)


@pytest.mark.parametrize("name", REQUIRED_ICONS)
def test_every_named_icon_renders(app: QApplication, name: str) -> None:
    pixmap = iconset.pixmap(name, "#ffffff", 16, 1.0)
    assert not pixmap.isNull()
    assert pixmap.width() == 16


def test_the_destination_icon_for_capture_is_still_the_camera() -> None:
    """The action icons added beside it must not shadow the nav entry."""
    assert iconset.ICON_NAMES["record"] == "video"
    assert iconset.ICON_NAMES["record-start"] == "circle"


def test_no_icon_key_points_at_a_missing_file(app: QApplication) -> None:
    missing = []
    for key in iconset.available():
        try:
            iconset.pixmap(key, "#ffffff", 16, 1.0)
        except iconset.IconError:
            missing.append(key)
    assert not missing, missing


# --------------------------------------------------------------------- UI-04


def test_a_context_field_that_is_fine_draws_no_tick(app: QApplication) -> None:
    """The decorative green ticks beside user/project/folder/disk are gone."""
    tokens = load_tokens("dark")
    field = ContextField(tokens)
    field.update_item(
        ContextItem("data", "Veri klasörü", "datasets", ContextState.OK)
    )
    assert field._icon.isHidden()
    assert field._icon.pixmap().isNull()


@pytest.mark.parametrize(
    "state", [ContextState.WARNING, ContextState.ERROR, ContextState.UNKNOWN]
)
def test_a_context_field_worth_reading_still_draws_its_mark(
    app: QApplication, state: ContextState
) -> None:
    tokens = load_tokens("dark")
    field = ContextField(tokens)
    field.update_item(ContextItem("disk", "Disk", "12 GB", state))
    assert not field._icon.isHidden()
    assert not field._icon.pixmap().isNull()


def test_the_state_is_still_spoken_even_when_nothing_is_drawn(
    app: QApplication,
) -> None:
    """Removing the tick must not remove the state from a screen reader."""
    tokens = load_tokens("dark")
    field = ContextField(tokens)
    field.update_item(ContextItem("data", "Veri klasörü", "datasets", ContextState.OK))
    assert "tamam" in field.accessibleName()
