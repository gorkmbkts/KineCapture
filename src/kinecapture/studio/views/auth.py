"""The sign-in gate shown before the shell.

One centred column on a quiet ground: the crest, the product's name in its own
face, and a form whose boxes all share one width and one centre line. Passwords
are never pre-filled and never remembered; the username is, because typing it
again every morning is friction with nothing behind it.

Two things the 19 September design review asked for, and why they are here.

**The captions live inside the boxes.** A label column beside the fields made
the form lopsided - the boxes started wherever the longest caption ended - and
on a two-field sign-in it bought nothing. The caption is now the placeholder,
which Qt hides while there is text and restores when the box is emptied. The
*accessible* name is set separately and does not move, so a screen reader still
announces "Kullanıcı adı" on a box that is showing what was typed into it.

**Show/hide sits inside the password box.** A checkbox beside it was a second
control competing with the field for the eye, and it pushed the two boxes out
of alignment. As a trailing action it is part of the box it belongs to.

The background is painted once, from tokens, and never animates: this screen is
a door, and a door that moves while you are trying to open it is worse than a
plain one.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import (
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

from . import fonts, iconset
from .qt_bridge import BoundView
from .brand import CREST_NAME, crest_pixmap
from .widgets import ElidedLabel, MessageBar, label

#: The product's own name. The one string on this screen set in the brand face.
WORDMARK = "KineCapture Studio"

#: What each mode is for. The wordmark above is constant, so these are the
#: sentence under it rather than a competing title.
_TITLES = {
    AuthMode.SETUP: ("Kuruluma hoş geldiniz", "Sistem Sahibi hesabını oluşturun"),
    AuthMode.SIGN_IN: ("", "Devam etmek için giriş yapın"),
    AuthMode.REGISTER: ("Yeni kullanıcı", "Kendi hesabınızı oluşturun"),
    AuthMode.CHANGE_PASSWORD: ("Parola değiştirin", "Geçici parolayla devam edilemez"),
}

#: ``(name, caption, is_secret)`` per mode, in tab order.
_FIELDS = {
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
}

_PRIMARY_TEXT = {
    AuthMode.SETUP: "Hesabı oluştur ve gir",
    AuthMode.SIGN_IN: "Giriş yap",
    AuthMode.REGISTER: "Hesap oluştur",
    AuthMode.CHANGE_PASSWORD: "Parolayı değiştir",
}

_SECONDARY_TEXT = {
    AuthMode.SIGN_IN: "Yeni kullanıcı oluştur",
    AuthMode.REGISTER: "Girişe dön",
}


class _Backdrop(QWidget):
    """The quiet ground the column sits on. Painted, never animated.

    A flat rectangle at this size reads as an unfinished page; a moving one
    reads as a screensaver. What is here is a single soft pass of light from
    behind the crest, mixed from the theme's own surfaces, so it costs one
    gradient per repaint and changes with the theme like everything else.
    """

    def __init__(self, tokens: ThemeTokens, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_tokens(self, tokens: ThemeTokens) -> None:
        self._tokens = tokens
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        painter = QPainter(self)
        rect = self.rect()
        tokens = self._tokens
        vertical = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        vertical.setColorAt(0.0, QColor(tokens.colour("KcSurfaceBase")))
        vertical.setColorAt(1.0, QColor(tokens.colour("KcSurfaceSunken")))
        painter.fillRect(rect, vertical)

        # One pool of light where the crest stands, faded out well before the
        # edges so nothing about it reads as a shape.
        centre = rect.center()
        centre.setY(int(rect.height() * 0.32))
        radius = max(rect.width(), rect.height()) * 0.55
        glow = QRadialGradient(centre, radius)
        warm = QColor(tokens.colour("KcAccentMuted"))
        warm.setAlpha(tokens.metric("KcIntervalFillAlphaSelected"))
        glow.setColorAt(0.0, warm)
        faded = QColor(warm)
        faded.setAlpha(0)
        glow.setColorAt(1.0, faded)
        painter.fillRect(rect, glow)
        painter.end()


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
        self._reveal: dict[str, object] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.backdrop = _Backdrop(tokens, self)
        backdrop_layout = QVBoxLayout(self.backdrop)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.backdrop)

        scroll = QScrollArea(self.backdrop)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # The backdrop shows through: a scroll area that paints its own ground
        # would cut a flat rectangle out of the gradient behind it.
        scroll.viewport().setAutoFillBackground(False)
        scroll.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        backdrop_layout.addWidget(scroll)

        holder = QWidget()
        holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        holder_layout = QHBoxLayout(holder)
        holder_layout.addStretch(1)
        column = QWidget()
        column.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # One width for everything in the column, so the crest, the wordmark,
        # the boxes and the button share a centre line and two edges.
        field_width = tokens.metric("KcAuthFieldWidth")
        column.setFixedWidth(field_width)
        holder_layout.addWidget(column)
        holder_layout.addStretch(1)
        scroll.setWidget(holder)

        self._column = QVBoxLayout(column)
        margin = tokens.metric("KcSpacingXxl")
        self._column.setContentsMargins(0, margin, 0, margin)
        self._column.setSpacing(tokens.metric("KcSpacingMd"))
        # Centred rather than pinned to the top: on a maximised window the card
        # otherwise sits in the corner of a very large empty rectangle. The
        # stretches collapse on a short window and the area scrolls instead.
        self._column.addStretch(1)

        # The crest leads the sign-in screen. This is the one place in the
        # product where the institution, not the task, is the first thing on
        # screen - so it is given real size and real room around it. The
        # institution's name is *in* the mark; repeating it underneath was a
        # second, smaller copy of something already being read.
        self.crest = QLabel()
        self.crest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crest.setAccessibleName(CREST_NAME)
        self.crest.setToolTip(CREST_NAME)
        self._column.addWidget(self.crest, 0, Qt.AlignmentFlag.AlignHCenter)
        self._column.addSpacing(tokens.metric("KcSpacingXl"))

        self.wordmark = label(WORDMARK, role="brandMark")
        self.wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wordmark.setAccessibleName(WORDMARK)
        self._column.addWidget(self.wordmark)

        self.title = label("", role="pageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle = ElidedLabel("")
        self.subtitle.setProperty("kcRole", "pageSubtitle")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.messages = MessageBar(tokens, self)
        self._column.addWidget(self.title)
        self._column.addWidget(self.subtitle)
        self._column.addSpacing(tokens.metric("KcSpacingXl"))
        self._column.addWidget(self.messages)
        self._show_crest()

        # A plain column of boxes. Every one is the column's width and the
        # shared control height, so the form is a rectangle rather than a
        # staircase.
        self.form = QVBoxLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(tokens.metric("KcSpacingLg"))
        self._column.addLayout(self.form)

        self.problem = label("", role="fieldError")
        self.problem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.problem.setWordWrap(True)
        self.problem.hide()
        self._column.addSpacing(tokens.metric("KcSpacingMd"))
        self._column.addWidget(self.problem)

        self.primary = QPushButton("")
        self.primary.setProperty("kcVariant", "primary")
        self.primary.setDefault(True)
        self.primary.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
        self._column.addSpacing(tokens.metric("KcSpacingLg"))
        self._column.addWidget(self.primary)

        # A link, not a rival: the second way in is centred under the button
        # rather than beside it, so there is one thing to press and one thing
        # to read.
        self.secondary = QPushButton("")
        self.secondary.setProperty("kcVariant", "quiet")
        self.secondary.setFlat(True)
        self.secondary.setCursor(Qt.CursorShape.PointingHandCursor)
        self._column.addSpacing(tokens.metric("KcSpacingSm"))
        self._column.addWidget(self.secondary, 0, Qt.AlignmentFlag.AlignHCenter)
        self._column.addStretch(1)

        self._edits: dict[str, QLineEdit] = {}
        self.primary.clicked.connect(self._submit)
        self.secondary.clicked.connect(self._switch)

        self.bind(viewmodel.state, self._render)
        self.bind_event(viewmodel.message, self.messages.show_message)
        if viewmodel.startup_notice is not None:
            self.messages.show_message(viewmodel.startup_notice)

    # ---------------------------------------------------------------- theming
    def apply_tokens(self, tokens: ThemeTokens) -> None:
        """The gate is outside the shell's pages, so it is themed separately."""
        self._tokens = tokens
        self.messages.set_tokens(tokens)
        self.backdrop.set_tokens(tokens)
        self._show_crest()
        for name in tuple(self._reveal):
            edit = self._edits.get(name)
            if edit is not None:
                self._retint_reveal(name, edit)

    def _show_crest(self) -> None:
        """Draw the crest for the current theme, or leave the space empty.

        A decoration that will not load must never be the reason somebody
        cannot sign in, so a missing crest simply hides itself.
        """
        pixmap = crest_pixmap(
            self._tokens,
            size=self._tokens.metric("KcCrestSizeAuth"),
            ratio=self.devicePixelRatioF(),
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
        self.title.setVisible(bool(title))
        self.subtitle.setText(subtitle)
        self._rebuild_form(state.mode)
        self.primary.setText(_PRIMARY_TEXT[state.mode])
        self.secondary.setText(_SECONDARY_TEXT.get(state.mode, ""))
        self.secondary.setVisible(bool(self.secondary.text()))
        self.primary.setEnabled(not state.busy)
        form_problem = state.problem_for("form")
        self.problem.setText(form_problem)
        self.problem.setVisible(bool(form_problem))
        for name, edit in self._edits.items():
            message = state.problem_for(name)
            edit.setToolTip(message or "")
            # ``kcState``, which is the property the stylesheet's error rule
            # actually matches. The previous ``kcStatus`` matched nothing, so a
            # rejected field looked exactly like an accepted one.
            edit.setProperty("kcState", "error" if message else "")
            style = edit.style()
            if style is not None:
                style.unpolish(edit)
                style.polish(edit)

    def _rebuild_form(self, mode: AuthMode) -> None:
        wanted = _FIELDS[mode]
        if tuple(self._edits) == tuple(name for name, _c, _s in wanted):
            return
        while self.form.count():
            item = self.form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._edits.clear()
        self._reveal.clear()
        tokens = self._tokens
        previous: Optional[QLineEdit] = None
        for name, caption, secret in wanted:
            edit = QLineEdit()
            # The caption lives in the box. The *name* does not: a screen
            # reader has to keep announcing "Parola" on a box that is showing
            # a password, and a placeholder disappears the moment it is typed
            # into.
            edit.setPlaceholderText(caption)
            edit.setAccessibleName(caption)
            # A floor, not a fixed size. The stylesheet's padding decides the
            # rest, so there is one place that owns the shape of a control;
            # pinning the height here as well produced a widget whose minimum
            # (38, from the sheet) was larger than its maximum (34, from us).
            edit.setMinimumHeight(tokens.metric("KcControlHeightLarge"))
            edit.setClearButtonEnabled(not secret)
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
                self._add_reveal(name, edit)
            edit.returnPressed.connect(self._submit)
            self.form.addWidget(edit)
            self._edits[name] = edit
            if previous is not None:
                self.setTabOrder(previous, edit)
            previous = edit
        if previous is not None:
            self.setTabOrder(previous, self.primary)
            self.setTabOrder(self.primary, self.secondary)
        if "username" in self._edits and self.viewmodel.remembered_username:
            self._edits["username"].setText(self.viewmodel.remembered_username)
        first = next(iter(self._edits.values()), None)
        if first is not None:
            first.setFocus()

    # ----------------------------------------------------------- reveal action
    def _add_reveal(self, name: str, edit: QLineEdit) -> None:
        """Show/hide, inside the box it belongs to."""
        action = edit.addAction(
            self._reveal_icon(shown=False), QLineEdit.ActionPosition.TrailingPosition
        )
        action.setCheckable(True)
        action.setToolTip("Parolayı göster")
        action.setText("Parolayı göster")
        action.toggled.connect(lambda shown, key=name: self._toggle_reveal(key, shown))
        self._reveal[name] = action

    def _reveal_icon(self, *, shown: bool):  # noqa: ANN202 - QIcon
        return iconset.icon(
            "overlay-off" if shown else "overlay-on",
            self._tokens,
            size=self._tokens.metric("KcIconSize"),
            ratio=self.devicePixelRatioF(),
        )

    def _retint_reveal(self, name: str, edit: QLineEdit) -> None:
        action = self._reveal.get(name)
        if action is None:
            return
        shown = edit.echoMode() is QLineEdit.EchoMode.Normal
        action.setIcon(self._reveal_icon(shown=shown))

    def _toggle_reveal(self, name: str, shown: bool) -> None:
        edit = self._edits.get(name)
        action = self._reveal.get(name)
        if edit is None or action is None:
            return
        edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        action.setIcon(self._reveal_icon(shown=shown))
        caption = "Parolayı gizle" if shown else "Parolayı göster"
        action.setToolTip(caption)
        action.setText(caption)

    def password_revealed(self, name: str = "password") -> bool:
        """Whether ``name`` is currently showing its text. For tests."""
        edit = self._edits.get(name)
        return edit is not None and edit.echoMode() is QLineEdit.EchoMode.Normal

    def field(self, name: str) -> Optional[QLineEdit]:
        return self._edits.get(name)

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
        # form left open on a shared machine holds nothing. Clearing also puts
        # the caption back, which is the placeholder doing its job.
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

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        tokens = self._tokens
        return QSize(
            tokens.metric("KcAuthFieldWidth") + tokens.metric("KcSpacingXxl") * 4,
            tokens.metric("KcWindowMinHeight"),
        )

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt naming
        self.unbind_all()
        super().closeEvent(event)


__all__ = ["AuthView", "WORDMARK"]
