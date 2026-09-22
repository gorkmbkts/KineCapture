"""Where the labelling screen's three regions go. Arithmetic only, no Qt.

The top band holds three things that have to agree with each other:

* the **RGB view**, which must keep the recording's own aspect ratio - read
  from the version's metadata, never assumed to be 16:9;
* the **3-D view**, which is square, because an orbit around a person is not a
  wider-than-tall thing and a stretched viewport makes a lean look like a
  camera angle;
* the **editing panel**, which has a width below which it stops being usable
  and must not be squeezed past it.

Given the band's height ``H`` and the source ratio ``r``, the first two are
``rH`` and ``H`` wide. So the band's height is what everything else falls out
of, and the solver's job is to choose the largest ``H`` that still leaves the
panel its minimum and the timeline its own.

Two rules the 19 September review stated and this file keeps:

**The picture is never stretched or cropped.** If the geometry cannot be
satisfied, the *height* comes down. Distorting a recording to fill a rectangle
would make every judgement about lean and depth wrong.

**Room that is freed does not all go to the video.** The panel is asked for a
comfortable width *first*, and gives width back only when that would push the
band under its floor. A wider window should make the labelling easier to do,
not only the recording easier to watch.

**Height the stage cannot use is given to the editor, not to a margin.** The
stage is usually decided by *width*: at 1852x830 with a 16:9 source the widths
allow a 499 px band while the height would have allowed 634, and the 135 px
difference used to collect below the timeline as empty space. That was a
deliberate choice and the wrong one - the 20 September review rejected it.
The surplus now sizes the contextual editor underneath, which is where the
movement and fault forms live, so a taller window buys a roomier editor
instead of a wider blank strip.

A window wider than the tallest band its height allows leaves ``spare_width``,
and the caller centres the band in it rather than stretching anything to fill
it.

Nothing here is tied to a resolution. 1850x760 with a 16:9 source comes out at
884/497/465, which is the arithmetic arriving at the brief's illustrative
890/500/460 rather than a constant matching it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: How wide the panel is asked for, as a multiple of its readable minimum.
#: Above this it is a column of short lines in a wide empty box, so the width
#: is better spent on the picture; below it the editors start wrapping.
PANEL_COMFORTABLE = 1.55


@dataclass(frozen=True)
class StageGeometry:
    """One solved top band."""

    #: Height shared by all three regions. They are top- and bottom-aligned.
    height: int
    video_width: int
    skeleton_width: int
    panel_width: int
    #: Width the band could not use: the window is wider than the tallest band
    #: it is allowed to show. The caller centres the band in it rather than
    #: stretching anything to fill it.
    spare_width: int = 0
    #: True when width, not height, decided the band. The picture is as large
    #: as this window allows.
    constrained: bool = False
    #: Height for the contextual editor between the stage and the toolbar.
    #: This is the room the stage could not use; it is never negative and
    #: never more than the editor asked for.
    editor_height: int = 0
    #: Height left over after every band has had what it asked for. Small by
    #: construction; a window that leaves a lot of this has a stage that is
    #: height-bound, which is the one case where nothing else can use it.
    slack_height: int = 0

    @property
    def total_width(self) -> int:
        return self.video_width + self.skeleton_width + self.panel_width

    def aspect_of_video(self) -> float:
        return self.video_width / self.height if self.height else 0.0


def solve_stage(
    *,
    available_width: int,
    available_height: int,
    source_ratio: float,
    panel_min_width: int,
    timeline_min_height: int,
    toolbar_height: int,
    stage_min_height: int,
    divider_width: int = 1,
    editor_min_height: int = 0,
    editor_max_height: int = 0,
    band_spacing: int = 0,
) -> StageGeometry:
    """Lay out the top band inside what the page actually has.

    ``source_ratio`` is width / height of the recording, from its metadata.
    A ratio that is missing or nonsensical falls back to 16:9 - and that
    fallback is the *only* place that number appears, so a caller can tell a
    known ratio from a guessed one by whether it passed one in.
    """
    ratio = float(source_ratio)
    if not ratio or ratio <= 0 or ratio != ratio:  # NaN-safe
        ratio = 16.0 / 9.0

    dividers = max(0, int(divider_width)) * 2
    width = max(0, int(available_width) - dividers)
    panel_min = max(0, int(panel_min_width))
    comfortable = max(panel_min, int(panel_min * PANEL_COMFORTABLE))

    editor_min = max(0, int(editor_min_height))
    editor_max = max(editor_min, int(editor_max_height))
    # The gaps between the four bands are height the page spends and cannot
    # give to anything. Left out, the solver hands back a set of heights that
    # sums to exactly the available space and the layout then has to overlap
    # them - which is what it did: the stage sat 8 px over the editor on a
    # 1900x970 window and 77 px over it at the minimum size.
    gaps = max(0, int(band_spacing)) * 3
    usable_height = max(0, int(available_height) - gaps)

    # The height the bands below will not give up. The editor's *minimum* is
    # part of that floor - it is a working surface, not a leftover - while
    # anything above the minimum comes out of what the stage does not use.
    ceiling = (
        usable_height
        - int(timeline_min_height)
        - int(toolbar_height)
        - editor_min
    )
    # The preferred stage floor cannot override the physical height budget.
    # A maximised 1080p desktop at 150% has only 533 logical pixels here;
    # forcing a 260px stage made the fixed bands overlap by 83px. Keep the
    # editor and timeline usable and shrink the proportional viewports.
    ceiling = max(0, ceiling)

    def band_height(panel: int) -> float:
        """How tall the viewports may be beside a panel of this width."""
        return max(0.0, width - panel) / (ratio + 1.0)

    # The panel is asked for its comfortable width first. This is the rule
    # that stops every pixel a wider window brings going to the picture: the
    # panel is where the labelling is done, and a wider window should make it
    # easier to do, not only easier to watch.
    panel = comfortable
    height = min(float(ceiling), band_height(panel))

    # ...but the panel gives width back if that left the band below its floor.
    # It gives back only as much as the band needs, and never goes under its
    # own readable minimum.
    if height < stage_min_height and panel > panel_min:
        wanted = width - float(stage_min_height) * (ratio + 1.0)
        panel = int(max(panel_min, min(panel, wanted)))
        height = min(float(ceiling), band_height(panel))

    height = int(height)
    if height <= 0:
        # Nothing fits. Give back a degenerate but consistent answer rather
        # than negative widths; the caller shows its minimum-size state.
        return StageGeometry(
            0, 0, 0, max(panel_min, width), constrained=True,
            editor_height=editor_min,
        )

    video = int(round(height * ratio))
    skeleton = height
    used = video + skeleton + panel

    # What is left once every band has had its floor. This is the height that
    # used to become an empty strip under the timeline.
    remaining = (
        usable_height
        - height
        - int(timeline_min_height)
        - int(toolbar_height)
    )
    editor = max(editor_min, min(editor_max, remaining))
    slack = max(0, remaining - editor)
    # Room the band could not use: the window is wider than the tallest band
    # the height allows, plus whatever a whole number of pixels leaves over.
    # Nothing is stretched into it - the caller centres the band instead.
    spare = max(0, width - used)
    return StageGeometry(
        height=height,
        video_width=video,
        skeleton_width=skeleton,
        panel_width=panel,
        spare_width=spare,
        # Width decided the band when the height it allows is at or under the
        # ceiling. Asked of the arithmetic rather than inferred from the
        # leftover, which is a pixel or two of rounding on most windows.
        constrained=band_height(panel) <= ceiling,
        editor_height=editor,
        slack_height=slack,
    )


def source_ratio_from(size: object) -> float:
    """``width / height`` from a recorded resolution, or ``0.0`` if unknown.

    Zero means *nothing said*, and the caller is expected to treat that as the
    one case where a fallback is used - not to quietly pass 16:9 along as if
    the recording had declared it.
    """
    try:
        width, height = size  # type: ignore[misc]
        width, height = float(width), float(height)
    except (TypeError, ValueError):
        return 0.0
    if width <= 0 or height <= 0:
        return 0.0
    return width / height


__all__ = [
    "PANEL_COMFORTABLE",
    "StageGeometry",
    "solve_stage",
    "source_ratio_from",
]
