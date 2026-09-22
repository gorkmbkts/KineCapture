"""The three things the labelling band deliberately does not hold.

The acceptance brief bans scrolling in the panel and asks for the editor to
stay a band rather than a form. Three things genuinely do not fit that: a
project's whole class vocabulary, a free-text note, and the per-interval joint
evidence that only a correction needs. Each gets a small window instead of a
row in the band.

They are modeless. A dialog that blocks would close over the interval that
prompted it, which is the failure the class picker was moved out of a dialog
to avoid in the first place.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.theme import ThemeTokens

from .widgets import ElidedLabel, label, separator


class _Window(QDialog):
    """Shared shell: a title, a body, and a way out that is not "OK"."""

    def __init__(
        self, title: str, tokens: ThemeTokens, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setWindowTitle(title)
        self.setModal(False)
        self.column = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingMd")
        self.column.setContentsMargins(margin, margin, margin, margin)
        self.column.setSpacing(tokens.metric("KcSpacingSm"))


class OverflowPanel(QWidget):
    """Keep short panels usable; show their full controls in a modeless window."""

    def __init__(self, content: QWidget, title: str, tokens: ThemeTokens,
                 quick_controls: Optional[QWidget] = None) -> None:
        super().__init__()
        self.content = content
        self._title = title
        self._tokens = tokens
        self._window = None
        self._compact = False
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.addWidget(content)
        self.compact = QWidget(self)
        column = QVBoxLayout(self.compact)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(tokens.metric("KcSpacingSm"))
        column.addWidget(label(title, role="sectionTitle"))
        if quick_controls is not None:
            column.addWidget(quick_controls)
        self.open_button = QPushButton(f"{title}…")
        self.open_button.clicked.connect(self.open_controls)
        column.addWidget(self.open_button)
        column.addStretch(1)
        self._column.addWidget(self.compact)
        self.compact.hide()

    def minimumSizeHint(self):  # noqa: N802
        return self.compact.minimumSizeHint()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._sync()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._sync()

    def _sync(self) -> None:
        self._compact = self.height() < self.content.minimumSizeHint().height()
        self.compact.setVisible(self._compact)
        if self._window is None or not self._window.isVisible():
            self.content.setVisible(not self._compact)

    def open_controls(self) -> None:
        if self._window is None:
            self._window = _Window(self._title, self._tokens, self)
            self._window.finished.connect(self._restore_content)
            close = QPushButton("Kapat")
            close.clicked.connect(self._window.close)
            self._window.column.addWidget(close)
        self._window.column.insertWidget(0, self.content)
        self.content.show()
        self._window.adjustSize()
        self._window.show()
        self._window.raise_()

    def _restore_content(self, _result=0) -> None:
        self._column.insertWidget(0, self.content)
        self._sync()


class DetailWindow(_Window):
    """Whatever a reserved line could only summarise, at full length.

    The Yakalama status pane keeps a fixed height so the controls under it
    cannot move; a long framing explanation or a stack of alerts therefore has
    nowhere to go on that screen. It comes here, wrapped, in full, with the
    kind of thing each row is.
    """

    def __init__(
        self, title: str, tokens: ThemeTokens, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(title, tokens, parent)
        self.resize(460, 300)
        self.body = QPlainTextEdit()
        self.body.setReadOnly(True)
        self.body.setAccessibleName(title)
        self.column.addWidget(self.body, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Kapat")
        close.clicked.connect(self.close)
        row.addWidget(close)
        self.column.addLayout(row)

    def show_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        blocks = [f"{kind}\n{text}" for kind, text in rows]
        self.body.setPlainText(
            "\n\n".join(blocks) or "Şu anda bildirilecek bir şey yok."
        )

    @property
    def text(self) -> str:
        return self.body.toPlainText()


class ClassBrowser(_Window):
    """Every class in the project, searchable. One scroll, and only here.

    The band shows the classes in use and sends the rest here. This is the one
    place a long list is allowed to scroll, because a list *is* the content -
    unlike the panel, where scrolling meant a form had been folded up.
    """

    chosen = Signal(str)

    def __init__(
        self,
        title: str,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(title, tokens, parent)
        self.resize(360, 460)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Sınıf ara")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Sınıf ara")
        self.search.textChanged.connect(lambda _t: self._refill())
        self.column.addWidget(self.search)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.itemActivated.connect(self._activated)
        self.list.itemClicked.connect(self._activated)
        self.column.addWidget(self.list, 1)

        self.count = ElidedLabel("")
        self.count.setProperty("kcRole", "pageSubtitle")
        self.column.addWidget(self.count)

        close = QPushButton("Kapat")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        self.column.addLayout(row)

        self._options: tuple[tuple[str, str], ...] = ()

    def set_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._options = tuple(options)
        self._refill()

    def _refill(self) -> None:
        needle = self.search.text().strip().casefold()
        self.list.clear()
        shown = 0
        for code, text in self._options:
            if needle and needle not in text.casefold() and needle not in code.casefold():
                continue
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.list.addItem(item)
            shown += 1
        total = len(self._options)
        self.count.setText(
            f"{shown}/{total} sınıf" if shown != total else f"{total} sınıf"
        )

    def _activated(self, item: QListWidgetItem) -> None:
        code = item.data(Qt.ItemDataRole.UserRole)
        if code:
            self.chosen.emit(str(code))
            self.close()


class NoteWindow(_Window):
    """A free-text note. Secondary by definition: nothing gates on it."""

    saved = Signal(str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__("Not", tokens, parent)
        self.resize(420, 260)
        self.subject = ElidedLabel("")
        self.subject.setProperty("kcRole", "contextValue")
        self.column.addWidget(self.subject)
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Not")
        self.column.addWidget(self.text, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Kapat")
        close.clicked.connect(self.close)
        row.addWidget(close)
        keep = QPushButton("Kaydet")
        keep.setProperty("kcVariant", "primary")
        keep.clicked.connect(self._save)
        row.addWidget(keep)
        self.column.addLayout(row)

    def show_note(self, subject: str, text: str) -> None:
        self.subject.setText(subject)
        self.text.setPlainText(text or "")

    def _save(self) -> None:
        self.saved.emit(self.text.toPlainText().strip())
        self.close()


class JointEvidenceWindow(_Window):
    """Correcting the joints on *one* interval, by their anatomical names.

    Deliberately not the main way in. Picking on the skeleton is, because the
    question is "which joint" and a joint is a thing on a body rather than a
    line in a list. What this window is for is the case picking cannot serve:
    a joint that is hidden behind the torso at every angle, a recording with
    no 3-D data at all, or an old label somebody needs to read back and amend.

    It edits this interval's evidence only. The class's own default joints are
    not touched, so correcting one repetition cannot silently redefine what a
    class means everywhere else.
    """

    applied = Signal(tuple, str)

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__("Eklem kanıtı", tokens, parent)
        self.resize(320, 460)

        self.subject = ElidedLabel("")
        self.subject.setProperty("kcRole", "contextValue")
        self.column.addWidget(self.subject)

        note = QLabel(
            "Bu pencere yalnız seçili aralığın eklem kanıtını değiştirir. "
            "Sınıfın varsayılan eklemleri olduğu gibi kalır."
        )
        note.setWordWrap(True)
        note.setProperty("kcRole", "pageSubtitle")
        self.column.addWidget(note)

        self.column.addWidget(separator())
        self.column.addWidget(label("Eklem durumu"))
        self.status = QComboBox()
        self.status.setAccessibleName("Eklem durumu")
        self.column.addWidget(self.status)

        self.column.addWidget(label("İlgili eklemler"))
        self.roles = QListWidget()
        self.roles.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.column.addWidget(self.roles, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Vazgeç")
        close.clicked.connect(self.close)
        row.addWidget(close)
        apply_button = QPushButton("Uygula")
        apply_button.setProperty("kcVariant", "primary")
        apply_button.clicked.connect(self._apply)
        row.addWidget(apply_button)
        self.column.addLayout(row)

    def set_statuses(self, statuses: Sequence[tuple[str, str]]) -> None:
        self.status.clear()
        for value, text in statuses:
            self.status.addItem(text, value)

    def show_interval(
        self,
        subject: str,
        available: Sequence[str],
        chosen: Sequence[str],
        status: str,
    ) -> None:
        """Offer only the roles this skeleton actually has.

        A role with no joint behind it is not listed: ticking it would be a
        claim about a joint the recording does not contain.
        """
        self.subject.setText(subject)
        self.roles.clear()
        marked = set(chosen)
        for role in sorted(available):
            item = QListWidgetItem(role.replace("_", " "))
            item.setData(Qt.ItemDataRole.UserRole, role)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if role in marked else Qt.CheckState.Unchecked
            )
            self.roles.addItem(item)
        index = self.status.findData(status)
        self.status.setCurrentIndex(max(0, index))

    def checked_roles(self) -> tuple[str, ...]:
        return tuple(
            self.roles.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.roles.count())
            if self.roles.item(i).checkState() is Qt.CheckState.Checked
        )

    def _apply(self) -> None:
        self.applied.emit(self.checked_roles(), str(self.status.currentData() or ""))
        self.close()


class SubjectListWindow(_Window):
    """The tracked people and the ambiguous intervals, side by side.

    Both lists are unbounded - a recording can hold several tracked people
    and dozens of moments the tracker was unsure about - so neither belongs
    in a panel that is not allowed to scroll. Here they have the room to be
    lists, and the panel keeps the decision and the counts.

    The panel still owns the rows: this window lends it two layouts to draw
    into, so there is one place that knows how a candidate or a question is
    rendered.
    """

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__("Kayıttaki kişiler", tokens, parent)
        self.resize(720, 560)
        row = QHBoxLayout()
        row.setSpacing(tokens.metric("KcSpacingMd"))

        people = QVBoxLayout()
        people.addWidget(label("Kayıttaki kişiler", role="section"))
        self.candidate_area, self.candidate_box = self._scroller(tokens)
        people.addWidget(self.candidate_area, 1)
        row.addLayout(people, 1)

        questions = QVBoxLayout()
        questions.addWidget(label("Belirsiz aralıklar", role="section"))
        self.question_area, self.question_box = self._scroller(tokens)
        questions.addWidget(self.question_area, 1)
        row.addLayout(questions, 1)
        self.column.addLayout(row, 1)

        close = QPushButton("Kapat")
        close.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close)
        self.column.addLayout(footer)

    @staticmethod
    def _scroller(tokens: ThemeTokens):  # noqa: ANN205
        from PySide6.QtWidgets import QScrollArea

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(tokens.metric("KcSpacingSm"))
        box.addStretch(1)
        area.setWidget(holder)
        return area, box

    def focus_questions(self) -> None:
        self.question_area.setFocus()


class AdvancedCameraWindow(_Window):
    """The camera controls that are used occasionally.

    They were on the panel and did not fit: the tab needed 652 px in a 455 px
    band, which the interface showed by drawing the compass over the line
    under it. Saving a view, going back to a saved one, redefining the front
    and turning off the transition are all real and all occasional, so they
    are here rather than gone.
    """

    def __init__(
        self,
        tokens: ThemeTokens,
        widgets: Sequence[QWidget],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Gelişmiş kamera", tokens, parent)
        self.resize(300, 240)
        for widget in widgets:
            widget.setParent(self)
            self.column.addWidget(widget)
        self.column.addStretch(1)
        close = QPushButton("Kapat")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        self.column.addLayout(row)


__all__ = [
    "AdvancedCameraWindow",
    "ClassBrowser",
    "JointEvidenceWindow",
    "NoteWindow",
    "SubjectListWindow",
]
