"""The İşlenen Videolar screen: finished versions, and the way into labelling.

Filtering happens over rows already in memory; changing a filter never re-reads
the project. The scan that does re-read it runs on a worker thread.

No Qt.
"""

from __future__ import annotations

import logging
from typing import Optional

from kinecapture.dataset.summary_index import TakeIndex
from kinecapture.studio.services.library import LibraryService, VersionRow
from kinecapture.studio.services.messages import Action, Message, Severity, from_error
from kinecapture.studio.services.processing import describe_issue
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

logger = logging.getLogger(__name__)


def _coverage_warning(row: VersionRow) -> Optional[Message]:
    """What this version is short of, on the axis it is short on.

    Three separate questions, answered separately:

    * were all the recorded frames found again in the raw source?
    * was the chosen person actually tracked through them?
    * and is there anything recorded that took nothing away?

    Only the first two can make a version incomplete. The third is said in the
    detail, never in the headline, because an informational note is not a
    warning - and treating it as one is how "Bu sürümün kaynak kapsamı
    doğrulanamadı" came to be shown for a note about when the athlete was
    chosen.
    """
    source_ok = row.coverage_verified
    subject_ok = row.subject_verified is not False
    if source_ok and subject_ok:
        return None

    facts: list[str] = []
    if row.capture_frames:
        facts.append(f"kaynak {row.matched_frames}/{row.capture_frames} kare eşleşti")
    if row.subject_text:
        facts.append(row.subject_text)

    if not subject_ok and not source_ok:
        headline = "Bu sürümde hem kaynak hem kişi kapsamı eksik."
        remedy = (
            "Yeniden işleme kişi takibini yeniden dener; ham kayıtta olmayan "
            "kareyi geri getiremez."
        )
    elif not subject_ok:
        headline = "Bu sürümde seçilen kişi kaydın tamamında izlenemedi."
        remedy = (
            "Etiketleyebilirsiniz, fakat kişi bulunmayan karelerde eklem "
            "verisi yok. Yeniden işleme bu kısmı düzeltebilir."
        )
    else:
        headline = "Bu sürümde ham kaynağın bazı kareleri eşleştirilemedi."
        remedy = (
            "Etiketleyebilirsiniz. Yeniden işleme eşleşmeyi tekrar dener; ham "
            "kayıtta olmayan kareyi geri getiremez."
        )

    notes = [describe_issue(code) for code in row.informational_issues]
    detail = " · ".join(facts)
    detail = f"{detail}. {remedy}" if detail else remedy
    if notes:
        detail = f"{detail} Ayrıca {len(notes)} bilgi notu var."
    return Message(
        headline=headline,
        severity=Severity.WARNING,
        detail=detail,
        code="coverage_incomplete",
        technical={
            "kaynak": f"{row.matched_frames}/{row.capture_frames}",
            "kişi": row.subject_text or "kaydedilmedi",
            "eksik_bulgular": list(row.source_issues),
            "bilgi_notları": list(row.informational_issues),
        },
    )


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
        #: ``(run_id, derived_bytes, raw_bytes)`` for the selected version.
        #: Walking a 2.7 GB folder takes long enough to be felt, so it happens
        #: on a worker and arrives here when it is ready. The run id travels
        #: with it so the view can tell whether the answer is still about the
        #: version on screen.
        self.selected_sizes: Observable[tuple[str, Optional[int], Optional[int]]] = (
            Observable(("", None, None), name="sizes")
        )
        self.message: Event[Message] = Event()
        #: Emitted when the user asks to label a version. The shell routes it.
        self.open_for_review: Event[VersionRow] = Event()
        #: Emitted when the user asks for another version of the same take,
        #: computed with the settings in force now. The shell routes it to
        #: the processing queue; the existing version is never touched.
        self.recompute_requested: Event[VersionRow] = Event()
        #: Bumped on every selection. A size measurement carrying an old token
        #: belongs to a version the user has already moved off and is dropped
        #: rather than allowed to land on the one now showing.
        self._selection_token = 0
        #: Measured sizes, kept for the life of the screen. The folders do not
        #: change under us, and walking one twice is the cost this avoids.
        self._size_cache: dict[str, tuple[Optional[int], Optional[int]]] = {}

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

        def work() -> tuple[TakeIndex, tuple[VersionRow, ...]]:
            index = self._service.refresh_index(workspace.root, force=force)
            # The rows are built here, on the worker: each one asks the disk
            # whether its version has labels, and thirty thousand of those
            # asked on the GUI thread froze the window (release gate A3).
            return index, tuple(self._service.versions(index))

        def done(result: tuple[TakeIndex, tuple[VersionRow, ...]]) -> None:
            self._index, self._all = result
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
        # Grouped, so the versions of one take are read together; still a flat
        # list, so each of them stays separately selectable and labellable.
        rows = tuple(
            self._service.grouped(
                [row for row in self._all if self._service.matches(row, key)]
            )
        )
        self.rows.force(rows)
        self.summary.set(self._summary_text(rows))
        current = self.selected.value
        if current is not None and current not in rows:
            self.select(None)

    def _summary_text(self, rows: tuple[VersionRow, ...]) -> str:
        if not self._all:
            return "Henüz işlenmiş sürüm yok."
        ready = sum(1 for r in self._all if r.subject_chosen)
        noted = sum(1 for r in self._all if not r.coverage_verified)
        no_subject = sum(1 for r in self._all if not r.subject_chosen)
        parts = [
            f"{len(rows)} / {len(self._all)} sürüm gösteriliyor",
            f"{ready} etiketlemeye hazır",
        ]
        if no_subject:
            parts.append(f"{no_subject} kişi seçilmemiş")
        if noted:
            # Counted separately rather than folded into the total: a note is
            # something to read before annotating, not a reason not to.
            parts.append(f"{noted} kapsam notu var")
        return " · ".join(parts)

    # ------------------------------------------------------------- selection
    def select(self, row: Optional[VersionRow]) -> None:
        self.selected.set(row)
        # Every selection invalidates any measurement still in flight.
        self._selection_token += 1
        token = self._selection_token
        if row is None:
            self.comparison.force(())
            self.selected_sizes.force(("", None, None))
            return
        self.comparison.force(tuple(self._service.versions_of(list(self._all), row.take_id)))
        self._load_sizes(row, token)

    def _load_sizes(self, row: VersionRow, token: int) -> None:
        """Measure the version on disk, off the interface's thread."""
        cached = self._size_cache.get(row.run_id)
        if cached is not None:
            self.selected_sizes.force((row.run_id, *cached))
            return
        # Nothing known yet: say so rather than leaving the previous version's
        # numbers on screen while this one is being measured.
        self.selected_sizes.force((row.run_id, None, None))

        def work() -> tuple[Optional[int], Optional[int]]:
            return self._service.sizes_for(row)

        def done(sizes: tuple[Optional[int], Optional[int]]) -> None:
            self._size_cache[row.run_id] = sizes
            if token != self._selection_token:
                # A later selection won. The answer is kept for when this
                # version is chosen again, but it must not be shown now.
                return
            self.selected_sizes.force((row.run_id, *sizes))

        def failed(exc: BaseException) -> None:
            logger.debug("Sürüm boyutu ölçülemedi (%s): %s", row.run_id, exc)

        self._runner.run(work, done, failed)

    def parameters(self, row: VersionRow) -> dict:
        return self._service.parameters_of(row)

    # ---------------------------------------------------------------- review
    def label(self, row: Optional[VersionRow] = None) -> bool:
        """Hand a version to the labelling screen, saying what is unresolved."""
        target = row or self.selected.value
        if target is None:
            return False
        warning = _coverage_warning(target)
        if warning is not None:
            # Allowed, but not silently: the annotator should know what is
            # missing before they spend an hour on it - and *which* thing is
            # missing. One sentence used to cover a two-frame source gap and a
            # recording with the athlete tracked in 42% of its frames.
            self.message.emit(warning)
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
