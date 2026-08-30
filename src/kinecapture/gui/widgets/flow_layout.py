"""A layout that wraps its children onto a second row instead of clipping them.

Qt ships no such layout, and both dense rows in this app need one: the capture
screen's nine live metrics and the review screen's action bar. In a plain
``QHBoxLayout`` those rows set a minimum width equal to the sum of their
children, which at 1120px either clips the last controls or forces the whole
page to scroll sideways. Neither is acceptable for controls that must be
readable and reachable at every supported window size.

Wrapping is the honest answer: at a wide window everything sits on one line, and
at a narrow one the row becomes two lines and the page grows a little taller -
which it can afford, because vertical space is what a scroll area is for and
horizontal space is not.

This is the standard height-for-width flow layout: ``hasHeightForWidth`` tells
Qt the height depends on the width, and ``heightForWidth`` runs the same
placement pass as ``setGeometry`` without moving anything.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


#: How narrow a flow row assumes it may get when Qt asks for its *minimum*
#: height. Qt works that out by asking ``heightForWidth`` at the row's own
#: minimum width; left at the true minimum - one control - nine metric tiles
#: would claim nine lines and 460px of vertical minimum, and the page could
#: then never be 700px tall. This bounds the assumption to a width narrower
#: than any supported window's content area, so the reported minimum is
#: pessimistic but realistic - and, unlike measuring at resize time, right on
#: the very first layout pass rather than the one after it.
#: 760px: the content area beside the navigation rail is 834px wide in the
#: narrowest window this app supports (1120px), so this leaves ~9% of slack.
_ASSUMED_MIN_WIDTH = 760


class FlowLayout(QLayout):
    """Left-to-right placement that starts a new row when it runs out of width."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        margin: int = 0,
        spacing: int = 6,
        min_width: int = _ASSUMED_MIN_WIDTH,
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._min_width = int(min_width)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    # ``QLayout`` requires all five of these.
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    # ---------------------------------------------------------- height-for-width
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        """One row's worth of height, at the assumed narrowest useful width.

        The width reported here is the one Qt feeds back into
        ``heightForWidth`` when it works out how short the *parent* may become.
        Reporting the true minimum - one control - would have it conclude that
        nine metric tiles need nine lines, and the page could then never be
        700px tall. ``min_width`` is deliberately narrower than any supported
        window's content area, so the answer is pessimistic but not absurd.
        """
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return QSize(
            max(size.width(), self._min_width) + margins.left() + margins.right(),
            size.height() + margins.top() + margins.bottom(),
        )

    def _layout(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        row_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if row_height and next_x - spacing > effective.right() + 1:
                x = effective.x()
                y = y + row_height + spacing
                next_x = x + hint.width() + spacing
                row_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            row_height = max(row_height, hint.height())

        return y + row_height - rect.y() + margins.bottom()


class FlowContainer(QWidget):
    """The widget a :class:`FlowLayout` lives in.

    The bounded ``minimumSize`` above gets the parent's arithmetic close; these
    two make it exact at the width the row actually receives, so the last
    control on a wrapped row is never a few pixels short of its box.
    """

    def sizeHint(self) -> QSize:  # noqa: N802
        layout = self.layout()
        if layout is None:
            return super().sizeHint()
        width = self.width() or layout.minimumSize().width()
        return QSize(width, layout.heightForWidth(width))

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        layout = self.layout()
        if layout is None:
            return
        # Tracks in both directions: a row that stops needing a third line
        # when the window is widened must give that line back, or the page
        # keeps the tallest layout it has ever had.
        needed = layout.heightForWidth(self.width())
        if needed != self.minimumHeight():
            self.setMinimumHeight(needed)
            self.updateGeometry()





def flow_row(
    widgets,
    *,
    spacing: int = 6,
    assumed_min_width: int = _ASSUMED_MIN_WIDTH,
    parent: Optional[QWidget] = None,
) -> QWidget:
    """A widget holding ``widgets`` in a row that wraps rather than clips."""
    container = FlowContainer(parent)
    layout = FlowLayout(container, spacing=spacing, min_width=assumed_min_width)
    for widget in widgets:
        layout.addWidget(widget)
    container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    return container


__all__ = ["FlowContainer", "FlowLayout", "flow_row"]
