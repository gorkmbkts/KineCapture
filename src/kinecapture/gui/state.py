"""Authenticated application state shared by every workspace page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from kinecapture.camera import create_backend_from_config
from kinecapture.capture.service import CaptureService
from kinecapture.core.config import AppConfig, save_user_state
from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.core.ids import new_id, utc_now_iso
from kinecapture.core.logging import get_logger
from kinecapture.dataset.index import DatasetIndex
from kinecapture.dataset.deletion import (
    ProjectDeletionService,
    recover_tombstones,
)
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import BackendKind
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import Participant, Project, Session, Take
from kinecapture.gui.theme import Theme, get_theme
from kinecapture.identity import IdentityDatabase, IdentityService, ProjectAccess, User

logger = get_logger(__name__)


class AppState(QObject):
    """Single authenticated context for identity, project and capture state."""

    user_changed = Signal(object)
    project_changed = Signal(object)
    participant_changed = Signal(object)
    session_changed = Signal(object)
    dataset_changed = Signal()
    theme_changed = Signal(object)
    backend_changed = Signal(object)
    error_raised = Signal(object)
    status_message = Signal(str, int)
    take_finalized = Signal(object)
    review_requested = Signal(object)

    def __init__(self, config: AppConfig, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.identity = IdentityService(IdentityDatabase(config.identity_db_path))
        self._theme = get_theme(config.theme)
        self._current_user: Optional[User] = None
        self._workspace: Optional[ProjectWorkspace] = None
        self._index: Optional[DatasetIndex] = None
        self._participant: Optional[Participant] = None
        self._session: Optional[Session] = None
        self._capture: Optional[CaptureService] = None
        self._deletion: Optional[ProjectDeletionService] = None
        self._run_id = new_id("run")

    # -------------------------------------------------------------- identity
    @property
    def current_user(self) -> Optional[User]:
        return self._current_user

    @property
    def is_authenticated(self) -> bool:
        return self._current_user is not None

    def authenticate(self, username: str, password: str) -> User:
        user = self.identity.authenticate(username, password)
        self.config.last_username = user.username
        self.save_preferences()
        return user

    def activate_user(self, user: User) -> None:
        current = self.identity.require_active(user)
        if current.must_change_password:
            raise ValidationError(
                "Çalışma alanına geçmeden önce şifrenizi değiştirin.",
                code="password_change_required",
            )
        self._current_user = current
        self.user_changed.emit(current)

    def refresh_current_user(self) -> User:
        user = self._require_user()
        self.user_changed.emit(user)
        return user

    def replace_current_user(self, user: User) -> None:
        """Install a freshly persisted version of the signed-in user."""
        if self._current_user is None or self._current_user.user_id != user.user_id:
            raise ValidationError("Aktif kullanıcı eşleşmiyor.", code="current_user_mismatch")
        self._current_user = self.identity.require_active(user)
        self.user_changed.emit(self._current_user)

    def _require_user(self) -> User:
        if self._current_user is None:
            raise ValidationError("Önce oturum açın.", code="login_required")
        self._current_user = self.identity.require_active(self._current_user)
        return self._current_user

    def logout(self, *, abort_recording: bool = False) -> None:
        service = self._capture
        if service is not None and service.is_recording:
            if not abort_recording:
                raise ValidationError(
                    "Kayıt sürerken oturum kapatılamaz.", code="recording_in_progress"
                )
            service.stop_recording(abort_reason="kullanıcı oturumu kapattı")
        self._close_automatic_session("kullanıcı oturumu kapattı")
        self.release_capture_service()
        self._workspace = None
        self._index = None
        self._participant = None
        self._session = None
        self._current_user = None
        self.project_changed.emit(None)
        self.participant_changed.emit(None)
        self.session_changed.emit(None)
        self.dataset_changed.emit()
        self.user_changed.emit(None)

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

    def list_accessible_projects(self) -> list[ProjectAccess]:
        return self.identity.list_projects(self._require_user())

    def _guard_context_change(self) -> None:
        if self._capture is not None and self._capture.is_recording:
            raise ValidationError(
                "Kayıt sürerken proje veya katılımcı değiştirilemez.",
                code="recording_context_locked",
            )

    def open_project(self, root: Path) -> ProjectWorkspace:
        self._guard_context_change()
        user = self._require_user()
        record = self.identity.authorize_project_path(user, Path(root))
        self._close_automatic_session("proje değiştirildi")
        workspace = ProjectWorkspace.open(record.path)
        if workspace.project.project_id != record.project_id:
            raise ValidationError(
                "Proje klasörünün kimliği erişim kaydıyla eşleşmiyor.",
                code="project_identity_mismatch",
            )
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
        self._guard_context_change()
        user = self._require_user()
        workspace = self.identity.create_project(
            user,
            self.config.dataset_root,
            name,
            description=description,
            capture_profile=self.config.capture,
        )
        return self.open_project(workspace.root)

    def import_project(self, root: Path) -> ProjectWorkspace:
        self._guard_context_change()
        user = self._require_user()
        self.identity.require_owner(user)
        workspace = ProjectWorkspace.open(root)
        self.identity.register_project(user, workspace)
        return self.open_project(workspace.root)

    def authorize_active_project(self) -> ProjectAccess:
        user = self._require_user()
        if self._workspace is None:
            raise ValidationError("Önce bir proje seçin.", code="project_required")
        return self.identity.authorize_project(user, self._workspace.project.project_id)

    def save_project(self) -> Project:
        self.authorize_active_project()
        if self._workspace is None:
            raise ValidationError("Önce bir proje seçin.", code="project_required")
        return self._workspace.save_project()

    def close_project(self) -> None:
        self._guard_context_change()
        self._close_automatic_session("proje kapatıldı")
        self._workspace = None
        self._index = None
        self._participant = None
        self._session = None
        self.project_changed.emit(None)
        self.participant_changed.emit(None)
        self.session_changed.emit(None)
        self.dataset_changed.emit()

    # ------------------------------------------------- permanent deletion
    @property
    def deletion(self) -> ProjectDeletionService:
        """The coordinator for permanently deleting a project."""
        if self._deletion is None:
            self._deletion = ProjectDeletionService(
                self.identity, self.config.dataset_root
            )
        return self._deletion

    def prepare_project_deletion(self, project_id: str) -> None:
        """Let go of a project completely, before anything is removed.

        Windows will not rename a directory that something has a file open in,
        and a stale ``VideoCapture`` is exactly such a something. So the order
        matters: authorise, refuse while recording, then release the camera
        service and every reader, and only then let the deletion begin.

        Recording is refused rather than aborted. Stopping a take from
        underneath the operator to free a folder would trade one kind of data
        loss for another; they can stop it themselves.
        """
        user = self._require_user()
        self.identity.authorize_project_deletion(user, project_id)
        if self._capture is not None and self._capture.is_recording:
            raise ValidationError(
                "Kayıt sürerken proje silinemez. Önce kaydı durdurun.",
                code="recording_blocks_delete",
            )

        active = self._workspace is not None and (
            self._workspace.project.project_id == project_id
        )
        if not active:
            return

        self._close_automatic_session("proje siliniyor")
        # Drops the camera backend and, with it, any proxy/video handle held
        # open on files inside this project.
        self.release_capture_service()
        self._workspace = None
        self._index = None
        self._participant = None
        self._session = None
        self.project_changed.emit(None)
        self.participant_changed.emit(None)
        self.session_changed.emit(None)

    def finish_project_deletion(self, project_id: str) -> None:
        """Forget the deleted project everywhere the user could meet it again."""
        last = self.config.last_project_path
        if last is not None and Path(last).name == project_id:
            self.config.last_project_path = None
            self.save_preferences()
        self.dataset_changed.emit()

    def recover_interrupted_deletions(self) -> list[str]:
        """Resolve any deletion a crash left half-done. Safe to call on start."""
        try:
            known = {
                record.project_id
                for record in self.identity.repository.list_projects(
                    self._require_user()
                )
            }
        except Exception:  # pragma: no cover - no user yet
            known = set()
        notes = recover_tombstones(self.config.dataset_root, known_project_ids=known)
        for note in notes:
            logger.warning("Yarım kalan proje silme: %s", note)
        return notes

    def refresh_dataset(self, *, force: bool = False) -> None:
        if self._index is None:
            return
        self.authorize_active_project()
        self._index.refresh(force=force)
        self.dataset_changed.emit()

    # ---------------------------------------------- participant and session
    @property
    def participant(self) -> Optional[Participant]:
        return self._participant

    def list_participants(self) -> list[Participant]:
        self.authorize_active_project()
        assert self._workspace is not None
        return self._workspace.list_participants()

    def create_participant(self) -> Participant:
        user = self._require_user()
        self.authorize_active_project()
        assert self._workspace is not None
        participant = self._workspace.create_participant(created_by_user_id=user.user_id)
        self.set_participant(participant)
        self.refresh_dataset(force=True)
        return participant

    def load_participant(self, participant_id: str) -> Participant:
        self.authorize_active_project()
        assert self._workspace is not None
        return self._workspace.load_participant(participant_id)

    def set_participant(self, participant: Optional[Participant]) -> None:
        if participant is not None:
            self.authorize_active_project()
        if participant is not None and self._participant is not None:
            if participant.participant_id == self._participant.participant_id:
                return
        self._guard_context_change()
        self._close_automatic_session("katılımcı değiştirildi")
        self._participant = participant
        self.participant_changed.emit(participant)

    @property
    def session(self) -> Optional[Session]:
        return self._session

    def set_session(self, session: Optional[Session]) -> None:
        """Compatibility hook; product flows should use prepare_capture()."""
        self._session = session
        if session is not None and self._workspace is not None:
            if self._participant is None or self._participant.participant_id != session.participant_id:
                self._participant = self._workspace.load_participant(session.participant_id)
                self.participant_changed.emit(self._participant)
        self.session_changed.emit(session)

    def _close_automatic_session(self, reason: str) -> None:
        session = self._session
        workspace = self._workspace
        if session is None or workspace is None:
            self._session = None
            return
        if session.is_open and bool(session.attributes.get("automatic")):
            session.ended_at = utc_now_iso()
            session.attributes["automatic_close_reason"] = reason
            try:
                workspace.save_session(session)
            except KineCaptureError:
                logger.exception("Otomatik oturum kapatılamadı: %s", session.session_id)
        self._session = None
        self.session_changed.emit(None)

    def _close_orphaned_sessions(self, participant_id: str) -> None:
        assert self._workspace is not None
        for session in self._workspace.list_sessions(participant_id):
            if not session.is_open or not bool(session.attributes.get("automatic")):
                continue
            if session.attributes.get("managed_run_id") == self._run_id:
                continue
            session.ended_at = utc_now_iso()
            session.attributes["automatic_close_reason"] = "önceki uygulama çalışması kapatıldı"
            self._workspace.save_session(session)

    def prepare_capture(
        self, participant: Participant, *, protocol_id: Optional[str] = None
    ) -> Session:
        self._guard_context_change()
        user = self._require_user()
        self.authorize_active_project()
        assert self._workspace is not None
        loaded = self._workspace.load_participant(participant.participant_id)
        protocols = list(self._workspace.project.protocols)
        if len(protocols) == 1:
            selected_protocol_id = protocols[0].protocol_id
        elif len(protocols) == 0:
            selected_protocol_id = None
        elif protocol_id is None:
            raise ValidationError(
                "Birden fazla Kayıt Planı var; devam etmek için birini seçin.",
                code="recording_plan_required",
                details={"protocol_ids": [p.protocol_id for p in protocols]},
            )
        elif self._workspace.project.protocol_by_id(protocol_id) is None:
            raise ValidationError("Kayıt Planı bulunamadı.", code="recording_plan_invalid")
        else:
            selected_protocol_id = protocol_id

        if (
            self._session is not None
            and self._session.is_open
            and self._session.participant_id == loaded.participant_id
            and self._session.project_id == self._workspace.project.project_id
            and self._session.operator_user_id == user.user_id
            and self._session.protocol_id == selected_protocol_id
            and bool(self._session.attributes.get("automatic"))
        ):
            self._participant = loaded
            self.participant_changed.emit(loaded)
            return self._session

        self._close_automatic_session("çekim bağlamı değiştirildi")
        self._close_orphaned_sessions(loaded.participant_id)
        session = self._workspace.create_session(
            loaded.participant_id,
            operator=user.display_name,
            operator_user_id=user.user_id,
            protocol_id=selected_protocol_id,
            capture_profile=self.config.capture,
            attributes={"automatic": True, "managed_run_id": self._run_id},
        )
        self._participant = loaded
        self._session = session
        self.participant_changed.emit(loaded)
        self.session_changed.emit(session)
        return session

    def authorize_capture(self) -> None:
        user = self._require_user()
        self.authorize_active_project()
        if self._workspace is None or self._participant is None or self._session is None:
            raise ValidationError(
                "Katılımcılar ekranından katılımcı seçip Kayda Başla'yı kullanın.",
                code="capture_context_required",
            )
        if not self._session.is_open or self._session.operator_user_id != user.user_id:
            raise ValidationError("Çekim bağlamı artık geçerli değil.", code="capture_context_invalid")
        if self._session.participant_id != self._participant.participant_id:
            raise ValidationError(
                "Katılımcı ve çekim oturumu eşleşmiyor.",
                code="capture_participant_mismatch",
            )

    @property
    def can_capture(self) -> bool:
        return (
            self._current_user is not None
            and self._workspace is not None
            and self._participant is not None
            and self._session is not None
            and self._session.is_open
        )

    # -------------------------------------------------------------- capture
    @property
    def capture(self) -> Optional[CaptureService]:
        return self._capture

    def ensure_capture_service(self, kind: Optional[BackendKind] = None) -> CaptureService:
        self.authorize_capture()
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
        self._close_automatic_session("uygulama kapatıldı")
        self.save_preferences()


__all__ = ["AppState"]
