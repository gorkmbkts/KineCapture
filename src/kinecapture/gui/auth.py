"""First setup, login, self-registration and password-change forms."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kinecapture import APP_NAME
from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.gui.state import AppState
from kinecapture.gui.theme import Theme
from kinecapture.gui.widgets.common import Card, FieldRow, make_button, make_label
from kinecapture.identity.models import User


class AccountFields(QWidget):
    """Shared profile/password fields with field-local errors."""

    def __init__(
        self,
        theme: Theme,
        *,
        include_password: bool = True,
        user: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.space_sm)
        self.rows: dict[str, FieldRow] = {}

        for key, label, value, required in (
            ("first_name", "Ad", user.first_name if user else "", True),
            ("last_name", "Soyad", user.last_name if user else "", True),
            ("title", "Unvan", user.title if user else "", False),
            ("username", "Kullanıcı adı", user.username if user else "", True),
        ):
            field = QLineEdit(value)
            if key == "username":
                field.setPlaceholderText("Harf, rakam, nokta, _ veya -")
            row = FieldRow(label, field, theme=theme, required=required)
            self.rows[key] = row
            layout.addWidget(row)

        self.password: Optional[QLineEdit] = None
        self.password_confirmation: Optional[QLineEdit] = None
        if include_password:
            self.password = QLineEdit()
            self.password.setEchoMode(QLineEdit.EchoMode.Password)
            self.password.setPlaceholderText("En az 8 karakter")
            self.rows["password"] = FieldRow(
                "Şifre", self.password, theme=theme, required=True
            )
            layout.addWidget(self.rows["password"])
            self.password_confirmation = QLineEdit()
            self.password_confirmation.setEchoMode(QLineEdit.EchoMode.Password)
            self.rows["password_confirmation"] = FieldRow(
                "Şifre tekrar", self.password_confirmation, theme=theme, required=True
            )
            layout.addWidget(self.rows["password_confirmation"])

    def line(self, key: str) -> QLineEdit:
        return self.rows[key].field  # type: ignore[return-value]

    def clear_errors(self) -> None:
        for row in self.rows.values():
            row.clear_error()

    def validate(self) -> bool:
        self.clear_errors()
        valid = True
        for key in ("first_name", "last_name", "username"):
            if not self.line(key).text().strip():
                self.rows[key].set_error("Bu alan zorunludur.")
                valid = False
        if self.password is not None and self.password_confirmation is not None:
            if len(self.password.text()) < 8:
                self.rows["password"].set_error("Şifre en az 8 karakter olmalıdır.")
                valid = False
            if self.password.text() != self.password_confirmation.text():
                self.rows["password_confirmation"].set_error("Şifreler eşleşmiyor.")
                valid = False
        return valid

    def values(self) -> dict[str, str]:
        result = {
            "first_name": self.line("first_name").text().strip(),
            "last_name": self.line("last_name").text().strip(),
            "title": self.line("title").text().strip(),
            "username": self.line("username").text().strip(),
        }
        if self.password is not None:
            result["password"] = self.password.text()
        return result

    def show_error(self, error: KineCaptureError) -> None:
        field = getattr(error, "field", "")
        row = self.rows.get(field)
        if row is not None:
            row.set_error(error.user_text())

    def clear_passwords(self) -> None:
        if self.password is not None:
            self.password.clear()
        if self.password_confirmation is not None:
            self.password_confirmation.clear()


class RegistrationDialog(QDialog):
    """Creates a normal user; it never exposes a role control."""

    def __init__(
        self,
        state: AppState,
        *,
        actor: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.actor = actor
        self.created_user: Optional[User] = None
        self.setWindowTitle("Yeni Kullanıcı Oluştur")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        self.fields = AccountFields(state.theme)
        layout.addWidget(self.fields)
        self._error = make_label("", role="error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Hesap Oluştur")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._create)
        layout.addWidget(buttons)

    def _create(self) -> None:
        if not self.fields.validate():
            return
        try:
            if self.actor is None:
                user = self.state.identity.self_register(**self.fields.values())
            else:
                user = self.state.identity.create_user(
                    self.actor, **self.fields.values()
                )
        except KineCaptureError as exc:
            self.fields.show_error(exc)
            self._error.setText(exc.user_text())
            self._error.setVisible(True)
            self.fields.clear_passwords()
            return
        self.created_user = user
        self.fields.clear_passwords()
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(
        self,
        state: AppState,
        user: User,
        *,
        current_password: str = "",
        forced: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.user = user
        self.updated_user: Optional[User] = None
        self.setWindowTitle("Şifre Değiştir")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        if forced:
            note = make_label(
                "Geçici şifrenizi değiştirmeden çalışma alanına geçemezsiniz.",
                role="subtitle",
            )
            note.setWordWrap(True)
            layout.addWidget(note)
        self._current = QLineEdit(current_password)
        self._current.setEchoMode(QLineEdit.EchoMode.Password)
        self._current_row = FieldRow(
            "Mevcut şifre", self._current, theme=state.theme, required=True
        )
        layout.addWidget(self._current_row)
        self._new = QLineEdit()
        self._new.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_row = FieldRow("Yeni şifre", self._new, theme=state.theme, required=True)
        layout.addWidget(self._new_row)
        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_row = FieldRow(
            "Yeni şifre tekrar", self._confirm, theme=state.theme, required=True
        )
        layout.addWidget(self._confirm_row)
        self._error = make_label("", role="error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        layout.addWidget(self._error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | (QDialogButtonBox.StandardButton.Cancel if not forced else QDialogButtonBox.StandardButton.NoButton)
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Şifreyi Değiştir")
        if not forced:
            buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Vazgeç")
            buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._change)
        layout.addWidget(buttons)

    def _change(self) -> None:
        self._current_row.clear_error()
        self._new_row.clear_error()
        self._confirm_row.clear_error()
        if not self._current.text():
            self._current_row.set_error("Mevcut şifre zorunludur.")
            return
        if len(self._new.text()) < 8:
            self._new_row.set_error("Şifre en az 8 karakter olmalıdır.")
            return
        if self._new.text() != self._confirm.text():
            self._confirm_row.set_error("Şifreler eşleşmiyor.")
            return
        try:
            self.updated_user = self.state.identity.change_password(
                self.user,
                current_password=self._current.text(),
                new_password=self._new.text(),
            )
        except KineCaptureError as exc:
            self._error.setText(exc.user_text())
            self._error.setVisible(True)
            self._new.clear()
            self._confirm.clear()
            return
        self._current.clear()
        self._new.clear()
        self._confirm.clear()
        self.accept()


class AuthPage(QWidget):
    """Full-window gate shown until a verified user context exists."""

    authenticated = Signal(object)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = state
        outer = QHBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 32)
        outer.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(540)
        layout = QVBoxLayout(column)
        layout.addStretch(1)
        brand = make_label(APP_NAME, role="metric")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)
        self._stack = QStackedWidget()
        self._setup = self._build_setup(state.theme)
        self._login = self._build_login(state.theme)
        self._stack.addWidget(self._setup)
        self._stack.addWidget(self._login)
        layout.addWidget(self._stack)
        layout.addStretch(1)
        outer.addWidget(column, 1)
        outer.addStretch(1)
        self.refresh_mode()

    def refresh_mode(self) -> None:
        self._stack.setCurrentWidget(
            self._setup if self.state.identity.needs_initial_setup else self._login
        )
        if not self.state.identity.needs_initial_setup:
            self._username.setText(self.state.config.last_username)
            self._username.setFocus()

    def _build_setup(self, theme: Theme) -> QWidget:
        card = Card(
            "İlk Kurulum — Sistem Sahibi Hesabı",
            subtitle="Bu hesap sistemdeki tek yönetici hesabıdır.",
            theme=theme,
        )
        self._setup_fields = AccountFields(theme)
        card.add_widget(self._setup_fields)
        self._setup_error = make_label("", role="error")
        self._setup_error.setWordWrap(True)
        self._setup_error.setVisible(False)
        card.add_widget(self._setup_error)
        button = make_button(
            "Sistem Sahibi Hesabını Oluştur", variant="primary", theme=theme
        )
        button.clicked.connect(self._create_owner)
        card.add_widget(button)
        return card

    def _build_login(self, theme: Theme) -> QWidget:
        card = Card("Oturum Aç", theme=theme)
        self._username = QLineEdit()
        self._username_row = FieldRow(
            "Kullanıcı adı", self._username, theme=theme, required=True
        )
        card.add_widget(self._username_row)
        password_container = QWidget()
        row = QHBoxLayout(password_container)
        row.setContentsMargins(0, 0, 0, 0)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(self._password, 1)
        self._show_password = QCheckBox("Göster")
        self._show_password.toggled.connect(
            lambda shown: self._password.setEchoMode(
                QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(self._show_password)
        self._password_row = FieldRow(
            "Şifre", password_container, theme=theme, required=True
        )
        card.add_widget(self._password_row)
        self._login_error = make_label("", role="error")
        self._login_error.setWordWrap(True)
        self._login_error.setVisible(False)
        card.add_widget(self._login_error)
        login = make_button("Oturum Aç", variant="primary", theme=theme)
        login.clicked.connect(self._attempt_login)
        card.add_widget(login)
        bottom = QHBoxLayout()
        bottom.addWidget(make_label("Yeni misiniz?", role="muted"))
        register = make_button("Yeni Kullanıcı Oluştur", theme=theme)
        register.clicked.connect(self._register)
        bottom.addWidget(register)
        bottom.addStretch(1)
        container = QWidget()
        container.setLayout(bottom)
        card.add_widget(container)
        self._username.returnPressed.connect(self._attempt_login)
        self._password.returnPressed.connect(self._attempt_login)
        return card

    def _create_owner(self) -> None:
        if not self._setup_fields.validate():
            return
        try:
            user = self.state.identity.create_initial_owner(
                **self._setup_fields.values()
            )
        except KineCaptureError as exc:
            self._setup_fields.show_error(exc)
            self._setup_error.setText(exc.user_text())
            self._setup_error.setVisible(True)
            self._setup_fields.clear_passwords()
            return
        self._setup_fields.clear_passwords()
        self.state.activate_user(user)
        self.authenticated.emit(user)

    def _attempt_login(self) -> None:
        self._username_row.clear_error()
        self._password_row.clear_error()
        self._login_error.setVisible(False)
        if not self._username.text().strip():
            self._username_row.set_error("Kullanıcı adı zorunludur.")
            return
        if not self._password.text():
            self._password_row.set_error("Şifre zorunludur.")
            return
        password = self._password.text()
        try:
            user = self.state.authenticate(self._username.text(), password)
            if user.must_change_password:
                dialog = ChangePasswordDialog(
                    self.state,
                    user,
                    current_password=password,
                    forced=True,
                    parent=self,
                )
                password = ""
                self._password.clear()
                if dialog.exec() != QDialog.DialogCode.Accepted or dialog.updated_user is None:
                    return
                user = dialog.updated_user
            self.state.activate_user(user)
        except KineCaptureError as exc:
            self._login_error.setText(exc.user_text())
            self._login_error.setVisible(True)
            self._password.clear()
            password = ""
            return
        self._password.clear()
        password = ""
        self.authenticated.emit(user)

    def _register(self) -> None:
        dialog = RegistrationDialog(self.state, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.created_user is None:
            return
        self._username.setText(dialog.created_user.username)
        self._password.clear()
        self._username.setFocus()
        self._login_error.setText("Hesabınız oluşturuldu. Şifrenizle oturum açabilirsiniz.")
        self._login_error.setProperty("role", "success")
        self._login_error.setVisible(True)

    def apply_theme(self, theme: Theme) -> None:
        for child in self.findChildren(QWidget):
            handler = getattr(child, "apply_theme", None)
            if callable(handler) and child is not self:
                handler(theme)


__all__ = [
    "AccountFields",
    "AuthPage",
    "ChangePasswordDialog",
    "RegistrationDialog",
]
