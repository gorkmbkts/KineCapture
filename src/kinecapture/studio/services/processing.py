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
import time
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


class IssueAxis(str, Enum):
    """Which question an issue is an answer to.

    They were all one question until 20 September: a version that matched 1473
    of 1475 source frames and an informational note about when the athlete was
    chosen produced the same sentence - "Bu sürümün kaynak kapsamı
    doğrulanamadı" - as a version with a real hole in it. Meanwhile the thing
    that was actually wrong with that recording, the person being tracked in
    622 frames out of 1473, was not mentioned at all.
    """

    #: Frames of the raw recording that could not be found again or matched.
    SOURCE = "source"
    #: Timestamp quality: gaps, duplicates, ordering.
    TIMING = "timing"
    #: Whether the chosen person was found and held.
    SUBJECT = "subject"
    #: The preview video. Never affects the data.
    PROXY = "proxy"
    #: Something worth recording that took nothing away.
    NOTE = "note"
    #: A code this build has never heard of. Its own axis so that no filter
    #: can quietly drop it: an unrecognised problem is still a problem.
    UNKNOWN = "unknown"


class IssueWeight(str, Enum):
    """How much an issue costs the person about to use the version."""

    #: Recorded, nothing missing. Does not make a version "unverified".
    NOTE = "note"
    #: Something is genuinely incomplete; the version is still usable.
    CAUTION = "caution"
    #: The version could not be published at all.
    BLOCKING = "blocking"


@dataclass(frozen=True)
class IssueMeaning:
    """One issue code, in a sentence, on one axis, with a weight."""

    text: str
    axis: IssueAxis = IssueAxis.NOTE
    weight: IssueWeight = IssueWeight.CAUTION


#: The contract. An unmapped code is shown verbatim, on no axis, and weighed as
#: a caution - an unknown problem is never rounded down to harmless.
ISSUE_CATALOGUE: dict[str, IssueMeaning] = {
    "source_frame_count_mismatch": IssueMeaning(
        "Dosya başlığındaki kare sayısı ile okunan kare sayısı farklı.",
        IssueAxis.SOURCE,
        IssueWeight.CAUTION,
    ),
    "capture_frames_unmatched": IssueMeaning(
        "Kayıt sırasındaki bazı kareler ham kaynakta eşleştirilemedi.",
        IssueAxis.SOURCE,
        IssueWeight.CAUTION,
    ),
    "source_empty": IssueMeaning(
        "Kaynaktan hiç kare okunamadı.", IssueAxis.SOURCE, IssueWeight.BLOCKING
    ),
    "source_capture_timestamp_unmatched_or_ambiguous": IssueMeaning(
        "Bazı karelerin zaman damgası kayıt indeksiyle birebir eşleşmedi.",
        IssueAxis.TIMING,
        IssueWeight.CAUTION,
    ),
    "capture_timestamp_duplicated": IssueMeaning(
        "Kamera iki kareye aynı mikrosaniyeyi verdi; kareler sırayla eşleştirildi.",
        IssueAxis.TIMING,
        # Resolved by acquisition order, and recorded so it can be checked.
        # Nothing was dropped, so this never made a version incomplete.
        IssueWeight.NOTE,
    ),
    "source_timestamp_gap": IssueMeaning(
        "Kaynakta zaman damgası boşluğu var.", IssueAxis.TIMING, IssueWeight.CAUTION
    ),
    "source_timestamp_non_monotonic": IssueMeaning(
        "Kaynakta zaman damgası geriye gitti.", IssueAxis.TIMING, IssueWeight.CAUTION
    ),
    "source_position_discontinuity": IssueMeaning(
        "Kaynak kare sırası kesintili.", IssueAxis.TIMING, IssueWeight.CAUTION
    ),
    "subject_anchor_unresolved": IssueMeaning(
        "Seçilen kişi o karede tek başına bulunamadı; kişi ataması yapılmadı.",
        IssueAxis.SUBJECT,
        IssueWeight.CAUTION,
    ),
    "subject_anchor_outside_source": IssueMeaning(
        "Seçim, ham kaynakta bulunmayan bir zaman damgasına işaret ediyor.",
        IssueAxis.SUBJECT,
        IssueWeight.CAUTION,
    ),
    "subject_anchor_before_recording": IssueMeaning(
        "Kişi seçimi kayıt başlamadan önce yapılmış; ilk kareye uygulandı.",
        IssueAxis.SUBJECT,
        # Applying the operator's own choice to the first frame is what was
        # meant. Nothing is missing and nothing was guessed.
        IssueWeight.NOTE,
    ),
    "review_proxy_unavailable": IssueMeaning(
        "Önizleme videosu üretilemedi; iskelet ve veriler etkilenmedi.",
        IssueAxis.PROXY,
        IssueWeight.NOTE,
    ),
    "review_proxy_desynchronised": IssueMeaning(
        "Önizleme videosunun kare sayısı sürümle uyuşmuyor.",
        IssueAxis.PROXY,
        IssueWeight.CAUTION,
    ),
    # Written by versions produced before the code was split in two. Kept so
    # an older job file still reads as a sentence instead of as a code.
    "review_proxy_incomplete": IssueMeaning(
        "Önizleme videosu eksik üretildi.", IssueAxis.PROXY, IssueWeight.CAUTION
    ),
    "requested_depth_missing": IssueMeaning(
        "İstenen derinlik bazı karelerde üretilemedi.",
        IssueAxis.SOURCE,
        IssueWeight.CAUTION,
    ),
    "calibration_invalid_or_missing": IssueMeaning(
        "Kamera kalibrasyonu okunamadı.", IssueAxis.SOURCE, IssueWeight.CAUTION
    ),
}

#: An unknown code. Named rather than inlined so every reader treats one the
#: same way, and so the way is visible.
UNKNOWN_ISSUE = IssueMeaning("", IssueAxis.UNKNOWN, IssueWeight.CAUTION)


def issue_meaning(code: str) -> IssueMeaning:
    known = ISSUE_CATALOGUE.get(code)
    if known is not None:
        return known
    return IssueMeaning(code, UNKNOWN_ISSUE.axis, UNKNOWN_ISSUE.weight)


def issues_on(codes, axis: IssueAxis) -> tuple[str, ...]:
    """Which of ``codes`` speak to one axis."""
    return tuple(code for code in codes if issue_meaning(code).axis is axis)


def material_issues(codes) -> tuple[str, ...]:
    """Those that actually took something away. Notes are not among them."""
    return tuple(
        code for code in codes if issue_meaning(code).weight is not IssueWeight.NOTE
    )


#: Backwards-compatible view of the catalogue, kept because several screens and
#: tests read it directly.
ISSUE_TEXT = {code: meaning.text for code, meaning in ISSUE_CATALOGUE.items()}


def describe_issue(code: str) -> str:
    return issue_meaning(code).text or code


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
    #: Everything the child printed. See :meth:`ProcessingService.start`.
    log_path: Optional[Path] = None

    @property
    def key(self) -> str:
        return self.take.take_id

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class ProcessingService:
    """Starts, pauses, cancels and follows offline processing jobs."""

    def __init__(
        self, *, python: Optional[str] = None, log_dir: Optional[Path] = None
    ) -> None:
        self._python = python or sys.executable
        self._jobs: dict[str, Job] = {}
        #: Where each child's stdout and stderr go. See :meth:`start`.
        self._log_dir = Path(log_dir) if log_dir is not None else _default_log_dir()

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
        command = self._command(take, parameters)

        # The child's output goes to a file, never to a pipe. Nothing reads a
        # pipe while the child runs, so a child that printed more than the
        # pipe holds - the ZED SDK reporting model optimisation, a run of
        # warnings - blocked on its next write and stayed "running" for ever
        # (measured: a 1 MB write, still blocked after 20 s; release gate,
        # 23 September 2026). A file never fills up that way, and it is the
        # place the reason for a failure can be read afterwards.
        # The working directory is the log folder: short, the user's own, and
        # never an installation folder a ``-m`` import could be shadowed from.
        directory = Path(self._log_dir)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A log folder that cannot be made must not cost the job.
            import tempfile

            directory = Path(tempfile.gettempdir()) / "kinecapture-processing"
            directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / f"{take.take_id}_{time.strftime('%Y%m%dT%H%M%S')}.log"
        logger.info("İşleme başlatılıyor: %s (çıktı: %s)", take.take_id, log_path)
        with open(log_path, "ab") as log:
            process = subprocess.Popen(  # noqa: S603 - our own module, fixed argv
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=str(directory),
                env=_child_environment(),
                creationflags=_creation_flags(),
            )
        job = Job(
            take=take,
            process=process,
            progress=JobProgress(state=JobState.RUNNING),
            log_path=log_path,
        )
        self._jobs[take.take_id] = job
        return job

    def _command(self, take: TakeSummary, parameters: Optional[dict]) -> list[str]:
        """The child's argv: this interpreter, the processing module, the take."""
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
        return command

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
        # is better than leaving a row spinning forever. Why it died is the
        # end of what it printed.
        detail = _tail(job.log_path)
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
    """Windows: own process group, and no console window.

    The group keeps a terminate aimed at the child from reaching this process.
    ``CREATE_NO_WINDOW`` matters once the application runs as ``pythonw.exe``
    from its shortcut: a console child of a console-less parent otherwise gets
    a console window of its own, flashing up for every processing job.
    """
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )


def _default_log_dir() -> Path:
    """Next to the application log when there is one, else the temp folder."""
    from kinecapture.core.logging import log_file_path

    active = log_file_path()
    if active is not None:
        return active.parent / "processing"
    import tempfile

    return Path(tempfile.gettempdir()) / "kinecapture-processing"


def _child_environment() -> dict[str, str]:
    """The child's environment: this one, with its output in UTF-8.

    Redirected to a file, Python writes in the locale's code page - cp1254 on
    a Turkish Windows - and :func:`_tail` reads UTF-8, so the child's own
    Turkish messages reached the screen as "Dosya bulunamad�" (release gate
    B6, 23 September 2026).
    """
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _tail(path: Optional[Path], limit: int = 400) -> str:
    """The last ``limit`` characters a child printed, or an empty string."""
    if path is None:
        return ""
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 4 * limit))
            text = stream.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return text.strip()[-limit:]


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
