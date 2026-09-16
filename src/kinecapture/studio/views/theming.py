"""Applying a theme to a running application, completely.

Three things have to move together or the result is a half-themed window:

* the **style**, because the native Windows style paints some controls with
  the system's colours whatever the palette says;
* the **palette**, because it is what Qt falls back to for every surface the
  stylesheet does not name;
* the **stylesheet**, including the small tinted images it draws arrows and
  ticks from.

Doing only the third is what left the 15 September audit looking at a light
shell wrapped around a dark form. This module is the one place that does all
of it, so there is nowhere for a fourth source of colour to appear.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtWidgets import QApplication, QStyleFactory, QWidget

from kinecapture.studio.theme import ThemeTokens, load_tokens, stylesheet_for

from . import qssassets
from .palette import palette_for

#: The one style that honours a palette on every control. Set once; changing
#: it later would re-polish every widget for no gain.
BASE_STYLE = "Fusion"


def apply_application_theme(theme: str | ThemeTokens) -> ThemeTokens:
    """Put ``theme`` in force everywhere, including windows already open."""
    tokens = theme if isinstance(theme, ThemeTokens) else load_tokens(theme)
    application = QApplication.instance()
    if application is None:
        return tokens
    _ensure_style(application)
    # Images first: the stylesheet references them by name, and a sheet applied
    # before they exist draws nothing where an arrow should be.
    qssassets.install(tokens)
    application.setPalette(palette_for(tokens))
    application.setStyleSheet(stylesheet_for(tokens.name))
    repolish_all()
    return tokens


def _ensure_style(application) -> None:  # noqa: ANN001 - QApplication
    current = application.style()
    if current is not None and current.objectName().lower() == BASE_STYLE.lower():
        return
    style = QStyleFactory.create(BASE_STYLE)
    if style is not None:
        # setStyle replaces the palette with the style's own, so it has to
        # happen before the palette is set, never after.
        application.setStyle(style)


def repolish(widget: Optional[QWidget]) -> None:
    """Re-evaluate the stylesheet for ``widget`` and everything under it.

    Qt does this itself for the widgets it knows changed. It does not do it
    for a widget whose dynamic property drove the rule, which is most of the
    state colours in this interface.
    """
    if widget is None:
        return
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()
    for child in widget.findChildren(QWidget):
        child_style = child.style()
        if child_style is None:
            continue
        child_style.unpolish(child)
        child_style.polish(child)
        child.update()


def repolish_all(widgets: Optional[Iterable[QWidget]] = None) -> None:
    """Repolish every top-level window, so nothing keeps the old theme.

    Helper windows and dialogs are top-level in their own right: they are not
    children of the main window and would otherwise keep whatever theme they
    were built under.
    """
    application = QApplication.instance()
    if application is None:
        return
    targets = widgets if widgets is not None else application.topLevelWidgets()
    for widget in targets:
        repolish(widget)


__all__ = ["BASE_STYLE", "apply_application_theme", "repolish", "repolish_all"]
