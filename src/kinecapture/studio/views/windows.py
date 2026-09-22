"""The six helper windows.

Modeless, so they can sit on a second monitor while the work continues in the
main window. None of them blocks anything, none of them changes anything, and
each one can be copied to the clipboard in a single click - the usual reason
to open one of these is to send what it says to somebody else.

They share one shell (:class:`ToolWindow`) and differ only in what they fill
it with, which is gathered by
:mod:`kinecapture.studio.services.inspectors` without Qt.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.inspectors import (
    LogBuffer,
    Row,
    Section,
    sections_as_text,
)
from kinecapture.studio.theme import ThemeTokens

from .widgets import label

#: Window key -> (title, what it answers). The key is what the menu passes.
WINDOW_TITLES = {
    "capture": ("Yakalama Durumu", "Kamera, kadraj ve uyarılar"),
    "log": ("Log Konsolu", "Uygulamanın kendi kaydettikleri"),
    "diagnostics": ("Tanılama", "Ortam, paketler, SDK ve kamera"),
    "device": ("Cihaz Bilgisi", "Bağlı kameranın kendi beyanı"),
    "audit": ("Kaynak Denetimi", "Türetilmiş dosyalar hâlâ aynı mı"),
    "provenance": ("Köken", "Bu sayılar nereden geldi"),
    "parameters": ("Ham Parametreler", "Sürüm hangi ayarlarla üretildi"),
}

_LEVEL_STATUS = {"ready": "ready", "warning": "warning", "error": "error"}


class ToolWindow(QWidget):
    """A modeless read-only window with a refresh and a copy button."""

    def __init__(
        self,
        key: str,
        tokens: ThemeTokens,
        provider: Callable[[], Sequence[Section]],
        parent: Optional[QWidget] = None,
    ) -> None:
        # No parent on purpose: a top-level window can be moved to another
        # monitor and does not sit on top of the main window.
        super().__init__(None)
        self.key = key
        self._tokens = tokens
        self._provider = provider
        self._sections: tuple[Section, ...] = ()

        title, subtitle = WINDOW_TITLES.get(key, (key, ""))
        self.setWindowTitle(f"{title} — KineCapture")
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.resize(560, 520)

        outer = QVBoxLayout(self)
        margin = tokens.metric("KcSpacingXl")
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(tokens.metric("KcSpacingLg"))

        outer.addWidget(label(title, role="pageTitle"))
        caption = label(subtitle)
        caption.setProperty("kcRole", "pageSubtitle")
        outer.addWidget(caption)

        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingSm"))
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_button)
        self.copy_button = QPushButton("Panoya kopyala")
        self.copy_button.setToolTip("Bütün pencereyi metin olarak kopyalar")
        self.copy_button.clicked.connect(self.copy)
        bar.addWidget(self.copy_button)
        bar.addStretch(1)
        outer.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Alan", "Değer"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setAlternatingRowColors(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(True)
        outer.addWidget(self.tree, 1)

    # ---------------------------------------------------------------- content
    def refresh(self) -> None:
        self._sections = tuple(self._provider())
        self.tree.clear()
        for section in self._sections:
            parent = QTreeWidgetItem([section.title, ""])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            self.tree.addTopLevelItem(parent)
            for row in section.rows:
                self._add(parent, row)
            if section.note:
                note = QTreeWidgetItem(["", section.note])
                note.setToolTip(1, section.note)
                parent.addChild(note)
            parent.setExpanded(True)

    def _add(self, parent: QTreeWidgetItem, row: Row) -> None:
        item = QTreeWidgetItem([row.label, row.value])
        if row.detail:
            item.setToolTip(0, row.detail)
            item.setToolTip(1, row.detail)
        status = _LEVEL_STATUS.get(row.level)
        if status:
            colour = {
                "ready": "KcStatusLive",
                "warning": "KcStatusWarning",
                "error": "KcStatusRecording",
            }[status]
            from PySide6.QtGui import QBrush, QColor

            item.setForeground(1, QBrush(QColor(self._tokens.colour(colour))))
        parent.addChild(item)

    def copy(self) -> str:
        text = sections_as_text(self._sections)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        return text

    def as_text(self) -> str:
        return sections_as_text(self._sections)

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        # Filled on open rather than on construction: these windows are built
        # once and looked at rarely, and stale content is worse than none.
        self.refresh()
        super().showEvent(event)


class LogWindow(ToolWindow):
    """The application's own log, filtered."""

    def __init__(
        self,
        tokens: ThemeTokens,
        buffer: LogBuffer,
        provider: Callable[[], Sequence[Section]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("log", tokens, provider, parent)
        self._buffer = buffer
        self.resize(820, 560)

        bar = QHBoxLayout()
        bar.setSpacing(tokens.metric("KcSpacingSm"))
        self.level_box = QComboBox()
        for name in ("DEBUG", "INFO", "WARNING", "ERROR"):
            self.level_box.addItem(name, name)
        self.level_box.setCurrentText("INFO")
        self.level_box.currentIndexChanged.connect(lambda _i: self.refresh())
        bar.addWidget(self.level_box)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Satır ara")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh())
        bar.addWidget(self.search, 1)

        self.follow_box = QCheckBox("Sonu takip et")
        self.follow_box.setChecked(True)
        bar.addWidget(self.follow_box)
        self.layout().insertLayout(3, bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.layout().insertWidget(5, self.view, 2)

    def refresh(self) -> None:
        super().refresh()
        if not hasattr(self, "view"):
            return
        lines = self._buffer.lines(
            minimum=self.level_box.currentData() or "DEBUG",
            contains=self.search.text(),
        )
        self.view.setPlainText("\n".join(lines))
        if self.follow_box.isChecked():
            bar = self.view.verticalScrollBar()
            bar.setValue(bar.maximum())

    def as_text(self) -> str:
        return "\n".join(
            [
                super().as_text(),
                "",
                "== Satırlar",
                *self._buffer.lines(minimum=self.level_box.currentData() or "DEBUG"),
            ]
        )

    def copy(self) -> str:
        text = self.as_text()
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        return text


__all__ = ["WINDOW_TITLES", "LogWindow", "ToolWindow"]
