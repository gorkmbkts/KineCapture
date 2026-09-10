"""The two small windows that do the actual labelling.

A movement gets a class; an error interval gets a class. That is the whole
writable label model, and it is now the whole of these dialogs. They replace a
permanently open panel that occupied two fifths of the review screen in order
to show forms the user needed for a few seconds at a time.

Correct-or-incorrect is not asked anywhere: it is derived from whether the
movement has any classified error interval. Saving the movement dialog records
that its class review is finished, which is the piece the intervals alone
cannot tell you - "no errors marked" and "nobody has looked yet" would
otherwise be the same state.

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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPlainTextEdit,
    QRadioButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from kinecapture.domain.enums import JointAnnotationStatus
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import ErrorInterval, MovementSample
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    ElidedLabel,
    FieldRow,
    make_button,
    make_label,
    make_wrapped_label,
    restyle,
)
from kinecapture.gui.widgets.joint_picker import JointRolePicker, role_label
from kinecapture.gui.widgets.label_picker import LabelClassPicker, LabelKind
from kinecapture.visualization.skeleton_spec import SkeletonSpec


class MovementLabelDialog(QDialog):
    """Which exercise this repetition is.

    That is the whole question. Correct-or-incorrect used to be asked here as
    well, and it is now read off the movement's error intervals instead: a
    repetition with a classified error interval is incorrect, one without is
    correct. Asking for both invited them to disagree, and a stored verdict
    that contradicts its own evidence tells you nothing about which half to
    believe.

    So saving this dialog means one thing: *the class review of this movement
    is finished*. With no error intervals marked, that immediately makes the
    movement correct and export-ready, with no second confirmation.
    """

    def __init__(
        self,
        theme: Theme,
        sample: MovementSample,
        schema: LabelSchema,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Hareket {sample.index} · hareket türü")
        # Sized to its content rather than to a fixed rectangle: with the
        # verdict row gone this is a search box, a short list and a note, and a
        # 480px-tall window left most of it empty.
        self.setMinimumSize(400, 340)
        self.resize(440, 420)
        self._theme = theme
        self._sample = sample
        self._schema = schema

        # The draft. Nothing touches the repository until Save.
        self._exercise = sample.exercise
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

        self._note = QPlainTextEdit()
        self._note.setPlainText(sample.note)
        self._note.setMaximumHeight(48)
        self._note.setPlaceholderText("Bu hareketle ilgili not (isteğe bağlı)")
        layout.addWidget(FieldRow("Not", self._note, theme=theme))

        self._status = ElidedLabel("", role="muted")
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self._save_button.setText("Kaydet")
        self._save_button.setDefault(True)
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
        # The dialog opened with no class has Save disabled.  Creation is a
        # valid draft class choice, so recalculate the gate immediately instead
        # of requiring the coach to close and reopen the window.
        self._sync()

    def _sync(self) -> None:
        """Say what saving will mean, and whether it is possible yet."""
        has_class = bool(self._exercise or self._pending_new_class)
        # Saving *is* the review. Without a class there is nothing to record,
        # so the button stays disabled and says why rather than accepting a
        # half-finished review that would look complete.
        self._save_button.setEnabled(has_class)
        if self._pending_new_class:
            return
        if not has_class:
            self._status.setText("Kaydetmek için bir hareket türü seçin.")
            return
        classified = len(self._sample.localised_error_codes)
        unclassified = len(self._sample.error_intervals) - classified
        if unclassified:
            self._status.setText(
                f"{unclassified} hata aralığının türü seçilmemiş; hareket "
                "tamamlanmamış kalır."
            )
        elif classified:
            self._status.setText(
                f"{classified} hata aralığı işaretli → hareket HATALI sayılır."
            )
        else:
            self._status.setText(
                "Hata aralığı yok → hareket DOĞRU sayılır ve export'a hazır olur."
            )

    # -------------------------------------------------------------- result
    @property
    def exercise(self) -> str:
        return self._exercise

    @property
    def note(self) -> str:
        return self._note.toPlainText().strip()

    @property
    def pending_new_class(self) -> str:
        """A class the user asked to create but which does not exist yet."""
        return self._pending_new_class


class ErrorLabelDialog(QDialog):
    """What the error is, and which joints it is about.

    Two questions in one place because they are one judgement: a coach who has
    just decided "knee valgus" already knows it is the left knee. Splitting
    them across two windows would ask them to remember the first answer while
    giving the second.

    The joint answer is not optional-by-omission. An empty selection has three
    different meanings - not looked at yet, no specific joint, cannot tell from
    the footage - and a model trained on the difference needs to know which. So
    the dialog makes the coach pick one of them, and refuses to save an
    interval that claims a selection with nothing selected.

    Playing the interval does **not** save or close. Watching the movement
    again is part of deciding, not the end of it; the old behaviour committed
    whatever was on screen the moment the coach wanted another look.
    """

    #: Emitted when the coach wants to watch this interval again. The review
    #: page loops it behind the dialog; the dialog stays open and unmodified.
    play_requested_now = Signal()

    def __init__(
        self,
        theme: Theme,
        interval: ErrorInterval,
        schema: LabelSchema,
        *,
        skeleton_spec: Optional[SkeletonSpec] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Hata aralığı etiketi")
        # Wide enough for the two columns to stay readable, and still well
        # inside the smallest supported window (1120x700). The layout's own
        # minimum is narrower, but at that width the splitter squeezes the
        # figure to a sliver and the explanatory lines truncate mid-word - a
        # size the dialog can be dragged to but not used at.
        self.setMinimumSize(780, 600)
        self.resize(880, 620)
        self._theme = theme
        self._interval = interval
        self._error_code = interval.error_code
        self._pending_new_class = ""
        self.requested_classes: list[str] = []
        #: Set when the user asks for the interval to be removed.
        self.delete_requested = False
        #: Kept for callers that still read it; the dialog no longer closes to
        #: play, so it is only ever ``True`` alongside a live signal.
        self.play_requested = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )
        outer.setSpacing(theme.space_sm)

        outer.addWidget(
            make_label(
                f"Kare {interval.start_frame}–{interval.end_frame}  ·  "
                f"{interval.frame_count} kare",
                role="muted",
            )
        )

        # Two columns: what happened on the left, where it happened on the
        # right. A splitter rather than fixed halves, so a long class list and
        # a large figure can each take the room they need.
        columns = QSplitter(Qt.Orientation.Horizontal)
        columns.setChildrenCollapsible(False)
        columns.addWidget(self._build_class_column(theme, schema))
        columns.addWidget(self._build_joint_column(theme, skeleton_spec))
        columns.setStretchFactor(0, 3)
        columns.setStretchFactor(1, 4)
        columns.setSizes([360, 480])
        outer.addWidget(columns, 1)

        self._status = make_wrapped_label("", role="muted")
        self._status.setMaximumHeight(40)
        outer.addWidget(self._status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self._save_button.setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        buttons.accepted.connect(self._attempt_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._restore_joint_state(interval)
        self._sync()
        self.picker.focus_search()

    # --------------------------------------------------------------- build
    def _build_class_column(self, theme: Theme, schema: LabelSchema) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_sm)

        self.picker = LabelClassPicker(theme, LabelKind.ERROR)
        self.picker.set_schema(schema)
        self.picker.set_current(self._error_code)
        self.picker.class_chosen.connect(self._class_chosen)
        self.picker.creation_requested.connect(self._creation_requested)
        layout.addWidget(self.picker, 1)

        self._note = QPlainTextEdit()
        self._note.setPlainText(self._interval.note)
        self._note.setMaximumHeight(48)
        self._note.setPlaceholderText("Bu aralıkla ilgili not (isteğe bağlı)")
        layout.addWidget(FieldRow("Not", self._note, theme=theme))

        actions = QHBoxLayout()
        actions.setSpacing(theme.space_xs)
        self.play_button = make_button(
            "Aralığı oynat",
            theme=theme,
            icon="play",
            tooltip="Bu aralığı arkada döngüde oynatır; pencere açık kalır.",
        )
        self.play_button.clicked.connect(self._request_play)
        actions.addWidget(self.play_button)
        remove = make_button("Aralığı sil", theme=theme, variant="danger")
        remove.clicked.connect(self._request_delete)
        actions.addWidget(remove)
        actions.addStretch(1)
        holder = QWidget()
        holder.setLayout(actions)
        layout.addWidget(holder)
        return column

    def _build_joint_column(
        self, theme: Theme, spec: Optional[SkeletonSpec]
    ) -> QWidget:
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_xs)

        layout.addWidget(
            make_label("Etkilenen eklemler", role="caption")
        )

        self.joint_picker = JointRolePicker(theme, spec)
        self.joint_picker.selection_changed.connect(self._selection_changed)
        layout.addWidget(self.joint_picker, 1)

        # The three answers, mutually exclusive, as radio buttons: they are one
        # question with three answers, not three independent switches.
        self._status_group = QButtonGroup(self)
        self._status_group.setExclusive(True)
        self.selected_radio = QRadioButton("Şekilde işaretlenen eklemler")
        self.not_applicable_radio = QRadioButton("Belirli bir eklem yok")
        self.not_applicable_radio.setToolTip(
            "Hata bütün gövdeyi veya tempoyu ilgilendiriyor; tek bir eklemle "
            "gösterilemiyor."
        )
        self.indeterminate_radio = QRadioButton("Görüntüden belirlenemiyor")
        self.indeterminate_radio.setToolTip(
            "Kadraj, örtüşme veya takip kalitesi güvenilir bir eklem kararına "
            "izin vermiyor."
        )
        for index, radio in enumerate(
            (
                self.selected_radio,
                self.not_applicable_radio,
                self.indeterminate_radio,
            )
        ):
            self._status_group.addButton(radio, index)
            radio.toggled.connect(lambda _=False: self._sync())
            layout.addWidget(radio)

        # Capped: the selection summary may name a dozen joints, and it must
        # not push the figure or the radio buttons out of a 700px window.
        self._chips = make_wrapped_label("", role="muted")
        self._chips.setMaximumHeight(38)
        layout.addWidget(self._chips)

        clear = make_button("Seçimi temizle", theme=theme, icon="close")
        clear.clicked.connect(self.joint_picker.clear_selection)
        self.clear_button = clear
        layout.addWidget(clear)

        self._topology_note = make_wrapped_label("", role="muted")
        self._topology_note.setMaximumHeight(46)
        layout.addWidget(self._topology_note)
        self._describe_topology(spec)
        return column

    def _describe_topology(self, spec: Optional[SkeletonSpec]) -> None:
        """Say what this take's format offers, and what it keeps regardless."""
        if spec is None:
            message = "Bu kaydın iskelet biçimi bilinmiyor; eklem seçimi yapılamaz."
            self._topology_note.setText(message)
            self._topology_note.setToolTip(message)
            return
        extra = self.joint_picker.non_target_joint_count
        missing = self.joint_picker.unavailable_roles

        # Two lines on screen, everything in the tooltip. The label is capped
        # so it cannot crowd the figure, and a sentence cut off mid-word reads
        # as a broken window - so the part that gets cut is moved out of the
        # visible text rather than left there to be truncated.
        visible = [
            f"Biçim: {spec.name} · {len(self.joint_picker.available_roles)} "
            "seçilebilir anatomik hedef."
        ]
        if extra:
            visible.append(
                f"{extra} yardımcı nokta hedef değil; export'ta kalır."
            )
        self._topology_note.setText(" ".join(visible))

        detail = list(visible)
        if extra:
            detail[-1] = (
                f"{extra} yardımcı tracker noktası hedef olarak sunulmuyor; "
                "export'ta ve modelde yerinde kalır."
            )
        if missing:
            detail.append(
                "Bu biçimde bulunmayan roller: "
                + ", ".join(role_label(role) for role in missing)
                + "."
            )
        self._topology_note.setToolTip(" ".join(detail))

    def _restore_joint_state(self, interval: ErrorInterval) -> None:
        """Put a saved interval's joint answer back exactly as it was."""
        status = interval.joint_status
        self.joint_picker.set_selected_roles(interval.affected_roles)
        if status is JointAnnotationStatus.NOT_APPLICABLE:
            self.not_applicable_radio.setChecked(True)
        elif status is JointAnnotationStatus.INDETERMINATE:
            self.indeterminate_radio.setChecked(True)
        elif status is JointAnnotationStatus.SELECTED:
            self.selected_radio.setChecked(True)
        # UNREVIEWED deliberately leaves all three unchecked, so an old
        # interval opens with the question visibly unanswered rather than
        # pre-filled with a guess.

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
        # A pending class is enough to satisfy the class half of validation.
        # Re-run the complete gate because the joint half may still be invalid.
        self._sync()

    def _request_play(self) -> None:
        """Watch the interval again without committing or closing anything."""
        self.play_requested = True
        self.play_requested_now.emit()

    def _request_delete(self) -> None:
        self.delete_requested = True
        self.accept()

    def _selection_changed(self) -> None:
        # Clicking a joint is itself the answer to "which"; ticking the radio
        # as well would be a second click for something already said.
        if self.joint_picker.selected_roles():
            self.selected_radio.setChecked(True)
        self._sync()

    # -------------------------------------------------------------- result
    @property
    def joint_status(self) -> JointAnnotationStatus:
        if self.not_applicable_radio.isChecked():
            return JointAnnotationStatus.NOT_APPLICABLE
        if self.indeterminate_radio.isChecked():
            return JointAnnotationStatus.INDETERMINATE
        if self.selected_radio.isChecked() and self.joint_picker.selected_roles():
            return JointAnnotationStatus.SELECTED
        return JointAnnotationStatus.UNREVIEWED

    @property
    def affected_roles(self) -> tuple[str, ...]:
        if self.joint_status is JointAnnotationStatus.SELECTED:
            return self.joint_picker.selected_roles()
        return ()

    def _sync(self) -> None:
        """Keep the figure, the chips and the Save gate agreeing with each other."""
        explicit_empty = (
            self.not_applicable_radio.isChecked()
            or self.indeterminate_radio.isChecked()
        )
        self.joint_picker.set_selection_enabled(not explicit_empty)
        self.clear_button.setEnabled(
            not explicit_empty and bool(self.joint_picker.selected_roles())
        )

        roles = self.joint_picker.selected_roles()
        if explicit_empty:
            self._chips.setText("Eklem seçimi bu durumda kullanılmaz.")
        elif roles:
            self._chips.setText(
                "Seçili: " + " · ".join(role_label(role) for role in roles)
            )
        else:
            self._chips.setText("Henüz eklem seçilmedi.")

        problem = self._validation_problem()
        self._save_button.setEnabled(problem == "")
        if problem:
            self._status.setText(problem)
        elif self._pending_new_class:
            self._status.setText(
                f"“{self._pending_new_class}” kaydedince projeye eklenecek "
                "ve bu aralığa atanacak."
            )
        elif self.joint_status is JointAnnotationStatus.UNREVIEWED:
            self._status.setText(
                "Eklem yanıtı verilmedi; aralık temporal hata eğitiminde "
                "kullanılır, node denetiminde maskelenir."
            )
        else:
            self._status.setText("")

    def _validation_problem(self) -> str:
        """The one thing stopping this from being saved, in the coach's words."""
        if not self._error_code and not self._pending_new_class:
            return (
                "Önce bir hata türü seçin. Sınıfsız aralık export'a girmez ve "
                "hareketi eksik bırakır."
            )
        if self.selected_radio.isChecked() and not self.joint_picker.selected_roles():
            return (
                "“Şekilde işaretlenen eklemler” seçildi fakat hiçbir eklem "
                "işaretlenmedi. Şekilden en az bir eklem seçin veya “Belirli "
                "bir eklem yok” ya da “Görüntüden belirlenemiyor” deyin."
            )
        return ""

    def _attempt_accept(self) -> None:
        """Refuse without closing, so the coach can see what to fix."""
        problem = self._validation_problem()
        if problem:
            self._status.setText(problem)
            self._status.setProperty("role", "error")
            restyle(self._status)
            return
        self.accept()

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
