"""Who is signed in, which project is open, and what the shell should say.

This is the Studio's single entry point to identity and to the project on disk.
Views never touch :class:`IdentityService` or :class:`ProjectWorkspace`
directly; they ask a viewmodel, which asks this.

No Qt import. Change notification is a plain callback list - the Qt adapter in
``views/qt_bridge.py`` turns it into signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from kinecapture.core.config import AppConfig, save_user_state
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.identity.database import IdentityDatabase
from kinecapture.identity.models import ProjectAccess, User
from kinecapture.identity.service import IdentityService

from .context import (
    ContextSnapshot,
    ContextState,
    data_root_item,
    disk_item,
    simple_item,
)

logger = logging.getLogger(__name__)

Listener = Callable[[], None]


@dataclass
class SessionService:
    """The signed-in user and the open project, and nothing else.

    Deliberately small. Capture, processing and review each get their own
    service; putting them here would recreate the god-object the old
    ``gui/state.py`` grew into.
    """

    config: AppConfig
    identity: IdentityService
    user: Optional[User] = None
    workspace: Optional[ProjectWorkspace] = None
    access: Optional[ProjectAccess] = None
    _listeners: list[Listener] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------- lifecycle
    @classmethod
    def open(cls, config: AppConfig) -> "SessionService":
        database = IdentityDatabase(config.identity_db_path)
        database.initialize()
        return cls(config=config, identity=IdentityService(database))

    def close(self) -> None:
        self.user = None
        self.workspace = None
        self.access = None

    # ---------------------------------------------------------- notification
    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _changed(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ---------------------------------------------------------------- access
    @property
    def is_authenticated(self) -> bool:
        return self.user is not None and not self.user.must_change_password

    @property
    def needs_initial_setup(self) -> bool:
        return self.identity.needs_initial_setup

    def sign_in(self, username: str, password: str) -> User:
        """Authenticate. The password is never stored, logged or remembered."""
        user = self.identity.authenticate(username, password)
        self.user = user
        self.config.last_username = user.username
        self._remember_preferences()
        self._changed()
        return user

    def sign_out(self) -> None:
        self.user = None
        self.workspace = None
        self.access = None
        self._changed()

    def projects(self) -> list[ProjectAccess]:
        if self.user is None:
            return []
        return self.identity.list_projects(self.user)

    def open_project(self, project_id: str) -> ProjectWorkspace:
        if self.user is None:
            raise PermissionError("Proje açmadan önce giriş yapılmalıdır.")
        access = self.identity.authorize_project(self.user, project_id)
        workspace = ProjectWorkspace.open(access.path)
        self.workspace = workspace
        self.access = access
        self.config.last_project_path = access.path
        self._remember_preferences()
        self._changed()
        return workspace

    def close_project(self) -> None:
        self.workspace = None
        self.access = None
        self._changed()

    # ------------------------------------------------------------- settings
    def set_theme(self, theme: str) -> None:
        self.config.theme = theme
        self._remember_preferences()
        self._changed()

    def _remember_preferences(self) -> None:
        """Persist preferences, never blocking the caller on a failure.

        A preference file that cannot be written is an inconvenience; refusing
        to sign the user in because of it would not be.
        """
        try:
            save_user_state(self.config)
        except Exception as exc:  # noqa: BLE001 - see docstring
            logger.warning("Kullanıcı tercihleri yazılamadı: %s", exc)

    # -------------------------------------------------------------- context
    def context(self) -> ContextSnapshot:
        """One reading for the context bar. Cheap enough to call a few times a second."""
        user = self.user
        access = self.access
        root: Optional[Path] = self.config.dataset_root
        items = (
            simple_item(
                "user",
                "Kullanıcı",
                user.full_name if user else None,
                detail=f"@{user.username}" if user else "Giriş yapılmadı",
            ),
            simple_item(
                "project",
                "Proje",
                access.name if access else None,
                detail=str(access.path) if access else "Proje açılmadı",
            ),
            data_root_item(root),
            disk_item(root),
        )
        return ContextSnapshot(items=items)


__all__ = ["ContextSnapshot", "ContextState", "SessionService"]
