"""Get RGB, depth and pose back out of a finished take, without touching it.

The point of the immutable archive is that a recording can be reprocessed years
later into a dataset nobody has thought of yet. That is only true if there is a
way to *read* it, so this is that way: a command that reads a take and writes a
new derived bundle beside it, leaving ``raw/`` byte-for-byte alone.

```powershell
conda run -n KineSynth python -m kinecapture.tools.extract_raw <take_dir> --out <dir>
conda run -n KineSynth python -m kinecapture.tools.extract_raw <take_dir> --verify
conda run -n KineSynth python -m kinecapture.tools.extract_raw <take_dir> --range 100 220
```

Two sources, and the difference matters
---------------------------------------
Depth comes from ``raw/rgbd/`` - the exact metric map the camera produced.
Colour comes from ``raw/rgbd/`` too when it is there, and otherwise from the
SVO2, which requires the ZED SDK. Depth is **never** taken from the SVO2:
replaying one was measured on this hardware to produce a different depth map
from the one that was recorded, so doing so would silently substitute a
reconstruction for a measurement.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture import APP_NAME, RAW_ARCHIVE_SCHEMA_VERSION
from kinecapture.core.fingerprint import verify_checksum_manifest
from kinecapture.core.jsonio import read_json_mapping, read_jsonl, write_json
from kinecapture.core.logging import setup_logging
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.dataset.workspace import TakePaths
from kinecapture.recording.rgbd_archive import RgbdArchiveReader


def _index_records(paths: TakePaths) -> list[dict[str, Any]]:
    if not path_exists(paths.raw_index):
        return []
    return [
        record
        for record in read_jsonl(paths.raw_index)
        if record.get("record") == "frame"
    ]


def verify(paths: TakePaths) -> int:
    """Check that the archive is complete and unmodified. Writes nothing."""
    problems: list[str] = []

    if not path_exists(paths.raw_manifest):
        print("  ham manifest yok: bu kayıt özellik katmanından önce alınmış.")
    else:
        manifest = read_json_mapping(paths.raw_manifest)
        print(f"  şema        : {manifest.get('schema_version')}")
        native = manifest.get("native_recording") or {}
        print(
            f"  native      : {native.get('format')} "
            f"sıkıştırma={native.get('compression_mode')} "
            f"kayıpsız={native.get('lossless')}"
        )
        depth = (manifest.get("rgbd_archive") or {}).get("depth") or {}
        print(
            f"  derinlik    : codec={depth.get('codec')} "
            f"kayıpsız={depth.get('lossless')} kare={depth.get('frames')} "
            f"düşen={depth.get('dropped')}"
        )
        if depth.get("dropped"):
            problems.append("derinlik kareleri kaybedilmiş")

    if path_exists(paths.checksums):
        mismatches = verify_checksum_manifest(
            read_json_mapping(paths.checksums), paths.root
        )
        if mismatches:
            for item in mismatches:
                problems.append(f"{item['file']}: {item['issue']}")
            print(f"  checksum    : {len(mismatches)} SORUN")
        else:
            print("  checksum    : tamamı eşleşti")
    else:
        problems.append("checksums.json yok")

    reader = RgbdArchiveReader(paths.rgbd_dir)
    chunk_problems = reader.verify()
    if chunk_problems:
        for item in chunk_problems:
            problems.append(f"{item['file']}: {item['issue']}")
        print(f"  chunk'lar   : {len(chunk_problems)} SORUN")
    else:
        stored = reader.positions()
        print(
            f"  chunk'lar   : tamamı okunabilir "
            f"(derinlik {len(stored['depth'])}, renk {len(stored['color'])} kare)"
        )

    records = _index_records(paths)
    print(f"  senkron idx : {len(records)} kare")
    if records:
        positions = [int(r["p"]) for r in records]
        if positions != list(range(len(positions))):
            problems.append("senkron indeks konumları sürekli değil")

    if problems:
        print("\nSORUNLAR:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nHam arşiv bütün ve değişmemiş.")
    return 0


def extract(
    paths: TakePaths,
    out_dir: Path,
    *,
    first: Optional[int],
    last: Optional[int],
    with_color: bool,
) -> int:
    """Write a derived bundle. Never modifies the take."""
    reader = RgbdArchiveReader(paths.rgbd_dir)
    records = _index_records(paths)
    if not records:
        print("Senkron indeks yok; bu kayıttan çıkarım yapılamıyor.", file=sys.stderr)
        return 2

    low = 0 if first is None else int(first)
    high = (len(records) - 1) if last is None else int(last)
    wanted = {
        int(record["p"])
        for record in records
        if low <= int(record["p"]) <= high
    }
    if not wanted:
        print("İstenen aralıkta kare yok.", file=sys.stderr)
        return 2

    ensure_dir(out_dir)
    depth_positions: list[int] = []
    depth_frames: list[np.ndarray] = []
    for position, frame in reader.iter_depth():
        if position in wanted:
            depth_positions.append(position)
            depth_frames.append(frame)

    color_positions: list[int] = []
    color_frames: list[np.ndarray] = []
    if with_color:
        for position, frame in reader.iter_color():
            if position in wanted:
                color_positions.append(position)
                color_frames.append(frame)

    payload: dict[str, np.ndarray] = {
        "positions": np.asarray(sorted(wanted), dtype=np.int64),
        "frame_indices": np.asarray(
            [int(r["i"]) for r in records if int(r["p"]) in wanted], dtype=np.int64
        ),
        "camera_timestamps_ns": np.asarray(
            [int(r["cam_ns"]) for r in records if int(r["p"]) in wanted],
            dtype=np.int64,
        ),
    }
    if depth_frames:
        payload["depth_positions"] = np.asarray(depth_positions, dtype=np.int64)
        payload["depth_m"] = np.stack(depth_frames).astype(np.float32)
    if color_frames:
        payload["color_positions"] = np.asarray(color_positions, dtype=np.int64)
        payload["color_rgb"] = np.stack(color_frames).astype(np.uint8)

    target = out_dir / f"{paths.root.name}_frames_{low}_{high}.npz"
    with open(long_path(target), "wb") as handle:
        np.savez_compressed(handle, **payload)

    write_json(
        out_dir / "extraction_manifest.json",
        {
            "schema_version": RAW_ARCHIVE_SCHEMA_VERSION,
            "produced_by": APP_NAME,
            "source_take": str(paths.root),
            "file": target.name,
            "positions": [low, high],
            "frames": len(wanted),
            "arrays": {
                "positions": "[N] int64 - kayıt içi konum, etiket sözleşmesiyle aynı",
                "frame_indices": "[N] int64 - kameranın kendi kare numarası",
                "camera_timestamps_ns": "[N] int64",
                "depth_m": "[Nd, H, W] float32 metre, geçersiz piksel NaN",
                "color_rgb": "[Nc, H, W, 3] uint8, RGB",
            },
            "depth_source": "raw/rgbd/ (ölçülen derinlik, yeniden hesaplanmış değil)",
            "color_source": (
                "raw/rgbd/" if color_frames else "yazılmadı (SVO2'de duruyor)"
            ),
            "raw_untouched": True,
            "note": (
                "Bu bir TÜRETİLMİŞ dosyadır. Otoritatif kaynak kaydın kendi "
                "raw/ klasörüdür ve bu işlem onu değiştirmez."
            ),
        },
        overwrite=True,
    )
    print(f"Yazıldı: {target}")
    print(f"  kare      : {len(wanted)}")
    print(f"  derinlik  : {len(depth_frames)}")
    print(f"  renk      : {len(color_frames)}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kinecapture.tools.extract_raw",
        description=(
            "Bir kaydın ham RGB-D arşivini doğrular veya ondan türetilmiş bir "
            "paket çıkarır. Ham veriyi değiştirmez."
        ),
    )
    parser.add_argument("take", type=Path, help="Kayıt (take) klasörü")
    parser.add_argument("--out", type=Path, default=None, help="Çıkarım klasörü")
    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("FIRST", "LAST"),
        default=None,
        help="Kayıt içi konum aralığı (her iki uç dahil)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Yalnız bütünlük doğrula, hiçbir şey yazma",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Renk karelerini çıkarma"
    )
    args = parser.parse_args(argv)

    setup_logging("WARNING", None)
    take_dir = args.take.expanduser().resolve()
    if not take_dir.is_dir():
        print(f"Kayıt klasörü bulunamadı: {take_dir}", file=sys.stderr)
        return 2
    paths = TakePaths(take_dir)

    print(f"Kayıt: {take_dir}")
    if args.verify or args.out is None:
        return verify(paths)

    first, last = (args.range or (None, None))
    return extract(
        paths,
        args.out.expanduser().resolve(),
        first=first,
        last=last,
        with_color=not args.no_color,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
