"""The İşlenen Videolar screen: finished versions, and the way into labelling.

Filtering happens over rows already in memory; changing a filter never re-reads
the project. The scan that does re-read it runs on a worker thread.

No Qt.
"""

from __future__ import annotations

from typing import Optional

from kinecapture.dataset.summary_index import TakeIndex
from kinecapture.studio.services.library import LibraryService, VersionRow
from kinecapture.studio.services.messages import Action, Message, Severity, from_error
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner


class LibraryViewModel:
    def __init__(
        self,
        session: SessionService,
        runner: Optional[TaskRunner] = None,
        service: Optional[LibraryService] = None,
    ) -> None:
        self._session = session
        self._runner: TaskRunner = runner or InlineRunner()
        self._service = service or LibraryService()
        self._all: tuple[VersionRow, ...] = ()
        self._index: Optional[TakeIndex] = None

        self.rows: Observable[tuple[VersionRow, ...]] = Observable((), name="versions")
        self.filter_key: Observable[str] = Observable("all", name="filter")
        self.selected: Observable[Optional[VersionRow]] = Observable(None, name="selected")
        self.comparison: Observable[tuple[VersionRow, ...]] = Observable(
            (), name="comparison"
        )
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.summary: Observable[str] = Observable("", name="summary")
        self.message: Event[Message] = Event()
        #: Emitted when the user asks to label a version. The shell routes it.
        self.open_for_review: Event[VersionRow] = Event()
        #: Emitted when the user asks for another version of the same take,
        #: computed with the settings in force now. The shell routes it to
        #: the processing queue; the existing version is never touched.
        self.recompute_requested: Event[VersionRow] = Event()

    @property
    def filters(self):  # noqa: ANN201
        return LibraryService.FILTERS

    # --------------------------------------------------------------- loading
    def reload(self, *, force: bool = False) -> None:
        workspace = self._session.workspace
        if workspace is None:
            self._all = ()
            self.rows.force(())
            self.summary.set("Önce bir proje açın.")
            return
        self.busy.set(True)

        def work() -> TakeIndex:
            return self._service.refresh_index(workspace.root, force=force)

        def done(index: TakeIndex) -> None:
            self._index = index
            self._all = tuple(self._service.versions(index))
            self.busy.set(False)
            self._apply_filter()

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Sürümler okunamadı."))

        self._runner.run(work, done, failed)

    def set_filter(self, key: str) -> None:
        """Filter in memory. Changing it must never re-read the project."""
        if self.filter_key.set(key):
            self._apply_filter()

    def _apply_filter(self) -> None:
        key = self.filter_key.value
        rows = tuple(row for row in self._all if self._service.matches(row, key))
        self.rows.force(rows)
        self.summary.set(self._summary_text(rows))
        current = self.selected.value
        if current is not None and current not in rows:
            self.select(None)

    def _summary_text(self, rows: tuple[VersionRow, ...]) -> str:
        if not self._all:
            return "Henüz işlenmiş sürüm yok."
        ready = sum(1 for r in self._all if r.coverage_verified and r.subject_chosen)
        unverified = sum(1 for r in self._all if not r.coverage_verified)
        no_subject = sum(1 for r in self._all if not r.subject_chosen)
        parts = [
            f"{len(rows)} / {len(self._all)} sürüm gösteriliyor",
            f"{ready} etiketlemeye hazır",
        ]
        if no_subject:
            parts.append(f"{no_subject} kişi seçilmemiş")
        if unverified:
            # Named rather than folded into a total: this is the one that must
            # not be mistaken for a finished result.
            parts.append(f"{unverified} kapsam doğrulanamadı")
        return " · ".join(parts)

    # ------------------------------------------------------------- selection
    def select(self, row: Optional[VersionRow]) -> None:
        self.selected.set(row)
        if row is None:
            self.comparison.force(())
            return
        self.comparison.force(tuple(self._service.versions_of(list(self._all), row.take_id)))

    def parameters(self, row: VersionRow) -> dict:
        return self._service.parameters_of(row)

    # ---------------------------------------------------------------- review
    def label(self, row: Optional[VersionRow] = None) -> bool:
        """Hand a version to the labelling screen, saying what is unresolved."""
        target = row or self.selected.value
        if target is None:
            return False
        if not target.coverage_verified:
            # Allowed, but not silently: the annotator should know the source
            # coverage did not check out before they spend an hour on it.
            self.message.emit(
                Message(
                    headline="Bu sürümün kaynak kapsamı doğrulanamadı.",
                    severity=Severity.WARNING,
                    detail=(
                        "Etiketleyebilirsiniz, fakat sonuç eksiksiz sayılmaz. "
                        "Gerekirse yeniden işleyin."
                    ),
                    code="coverage_unverified",
                    technical={"issues": list(target.issues)},
                )
            )
        self.open_for_review.emit(target)
        return True

    # ------------------------------------------------------------ new version
    def recompute(self, row: Optional[VersionRow] = None) -> bool:
        """Ask for another version of this take with the current settings.

        A new version, never an edit of the old one: the arrays and the
        checksums of a finished run are what the labels point at, and
        recomputing in place would change data somebody has already reviewed.
        """
        target = row or self.selected.value
        if target is None:
            return False
        self.recompute_requested.emit(target)
        return True

    def subject_recovery_message(self, row: VersionRow) -> Message:
        """What can honestly be done about a version with nobody in it.

        Choosing an athlete now cannot fill arrays that were written empty at
        processing time. The only real repair is another run with the athlete
        marked - and if the raw recording carries no anchor either, that has to
        be said rather than implied away.
        """
        return Message(
            headline="Bu sürümde izlenen kişi yok.",
            severity=Severity.WARNING,
            detail=(
                "Sürüm işlenirken hiçbir kişi seçilmemiş; eklem dizileri boş "
                "ve sonradan seçim onları doldurmaz. Kaydı yeniden işlemek yeni "
                "bir sürüm üretir; mevcut sürüm olduğu gibi kalır. Ham kayıtta "
                "kişi işareti yoksa yeni sürüm de kişisiz çıkar — işaret kayıt "
                "sırasında konur."
            ),
            code="needs_subject_selection",
            technical={"kayıt": row.take_id, "sürüm": row.run_id},
            actions=(
                Action("goto:processing", "Yeni sürüm hesapla", primary=True),
            ),
        )

    @property
    def all_rows(self) -> tuple[VersionRow, ...]:
        return self._all


__all__ = ["LibraryViewModel"]
