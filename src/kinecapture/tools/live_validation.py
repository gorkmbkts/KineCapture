"""Operator-controlled single-person hardware validation, isolated from user settings.

python -m kinecapture.tools.live_validation --output <new permanent directory>
The camera opens for framing only. Recording requires a button and a countdown.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSpinBox)

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.core.jsonio import write_json
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import ConsentStatus
from kinecapture.domain.project import CaptureProfile
from kinecapture.preview.pose import CpuPosePreview, PosePreview, BONES
from kinecapture.tools.fetch_preview_models import DEFAULT_MODEL_DIR


CASES = (
    ("Önden · RGB + hafif iskelet", "front_pose", True,
     "Kameraya dönük dur. İlk 3 saniye sabit kal, sonra 3 yavaş squat yap; son 3 saniye sabit kal."),
    ("Önden · yalnız RGB (hız karşılaştırması)", "front_rgb", False,
     "Aynı yerde ve aynı ışıkta, önceki kayıttaki hareketleri tekrarla. İskelet önizlemesi bu testte kapalı."),
    ("Çapraz · RGB + hafif iskelet", "oblique_pose", True,
     "Kameraya göre yaklaşık 45° dön. İlk 3 saniye sabit kal, 3 yavaş squat yap, son 3 saniye sabit kal."),
    ("Kadrajdan çıkış ve dönüş · tek kişi", "leave_return", True,
     "İlk 5 saniye sabit dur. Kısa süre kadrajdan çık, sonra aynı yere dön ve sabit kal."),
)


class SwitchablePose:
    """One preview worker owns the model; toggles occur only between takes."""
    def __init__(self, model_dir, *, model=None):
        self.model = model if model is not None else CpuPosePreview(model_dir)
        self.enabled = True
        self.provenance = getattr(self.model, "provenance", {})

    def __call__(self, packet):
        return self.model(packet) if self.enabled else PosePreview(packet, ())


def framing_status(preview):
    """A visible heuristic, never a guarantee of full body visibility."""
    if preview is None or len(preview.people) != 1:
        return False, "Tek kişi ve baş–ayak noktaları henüz güvenilir görünmüyor. Görüntüyü kendin kontrol et."
    p = preview.people[0]
    indices = [0, 11, 12, 23, 24, 27, 28, 31, 32]
    points = p.points[indices]
    w, h = preview.packet.resolution
    ok = (np.isfinite(points).all() and np.min(p.confidence[indices]) >= .5
          and (points >= [w*.015, h*.015]).all()
          and (points <= [w*.985, h*.985]).all())
    return bool(ok), ("Baş ve ayak noktaları kadrajda (model tahmini). Ayakkabıların ve baş üstü boşluğunu gözünle kontrol et."
                      if ok else "Baş/ayak noktaları kenara yakın veya belirsiz. Biraz geri çekilip görüntüyü kontrol et.")


class CameraCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(480, 270)
        self.preview = None
        self.image = None

    def show_preview(self, preview):
        self.preview = preview
        rgb = np.ascontiguousarray(preview.packet.color_frame)
        self.image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0],
                            QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#080e16"))
        if self.image is None:
            p.setPen(QColor("#d7e4f2"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Kamera görüntüsü hazırlanıyor…")
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2,
                        size.width(), size.height())
        p.drawImage(target, self.image)
        w, h = self.preview.packet.resolution
        def point(xy):
            return QPointF(target.x()+xy[0]*target.width()/w, target.y()+xy[1]*target.height()/h)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#55f0b6"), 2))
        for person in self.preview.people:
            for a, b in BONES:
                if min(person.confidence[a], person.confidence[b]) >= .5 and np.isfinite(person.points[[a,b]]).all():
                    p.drawLine(point(person.points[a]), point(person.points[b]))


class ValidationWindow(QWidget):
    def __init__(self, output: Path, *, backend_name="zed", processor=None, backend=None,
                 countdown_seconds=8, max_seconds=20):
        super().__init__()
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.processor = processor or SwitchablePose(DEFAULT_MODEL_DIR)
        self.profile = CaptureProfile()
        backend = backend or (ZedCameraBackend(self.profile) if backend_name == "zed" else
            MockCameraBackend(width=640, height=360, fps=60, real_time=True, profile=self.profile))
        self.service = CaptureService(backend, preview_processor=self.processor)
        self.workspace = ProjectWorkspace.create(self.output, "ZED tek kişi doğrulaması")
        participant = self.workspace.create_participant()
        self.session = self.workspace.create_session(participant.participant_id,
            operator="single_subject_hardware_validation", consent=ConsentStatus.GRANTED,
            capture_profile=self.profile)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="validation-control")
        self.future = None
        self.action = ""
        self.mode = "connecting"
        self.deadline = 0.0
        self.started = 0.0
        self.finish_requested = False
        self.stop_requested = False
        self.closed_cleanly = False
        self.anchor_saved = False
        self.anchor_after_ns = 0
        self.samples = []
        self.takes = []
        self.events = []
        self.last_sample = 0.0
        self.preview_times = []
        self.last_preview_index = -1
        self.current = {}
        self._build(countdown_seconds, max_seconds)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)
        self.submit("connect", self.connect_camera)

    def _build(self, countdown, seconds):
        self.setWindowTitle("KineCapture — Tek kişiyle ZED testi")
        self.resize(1100, 800)
        self.setStyleSheet("QWidget { background:#121b28; color:#eaf1fa; font:11pt 'Segoe UI'; }"
            "QPushButton { padding:10px 18px; border:1px solid #52677f; border-radius:6px; }"
            "QPushButton:disabled { color:#6e7d90; border-color:#354255; }"
            "QComboBox,QSpinBox { padding:6px; background:#26364a; }"
            "QPushButton#start { background:#11794e; } QPushButton#stop { background:#a12f3d; }")
        layout = QVBoxLayout(self)
        title = QLabel("Tek kişiyle kayıt testi · HD720 / 60 FPS")
        title.setStyleSheet("font-size:18pt; font-weight:600")
        layout.addWidget(title)
        self.case = QComboBox()
        for label, *_ in CASES: self.case.addItem(label)
        self.case.currentIndexChanged.connect(self.change_case)
        layout.addWidget(self.case)
        self.instructions = QLabel(CASES[0][3])
        self.instructions.setWordWrap(True)
        layout.addWidget(self.instructions)
        self.canvas = CameraCanvas()
        layout.addWidget(self.canvas, 1)
        self.framing = QLabel("Görüntü kırpılmaz. Başın, ellerin ve iki ayağın tamamını kontrol et.")
        self.framing.setWordWrap(True)
        layout.addWidget(self.framing)
        self.status = QLabel("Kamera bağlanıyor; henüz kayıt alınmıyor.")
        self.status.setStyleSheet("font-size:16pt; font-weight:600")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.metrics = QLabel("Kayıt yalnız Başlat düğmesiyle başlar.")
        layout.addWidget(self.metrics)
        row = QHBoxLayout()
        self.countdown = QSpinBox(); self.countdown.setRange(0,20); self.countdown.setValue(countdown)
        self.duration = QSpinBox(); self.duration.setRange(2,60); self.duration.setValue(seconds)
        row.addWidget(QLabel("Hazırlık (sn)")); row.addWidget(self.countdown)
        row.addWidget(QLabel("En fazla kayıt (sn)")); row.addWidget(self.duration)
        self.start_button = QPushButton("Kaydı başlat (R)"); self.start_button.setObjectName("start")
        self.stop_button = QPushButton("Durdur / iptal (Esc)"); self.stop_button.setObjectName("stop")
        self.finish_button = QPushButton("Testi bitir")
        for button in (self.start_button,self.stop_button,self.finish_button): row.addWidget(button)
        layout.addLayout(row)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        self.finish_button.clicked.connect(self.finish)
        QShortcut(QKeySequence("R"), self, activated=self.start)
        QShortcut(QKeySequence("Escape"), self, activated=self.stop)
        self.history = QLabel("Tamamlanan kayıt yok. Her kayıt ayrı saklanır; eski kayıtlar üzerine yazılmaz.")
        self.history.setWordWrap(True)
        layout.addWidget(self.history)
        note = QLabel("İskelet açıkken kadrajdaki tek kişi, senin talebin doğrultusunda seçilir. Bu 2D önizlemedir; nihai 3D iskelet sonra hesaplanır.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.controls()

    def log(self, name, **data):
        self.events.append({"event": name, "utc": datetime.now(timezone.utc).isoformat(), **data})
        self.save()

    def save(self):
        write_json(self.workspace.root / "validation.json", {
            "schema_version":"1.0.0", "single_subject_authorized":True,
            "profile":self.profile.to_dict(), "pose_provider":self.processor.provenance,
            "camera": self.service.camera_info.to_dict() if self.service.camera_info else None,
            "takes":self.takes, "events":self.events, "samples":self.samples,
            "mode":self.mode, "closed_cleanly":self.closed_cleanly}, overwrite=True)

    def submit(self, action, fn):
        if self.future is not None: return
        self.action = action
        self.future = self.pool.submit(fn)
        self.controls()

    def connect_camera(self):
        info = self.service.connect()
        self.service.start_preview()
        return info.to_dict()

    def controls(self):
        idle = self.mode == "ready" and self.future is None
        self.start_button.setEnabled(idle)
        for widget in (self.case,self.countdown,self.duration): widget.setEnabled(idle)
        self.stop_button.setEnabled(self.mode in ("countdown","starting","recording","error"))
        self.finish_button.setEnabled(self.mode != "closing")

    def change_case(self):
        case = CASES[self.case.currentIndex()]
        self.instructions.setText(case[3])
        self.processor.enabled = case[2]

    def start(self):
        if self.mode != "ready" or self.future is not None: return
        self.change_case()
        self.mode = "countdown"
        self.deadline = time.monotonic()+self.countdown.value()
        self.log("operator_start_requested", case=CASES[self.case.currentIndex()][1])
        self.controls()

    def stop(self):
        if self.mode == "countdown":
            self.mode = "ready"
            self.status.setText("Geri sayım iptal edildi; kayıt başlamadı.")
            self.log("countdown_cancelled")
        elif self.mode == "starting":
            self.stop_requested = True
        elif self.mode == "recording" and self.future is not None:
            self.stop_requested = True
        elif self.mode in ("recording", "error") and self.future is None:
            self.mode = "stopping"
            self.status.setText("Kayıt durduruluyor; dosyalar doğrulanıp kapatılıyor…")
            self.submit("stop", self.service.stop_recording)
        self.controls()

    def finish(self):
        self.finish_requested = True
        self.stop()
        if self.future is None and self.mode in ("ready","error"):
            self.mode = "closing"
            self.status.setText("Kamera güvenle kapatılıyor…")
            self.submit("close", self.service.disconnect)

    def closeEvent(self, event):
        if self.closed_cleanly:
            event.accept()
        else:
            event.ignore()
            self.finish()

    def tick(self):
        now = time.monotonic()
        if self.future is not None and self.future.done():
            future, action = self.future, self.action
            self.future = None
            try:
                result = future.result()
                if action == "connect":
                    self.mode = "ready"
                    self.status.setText("Hazır · Kayıt yok. Kadrajı kontrol et, ardından Başlat'a bas.")
                    self.log("connected", info=result)
                elif action == "start":
                    self.mode = "recording"; self.started = now; self.anchor_saved = False
                    latest = self.service.pose_preview
                    self.anchor_after_ns = latest.packet.camera_timestamp_ns if latest else 0
                    self.current = {"take_id":result.take_id,
                        "take_dir":str(self.workspace.take_paths(result).root),
                        "case":CASES[self.case.currentIndex()][1],"pose_enabled":self.processor.enabled,
                        "requested_seconds":self.duration.value(),"display_enabled":True}
                    self.log("recording_started", **self.current)
                    if self.stop_requested or self.finish_requested:
                        self.stop_requested = False; self.stop()
                elif action == "anchor":
                    self.log("single_person_anchor_saved")
                elif action == "stop":
                    if result:
                        self.current.update(state=result.state.value, duration_s=result.metrics.duration_s)
                        self.takes.append(self.current.copy())
                        self.history.setText("\n".join(f"{i+1}. {t['case']} · {t['duration_s']:.1f} sn · {t['state']}"
                                                      for i,t in enumerate(self.takes)))
                    self.mode = "ready"
                    self.status.setText("Kayıt kapandı. Sonraki testi seçebilir veya Testi bitir'e basabilirsin.")
                    self.log("recording_stopped", result=self.current)
                elif action == "close":
                    self.mode = "closed"; self.closed_cleanly = True
                    self.log("closed")
                    self.timer.stop(); self.pool.shutdown(wait=False); self.close()
                    return
            except Exception as exc:
                self.mode = "error"
                self.finish_requested = False
                self.status.setText(f"Hata: {exc}")
                self.log("error", action=action, detail=repr(exc))
            self.controls()
        if self.stop_requested and self.mode == "recording" and self.future is None:
            self.stop_requested = False
            self.stop()
        if self.mode == "countdown":
            remaining = max(0, int(np.ceil(self.deadline-now)))
            self.status.setText(f"{remaining} · Kadraja geç — kayıt henüz başlamadı")
            if now >= self.deadline:
                self.mode = "starting"
                self.status.setText("Kayıt başlatılıyor…")
                case = CASES[self.case.currentIndex()][1]
                self.submit("start", lambda: self.service.start_recording(self.workspace, self.session,
                    notes=f"single_subject_validation; case={case}; operator-controlled"))
        preview = self.service.pose_preview
        if preview is not None and preview.packet.frame_index != self.last_preview_index:
            self.last_preview_index = preview.packet.frame_index
            self.preview_times.append(now); self.preview_times = self.preview_times[-30:]
            self.canvas.show_preview(preview)
            good, message = framing_status(preview)
            self.framing.setText(message if self.processor.enabled else
                "İskelet hesabı kapalı; görüntü tam kadraj gösteriliyor. Başını ve ayaklarını kendin kontrol et.")
            if (self.mode == "recording" and not self.anchor_saved and good
                and preview.packet.camera_timestamp_ns > self.anchor_after_ns and self.future is None):
                person = preview.people[0]
                xy = np.mean(person.points[[23,24]],axis=0)
                anchor = preview.anchor(*xy)
                anchor["selection_method"] = "user_authorized_single_visible_person"
                self.anchor_saved = True
                self.submit("anchor", lambda: self.service.set_subject_anchor(anchor))
        if self.mode == "recording":
            elapsed = now-self.started
            self.status.setText(f"KAYIT · {elapsed:.1f} / {self.duration.value()} sn · Durdur her an kullanılabilir")
            if elapsed >= self.duration.value(): self.stop()
        if now-self.last_sample >= 1:
            self.last_sample = now
            stats = self.service.statistics
            worker = self.service._preview_worker
            pfps = ((len(self.preview_times)-1)/(self.preview_times[-1]-self.preview_times[0])
                    if len(self.preview_times)>1 else 0)
            self.metrics.setText(f"Kamera {stats.acquisition_fps:.1f} FPS  |  Görüntü {pfps:.1f} FPS  |  "
                f"Yazılan {self.service.recorded_frame_count} kare  |  Kayıt kuyruğu kaybı {stats.recording_frames_dropped}")
            self.samples.append({"monotonic_s":now,"mode":self.mode,
                "take_id": self.current.get("take_id") if self.mode in ("recording","stopping") else None,
                "source_fps":stats.acquisition_fps,"display_fps":pfps,
                "written":self.service.recorded_frame_count,"queue_loss":stats.recording_frames_dropped,
                "backend_drop_cumulative":stats.backend_dropped_frames,
                "preview_ms":worker.last_ms if worker else None,
                "preview_error":worker.error if worker else None,
                "sdk_status":self.service.last_recording_status})
            self.save()
        if self.service.last_error and self.mode == "recording":
            self.status.setText(str(self.service.last_error)); self.stop()
        if self.finish_requested and self.future is None and self.mode in ("ready","error"):
            self.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("zed","mock"), default="zed")
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    app = QApplication([])
    window = ValidationWindow(args.output, backend_name=args.backend)
    window.showMaximized()
    if args.screenshot:
        QTimer.singleShot(6500, lambda: window.grab().save(str(args.screenshot)))
    print(str(window.workspace.root), flush=True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
