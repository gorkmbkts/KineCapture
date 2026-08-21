"""Common scaffolding for workspace pages."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import SectionHeader


class Page(QWidget):
    """Base class for the pages behind the navigation rail.

    A page is built once and kept alive. :meth:`on_activated` is called every
    time it becomes visible, which is where a page refreshes what it shows -
    doing that work on show rather than on every data change keeps a background
    page from repainting itself for nothing.
    """

    #: Title shown in the page header and the navigation rail.
    title: str = ""
    #: One-line description under the title.
    description: str = ""
    #: Icon name from :mod:`kinecapture.gui.icons`.
    icon: str = "info"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        self._theme = state.theme

        outer = QVBoxLayout(self)
        # Tight enough that a 1366x768 screen still fits a page's controls
        # without scrolling, roomy enough not to feel cramped at 1080p.
        margin = self._theme.space_md
        outer.setContentsMargins(margin, margin, margin, self._theme.space_sm)
        outer.setSpacing(self._theme.space_sm)

        self.header = SectionHeader(self.title, self.description, theme=self._theme)
        outer.addWidget(self.header)

        self.content = QVBoxLayout()
        self.content.setSpacing(self._theme.space_md)
        outer.addLayout(self.content, 1)

    @property
    def theme(self) -> Theme:
        return self._theme

    def on_activated(self) -> None:
        """Called each time the page becomes visible."""

    def on_deactivated(self) -> None:
        """Called when the user navigates away."""

    def apply_theme(self, theme: Theme) -> None:
        """Propagate a theme change to every child that knows how to restyle."""
        self._theme = theme
        for child in self.findChildren(QWidget):
            handler = getattr(child, "apply_theme", None)
            if callable(handler) and child is not self:
                try:
                    handler(theme)
                except Exception:  # pragma: no cover - defensive
                    pass
        self.header.apply_theme(theme)

    def can_leave(self) -> bool:
        """Return False to veto navigation (unsaved work, active recording)."""
        return True


def scrollable(inner: QWidget) -> QScrollArea:
    """Wrap a widget so a dense page stays usable at 1366x768."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area.setWidget(inner)
    return area


__all__ = ["Page", "scrollable"]
