import argparse
import json
from pathlib import Path
from .jobs import ProcessingConfig, process_take, restart_job
from kinecapture.core.jsonio import read_json

def main():
    parser = argparse.ArgumentParser(description="KineCapture — Verileri Hesapla (GUI bağımsız)")
    parser.add_argument("take", type=Path, nargs="?")
    parser.add_argument("--restart", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--body-format", default="BODY_38", choices=("BODY_18", "BODY_34", "BODY_38"))
    parser.add_argument("--depth-mode", default="NEURAL_PLUS")
    parser.add_argument("--body-model", default="HUMAN_BODY_ACCURATE")
    parser.add_argument("--no-depth", action="store_true")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--no-body", action="store_true")
    parser.add_argument("--thumbnails", type=int, default=None,
                        help="üretilecek önizleme sayısı (0 = üretme)")
    parser.add_argument("--calibration-file")
    parser.add_argument("--subject-anchors", type=Path, help="JSON list of corrected source-image anchors; raw is never rewritten")
    args = parser.parse_args()
    if args.restart:
        output = restart_job(args.restart, output_root=args.output_root)
    elif args.take:
        output = process_take(args.take, ProcessingConfig(body_format=args.body_format, depth_mode=args.depth_mode,
            body_model=args.body_model, store_depth=not args.no_depth, store_proxy=not args.no_proxy,
            compute_body=not args.no_body, calibration_file=args.calibration_file,
            **({"thumbnail_count": args.thumbnails} if args.thumbnails is not None else {}),
            subject_anchors=tuple(read_json(args.subject_anchors)) if args.subject_anchors else ()), output_root=args.output_root)
    else:
        parser.error("take veya --restart gerekli")
    job = read_json(output / "job.json")
    print(json.dumps({"output": str(output), "state": job["state"], "frames": job["frames_processed"],
                      "declared": job.get("source_frames_declared"), "rate_fps": job.get("rate_fps"),
                      "thumbnails": len((job.get("thumbnails") or {}).get("entries", [])),
                      "summary_levels": len((job.get("summary") or {}).get("levels", [])),
                      "issues": job.get("issues"), "error": job.get("error")}, ensure_ascii=False))
    return 0 if job["state"] == "complete" else 2

if __name__ == "__main__":
    raise SystemExit(main())
