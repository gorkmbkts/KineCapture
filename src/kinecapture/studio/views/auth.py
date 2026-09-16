"""The sign-in gate shown before the shell.

One narrow centred column, scrollable, so the form still fits on a 700-pixel
screen. Passwords are never pre-filled and never remembered; the username is,
because typing it again every morning is friction with nothing behind it.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kinecapture.studio.services.messages import Message
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.auth import AuthMode, AuthState, AuthViewModel

from .qt_bridge import BoundView
from .brand import CREST_NAME, crest_pixmap
from .widgets import ElidedLabel, MessageBar, label, separator

#: How big the crest is on the sign-in screen. Large enough to be the first
#: thing read, small enough to leave the form above the fold on a 700px window.
CREST_SIZE = 168


_TITLES = {
    AuthMode.SETUP: ("Kuruluma hoş geldiniz", "Sistem Sahibi hesabını oluşturun"),
    AuthMode.SIGN_IN: ("KineCapture Studio", "Devam etmek için giriş yapın"),
    AuthMode.REGISTER: ("Yeni kullanıcı", "Kendi hesabınızı oluşturun"),
    AuthMode.CHANGE_PASSWORD: ("Parola değiştirin", "Geçici parolayla devam edilemez"),
}


class AuthView(QWidget, BoundView):
    """Drives :class:`AuthViewModel`; owns no state of its own."""

    def __init__(
        self,
        viewmodel: AuthViewModel,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        QWidget.__init__(self, parent)
        BoundView.__init__(self)
        self.viewmodel = viewmodel
        self._tokens = tokens

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.addStretch(1)
        column = QWidget()
        column.setMinimumWidth(360)
        column.setMaximumWidth(520)
        holder_layout.addWidget(column)
        holder_layout.addStretch(1)
        scroll.setWidget(holder)

        self._column = QVBoxLayout(column)
        margin = tokens.metric("KcSpacingXxl")
        self._column.setContentsMargins(margin, margin, margin, margin)
        self._column.setSpacing(tokens.metric("KcSpacingLg"))
        # Centred rather than pinned to the top: on a maximised window the card
        # otherwise sits in the corner of a very large empty rectangle. The
        # stretches collapse on a short window and the area scrolls instead.
        self._column.addStretch(1)

        # The crest leads the sign-in screen. This is the one place in the
        # product where the institution, not the task, is the first thing on
        # screen - so it is given real size and real room around it.
        self.crest = QLabel()
        self.crest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crest.setAccessibleName(CREST_NAME)
        self.crest.setToolTip(CREST_NAME)
        self._column.addWidget(self.crest, 0, Qt.AlignmentFlag.AlignHCenter)
        self.institution = label(CREST_NAME, role="section")
        self.institution.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._column.addWidget(self.institution)
        self._column.addSpacing(tokens.metric("KcSpacingXl"))

        self.title = label("", role="pageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = ElidedLabel("")
        self.subtitle.setProperty("kcRole", "pageSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.messages = MessageBar(tokens, self)
        self._column.addWidget(self.title)
        self._column.addWidget(self.subtitle)
        self._column.addSpacing(tokens.metric("KcSpacingMd"))
        self._column.addWidget(self.messages)
        self._column.addWidget(separator())
        self._column.addSpacing(tokens.metric("KcSpacingMd"))
        self._show_crest()

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setHorizontalSpacing(tokens.metric("KcSpacingXl"))
        self.form.setVerticalSpacing(tokens.metric("KcSpacingLg"))
        self.form.setContentsMargins(0, tokens.metric("KcSpacingMd"), 0, 0)
        self._column.addLayout(self.form)

        self.problem = label("", role="sectionTitle")
        self.problem.setProperty("kcStatus", "error")
        self.problem.setWordWrap(True)
        self.problem.hide()
        self._column.addWidget(self.problem)

        buttons = QHBoxLayout()
        self.secondary = QPushButton("")
        self.secondary.setProperty("kcVariant", "quiet")
        self.primary = QPushButton("")
        self.primary.setProperty("kcVariant", "primary")
        self.primary.setDefault(True)
        buttons.addWidget(self.secondary)
        buttons.addStretch(1)
        buttons.addWidget(self.primary)
        self._column.addSpacing(tokens.metric("KcSpacingLg"))
        self._column.addLayout(buttons)
        self._column.addStretch(1)

        self._edits: dict[str, QLineEdit] = {}
        self.primary.clicked.connect(self._submit)
        self.secondary.clicked.connect(self._switch)

        self.bind(viewmodel.state, self._render)
        self.bind_event(viewmodel.message, self.messages.show_message)

    def apply_tokens(self, tokens: ThemeTokens) -> None:
        """The gate is outside the shell's pages, so it is themed separately."""
        self._tokens = tokens
        self.messages.set_tokens(tokens)
        self._show_crest()

    def _show_crest(self) -> None:
        """Draw the crest for the current theme, or leave the space empty.

        A decoration that will not load must never be the reason somebody
        cannot sign in, so a missing crest simply hides itself.
        """
        pixmap = crest_pixmap(
            self._tokens, size=CREST_SIZE, ratio=self.devicePixelRatioF()
        )
        if pixmap is None:
            self.crest.hide()
            return
        self.crest.setPixmap(pixmap)
        self.crest.setFixedSize(pixmap.size() / pixmap.devicePixelRatio())
        self.crest.show()

    # ---------------------------------------------------------------- render
    def _render(self, state: AuthState) -> None:
        title, subtitle = _TITLES[state.mode]
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self._rebuild_form(state.mode)
        self.primary.setText(
            {
                AuthMode.SETUP: "Hesabı oluştur ve gir",
                AuthMode.SIGN_IN: "Giriş yap",
                AuthMode.REGISTER: "Hesap oluştur",
                AuthMode.CHANGE_PASSWORD: "Parolayı değiştir",
            }[state.mode]
        )
        self.secondary.setText(
            {
                AuthMode.SIGN_IN: "Yeni kullanıcı oluştur",
                AuthMode.REGISTER: "Girişe dön",
            }.get(state.mode, "")
        )
        self.secondary.setVisible(bool(self.secondary.text()))
        self.primary.setEnabled(not state.busy)
        form_problem = state.problem_for("form")
        self.problem.setText(form_problem)
        self.problem.setVisible(bool(form_problem))
        for name, edit in self._edits.items():
            message = state.problem_for(name)
            edit.setToolTip(message or "")
            edit.setProperty("kcStatus", "error" if message else "")

    def _rebuild_form(self, mode: AuthMode) -> None:
        wanted = {
            AuthMode.SIGN_IN: (
                ("username", "Kullanıcı adı", False),
                ("password", "Parola", True),
            ),
            AuthMode.SETUP: (
                ("first_name", "Ad", False),
                ("last_name", "Soyad", False),
                ("title", "Unvan (isteğe bağlı)", False),
                ("username", "Kullanıcı adı", False),
                ("password", "Parola", True),
                ("password_confirm", "Parola (tekrar)", True),
            ),
            AuthMode.REGISTER: (
                ("first_name", "Ad", False),
                ("last_name", "Soyad", False),
                ("title", "Unvan (isteğe bağlı)", False),
                ("username", "Kullanıcı adı", False),
                ("password", "Parola", True),
                ("password_confirm", "Parola (tekrar)", True),
            ),
            AuthMode.CHANGE_PASSWORD: (
                ("current_password", "Mevcut parola", True),
                ("password", "Yeni parola", True),
                ("password_confirm", "Yeni parola (tekrar)", True),
            ),
        }[mode]
        if tuple(self._edits) == tuple(name for name, _c, _s in wanted):
            return
        while self.form.rowCount():
            self.form.removeRow(0)
        self._edits.clear()
        previous: Optional[QLineEdit] = None
        for name, caption, secret in wanted:
            edit = QLineEdit()
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            else:
                edit.setClearButtonEnabled(True)
            edit.setAccessibleName(caption)
            edit.returnPressed.connect(self._submit)
            self.form.addRow(caption, edit)
            self._edits[name] = edit
            if previous is not None:
                self.setTabOrder(previous, edit)
            previous = edit
        if "username" in self._edits and self.viewmodel.remembered_username:
            self._edits["username"].setText(self.viewmodel.remembered_username)
        first = next(iter(self._edits.values()), None)
        if first is not None:
            first.setFocus()

    # ---------------------------------------------------------------- actions
    def _values(self) -> dict[str, str]:
        return {name: edit.text() for name, edit in self._edits.items()}

    def _submit(self) -> None:
        values = self._values()
        mode = self.viewmodel.mode
        if mode is AuthMode.SIGN_IN:
            self.viewmodel.sign_in(values.get("username", ""), values.get("password", ""))
        elif mode is AuthMode.SETUP:
            self.viewmodel.create_owner(**values)
        elif mode is AuthMode.REGISTER:
            self.viewmodel.register(**values)
        else:
            self.viewmodel.change_password(
                values.get("current_password", ""),
                values.get("password", ""),
                values.get("password_confirm", ""),
            )
        # Passwords are cleared from the widgets as soon as they are used, so a
        # form left open on a shared machine holds nothing.
        for name, edit in self._edits.items():
            if "password" in name:
                edit.clear()

    def _switch(self) -> None:
        self.viewmodel.set_mode(
            AuthMode.SIGN_IN
            if self.viewmodel.mode is AuthMode.REGISTER
            else AuthMode.REGISTER
        )

    def show_message(self, message: Message) -> None:
        self.messages.show_message(message)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self.unbind_all()
        super().closeEvent(event)


__all__ = ["AuthView"]
