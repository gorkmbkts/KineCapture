"""The Projects screen: projects, their participants, and what is waiting.

The take index behind the counts is slow enough to matter, so it is fetched
through a :class:`~kinecapture.studio.viewmodels.tasks.TaskRunner` and the
screen stays responsive while it runs. ``busy`` says a refresh is in flight;
the old rows stay on screen until new ones arrive, because blanking a list to
show a spinner loses the user's place for no reason.

No Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from kinecapture.core.errors import KineCaptureError
from kinecapture.dataset.summary_index import TakeIndex
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.projects import (
    ParticipantRow,
    ProjectRow,
    ProjectService,
    SessionRow,
)
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner


class ProjectsViewModel:
    def __init__(
        self,
        session: SessionService,
        runner: Optional[TaskRunner] = None,
    ) -> None:
        self._session = session
        self._runner: TaskRunner = runner or InlineRunner()
        self._service = ProjectService(session.identity, session.user)
        self._index: Optional[TakeIndex] = None

        self.projects: Observable[tuple[ProjectRow, ...]] = Observable((), name="projects")
        self.participants: Observable[tuple[ParticipantRow, ...]] = Observable(
            (), name="participants"
        )
        self.sessions: Observable[tuple[SessionRow, ...]] = Observable((), name="sessions")
        self.selected_project: Observable[str] = Observable("", name="selected_project")
        self.selected_participant: Observable[str] = Observable(
            "", name="selected_participant"
        )
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.summary: Observable[str] = Observable("", name="summary")
        self.message: Event[Message] = Event()

    # --------------------------------------------------------------- loading
    def reload_projects(self) -> None:
        self._service.user = self._session.user
        try:
            rows = tuple(self._service.projects())
        except KineCaptureError as exc:
            self.message.emit(from_error(exc, headline="Projeler listelenemedi."))
            return
        self.projects.force(rows)
        current = self.selected_project.value
        if rows and current not in {row.project_id for row in rows}:
            self.open_project(rows[0].project_id)
        elif not rows:
            self.selected_project.set("")
            self.participants.force(())
            self.sessions.force(())
            self.summary.set("Henüz proje yok.")

    def open_project(self, project_id: str) -> None:
        """Open a project and start the index refresh that fills in its counts."""
        row = next((r for r in self.projects.value if r.project_id == project_id), None)
        if row is None:
            return
        if not row.exists:
            # The folder is gone - very often a drive that is not plugged in.
            # Nothing is deleted or de-registered on the strength of that.
            self.message.emit(
                Message(
                    headline="Proje klasörü bulunamadı.",
                    severity=Severity.WARNING,
                    detail=(
                        "Veri diski bağlı olmayabilir. Kayıt silinmedi; klasör "
                        "yerine geldiğinde proje açılabilir."
                    ),
                    code="project_folder_missing",
                    technical={"yol": row.path},
                )
            )
            return
        try:
            self._session.open_project(project_id)
        except (KineCaptureError, PermissionError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Proje açılamadı."))
            return
        self.selected_project.set(project_id)
        self.selected_participant.set("")
        self.refresh_index()

    def refresh_index(self, *, force: bool = False) -> None:
        """Rescan the project on a worker thread, then refill the lists."""
        workspace = self._session.workspace
        if workspace is None:
            return
        self.busy.set(True)

        def work() -> TakeIndex:
            return self._service.refresh_index(workspace, force=force)

        def done(index: TakeIndex) -> None:
            self._index = index
            self.busy.set(False)
            self._refill()

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(
                from_error(exc, headline="Proje içeriği okunamadı.")
            )

        self._runner.run(work, done, failed)

    def _refill(self) -> None:
        workspace = self._session.workspace
        if workspace is None:
            return
        try:
            participants = tuple(self._service.participants(workspace, self._index))
            sessions = tuple(
                self._service.sessions(
                    workspace, self.selected_participant.value or None, self._index
                )
            )
        except KineCaptureError as exc:
            self.message.emit(from_error(exc, headline="Katılımcılar okunamadı."))
            return
        self.participants.force(participants)
        self.sessions.force(sessions)
        self.summary.set(self._summary_text(participants))

    def _summary_text(self, participants: tuple[ParticipantRow, ...]) -> str:
        takes = sum(row.take_count for row in participants)
        waiting = sum(row.awaiting_count for row in participants)
        processed = sum(row.processed_count for row in participants)
        legacy = sum(row.legacy_count for row in participants)
        parts = [
            f"{len(participants)} katılımcı",
            f"{takes} kayıt",
            f"{processed} işlenmiş",
        ]
        if waiting:
            parts.append(f"{waiting} işlenmeyi bekliyor")
        if legacy:
            # Named, not hidden: these are readable in the old interface and
            # are being kept on purpose.
            parts.append(f"{legacy} eski biçim")
        return " · ".join(parts)

    # -------------------------------------------------------------- selection
    def select_participant(self, participant_id: str) -> None:
        self.selected_participant.set(participant_id)
        self._refill()

    # ---------------------------------------------------------------- actions
    def create_project(self, name: str, description: str = "") -> bool:
        clean = name.strip()
        if not clean:
            self.message.emit(
                Message(headline="Proje adı gerekli.", severity=Severity.WARNING)
            )
            return False
        self._service.user = self._session.user
        try:
            workspace = self._service.create_project(
                Path(self._session.config.dataset_root), clean, description=description.strip()
            )
        except (KineCaptureError, PermissionError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Proje oluşturulamadı."))
            return False
        self.reload_projects()
        self.open_project(workspace.project.project_id)
        self.message.emit(
            Message(headline=f"Proje oluşturuldu: {clean}", severity=Severity.INFO)
        )
        return True

    def create_participant(self) -> bool:
        workspace = self._session.workspace
        if workspace is None:
            self.message.emit(
                Message(headline="Önce bir proje açın.", severity=Severity.WARNING)
            )
            return False
        self._service.user = self._session.user
        try:
            participant = self._service.create_participant(workspace)
        except (KineCaptureError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Katılımcı eklenemedi."))
            return False
        self.refresh_index(force=True)
        self.message.emit(
            Message(
                headline=f"Katılımcı eklendi: {participant.code}",
                severity=Severity.INFO,
                detail="Kod proje içinde anonim ve değişmezdir.",
            )
        )
        return True

    @property
    def index(self) -> Optional[TakeIndex]:
        return self._index


__all__ = ["ProjectsViewModel"]
