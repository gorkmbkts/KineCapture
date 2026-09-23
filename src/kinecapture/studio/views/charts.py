"""Small painted charts for the Veri Seti overview.

Deliberately painted rather than assembled from widgets. Each of these draws
a few dozen primitives from numbers the screen already has; a per-row widget
would be a hundred objects, a stylesheet pass and a layout pass to say the
same thing, and it would fight the panel's height instead of filling it.

Three rules they share.

**Every colour comes from the token set.** A class's bar is the colour the
timeline paints that class in, resolved from its position in the project's own
vocabulary - so a bar and a box on the timeline are recognisably the same
thing, and a class keeps its colour whatever order the chart happens to rank
it in.

**A number is drawn, never only a length.** A bar with no figure beside it is
a shape somebody has to measure against a neighbour. The count is printed at
the end of every row, and the row keeps room for it whatever the bar does.

**Nothing is invented.** No smoothing, no "other" bucket that hides what it
holds, no axis that starts anywhere but zero. Where there is nothing to draw
these say so in a sentence rather than showing an empty frame.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from kinecapture.studio.theme import ThemeTokens

#: One row of a bar chart: what it is, how many, and the token its bar takes.
Row = tuple[str, int, str]

#: How many bars a chart draws before it stops and counts the rest. Past this
#: the chart is a list with decoration, and the table beside it is the better
#: tool for reading a long tail.
MAX_ROWS = 9

#: How wide a chart draws, however much room it is given. A bar six hundred
#: pixels long is not more informative than one four hundred long - it only
#: puts its own figure further from it, and on a wide window it left the
#: counts against the right-hand edge of the screen with an arm's length of
#: bar between them and the name.
MAX_CHART_WIDTH = 560

#: Room reserved whatever the data does. A project with two classes and one
#: with six then produce blocks of the same shape, and a chart does not jump
#: up the column as a class is added to it.
MIN_ROWS = 4


class BarRows(QWidget):
    """A ranked horizontal bar chart: one row per class, longest first."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._rows: tuple[Row, ...] = ()
        self._hidden = 0
        self._empty = "Henüz veri yok."
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._resize()

    # ----------------------------------------------------------------- state
    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._resize()
        self.update()

    def set_empty_text(self, text: str) -> None:
        self._empty = text
        self.update()

    def set_rows(self, rows: Sequence[Row]) -> None:
        """Take the rows already ranked. Everything past :data:`MAX_ROWS` is
        counted rather than drawn, and the count says so in words."""
        rows = list(rows)
        self._hidden = max(0, len(rows) - MAX_ROWS)
        self._rows = tuple(rows[:MAX_ROWS])
        self._resize()
        self.update()

    @property
    def rows(self) -> tuple[Row, ...]:
        """What is drawn right now. For a measurement to read."""
        return self._rows

    # ------------------------------------------------------------- geometry
    def _row_height(self) -> int:
        return max(
            self._tokens.metric("KcControlHeightSmall"),
            QFontMetrics(self.font()).height() + self._tokens.metric("KcSpacingMd"),
        )

    def _resize(self) -> None:
        """Room for the rows, never less than :data:`MIN_ROWS` of them."""
        lines = max(len(self._rows), MIN_ROWS)
        extra = 1 if self._hidden else 0
        self.setFixedHeight(self._row_height() * (lines + extra))

    # -------------------------------------------------------------- painting
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt naming
        del event
        painter = QPainter(self)
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        metrics = painter.fontMetrics()
        height = self._row_height()

        if not self._rows:
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._empty,
            )
            painter.end()
            return

        # Three columns: the name, the bar, the figure. The name gets a third
        # of the width and the figure exactly the room the largest one needs,
        # so no row's bar starts or ends anywhere different from another's.
        gap = tokens.metric("KcSpacingMd")
        width = min(self.width(), MAX_CHART_WIDTH)
        largest = max(value for _label, value, _token in self._rows) or 1
        figure_width = max(
            metrics.horizontalAdvance(str(value)) for _l, value, _t in self._rows
        )
        name_width = max(90, min(int(width * 0.38), 200))
        bar_left = name_width + gap
        bar_width = max(1, width - bar_left - figure_width - gap)
        radius = tokens.metric("KcRadiusSmall") / 2.0

        for index, (text, value, token) in enumerate(self._rows):
            top = index * height
            middle = QRectF(0, top, self.width(), height)

            painter.setPen(QColor(tokens.colour("KcTextSecondary")))
            painter.drawText(
                QRectF(0, top, name_width, height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, name_width),
            )

            # The track, so a short bar still reads as a share of something.
            track = QRectF(
                bar_left, middle.center().y() - 6, bar_width, 12
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.colour("KcSurfaceControl")))
            painter.drawRoundedRect(track, radius, radius)

            filled = QRectF(track)
            filled.setWidth(max(2.0, bar_width * value / largest))
            painter.setBrush(QColor(tokens.colour(token)))
            painter.drawRoundedRect(filled, radius, radius)

            painter.setPen(QColor(tokens.colour("KcTextPrimary")))
            painter.drawText(
                QRectF(width - figure_width, top, figure_width, height),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                str(value),
            )

        if self._hidden:
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                QRectF(0, len(self._rows) * height, self.width(), height),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                f"…ve {self._hidden} sınıf daha",
            )
        painter.end()


class Proportion(QWidget):
    """One stacked bar and a legend: how a whole divides into a few parts."""

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._parts: tuple[Row, ...] = ()
        self._empty = "Henüz veri yok."
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._resize()

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self._resize()
        self.update()

    def set_parts(self, parts: Sequence[Row]) -> None:
        """Every part, including the empty ones.

        A zero keeps its place in the legend rather than disappearing: "no
        record is waiting on anything" and "nothing has been counted yet" are
        different answers and must not look alike.
        """
        self._parts = tuple(parts)
        self._resize()
        self.update()

    @property
    def parts(self) -> tuple[Row, ...]:
        return self._parts

    def _resize(self) -> None:
        line = QFontMetrics(self.font()).height()
        self.setFixedHeight(
            14 + self._tokens.metric("KcSpacingMd") + line + 2
        )

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt naming
        del event
        painter = QPainter(self)
        tokens = self._tokens
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        metrics = painter.fontMetrics()
        radius = tokens.metric("KcRadiusSmall") / 2.0
        total = sum(value for _l, value, _t in self._parts)

        width = min(self.width(), MAX_CHART_WIDTH)
        bar = QRectF(0, 0, width, 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.colour("KcSurfaceControl")))
        painter.drawRoundedRect(bar, radius, radius)

        if total:
            offset = 0.0
            for _text, value, token in self._parts:
                if not value:
                    continue
                part = width * value / total
                painter.setBrush(QColor(tokens.colour(token)))
                painter.drawRoundedRect(
                    QRectF(offset, 0, max(2.0, part), 14), radius, radius
                )
                offset += part

        top = 14 + tokens.metric("KcSpacingMd")
        if not total:
            painter.setPen(QColor(tokens.colour("KcTextMuted")))
            painter.drawText(
                QRectF(0, top, self.width(), metrics.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._empty,
            )
            painter.end()
            return

        # The legend, left to right in the bar's own order, each entry a dot
        # and its own count so nothing has to be read off the bar's length.
        x = 0.0
        gap = tokens.metric("KcSpacingLg")
        for text, value, token in self._parts:
            entry = f"{text} {value}"
            entry_width = metrics.horizontalAdvance(entry) + 14
            if x + entry_width > self.width():
                break
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.colour(token)))
            painter.drawEllipse(QRectF(x, top + metrics.height() / 2 - 4, 8, 8))
            painter.setPen(QColor(tokens.colour("KcTextSecondary")))
            painter.drawText(
                QRectF(x + 12, top, entry_width, metrics.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                entry,
            )
            x += entry_width + gap
        painter.end()


__all__ = ["MAX_CHART_WIDTH", "MAX_ROWS", "MIN_ROWS", "BarRows", "Proportion", "Row"]
