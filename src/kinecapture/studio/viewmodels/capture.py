"""The Capture screen: connect, frame the shot, pick the athlete, record.

Recording only ever produces the raw source. The skeleton is computed
afterwards, so the end of a take is *"Ham kayıt kaydedildi · İskelet bekliyor"*
and never a failure - a take with nobody detected in it is still a perfectly
good recording, and saying otherwise would train the operator to distrust a
correct result.

No Qt.
"""

from __future__ import annotations

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
from kinecapture.studio.services.messages import Message, Severity, from_error
from kinecapture.studio.services.session import SessionService

from .observable import Event, Observable


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


class CaptureViewModel:
    def __init__(self, session: SessionService, service: Optional[CaptureService] = None) -> None:
        self._session = session
        self.service = service or CaptureService(session.config)

        self.metrics: Observable[CaptureMetrics] = Observable(
            CaptureMetrics(), name="capture_metrics"
        )
        self.alerts: Observable[tuple[Alert, ...]] = Observable((), name="alerts")
        self.anchor: Observable[Optional[SubjectAnchor]] = Observable(None, name="anchor")
        self.mode: Observable[str] = Observable(
            "live_skeleton" if session.config.capture.enable_body_tracking else "raw_only",
            name="mode",
        )
        self.pose_note: Observable[str] = Observable(
            PREVIEW_POSE_DISCLAIMER, name="pose_note"
        )
        self.message: Event[Message] = Event()
        self.take_finished: Event[object] = Event()

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> bool:
        try:
            self.service.connect()
        except (KineCaptureError, OSError, RuntimeError) as exc:
            self.message.emit(from_error(exc, headline="Kameraya bağlanılamadı."))
            self.refresh()
            return False
        if self.service.pose_unavailable_reason:
            self.pose_note.set(
                f"Hafif kaplama kullanılamıyor: {self.service.pose_unavailable_reason}"
            )
        else:
            self.pose_note.set(PREVIEW_POSE_DISCLAIMER)
        self.refresh()
        return True

    def disconnect(self) -> None:
        self.service.disconnect()
        self.anchor.set(None)
        self.refresh()

    def set_mode(self, key: str) -> None:
        if key not in {mode.key for mode in RECORDING_MODES}:
            return
        self.mode.set(key)

    # --------------------------------------------------------------- metrics
    def refresh(self) -> None:
        """One reading. Called a few times a second, never per frame."""
        metrics = self.service.metrics()
        self.metrics.set(metrics)
        self.alerts.force(self._alerts_for(metrics))
        current = self.service.subject_anchor
        if current != self.anchor.value:
            self.anchor.set(current)

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
        """The open session for this participant, or a new one."""
        try:
            participants = workspace.list_participants()
            if not participants:
                self.message.emit(
                    Message(
                        headline="Önce bir katılımcı ekleyin.",
                        severity=Severity.WARNING,
                        detail="Projeler ekranından ekleyebilirsiniz.",
                    )
                )
                return None
            participant = participants[0]
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
        try:
            take = self.service.stop_recording()
        except (KineCaptureError, OSError, RuntimeError) as exc:
            self.message.emit(from_error(exc, headline="Kayıt kapatılamadı."))
            self.refresh()
            return False
        self.refresh()
        if take is None:
            return False
        # Not a verdict on the recording: no skeleton was asked for yet.
        self.message.emit(
            Message(
                headline="Ham kayıt kaydedildi · İskelet bekliyor",
                severity=Severity.INFO,
                detail=(
                    f"{take.metrics.frames_written} kare, "
                    f"{take.metrics.duration_s:.1f} sn. İskeleti hesaplamak için "
                    "Verileri Hesapla ekranını kullanın."
                ),
                code="awaiting_processing",
            )
        )
        self.take_finished.emit(take)
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


__all__ = ["Alert", "AlertLevel", "CaptureViewModel", "RECORDING_MODES", "RecordingMode"]
