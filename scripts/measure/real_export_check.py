"""Canonical export on a COPY of real processed recordings, checked by the oracle.

Release gate A2, real-data leg. Given one or more real ``run_<id>`` folders,
this copies what the export reads - the project and label schema files, the
participant and session files, and each take (``take.json``, the version,
its annotation and subject sidecars; ``--with-raw`` adds the raw recording) -
into a temporary tree with the same layout, builds the canonical package from
the copy, and compares it with what ``tests/release_oracle.py`` derives from
the copied files.

The originals are only read. Every original file the check touches is hashed
before and after, and the run fails if any hash moved.

    python scripts/measure/real_export_check.py <out.json> <run_dir> [<run_dir> ...]
        [--work <dir>] [--with-raw] [--keep]

``--work`` is where the copy goes (default: a new temporary folder); without
``--keep`` the copy is deleted afterwards, because it is a copy of real data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests"))

import release_oracle as oracle  # noqa: E402

from kinecapture.domain.labels import LabelSchema  # noqa: E402
from kinecapture.export.canonical import build_release  # noqa: E402


def extended(path: Path) -> str:
    text = os.path.abspath(str(path))
    return text if text.startswith("\\\\?\\") else "\\\\?\\" + text


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(extended(path), "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(paths: list[Path]) -> dict[str, str]:
    """Hash of every file under ``paths``, keyed by absolute path."""
    out: dict[str, str] = {}
    for root in paths:
        root_ext = Path(extended(root))
        if root_ext.is_file():
            out[str(root)] = sha256(root)
            continue
        for path in sorted(root_ext.rglob("*")):
            if path.is_file():
                out[str(path).removeprefix("\\\\?\\")] = sha256(path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--work", type=Path, default=None)
    parser.add_argument("--with-raw", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    runs = [run.resolve() for run in args.runs]
    # <project>/participants/<P>/sessions/<S>/takes/<T>/derived/processing/<run>
    takes = [run.parents[2] for run in runs]
    projects = {take.parents[5] for take in takes}
    if len(projects) != 1:
        raise SystemExit("Bütün sürümler aynı projeden olmalı.")
    project = projects.pop()

    watched: list[Path] = [project / "project.json", project / "label_schema.json"]
    for take in takes:
        watched += [take.parents[3] / "participant.json", take.parents[1] / "session.json"]
        watched += [take / "take.json", take / "annotations"]
    for run in runs:
        watched.append(run)
    watched = [p for p in watched if Path(extended(p)).exists()]
    started = time.perf_counter()
    before = snapshot(watched)
    hashed_s = time.perf_counter() - started

    work = args.work or Path(tempfile.mkdtemp(prefix="kc_real_export_"))
    target_project = work / "projects" / project.name
    copies: list[Path] = []
    copy_started = time.perf_counter()
    for name in ("project.json", "label_schema.json"):
        Path(extended(target_project)).mkdir(parents=True, exist_ok=True)
        shutil.copy2(extended(project / name), extended(target_project / name))
    for run, take in zip(runs, takes):
        relative = take.relative_to(project)
        target_take = target_project / relative
        Path(extended(target_take / "derived" / "processing")).mkdir(parents=True, exist_ok=True)
        for up, name in ((3, "participant.json"), (1, "session.json")):
            source = take.parents[up] / name
            if Path(extended(source)).is_file():
                destination = target_project / relative.parents[up] / name
                Path(extended(destination.parent)).mkdir(parents=True, exist_ok=True)
                shutil.copy2(extended(source), extended(destination))
        shutil.copy2(extended(take / "take.json"), extended(target_take / "take.json"))
        if Path(extended(take / "annotations")).is_dir() and not Path(extended(target_take / "annotations")).exists():
            shutil.copytree(extended(take / "annotations"), extended(target_take / "annotations"))
        if args.with_raw and not Path(extended(target_take / "raw")).exists():
            shutil.copytree(extended(take / "raw"), extended(target_take / "raw"))
        target_run = target_take / "derived" / "processing" / run.name
        shutil.copytree(extended(run), extended(target_run))
        copies.append(target_run)
    copy_s = time.perf_counter() - copy_started

    schema = LabelSchema.from_dict(
        json.loads(Path(extended(target_project / "label_schema.json")).read_text("utf-8"))
    )
    build_started = time.perf_counter()
    report = build_release(copies, work / "releases", schema, operator="release-gate")
    build_s = time.perf_counter() - build_started

    verify_started = time.perf_counter()
    problems = oracle.verify(
        report.release_dir,
        copies,
        json.loads(Path(extended(target_project / "label_schema.json")).read_text("utf-8")),
        project=json.loads(Path(extended(target_project / "project.json")).read_text("utf-8")),
    )
    verify_s = time.perf_counter() - verify_started

    after = snapshot(watched)
    moved = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    manifest = json.loads(Path(extended(report.release_dir / "manifest.json")).read_text("utf-8"))
    result = {
        "runs": [str(r) for r in runs],
        "copy": str(work),
        "with_raw": bool(args.with_raw),
        "samples": report.samples,
        "versions_accepted": [v.run_id for v in report.accepted],
        "versions_refused": {v.run_id: [r.value for r in v.refusals] for v in report.refused},
        "skeletons": sorted(manifest.get("skeletons", {})),
        "counts": manifest["counts"],
        "oracle_problems": problems,
        "originals_hashed": len(before),
        "originals_changed": moved,
        "seconds": {
            "hash_originals": round(hashed_s, 2),
            "copy": round(copy_s, 2),
            "build_release": round(build_s, 2),
            "oracle": round(verify_s, 2),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if not args.keep:
        shutil.rmtree(extended(work), ignore_errors=True)
    return 0 if not problems and not moved else 1


if __name__ == "__main__":
    raise SystemExit(main())
