"""Choosing the athlete: candidate cards and the questions that remain.

Two halves, in the order the work happens.

**Who is this recording about.** One card per tracked body, each showing three
frames of that body - the start, middle and end of its own span - because a
coach recognises a person by looking, not by reading a tracker id. The id is
there, in small text, for the audit trail.

**Where the tracker was unsure.** One row per unsettled stretch, each with the
same three buttons and no default. "Diğer kişi" asks which person, because
"someone else" without a name leaves those frames attributed to nobody.

The screen never proposes an answer. Nothing is pre-selected, nothing is
pre-filled, and a version with an open question says so rather than looking
finished.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kinecapture.processing.subject_review import Verdict
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.subject import CandidateRow, QuestionRow

from .widgets import ElidedLabel, label, mono_label, separator

#: Preview thumbnail width. Big enough to tell two people apart, small enough
#: that three of them fit across the inspector column without pushing it wider.
_PREVIEW_WIDTH = 68


def _thumbnail(rgb: Optional[np.ndarray], width: int = _PREVIEW_WIDTH) -> QPixmap:
    if rgb is None or rgb.size == 0:
        return QPixmap()
    array = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, source_width = array.shape[:2]
    image = QImage(
        array.data, source_width, height, source_width * 3, QImage.Format.Format_RGB888
    )
    return QPixmap.fromImage(image.copy()).scaledToWidth(
        width, Qt.TransformationMode.SmoothTransformation
    )


class CandidateCard(QFrame):
    """One person to choose between."""

    chosen = Signal(int)

    def __init__(
        self,
        row: CandidateRow,
        tokens: ThemeTokens,
        frame_at: Callable[[int], Optional[np.ndarray]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.row = row
        self.setProperty("kcRole", "raised")
        self.setProperty("kcStatus", "ready" if row.is_chosen else "neutral")
        column = QVBoxLayout(self)
        column.setContentsMargins(*(tokens.metric("KcSpacingMd"),) * 4)
        column.setSpacing(tokens.metric("KcSpacingSm"))

        header = QHBoxLayout()
        header.setSpacing(tokens.metric("KcSpacingSm"))
        title = label(row.title, role="section")
        header.addWidget(title)
        header.addStretch(1)
        # The tracker id is provenance, not identity: it means nothing outside
        # this one recording, so it is the smallest thing on the card and it
        # elides rather than pushing the column wider.
        technical = ElidedLabel(f"#{row.tracker_id}")
        technical.setProperty("kcRole", "mono")
        technical.setToolTip(
            f"tracker {row.tracker_id} — bu kimlik yalnız bu kaydın içinde "
            "geçerlidir; kayıtlar arasında bir kişiyi tanımlamaz."
        )
        technical.setMaximumWidth(72)
        header.addWidget(technical, 0, Qt.AlignmentFlag.AlignRight)
        column.addLayout(header)

        strip = QHBoxLayout()
        strip.setSpacing(tokens.metric("KcSpacingXs"))
        shown = 0
        for position in row.preview_positions:
            pixmap = _thumbnail(frame_at(position))
            if pixmap.isNull():
                continue
            view = QLabel()
            view.setPixmap(pixmap)
            view.setToolTip(f"kare {position}")
            strip.addWidget(view)
            shown += 1
        if not shown:
            missing = QLabel("Önizleme yok (bu sürümde inceleme videosu yok)")
            missing.setWordWrap(True)
            missing.setProperty("kcRole", "pageSubtitle")
            strip.addWidget(missing, 1)
        strip.addStretch(1)
        column.addLayout(strip)

        detail = QLabel(row.detail)
        detail.setWordWrap(True)
        detail.setProperty("kcRole", "pageSubtitle")
        column.addWidget(detail)

        self.button = QPushButton("Seçili sporcu" if row.is_chosen else "Bu sporcu")
        self.button.setEnabled(not row.is_chosen)
        self.button.clicked.connect(lambda: self.chosen.emit(row.tracker_id))
        column.addWidget(self.button)


class QuestionRowWidget(QFrame):
    """One unsettled stretch, with the three answers and no default."""

    answered = Signal(str, object, object)   # interval_id, verdict, tracker_id
    cleared = Signal(str)
    show_requested = Signal(str)

    def __init__(
        self,
        row: QuestionRow,
        tokens: ThemeTokens,
        fps: float,
        candidate_title: Callable[[Optional[int]], str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.row = row
        self.setProperty("kcRole", "raised")
        self.setProperty("kcStatus", "ready" if row.is_answered else "warning")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(tokens.metric("KcSpacingMd"),) * 4)
        outer.setSpacing(tokens.metric("KcSpacingSm"))

        head = QHBoxLayout()
        seconds = row.start / max(1.0, fps)
        span = (row.end - row.start + 1) / max(1.0, fps)
        when = mono_label(
            f"{int(seconds // 60):02d}:{seconds % 60:05.2f}  ·  {span:.2f} sn"
        )
        head.addWidget(when)
        head.addStretch(1)
        go = QPushButton("Göster")
        go.setToolTip("Etiketleme ekranını bu ana götür")
        go.clicked.connect(lambda: self.show_requested.emit(row.interval_id))
        head.addWidget(go)
        outer.addLayout(head)

        why = QLabel(row.reason or "tracker bu aralıkta kararsız kaldı")
        why.setWordWrap(True)
        why.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(why)

        buttons = QHBoxLayout()
        buttons.setSpacing(tokens.metric("KcSpacingSm"))
        same = QPushButton("Aynı sporcu")
        same.clicked.connect(
            lambda: self.answered.emit(row.interval_id, Verdict.SAME_ATHLETE, None)
        )
        buttons.addWidget(same)

        self.other = QPushButton("Diğer kişi…")
        self.other.setToolTip("Hangi kişi olduğunu seçin")
        self._menu = QMenu(self.other)
        for tracker_id in row.visible:
            action = self._menu.addAction(candidate_title(tracker_id))
            action.triggered.connect(
                lambda _checked=False, t=tracker_id: self.answered.emit(
                    row.interval_id, Verdict.OTHER_PERSON, t
                )
            )
        self.other.setMenu(self._menu)
        self.other.setEnabled(bool(row.visible))
        buttons.addWidget(self.other)

        nobody = QPushButton("Sporcu yok")
        nobody.clicked.connect(
            lambda: self.answered.emit(row.interval_id, Verdict.NO_ATHLETE, None)
        )
        buttons.addWidget(nobody)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        if row.is_answered:
            answer = QHBoxLayout()
            answer.addWidget(label(f"Yanıt: {row.answer_text}"))
            answer.addStretch(1)
            undo = QPushButton("Yanıtı kaldır")
            undo.clicked.connect(lambda: self.cleared.emit(row.interval_id))
            answer.addWidget(undo)
            outer.addLayout(answer)


class SubjectPanel(QWidget):
    """The whole athlete-selection surface."""

    athlete_chosen = Signal(int)
    answered = Signal(str, object, object)
    cleared = Signal(str)
    show_requested = Signal(str)
    answer_all = Signal(object)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._frame_at: Callable[[int], Optional[np.ndarray]] = lambda _p: None
        self._candidate_title: Callable[[Optional[int]], str] = lambda t: str(t)
        self._fps = 30.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(tokens.metric("KcSpacingMd"))

        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        outer.addWidget(label("Kayıttaki kişiler", role="section"))
        self.candidate_area, self.candidate_box = self._scroller()
        outer.addWidget(self.candidate_area, 1)

        outer.addWidget(separator())
        head = QHBoxLayout()
        head.addWidget(label("Belirsiz aralıklar", role="section"))
        head.addStretch(1)
        self.all_same = QPushButton("Kalanlar: aynı sporcu")
        self.all_same.setToolTip(
            "Açık kalan bütün aralıkları seçili sporcu olarak yanıtlar. "
            "Zaten yanıtlanmış aralıklar değişmez."
        )
        self.all_same.clicked.connect(lambda: self.answer_all.emit(Verdict.SAME_ATHLETE))
        head.addWidget(self.all_same)
        outer.addLayout(head)

        self.question_area, self.question_box = self._scroller()
        outer.addWidget(self.question_area, 2)

    def _scroller(self) -> tuple[QScrollArea, QVBoxLayout]:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(self._tokens.metric("KcSpacingSm"))
        box.addStretch(1)
        area.setWidget(holder)
        return area, box

    # ---------------------------------------------------------------- wiring
    def set_context(
        self,
        frame_at: Callable[[int], Optional[np.ndarray]],
        candidate_title: Callable[[Optional[int]], str],
        fps: float,
    ) -> None:
        self._frame_at = frame_at
        self._candidate_title = candidate_title
        self._fps = fps

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens

    def set_status(self, text: str, settled: bool) -> None:
        self.status.setText(text)
        self.status.setProperty("kcStatus", "ready" if settled else "warning")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    # ----------------------------------------------------------------- fill
    def show_candidates(self, rows: tuple[CandidateRow, ...]) -> None:
        self._clear(self.candidate_box)
        for row in rows:
            card = CandidateCard(row, self._tokens, self._frame_at)
            card.chosen.connect(self.athlete_chosen)
            self.candidate_box.insertWidget(self.candidate_box.count() - 1, card)
        if not rows:
            self.candidate_box.insertWidget(
                0, self._empty("Bu sürümde izlenen hiçbir kişi yok.")
            )

    def show_questions(self, rows: tuple[QuestionRow, ...]) -> None:
        self._clear(self.question_box)
        self.all_same.setEnabled(any(not r.is_answered for r in rows))
        for row in rows:
            widget = QuestionRowWidget(
                row, self._tokens, self._fps, self._candidate_title
            )
            widget.answered.connect(self.answered)
            widget.cleared.connect(self.cleared)
            widget.show_requested.connect(self.show_requested)
            self.question_box.insertWidget(self.question_box.count() - 1, widget)
        if not rows:
            self.question_box.insertWidget(
                0,
                self._empty(
                    "Tracker bu kayıtta hiç kararsız kalmadı; sorulacak aralık yok."
                ),
            )

    def _empty(self, text: str) -> QLabel:
        widget = QLabel(text)
        widget.setWordWrap(True)
        widget.setProperty("kcRole", "pageSubtitle")
        return widget

    @staticmethod
    def _clear(box: QVBoxLayout) -> None:
        while box.count() > 1:
            item = box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        return QSize(320, 520)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        # Must stay small: this panel lives in a column whose width the user
        # chooses, and a large minimum here would push the whole window wider.
        return QSize(220, 240)


__all__ = ["CandidateCard", "QuestionRowWidget", "SubjectPanel"]
