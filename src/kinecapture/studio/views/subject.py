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
        # Inset on all four sides. Without it the three buttons below ran the
        # full width of the panel and touched its edges, which is what made
        # them read as slabs rather than as controls.
        pad = tokens.metric("KcSpacingLg")
        outer.setContentsMargins(pad, pad, pad, pad)
        outer.setSpacing(tokens.metric("KcSpacingMd"))

        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        outer.addWidget(separator())
        outer.addWidget(label("SEÇİLİ SPORCU", role="sectionTitle"))
        self.chosen_name = ElidedLabel("Sporcu seçilmedi")
        self.chosen_name.setProperty("kcRole", "contextValue")
        outer.addWidget(self.chosen_name)
        self.chosen_detail = ElidedLabel("")
        self.chosen_detail.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(self.chosen_detail)

        outer.addWidget(separator())
        self.counts = ElidedLabel("")
        self.counts.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(self.counts)

        # The lists themselves are unbounded - a recording can hold many
        # tracked people and many ambiguous intervals - so they do not live
        # here. R-02 bans scrolling in this panel, and a list folded under a
        # fold is exactly the failure that ban is about.
        self.open_people = QPushButton("Kişileri seç…")
        self.open_people.setToolTip(
            "Kayıttaki kişileri önizlemeleriyle ayrı pencerede aç"
        )
        self.open_people.setProperty("kcVariant", "primary")
        self.open_questions = QPushButton("Belirsiz aralıkları yanıtla…")
        self.open_questions.setToolTip(
            "Tracker'ın kararsız kaldığı aralıkları ayrı pencerede yanıtla"
        )
        self.all_same = QPushButton("Kalanlar: aynı sporcu")
        self.all_same.setToolTip(
            "Açık kalan bütün aralıkları seçili sporcu olarak yanıtlar. "
            "Zaten yanıtlanmış aralıklar değişmez."
        )
        self.all_same.clicked.connect(lambda: self.answer_all.emit(Verdict.SAME_ATHLETE))
        # Choosing the athlete is the primary act here, and the two below it
        # answer what is left over. A hierarchy rather than three identical
        # slabs, and left-aligned at their natural width rather than stretched
        # to the panel's edges.
        for button, stretch in (
            (self.open_people, True),
            (self.open_questions, False),
            (self.all_same, False),
        ):
            button.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(button, 1 if stretch else 0)
            if not stretch:
                row.addStretch(1)
            outer.addLayout(row)
        outer.addStretch(1)

        #: The lists the buttons above open. Built by whoever owns the panel,
        #: because the window is a sibling of the panel rather than a part of
        #: it - the panel has to stay scroll-free whatever the window holds.
        self.candidate_box: Optional[QVBoxLayout] = None
        self.question_box: Optional[QVBoxLayout] = None
        self._candidates: tuple[CandidateRow, ...] = ()
        self._questions: tuple[QuestionRow, ...] = ()

    def attach_lists(
        self, candidate_box: QVBoxLayout, question_box: QVBoxLayout
    ) -> None:
        """Where the two lists are drawn, once somebody has somewhere to put
        them. Re-filled at once so a window opened later is not empty."""
        self.candidate_box = candidate_box
        self.question_box = question_box
        self.show_candidates(self._candidates)
        self.show_questions(self._questions)

    def show_chosen(self, name: str, detail: str = "") -> None:
        self.chosen_name.setText(name or "Sporcu seçilmedi")
        self.chosen_name.setProperty("kcStatus", "ready" if name else "warning")
        style = self.chosen_name.style()
        if style is not None:
            style.unpolish(self.chosen_name)
            style.polish(self.chosen_name)
        self.chosen_detail.setText(detail)

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
        self._candidates = tuple(rows)
        self._show_counts()
        if self.candidate_box is None:
            return
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
        self._questions = tuple(rows)
        self.all_same.setEnabled(any(not r.is_answered for r in rows))
        self._show_counts()
        if self.question_box is None:
            return
        self._clear(self.question_box)
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

    def _show_counts(self) -> None:
        """Numbers, not a list. The unanswered count is the one that gates
        the export, so it is the one that reads as a warning."""
        open_questions = sum(1 for row in self._questions if not row.is_answered)
        parts = [f"{len(self._candidates)} kişi izlendi"]
        if self._questions:
            parts.append(
                f"{open_questions} belirsiz aralık yanıtsız"
                if open_questions
                else "belirsiz aralık kalmadı"
            )
        self.counts.setText(" · ".join(parts))
        self.counts.setProperty("kcStatus", "warning" if open_questions else None)
        style = self.counts.style()
        if style is not None:
            style.unpolish(self.counts)
            style.polish(self.counts)
        self.open_questions.setEnabled(bool(self._questions))
        self.open_people.setEnabled(bool(self._candidates))

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
        return QSize(320, 260)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        # Must stay small: this panel lives in a column whose width the user
        # chooses, and a large minimum here would push the whole window wider.
        return QSize(220, 200)


__all__ = ["CandidateCard", "QuestionRowWidget", "SubjectPanel"]
