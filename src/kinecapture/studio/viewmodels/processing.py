"""The Verileri Hesapla screen: what is waiting, what is running, what failed.

Progress comes from each job's own ``job.json``, so the screen and the record
on disk cannot disagree. Where the source never declared a frame count there is
no percentage, and none is invented.

No Qt.
"""

from __future__ import annotations

from typing import Optional

from kinecapture.dataset.summary_index import TakeIndex, TakeSummary, build_index
from kinecapture.studio.services.messages import Message, Severity, from_error
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
        self.jobs: Observable[tuple[Job, ...]] = Observable((), name="jobs")
        self.busy: Observable[bool] = Observable(False, name="busy")
        self.summary: Observable[str] = Observable("", name="summary")
        self.can_pause: Observable[bool] = Observable(pause_supported(), name="can_pause")
        self.message: Event[Message] = Event()

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
            self._refill()

        def failed(exc: BaseException) -> None:
            self.busy.set(False)
            self.message.emit(from_error(exc, headline="Kayıtlar okunamadı."))

        self._runner.run(work, done, failed)

    def _refill(self) -> None:
        if self._index is None:
            return
        waiting = tuple(
            take
            for take in self._index
            if not take.is_legacy and not take.complete_runs
        )
        self.waiting.force(waiting)
        done = len(self._index.with_complete_runs())
        parts = [f"{len(waiting)} kayıt işlenmeyi bekliyor", f"{done} kayıt işlenmiş"]
        legacy = len(self._index.legacy_takes())
        if legacy:
            parts.append(f"{legacy} eski biçim (yeni arayüz açmaz)")
        self.summary.set(" · ".join(parts))

    # ---------------------------------------------------------------- control
    def start(self, take: TakeSummary) -> bool:
        parameters = {
            "body_format": self._settings.processing.body_format,
            "body_model": self._settings.processing.body_model,
            "depth_mode": self._settings.processing.depth_mode,
            "store_depth": self._settings.processing.store_depth,
            "store_proxy": self._settings.processing.store_proxy,
        }
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
        if state is JobState.COMPLETE:
            self.message.emit(
                Message(
                    headline=f"{job.take.take_id} işlendi.",
                    severity=Severity.INFO,
                    detail=f"{job.progress.frames_processed} kare.",
                )
            )
            self.reload(force=True)
            return
        if state is JobState.PARTIAL:
            # Never called complete. The interface says exactly which check
            # did not pass rather than rounding it up to success.
            self.message.emit(
                Message(
                    headline=f"{job.take.take_id}: kaynak kapsamı doğrulanamadı.",
                    severity=Severity.WARNING,
                    detail=" · ".join(job.progress.issue_texts) or "Ayrıntılar işte.",
                    code="processing_partial",
                    technical={"issues": list(job.progress.issues)},
                )
            )
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

    @property
    def index(self) -> Optional[TakeIndex]:
        return self._index

    def shutdown(self) -> None:
        self.service.shutdown()


__all__ = ["CANCEL_NOTE", "ProcessingViewModel"]
