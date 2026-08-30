"""Confirming the one action in this application that cannot be undone.

A yes/no box is not enough here, and not because users are careless. A project
is tens of gigabytes of recordings that can never be captured again from the
same session with the same participant, and the list it is chosen from shows
several projects with similar names. The cost of the wrong answer is total and
the cost of a slow answer is a few seconds, so this window is deliberately slow
to say yes to:

* it names the project **and** shows its full path, unelided and selectable, so
  the admin can check they are looking at the right one;
* it says in plain words what will be destroyed and that it will not come back;
* the final button stays disabled until the project's own name is typed. Typing
  a name is the cheapest available proof that the person read which project
  this is - a checkbox proves only that a checkbox was clicked.

Once the work starts there is no Cancel button. Offering one over a recursive
delete would be a lie: by the time it were pressed the files would be part
gone, and "cancelled" would describe a half-deleted project. The window stays
open instead, showing what stage the work has reached, and closes itself when
there is a real answer to give.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import Card, KeyValueList, make_label


class DeletionWorker(QThread):
    """Runs the blocking delete off the GUI thread.

    Measuring a project's size walks every file in it and removing it walks
    them again; on a full dataset that is seconds to minutes. Doing either on
    the GUI thread would freeze the window at exactly the moment the user most
    wants to see that something is happening.

    It is handed a plain callable rather than the service, so the threading can
    be tested without deleting anything and the dialog needs to know nothing
    about identity or the filesystem.
    """

    progressed = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(object)

    def __init__(
        self,
        work: Callable[[Callable[[str], None]], Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._work = work

    def run(self) -> None:
        try:
            result = self._work(self.progressed.emit)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            self.failed.emit(exc)
            return
        self.finished_ok.emit(result)


class DeleteProjectDialog(QDialog):
    """Typed confirmation, then progress, for one permanent deletion."""

    def __init__(
        self,
        theme: Theme,
        *,
        project_name: str,
        project_id: str,
        project_path: Path,
        work: Callable[[Callable[[str], None]], Any],
        is_active: bool = False,
        take_count: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Projeyi kalıcı olarak sil")
        self.setMinimumWidth(520)
        self._theme = theme
        self._project_name = project_name
        self._work = work
        self._worker: Optional[DeletionWorker] = None
        #: True once the work has begun, so a second click cannot start it again.
        self.started = False
        #: The service's report, when it got that far.
        self.outcome: Any = None
        #: What went wrong, when something did.
        self.error: Optional[BaseException] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )
        layout.setSpacing(theme.space_md)

        identity = Card("Silinecek proje", theme=theme, icon="warning")
        details = KeyValueList(theme)
        items = [("Proje", project_name), ("Proje kimliği", project_id)]
        if take_count is not None:
            items.append(("Kayıt sayısı", str(take_count)))
        details.set_items(items)
        identity.add_widget(details)

        # The path is a selectable text box rather than a label: it is the one
        # piece of evidence the admin may want to copy and check elsewhere, and
        # eliding it would hide the very part that differs between two projects.
        self.path_box = QPlainTextEdit(str(project_path))
        self.path_box.setReadOnly(True)
        self.path_box.setMaximumHeight(52)
        self.path_box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.path_box.setToolTip("Tam yol. Seçip kopyalayabilirsiniz.")
        identity.add_widget(self.path_box)
        layout.addWidget(identity)

        self.warning = make_label(
            "Bu işlem GERİ ALINAMAZ. Proje klasöründeki her şey kalıcı olarak "
            "silinir: ham RGB-D arşivi, proxy videolar, iskelet akışları, "
            "etiketler ve oluşturulmuş dataset sürümleri. Geri dönüşüm "
            "kutusuna taşınmaz, disk alanı boşalır."
            + (
                "\n\nBu proje şu anda açık; silmeden önce kapatılacak."
                if is_active
                else ""
            ),
            role="error",
        )
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)

        layout.addWidget(
            make_label(
                f"Onaylamak için proje adını birebir yazın: {project_name}",
                role="muted",
            )
        )
        self.confirm_field = QLineEdit()
        self.confirm_field.setPlaceholderText(project_name)
        self.confirm_field.textChanged.connect(self._sync)
        layout.addWidget(self.confirm_field)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate: the work is a file walk
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = make_label("", role="muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.delete_button = self._buttons.addButton(
            "Kalıcı olarak sil", QDialogButtonBox.ButtonRole.DestructiveRole
        )
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.clicked.connect(self.start)
        self.cancel_button = self._buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.cancel_button.setText("Vazgeç")
        self.cancel_button.setDefault(True)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._sync()
        self.confirm_field.setFocus()

    # ------------------------------------------------------------- gating
    def _sync(self) -> None:
        """Enable the final button only on an exact match of the project name."""
        typed = self.confirm_field.text().strip()
        matches = typed == self._project_name.strip()
        self.delete_button.setEnabled(matches and not self.started)
        if self.started:
            return
        if not typed:
            self._status.setText("")
        elif not matches:
            self._status.setText("Yazdığınız ad proje adıyla aynı değil.")
        else:
            self._status.setText("Ad doğrulandı.")

    # --------------------------------------------------------------- work
    def start(self) -> None:
        """Begin the deletion. Idempotent: a second click does nothing."""
        if self.started:
            return
        if self.confirm_field.text().strip() != self._project_name.strip():
            return
        self.started = True
        self.delete_button.setEnabled(False)
        self.confirm_field.setEnabled(False)
        # No Cancel from here on: the work is not interruptible without leaving
        # a half-deleted project, so offering the button would be dishonest.
        self.cancel_button.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText("Başlatılıyor…")

        self._worker = DeletionWorker(self._work, self)
        self._worker.progressed.connect(self._status.setText)
        self._worker.finished_ok.connect(self._succeeded)
        self._worker.failed.connect(self._errored)
        self._worker.start()

    def _succeeded(self, outcome: Any) -> None:
        self.outcome = outcome
        self._progress.setVisible(False)
        self.accept()

    def _errored(self, error: BaseException) -> None:
        self.error = error
        self._progress.setVisible(False)
        # Failure leaves the window open with a way out, because the user now
        # has something to read and possibly to act on.
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Kapat")
        text = getattr(error, "user_text", None)
        self._status.setText(text() if callable(text) else str(error))
        self._status.setProperty("role", "error")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Never leave a worker running after the window goes away."""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.wait(30_000)
        super().closeEvent(event)


__all__ = ["DeleteProjectDialog", "DeletionWorker"]
