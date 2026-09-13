"""Verileri Hesapla: the queue between recording and labelling.

Two lists. Above, the takes with no finished version yet. Below, the attempts
that are running or have finished, each with real progress read from its own
job file - and a percentage only where the source declared a frame count.

"İptal ham kaydı silmez" is printed next to the button, not hidden in a
confirmation nobody reads twice.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kinecapture.dataset.summary_index import TakeSummary
from kinecapture.studio.services.processing import Job, JobState
from kinecapture.studio.theme import ThemeTokens
from kinecapture.studio.viewmodels.navigation import Destination
from kinecapture.studio.viewmodels.processing import CANCEL_NOTE, ProcessingViewModel

from ..models import ROW_ROLE, Column, RowTableModel
from ..widgets import ElidedLabel, label, separator
from .base import StudioPage

#: Job files are re-read at this rate. Progress that updates faster than it can
#: be read costs paint time and tells nobody anything.
_POLL_INTERVAL_MS = 400

_STATE_TEXT = {
    JobState.QUEUED: "sırada",
    JobState.RUNNING: "işleniyor",
    JobState.PAUSED: "duraklatıldı",
    JobState.COMPLETE: "tamamlandı",
    JobState.PARTIAL: "kapsam doğrulanamadı",
    JobState.FAILED: "başarısız",
    JobState.CANCELLED: "iptal edildi",
}

_STATE_STATUS = {
    JobState.COMPLETE: "live",
    JobState.PARTIAL: "warning",
    JobState.FAILED: "error",
    JobState.CANCELLED: "warning",
}


def _waiting_columns() -> tuple[Column[TakeSummary], ...]:
    return (
        Column("participant", "Katılımcı", lambda r: r.participant_id),
        Column(
            "started",
            "Tarih",
            lambda r: r.started_at[:16].replace("T", " "),
            sort_key=lambda r: r.started_at,
            numeric=True,
        ),
        Column(
            "duration",
            "Süre",
            lambda r: f"{r.duration_s:.0f} sn",
            sort_key=lambda r: r.duration_s,
            numeric=True,
        ),
        Column(
            "frames", "Kare", lambda r: str(r.frames), sort_key=lambda r: r.frames, numeric=True
        ),
        Column(
            "attempts",
            "Deneme",
            lambda r: str(len(r.runs)) if r.runs else "—",
            sort_key=lambda r: len(r.runs),
            numeric=True,
        ),
    )


def _job_columns() -> tuple[Column[Job], ...]:
    return (
        Column("take", "Kayıt", lambda j: j.take.take_id),
        Column(
            "state",
            "Durum",
            lambda j: _STATE_TEXT.get(j.progress.state, j.progress.state.value),
            status=lambda j: _STATE_STATUS.get(j.progress.state, ""),
        ),
        Column("progress", "İlerleme", lambda j: j.progress.progress_text, numeric=True),
        Column("eta", "Kalan", lambda j: j.progress.eta_text, numeric=True),
        Column(
            "rate",
            "Hız",
            lambda j: (f"{j.progress.rate_fps:.1f} FPS" if j.progress.rate_fps else "—"),
            numeric=True,
        ),
        Column(
            "issues",
            "Bulgular",
            lambda j: " · ".join(j.progress.issue_texts) or "—",
            tooltip=lambda j: "\n".join(j.progress.issue_texts) or "Bulgu yok",
        ),
    )


class ProcessingPage(StudioPage):
    def __init__(
        self,
        destination: Destination,
        tokens: ThemeTokens,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(destination, tokens, parent)
        self.viewmodel: Optional[ProcessingViewModel] = None

        self.summary = ElidedLabel("")
        self.summary.setProperty("kcRole", "sectionTitle")
        self.body_layout.addWidget(self.summary)

        actions = QHBoxLayout()
        actions.setSpacing(tokens.metric("KcSpacingMd"))
        self.start_button = QPushButton("Seçileni işle")
        self.start_button.setProperty("kcVariant", "primary")
        self.start_all_button = QPushButton("Hepsini kuyruğa al")
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setProperty("kcVariant", "quiet")
        actions.addWidget(self.start_button)
        actions.addWidget(self.start_all_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        self.body_layout.addLayout(actions)

        self.body_layout.addWidget(label("İŞLENMEYİ BEKLEYENLER", role="sectionTitle"))
        self.waiting_model, self.waiting_view = self._make_table(
            _waiting_columns(), "İşlenmeyi bekleyen kayıtlar"
        )
        self.body_layout.addWidget(self.waiting_view, 1)

        self.body_layout.addWidget(separator())
        self.body_layout.addWidget(label("İŞLER", role="sectionTitle"))
        self.job_model, self.job_view = self._make_table(_job_columns(), "İşler")
        self.body_layout.addWidget(self.job_view, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        self.body_layout.addWidget(self.progress)

        job_actions = QHBoxLayout()
        job_actions.setSpacing(tokens.metric("KcSpacingMd"))
        self.pause_button = QPushButton("Duraklat")
        self.resume_button = QPushButton("Devam et")
        self.cancel_button = QPushButton("İptal")
        self.retry_button = QPushButton("Yeniden dene")
        for button in (self.pause_button, self.resume_button, self.cancel_button, self.retry_button):
            button.setProperty("kcVariant", "quiet")
            button.setEnabled(False)
            job_actions.addWidget(button)
        self.cancel_note = ElidedLabel(CANCEL_NOTE)
        self.cancel_note.setProperty("kcRole", "pageSubtitle")
        self.cancel_note.setToolTip(CANCEL_NOTE)
        job_actions.addWidget(self.cancel_note, 1)
        self.body_layout.addLayout(job_actions)

        self.start_button.clicked.connect(self._start_selected)
        self.start_all_button.clicked.connect(self._start_all)
        self.refresh_button.clicked.connect(self._refresh)
        self.pause_button.clicked.connect(self._pause_selected)
        self.resume_button.clicked.connect(self._resume_selected)
        self.cancel_button.clicked.connect(self._cancel_selected)
        self.retry_button.clicked.connect(self._retry_selected)
        self.job_view.selectionModel().selectionChanged.connect(self._job_selected)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def _make_table(self, columns, caption: str):  # noqa: ANN001
        model = RowTableModel(columns, self)
        view = QTableView(self)
        view.setModel(model)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.verticalHeader().setVisible(False)
        view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        view.horizontalHeader().setStretchLastSection(True)
        view.setAccessibleName(caption)
        return model, view

    # -------------------------------------------------------------- binding
    def attach(self, viewmodel: ProcessingViewModel) -> None:
        self.viewmodel = viewmodel
        self.bind(viewmodel.waiting, self.waiting_model.set_rows)
        self.bind(viewmodel.jobs, self._show_jobs)
        self.bind(viewmodel.summary, self.summary.setText)
        self.bind(viewmodel.busy, self._show_busy)
        self.bind(viewmodel.can_pause, self._show_pause_support)
        self.bind_event(viewmodel.message, self.show_message)

    def page_activated(self) -> None:
        if self.viewmodel is None:
            return
        self.viewmodel.reload()
        self._timer.start()

    def page_deactivated(self) -> None:
        self._timer.stop()

    # ----------------------------------------------------------------- slots
    def _tick(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.poll()

    def _show_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)

    def _show_pause_support(self, supported: bool) -> None:
        self.pause_button.setToolTip(
            "" if supported else "Bu makinede duraklatma desteklenmiyor."
        )

    def _show_jobs(self, jobs: tuple[Job, ...]) -> None:
        self.job_model.set_rows(jobs)
        active = [j for j in jobs if j.progress.state is JobState.RUNNING]
        if not active:
            self.progress.hide()
        else:
            job = active[0]
            fraction = job.progress.fraction
            if fraction is None:
                # No declared total: a busy indicator, never a made-up number.
                self.progress.setRange(0, 0)
                self.progress.setFormat(job.progress.progress_text)
            else:
                self.progress.setRange(0, 100)
                self.progress.setValue(int(fraction * 100))
                self.progress.setFormat(
                    f"{job.progress.progress_text}  ·  %{int(fraction * 100)}"
                )
            self.progress.show()
        self._job_selected()

    def _selected_job(self) -> Optional[Job]:
        rows = self.job_view.selectionModel().selectedRows()
        return rows[0].data(ROW_ROLE) if rows else None

    def _selected_take(self) -> Optional[TakeSummary]:
        rows = self.waiting_view.selectionModel().selectedRows()
        return rows[0].data(ROW_ROLE) if rows else None

    def _job_selected(self, *_args) -> None:
        job = self._selected_job()
        state = job.progress.state if job else None
        running = state is JobState.RUNNING
        paused = state is JobState.PAUSED
        finished = bool(state and state.is_finished)
        self.pause_button.setEnabled(running and bool(self.viewmodel and self.viewmodel.can_pause.value))
        self.resume_button.setEnabled(paused)
        self.cancel_button.setEnabled(running or paused)
        self.retry_button.setEnabled(finished)

    # --------------------------------------------------------------- actions
    def _refresh(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.reload(force=True)

    def _start_selected(self) -> None:
        take = self._selected_take()
        if take is not None and self.viewmodel is not None:
            self.viewmodel.start(take)

    def _start_all(self) -> None:
        if self.viewmodel is not None:
            self.viewmodel.start_all()

    def _pause_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.pause(job.key)

    def _resume_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.resume(job.key)

    def _cancel_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.cancel(job.key)

    def _retry_selected(self) -> None:
        job = self._selected_job()
        if job and self.viewmodel:
            self.viewmodel.restart(job.take)


__all__ = ["ProcessingPage"]
