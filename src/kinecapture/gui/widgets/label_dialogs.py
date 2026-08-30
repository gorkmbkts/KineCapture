"""The two small windows that do the actual labelling.

A movement gets a class and a verdict; an error interval gets a class. That is
the whole writable label model, and it is now the whole of these dialogs. They
replace a permanently open panel that occupied two fifths of the review screen
in order to show forms the user needed for a few seconds at a time.

Both open on a double click on the interval they belong to, so the thing being
labelled is the thing that was clicked - there is no separate "which one is
selected?" question to get wrong.

Cancel semantics, stated because they are easy to get subtly wrong:

* **Cancel leaves the interval exactly as it was.** Every edit is applied to a
  local draft and only written on Save.
* **A class created inside the dialog stays created even if you then cancel.**
  Adding a class is a *project* edit - it goes into ``label_schema.json`` for
  every take - and quietly removing it because one dialog was dismissed would
  be surprising and could break another take that already used it. Cancelling
  only means "do not assign it here".
* An interval left without a class is not silently "done": it keeps showing as
  incomplete, and the export rule that reads the same state agrees.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from kinecapture.domain.enums import Correctness
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import ErrorInterval, MovementSample
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import FieldRow, make_button, make_label
from kinecapture.gui.widgets.label_picker import LabelClassPicker, LabelKind


class MovementLabelDialog(QDialog):
    """Class and verdict for one movement.

    The verdict is here rather than on a side panel because it is inseparable
    from the class: a movement with neither is not labelled, and the two are
    always decided in the same breath.
    """

    def __init__(
        self,
        theme: Theme,
        sample: MovementSample,
        schema: LabelSchema,
        *,
        readiness: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Hareket {sample.index} etiketi")
        self.setMinimumSize(440, 480)
        self._theme = theme
        self._sample = sample
        self._schema = schema
        self._readiness = readiness

        # The draft. Nothing touches the repository until Save.
        self._exercise = sample.exercise
        self._correctness = sample.correctness
        self._pending_new_class = ""
        #: Names typed into the picker that the caller must create. Reported
        #: even when the dialog is cancelled, because creating a class is a
        #: project edit the user asked for explicitly.
        self.requested_classes: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )
        layout.setSpacing(theme.space_sm)

        span = make_label(
            f"Kare {sample.start_frame}–{sample.end_frame}  ·  "
            f"{sample.frame_count} kare",
            role="muted",
        )
        layout.addWidget(span)

        self.picker = LabelClassPicker(theme, LabelKind.MOVEMENT)
        self.picker.set_schema(schema)
        self.picker.set_current(self._exercise)
        self.picker.class_chosen.connect(self._class_chosen)
        self.picker.creation_requested.connect(self._creation_requested)
        layout.addWidget(self.picker, 1)

        verdict = QHBoxLayout()
        verdict.setSpacing(theme.space_xs)
        self._correct_button = make_button(
            "Doğru", theme=theme, icon="check", tooltip="Bu tekrar doğru yapıldı (1)"
        )
        self._correct_button.setCheckable(True)
        self._correct_button.clicked.connect(
            lambda: self._set_verdict(Correctness.CORRECT)
        )
        verdict.addWidget(self._correct_button)
        self._incorrect_button = make_button(
            "Hatalı",
            theme=theme,
            icon="warning",
            tooltip="Bu tekrarda hata var; hata aralığını ayrıca işaretleyin (2)",
        )
        self._incorrect_button.setCheckable(True)
        self._incorrect_button.clicked.connect(
            lambda: self._set_verdict(Correctness.INCORRECT)
        )
        verdict.addWidget(self._incorrect_button)
        verdict.addStretch(1)
        holder = QWidget()
        holder.setLayout(verdict)
        layout.addWidget(FieldRow("Karar", holder, theme=theme))

        self._note = QPlainTextEdit()
        self._note.setPlainText(sample.note)
        self._note.setMaximumHeight(56)
        self._note.setPlaceholderText("Bu hareketle ilgili not (isteğe bağlı)")
        layout.addWidget(FieldRow("Not", self._note, theme=theme))

        self._status = make_label("", role="muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._sync()
        self.picker.focus_search()

    # ------------------------------------------------------------- editing
    def _class_chosen(self, code: str) -> None:
        self._exercise = code
        # Picking an existing class supersedes a "create this name" request the
        # user made a moment earlier, otherwise Save would create the abandoned
        # name as well and assign that instead.
        self._pending_new_class = ""
        self.picker.set_current(code)
        self._sync()

    def _creation_requested(self, name: str) -> None:
        """Remember the request; the page owns the repository that creates it."""
        cleaned = " ".join((name or "").split())
        if cleaned and cleaned not in self.requested_classes:
            self.requested_classes.append(cleaned)
        self._status.setText(
            f"“{cleaned}” kaydedince projeye eklenecek ve bu harekete atanacak."
        )
        self._pending_new_class = cleaned

    def _set_verdict(self, correctness: Correctness) -> None:
        self._correctness = correctness
        self._sync()

    def _sync(self) -> None:
        self._correct_button.setChecked(self._correctness is Correctness.CORRECT)
        self._incorrect_button.setChecked(self._correctness is Correctness.INCORRECT)
        if self._pending_new_class:
            return
        missing: list[str] = []
        if not self._exercise:
            missing.append("hareket türü")
        if not self._correctness.is_decided:
            missing.append("doğru/hatalı kararı")
        if missing:
            self._status.setText(
                "Eksik: " + ", ".join(missing) + ". Kaydedebilirsiniz; hareket "
                "tamamlanmamış olarak işaretlenir ve export'a girmez."
            )
        elif self._correctness is Correctness.INCORRECT and not self._sample.error_intervals:
            self._status.setText(
                "Hatalı işaretlendi. Hata aralığı eklenene kadar export'a girmez."
            )
        elif self._correctness is Correctness.CORRECT and self._sample.error_intervals:
            self._status.setText(
                "Çelişki: doğru işaretli bir harekette hata aralığı var."
            )
        elif self._readiness:
            self._status.setText(f"Durum: {self._readiness}")
        else:
            self._status.setText("")

    # -------------------------------------------------------------- result
    @property
    def exercise(self) -> str:
        return self._exercise

    @property
    def correctness(self) -> Correctness:
        return self._correctness

    @property
    def note(self) -> str:
        return self._note.toPlainText().strip()

    @property
    def pending_new_class(self) -> str:
        """A class the user asked to create but which does not exist yet."""
        return self._pending_new_class


class ErrorLabelDialog(QDialog):
    """The single class carried by one error interval."""

    def __init__(
        self,
        theme: Theme,
        interval: ErrorInterval,
        schema: LabelSchema,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hata aralığı etiketi")
        self.setMinimumSize(440, 460)
        self._theme = theme
        self._interval = interval
        self._error_code = interval.error_code
        self._pending_new_class = ""
        self.requested_classes: list[str] = []
        #: Set when the user asks for the interval to be removed.
        self.delete_requested = False
        #: Set when the user asks to loop this interval in the player.
        self.play_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )
        layout.setSpacing(theme.space_sm)

        layout.addWidget(
            make_label(
                f"Kare {interval.start_frame}–{interval.end_frame}  ·  "
                f"{interval.frame_count} kare",
                role="muted",
            )
        )

        self.picker = LabelClassPicker(theme, LabelKind.ERROR)
        self.picker.set_schema(schema)
        self.picker.set_current(self._error_code)
        self.picker.class_chosen.connect(self._class_chosen)
        self.picker.creation_requested.connect(self._creation_requested)
        layout.addWidget(self.picker, 1)

        self._note = QPlainTextEdit()
        self._note.setPlainText(interval.note)
        self._note.setMaximumHeight(48)
        self._note.setPlaceholderText("Bu aralıkla ilgili not (isteğe bağlı)")
        layout.addWidget(FieldRow("Not", self._note, theme=theme))

        actions = QHBoxLayout()
        actions.setSpacing(theme.space_xs)
        play = make_button("Aralığı oynat", theme=theme, icon="play")
        play.clicked.connect(self._request_play)
        actions.addWidget(play)
        remove = make_button("Aralığı sil", theme=theme, variant="danger")
        remove.clicked.connect(self._request_delete)
        actions.addWidget(remove)
        actions.addStretch(1)
        holder = QWidget()
        holder.setLayout(actions)
        layout.addWidget(holder)

        self._status = make_label("", role="muted")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._sync()
        self.picker.focus_search()

    def _class_chosen(self, code: str) -> None:
        self._error_code = code
        self._pending_new_class = ""
        self.picker.set_current(code)
        self._sync()

    def _creation_requested(self, name: str) -> None:
        cleaned = " ".join((name or "").split())
        if cleaned and cleaned not in self.requested_classes:
            self.requested_classes.append(cleaned)
        self._pending_new_class = cleaned
        self._status.setText(
            f"“{cleaned}” kaydedince projeye eklenecek ve bu aralığa atanacak."
        )

    def _request_play(self) -> None:
        self.play_requested = True
        self.accept()

    def _request_delete(self) -> None:
        self.delete_requested = True
        self.accept()

    def _sync(self) -> None:
        if self._pending_new_class:
            return
        self._status.setText(
            ""
            if self._error_code
            else "Sınıfsız aralık export'a girmez ve hareketi eksik bırakır."
        )

    @property
    def error_code(self) -> str:
        return self._error_code

    @property
    def note(self) -> str:
        return self._note.toPlainText().strip()

    @property
    def pending_new_class(self) -> str:
        return self._pending_new_class


__all__ = ["ErrorLabelDialog", "MovementLabelDialog"]
