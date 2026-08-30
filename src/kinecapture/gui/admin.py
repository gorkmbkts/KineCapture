"""Owner-only user, password-reset and project-access management UI."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kinecapture.core.errors import KineCaptureError
from kinecapture.gui.auth import AccountFields, RegistrationDialog
from kinecapture.gui.state import AppState
from kinecapture.gui.widgets.common import FieldRow, make_button, make_label
from kinecapture.identity.models import ProjectAccess, User, UserRole


class UserProfileDialog(QDialog):
    def __init__(
        self, state: AppState, user: User, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.user = user
        self.updated_user: Optional[User] = None
        self.setWindowTitle("Kullanıcı Bilgilerini Düzenle")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self.fields = AccountFields(state.theme, include_password=False, user=user)
        layout.addWidget(self.fields)
        self._error = make_label("", role="error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        layout.addWidget(buttons)

    def _save(self) -> None:
        if not self.fields.validate():
            return
        actor = self.state.current_user
        if actor is None:
            return
        try:
            self.updated_user = self.state.identity.update_user(
                actor, self.user.user_id, **self.fields.values()
            )
        except KineCaptureError as exc:
            self.fields.show_error(exc)
            self._error.setText(exc.user_text())
            self._error.setVisible(True)
            return
        self.accept()


class PasswordResetDialog(QDialog):
    def __init__(
        self, state: AppState, user: User, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.user = user
        self.setWindowTitle("Geçici Parola Belirle")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        note = make_label(
            f"{user.display_name} bir sonraki girişte bu parolayı değiştirmek zorunda olacak.",
            role="subtitle",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_row = FieldRow(
            "Geçici parola", self._password, theme=state.theme, required=True
        )
        layout.addWidget(self._password_row)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_row = FieldRow(
            "Parola tekrar", self._confirm, theme=state.theme, required=True
        )
        layout.addWidget(self._confirm_row)
        self._error = make_label("", role="error")
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Parolayı Sıfırla")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._reset)
        layout.addWidget(buttons)

    def _reset(self) -> None:
        if len(self._password.text()) < 8:
            self._password_row.set_error("Parola en az 8 karakter olmalıdır.")
            return
        if self._password.text() != self._confirm.text():
            self._confirm_row.set_error("Parolalar eşleşmiyor.")
            return
        actor = self.state.current_user
        if actor is None:
            return
        try:
            self.state.identity.reset_password(
                actor, self.user.user_id, self._password.text()
            )
        except KineCaptureError as exc:
            self._error.setText(exc.user_text())
            self._error.setVisible(True)
            self._password.clear()
            self._confirm.clear()
            return
        self._password.clear()
        self._confirm.clear()
        self.accept()


class ProjectAccessDialog(QDialog):
    def __init__(
        self, state: AppState, user: User, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.user = user
        self.setWindowTitle("Proje Erişimleri")
        self.setMinimumSize(500, 430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = make_label(f"{user.display_name} — erişebildiği projeler", role="section")
        layout.addWidget(title)
        self._list = QListWidget()
        layout.addWidget(self._list, 1)
        actor = state.current_user
        self._projects = state.identity.list_projects(actor) if actor else []
        self._before = state.identity.assigned_project_ids(actor, user.user_id) if actor else set()
        for project in self._projects:
            owned = project.owner_user_id == user.user_id
            item = QListWidgetItem(project.name + ("  ·  sahibi" if owned else ""))
            item.setData(Qt.ItemDataRole.UserRole, project.project_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if user.is_owner or project.project_id in self._before
                else Qt.CheckState.Unchecked
            )
            if user.is_owner or owned:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._list.addItem(item)
        if user.is_owner:
            note = make_label(
                "Sistem Sahibi bütün projelere otomatik erişir; erişimi kısıtlanamaz.",
                role="muted",
            )
            note.setWordWrap(True)
            layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not user.is_owner)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._save)
        layout.addWidget(buttons)

    def _save(self) -> None:
        actor = self.state.current_user
        if actor is None:
            return
        wanted: set[str] = set()
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                wanted.add(str(item.data(Qt.ItemDataRole.UserRole)))
        owned = {p.project_id for p in self._projects if p.owner_user_id == self.user.user_id}
        try:
            for project_id in sorted(wanted - self._before):
                self.state.identity.assign_project(actor, self.user.user_id, project_id)
            for project_id in sorted((self._before - wanted) - owned):
                self.state.identity.remove_project_access(
                    actor, self.user.user_id, project_id
                )
        except KineCaptureError as exc:
            QMessageBox.warning(self, "Erişim güncellenemedi", exc.user_text())
            return
        self.accept()


class ManageUsersDialog(QDialog):
    """Modern owner-only user and access workspace."""

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        actor = state.current_user
        if actor is None:
            raise RuntimeError("authenticated owner required")
        state.identity.require_owner(actor)
        self.setWindowTitle("Kullanıcılar ve Erişimler")
        self.setMinimumSize(1050, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        heading = make_label("Kullanıcılar ve Erişimler", role="metric")
        layout.addWidget(heading)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Ad soyad", "Unvan", "Kullanıcı adı", "Durum", "Proje", "Son giriş"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemDoubleClicked.connect(lambda _: self._edit())
        layout.addWidget(self._table, 1)

        actions = QHBoxLayout()
        for label, handler, primary in (
            ("Yeni kullanıcı", self._new, True),
            ("Bilgileri düzenle", self._edit, False),
            ("Aktif / pasif", self._toggle_active, False),
            ("Parola sıfırla", self._reset_password, False),
            ("Proje erişimleri", self._access, False),
        ):
            button = make_button(
                label, variant="primary" if primary else "", theme=state.theme
            )
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        close = make_button("Kapat", theme=state.theme)
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        container = QWidget()
        container.setLayout(actions)
        layout.addWidget(container)
        self._users: dict[str, User] = {}
        self._reload()

    def _reload(self) -> None:
        actor = self.state.current_user
        if actor is None:
            return
        summaries = self.state.identity.list_users(actor)
        self._users = {summary.user.user_id: summary.user for summary in summaries}
        self._table.setRowCount(len(summaries))
        for row, summary in enumerate(summaries):
            user = summary.user
            role = " · Sistem Sahibi" if user.is_owner else ""
            values = (
                user.display_name + role,
                user.title or "-",
                user.username,
                "Aktif" if user.is_active else "Pasif",
                str(summary.project_count),
                (user.last_login_at or "Henüz giriş yok")[:19].replace("T", " "),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, user.user_id)
                self._table.setItem(row, column, item)
        if summaries:
            self._table.selectRow(0)

    def _selected(self) -> Optional[User]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return self._users.get(str(item.data(Qt.ItemDataRole.UserRole))) if item else None

    def _new(self) -> None:
        actor = self.state.current_user
        if actor is None:
            return
        dialog = RegistrationDialog(self.state, actor=actor, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _edit(self) -> None:
        user = self._selected()
        if user is None:
            return
        dialog = UserProfileDialog(self.state, user, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.state.current_user and user.user_id == self.state.current_user.user_id:
                if dialog.updated_user is not None:
                    self.state.replace_current_user(dialog.updated_user)
            self._reload()

    def _toggle_active(self) -> None:
        user = self._selected()
        actor = self.state.current_user
        if user is None or actor is None:
            return
        try:
            self.state.identity.set_user_active(actor, user.user_id, not user.is_active)
        except KineCaptureError as exc:
            QMessageBox.warning(self, "İşlem reddedildi", exc.user_text())
            return
        self._reload()

    def _reset_password(self) -> None:
        user = self._selected()
        if user is None:
            return
        if PasswordResetDialog(self.state, user, self).exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _access(self) -> None:
        user = self._selected()
        if user is None:
            return
        if ProjectAccessDialog(self.state, user, self).exec() == QDialog.DialogCode.Accepted:
            self._reload()


__all__ = ["ManageUsersDialog", "PasswordResetDialog", "ProjectAccessDialog"]
