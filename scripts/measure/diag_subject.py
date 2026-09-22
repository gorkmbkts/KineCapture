"""What the SDK actually saw around the moment the subject was lost.

Read-only: the SVO is replayed, nothing in the take is written. The output is
a JSONL of per-frame facts - every body, its tracker id, state, root position
and the measurements the subject lock scores on - so the cause can be read off
rather than guessed at.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.capture.subject_lock import SubjectSignature, _root_position
from kinecapture.domain.project import CaptureProfile

TAKE = Path(
    r"C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4"
    r"\participants\P0001\sessions\ses_20260916T151622_57a9"
    r"\takes\take_20260920T195059_c183"
)
OUT = Path(sys.argv[1])
LAST = int(sys.argv[2]) if len(sys.argv) > 2 else 780

profile = CaptureProfile(
    fps=60,
    resolution="HD720",
    body_format="BODY_38",
    body_tracking_model="HUMAN_BODY_ACCURATE",
    depth_mode="NEURAL_PLUS",
    enable_body_fitting=True,
    allow_reduced_precision_inference=False,
    detection_confidence=40,
    enable_depth=True,
    enable_body_tracking=True,
    store_skeleton=True,
    store_proxy=False,
    preview_enabled=False,
    coordinate_system="RIGHT_HANDED_Y_UP",
    length_unit="METER",
)

backend = ZedCameraBackend(profile, svo_path=TAKE / "raw" / "capture.svo2")
info = backend.connect()
spec = backend.skeleton_spec()
backend.start_preview()
print("opened;", backend.source_frame_count, "frames;", spec.name, flush=True)

started = time.perf_counter()
rows = []
index = 0
while index <= LAST:
    try:
        packet = backend.grab_frame()
    except EOFError:
        break
    if packet is None:
        break
    bodies = []
    for body in packet.bodies:
        point = _root_position(body, spec)
        sig = SubjectSignature.measure(body, spec)
        joints = np.asarray(body.joint_positions_xyz, dtype=float)
        finite = np.isfinite(joints).all(axis=1)
        extent = 0.0
        if finite.sum() >= 2:
            usable = joints[finite]
            extent = float(np.max(usable, axis=0)[1] - np.min(usable, axis=0)[1])
        bodies.append(
            {
                "id": int(body.tracking_id),
                "state": str(getattr(body.tracking_state, "value", body.tracking_state)),
                "action": str(getattr(body, "action_state", "")),
                "conf": round(float(body.body_confidence), 1),
                "valid": int(finite.sum()),
                "root": None if point is None else [round(float(v), 4) for v in point],
                "stature": round(float(sig.stature), 4) if sig.stature == sig.stature else None,
                "usable_sig": bool(sig.is_usable),
                "y_extent": round(extent, 4),
            }
        )
    rows.append(
        {
            "i": index,
            "pos": packet.source_position,
            "cam_ns": packet.camera_timestamp_ns,
            "n": len(packet.bodies),
            "bodies": bodies,
        }
    )
    index += 1
    if index % 100 == 0:
        print(f"{index} frames, {time.perf_counter()-started:.0f}s", flush=True)

backend.disconnect()
OUT.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
print("wrote", OUT, len(rows), "rows in", round(time.perf_counter() - started, 1), "s")
