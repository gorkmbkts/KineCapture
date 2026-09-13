"""Independent diagnostic capture/viewer; no identity DB or user preferences.

Example: python -m kinecapture.tools.capture_diagnostic --backend mock --output C:/temp/kc-test --seconds 5 --no-display
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
import numpy as np

from kinecapture.camera.mock import MockCameraBackend
from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.capture.service import CaptureService
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.project import CaptureProfile
from kinecapture.domain.enums import ConsentStatus
from kinecapture.preview.pose import CpuPosePreview, BONES
from kinecapture.tools.fetch_preview_models import DEFAULT_MODEL_DIR
from kinecapture.core.jsonio import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("mock", "zed"), default="mock")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--no-pose", action="store_true")
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()
    if not 0 < args.seconds <= 600:
        parser.error("seconds must be within (0,600]")
    profile = CaptureProfile(preview_enabled=not args.no_preview)
    processor = None if args.no_pose or args.no_preview else CpuPosePreview(args.model_dir)
    backend = ZedCameraBackend(profile) if args.backend == "zed" else MockCameraBackend(
        width=640, height=360, fps=60, real_time=True, profile=profile)
    service = CaptureService(backend, preview_processor=processor)
    workspace = ProjectWorkspace.create(args.output, "Backend diagnostic")
    participant = workspace.create_participant()
    session = workspace.create_session(participant.participant_id, operator="diagnostic",
        consent=ConsentStatus.GRANTED, capture_profile=profile)
    samples = []
    displayed = {"pose": None, "scale": None, "anchor": None, "message": "Kayıt sırasında kişiye tıklayın"}
    if not args.no_display:
        import cv2
        cv2.namedWindow("KineCapture diagnostic", cv2.WINDOW_AUTOSIZE)
        def click(event, x, y, flags, userdata):
            if event != cv2.EVENT_LBUTTONDOWN or displayed["pose"] is None:
                return
            try:
                sx, sy = displayed["scale"]
                anchor = displayed["pose"].anchor(x * sx, y * sy)
                service.set_subject_anchor(anchor)
                displayed["anchor"] = anchor
                displayed["message"] = "Anchor kaydedildi; offline esleme bekliyor"
            except ValueError as exc:
                displayed["message"] = str(exc)
        cv2.setMouseCallback("KineCapture diagnostic", click)
    result = None
    try:
        service.connect()
        service.start_preview()
        service.start_recording(workspace, session)
        started = time.perf_counter()
        next_sample = started
        while time.perf_counter() - started < args.seconds:
            if service.last_error:
                raise RuntimeError(service.last_error)
            packet = service.latest_frame()
            preview = service.pose_preview
            if packet is not None and not args.no_display:
                import cv2
                if preview is not None:
                    packet = preview.packet  # exact image used by inference
                frame = cv2.cvtColor(packet.color_frame, cv2.COLOR_RGB2BGR)
                sx, sy = np.asarray(packet.resolution) / np.array([frame.shape[1], frame.shape[0]])
                if preview:
                    for person in preview.people:
                        points = person.points / [sx,sy]
                        for a,b in BONES:
                            if min(person.confidence[a],person.confidence[b]) >= 0.5 and np.isfinite(points[[a,b]]).all():
                                cv2.line(frame, tuple(points[a].astype(int)), tuple(points[b].astype(int)), (0,220,0), 2)
                    displayed["pose"], displayed["scale"] = preview, (sx,sy)
                worker = service._preview_worker
                status = service.last_recording_status or {}
                lines = [f"Source {service.statistics.acquisition_fps:.1f} fps | Preview {1000/max(1,worker.last_ms) if worker else 0:.1f} fps",
                         f"Queue lost {service.statistics.recording_frames_dropped} | SDK dropped {service.statistics.backend_dropped_frames}",
                         f"Ingested {status.get('frames_ingested','?')} Encoded {status.get('frames_encoded','?')} (unverified counters)",
                         displayed["message"]]
                for n, line in enumerate(lines):
                    cv2.putText(frame, line, (8,20+22*n), cv2.FONT_HERSHEY_SIMPLEX, .43, (255,255,255), 1)
                cv2.imshow("KineCapture diagnostic", frame)
            if not args.no_display:
                import cv2
                if cv2.waitKey(1) in (27, ord('q')):
                    break
            now = time.perf_counter()
            if now >= next_sample:
                worker = service._preview_worker
                sample = {"elapsed_s": now-started, "source_fps": service.statistics.acquisition_fps,
                    "recorded_frames": service.recorded_frame_count, "recording_queue_loss": service.statistics.recording_frames_dropped,
                    "sdk_drop_count": service.statistics.backend_dropped_frames, "sdk_recording": service.last_recording_status,
                    "preview_completed": worker.completed if worker else 0, "preview_discarded": worker.dropped if worker else 0,
                    "preview_last_ms": worker.last_ms if worker else None, "preview_error": worker.error if worker else None}
                samples.append(sample)
                print(json.dumps(sample), flush=True)
                next_sample = now+1
            time.sleep(.003)
        result = service.stop_recording()
    finally:
        service.shutdown()
        write_json(workspace.root / "diagnostic.json", {"samples": samples,
            "profile": profile.to_dict(), "display": not args.no_display,
            "pose": processor.provenance if processor else None,
            "take_id": result.take_id if result else None})
        if not args.no_display:
            import cv2
            cv2.destroyAllWindows()
    print(json.dumps({"take_dir": str(workspace.take_paths(result).root), "state": result.state.value}))
    return 0 if result.state.value == "finalized" else 2

if __name__ == "__main__":
    raise SystemExit(main())
