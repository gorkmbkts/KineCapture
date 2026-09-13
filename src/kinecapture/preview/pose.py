"""CPU-only 2D pose preview using pinned OpenCV Zoo ONNX models.

Model weights are explicit local artifacts, never downloaded on capture start.
Preview indices are detection-local, not tracker identities or participants.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np

from kinecapture.domain.models import FramePacket
from kinecapture.core.fingerprint import hash_file

BONES = ((11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),
         (23,24),(23,25),(25,27),(24,26),(26,28),(27,29),(29,31),(28,30),(30,32))

@dataclass(frozen=True)
class PreviewPerson:
    bbox: np.ndarray
    points: np.ndarray
    confidence: np.ndarray

@dataclass(frozen=True)
class PosePreview:
    packet: FramePacket
    people: tuple[PreviewPerson, ...]

    def anchor(self, x: float, y: float) -> dict:
        """Click and boxes use canonical source pixels, not resized display pixels."""
        matches = [p for p in self.people if p.bbox[0,0] <= x <= p.bbox[1,0]
                   and p.bbox[0,1] <= y <= p.bbox[1,1]]
        if len(matches) != 1:
            raise ValueError("Seçim tek bir kişiyi göstermeli; örtüşmeyen bir kare seçin.")
        return {"schema_version": "1.0.0", "frame_index": self.packet.frame_index,
                "source_position": self.packet.source_position,
                "camera_timestamp_ns": self.packet.camera_timestamp_ns,
                "source_resolution": list(self.packet.resolution),
                "point_xy": [float(x), float(y)], "bbox_xyxy": matches[0].bbox.ravel().tolist(),
                "identity_semantics": "operator_selected_image_anchor; requires_offline_association"}

class CpuPosePreview:
    def __init__(self, model_dir: Path, *, max_people: int = 3):
        import cv2
        from .vendor.mp_persondet import MPPersonDet
        from .vendor.mp_pose import MPPose
        # Limit CPU pressure. No CUDA/DNN GPU work competes with SVO recording.
        cv2.setNumThreads(1)
        detector = Path(model_dir) / "person_detection_mediapipe_2023mar.onnx"
        pose = Path(model_dir) / "pose_estimation_mediapipe_2023mar.onnx"
        self.provenance = {"engine": "opencv_zoo_mediapipe_cpu", "opencv": cv2.__version__,
                           "models": {p.name: hash_file(p) for p in (detector, pose)}}
        self.detector = MPPersonDet(str(detector), scoreThreshold=0.65,
                                  backendId=cv2.dnn.DNN_BACKEND_OPENCV, targetId=cv2.dnn.DNN_TARGET_CPU)
        self.pose = MPPose(str(pose), backendId=cv2.dnn.DNN_BACKEND_OPENCV, targetId=cv2.dnn.DNN_TARGET_CPU)
        self.max_people = max_people

    def __call__(self, packet: FramePacket) -> PosePreview:
        import cv2
        if packet.color_frame is None:
            return PosePreview(packet, ())
        bgr = cv2.cvtColor(packet.color_frame, cv2.COLOR_RGB2BGR)
        scale = np.asarray(packet.resolution) / np.array([bgr.shape[1], bgr.shape[0]])
        people = []
        detections = self.detector.infer(bgr)
        for detection in sorted(detections, key=lambda d: -d[-1])[:self.max_people]:
            result = self.pose.infer(bgr, detection.copy())
            if result is None:
                continue
            bbox, landmarks = result[:2]
            people.append(PreviewPerson(bbox * scale, landmarks[:33,:2] * scale,
                                        np.minimum(landmarks[:33,3], landmarks[:33,4])))
        return PosePreview(packet, tuple(people))
