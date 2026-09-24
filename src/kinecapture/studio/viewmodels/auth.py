"""Signing in, first-run setup and self-registration.

Passwords pass through here and are never kept: not in an attribute, not in a
preference file, not in a log line. The only thing remembered between runs is
the username, so the field can be pre-filled.

No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from kinecapture.core.errors import KineCaptureError
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable


class AuthMode(str, Enum):
    """Which form is on screen."""

    SETUP = "setup"          # no accounts exist yet
    SIGN_IN = "sign_in"
    REGISTER = "register"
    CHANGE_PASSWORD = "change_password"


@dataclass(frozen=True)
class AuthState:
    mode: AuthMode
    busy: bool = False
    #: Per-field problems, keyed by field name.
    problems: tuple[tuple[str, str], ...] = ()

    def problem_for(self, field: str) -> str:
        return dict(self.problems).get(field, "")


class AuthViewModel:
    """The login gate. Emits ``signed_in`` once, when the shell may be shown."""

    def __init__(self, session: SessionService) -> None:
        self._session = session
        start = AuthMode.SETUP if session.needs_initial_setup else AuthMode.SIGN_IN
        self.state: Observable[AuthState] = Observable(AuthState(mode=start), name="auth")
        self.message: Event[Message] = Event()
        self.signed_in: Event[object] = Event()
        self.remembered_username: str = session.config.last_username or ""
        #: Shown once, when the form first appears: what the installer's owner
        #: seed did (or declined to do) on this start.
        self.startup_notice: Optional[Message] = None
        notice = session.startup_notice
        if notice is not None:
            self.startup_notice = Message(
                headline=notice.headline,
                detail=notice.detail,
                severity=Severity.WARNING if notice.is_warning else Severity.INFO,
                code=f"owner_seed_{notice.outcome.value}",
            )
            if notice.username and not self.remembered_username:
                self.remembered_username = notice.username

    # ------------------------------------------------------------------ mode
    def set_mode(self, mode: AuthMode) -> None:
        if self._session.needs_initial_setup and mode is not AuthMode.SETUP:
            # Nothing else is reachable before the first account exists, and
            # offering it would be a form that can only fail.
            return
        self.state.set(AuthState(mode=mode))

    @property
    def mode(self) -> AuthMode:
        return self.state.value.mode

    # ---------------------------------------------------------------- actions
    def sign_in(self, username: str, password: str) -> bool:
        problems = []
        if not username.strip():
            problems.append(("username", "Kullanıcı adı gerekli."))
        if not password:
            problems.append(("password", "Parola gerekli."))
        if problems:
            self.state.set(AuthState(mode=self.mode, problems=tuple(problems)))
            return False
        return self._attempt(
            lambda: self._session.sign_in(username.strip(), password),
            headline="Giriş yapılamadı.",
        )

    def create_owner(self, **fields: str) -> bool:
        """Create the one System Owner. Only reachable on a fresh install."""
        password = fields.get("password", "")
        confirm = fields.pop("password_confirm", "")
        if password != confirm:
            self.state.set(
                AuthState(
                    mode=self.mode,
                    problems=(("password_confirm", "Parolalar aynı değil."),),
                )
            )
            return False

        def work():
            self._session.identity.create_initial_owner(**fields)
            return self._session.sign_in(fields["username"], password)

        return self._attempt(work, headline="Hesap oluşturulamadı.")

    def register(self, **fields: str) -> bool:
        password = fields.get("password", "")
        confirm = fields.pop("password_confirm", "")
        if password != confirm:
            self.state.set(
                AuthState(
                    mode=self.mode,
                    problems=(("password_confirm", "Parolalar aynı değil."),),
                )
            )
            return False

        def work():
            user = self._session.identity.self_register(**fields)
            # The username is carried to the sign-in form; the password is not,
            # and is not stored anywhere.
            self.remembered_username = user.username
            return None

        created = self._attempt(work, headline="Kayıt tamamlanamadı", sign_in=False)
        if created:
            self.state.set(AuthState(mode=AuthMode.SIGN_IN))
            self.message.emit(
                Message(
                    headline="Hesabınız oluşturuldu. Şimdi giriş yapabilirsiniz.",
                    severity=Severity.INFO,
                )
            )
        return created

    def change_password(self, current: str, new: str, confirm: str) -> bool:
        if new != confirm:
            self.state.set(
                AuthState(
                    mode=self.mode,
                    problems=(("password_confirm", "Parolalar aynı değil."),),
                )
            )
            return False
        user = self._session.user
        if user is None:
            return False

        def work():
            self._session.identity.change_password(
                user, current_password=current, new_password=new
            )
            return self._session.sign_in(user.username, new)

        return self._attempt(work, headline="Parola değiştirilemedi.")

    # --------------------------------------------------------------- internals
    def _attempt(self, work, *, headline: str, sign_in: bool = True) -> bool:  # noqa: ANN001
        self.state.set(AuthState(mode=self.mode, busy=True))
        try:
            result = work()
        except KineCaptureError as exc:
            self.state.set(
                AuthState(mode=self.mode, problems=(("form", str(exc)),))
            )
            # No headline override: this error's own text is already written
            # for the user, and it is more specific than anything generic we
            # would put in front of it.
            self.message.emit(from_error(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - never leave the form stuck busy
            self.state.set(AuthState(mode=self.mode, problems=(("form", str(exc)),)))
            self.message.emit(from_error(exc, headline=headline))
            return False
        self.state.set(AuthState(mode=self.mode))
        if sign_in:
            user = self._session.user
            if user is not None and user.must_change_password:
                self.state.set(AuthState(mode=AuthMode.CHANGE_PASSWORD))
                self.message.emit(
                    Message(
                        headline="Devam etmeden önce parolanızı değiştirin.",
                        severity=Severity.WARNING,
                        detail="Geçici parola yönetici tarafından verilmiştir.",
                    )
                )
                return True
            self.signed_in.emit(result)
        return True


__all__ = ["AuthMode", "AuthState", "AuthViewModel"]
