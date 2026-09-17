"""The Capture screen: a whole round through the mock backend.

The distinctions checked here are the ones that make the screen honest rather
than merely working - preview loss kept apart from recording loss, the subject
anchor bound to the frame the operator was looking at, and a finished take
reported as *waiting for a skeleton* instead of as a failure.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from kinecapture.core.config import AppConfig
from kinecapture.core.errors import CameraError
from kinecapture.studio.services.capture import (
    PREVIEW_POSE_DISCLAIMER,
    CaptureMetrics,
    CaptureService,
    SubjectAnchor,
)
from kinecapture.studio.services.messages import Severity
from kinecapture.studio.services.session import SessionService
from kinecapture.studio.viewmodels.auth import AuthViewModel
from kinecapture.studio.viewmodels.capture import (
    RECORDING_MODES,
    AlertLevel,
    CaptureViewModel,
)
from kinecapture.studio.viewmodels.projects import ProjectsViewModel
from conftest import choose_subject
from kinecapture.studio.viewmodels.tasks import InlineRunner


@pytest.fixture
def config(tmp_path: Path) -> AppConfig:
    settings = AppConfig()
    settings.dataset_root = tmp_path / "datasets"
    settings.identity_db_path = tmp_path / "identity.sqlite3"
    settings.log_dir = tmp_path / "logs"
    settings.dataset_root.mkdir(parents=True)
    settings.backend = "mock"
    # No preview models in a test environment, and none needed: the overlay is
    # a convenience and its absence must not stop a recording.
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
def capture(session: SessionService) -> CaptureViewModel:
    viewmodel = CaptureViewModel(session)
    yield viewmodel
    viewmodel.disconnect()


# ----------------------------------------------------------------- the rules


def test_the_overlay_says_what_it_is_not(capture: CaptureViewModel) -> None:
    """It is a framing aid, not the skeleton and not an identity."""
    text = PREVIEW_POSE_DISCLAIMER
    assert "metrik iskelet değildir" in text.casefold()
    assert "katılımcı kimliği taşımaz" in text.casefold()
    assert capture.pose_note.value == text


def test_the_two_recording_modes_are_offered_and_priced() -> None:
    keys = {mode.key for mode in RECORDING_MODES}
    assert keys == {"raw_only", "live_skeleton"}
    live = next(m for m in RECORDING_MODES if m.key == "live_skeleton")
    # The expensive one says so before it is chosen, not after.
    assert live.cost


def test_preview_loss_and_recording_loss_are_different_numbers() -> None:
    metrics = CaptureMetrics(preview_dropped=40, recording_dropped=0)
    assert metrics.has_recording_loss is False
    assert CaptureMetrics(recording_dropped=1).has_recording_loss is True
    assert CaptureMetrics(backend_dropped=1).has_recording_loss is True


# ------------------------------------------------------------------ lifecycle


def test_disconnected_is_reported_before_anything_else(
    capture: CaptureViewModel,
) -> None:
    capture.refresh()
    assert [alert.key for alert in capture.alerts.value] == ["disconnected"]


def test_connecting_starts_the_preview(capture: CaptureViewModel) -> None:
    assert capture.connect()
    time.sleep(0.3)
    capture.refresh()
    metrics = capture.metrics.value
    assert metrics.connected
    assert metrics.frames_acquired > 0
    assert not [a for a in capture.alerts.value if a.key == "disconnected"]


def test_a_failure_to_connect_is_reported_not_raised(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise CameraError("Kamera bulunamadı.", code="camera_unavailable")

    monkeypatch.setattr(capture.service, "connect", boom)
    seen = []
    capture.message.subscribe(seen.append)
    assert capture.connect() is False
    assert seen and seen[0].severity.value == "error"


def test_a_missing_pose_model_does_not_stop_capture(
    session: SessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The overlay is a convenience; the recording is the point."""
    session.config.extra["preview_pose_enabled"] = True
    service = CaptureService(session.config)
    service._pose_factory = lambda: (_ for _ in ()).throw(FileNotFoundError("model yok"))
    viewmodel = CaptureViewModel(session, service)
    try:
        assert viewmodel.connect() is True
        assert "kullanılamıyor" in viewmodel.pose_note.value.casefold()
        time.sleep(0.2)
        viewmodel.refresh()
        assert viewmodel.metrics.value.frames_acquired > 0
    finally:
        viewmodel.disconnect()


# ------------------------------------------------------------------ recording


def test_a_full_round_produces_a_take_waiting_for_its_skeleton(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert capture.connect()
    seen = []
    capture.message.subscribe(seen.append)
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    time.sleep(0.8)
    capture.refresh()
    assert capture.metrics.value.recording is True
    assert capture.metrics.value.recorded_frames > 0
    assert capture.stop_recording()

    take = capture.service.last_take
    assert take is not None
    assert take.state.value == "finalized"
    # Not a failure, and not "done": the skeleton has not been computed yet.
    assert take.processing_status == "awaiting_processing"
    final = seen[-1]
    assert final.code == "awaiting_processing"
    assert "İskelet bekliyor" in final.headline


def test_no_recorded_frames_are_lost_with_the_preview_running(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interface may skip preview frames; it may not cost recorded ones."""
    assert capture.connect()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    time.sleep(1.0)
    capture.refresh()
    metrics = capture.metrics.value
    capture.stop_recording()
    assert metrics.recorded_frames > 0
    assert metrics.recording_dropped == 0, "kayıt kaybı oldu"


def test_recording_needs_a_project(config: AppConfig, monkeypatch) -> None:
    monkeypatch.setattr(
        "kinecapture.studio.services.session.save_user_state", lambda _c: None
    )
    service = SessionService.open(config)
    viewmodel = CaptureViewModel(service)
    seen = []
    viewmodel.message.subscribe(seen.append)
    assert viewmodel.start_recording() is False
    assert seen and "proje" in seen[0].headline.casefold()


def test_an_empty_project_gets_a_participant_rather_than_a_dead_button(
    session: SessionService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recording into an empty project creates its first participant.

    This used to refuse, and the screen disabled the button to match. On a
    real ZED that was a camera showing a live image with a record button that
    did nothing and said nothing. There is no ambiguity to protect in an empty
    project, so the participant is created and *named* instead.
    """
    import shutil

    workspace = session.workspace
    assert workspace is not None
    shutil.rmtree(workspace.participants_dir)
    workspace.participants_dir.mkdir()
    viewmodel = CaptureViewModel(session)
    seen = []
    viewmodel.message.subscribe(seen.append)
    assert viewmodel.connect()
    try:
        choose_subject(viewmodel, monkeypatch)
        assert viewmodel.start_recording() is True
        participants = workspace.list_participants()
        assert len(participants) == 1
        code = participants[0].code
        created = [m for m in seen if m.code == "participant_created"]
        assert created, "the new participant has to be announced, not assumed"
        # Named in the message, whatever the code allocator hands out - codes
        # are never reused, so it is not necessarily P0001.
        assert code in created[0].headline
        # And the take really belongs to it.
        assert viewmodel.target.value.participant_code == code
    finally:
        viewmodel.stop_recording()
        viewmodel.disconnect()


def test_an_unselected_participant_is_chosen_out_loud(
    session: SessionService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With several to pick from, the one used is named so it can be corrected."""
    workspace = session.workspace
    assert workspace is not None
    workspace.create_participant()
    assert len(workspace.list_participants()) >= 2
    session.select_participant("")

    viewmodel = CaptureViewModel(session)
    seen = []
    viewmodel.message.subscribe(seen.append)
    assert viewmodel.connect()
    try:
        choose_subject(viewmodel, monkeypatch)
        assert viewmodel.start_recording() is True
        defaulted = [m for m in seen if m.code == "capture_target_defaulted"]
        assert defaulted, "a defaulted target must be visible, not silent"
        assert defaulted[0].severity is Severity.WARNING
        assert viewmodel.target.value.is_set
    finally:
        viewmodel.stop_recording()
        viewmodel.disconnect()


# -------------------------------------------------------------------- subject


class _FakePreview:
    """Stands in for the pose preview, with two people in known boxes."""

    class _Person:
        def __init__(self, box) -> None:
            self.bbox = np.asarray(box, dtype=np.float32).reshape(2, 2)
            self.points = np.zeros((33, 2), dtype=np.float32)
            self.confidence = np.ones(33, dtype=np.float32)

    def __init__(self, packet) -> None:  # noqa: ANN001
        self.packet = packet
        self.people = (
            self._Person([[10, 10], [100, 200]]),
            self._Person([[300, 10], [400, 200]]),
        )

    def anchor(self, x: float, y: float) -> dict:
        from kinecapture.preview.pose import PosePreview

        return PosePreview.anchor(self, x, y)  # reuse the real rule


def test_an_anchor_is_bound_to_the_frame_that_was_shown(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolved against the displayed frame, never a freshly grabbed one."""
    assert capture.connect()
    time.sleep(0.3)
    packet = capture.service.latest_frame()
    assert packet is not None
    preview = _FakePreview(packet)
    monkeypatch.setattr(capture.service, "pose_preview", lambda: preview)

    assert capture.select_subject(50.0, 100.0)
    anchor = capture.anchor.value
    assert isinstance(anchor, SubjectAnchor)
    assert anchor.camera_timestamp_ns == packet.camera_timestamp_ns
    assert anchor.source_resolution == tuple(packet.resolution)
    assert anchor.point_xy == (50.0, 100.0)


def test_an_ambiguous_click_is_refused_not_guessed(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wrong person in the dataset is worse than asking again."""
    assert capture.connect()
    time.sleep(0.3)
    packet = capture.service.latest_frame()
    preview = _FakePreview(packet)
    monkeypatch.setattr(capture.service, "pose_preview", lambda: preview)

    seen = []
    capture.message.subscribe(seen.append)
    # A point inside neither box: nothing is selected and nothing is invented.
    assert capture.select_subject(200.0, 100.0) is False
    assert capture.anchor.value is None
    assert seen and seen[-1].code == "subject_anchor_ambiguous"


def test_an_anchor_is_written_next_to_the_raw_recording(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    assert capture.connect()
    choose_subject(capture, monkeypatch)
    assert capture.start_recording()
    time.sleep(0.4)
    packet = capture.service.latest_frame()
    monkeypatch.setattr(capture.service, "pose_preview", lambda: _FakePreview(packet))
    assert capture.select_subject(50.0, 100.0)
    capture.stop_recording()

    take = capture.service.last_take
    workspace = capture._session.workspace  # noqa: SLF001 - test reaches in
    paths = workspace.take_paths(take)
    anchors = json.loads((paths.raw_dir / "subject_anchors.json").read_text("utf-8"))
    # Two: the one made before recording started, which is how an operator
    # actually works, and this one. Every choice is kept, in the order it was
    # made, and the raw recording is never rewritten.
    assert len(anchors) == 2
    assert anchors[-1]["camera_timestamp_ns"] == packet.camera_timestamp_ns
    # The anchor says what it is: a selection to be resolved later, not an
    # identity already established.
    assert "requires_offline_association" in anchors[-1]["identity_semantics"]


def test_clearing_the_subject_leaves_the_recording_alone(
    capture: CaptureViewModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert capture.connect()
    time.sleep(0.2)
    packet = capture.service.latest_frame()
    monkeypatch.setattr(capture.service, "pose_preview", lambda: _FakePreview(packet))
    assert capture.select_subject(50.0, 100.0)
    capture.clear_subject()
    assert capture.anchor.value is None


# --------------------------------------------------------------------- alerts


def test_recording_loss_is_reported_as_an_error(capture: CaptureViewModel) -> None:
    alerts = capture._alerts_for(  # noqa: SLF001 - the rule under test
        CaptureMetrics(connected=True, recording_dropped=3)
    )
    loss = next(a for a in alerts if a.key == "recording_loss")
    assert loss.level is AlertLevel.ERROR
    assert "veri kaybıdır" in loss.text.casefold()


def test_low_disk_is_a_warning_with_an_action(capture: CaptureViewModel) -> None:
    alerts = capture._alerts_for(  # noqa: SLF001
        CaptureMetrics(connected=True, free_bytes=1_000_000_000)
    )
    disk = next(a for a in alerts if a.key == "disk")
    assert disk.level is AlertLevel.WARNING
    assert disk.action


def test_recording_without_a_subject_is_refused_with_a_reason(
    capture: CaptureViewModel,
) -> None:
    """Not a silently dead button: a refusal that says what to do.

    A take with nobody marked comes back from processing with joint arrays
    that are NaN from end to end, and no decision made afterwards can fill
    them in. Two real ZED recordings were lost that way on 17 September while
    the screen said the choice could be made later.
    """
    assert capture.connect()
    seen = []
    notices = []
    capture.message.subscribe(seen.append)
    capture.notice.subscribe(notices.append)

    assert capture.start_recording() is False
    assert capture.anchor.value is None
    refusal = seen[-1]
    assert refusal.severity is Severity.WARNING
    assert "kişiyi seçin" in refusal.headline.casefold()
    # And it says why, not just no.
    assert "boş" in refusal.detail.casefold()
    # On the picture too, for whoever is standing in front of the camera.
    assert notices and "kendinize tıklayın" in notices[-1][0].casefold()


def test_a_recording_already_running_still_reports_a_missing_subject(
    capture: CaptureViewModel,
) -> None:
    """The alert no longer promises a repair that does not exist."""
    alerts = capture._alerts_for(  # noqa: SLF001
        CaptureMetrics(connected=True, recording=True)
    )
    warning = next(a for a in alerts if a.key == "no_subject")
    assert warning.level is AlertLevel.WARNING
    assert "sonradan" not in warning.text.casefold()
    assert "boş" in warning.text.casefold()
