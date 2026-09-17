"""The Capture screen: connect, frame the shot, pick the athlete, record.

Recording only ever produces the raw source. The skeleton is computed
afterwards, so the end of a take is *"Ham kayıt kaydedildi · İskelet bekliyor"*
and never a failure - a take with nobody detected in it is still a perfectly
good recording, and saying otherwise would train the operator to distrust a
correct result.

No Qt.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from kinecapture.core.errors import KineCaptureError
from kinecapture.studio.services.capture import (
    PREVIEW_POSE_DISCLAIMER,
    CaptureMetrics,
    CaptureService,
    SubjectAnchor,
)
from kinecapture.studio.services.framing import Framing, FramingWatch, measure
from kinecapture.studio.services.messages import Action, Message, Severity, from_error
from kinecapture.studio.services.session import SessionService, WorkTarget

from .observable import Event, Observable
from .tasks import InlineRunner, TaskRunner


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Alert:
    """One thing wrong right now, with what to do about it."""

    key: str
    level: AlertLevel
    text: str
    action: str = ""


@dataclass(frozen=True)
class RecordingMode:
    key: str
    label: str
    detail: str
    cost: str = ""


#: Countdown lengths offered to somebody who has to walk into the shot.
COUNTDOWN_CHOICES = (0, 3, 5, 10)

#: Optional automatic stop, in seconds. 0 means "until I say so".
DURATION_CHOICES = (0, 15, 30, 60, 120)


#: The two ways to record. The default keeps the live path as light as it can
#: be; the other is offered, priced, and never chosen silently.
RECORDING_MODES = (
    RecordingMode(
        key="raw_only",
        label="Hızlı kayıt · İskeleti sonra çıkar",
        detail=(
            "Yalnız ham stereo kayıt alınır. İskelet kayıttan sonra, daha iyi "
            "bir modelle ve kare atlamadan hesaplanır."
        ),
    ),
    RecordingMode(
        key="live_skeleton",
        label="Canlı iskelet · Daha yüksek sistem yükü",
        detail=(
            "Kayıt sırasında iskelet de hesaplanır. Anında görmek gerektiğinde "
            "kullanılır."
        ),
        cost="Kayıt hızını düşürür ve kare kaybı riskini artırır.",
    ),
)


#: What the recording is doing, as one word the whole shell can show.
class RecordingPhase(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RECORDING = "recording"
    CLOSING = "closing"


@dataclass(frozen=True)
class RecordingStatus:
    """One reading of the live recording, for any screen that has to show it.

    Separate from :class:`CaptureMetrics` because the shell needs a *verdict*
    ("is a take open, who does it belong to, can it be stopped"), not a set of
    counters, and because the shell must be able to say all of that while the
    Capture screen is not even built.
    """

    phase: RecordingPhase = RecordingPhase.IDLE
    elapsed_s: float = 0.0
    frames: int = 0
    lost_frames: int = 0
    target_text: str = ""
    #: The long form, for a tooltip. The strip itself only has room for a code.
    target_detail: str = ""

    @property
    def is_open(self) -> bool:
        """A take owns the directory: recording, or still closing its files."""
        return self.phase in (RecordingPhase.RECORDING, RecordingPhase.CLOSING)

    @property
    def elapsed_text(self) -> str:
        minutes, seconds = divmod(int(self.elapsed_s), 60)
        return f"{minutes:02d}:{seconds:02d}"

    @property
    def phase_text(self) -> str:
        return {
            RecordingPhase.IDLE: "kayıt yok",
            RecordingPhase.PREPARING: "hazırlanıyor",
            RecordingPhase.RECORDING: "kaydediliyor",
            RecordingPhase.CLOSING: "dosyalar kapatılıyor",
        }[self.phase]


class CaptureViewModel:
    def __init__(
        self,
        session: SessionService,
        service: Optional[CaptureService] = None,
        runner: Optional[TaskRunner] = None,
    ) -> None:
        self._session = session
        self.service = service or CaptureService(session.config)
        # Connecting a ZED and closing a take are both measured in seconds to
        # minutes. Neither may run where a repaint is waiting.
        self._runner: TaskRunner = runner or InlineRunner()

        self.metrics: Observable[CaptureMetrics] = Observable(
            CaptureMetrics(), name="capture_metrics"
        )
        self.alerts: Observable[tuple[Alert, ...]] = Observable((), name="alerts")
        self.anchor: Observable[Optional[SubjectAnchor]] = Observable(None, name="anchor")
        #: The mode chosen for the next recording.
        self.mode: Observable[str] = Observable(self.service.mode, name="mode")
        #: The mode the connected camera is really running. Empty when nothing
        #: is connected; never equal to ``mode`` on the strength of a click.
        self.active_mode: Observable[str] = Observable("", name="active_mode")
        #: True when the choice has been made but is not in force yet.
        self.mode_pending: Observable[bool] = Observable(False, name="mode_pending")
        self.pose_note: Observable[str] = Observable(
            PREVIEW_POSE_DISCLAIMER, name="pose_note"
        )
        #: Whether the whole person is in shot, right now.
        self.framing: Observable[Framing] = Observable(Framing(), name="framing")
        #: And what the worst of the last few seconds was, which is the one
        #: you can actually read after standing up from a squat.
        self.framing_history: Observable[str] = Observable("", name="framing_history")
        self._framing_watch = FramingWatch()
        #: Who the next take belongs to, resolved from the session.
        self.target: Observable[WorkTarget] = Observable(WorkTarget(), name="target")
        #: (participant_id, code) for the target chooser.
        self.participants: Observable[tuple[tuple[str, str], ...]] = Observable(
            (), name="participants"
        )
        self.connecting: Observable[bool] = Observable(False, name="connecting")
        self.stopping: Observable[bool] = Observable(False, name="stopping")
        self.status: Observable[RecordingStatus] = Observable(
            RecordingStatus(), name="recording_status"
        )
        #: Seconds left before a countdown-started recording begins. 0 means
        #: no countdown is running - it is cancellable the whole time.
        self.countdown: Observable[int] = Observable(0, name="countdown")
        #: The countdown length the operator chose, in seconds.
        self.countdown_seconds: Observable[int] = Observable(0, name="countdown_seconds")
        #: Stop by itself after this many seconds. 0 means never.
        self.auto_stop_seconds: Observable[int] = Observable(0, name="auto_stop_seconds")
        #: Display-only: mirror the preview, draw framing guides.
        self.mirrored: Observable[bool] = Observable(False, name="mirrored")
        self.guides: Observable[bool] = Observable(False, name="guides")
        self.message: Event[Message] = Event()
        self.take_finished: Event[object] = Event()

        # The target is read from disk, so it is refreshed when the session
        # says something changed - not several times a second on a timer.
        self._unsubscribe_session = session.subscribe(self.refresh_target)
        self.refresh_target()

    def close(self) -> None:
        self._unsubscribe_session()

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> bool:
        """Open the camera off the GUI thread.

        Returns False when the attempt has already failed by the time this
        returns - which is what a synchronous runner gives - and True when the
        attempt is under way; the outcome then arrives through ``connecting``
        and ``metrics``.
        """
        if self.connecting.value:
            return False
        self.connecting.set(True)
        self.refresh()
        outcome = [True]

        def work():  # noqa: ANN202
            return self.service.connect()

        def done(_info) -> None:  # noqa: ANN001
            self.connecting.set(False)
            if self.service.pose_unavailable_reason:
                self.pose_note.set(
                    "Hafif kaplama kullanılamıyor: "
                    f"{self.service.pose_unavailable_reason}"
                )
            else:
                self.pose_note.set(PREVIEW_POSE_DISCLAIMER)
            self.refresh()

        def failed(exc: BaseException) -> None:
            outcome[0] = False
            self.connecting.set(False)
            self.message.emit(from_error(exc, headline="Kameraya bağlanılamadı."))
            self.refresh()

        self._runner.run(work, done, failed)
        return outcome[0]

    def disconnect(self) -> None:
        self.service.disconnect()
        self.anchor.set(None)
        self.refresh()

    # ------------------------------------------------------------------ mode
    def set_mode(self, key: str) -> bool:
        """Choose a recording mode. It is not "etkin" until the camera has it.

        Applying it means rebuilding the connection, which on a real device is
        slow, so the choice is recorded and the screen says plainly that it
        takes effect on the next connection until :meth:`apply_mode` runs.
        """
        if key not in {mode.key for mode in RECORDING_MODES}:
            return False
        if self.service.is_recording:
            self.message.emit(
                Message(
                    headline="Kayıt sürerken kayıt modu değiştirilemez.",
                    severity=Severity.WARNING,
                    detail="Bu kayıt kapandıktan sonra değiştirilebilir.",
                    code="mode_locked_while_recording",
                )
            )
            self.mode.set(self.service.mode)
            self._refresh_mode()
            return False
        self.service.set_mode(key)
        self.mode.set(key)
        self._refresh_mode()
        if self.mode_pending.value:
            self.message.emit(
                Message(
                    headline="Kayıt modu seçildi; henüz etkin değil.",
                    severity=Severity.INFO,
                    detail=(
                        "Kameranın bu modla yeniden bağlanması gerekiyor. "
                        "'Modu uygula' ile şimdi, yoksa bir sonraki bağlantıda."
                    ),
                    code="mode_needs_reconnect",
                )
            )
        return True

    def apply_mode(self) -> bool:
        """Reconnect so the chosen mode is really the one in force."""
        if self.service.is_recording:
            self.message.emit(
                Message(
                    headline="Kayıt sürerken yeniden bağlanılamaz.",
                    severity=Severity.WARNING,
                )
            )
            return False
        if not self.service.is_connected:
            return self.connect()
        self.service.disconnect()
        self.anchor.set(None)
        return self.connect()

    def _refresh_mode(self) -> None:
        active = self.service.active_mode
        self.active_mode.set(active)
        self.mode_pending.set(bool(active) and active != self.mode.value)

    # --------------------------------------------------------------- metrics
    def observe_framing(self) -> Framing:
        """Measure the live preview and remember it. Called per preview frame.

        Kept in the viewmodel rather than the widget so the rule about what
        counts as "in shot" is one testable thing, and so the history survives
        a repaint.
        """
        framing = measure(self.service.pose_preview())
        self.framing.set(framing)
        if framing.state in ("no_camera", "no_overlay"):
            self._framing_watch.reset()
            self.framing_history.set("")
            return framing
        self._framing_watch.observe(framing, now=time.monotonic())
        self.framing_history.set(self._framing_watch.verdict)
        return framing

    def reset_framing_history(self) -> None:
        """Start the window again - after moving the camera, for instance."""
        self._framing_watch.reset()
        self.framing_history.set("")

    def read_status(self) -> RecordingStatus:
        """A cheap reading of the recording, for anyone who only needs that.

        The shell shows a recording indicator on every screen, so this has to
        be answerable without rebuilding the Capture screen's alerts or
        re-reading the project from disk.
        """
        metrics = self.service.metrics()
        self.metrics.set(metrics)
        status = self._status_for(metrics)
        self.status.set(status)
        return status

    def refresh(self) -> None:
        """One reading. Called a few times a second, never per frame."""
        self.read_status()
        metrics = self.metrics.value
        self.alerts.force(self._alerts_for(metrics))
        current = self.service.subject_anchor
        if current != self.anchor.value:
            self.anchor.set(current)
        self._refresh_mode()

    def _status_for(self, metrics: CaptureMetrics) -> RecordingStatus:
        if self.stopping.value or metrics.state == "stopping":
            phase = RecordingPhase.CLOSING
        elif metrics.recording:
            phase = RecordingPhase.RECORDING
        elif self.connecting.value:
            phase = RecordingPhase.PREPARING
        else:
            phase = RecordingPhase.IDLE
        return RecordingStatus(
            phase=phase,
            elapsed_s=metrics.elapsed_s,
            frames=metrics.recorded_frames,
            lost_frames=metrics.recording_dropped,
            target_text=self.target.value.text,
            target_detail=self.target.value.detail,
        )

    # ---------------------------------------------------------------- target
    def refresh_target(self) -> None:
        """Re-read who the next take belongs to, and who it could belong to."""
        self.target.set(self._session.target())
        workspace = self._session.workspace
        if workspace is None:
            self.participants.force(())
            return
        try:
            rows = tuple(
                (p.participant_id, p.code) for p in workspace.list_participants()
            )
        except (KineCaptureError, OSError):
            rows = ()
        self.participants.force(rows)

    def choose_target(self, participant_id: str) -> bool:
        """Point the next recording at a participant.

        Refused while a take is open: the directory it is writing into was
        decided when it started, and pretending otherwise would put half a
        recording under one participant and half under another.
        """
        if self.service.is_recording:
            self.message.emit(
                Message(
                    headline="Kayıt sürerken hedef değiştirilemez.",
                    severity=Severity.WARNING,
                    detail="Bu kayıt kapandıktan sonra seçilebilir.",
                    code="target_locked_while_recording",
                )
            )
            self.refresh_target()
            return False
        self._session.select_participant(participant_id)
        self.refresh_target()
        return True

    def _alerts_for(self, metrics: CaptureMetrics) -> tuple[Alert, ...]:
        """Most urgent first. Recording loss outranks everything else."""
        alerts: list[Alert] = []
        if not metrics.connected:
            alerts.append(
                Alert("disconnected", AlertLevel.WARNING, "Kamera bağlı değil.", "Bağlan")
            )
            return tuple(alerts)
        if metrics.recording_dropped:
            alerts.append(
                Alert(
                    "recording_loss",
                    AlertLevel.ERROR,
                    f"{metrics.recording_dropped} kare kaydedilemedi. Bu veri kaybıdır.",
                    "Ayrıntılar",
                )
            )
        if metrics.backend_dropped:
            alerts.append(
                Alert(
                    "backend_loss",
                    AlertLevel.ERROR,
                    f"Kamera {metrics.backend_dropped} kare bildirmedi.",
                )
            )
        if metrics.free_bytes and metrics.free_minutes < 10:
            alerts.append(
                Alert(
                    "disk",
                    AlertLevel.WARNING,
                    f"Diskte yaklaşık {metrics.free_minutes:.0f} dakikalık yer kaldı.",
                    "Veri klasörünü değiştir",
                )
            )
        if metrics.recording and self.anchor.value is None:
            alerts.append(
                Alert(
                    "no_subject",
                    AlertLevel.WARNING,
                    "Kaydedilecek kişi seçilmedi. Kayıt sürüyor; seçim sonradan da yapılabilir.",
                )
            )
        return tuple(alerts)

    # -------------------------------------------------------------- subject
    def select_subject(self, x: float, y: float) -> bool:
        """Pick the person under a click on the displayed frame."""
        if self.service.service is None:
            return False
        try:
            anchor = self.service.anchor_from_click(x, y)
        except ValueError as exc:
            # Two overlapping people, or none. Never guessed at: the wrong
            # person in the dataset is worse than asking again.
            self.message.emit(
                Message(
                    headline=str(exc),
                    severity=Severity.WARNING,
                    detail="Kişilerin ayrıldığı bir anda tekrar deneyin.",
                    code="subject_anchor_ambiguous",
                )
            )
            return False
        except (KineCaptureError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Kişi seçimi kaydedilemedi."))
            return False
        self.anchor.set(anchor)
        self.message.emit(
            Message(
                headline="Kaydedilecek kişi seçildi.",
                severity=Severity.INFO,
                detail=(
                    "Seçim gösterilen karenin zaman damgasına bağlandı; "
                    "eşleştirme kayıttan sonra yapılır."
                ),
            )
        )
        return True

    def clear_subject(self) -> None:
        self.service.clear_subject()
        self.anchor.set(None)

    # ----------------------------------------------------------- solo capture
    def set_countdown_seconds(self, seconds: int) -> None:
        if int(seconds) in COUNTDOWN_CHOICES:
            self.countdown_seconds.set(int(seconds))

    def set_auto_stop_seconds(self, seconds: int) -> None:
        if int(seconds) in DURATION_CHOICES:
            self.auto_stop_seconds.set(int(seconds))

    def set_mirrored(self, mirrored: bool) -> None:
        """Display only. The raw recording is never mirrored."""
        self.mirrored.set(bool(mirrored))

    def set_guides(self, shown: bool) -> None:
        self.guides.set(bool(shown))

    def toggle_recording(self) -> bool:
        """One control for the whole cycle, so it can live on one key.

        Somebody standing in the frame cannot see which of two buttons is the
        right one, so start, cancel-the-countdown and stop are the same key.
        """
        if self.countdown.value:
            self.cancel_countdown()
            return False
        if self.service.is_recording:
            return self.stop_recording()
        return self.begin_recording()

    def begin_recording(self) -> bool:
        """Start, after the chosen countdown. No countdown means start now."""
        seconds = self.countdown_seconds.value
        if seconds <= 0:
            return self.start_recording()
        if not self._can_record():
            return False
        self.countdown.set(seconds)
        return True

    def cancel_countdown(self) -> bool:
        """Stop a countdown before it starts anything. Nothing was recorded."""
        if not self.countdown.value:
            return False
        self.countdown.set(0)
        self.message.emit(
            Message(
                headline="Geri sayım iptal edildi.",
                severity=Severity.INFO,
                detail="Kayıt başlamadı.",
                code="countdown_cancelled",
            )
        )
        return True

    def tick_countdown(self) -> bool:
        """One second of the countdown. Returns True when recording started.

        Driven by the screen's timer: a viewmodel owns no clock of its own.
        """
        remaining = self.countdown.value
        if remaining <= 0:
            return False
        remaining -= 1
        self.countdown.set(remaining)
        if remaining > 0:
            return False
        return self.start_recording()

    def tick_auto_stop(self) -> bool:
        """Stop when the chosen duration is up. Returns True when it stopped."""
        limit = self.auto_stop_seconds.value
        if not limit or not self.service.is_recording:
            return False
        if self.metrics.value.elapsed_s < limit:
            return False
        self.message.emit(
            Message(
                headline=f"Süre doldu: {limit} sn.",
                severity=Severity.INFO,
                detail="Kayıt kendiliğinden kapatıldı.",
                code="auto_stopped",
            )
        )
        return self.stop_recording()

    def _can_record(self) -> bool:
        """Whether a recording could start now, without starting one."""
        if self._session.workspace is None:
            self.message.emit(
                Message(headline="Önce bir proje açın.", severity=Severity.WARNING)
            )
            return False
        if not self.service.is_connected:
            self.message.emit(
                Message(headline="Önce kameraya bağlanın.", severity=Severity.WARNING)
            )
            return False
        return True

    # ------------------------------------------------------------- recording
    def start_recording(self) -> bool:
        workspace = self._session.workspace
        if workspace is None:
            self.message.emit(
                Message(headline="Önce bir proje açın.", severity=Severity.WARNING)
            )
            return False
        session = self._current_session(workspace)
        if session is None:
            return False
        try:
            self.service.start_recording(workspace, session)
        except (KineCaptureError, OSError, RuntimeError) as exc:
            self.message.emit(from_error(exc, headline="Kayıt başlatılamadı."))
            return False
        self.refresh()
        return True

    def _current_session(self, workspace):  # noqa: ANN001, ANN202
        """The open session for the target participant, creating what is missing.

        The participant is never *silently* guessed: a selection made on
        Projeler always wins, and when there is no selection the one that gets
        used is announced. What this will not do is refuse to record, which is
        what left a connected camera with a dead button.
        """
        try:
            participants = list(workspace.list_participants())
            if not participants:
                # An empty project has no ambiguity to protect: make the first
                # participant rather than sending the operator away mid-shot.
                participant = workspace.create_participant(
                    created_by_user_id=(
                        self._session.user.user_id if self._session.user else ""
                    )
                )
                self._session.select_participant(participant.participant_id)
                self.refresh_target()
                self.message.emit(
                    Message(
                        headline=f"Katılımcı oluşturuldu: {participant.code}",
                        severity=Severity.INFO,
                        detail=(
                            "Projede katılımcı yoktu; kayıt bu katılımcıya "
                            "yazılacak. Kod proje içinde anonim ve değişmezdir."
                        ),
                        code="participant_created",
                    )
                )
                participants = [participant]
            selected = self._session.selected_participant_id
            participant = next(
                (p for p in participants if p.participant_id == selected), None
            )
            if participant is None:
                participant = participants[0]
                self._session.select_participant(participant.participant_id)
                self.refresh_target()
                if len(participants) > 1:
                    # Several to choose from and none chosen: say which one is
                    # being used, loudly enough to be corrected.
                    self.message.emit(
                        Message(
                            headline=f"Kayıt hedefi: {participant.code}",
                            severity=Severity.WARNING,
                            detail=(
                                "Katılımcı seçilmemişti; listedeki ilki kullanıldı. "
                                "Başkasına kaydetmek için Projeler ekranından "
                                "katılımcıyı seçip yeniden başlatın."
                            ),
                            code="capture_target_defaulted",
                        )
                    )
            open_sessions = [
                s
                for s in workspace.list_sessions(participant.participant_id)
                if not s.ended_at
            ]
            if open_sessions:
                return open_sessions[0]
            operator = self._session.user.full_name if self._session.user else ""
            return workspace.create_session(
                participant.participant_id,
                operator=operator,
                operator_user_id=self._session.user.user_id if self._session.user else "",
            )
        except (KineCaptureError, OSError) as exc:
            self.message.emit(from_error(exc, headline="Oturum hazırlanamadı."))
            return None

    def stop_recording(self) -> bool:
        """Close the take. Runs off the GUI thread and only ever once.

        Flushing a take means finishing a writer queue and, on a real device,
        closing an SVO2 - seconds, sometimes more. Doing that where a repaint
        is waiting is what makes a window impossible to move while it happens.

        A second press while the first is still closing is ignored rather than
        starting a second finalisation of the same take.
        """
        if self.stopping.value:
            return False
        if not self.service.is_recording:
            return False
        self.stopping.set(True)
        self.refresh()

        def work():  # noqa: ANN202
            return self.service.stop_recording()

        def done(take) -> None:  # noqa: ANN001
            self.stopping.set(False)
            self.refresh()
            if take is None:
                return
            # Not a verdict on the recording: no skeleton was asked for yet.
            self.message.emit(
                Message(
                    headline="Ham kayıt kaydedildi · İskelet bekliyor",
                    severity=Severity.INFO,
                    detail=(
                        f"{take.metrics.frames_written} kare, "
                        f"{take.metrics.duration_s:.1f} sn."
                    ),
                    code="awaiting_processing",
                    # Naming the screen and leaving the user to find the take
                    # again is what the audit had to do. This takes them there.
                    actions=(
                        Action("goto:processing", "Bu kaydı hesapla", primary=True),
                    ),
                )
            )
            self.take_finished.emit(take)

        def failed(exc: BaseException) -> None:
            self.stopping.set(False)
            self.message.emit(from_error(exc, headline="Kayıt kapatılamadı."))
            self.refresh()

        self._runner.run(work, done, failed)
        return True

    def add_marker(self) -> None:
        marker = self.service.add_marker()
        if marker:
            self.message.emit(
                Message(
                    headline=f"İşaret kondu: kare {marker.get('frame_index', '?')}",
                    severity=Severity.INFO,
                )
            )


__all__ = [
    "COUNTDOWN_CHOICES",
    "DURATION_CHOICES",
    "Alert",
    "AlertLevel",
    "CaptureViewModel",
    "RECORDING_MODES",
    "RecordingMode",
    "RecordingPhase",
    "RecordingStatus",
]
