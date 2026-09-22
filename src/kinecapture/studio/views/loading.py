"""One preparation surface, shown in place of the work it is preparing.

Not a dialog and not a spinner in a corner. While a version is opening, the
labelling screen shows *this* where the editor will be, and the editor appears
whole when it is ready. The 19 September brief is explicit about why: an editor
that appears with an empty video, then an empty timeline, then a skeleton, is
four screens in a row and none of them is the one the annotator asked for.

Three rules the design review fixed, and the reason for each.

**A percentage only where something measured one.** The load's expensive stage
- re-hashing every derived file - counts bytes, so it has an honest fraction.
The others are steps. A stage with no fraction gets an indeterminate bar and
its own sentence, never a number invented to fill the space.

**No estimate before there is a rate.** An estimate quoted from the first half
second of a seven-second hash is wrong by a factor of several, and the way a
reader finds that out is by watching it sit at 100%.

**Cancel is real.** It stops the work at the next file boundary, and whatever
the worker produces afterwards is discarded rather than shown.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens

from .widgets import label, mono_label


class LoadingSurface(QWidget):
    """What the screen shows while a version is being opened."""

    #: The user asked to stop. The page stops the work and goes back.
    cancelled = Signal()
    #: The user asked to try the same version again, after a failure.
    retried = Signal()

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName("kcLoadingSurface")

        outer = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingXxl")
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(tokens.metric("KcSpacingMd"))
        outer.addStretch(1)

        self.headline = label("", role="section")
        self.headline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.headline)

        self.stage = label("", role="pageSubtitle")
        self.stage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage.setWordWrap(True)
        outer.addWidget(self.stage)

        bar_row = QHBoxLayout()
        bar_row.addStretch(1)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(tokens.metric("KcAuthFieldWidth"))
        bar_row.addWidget(self.bar)
        bar_row.addStretch(1)
        outer.addLayout(bar_row)

        self.detail = mono_label("")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.detail)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Vazgeç")
        self.cancel_button.setProperty("kcVariant", "quiet")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        buttons.addWidget(self.cancel_button)
        self.retry_button = QPushButton("Yeniden dene")
        self.retry_button.clicked.connect(self.retried.emit)
        self.retry_button.hide()
        buttons.addWidget(self.retry_button)
        buttons.addStretch(1)
        outer.addLayout(buttons)
        outer.addStretch(1)

        self.setAccessibleName("Sürüm hazırlanıyor")

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.bar.setFixedWidth(tokens.metric("KcAuthFieldWidth"))

    # ------------------------------------------------------------------ states
    def show_progress(self, progress) -> None:  # noqa: ANN001 - LoadProgress
        """One reading of the open. Nothing here is rounded up."""
        self.headline.setText("Sürüm hazırlanıyor")
        self.stage.setText(progress.text or "")
        self.cancel_button.show()
        self.retry_button.hide()
        if progress.fraction is None:
            # Nothing measured a total for this step. A moving bar with no
            # number is the truth; a number would not be.
            self.bar.setRange(0, 0)
            self.detail.setText("")
            return
        self.bar.setRange(0, 100)
        self.bar.setValue(int(progress.fraction * 100))
        parts = [progress.percent_text]
        if progress.eta_text:
            parts.append(progress.eta_text)
        self.detail.setText("  ·  ".join(part for part in parts if part))

    def show_empty(self, text: str, action: str = "") -> None:
        """No version chosen. A state with a way out, not a blank rectangle."""
        self.headline.setText("Etiketlenecek sürüm seçilmedi")
        self.stage.setText(text)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.hide()
        self.detail.setText("")
        self.cancel_button.hide()
        self.retry_button.setText(action or "İşlenen Videolar'a git")
        self.retry_button.setVisible(bool(action or True))

    def show_failure(self, reason: str) -> None:
        self.headline.setText("Sürüm açılamadı")
        self.stage.setText(reason or "Ayrıntı için bildirimlere bakın.")
        self.bar.hide()
        self.detail.setText("")
        self.cancel_button.hide()
        self.retry_button.setText("Yeniden dene")
        self.retry_button.show()

    def prepare(self) -> None:
        """Back to the loading look, after an empty or failed state."""
        self.bar.show()
        self.bar.setRange(0, 0)
        self.detail.setText("")
        self.cancel_button.show()
        self.retry_button.hide()


__all__ = ["LoadingSurface"]
