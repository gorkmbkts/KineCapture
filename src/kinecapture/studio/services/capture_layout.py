"""How the Yakalama screen divides its width. No Qt.

The picture is the point of the screen, and a camera image has an aspect ratio
the application does not get to choose. Letting the image widget take all the
room and letterbox itself inside it produced two black bars that were doing
nothing: on a 1920-wide window with a 16:9 source and a 900-pixel stage, about
three hundred horizontal pixels of the widget were background.

So the width the picture can actually use is computed from its own ratio and
the height available, and what is left over goes to the console beside it -
up to a readable limit, because a settings column three hundred pixels wider
than its content is not more readable, it is just wider.

Nothing here scales, crops or stretches the image. The picture keeps its exact
ratio; what changes is how much of the window is offered to it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Below this the console stops being readable: two-line labels start wrapping
#: into four and the mode buttons collide.
CONSOLE_MIN_WIDTH = 300

#: Above this the console is only wider, not clearer. Measured against the
#: longest label it carries ("Kaydedilecek kişiyi görüntüde üzerine tıklayarak
#: seçin.") at 150% scaling, which wraps to two lines well before this.
CONSOLE_MAX_WIDTH = 460

#: A source whose ratio is unknown - no frame yet - is laid out as 16:9 rather
#: than as a square, because every camera this application supports is wider
#: than it is tall and a square would move the split on the first frame.
DEFAULT_SOURCE_RATIO = 16 / 9


def console_columns_for(
    *, available_height: int, height_in_one_column: int
) -> int:
    """One column, or two.

    Two exactly when the blocks do not fit the height they are given. A second
    column is how this screen answers being short of height, because the two
    alternatives are both worse: a scrollbar hides controls the operator needs
    while a recording is running, and a ``QVBoxLayout`` given less than its
    minimum does not clip - it overlaps, which on 19 September printed "Süre
    sonunda dur" through "Önizlemeyi aynala".

    The width is not consulted. On a window too narrow for two readable
    columns *and* a picture, something has to give, and it is the picture: a
    small picture is still a picture, while a control drawn on top of another
    control is neither of them. Such a window is below the size this
    application is meant to run at in any case - it is always maximised, and
    the smallest screen it supports leaves room for both.
    """
    return 1 if height_in_one_column <= max(0, int(available_height)) else 2


@dataclass(frozen=True)
class CaptureStage:
    """Widths for one layout pass, in logical pixels."""

    preview_width: int
    console_width: int
    #: How many columns the console was laid out in for this split.
    console_columns: int
    #: Horizontal pixels neither pane took. Zero in every normal case; this
    #: exists so a test can say so rather than assume it.
    slack: int

    @property
    def total(self) -> int:
        return self.preview_width + self.console_width


def solve_capture_stage(
    *,
    available_width: int,
    stage_height: int,
    source_ratio: float = DEFAULT_SOURCE_RATIO,
    spacing: int = 0,
    console_min: int = CONSOLE_MIN_WIDTH,
    console_max: int = CONSOLE_MAX_WIDTH,
    console_columns: int = 1,
) -> CaptureStage:
    """Split ``available_width`` between the picture and the console.

    The picture asks for exactly the width its ratio needs at ``stage_height``
    and never more: wider than that and it would letterbox again, this time
    with the bars inside a widget that had claimed the room. The console takes
    what is left, clamped to something readable. When the window is too narrow
    for both, the console keeps its minimum and the picture shrinks - the
    picture is elastic, the controls are not.
    """
    width = max(0, int(available_width) - max(0, int(spacing)))
    height = max(0, int(stage_height))
    ratio = float(source_ratio) if source_ratio and source_ratio > 0 else DEFAULT_SOURCE_RATIO
    columns = max(1, int(console_columns))
    # A second column is how the console answers being too tall for the
    # window. It is not a scrollbar and not a smaller font: the same controls,
    # side by side, each still at a readable width.
    console_min = max(0, int(console_min)) * columns + spacing * (columns - 1)
    console_max = max(console_min, int(console_max) * columns + spacing * (columns - 1))

    if width <= 0 or height <= 0:
        return CaptureStage(0, min(console_max, max(console_min, width)), columns, 0)

    wanted = int(round(height * ratio))
    console = width - wanted
    if console < console_min:
        # Not enough width for the picture's full ratio plus a usable console.
        console = min(console_min, width)
        preview = max(0, width - console)
    elif console > console_max:
        console = console_max
        preview = width - console
        # The picture now has more width than its ratio can use. Give it only
        # what it needs; the rest is slack, which the caller centres.
        preview = min(preview, wanted)
    else:
        preview = wanted
    slack = max(0, width - preview - console)
    return CaptureStage(int(preview), int(console), columns, int(slack))


__all__ = [
    "CONSOLE_MAX_WIDTH",
    "CONSOLE_MIN_WIDTH",
    "console_columns_for",
    "DEFAULT_SOURCE_RATIO",
    "CaptureStage",
    "solve_capture_stage",
]
