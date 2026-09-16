"""The thin strip across the top: where am I working, is this machine ready.

Refreshed on a timer at 3 Hz, not per frame - a readout that updates faster
than it can be read costs paint time and gives nothing back. The underlying
:class:`Observable` only notifies on real change, so a steady bar repaints
nothing at all.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from kinecapture.studio.services.context import ContextSnapshot
from kinecapture.studio.theme import ThemeTokens

from . import iconset
from .brand import CREST_NAME, crest_pixmap
from .widgets import ContextField, RecordingStrip, separator


class ContextBar(QFrame):
    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("kcContextBar")
        self._tokens = tokens
        self._fields: dict[str, ContextField] = {}

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(
            tokens.metric("KcSpacingLg"),
            tokens.metric("KcSpacingXs"),
            tokens.metric("KcSpacingMd"),
            tokens.metric("KcSpacingXs"),
        )
        self._layout.setSpacing(tokens.metric("KcSpacingLg"))

        # A small crest at the head of the bar: present on every screen, never
        # competing with the work. The fields are inserted after it.
        self.crest = QLabel(self)
        self.crest.setAccessibleName(CREST_NAME)
        self.crest.setToolTip(CREST_NAME)
        self._layout.addWidget(self.crest)
        self._layout.addWidget(separator(Qt.Orientation.Vertical))
        self._leading = 2

        self._layout.addStretch(1)

        # A continuous state, so it lives in a region whose size never changes
        # rather than in a message that appears and pushes things about.
        self.recording = RecordingStrip(tokens, self)
        self._layout.addWidget(self.recording)

        self.theme_button = QPushButton()
        self.theme_button.setProperty("kcVariant", "quiet")
        self.theme_button.setToolTip("Temayı değiştir")
        self.theme_button.setAccessibleName("Temayı değiştir")
        self.inspector_button = QPushButton()
        self.inspector_button.setProperty("kcVariant", "quiet")
        self.inspector_button.setCheckable(True)
        self.inspector_button.setToolTip("İnceleme panelini aç/kapat  (F9)")
        self.inspector_button.setAccessibleName("İnceleme paneli")
        self._layout.addWidget(self.theme_button)
        self._layout.addWidget(self.inspector_button)

        self.setFixedHeight(tokens.metric("KcContextBarHeight"))
        self.apply_tokens(tokens)

    def apply_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.setFixedHeight(tokens.metric("KcContextBarHeight"))
        for field in self._fields.values():
            field.set_tokens(tokens)
        self.recording.set_tokens(tokens)
        self._show_crest()
        ratio = self.devicePixelRatioF()
        size = tokens.metric("KcIconSize")
        self.theme_button.setIcon(
            iconset.icon(
                "theme-light" if tokens.is_dark else "theme-dark",
                tokens,
                size=size,
                ratio=ratio,
            )
        )
        self.inspector_button.setIcon(
            iconset.icon("inspector", tokens, size=size, ratio=ratio)
        )

    def _show_crest(self) -> None:
        size = self._tokens.metric("KcContextBarHeight") - self._tokens.metric(
            "KcSpacingMd"
        )
        pixmap = crest_pixmap(
            self._tokens, size=size, ratio=self.devicePixelRatioF()
        )
        if pixmap is None:
            self.crest.hide()
            return
        self.crest.setPixmap(pixmap)
        self.crest.setFixedSize(pixmap.size() / pixmap.devicePixelRatio())
        self.crest.show()

    def update_context(self, snapshot: ContextSnapshot) -> None:
        """Add fields the first time they appear, then only update values.

        Rebuilding the row on every tick would churn widgets three times a
        second for a bar that usually says exactly what it said before.
        """
        for index, item in enumerate(snapshot.items):
            field = self._fields.get(item.key)
            if field is None:
                field = ContextField(self._tokens, self)
                self._fields[item.key] = field
                position = self._leading + index * 2
                self._layout.insertWidget(position, field)
                if index < len(snapshot.items) - 1:
                    self._layout.insertWidget(
                        position + 1, separator(Qt.Orientation.Vertical)
                    )
            field.update_item(item)

    def field(self, key: str) -> Optional[ContextField]:
        return self._fields.get(key)


__all__ = ["ContextBar"]
