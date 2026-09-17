"""The Verileri Hesapla screen: what is waiting, what is running, what failed.

Progress comes from each job's own ``job.json``, so the screen and the record
on disk cannot disagree. Where the source never declared a frame count there is
no percentage, and none is invented.

No Qt.
"""

from __future__ import annotations

from typing import Optional

from kinecapture.dataset.summary_index import TakeIndex, TakeSummary, build_index
from kinecapture.studio.services.messages import Action, Message, Severity, from_error
from kinecapture.studio.services.processing import (
    Job,
    JobState,
    ProcessingService,
    describe_issue,
    pause_supported,
)
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.services.settings import SettingsService

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner

#: Said on the screen, next to the button. Cancelling frees the GPU; it does
#: not touch the recording, and an operator must not have to guess that.
CANCEL_NOTE = "İptal ham kaydı silmez. Kayıt olduğu gibi kalır."

#: A take in this state still has a writer holding its directory. Its frame
#: count and duration are whatever has been flushed so far, which is why the
#: audit saw a live recording appear in the queue as "0 kare, 0 saniye".
OPEN_TAKE_STATE = "recording"


class ProcessingViewModel:
    def __init__(
        self,
        session: SessionService,
        service: Optional[ProcessingService] = None,
        runner: Optional[TaskRunner] = None,
        settings: Optional[SettingsService] = None,
    ) -> None:
        self._session = session
        self.service = service or ProcessingService()
        self._runner: TaskRunner = runner or InlineRunner()
        self._settings = settings or SettingsService(session.config)
        self._index: Optional[TakeIndex] = None

        self.waiting: Observable[tuple[TakeSummary, ...]] = Observable((), name="waiting")
        #: Takes a writer still owns. Listed apart from the queue, never in it.
        self.open_takes: Observable[tuple[TakeSummary, ...]] = Observable(
            (), name="open_takes"
        )
        self.jobs: Observable[tuple[Job, ...]] = Observable((), name="jobs")
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.summary: Observable[str] = Observable("", name="summary")
        self.can_pause: Observable[bool] = Observable(pause_supported(), name="can_pause")
        #: The settings the next job will actually be started with, as one
        #: line. The audit found "Seçileni işle" starting a run with no
        #: statement anywhere of what it was about to apply.
        self.profile_summary: Observable[str] = Observable("", name="profile_summary")
        self.profile_rows: Observable[tuple[tuple[str, str], ...]] = Observable(
            (), name="profile_rows"
        )
        self.message: Event[Message] = Event()
        #: One per job, when it stops for any reason. The shell uses it to make
        #: the library and the project counts current without polling them.
        self.job_finished: Event[Job] = Event()

    # ---------------------------------------------------------------- profile
    def parameters(self) -> dict:
        """Exactly what :meth:`start` will pass to the job. One source."""
        processing = self._settings.processing
        return {
            "body_format": processing.body_format,
            "body_model": processing.body_model,
            "depth_mode": processing.depth_mode,
            "store_depth": processing.store_depth,
            "store_proxy": processing.store_proxy,
        }

    def refresh_profile(self) -> None:
        parameters = self.parameters()
        rows = (
            ("İskelet biçimi", str(parameters["body_format"])),
            ("Model", str(parameters["body_model"])),
            ("Derinlik modu", str(parameters["depth_mode"])),
            ("Derinlik saklanır", "evet" if parameters["store_depth"] else "hayır"),
            ("Proxy video", "evet" if parameters["store_proxy"] else "hayır"),
        )
        self.profile_rows.force(rows)
        self.profile_summary.set(
            " · ".join(
                (
                    str(parameters["body_format"]),
                    str(parameters["body_model"]),
                    str(parameters["depth_mode"]),
                    "derinlik saklanır" if parameters["store_depth"] else "derinlik saklanmaz",
                    "proxy var" if parameters["store_proxy"] else "proxy yok",
                )
            )
        )

    # --------------------------------------------------------------- loading
    def reload(self, *, force: bool = False) -> None:
        """Find the takes that have no finished version yet."""
        workspace = self._session.workspace
        if workspace is None:
            self.waiting.force(())
            self.summary.set("Önce bir proje açın.")
            return
        self.busy.set(True)

        def work() -> TakeIndex:
            return build_index(workspace.root, force=force)

        def done(index: TakeIndex) -> None:
            self._index = index
            self.busy.set(False)
            self.refresh_profile()
            self._refill()

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Kayıtlar okunamadı."))

        self._runner.run(work, done, failed)

    def _refill(self) -> None:
        if self._index is None:
            return
        candidates = [
            take
            for take in self._index
            if not take.is_legacy and not take.published_runs
        ]
        # A take whose writer has not let go is not a candidate for anything.
        # Processing it would read a directory that is still being written.
        open_takes = tuple(t for t in candidates if t.state == OPEN_TAKE_STATE)
        waiting = tuple(t for t in candidates if t.state != OPEN_TAKE_STATE)
        self.open_takes.force(open_takes)
        self.waiting.force(waiting)
        done = len(self._index.with_published_runs())
        parts = [f"{len(waiting)} kayıt işlenmeyi bekliyor", f"{done} kayıt işlenmiş"]
        if open_takes:
            parts.append(f"{len(open_takes)} kayıt hâlâ açık (işlenemez)")
        legacy = len(self._index.legacy_takes())
        if legacy:
            parts.append(f"{legacy} eski biçim (yeni arayüz açmaz)")
        self.summary.set(" · ".join(parts))

    # ---------------------------------------------------------------- control
    def start(self, take: TakeSummary) -> bool:
        if take.state == OPEN_TAKE_STATE:
            self.message.emit(
                Message(
                    headline="Bu kayıt hâlâ açık.",
                    severity=Severity.WARNING,
                    detail=(
                        "Kayıt kapanmadan işlenemez. Önce Yakalama ekranından "
                        "ya da başlıktaki göstergeden kaydı durdurun."
                    ),
                    code="take_still_recording",
                    technical={"take": take.take_id, "state": take.state},
                )
            )
            return False
        parameters = self.parameters()
        try:
            self.service.start(take, parameters=parameters)
        except (OSError, ValueError) as exc:
            self.message.emit(from_error(exc, headline="İşleme başlatılamadı."))
            return False
        self.poll()
        return True

    def start_all(self) -> int:
        started = 0
        for take in self.waiting.value:
            job = self.service.job_for(take.take_id)
            if job is not None and job.is_running:
                continue
            if self.start(take):
                started += 1
        return started

    def cancel(self, take_id: str) -> bool:
        stopped = self.service.cancel(take_id)
        if stopped:
            self.message.emit(
                Message(
                    headline="İşleme iptal edildi.",
                    severity=Severity.INFO,
                    detail=CANCEL_NOTE,
                    code="processing_cancelled",
                )
            )
        self.poll()
        return stopped

    def pause(self, take_id: str) -> bool:
        if not self.can_pause.value:
            self.message.emit(
                Message(
                    headline="Bu makinede duraklatma desteklenmiyor.",
                    severity=Severity.WARNING,
                    detail="İş iptal edilip sonra yeniden başlatılabilir.",
                )
            )
            return False
        result = self.service.pause(take_id)
        self.poll()
        return result

    def resume(self, take_id: str) -> bool:
        result = self.service.resume(take_id)
        self.poll()
        return result

    def pause_for_recording(self) -> int:
        """Called when a live recording starts: hand the GPU back, keep the work."""
        held = self.service.pause_all()
        if held:
            self.message.emit(
                Message(
                    headline=f"{held} iş duraklatıldı.",
                    severity=Severity.INFO,
                    detail="Kayıttan sonra devam edecek.",
                )
            )
        return held

    def restart(self, take: TakeSummary) -> bool:
        """Try again from the beginning. The previous attempt is left alone."""
        return self.start(take)

    # --------------------------------------------------------------- progress
    def poll(self) -> None:
        jobs = self.service.poll()
        self.jobs.force(jobs)
        for job in jobs:
            self._report_if_finished(job)

    def _report_if_finished(self, job: Job) -> None:
        state = job.progress.state
        if not state.is_finished or getattr(job, "_reported", False):
            return
        job._reported = True  # noqa: SLF001 - one message per job, by design
        self.job_finished.emit(job)
        if state in (JobState.COMPLETE, JobState.PARTIAL):
            self._report_result(job)
            self.reload(force=True)
            return
        if state is JobState.FAILED:
            self.message.emit(
                Message(
                    headline=f"{job.take.take_id} işlenemedi.",
                    severity=Severity.ERROR,
                    detail="Ham kayıt güvende; yeniden denenebilir.",
                    code="processing_failed",
                    technical={"hata": job.progress.error},
                )
            )

    def _report_result(self, job: Job) -> None:
        """Announce a finished version, and offer the screen that uses it.

        Both endings say what happened and both hand over the same way. The
        old "Sürümü incele" pointed at the library, which on 16 September was
        empty - the version it named had never been published. The link now
        carries the directory, so it opens that version in Etiketleme whether
        or not a list would have shown it.
        """
        progress = job.progress
        # Two notes on the card, the rest behind "Ayrıntılar". Five sentences
        # in a row is a wall, and the one that matters - how much matched - is
        # then the hardest to find.
        texts = list(progress.issue_texts)
        caveats = " · ".join(texts[:2])
        if len(texts) > 2:
            caveats += f" · +{len(texts) - 2} not daha"
        coverage = progress.coverage_text
        actions: list[Action] = []
        if progress.published and progress.directory is not None:
            actions.append(
                Action(f"review:{progress.directory}", "Etiketlemeyi aç", primary=True)
            )
            actions.append(Action("goto:library", "Sürüm listesi"))
        else:
            actions.append(Action("goto:processing", "İşleme ekranı"))
        if not progress.issues:
            self.message.emit(
                Message(
                    headline=f"{job.take.participant_id} kaydı işlendi.",
                    severity=Severity.INFO,
                    detail=" · ".join(
                        part for part in (f"{progress.frames_processed} kare", coverage) if part
                    ),
                    code="processing_complete",
                    technical={"kayıt": job.take.take_id, "sürüm": str(progress.directory or "")},
                    actions=tuple(actions),
                )
            )
            return
        if progress.published:
            # Published, and the notes are attached to it. Not rounded up to
            # success and not rounded down to failure: the version exists, the
            # caveats are on the row, and the operator decides.
            self.message.emit(
                Message(
                    headline=f"{job.take.participant_id} kaydı işlendi · notlarla.",
                    severity=Severity.WARNING,
                    detail=" · ".join(
                        part for part in (coverage, caveats) if part
                    ) or "Ayrıntılar işte.",
                    code="processing_published_with_issues",
                    technical={
                        "kayıt": job.take.take_id,
                        "sürüm": str(progress.directory or ""),
                        "notlar": list(progress.issue_texts),
                        "issues": list(progress.issues),
                    },
                    actions=tuple(actions),
                )
            )
            return
        self.message.emit(
            Message(
                headline=f"{job.take.take_id}: sürüm yayımlanamadı.",
                severity=Severity.ERROR,
                detail=" · ".join(
                    describe_issue(code) for code in progress.blocking_issues
                ) or caveats or "Ayrıntılar işte.",
                code="processing_blocked",
                technical={
                    "kayıt": job.take.take_id,
                    "blocking": list(progress.blocking_issues),
                    "issues": list(progress.issues),
                },
                actions=tuple(actions),
            )
        )

    @property
    def index(self) -> Optional[TakeIndex]:
        return self._index

    def shutdown(self) -> None:
        self.service.shutdown()


__all__ = ["CANCEL_NOTE", "ProcessingViewModel"]
