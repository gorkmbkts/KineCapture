"""Replay the real take through the real subject lock and log every decision.

Read-only. Selects tracker id 0 on the first frame, which is what the stored
anchor did (``source_image_anchor_preroll``), then records for every frame the
state, the reason, the contradiction run and the two similarity scores the veto
is made of. The point is to read the cause off the recording instead of
inferring it from counters.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.capture.subject_lock import (
    SubjectLock,
    SubjectLockState,
    SubjectSignature,
)
from kinecapture.domain.project import CaptureProfile

TAKE = Path(
    r"C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4"
    r"\participants\P0001\sessions\ses_20260916T151622_57a9"
    r"\takes\take_20260920T195059_c183"
)
OUT = Path(sys.argv[1])
LAST = int(sys.argv[2]) if len(sys.argv) > 2 else 1473

profile = CaptureProfile(
    fps=60, resolution="HD720", body_format="BODY_38",
    body_tracking_model="HUMAN_BODY_ACCURATE", depth_mode="NEURAL_PLUS",
    enable_body_fitting=True, allow_reduced_precision_inference=False,
    detection_confidence=40, enable_depth=True, enable_body_tracking=True,
    store_skeleton=True, store_proxy=False, preview_enabled=False,
    coordinate_system="RIGHT_HANDED_Y_UP", length_unit="METER",
)

backend = ZedCameraBackend(profile, svo_path=TAKE / "raw" / "capture.svo2")
backend.connect()
spec = backend.skeleton_spec()
backend.start_preview()

lock = SubjectLock()
lock.spec = spec
rows = []
started = time.perf_counter()
index = 0
while index <= LAST:
    try:
        packet = backend.grab_frame()
    except EOFError:
        break
    if packet is None:
        break
    if index == 0:
        first = next((b for b in packet.bodies if int(b.tracking_id) == 0), None)
        assert first is not None, "tracker 0 is not in the first frame"
        lock.select(
            first, frame_index=0, timestamp_ns=packet.camera_timestamp_ns, spec=spec
        )
        rows.append({"i": 0, "state": "locked", "reason": "selected", "n": len(packet.bodies)})
        index += 1
        continue

    # What the veto would see this frame, measured before the lock updates.
    body = next(
        (b for b in packet.bodies if int(b.tracking_id) == lock.tracking_id), None
    )
    limb = stature = None
    measured = None
    if body is not None and lock.signature.is_usable:
        found = SubjectSignature.measure(body, spec)
        measured = round(found.stature, 4) if found.stature == found.stature else None
        pair = lock.signature.similarity(found)
        limb = None if pair[0] != pair[0] else round(pair[0], 4)
        stature = None if pair[1] != pair[1] else round(pair[1], 4)

    before = lock.state
    result = lock.update(
        packet.bodies, frame_index=index, timestamp_ns=packet.camera_timestamp_ns
    )
    rows.append(
        {
            "i": index,
            "n": len(packet.bodies),
            "ids": sorted(int(b.tracking_id) for b in packet.bodies),
            "was": before.value,
            "state": result.state.value,
            "reason": result.reason,
            "run": lock._contradiction_run,
            "limb": limb,
            "stature_score": stature,
            "measured_stature": measured,
            "signature_stature": round(lock.signature.stature, 4),
        }
    )
    index += 1
    if index % 200 == 0:
        print(f"{index} frames {time.perf_counter()-started:.0f}s", flush=True)

backend.disconnect()
OUT.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
counters = dict(lock._counters)
print(json.dumps({"counters": counters, "final": lock.state.value}, ensure_ascii=False))
print("wrote", OUT, len(rows), "rows in", round(time.perf_counter() - started, 1), "s")
