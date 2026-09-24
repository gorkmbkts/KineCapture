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
from kinecapture.dataset.deletion import ProjectDeletionService
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


_Lists = tuple[tuple[ParticipantRow, ...], tuple[SessionRow, ...]]


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
        #: Which of the four situations the list is in. "boş" and "giriş
        #: yapılmadı" and "okunamadı" are different statements, and only the
        #: user can tell which one explains an empty screen.
        self.state: Observable[str] = Observable("idle", name="projects_state")
        #: True while a deletion is running. The list stays on screen; only
        #: the actions are held, because erasing is not instant.
        self.deleting: Observable[bool] = Observable(False, name="deleting")
        self.message: Event[Message] = Event()
        #: The user the current list belongs to. A list loaded for nobody is
        #: not a list of no projects.
        self._loaded_for: Optional[str] = None
        #: Every read of the participant and session lists - a rescan or a
        #: new selection - takes a number, and only the newest read reaches
        #: the screen. Rescans run in a thread pool and can finish out of
        #: order: four participants added in a row once showed three
        #: (release gate A1, 24 September 2026).
        self._reads = 0
        self._last_selection_read = 0
        self._scans = 0

    @property
    def loaded_for(self) -> Optional[str]:
        return self._loaded_for

    @property
    def current_user_id(self) -> str:
        user = self._session.user
        return user.user_id if user is not None else ""

    # --------------------------------------------------------------- loading
    def reload_projects(self) -> None:
        """Read the projects this user may open.

        Called again after signing in. The audit found a list loaded before
        authentication - which can only ever be empty - being kept as the
        answer afterwards, so a real project looked like no projects at all.
        """
        self._service.user = self._session.user
        if self._session.user is None:
            self._loaded_for = None
            self.projects.force(())
            self._next_read()
            self.participants.force(())
            self.sessions.force(())
            self.state.set("signed_out")
            self.summary.set("Projeleri görmek için giriş yapın.")
            return
        self.state.set("loading")
        try:
            rows = tuple(self._service.projects())
        except KineCaptureError as exc:
            self.state.set("error")
            self.summary.set("Projeler listelenemedi.")
            self.message.emit(from_error(exc, headline="Projeler listelenemedi."))
            return
        self._loaded_for = self.current_user_id
        self.projects.force(rows)
        current = self.selected_project.value
        if rows and current not in {row.project_id for row in rows}:
            self.state.set("ready")
            self.open_project(rows[0].project_id)
        elif not rows:
            self.selected_project.set("")
            self._next_read()
            self.participants.force(())
            self.sessions.force(())
            self.state.set("empty")
            self.summary.set("Bu hesapta proje yok. 'Yeni proje' ile başlayın.")
        else:
            self.state.set("ready")

    def refresh_all(self, *, force: bool = True) -> None:
        """What the "Yenile" button promises: the whole screen, not part of it.

        The old button rebuilt only the open project's index, so a project
        registered elsewhere - or missed because the list was loaded before
        sign-in - never appeared however many times it was pressed.
        """
        self.reload_projects()
        if self._session.workspace is not None:
            self.refresh_index(force=force)

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
        self._session.select_participant("")
        self.refresh_index()

    def refresh_index(self, *, force: bool = False) -> None:
        """Rescan the project on a worker thread, then refill the lists."""
        workspace = self._session.workspace
        if workspace is None:
            return
        self.busy.set(True)
        self._scans += 1
        scan = self._scans
        read = self._next_read()
        wanted = self.selected_participant.value or None

        def work() -> tuple[TakeIndex, _Lists]:
            index = self._service.refresh_index(workspace, force=force)
            return index, self._read_lists(workspace, index, wanted)

        def done(result: tuple[TakeIndex, _Lists]) -> None:
            index, lists = result
            newest_scan = scan == self._scans
            if newest_scan:
                self._index = index
                self.busy.set(False)
            if read == self._reads:
                self._apply(lists)
            elif newest_scan and self._last_selection_read > read:
                # A participant was chosen while this scan ran; that read used
                # the old index, so read again with the new one.
                self._refill()

        def failed(exc: BaseException) -> None:
            if scan == self._scans:
                self.busy.set(False)
            self.message.emit(
                from_error(exc, headline="Proje içeriği okunamadı.")
            )

        self._runner.run(work, done, failed)

    def _next_read(self) -> int:
        self._reads += 1
        return self._reads

    def _read_lists(
        self, workspace, index: Optional[TakeIndex], participant_id: Optional[str]  # noqa: ANN001
    ) -> "_Lists":
        """Participants and sessions from disk - on the runner's thread.

        Every participant and every session is its own JSON file, and with no
        participant chosen the session list is every session in the project:
        at 30 000 takes that kept the GUI thread for seconds (release gate A3,
        23 September 2026).
        """
        participants = tuple(self._service.participants(workspace, index))
        sessions = tuple(self._service.sessions(workspace, participant_id, index))
        return participants, sessions

    def _apply(self, lists: "_Lists") -> None:
        participants, sessions = lists
        self.participants.force(participants)
        self.sessions.force(sessions)
        self.summary.set(self._summary_text(participants))

    def _refill(self) -> None:
        workspace = self._session.workspace
        if workspace is None:
            return
        wanted = self.selected_participant.value or None
        index = self._index
        read = self._next_read()
        self._last_selection_read = read

        def work() -> _Lists:
            return self._read_lists(workspace, index, wanted)

        def done(lists: _Lists) -> None:
            if read == self._reads:
                self._apply(lists)

        def failed(exc: BaseException) -> None:
            self.message.emit(from_error(exc, headline="Katılımcılar okunamadı."))

        self._runner.run(work, done, failed)

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
        """Choose whose data the whole application is working on.

        Written to the session rather than kept here: Capture asks the session
        who the recording belongs to, and two independent selections is how a
        take ends up filed under the wrong participant.
        """
        self.selected_participant.set(participant_id)
        self._session.select_participant(participant_id)
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
        # Creating one *is* choosing it: the operator asked for this person to
        # exist, in this project, now. What was removed on 20 September is the
        # opposite - a participant being created because a recording needed a
        # folder and nobody had said which.
        self._session.select_participant(participant.participant_id)
        self.refresh_index(force=True)
        self.message.emit(
            Message(
                headline=f"Katılımcı eklendi ve seçildi: {participant.code}",
                severity=Severity.INFO,
                detail=(
                    "Kod proje içinde anonim ve değişmezdir. Kayıt bu "
                    "katılımcının klasörüne yazılır."
                ),
            )
        )
        return True

    # ----------------------------------------------------------------- delete
    def deletion_preflight(self, project_id: str):  # noqa: ANN201 - TargetReport
        """Check what deleting this project would mean, changing nothing.

        Returns the report, or ``None`` when it cannot even be inspected. The
        caller shows it to the user *before* asking them to agree: a
        confirmation that cannot say what is about to be erased is not consent.
        """
        user = self._session.user
        if user is None:
            return None
        service = ProjectDeletionService(
            self._session.identity, Path(self._session.config.dataset_root)
        )
        try:
            return service.preflight(user, project_id)
        except (KineCaptureError, PermissionError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Proje silinemez."))
            return None

    def delete_project(self, project_id: str) -> bool:
        """Erase one project for good. Runs off the calling thread.

        The row is found first so the message can name the project after its
        folder has gone. Everything dangerous is the deletion service's.
        """
        user = self._session.user
        if user is None:
            return False
        row = next(
            (r for r in self.projects.value if r.project_id == project_id), None
        )
        name = row.name if row is not None else project_id
        service = ProjectDeletionService(
            self._session.identity, Path(self._session.config.dataset_root)
        )
        self.deleting.set(True)

        def work():  # noqa: ANN202
            return service.delete(user, project_id)

        def done(result) -> None:  # noqa: ANN001
            self.deleting.set(False)
            # The open project may be the one that just went.
            if self.selected_project.value == project_id:
                self._session.close_project()
                self.selected_project.set("")
                self._next_read()
                self.participants.force(())
                self.sessions.force(())
            self.reload_projects()
            if result.remaining:
                self.message.emit(
                    Message(
                        headline=f"{name} kaydı silindi; bazı dosyalar kaldı.",
                        severity=Severity.WARNING,
                        detail=(
                            "Proje listeden kaldırıldı, fakat bazı dosyalar "
                            "silinemedi. Klasör başka bir program tarafından "
                            "kullanılıyor olabilir."
                        ),
                        code="project_partially_deleted",
                        technical={"kalan": list(result.remaining)[:10]},
                    )
                )
                return
            self.message.emit(
                Message(
                    headline=f"Proje silindi: {name}",
                    severity=Severity.INFO,
                    detail=result.summary if hasattr(result, "summary") else "",
                    code="project_deleted",
                )
            )

        def failed(exc: BaseException) -> None:
            self.deleting.set(False)
            self.message.emit(from_error(exc, headline="Proje silinemedi."))
            self.reload_projects()

        self._runner.run(work, done, failed)
        return True

    @property
    def index(self) -> Optional[TakeIndex]:
        return self._index


__all__ = ["ProjectsViewModel"]
