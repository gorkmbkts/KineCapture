"""Destination pages.

``build_page`` is the single registry the shell asks, so delivering a screen in
a later phase is a one-line change here. Anything not yet built is a
:class:`PlaceholderPage` that names the phase which will build it - shown in
its real place in the workflow rather than hidden.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination

from .base import PlaceholderPage, StudioPage
from .capture import CapturePage
from .library import LibraryPage
from .processing import ProcessingPage
from .projects import ProjectsPage
from .settings import SettingsPage

#: destination key -> page class. Missing keys fall back to the placeholder.
PAGE_TYPES: dict[str, type[StudioPage]] = {
    "projects": ProjectsPage,
    "capture": CapturePage,
    "library": LibraryPage,
    "processing": ProcessingPage,
    "settings": SettingsPage,
}


def build_page(
    destination: Destination, tokens: ThemeTokens, parent: Optional[QWidget] = None
) -> StudioPage:
    factory = PAGE_TYPES.get(destination.key, PlaceholderPage)
    return factory(destination, tokens, parent)


__all__ = [
    "PAGE_TYPES",
    "CapturePage",
    "LibraryPage",
    "PlaceholderPage",
    "ProcessingPage",
    "ProjectsPage",
    "SettingsPage",
    "StudioPage",
    "build_page",
]
