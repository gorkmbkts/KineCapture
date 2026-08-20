"""Shared application state.

One :class:`AppState` object owns everything the pages coordinate through: the
open project, the active participant and session, the capture service, and the
dataset index. Pages read it and emit intent; only ``AppState`` mutates it and
announces the result through Qt signals.

That keeps two properties worth having:

* there is exactly one answer to "what is open right now", so two pages can
  never disagree about it;
* a page can be opened, closed and reopened without losing context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from kinecapture.camera import create_backend_from_config
from kinecapture.capture.service import CaptureService
from kinecapture.core.config import AppConfig, save_user_state
from kinecapture.core.errors import KineCaptureError
from kinecapture.core.logging import get_logger
from kinecapture.dataset.index import DatasetIndex
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import BackendKind
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import Participant, Project, Session, Take
from kinecapture.gui.theme import Theme, get_theme

logger = get_logger(__name__)


class AppState(QObject):
    """Mutable application state, with change notification."""

    project_changed = Signal(object)          # ProjectWorkspace | None
    participant_changed = Signal(object)      # Participant | None
    session_changed = Signal(object)          # Session | None
    dataset_changed = Signal()                # index rebuilt
    theme_changed = Signal(object)            # Theme
    backend_changed = Signal(object)          # BackendKind
    error_raised = Signal(object)             # KineCaptureError
    status_message = Signal(str, int)         # text, timeout ms
    take_finalized = Signal(object)           # Take
    review_requested = Signal(object)         # Take

    def __init__(self, config: AppConfig, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self._theme = get_theme(config.theme)
        self._workspace: Optional[ProjectWorkspace] = None
        self._index: Optional[DatasetIndex] = None
        self._participant: Optional[Participant] = None
        self._session: Optional[Session] = None
        self._capture: Optional[CaptureService] = None

    # ---------------------------------------------------------------- theme
    @property
    def theme(self) -> Theme:
        return self._theme

    def set_theme(self, name: str) -> None:
        theme = get_theme(name)
        if theme.name == self._theme.name:
            return
        self._theme = theme
        self.config.theme = theme.name
        self.theme_changed.emit(theme)
        self.save_preferences()

    # -------------------------------------------------------------- project
    @property
    def workspace(self) -> Optional[ProjectWorkspace]:
        return self._workspace

    @property
    def project(self) -> Optional[Project]:
        return self._workspace.project if self._workspace else None

    @property
    def label_schema(self) -> LabelSchema:
        return self._workspace.label_schema if self._workspace else LabelSchema.default()

    @property
    def index(self) -> Optional[DatasetIndex]:
        return self._index

    @property
    def has_project(self) -> bool:
        return self._workspace is not None

    def open_project(self, root: Path) -> ProjectWorkspace:
        """Open a project directory and make it the active one."""
        workspace = ProjectWorkspace.open(Path(root))
        self._workspace = workspace
        self._index = DatasetIndex(workspace).refresh(force=True)
        self._participant = None
        self._session = None
        self.config.last_project_path = workspace.root
        self.save_preferences()
        logger.info("Proje açıldı: %s", workspace.project.name)
        self.project_changed.emit(workspace)
        self.participant_changed.emit(None)
        self.session_changed.emit(None)
        self.dataset_changed.emit()
        return workspace

    def create_project(self, name: str, description: str = "") -> ProjectWorkspace:
        workspace = ProjectWorkspace.create(
            self.config.dataset_root,
            name,
            description=description,
            capture_profile=self.config.capture,
        )
        return self.open_project(workspace.root)

    def close_project(self) -> None:
        self._workspace = None
        self._index = None
        self._participant = None
        self._session = None
        self.project_changed.emit(None)
        self.participant_changed.emit(None)
        self.session_changed.emit(None)
        self.dataset_changed.emit()

    def refresh_dataset(self, *, force: bool = False) -> None:
        """Rebuild the index if the on-disk metadata moved on."""
        if self._index is None:
            return
        self._index.refresh(force=force)
        self.dataset_changed.emit()

    # ---------------------------------------------- participant and session
    @property
    def participant(self) -> Optional[Participant]:
        return self._participant

    def set_participant(self, participant: Optional[Participant]) -> None:
        if participant is not None and self._participant is not None:
            if participant.participant_id == self._participant.participant_id:
                return
        self._participant = participant
        # A session always belongs to a participant; changing one invalidates
        # the other rather than leaving a mismatched pair active.
        if self._session is not None and (
            participant is None
            or self._session.participant_id != participant.participant_id
        ):
            self._session = None
            self.session_changed.emit(None)
        self.participant_changed.emit(participant)

    @property
    def session(self) -> Optional[Session]:
        return self._session

    def set_session(self, session: Optional[Session]) -> None:
        self._session = session
        if session is not None and self._workspace is not None:
            if (
                self._participant is None
                or self._participant.participant_id != session.participant_id
            ):
                try:
                    self._participant = self._workspace.load_participant(
                        session.participant_id
                    )
                    self.participant_changed.emit(self._participant)
                except KineCaptureError as exc:
                    self.report_error(exc)
        self.session_changed.emit(session)

    @property
    def can_capture(self) -> bool:
        return self._workspace is not None and self._session is not None

    # -------------------------------------------------------------- capture
    @property
    def capture(self) -> Optional[CaptureService]:
        return self._capture

    def ensure_capture_service(
        self, kind: Optional[BackendKind] = None
    ) -> CaptureService:
        """Return the capture service, rebuilding it if the backend changed."""
        target = kind or self.config.backend
        if self._capture is not None and self._capture.backend_name == target.value:
            return self._capture
        self.release_capture_service()
        backend = create_backend_from_config(self.config, target)
        self._capture = CaptureService(backend)
        self._capture.add_error_listener(self.report_error)
        self._capture.add_take_listener(self.take_finalized.emit)
        self.config.backend = target
        self.backend_changed.emit(target)
        return self._capture

    def release_capture_service(self) -> None:
        service, self._capture = self._capture, None
        if service is not None:
            service.shutdown()

    # --------------------------------------------------------------- takes
    def notify_take_saved(self, take: Take) -> None:
        self.refresh_dataset(force=True)
        self.take_finalized.emit(take)

    def request_review(self, take: Take) -> None:
        self.review_requested.emit(take)

    # ------------------------------------------------------------ messaging
    def report_error(self, error: KineCaptureError) -> None:
        logger.error("Hata bildirildi [%s]: %s", error.code, error.message)
        self.error_raised.emit(error)

    def notify(self, message: str, timeout_ms: int = 4000) -> None:
        self.status_message.emit(message, timeout_ms)

    # ------------------------------------------------------------- settings
    def save_preferences(self) -> None:
        try:
            save_user_state(self.config)
        except KineCaptureError as exc:
            logger.warning("Ayarlar kaydedilemedi: %s", exc.message)

    def shutdown(self) -> None:
        self.release_capture_service()
        self.save_preferences()


__all__ = ["AppState"]
