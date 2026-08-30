"""A modeless side window for reference information.

Both the capture and the review screen used to keep a permanent column of
read-only panels - pre-flight checks, plan, take metadata, archive status - next
to the thing the user was actually looking at. The panels were right, and they
were in the way: they are consulted at the start of a session and then perhaps
twice more, while the camera views and the timeline they were crowding are
looked at continuously.

So they moved here. The window is:

* **Modeless** - recording and playback carry on while it is open, and it can
  stay open on a second monitor for a whole session.
* **Single instance per page** - the button raises the existing window instead
  of stacking copies, which is the usual failure of "open in a window" buttons.
* **Never where a critical alert goes.** Anything the user must react to now
  stays on the main screen; this window is for what they may want to check.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kinecapture.gui.theme import Theme


class InfoWindow(QDialog):
    """A scrollable stack of cards, shown beside the screen that owns it."""

    def __init__(
        self,
        title: str,
        theme: Theme,
        parent: Optional[QWidget] = None,
    ) -> None:
        # Qt.Tool keeps it above its owner without becoming a second entry in
        # the task bar; the owner is a page, so it follows the main window.
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle(title)
        self.setModal(False)
        # Wide enough for a two-column detail list without either column
        # having to be clipped or scrolled sideways.
        self.setMinimumWidth(420)
        self.resize(520, 680)
        self._theme = theme

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        outer.addWidget(self._scroll)

        self._body = QWidget()
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(
            theme.space_md, theme.space_md, theme.space_md, theme.space_md
        )
        self._layout.setSpacing(theme.space_md)
        self._layout.addStretch(1)
        self._scroll.setWidget(self._body)

    def add_card(self, card: QWidget) -> QWidget:
        """Append a card above the trailing stretch."""
        self._layout.insertWidget(self._layout.count() - 1, card)
        return card

    def present(self) -> None:
        """Show, or raise if it is already open behind something."""
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle(self) -> None:
        if self.isVisible():
            self.close()
        else:
            self.present()

    def closeEvent(self, event: QCloseEvent) -> None:
        # Hidden rather than destroyed: the cards inside are live widgets the
        # owning page keeps updating, and rebuilding them on every open would
        # lose their state.
        event.accept()


__all__ = ["InfoWindow"]
