"""Projects, participants and sessions, as rows a list can show.

Wraps :class:`IdentityService` (who may see what) and :class:`ProjectWorkspace`
(what is on disk) behind value objects, so a screen never holds either. The
take counts come from the derived index rather than a directory walk - see
:mod:`kinecapture.dataset.summary_index` for why that distinction matters.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kinecapture.dataset.summary_index import TakeIndex, TakeSummary, build_index
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.project import Participant, Session
from kinecapture.identity.models import ProjectAccess, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectRow:
    """One project the signed-in user may open."""

    project_id: str
    name: str
    description: str
    path: str
    created_at: str
    is_owner: bool = False
    #: False when the folder is gone - the drive may simply not be plugged in.
    exists: bool = True

    @property
    def status_text(self) -> str:
        return "klasör bulunamadı" if not self.exists else ""


@dataclass(frozen=True)
class ParticipantRow:
    participant_id: str
    code: str
    created_at: str
    take_count: int = 0
    processed_count: int = 0
    awaiting_count: int = 0
    legacy_count: int = 0
    last_take_at: str = ""

    @property
    def has_work_waiting(self) -> bool:
        return self.awaiting_count > 0


@dataclass(frozen=True)
class SessionRow:
    session_id: str
    participant_id: str
    started_at: str
    ended_at: str = ""
    take_count: int = 0

    @property
    def is_open(self) -> bool:
        return not self.ended_at


class ProjectService:
    """Everything the Projects screen needs, and nothing it does not."""

    def __init__(self, identity, user: Optional[User] = None) -> None:  # noqa: ANN001
        self.identity = identity
        self.user = user

    # -------------------------------------------------------------- projects
    def projects(self) -> list[ProjectRow]:
        """Projects this user may open, newest first.

        A registered project whose folder has vanished is listed and marked,
        never dropped: "I cannot see it" and "it is not there" are different
        statements, and only the user can tell which one applies.
        """
        if self.user is None:
            return []
        rows: list[ProjectRow] = []
        for access in self.identity.list_projects(self.user):
            rows.append(
                ProjectRow(
                    project_id=access.project_id,
                    name=access.name,
                    description=access.description,
                    path=str(access.path),
                    created_at=access.created_at,
                    is_owner=access.owner_user_id == self.user.user_id,
                    exists=Path(access.path).is_dir(),
                )
            )
        rows.sort(key=lambda row: (row.created_at, row.name), reverse=True)
        return rows

    def create_project(
        self, dataset_root: Path, name: str, *, description: str = ""
    ) -> ProjectWorkspace:
        if self.user is None:
            raise PermissionError("Proje oluşturmadan önce giriş yapılmalıdır.")
        return self.identity.create_project(
            self.user, Path(dataset_root), name, description=description
        )

    def open_workspace(self, access: ProjectAccess) -> ProjectWorkspace:
        return ProjectWorkspace.open(access.path)

    # ---------------------------------------------------- participants/sessions
    def participants(
        self, workspace: ProjectWorkspace, index: Optional[TakeIndex] = None
    ) -> list[ParticipantRow]:
        """Participants with their take counts, taken from the derived index."""
        counts = self._counts_by_participant(index)
        rows: list[ParticipantRow] = []
        for participant in workspace.list_participants():
            summary = counts.get(participant.participant_id, {})
            rows.append(
                ParticipantRow(
                    participant_id=participant.participant_id,
                    code=participant.code,
                    created_at=participant.created_at,
                    take_count=summary.get("total", 0),
                    processed_count=summary.get("processed", 0),
                    awaiting_count=summary.get("awaiting", 0),
                    legacy_count=summary.get("legacy", 0),
                    last_take_at=summary.get("last", ""),
                )
            )
        rows.sort(key=lambda row: row.code)
        return rows

    @staticmethod
    def _counts_by_participant(index: Optional[TakeIndex]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        if index is None:
            return result
        for take in index:
            entry = result.setdefault(
                take.participant_id,
                {"total": 0, "processed": 0, "awaiting": 0, "legacy": 0, "last": ""},
            )
            entry["total"] += 1
            if take.complete_runs:
                entry["processed"] += 1
            if take.awaits_processing:
                entry["awaiting"] += 1
            if take.is_legacy:
                entry["legacy"] += 1
            if take.started_at > entry["last"]:
                entry["last"] = take.started_at
        return result

    def create_participant(self, workspace: ProjectWorkspace) -> Participant:
        """Allocate the next anonymous code. No biometric form, by design."""
        created_by = self.user.user_id if self.user else ""
        return workspace.create_participant(created_by_user_id=created_by)

    def sessions(
        self,
        workspace: ProjectWorkspace,
        participant_id: Optional[str] = None,
        index: Optional[TakeIndex] = None,
    ) -> list[SessionRow]:
        counts: dict[str, int] = {}
        if index is not None:
            for take in index:
                counts[take.session_id] = counts.get(take.session_id, 0) + 1
        rows = [
            SessionRow(
                session_id=session.session_id,
                participant_id=session.participant_id,
                started_at=session.started_at,
                ended_at=session.ended_at or "",
                take_count=counts.get(session.session_id, 0),
            )
            for session in workspace.list_sessions(participant_id)
        ]
        rows.sort(key=lambda row: row.started_at, reverse=True)
        return rows

    # ----------------------------------------------------------------- index
    def refresh_index(self, workspace: ProjectWorkspace, *, force: bool = False) -> TakeIndex:
        """Rebuild the derived take index.

        Slow enough to belong on a worker thread - measured at roughly 150 ms
        for a thousand takes even when nothing changed - which is why every
        caller in the interface reaches it through a
        :class:`~kinecapture.studio.viewmodels.tasks.TaskRunner`.
        """
        return build_index(workspace.root, force=force)

    @staticmethod
    def take_rows(index: Optional[TakeIndex]) -> list[TakeSummary]:
        return [] if index is None else index.sorted_takes()


__all__ = ["ParticipantRow", "ProjectRow", "ProjectService", "SessionRow"]
