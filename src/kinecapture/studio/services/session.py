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


@dataclass(frozen=True)
class WorkTarget:
    """Who the next recording belongs to.

    One value, resolved from one place. The 15 September audit found a take
    started with P0002 selected landing under P0001, because the Capture
    screen took ``participants[0]`` while the Projects screen held a different
    selection - two answers to the same question.

    ``participant_code`` is the anonymous project code (P0001), which is the
    owner of the data. It is **not** the person picked out of the camera
    image; that is a separate choice made on the preview.
    """

    project_name: str = ""
    participant_id: str = ""
    participant_code: str = ""
    session_id: str = ""
    session_started_at: str = ""
    #: True when a session already exists; otherwise one is created on start.
    session_open: bool = False

    @property
    def is_set(self) -> bool:
        return bool(self.participant_id)

    @property
    def text(self) -> str:
        """Short enough for the recording strip: who, and nothing else.

        The session id used to be appended in truncated form, which produced
        things like "P0001 · 0_l" - a fragment that identifies nothing. The
        full session belongs in :attr:`detail`, where there is room for it.
        """
        return self.participant_code if self.is_set else "Hedef seçilmedi"

    @property
    def detail(self) -> str:
        """The long form, for a tooltip."""
        if not self.is_set:
            return "Kayıt hedefi seçilmedi."
        session = self.session_id or "kayda başlayınca yeni oturum açılır"
        return f"{self.project_name} · {self.participant_code} · {session}"


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
    #: The participant every screen means when it says "the current one".
    #: Set from Projects or from Capture; read by both.
    selected_participant_id: str = ""
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
        self.selected_participant_id = ""

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
        self.selected_participant_id = ""
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
        # A participant belongs to one project; carrying the old id across
        # would let the next recording quietly aim at a project nobody has
        # open any more.
        self.selected_participant_id = ""
        self.config.last_project_path = access.path
        self._remember_preferences()
        self._changed()
        return workspace

    def close_project(self) -> None:
        self.workspace = None
        self.access = None
        self.selected_participant_id = ""
        self._changed()

    # ----------------------------------------------------------- work target
    def select_participant(self, participant_id: str) -> bool:
        """Say who the work is about. Returns whether it changed."""
        clean = str(participant_id or "")
        if clean == self.selected_participant_id:
            return False
        self.selected_participant_id = clean
        self._changed()
        return True

    def target(self) -> WorkTarget:
        """Resolve the selection against what is actually on disk.

        Reads the workspace rather than trusting a cached row: a participant
        that has been removed, or a project that was swapped underneath, must
        come back as "no target" rather than as a stale name.
        """
        workspace = self.workspace
        if workspace is None:
            return WorkTarget()
        name = self.access.name if self.access else ""
        try:
            participants = list(workspace.list_participants())
        except Exception as exc:  # noqa: BLE001 - a listing failure is not fatal
            logger.warning("Katılımcılar okunamadı: %s", exc)
            return WorkTarget(project_name=name)
        chosen = next(
            (p for p in participants if p.participant_id == self.selected_participant_id),
            None,
        )
        if chosen is None:
            return WorkTarget(project_name=name)
        try:
            open_sessions = [
                s
                for s in workspace.list_sessions(chosen.participant_id)
                if not s.ended_at
            ]
        except Exception as exc:  # noqa: BLE001 - see above
            logger.warning("Oturumlar okunamadı: %s", exc)
            open_sessions = []
        session = open_sessions[0] if open_sessions else None
        return WorkTarget(
            project_name=name,
            participant_id=chosen.participant_id,
            participant_code=chosen.code,
            session_id=session.session_id if session else "",
            session_started_at=session.started_at if session else "",
            session_open=session is not None,
        )

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


__all__ = ["ContextSnapshot", "ContextState", "SessionService", "WorkTarget"]
