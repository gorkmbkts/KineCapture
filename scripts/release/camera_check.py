"""Open the attached ZED once from an installed release, grab a few frames, close.

    <kurulum>\\env\\python.exe -B scripts\\release\\camera_check.py --report sonuc.json

The installer's own verification never opens a camera; this is the release
gate's "a real ZED, if attached, connects" step, run by hand against an
installed copy. Nothing is recorded and nothing is written but the report.
With no camera attached it says so and exits 0.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", required=True)
    parser.add_argument("--frames", type=int, default=30)
    args = parser.parse_args(argv)

    from kinecapture.camera.zed import ZedCameraBackend, list_devices, sdk_bin_directory, sdk_version

    result: dict = {"python": sys.executable, "sdk_version": sdk_version(), "sdk_bin": str(sdk_bin_directory())}
    devices = list_devices()
    result["devices"] = devices
    if not devices:
        result["ok"] = True
        result["note"] = "bağlı ZED yok; açma denenmedi"
    else:
        backend = ZedCameraBackend()
        started = time.perf_counter()
        info = backend.connect()
        result["connect_s"] = round(time.perf_counter() - started, 2)
        result["camera"] = {"model": info.model, "serial": info.serial_number, "firmware": info.firmware_version,
                            "resolution": list(info.resolution), "target_fps": info.target_fps}
        try:
            backend.start_preview()
            frames = with_depth = 0
            began = time.perf_counter()
            deadline = began + 20.0
            while frames < args.frames and time.perf_counter() < deadline:
                packet = backend.grab_frame()
                if packet is None or packet.color_frame is None:
                    continue
                frames += 1
                if packet.depth_frame is not None:
                    with_depth += 1
            elapsed = time.perf_counter() - began
            result["frames"] = frames
            result["frames_with_depth"] = with_depth
            result["fps_observed"] = round(frames / elapsed, 1) if elapsed > 0 else None
            backend.stop_preview()
        finally:
            backend.disconnect()
        result["ok"] = result.get("frames", 0) >= args.frames
    Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
