"""Running offline processing as a separate process, and reading its progress.

``process_take`` is deliberately GUI-free, and it stays that way: the Studio
starts it with ``python -m kinecapture.processing`` in a child process rather
than importing it. Three reasons, in order of how much they cost when ignored:

* The SDK is opened in that process, not this one. A crash there loses a job;
  the same crash in here would lose the application.
* Nothing it does can block a repaint, no matter how badly it behaves.
* It can be paused and killed by the operating system, which is what "iptal"
  has to mean when a run has been going for twenty minutes.

Progress is **read from ``job.json``**, which the job writes as it goes. That
file is the record; this module never keeps a second, prettier copy that could
disagree with it.

No Qt.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

from kinecapture.core.jsonio import read_json
from kinecapture.core.paths import long_path, path_exists
from kinecapture.dataset.summary_index import TakeSummary

logger = logging.getLogger(__name__)


class JobState(str, Enum):
    """Where a job is. Mirrors what ``job.json`` says, never guessed at."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_finished(self) -> bool:
        return self in (
            JobState.COMPLETE,
            JobState.PARTIAL,
            JobState.FAILED,
            JobState.CANCELLED,
        )

    @property
    def is_active(self) -> bool:
        return self in (JobState.RUNNING, JobState.PAUSED, JobState.QUEUED)


#: What each issue code means in a sentence, for the screen to show instead of
#: the code. An unmapped code is shown verbatim rather than glossed over.
ISSUE_TEXT = {
    "source_frame_count_mismatch": (
        "Dosya başlığındaki kare sayısı ile okunan kare sayısı farklı."
    ),
    "capture_frames_unmatched": (
        "Kayıt sırasındaki bazı kareler ham kaynakta eşleştirilemedi."
    ),
    "source_capture_timestamp_unmatched_or_ambiguous": (
        "Bazı karelerin zaman damgası kayıt indeksiyle birebir eşleşmedi."
    ),
    "subject_anchor_unresolved": (
        "Seçilen kişi o karede tek başına bulunamadı; kişi ataması yapılmadı."
    ),
    "subject_anchor_outside_source": (
        "Seçim, ham kaynakta bulunmayan bir zaman damgasına işaret ediyor."
    ),
    "capture_timestamp_duplicated": (
        "Kamera iki kareye aynı mikrosaniyeyi verdi; kareler sırayla eşleştirildi."
    ),
    "subject_anchor_before_recording": (
        "Kişi seçimi kayıt başlamadan önce yapılmış; ilk kareye uygulandı."
    ),
    "review_proxy_unavailable": (
        "Önizleme videosu üretilemedi; iskelet ve veriler etkilenmedi."
    ),
    "review_proxy_desynchronised": (
        "Önizleme videosunun kare sayısı sürümle uyuşmuyor."
    ),
    # Written by versions produced before the code was split in two. Kept so
    # an older job file still reads as a sentence instead of as a code.
    "review_proxy_incomplete": "Önizleme videosu eksik üretildi.",
    "source_empty": "Kaynaktan hiç kare okunamadı.",
    "requested_depth_missing": "İstenen derinlik bazı karelerde üretilemedi.",
    "calibration_invalid_or_missing": "Kamera kalibrasyonu okunamadı.",
    "source_timestamp_gap": "Kaynakta zaman damgası boşluğu var.",
    "source_timestamp_non_monotonic": "Kaynakta zaman damgası geriye gitti.",
    "source_position_discontinuity": "Kaynak kare sırası kesintili.",
}


def describe_issue(code: str) -> str:
    return ISSUE_TEXT.get(code, code)


@dataclass(frozen=True)
class JobProgress:
    """One reading of a job. Everything here comes from ``job.json``."""

    state: JobState = JobState.QUEUED
    frames_processed: int = 0
    #: ``None`` when the source never declared a total. No percentage is
    #: invented from a denominator nobody supplied.
    frames_declared: Optional[int] = None
    rate_fps: Optional[float] = None
    eta_s: Optional[float] = None
    elapsed_s: float = 0.0
    paused_s: float = 0.0
    issues: tuple[str, ...] = ()
    #: The subset of ``issues`` that kept the version out of the library.
    blocking_issues: tuple[str, ...] = ()
    #: Recorded frames and how many were found again in the replayed source.
    capture_frames: int = 0
    matched_frames: int = 0
    error: str = ""
    run_id: str = ""
    directory: Optional[Path] = None

    @property
    def published(self) -> bool:
        """Whether this attempt produced a version the screens can open."""
        return self.state in (JobState.COMPLETE, JobState.PARTIAL) and not self.blocking_issues

    @property
    def coverage_text(self) -> str:
        """Matched frames as a count, or "" when nothing was declared."""
        if not self.capture_frames:
            return ""
        if self.matched_frames >= self.capture_frames:
            return f"{self.capture_frames} karenin tamamı eşleşti"
        return f"{self.capture_frames} kareden {self.matched_frames} tanesi eşleşti"

    @property
    def fraction(self) -> Optional[float]:
        if not self.frames_declared:
            return None
        return min(1.0, self.frames_processed / float(self.frames_declared))

    @property
    def progress_text(self) -> str:
        """What to show. A percentage only when there is an honest denominator."""
        if self.frames_declared:
            return (
                f"İşlenen {self.frames_processed} / doğrulanmış "
                f"{self.frames_declared} kare"
            )
        return f"İşlenen {self.frames_processed} kare"

    @property
    def eta_text(self) -> str:
        if self.state is JobState.PAUSED:
            return "duraklatıldı"
        if self.eta_s is None:
            # Before the model has warmed up there is no rate worth quoting,
            # and a made-up estimate is worse than none.
            return "süre hesaplanıyor" if self.state is JobState.RUNNING else "—"
        minutes, seconds = divmod(int(self.eta_s), 60)
        return f"yaklaşık {minutes:02d}:{seconds:02d}"

    @property
    def issue_texts(self) -> tuple[str, ...]:
        return tuple(describe_issue(code) for code in self.issues)


@dataclass
class Job:
    """One processing attempt, and the child process running it."""

    take: TakeSummary
    progress: JobProgress = field(default_factory=JobProgress)
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    #: Where the attempt writes. Discovered after the child creates it.
    attempt_dir: Optional[Path] = None
    requested_cancel: bool = False
    requested_pause: bool = False

    @property
    def key(self) -> str:
        return self.take.take_id

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class ProcessingService:
    """Starts, pauses, cancels and follows offline processing jobs."""

    def __init__(self, *, python: Optional[str] = None) -> None:
        self._python = python or sys.executable
        self._jobs: dict[str, Job] = {}

    # ------------------------------------------------------------------ queue
    @property
    def jobs(self) -> tuple[Job, ...]:
        return tuple(self._jobs.values())

    def job_for(self, take_id: str) -> Optional[Job]:
        return self._jobs.get(take_id)

    @property
    def active_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.is_running)

    # ------------------------------------------------------------------ start
    def start(self, take: TakeSummary, *, parameters: Optional[dict] = None) -> Job:
        """Launch processing for one take in a child process."""
        if take.state == "recording":
            # Guarded here as well as in the interface: a directory a writer
            # still owns has no final frame count, no checksums and no
            # guarantee that what is read now is what will be there in a
            # second's time.
            raise ValueError(
                f"{take.take_id} hâlâ kaydediliyor; kapanmadan işlenemez."
            )
        existing = self._jobs.get(take.take_id)
        if existing is not None and existing.is_running:
            return existing
        command = [self._python, "-B", "-m", "kinecapture.processing", str(take.directory)]
        for flag, key in (
            ("--body-format", "body_format"),
            ("--depth-mode", "depth_mode"),
            ("--body-model", "body_model"),
        ):
            value = (parameters or {}).get(key)
            if value:
                command += [flag, str(value)]
        if (parameters or {}).get("store_depth") is False:
            command.append("--no-depth")
        if (parameters or {}).get("store_proxy") is False:
            command.append("--no-proxy")

        logger.info("İşleme başlatılıyor: %s", take.take_id)
        process = subprocess.Popen(  # noqa: S603 - our own module, fixed argv
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path.cwd()),
            creationflags=_creation_flags(),
        )
        job = Job(take=take, process=process, progress=JobProgress(state=JobState.RUNNING))
        self._jobs[take.take_id] = job
        return job

    # ----------------------------------------------------------------- control
    def cancel(self, take_id: str) -> bool:
        """Stop a job. **The raw recording is not touched.**"""
        job = self._jobs.get(take_id)
        if job is None or job.process is None:
            return False
        job.requested_cancel = True
        if job.process.poll() is None:
            job.process.terminate()
        return True

    def pause(self, take_id: str) -> bool:
        """Hold a job where it is, keeping what it has already done.

        Implemented by suspending the child process. A half-finished attempt
        directory is never published, so a paused job is simply a job that is
        not using the GPU right now.
        """
        job = self._jobs.get(take_id)
        if job is None or not job.is_running:
            return False
        if not _suspend(job.process):
            return False
        job.requested_pause = True
        job.progress = _replace_state(job.progress, JobState.PAUSED)
        return True

    def resume(self, take_id: str) -> bool:
        job = self._jobs.get(take_id)
        if job is None or not job.is_running or not job.requested_pause:
            return False
        if not _resume(job.process):
            return False
        job.requested_pause = False
        job.progress = _replace_state(job.progress, JobState.RUNNING)
        return True

    def pause_all(self) -> int:
        """Used when a live recording starts: give the GPU back, keep the work."""
        return sum(1 for job in list(self._jobs) if self.pause(job))

    def resume_all(self) -> int:
        return sum(1 for job in list(self._jobs) if self.resume(job))

    def shutdown(self) -> None:
        """Stop every child on the way out. Nothing half-finished is published."""
        for job in self._jobs.values():
            if job.process is not None and job.process.poll() is None:
                if job.requested_pause:
                    _resume(job.process)
                job.process.terminate()
        for job in self._jobs.values():
            if job.process is not None:
                try:
                    job.process.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover - stubborn child
                    job.process.kill()

    # ---------------------------------------------------------------- progress
    def poll(self) -> tuple[Job, ...]:
        """Re-read every job's state from disk. Cheap enough for a timer."""
        for job in self._jobs.values():
            if job.requested_pause and job.is_running:
                # Suspended: the file cannot move, so neither should the reading.
                continue
            job.attempt_dir = job.attempt_dir or self._find_attempt(job)
            progress = self._read_progress(job)
            if progress is not None:
                job.progress = progress
            self._settle(job)
        return self.jobs

    def _find_attempt(self, job: Job) -> Optional[Path]:
        base = Path(job.take.directory) / "derived" / "processing"
        try:
            names = os.listdir(long_path(base))
        except OSError:
            return None
        partial = sorted(n for n in names if n.startswith(".") and n.endswith(".partial"))
        if partial:
            return base / partial[-1]
        return None

    def _read_progress(self, job: Job) -> Optional[JobProgress]:
        directory = job.attempt_dir
        candidates: tuple[Path, ...] = ()
        if directory is not None:
            published = directory.parent / directory.name.lstrip(".").removesuffix(".partial")
            candidates = (directory / "job.json", published / "job.json")
        published_dir = candidates[1].parent if candidates else None
        for candidate in candidates:
            if not path_exists(candidate):
                continue
            try:
                payload = dict(read_json(candidate))
            except Exception:  # noqa: BLE001 - caught mid-write; try next poll
                return None
            staged = candidate.parent.name.startswith(".")
            will_publish = bool(payload.get("published")) or str(
                payload.get("state")
            ) == "complete"
            if (
                staged
                and will_publish
                and published_dir is not None
                and not path_exists(published_dir)
            ):
                # The child writes the final state, then the checksums, then
                # renames the folder. Announcing the result here sends the user
                # to a version that is not there yet, so the row keeps running
                # until the rename lands. ``partial`` gets published too now,
                # so it has to wait for the same rename.
                payload["state"] = "running"
            return _progress_from(payload, candidate.parent)
        return None

    def _settle(self, job: Job) -> None:
        """Give a finished child a final state, even if it never wrote one."""
        if job.process is None or job.process.poll() is None:
            return
        if job.progress.state.is_finished:
            return
        if job.requested_cancel:
            job.progress = _replace_state(job.progress, JobState.CANCELLED)
            return
        code = job.process.returncode
        if code == 0:
            job.progress = _replace_state(job.progress, JobState.COMPLETE)
            return
        if code == 1:
            # Published, with caveats the job file already lists.
            job.progress = _replace_state(job.progress, JobState.PARTIAL)
            return
        # A child that died without writing a state is a failure, and saying so
        # is better than leaving a row spinning forever.
        detail = ""
        try:
            _out, err = job.process.communicate(timeout=1)
            detail = (err or b"").decode("utf-8", "replace").strip()[-400:]
        except Exception:  # noqa: BLE001 - best effort
            detail = ""
        job.progress = _replace_state(
            job.progress, JobState.FAILED, error=detail or f"çıkış kodu {code}"
        )


def _progress_from(payload: dict[str, Any], directory: Path) -> JobProgress:
    raw_state = str(payload.get("state", "running"))
    try:
        state = JobState(raw_state)
    except ValueError:
        state = JobState.RUNNING
    declared = payload.get("source_frames_declared")
    return JobProgress(
        state=state,
        frames_processed=int(payload.get("frames_processed", 0) or 0),
        frames_declared=int(declared) if declared else None,
        rate_fps=payload.get("rate_fps"),
        eta_s=payload.get("eta_s"),
        elapsed_s=float(payload.get("elapsed_s", 0.0) or 0.0),
        paused_s=float(payload.get("paused_s", 0.0) or 0.0),
        issues=tuple(payload.get("issues") or ()),
        blocking_issues=tuple(payload.get("blocking_issues") or ()),
        capture_frames=int((payload.get("coverage") or {}).get("capture_frames", 0) or 0),
        matched_frames=int((payload.get("coverage") or {}).get("matched_frames", 0) or 0),
        error=str(payload.get("error") or ""),
        run_id=str(payload.get("run_id", "")),
        directory=directory,
    )


def _replace_state(progress: JobProgress, state: JobState, *, error: str = "") -> JobProgress:
    return JobProgress(
        state=state,
        frames_processed=progress.frames_processed,
        frames_declared=progress.frames_declared,
        rate_fps=progress.rate_fps,
        eta_s=progress.eta_s,
        elapsed_s=progress.elapsed_s,
        paused_s=progress.paused_s,
        issues=progress.issues,
        error=error or progress.error,
        run_id=progress.run_id,
        directory=progress.directory,
    )


def _creation_flags() -> int:
    """Windows: own process group, so a terminate does not hit this process."""
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _suspend(process: Optional[subprocess.Popen]) -> bool:
    if process is None or process.poll() is not None:
        return False
    try:
        import psutil  # noqa: PLC0415 - optional

        psutil.Process(process.pid).suspend()
        return True
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("İş duraklatılamadı: %s", exc)
        return False
    if hasattr(signal, "SIGSTOP"):  # pragma: no cover - not Windows
        try:
            os.kill(process.pid, signal.SIGSTOP)
            return True
        except OSError as exc:
            logger.warning("İş duraklatılamadı: %s", exc)
    logger.info("Bu platformda iş duraklatma desteklenmiyor; iptal kullanılabilir.")
    return False


def _resume(process: Optional[subprocess.Popen]) -> bool:
    if process is None or process.poll() is not None:
        return False
    try:
        import psutil  # noqa: PLC0415 - optional

        psutil.Process(process.pid).resume()
        return True
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("İş devam ettirilemedi: %s", exc)
        return False
    if hasattr(signal, "SIGCONT"):  # pragma: no cover - not Windows
        try:
            os.kill(process.pid, signal.SIGCONT)
            return True
        except OSError as exc:
            logger.warning("İş devam ettirilemedi: %s", exc)
    return False


def pause_supported() -> bool:
    """Whether this machine can hold a job rather than only cancel it."""
    if hasattr(signal, "SIGSTOP"):
        return True
    try:
        import psutil  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


__all__ = [
    "ISSUE_TEXT",
    "Job",
    "JobProgress",
    "JobState",
    "ProcessingService",
    "describe_issue",
    "pause_supported",
]
