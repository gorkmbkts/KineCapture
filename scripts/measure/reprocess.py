"""A new version of the real take, from the same untouched raw recording.

The existing version and its evidence are left exactly as they are: this
writes a new run directory beside it, which is the only way this application
ever produces a second version.

Depth archiving is off. The tracking still runs at NEURAL_PLUS, exactly as the
original version did - what is skipped is writing another 2.9 GB of depth
frames into the user's take for a comparison that does not read them.
"""
import json, sys, time
from pathlib import Path
from kinecapture.processing.jobs import ProcessingConfig, process_take

TAKE = Path(
    r"C:\kc15\ry8kajfjq\datasets\projects\prj_20260916T141947_23b4"
    r"\participants\P0001\sessions\ses_20260916T151622_57a9"
    r"\takes\take_20260920T195059_c183"
)
started = time.perf_counter()
out = process_take(TAKE, ProcessingConfig(
    body_format="BODY_38", depth_mode="NEURAL_PLUS",
    body_model="HUMAN_BODY_ACCURATE", body_fitting=True,
    confidence_threshold=40, store_depth=False, store_proxy=True,
    compute_body=True, thumbnail_count=12,
))
job = json.loads((out / "job.json").read_text(encoding="utf-8"))
print(json.dumps({
    "output": str(out), "state": job["state"], "frames": job["frames_processed"],
    "issues": job.get("issues"), "coverage": job.get("coverage"),
    "subject_status": job.get("subject_status"),
    "seconds": round(time.perf_counter() - started, 1),
}, ensure_ascii=False))
