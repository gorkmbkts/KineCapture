"""Verileri Hesapla: the queue, and what it is allowed to claim.

The rules worth protecting here are about honesty rather than plumbing. A
percentage is only shown where the source declared a frame count. A run whose
coverage could not be verified is never called complete. And cancelling frees
the GPU without touching the recording - which the screen says out loud,
because an operator should not have to guess.

The child process is real: these tests launch ``python -m
kinecapture.processing`` against a take recorded through the mock backend.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from kinecapture.core.config import AppConfig
from kinecapture.dataset.summary_index import TakeSummary, build_index
from kinecapture.domain.enums import BackendKind
from kinecapture.studio.services.processing import (
    ISSUE_TEXT,
    Job,
    JobProgress,
    JobState,
    ProcessingService,
    describe_issue,
    pause_supported,
)
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.capture import CaptureViewModel
from kinecapture.studio.viewmodels.processing import CANCEL_NOTE, ProcessingViewModel
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from kinecapture.studio.viewmodels.tasks import InlineRunner


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    settings = AppConfig()
    settings.dataset_root = tmp_path / "d"
    settings.identity_db_path = tmp_path / "id.sqlite3"
    settings.log_dir = tmp_path / "l"
    settings.dataset_root.mkdir(parents=True)
    settings.backend = BackendKind.MOCK
    settings.extra["preview_pose_enabled"] = False
    return settings


@pytest.fixture
def session(config: AppConfig, monkeypatch: pytest.MonkeyPatch) -> SessionService:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    service = SessionService.open(config)
    auth = AuthViewModel(service)
    assert auth.create_owner(
        first_name="Ada", last_name="Lovelace", title="",
        username="ada", password="kinecapture1", password_confirm="kinecapture1",
    )
    projects = ProjectsViewModel(service, InlineRunner())
    projects.reload_projects()
    assert projects.create_project("Squat")
    assert projects.create_participant()
    return service


@pytest.fixture
def recorded(session: SessionService) -> SessionService:
    """One short raw take, recorded through the mock backend."""
    capture = CaptureViewModel(session)
    assert capture.connect()
    try:
        assert capture.start_recording()
        time.sleep(0.7)
        assert capture.stop_recording()
    finally:
        capture.disconnect()
    return session


@pytest.fixture
def processing(recorded: SessionService) -> ProcessingViewModel:
    viewmodel = ProcessingViewModel(recorded, runner=InlineRunner())
    yield viewmodel
    viewmodel.shutdown()


# ------------------------------------------------------------------ honesty


def test_no_percentage_without_a_declared_total() -> None:
    """An undeclared source count has no honest denominator, so none is used."""
    progress = JobProgress(
        state=JobState.RUNNING, frames_processed=412, frames_declared=None
    )
    assert progress.fraction is None
    assert progress.progress_text == "İşlenen 412 kare"
    assert "%" not in progress.progress_text


def test_a_declared_total_gives_both_numbers() -> None:
    progress = JobProgress(
        state=JobState.RUNNING, frames_processed=412, frames_declared=900
    )
    assert progress.fraction == pytest.approx(412 / 900)
    assert progress.progress_text == "İşlenen 412 / doğrulanmış 900 kare"


def test_no_estimate_before_there_is_a_rate() -> None:
    """A guess made from model warm-up is worse than saying nothing yet."""
    warming = JobProgress(state=JobState.RUNNING, eta_s=None)
    assert warming.eta_text == "süre hesaplanıyor"
    running = JobProgress(state=JobState.RUNNING, eta_s=125.0)
    assert running.eta_text == "yaklaşık 02:05"
    assert JobProgress(state=JobState.PAUSED).eta_text == "duraklatıldı"


def test_partial_is_never_called_complete() -> None:
    assert JobState.PARTIAL.is_finished
    assert JobState.PARTIAL is not JobState.COMPLETE


def test_coverage_issues_are_explained_not_shown_as_codes() -> None:
    """A sentence about what happened, not a verdict and not a code.

    This one used to read "kaynak kapsamı doğrulanamadı", which is a judgement
    about the whole version for what is a one-frame disagreement between the
    SVO header and its playback.
    """
    text = describe_issue("source_frame_count_mismatch")
    assert "kare sayısı" in text
    assert "_" not in text
    # An unknown code is shown as-is rather than silently dropped.
    assert describe_issue("brand_new_code") == "brand_new_code"


def test_every_mapped_issue_reads_as_a_sentence() -> None:
    for code, text in ISSUE_TEXT.items():
        assert text.strip().endswith("."), code
        assert code not in text


def test_cancelling_says_the_recording_is_safe() -> None:
    assert "ham kaydı silmez" in CANCEL_NOTE.casefold()


def test_a_finished_version_is_announced_with_a_link_to_itself(
    processing: ProcessingViewModel, recorded: SessionService
) -> None:
    """"Sürümü incele" has to reach the version, not a list that may not have it.

    On 16 September it pointed at İşlenen Videolar, which was empty - the
    version it was announcing had never been published. The link now carries
    the folder, so it opens that version in Etiketleme either way.
    """
    processing.reload(force=True)
    take = processing.waiting.value[0]
    directory = Path(take.directory) / "derived" / "processing" / "run_done"
    job = Job(take=take)
    job.progress = JobProgress(
        state=JobState.PARTIAL,
        frames_processed=522,
        issues=("capture_frames_unmatched",),
        capture_frames=524,
        matched_frames=522,
        directory=directory,
    )
    seen: list = []
    processing.message.subscribe(seen.append)
    processing._report_if_finished(job)  # noqa: SLF001 - that is what is under test

    assert len(seen) == 1
    message = seen[0]
    assert message.actions[0].key == f"review:{directory}"
    assert message.actions[0].primary
    # And it says how much matched instead of only that something did not.
    assert "522" in message.detail and "524" in message.detail


# -------------------------------------------------------------------- queue


def test_a_raw_take_is_listed_as_waiting(processing: ProcessingViewModel) -> None:
    processing.reload(force=True)
    assert len(processing.waiting.value) == 1
    assert "işlenmeyi bekliyor" in processing.summary.value


def test_a_take_with_a_finished_version_is_not_waiting(
    processing: ProcessingViewModel, recorded: SessionService
) -> None:
    processing.reload(force=True)
    take = processing.waiting.value[0]
    run = Path(take.directory) / "derived" / "processing" / "run_done"
    run.mkdir(parents=True)
    (run / "job.json").write_text(
        json.dumps({"run_id": "run_done", "state": "complete", "frames_processed": 10}),
        encoding="utf-8",
    )
    processing.reload(force=True)
    assert processing.waiting.value == ()
    assert "1 kayıt işlenmiş" in processing.summary.value


def test_pre_policy_takes_are_not_offered_for_processing(
    processing: ProcessingViewModel, recorded: SessionService
) -> None:
    """Old recordings stay on disk and stay listed elsewhere, but not here."""
    processing.reload(force=True)
    take = processing.waiting.value[0]
    metadata = Path(take.directory) / "take.json"
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["processing_status"] = "live"
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    processing.reload(force=True)
    assert processing.waiting.value == ()
    assert "eski biçim" in processing.summary.value


def test_without_a_project_the_screen_says_so(config: AppConfig, monkeypatch) -> None:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    service = SessionService.open(config)
    viewmodel = ProcessingViewModel(service, runner=InlineRunner())
    viewmodel.reload()
    assert viewmodel.waiting.value == ()
    assert "proje" in viewmodel.summary.value.casefold()


#: Under pytest's temp root the take path is long enough that OpenCV refuses
#: to open the proxy file, so processing honestly reports the version as
#: partial. That is the environment, not the code under test: these tests are
#: about the child process finishing, so a run whose *only* complaint is the
#: proxy counts as finished.
_PATH_LENGTH_ISSUES = frozenset({"review_proxy_unavailable", "review_proxy_incomplete"})


def assert_finished_cleanly(progress) -> None:  # noqa: ANN001 - JobProgress
    if progress.state is JobState.COMPLETE:
        return
    remaining = set(progress.issues) - _PATH_LENGTH_ISSUES
    assert progress.state is JobState.PARTIAL and not remaining, (
        f"{progress.state.value}: {progress.error} {progress.issues}"
    )


# ------------------------------------------------------------- child process


@pytest.mark.slow
def test_a_job_runs_in_a_child_process_and_finishes(
    processing: ProcessingViewModel,
) -> None:
    processing.reload(force=True)
    take = processing.waiting.value[0]
    assert processing.start(take)

    job = processing.service.job_for(take.take_id)
    assert job is not None
    # Genuinely another process: the SDK is opened there, not here.
    assert job.process is not None
    assert job.process.pid != 0

    deadline = time.time() + 240
    while time.time() < deadline:
        processing.poll()
        if processing.service.job_for(take.take_id).progress.state.is_finished:
            break
        time.sleep(0.1)

    progress = processing.service.job_for(take.take_id).progress
    assert_finished_cleanly(progress)
    assert progress.frames_processed > 0
    assert progress.frames_declared == progress.frames_processed


@pytest.mark.slow
def test_cancelling_stops_the_job_and_keeps_the_recording(
    processing: ProcessingViewModel,
) -> None:
    processing.reload(force=True)
    take = processing.waiting.value[0]
    raw = Path(take.directory) / "raw"
    before = sorted(p.name for p in raw.rglob("*") if p.is_file())

    assert processing.start(take)
    seen = []
    processing.message.subscribe(seen.append)
    time.sleep(0.4)
    assert processing.cancel(take.take_id)

    deadline = time.time() + 60
    while time.time() < deadline:
        processing.poll()
        if processing.service.job_for(take.take_id).progress.state.is_finished:
            break
        time.sleep(0.1)

    # The raw recording is untouched - the whole point of the message.
    assert sorted(p.name for p in raw.rglob("*") if p.is_file()) == before
    assert any(m.code == "processing_cancelled" for m in seen)
    assert any("ham kaydı silmez" in m.detail.casefold() for m in seen if m.detail)


@pytest.mark.skipif(not pause_supported(), reason="bu makinede duraklatma yok")
@pytest.mark.slow
def test_pausing_holds_the_work_instead_of_discarding_it(
    processing: ProcessingViewModel,
) -> None:
    processing.reload(force=True)
    take = processing.waiting.value[0]
    assert processing.start(take)
    time.sleep(0.5)
    processing.poll()

    assert processing.pause(take.take_id)
    held = processing.service.job_for(take.take_id)
    assert held.progress.state is JobState.PAUSED
    frames_at_pause = held.progress.frames_processed

    time.sleep(0.8)
    processing.poll()
    # Held, not running: the count cannot have moved.
    assert processing.service.job_for(take.take_id).progress.frames_processed == frames_at_pause

    assert processing.resume(take.take_id)
    deadline = time.time() + 240
    while time.time() < deadline:
        processing.poll()
        if processing.service.job_for(take.take_id).progress.state.is_finished:
            break
        time.sleep(0.1)
    progress = processing.service.job_for(take.take_id).progress
    assert_finished_cleanly(progress)
    # Resumed rather than restarted: it finished the frames it already had.
    assert progress.frames_processed >= frames_at_pause


def test_a_dead_child_becomes_a_reported_failure(
    processing: ProcessingViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that spins forever is worse than one that says it failed."""
    import subprocess
    import sys

    processing.reload(force=True)
    take = processing.waiting.value[0]

    real_popen = subprocess.Popen

    def fake(_command, **kwargs):  # noqa: ANN001
        return real_popen([sys.executable, "-c", "raise SystemExit(3)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", fake)
    assert processing.start(take)

    seen = []
    processing.message.subscribe(seen.append)
    deadline = time.time() + 60
    while time.time() < deadline:
        processing.poll()
        if processing.service.job_for(take.take_id).progress.state.is_finished:
            break
        time.sleep(0.05)

    progress = processing.service.job_for(take.take_id).progress
    assert progress.state is JobState.FAILED
    assert any(m.code == "processing_failed" for m in seen)
    assert any("ham kayıt güvende" in m.detail.casefold() for m in seen if m.detail)


def test_shutdown_stops_every_child(processing: ProcessingViewModel) -> None:
    processing.reload(force=True)
    take = processing.waiting.value[0]
    assert processing.start(take)
    job = processing.service.job_for(take.take_id)
    processing.shutdown()
    assert job.process.poll() is not None
