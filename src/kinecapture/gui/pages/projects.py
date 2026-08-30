"""Access-filtered projects and coach-friendly recording plans."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.errors import KineCaptureError
from kinecapture.domain.project import CaptureProtocol, ProtocolTask
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import Card, FieldRow, KeyValueList, make_button, make_label


class NewProjectDialog(QDialog):
    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yeni proje")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self._name = QLineEdit()
        self._name.setPlaceholderText("Örn. Diz Rehabilitasyonu Pilot")
        self._name_row = FieldRow("Proje adı", self._name, theme=theme, required=True)
        layout.addWidget(self._name_row)
        self._description = QPlainTextEdit()
        self._description.setMaximumHeight(80)
        self._description.setPlaceholderText("Kısa açıklama (isteğe bağlı)")
        layout.addWidget(FieldRow("Açıklama", self._description, theme=theme))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Oluştur")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self._name.text().strip():
            self._name_row.set_error("Proje adı zorunludur.")
            return
        self.accept()

    @property
    def project_name(self) -> str:
        return self._name.text().strip()

    @property
    def project_description(self) -> str:
        return self._description.toPlainText().strip()


class RecordingPlanDialog(QDialog):
    """Three-step-equivalent compact form: name, ordered movements, summary."""

    def __init__(
        self,
        theme: Theme,
        protocol: Optional[CaptureProtocol] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.protocol = protocol
        self.setWindowTitle("Kayıt Planı")
        self.setMinimumSize(520, 470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self._name = QLineEdit(protocol.name if protocol else "")
        self._name_row = FieldRow("1. Plan adı", self._name, theme=theme, required=True)
        layout.addWidget(self._name_row)
        self._movements = QPlainTextEdit()
        self._movements.setPlaceholderText("Her satıra bir hareket yazın\nÖrn.\nSquat\nLunge")
        if protocol:
            self._movements.setPlainText(
                "\n".join(task.display_label for task in protocol.tasks)
            )
        self._movement_row = FieldRow(
            "2. Kaydedilecek hareketler (sıralı)",
            self._movements,
            theme=theme,
            required=True,
        )
        layout.addWidget(self._movement_row, 1)
        self._advanced = QGroupBox("Gelişmiş hedefler")
        self._advanced.setCheckable(True)
        self._advanced.setChecked(False)
        advanced_layout = QVBoxLayout(self._advanced)
        advanced_note = make_label(
            "Doğru/hatalı kayıt hedefi, tekrar, taraf, talimat ve güvenlik notu "
            "plan kaydedildikten sonra seçili hareket için düzenlenebilir.",
            role="muted",
        )
        advanced_note.setWordWrap(True)
        advanced_layout.addWidget(advanced_note)
        layout.addWidget(self._advanced)
        self._summary = make_label("3. Özet kaydederken doğrulanacaktır.", role="subtitle")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        self._movements.textChanged.connect(self._update_summary)
        self._name.textChanged.connect(self._update_summary)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kayıt Planını Kaydet")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)
        self._update_summary()

    def _movement_names(self) -> list[str]:
        return [line.strip() for line in self._movements.toPlainText().splitlines() if line.strip()]

    def _update_summary(self) -> None:
        names = self._movement_names()
        self._summary.setText(
            f"3. Özet: {self._name.text().strip() or 'Adsız plan'} · "
            f"{len(names)} hareket"
        )

    def _accept(self) -> None:
        valid = True
        if not self._name.text().strip():
            self._name_row.set_error("Plan adı zorunludur.")
            valid = False
        else:
            self._name_row.clear_error()
        if not self._movement_names():
            self._movement_row.set_error("En az bir hareket ekleyin.")
            valid = False
        else:
            self._movement_row.clear_error()
        if valid:
            self.accept()

    def build(self) -> CaptureProtocol:
        protocol = self.protocol or CaptureProtocol.create(self._name.text().strip())
        old_by_label = {task.display_label.casefold(): task for task in protocol.tasks}
        tasks: list[ProtocolTask] = []
        for movement in self._movement_names():
            existing = old_by_label.get(movement.casefold())
            if existing:
                existing.label = movement
                tasks.append(existing)
            else:
                tasks.append(ProtocolTask.create(exercise=movement, label=movement))
        protocol.name = self._name.text().strip()
        protocol.tasks = tasks
        return protocol


class AdvancedTargetDialog(QDialog):
    def __init__(
        self, theme: Theme, task: ProtocolTask, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.setWindowTitle("Gelişmiş hareket hedefleri")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self._correct = QSpinBox()
        self._correct.setRange(0, 999)
        self._correct.setValue(task.target_correct_takes)
        layout.addWidget(FieldRow("Hedef doğru kayıt", self._correct, theme=theme))
        self._incorrect = QSpinBox()
        self._incorrect.setRange(0, 999)
        self._incorrect.setValue(task.target_incorrect_takes)
        layout.addWidget(FieldRow("Hedef hatalı kayıt", self._incorrect, theme=theme))
        self._reps = QSpinBox()
        self._reps.setRange(0, 999)
        self._reps.setValue(task.reps_per_take)
        layout.addWidget(FieldRow("Kayıt başına tekrar", self._reps, theme=theme))
        self._side = QComboBox()
        for value, label in (("both", "Her iki taraf"), ("left", "Sol"), ("right", "Sağ")):
            self._side.addItem(label, value)
        self._side.setCurrentIndex(max(0, self._side.findData(task.side)))
        layout.addWidget(FieldRow("Taraf", self._side, theme=theme))
        self._error_type = QLineEdit(task.planned_error_type)
        layout.addWidget(FieldRow("Planlanan hata türü", self._error_type, theme=theme))
        self._instruction = QPlainTextEdit(task.operator_instruction)
        self._instruction.setMaximumHeight(65)
        layout.addWidget(FieldRow("Operatör talimatı", self._instruction, theme=theme))
        self._safety = QPlainTextEdit(task.safety_note)
        self._safety.setMaximumHeight(65)
        layout.addWidget(FieldRow("Güvenlik notu", self._safety, theme=theme))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def apply(self) -> None:
        self.task.target_correct_takes = self._correct.value()
        self.task.target_incorrect_takes = self._incorrect.value()
        self.task.reps_per_take = self._reps.value()
        self.task.side = str(self._side.currentData())
        self.task.planned_error_type = self._error_type.text().strip()
        self.task.operator_instruction = self._instruction.toPlainText().strip()
        self.task.safety_note = self._safety.toPlainText().strip()


class ProjectsPage(Page):
    navigate_requested = Signal(str)
    title = "Projeler"
    description = "Erişebildiğiniz projeyi seçin veya yeni bir proje oluşturun."
    icon = "project"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme
        new_button = make_button("Yeni Proje", variant="primary", icon="add", theme=theme)
        new_button.clicked.connect(self._create_project)
        self.header.add_action(new_button)
        self._import_button = make_button("Klasörden içe aktar", icon="folder-open", theme=theme)
        self._import_button.clicked.connect(self._import_project)
        self.header.add_action(self._import_button)
        self._root_button = make_button("Veri klasörü", icon="settings", theme=theme)
        self._root_button.clicked.connect(self._change_root)
        self.header.add_action(self._root_button)

        columns = QHBoxLayout()
        columns.setSpacing(theme.space_md)
        columns.addWidget(self._build_list(theme), 2)
        columns.addWidget(self._build_details(theme), 3)
        self.content.addLayout(columns, 1)
        state.project_changed.connect(lambda _: self._reload())

    def _build_list(self, theme: Theme) -> QWidget:
        card = Card("Erişilebilir projeler", theme=theme, icon="project")
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentItemChanged.connect(lambda *_: self._refresh_details())
        self._list.itemDoubleClicked.connect(lambda _: self._open_selected())
        card.add_widget(self._list, 1)
        open_button = make_button("Projeyi Aç", variant="primary", theme=theme)
        open_button.clicked.connect(self._open_selected)
        card.add_widget(open_button)
        return card

    def _build_details(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)
        detail = Card("Proje özeti", theme=theme, icon="info")
        self._details = KeyValueList(theme)
        detail.add_widget(self._details)
        layout.addWidget(detail)
        plans = Card(
            "Kayıt Planları",
            subtitle="Tek plan otomatik seçilir; plan yoksa serbest kayıt kullanılır.",
            theme=theme,
            icon="list",
        )
        self._plans = QComboBox()
        self._plans.currentIndexChanged.connect(self._reload_tasks)
        plans.add_widget(self._plans)
        self._tasks = QListWidget()
        self._tasks.itemDoubleClicked.connect(lambda _: self._edit_target())
        plans.add_widget(self._tasks, 1)
        row = QHBoxLayout()
        for label, handler in (
            ("Kayıt Planı Ekle", self._add_plan),
            ("Planı Düzenle", self._edit_plan),
            ("Gelişmiş hedefler", self._edit_target),
        ):
            button = make_button(label, theme=theme)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        plans.add_widget(container)
        self._plan_card = plans
        layout.addWidget(plans, 1)
        return wrapper

    def on_activated(self) -> None:
        user = self.state.current_user
        owner = bool(user and user.is_owner)
        self._import_button.setVisible(owner)
        self._root_button.setVisible(owner)
        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        if not self.state.is_authenticated:
            return
        try:
            projects = self.state.list_accessible_projects()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        for project in projects:
            item = QListWidgetItem(
                f"{project.name}\n{project.description or 'Açıklama yok'}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(project.path))
            item.setData(Qt.ItemDataRole.UserRole + 1, project.project_id)
            self._list.addItem(item)
            if self.state.workspace and self.state.workspace.root == project.path:
                self._list.setCurrentItem(item)
        if not projects:
            item = QListWidgetItem(
                "Henüz erişebildiğiniz bir proje yok.\nYeni Proje ile başlayabilirsiniz."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
        self._refresh_details()

    def _refresh_details(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            self._details.set_items([("Durum", "Açık proje yok")])
            self._plan_card.setEnabled(False)
            self._plans.clear()
            self._tasks.clear()
            return
        self._plan_card.setEnabled(True)
        project = workspace.project
        counts = workspace.summary_counts()
        items = [
            ("Ad", project.name),
            ("Açıklama", project.description or "-"),
            ("Katılımcı", str(counts["participants"])),
            ("Kayıt", str(counts["takes"])),
            ("Kayıt Planı", str(len(project.protocols))),
        ]
        if self.state.current_user and self.state.current_user.is_owner:
            items.append(("Klasör", str(workspace.root)))
        self._details.set_items(items)
        self._plans.blockSignals(True)
        self._plans.clear()
        for plan in project.protocols:
            self._plans.addItem(plan.name, plan.protocol_id)
        if not project.protocols:
            self._plans.addItem("Kayıt Planı yok — serbest kayıt", None)
        self._plans.blockSignals(False)
        self._reload_tasks()

    def _current_plan(self) -> Optional[CaptureProtocol]:
        workspace = self.state.workspace
        plan_id = self._plans.currentData()
        return workspace.project.protocol_by_id(plan_id) if workspace and plan_id else None

    def _reload_tasks(self) -> None:
        self._tasks.clear()
        plan = self._current_plan()
        if plan is None:
            item = QListWidgetItem("Hareket listesi yok; serbest kayıt kullanılacak.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._tasks.addItem(item)
            return
        for index, task in enumerate(plan.tasks, start=1):
            item = QListWidgetItem(f"{index}. {task.display_label}")
            item.setData(Qt.ItemDataRole.UserRole, task.task_id)
            self._tasks.addItem(item)

    def _create_project(self) -> None:
        dialog = NewProjectDialog(self.theme, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            workspace = self.state.create_project(
                dialog.project_name, dialog.project_description
            )
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(f"Proje oluşturuldu: {workspace.project.name}")
        self.navigate_requested.emit("participants")

    def _open_selected(self) -> None:
        item = self._list.currentItem()
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not path:
            return
        try:
            workspace = self.state.open_project(Path(str(path)))
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify(f"Proje açıldı: {workspace.project.name}")
        self.navigate_requested.emit("participants")

    def _import_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "KineCapture proje klasörü", str(self.state.config.dataset_root)
        )
        if not directory:
            return
        try:
            self.state.import_project(Path(directory))
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self.state.notify("Proje erişim sistemine kaydedildi.")
        self.navigate_requested.emit("participants")

    def _change_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Yeni projelerin veri klasörü", str(self.state.config.dataset_root)
        )
        if directory:
            self.state.config.dataset_root = Path(directory)
            self.state.save_preferences()
            self.state.notify("Yeni proje veri klasörü güncellendi.")

    def _add_plan(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        dialog = RecordingPlanDialog(self.theme, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        workspace.project.protocols.append(dialog.build())
        try:
            self.state.save_project()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._refresh_details()

    def _edit_plan(self) -> None:
        plan = self._current_plan()
        if plan is None:
            return
        dialog = RecordingPlanDialog(self.theme, plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.build()
        try:
            self.state.save_project()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._refresh_details()

    def _edit_target(self) -> None:
        plan = self._current_plan()
        item = self._tasks.currentItem()
        if plan is None or item is None:
            return
        task = plan.task_by_id(str(item.data(Qt.ItemDataRole.UserRole)))
        if task is None:
            return
        dialog = AdvancedTargetDialog(self.theme, task, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.apply()
        try:
            self.state.save_project()
        except KineCaptureError as exc:
            self.state.report_error(exc)
            return
        self._reload_tasks()


__all__ = ["NewProjectDialog", "ProjectsPage", "RecordingPlanDialog"]
