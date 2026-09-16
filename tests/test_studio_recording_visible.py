"""An open recording is visible everywhere, stoppable everywhere, and is not
a candidate for processing.

The 15 September audit moved to "Verileri Hesapla" while a take was running.
The RECORDING marker vanished with the Yakalama page, there was no way to stop
the take, and the still-open take appeared in the processing queue as "0 kare,
0 saniye". All three are checked here.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from kinecapture.dataset.summary_index import TakeSummary
from kinecapture.studio.services.processing import ProcessingService
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.capture import RecordingPhase, RecordingStatus
from kinecapture.studio.viewmodels.processing import OPEN_TAKE_STATE, ProcessingViewModel
from kinecapture.studio.viewmodels.shell import ShellViewModel


class _Camera:
    """Stands in for the Capture viewmodel: one status, one stop."""

    def __init__(self) -> None:
        self.status = RecordingStatus(
            phase=RecordingPhase.RECORDING,
            elapsed_s=41.0,
            frames=1231,
            target_text="P0002 · 20260914T2013",
        )
        self.stops = 0

    def read(self) -> RecordingStatus:
        return self.status

    def stop(self) -> bool:
        self.stops += 1
        self.status = replace(self.status, phase=RecordingPhase.CLOSING)
        return True


@pytest.fixture
def shell(tmp_path) -> ShellViewModel:
    from kinecapture.core.config import AppConfig

    config = AppConfig()
    config.dataset_root = tmp_path / "datasets"
    config.identity_db_path = tmp_path / "identity.sqlite3"
    session = SessionService(config=config, identity=None)
    return ShellViewModel(session)


# ------------------------------------------------------------ the indicator
def test_the_shell_shows_no_recording_before_a_camera_exists(shell) -> None:
    assert shell.recording.value.phase is RecordingPhase.IDLE
    assert shell.recording.value.is_open is False
    assert shell.stop_recording() is False


def test_the_recording_is_visible_from_every_page(shell) -> None:
    camera = _Camera()
    shell.set_recording_source(camera.read, camera.stop)
    for key in [item.key for item in shell.destinations]:
        shell.navigate(key)
        shell.refresh_context()
        status = shell.recording.value
        assert status.is_open is True, f"{key} lost the recording indicator"
        assert "P0002" in status.target_text
        assert status.elapsed_text == "00:41"


def test_stopping_from_another_page_works_once(shell) -> None:
    camera = _Camera()
    shell.set_recording_source(camera.read, camera.stop)
    shell.navigate("processing")
    assert shell.stop_recording() is True
    assert camera.stops == 1
    # Now closing: the take is already on its way down, so a second press must
    # not start a second finalisation.
    assert shell.recording.value.phase is RecordingPhase.CLOSING
    assert shell.stop_recording() is True  # still open, still one stop path
    assert camera.stops == 2

    camera.status = RecordingStatus()
    shell.refresh_recording()
    assert shell.stop_recording() is False
    assert camera.stops == 2


def test_the_phases_have_distinct_words() -> None:
    words = {
        phase: RecordingStatus(phase=phase).phase_text for phase in RecordingPhase
    }
    assert len(set(words.values())) == len(RecordingPhase)
    assert RecordingStatus(phase=RecordingPhase.CLOSING).is_open is True
    assert RecordingStatus(phase=RecordingPhase.PREPARING).is_open is False


# --------------------------------------------------------- processing queue
def _take(take_id: str, state: str) -> TakeSummary:
    return TakeSummary(
        take_id=take_id,
        participant_id="p1",
        session_id="s1",
        directory=f"C:/nowhere/{take_id}",
        started_at="2026-09-14T20:13:08",
        state=state,
        processing_status="awaiting_processing",
        frames=0 if state == OPEN_TAKE_STATE else 1231,
    )


class _Index(list):
    def with_complete_runs(self):  # noqa: ANN201
        return []

    def legacy_takes(self):  # noqa: ANN201
        return []


def test_an_open_take_is_kept_out_of_the_waiting_list(shell, tmp_path) -> None:
    viewmodel = ProcessingViewModel(shell.session, service=ProcessingService())
    viewmodel._index = _Index([_take("take_open", OPEN_TAKE_STATE), _take("take_done", "finalized")])
    viewmodel._refill()

    assert [t.take_id for t in viewmodel.waiting.value] == ["take_done"]
    assert [t.take_id for t in viewmodel.open_takes.value] == ["take_open"]
    assert "hâlâ açık" in viewmodel.summary.value


def test_starting_an_open_take_is_refused_with_a_reason(shell) -> None:
    viewmodel = ProcessingViewModel(shell.session, service=ProcessingService())
    seen = []
    viewmodel.message.subscribe(seen.append)
    assert viewmodel.start(_take("take_open", OPEN_TAKE_STATE)) is False
    assert [m.code for m in seen] == ["take_still_recording"]


def test_the_service_refuses_an_open_take_too() -> None:
    """The guard is not only in the screen: the queue is not the only caller."""
    with pytest.raises(ValueError, match="kaydediliyor"):
        ProcessingService().start(_take("take_open", OPEN_TAKE_STATE))
