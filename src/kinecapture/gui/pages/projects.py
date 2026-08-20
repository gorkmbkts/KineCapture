"""Projects and protocols: create, open, repair, and plan capture."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
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

from kinecapture.core.errors import KineCaptureError, StorageError
from kinecapture.core.jsonio import read_json_mapping
from kinecapture.dataset.workspace import PROJECT_FILE, ProjectWorkspace
from kinecapture.domain.project import CaptureProtocol, ProtocolTask
from kinecapture.gui.pages.base import Page
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import (
    Card,
    FieldRow,
    KeyValueList,
    make_button,
    make_label,
)


class NewProjectDialog(QDialog):
    """Collects the minimum needed to create a project."""

    def __init__(self, theme: Theme, dataset_root: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Yeni proje")
        self.setMinimumWidth(480)
        self._theme = theme

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.space_md)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )

        self._name = QLineEdit()
        self._name.setPlaceholderText("Örn. Diz Rehabilitasyonu Pilot")
        self._name_row = FieldRow("Proje adı", self._name, theme=theme, required=True)
        layout.addWidget(self._name_row)

        self._description = QPlainTextEdit()
        self._description.setPlaceholderText("Kısa açıklama (isteğe bağlı)")
        self._description.setMaximumHeight(72)
        layout.addWidget(
            FieldRow("Açıklama", self._description, theme=theme)
        )

        layout.addWidget(
            make_label(
                f"Proje klasörü: {dataset_root / 'projects'}",
                role="muted",
            )
        )
        layout.addWidget(
            make_label(
                "Katılımcılar varsayılan olarak anonim kodla (P0001) oluşturulur; "
                "kişisel bilgi toplanmaz.",
                role="muted",
            )
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Oluştur")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if not self._name.text().strip():
            self._name_row.set_error("Proje adı zorunludur.")
            return
        self._name_row.clear_error()
        self.accept()

    @property
    def project_name(self) -> str:
        return self._name.text().strip()

    @property
    def project_description(self) -> str:
        return self._description.toPlainText().strip()


class ProtocolTaskDialog(QDialog):
    """Editor for one planned capture task."""

    def __init__(
        self,
        theme: Theme,
        task: Optional[ProtocolTask] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Protokol görevi")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.space_sm)
        layout.setContentsMargins(
            theme.space_lg, theme.space_lg, theme.space_lg, theme.space_lg
        )

        self._exercise = QLineEdit(task.exercise if task else "")
        self._exercise.setPlaceholderText("Örn. squat")
        self._exercise_row = FieldRow(
            "Egzersiz kodu", self._exercise, theme=theme, required=True
        )
        layout.addWidget(self._exercise_row)

        self._label = QLineEdit(task.label if task else "")
        self._label.setPlaceholderText("Ekranda görünecek ad")
        layout.addWidget(FieldRow("Görünen ad", self._label, theme=theme))

        counts = QHBoxLayout()
        self._correct = QSpinBox()
        self._correct.setRange(0, 999)
        self._correct.setValue(task.target_correct_takes if task else 3)
        counts.addWidget(FieldRow("Hedef doğru kayıt", self._correct, theme=theme))
        self._incorrect = QSpinBox()
        self._incorrect.setRange(0, 999)
        self._incorrect.setValue(task.target_incorrect_takes if task else 3)
        counts.addWidget(FieldRow("Hedef hatalı kayıt", self._incorrect, theme=theme))
        self._reps = QSpinBox()
        self._reps.setRange(0, 999)
        self._reps.setValue(task.reps_per_take if task else 5)
        counts.addWidget(FieldRow("Kayıt başına tekrar", self._reps, theme=theme))
        container = QWidget()
        container.setLayout(counts)
        layout.addWidget(container)

        self._side = QComboBox()
        self._side.addItems(["both", "left", "right"])
        if task:
            self._side.setCurrentText(task.side)
        layout.addWidget(FieldRow("Taraf", self._side, theme=theme))

        self._planned_error = QLineEdit(task.planned_error_type if task else "")
        self._planned_error.setPlaceholderText("Planlanan hata türü (isteğe bağlı)")
        layout.addWidget(
            FieldRow("Planlanan hata", self._planned_error, theme=theme)
        )

        self._instruction = QPlainTextEdit(task.operator_instruction if task else "")
        self._instruction.setMaximumHeight(64)
        layout.addWidget(
            FieldRow("Operatör talimatı", self._instruction, theme=theme)
        )

        self._safety = QPlainTextEdit(task.safety_note if task else "")
        self._safety.setMaximumHeight(56)
        layout.addWidget(
            FieldRow(
                "Güvenlik notu",
                self._safety,
                theme=theme,
                help_text="Katılımcıya okunacak güvenlik uyarısı.",
            )
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._task = task

    def _accept(self) -> None:
        if not self._exercise.text().strip():
            self._exercise_row.set_error("Egzersiz kodu zorunludur.")
            return
        self._exercise_row.clear_error()
        self.accept()

    def build_task(self) -> ProtocolTask:
        values = {
            "exercise": self._exercise.text().strip(),
            "label": self._label.text().strip(),
            "target_correct_takes": self._correct.value(),
            "target_incorrect_takes": self._incorrect.value(),
            "reps_per_take": self._reps.value(),
            "side": self._side.currentText(),
            "planned_error_type": self._planned_error.text().strip(),
            "operator_instruction": self._instruction.toPlainText().strip(),
            "safety_note": self._safety.toPlainText().strip(),
        }
        if self._task is not None:
            for key, value in values.items():
                setattr(self._task, key, value)
            return self._task
        return ProtocolTask.create(**values)


class ProjectsPage(Page):
    """Project list, project details and protocol planning."""

    title = "Projeler ve Protokoller"
    description = "Çalışma alanını seçin, çekim planını tanımlayın."
    icon = "project"

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(state, parent)
        theme = self.theme

        new_button = make_button(
            "Yeni proje", variant="primary", icon="add", theme=theme
        )
        new_button.clicked.connect(self._create_project)
        self.header.add_action(new_button)

        open_button = make_button("Klasörden aç", icon="folder-open", theme=theme)
        open_button.clicked.connect(self._browse_project)
        self.header.add_action(open_button)

        columns = QHBoxLayout()
        columns.setSpacing(theme.space_md)
        columns.addWidget(self._build_project_list(theme), 2)
        columns.addWidget(self._build_details(theme), 3)
        self.content.addLayout(columns, 1)

        state.project_changed.connect(lambda _: self._reload())
        state.dataset_changed.connect(self._refresh_details)

    # --------------------------------------------------------------- layout
    def _build_project_list(self, theme: Theme) -> QWidget:
        card = Card(
            "Projeler",
            subtitle=f"Kök klasör: {self.state.config.dataset_root}",
            theme=theme,
            icon="folder-open",
        )
        self._project_list = QListWidget()
        self._project_list.setAlternatingRowColors(True)
        self._project_list.itemDoubleClicked.connect(self._open_selected)
        card.add_widget(self._project_list, 1)

        row = QHBoxLayout()
        open_selected = make_button("Aç", variant="primary", theme=theme)
        open_selected.clicked.connect(
            lambda: self._open_selected(self._project_list.currentItem())
        )
        row.addWidget(open_selected)
        rescan = make_button("Tara", icon="refresh", theme=theme)
        rescan.clicked.connect(self._reload)
        row.addWidget(rescan)
        change_root = make_button("Kök klasörü değiştir", icon="settings", theme=theme)
        change_root.clicked.connect(self._change_root)
        row.addWidget(change_root)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        card.add_widget(container)
        self._list_card = card
        return card

    def _build_details(self, theme: Theme) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_md)

        self._details_card = Card("Proje ayrıntısı", theme=theme, icon="info")
        self._details = KeyValueList(theme)
        self._details_card.add_widget(self._details)
        layout.addWidget(self._details_card)

        self._protocol_card = Card(
            "Çekim protokolü",
            subtitle=(
                "Planlanan görevler capture ekranında sırayla gösterilir. "
                "Protokolsüz serbest kayıt da mümkündür."
            ),
            theme=theme,
            icon="list",
        )
        self._protocol_selector = QComboBox()
        self._protocol_selector.currentIndexChanged.connect(self._protocol_selected)
        self._protocol_card.add_widget(self._protocol_selector)

        self._task_list = QListWidget()
        self._task_list.setAlternatingRowColors(True)
        self._task_list.itemDoubleClicked.connect(lambda _: self._edit_task())
        self._protocol_card.add_widget(self._task_list, 1)

        row = QHBoxLayout()
        for text, icon, handler in (
            ("Protokol ekle", "add", self._add_protocol),
            ("Görev ekle", "add", self._add_task),
            ("Düzenle", "edit", self._edit_task),
            ("Sil", "trash", self._delete_task),
        ):
            button = make_button(text, icon=icon, theme=theme)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        self._protocol_card.add_widget(container)
        layout.addWidget(self._protocol_card, 1)
        return wrapper

    # ----------------------------------------------------------------- data
    def on_activated(self) -> None:
        self._reload()

    def _reload(self) -> None:
        self._project_list.clear()
        root = self.state.config.dataset_root
        self._list_card.set_subtitle(f"Kök klasör: {root}")
        try:
            directories = ProjectWorkspace.discover(root)
        except OSError:
            directories = []

        for directory in directories:
            try:
                payload = read_json_mapping(directory / PROJECT_FILE)
                name = payload.get("name", directory.name)
                created = str(payload.get("created_at", ""))[:10]
            except StorageError:
                name, created = f"{directory.name} (okunamadı)", ""
            item = QListWidgetItem(f"{name}\n{created}  ·  {directory.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(directory))
            self._project_list.addItem(item)
            current = self.state.workspace
            if current is not None and current.root == directory:
                item.setSelected(True)
                self._project_list.setCurrentItem(item)

        if not directories:
            item = QListWidgetItem(
                "Bu klasörde proje yok.\nYeni proje oluşturun veya kök klasörü değiştirin."
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._project_list.addItem(item)

        self._refresh_details()

    def _refresh_details(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            self._details.set_items([("Durum", "Açık proje yok")])
            self._protocol_selector.clear()
            self._task_list.clear()
            self._protocol_card.setEnabled(False)
            return

        self._protocol_card.setEnabled(True)
        project = workspace.project
        counts = workspace.summary_counts()
        schema = workspace.label_schema
        self._details.set_items(
            [
                ("Ad", project.name),
                ("Açıklama", project.description or "-"),
                ("Kimlik", project.project_id),
                ("Klasör", str(workspace.root)),
                ("Oluşturma", project.created_at[:19].replace("T", " ")),
                (
                    "İçerik",
                    f"{counts['participants']} katılımcı · {counts['sessions']} oturum · "
                    f"{counts['takes']} kayıt · {counts['repetitions']} tekrar",
                ),
                (
                    "Varsayılan profil",
                    f"{project.default_capture_profile.resolution} @ "
                    f"{project.default_capture_profile.fps} FPS · "
                    f"{project.default_capture_profile.body_format}",
                ),
                (
                    "Etiket şeması",
                    f"v{schema.schema_version} · "
                    f"{len(schema.exercises)} egzersiz · "
                    f"{len(schema.error_types)} hata türü",
                ),
            ]
        )
        self._reload_protocols()

    def _reload_protocols(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        self._protocol_selector.blockSignals(True)
        self._protocol_selector.clear()
        for protocol in workspace.project.protocols:
            self._protocol_selector.addItem(protocol.name, protocol.protocol_id)
        if not workspace.project.protocols:
            self._protocol_selector.addItem("(protokol tanımlı değil)", None)
        self._protocol_selector.blockSignals(False)
        self._protocol_selected()

    def _current_protocol(self) -> Optional[CaptureProtocol]:
        workspace = self.state.workspace
        if workspace is None:
            return None
        protocol_id = self._protocol_selector.currentData()
        return workspace.project.protocol_by_id(protocol_id) if protocol_id else None

    def _protocol_selected(self) -> None:
        self._task_list.clear()
        protocol = self._current_protocol()
        if protocol is None:
            item = QListWidgetItem("Görev yok. 'Protokol ekle' ile başlayın.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._task_list.addItem(item)
            return
        for position, task in enumerate(protocol.tasks, start=1):
            summary = (
                f"{position}. {task.display_label}  ·  "
                f"{task.target_correct_takes} doğru / {task.target_incorrect_takes} hatalı"
            )
            if task.reps_per_take:
                summary += f"  ·  {task.reps_per_take} tekrar"
            if task.side != "both":
                summary += f"  ·  {task.side}"
            item = QListWidgetItem(summary)
            item.setData(Qt.ItemDataRole.UserRole, task.task_id)
            self._task_list.addItem(item)

    # -------------------------------------------------------------- actions
    def _create_project(self) -> None:
        dialog = NewProjectDialog(self.theme, self.state.config.dataset_root, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.state.create_project(dialog.project_name, dialog.project_description)
            self.state.notify(f"Proje oluşturuldu: {dialog.project_name}")
        except KineCaptureError as exc:
            self.state.report_error(exc)
        self._reload()

    def _browse_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Proje klasörünü seçin",
            str(self.state.config.dataset_root),
        )
        if directory:
            self._open_path(Path(directory))

    def _open_selected(self, item: Optional[QListWidgetItem]) -> None:
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._open_path(Path(path))

    def _open_path(self, path: Path) -> None:
        try:
            workspace = self.state.open_project(path)
            self.state.notify(f"Proje açıldı: {workspace.project.name}")
        except KineCaptureError as exc:
            # A moved or renamed dataset root is the common case; offer the fix
            # rather than only reporting the failure.
            answer = QMessageBox.question(
                self,
                "Proje açılamadı",
                f"{exc.message}\n\n{exc.remedy}\n\nBaşka bir klasör seçmek ister misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._browse_project()
        self._reload()

    def _change_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Dataset kök klasörü", str(self.state.config.dataset_root)
        )
        if not directory:
            return
        self.state.config.dataset_root = Path(directory)
        self.state.save_preferences()
        self.state.notify(f"Kök klasör: {directory}")
        self._reload()

    def _add_protocol(self) -> None:
        workspace = self.state.workspace
        if workspace is None:
            return
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Yeni protokol", "Protokol adı:")
        if not ok or not name.strip():
            return
        protocol = CaptureProtocol.create(name.strip())
        workspace.project.protocols.append(protocol)
        workspace.save_project()
        self._reload_protocols()
        self._protocol_selector.setCurrentIndex(
            self._protocol_selector.count() - 1
        )
        self.state.notify(f"Protokol eklendi: {protocol.name}")

    def _add_task(self) -> None:
        protocol = self._current_protocol()
        workspace = self.state.workspace
        if protocol is None or workspace is None:
            self.state.notify("Önce bir protokol oluşturun.", 5000)
            return
        dialog = ProtocolTaskDialog(self.theme, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        protocol.tasks.append(dialog.build_task())
        workspace.save_project()
        self._protocol_selected()

    def _edit_task(self) -> None:
        protocol = self._current_protocol()
        workspace = self.state.workspace
        item = self._task_list.currentItem()
        if protocol is None or workspace is None or item is None:
            return
        task = protocol.task_by_id(item.data(Qt.ItemDataRole.UserRole))
        if task is None:
            return
        dialog = ProtocolTaskDialog(self.theme, task, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.build_task()
        workspace.save_project()
        self._protocol_selected()

    def _delete_task(self) -> None:
        protocol = self._current_protocol()
        workspace = self.state.workspace
        item = self._task_list.currentItem()
        if protocol is None or workspace is None or item is None:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = protocol.task_by_id(task_id)
        if task is None:
            return
        answer = QMessageBox.question(
            self,
            "Görevi sil",
            f"'{task.display_label}' görevi protokolden kaldırılsın mı?\n"
            "Bu işlem kayıtlı verileri silmez.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        protocol.tasks = [t for t in protocol.tasks if t.task_id != task_id]
        workspace.save_project()
        self._protocol_selected()


__all__ = ["ProjectsPage"]
