"""Release gate A3, backend: how the offline layer scales with the project.

    python scripts/measure/scale_backend.py <out.json> [--work <dir>] [--only NAME]
        [--keep NAME]

Each scenario runs in its own child process, so its memory is its own: it
generates a seeded project with ``scale_dataset.py`` (temp folder only), then
times - and samples the resident set of - every step a user waits on:

* ``index_cold`` / ``index_warm``: ``build_index`` with and without its cache;
* ``library``: the version list every screen starts from;
* ``dataset_rows`` / ``aggregate``: what the Veri Seti screen and its four
  statistic blocks compute;
* ``review_open``: ``ReviewDataset`` with checksum verification, on a sample;
* ``export``: the canonical package from every version;
* ``oracle``: the independent reader checking that package in full.

Counts are checked on the way - takes, versions, repetitions, refusals - so a
number that is fast but wrong fails the run. Timings are wall clock on this
machine; the report records which.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

SCENARIOS: dict[str, dict[str, int]] = {
    # runs and labelled segments grow together; the 30k point is the combined
    # scenario of the task (>= 30 000 runs, >= 30 000 segments, >= 100 classes)
    "runs_1k": {"runs": 1_000, "segments": 1_000, "classes": 100, "awaiting": 100},
    "runs_10k": {"runs": 10_000, "segments": 10_000, "classes": 100, "awaiting": 1_000},
    "runs_30k": {"runs": 30_000, "segments": 30_000, "classes": 100, "awaiting": 3_000},
    # segments grow inside a fixed number of versions (dense labelling)
    "segments_1k": {"runs": 1_000, "segments": 1_000, "classes": 100, "awaiting": 0},
    "segments_10k": {"runs": 1_000, "segments": 10_000, "classes": 100, "awaiting": 0},
    "segments_30k": {"runs": 1_000, "segments": 30_000, "classes": 100, "awaiting": 0},
    # the class vocabulary grows, and one step past the threshold
    "classes_100": {"runs": 1_000, "segments": 10_000, "classes": 100, "awaiting": 0},
    "classes_150": {"runs": 1_000, "segments": 10_000, "classes": 150, "awaiting": 0},
    "classes_200": {"runs": 1_000, "segments": 10_000, "classes": 200, "awaiting": 0},
    # everything at once, with the widest vocabulary
    "combined_30k_200": {"runs": 30_000, "segments": 30_000, "classes": 200, "awaiting": 3_000},
}


# ------------------------------------------------------------------ child
class Meter:
    """Wall time and peak resident set of one phase, sampled every 10 ms."""

    def __init__(self) -> None:
        import psutil

        self._process = psutil.Process()
        self.phases: dict[str, dict[str, float]] = {}

    def run(self, name: str, function):  # noqa: ANN001, ANN201
        peak = [self._process.memory_info().rss]
        start_rss = peak[0]
        stop = threading.Event()

        def sample() -> None:
            while not stop.wait(0.01):
                peak[0] = max(peak[0], self._process.memory_info().rss)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        started = time.perf_counter()
        try:
            result = function()
        finally:
            seconds = time.perf_counter() - started
            stop.set()
            sampler.join()
            peak[0] = max(peak[0], self._process.memory_info().rss)
        self.phases[name] = {
            "seconds": round(seconds, 3),
            "rss_start_mb": round(start_rss / 2**20, 1),
            "rss_peak_mb": round(peak[0] / 2**20, 1),
            "rss_growth_mb": round((peak[0] - start_rss) / 2**20, 1),
        }
        return result


def child(name: str, work: Path, out: Path, keep: bool) -> int:
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(REPO / "tests"))
    import release_oracle as oracle
    import scale_dataset

    from kinecapture.core.paths import extended_path
    from kinecapture.dataset.summary_index import CACHE_DIRNAME, build_index
    from kinecapture.domain.labels import LabelSchema
    from kinecapture.export.canonical import build_release
    from kinecapture.processing.review import ReviewDataset
    from kinecapture.studio.services.library import LibraryService
    from kinecapture.studio.viewmodels.dataset import _summarise, aggregate

    spec = SCENARIOS[name]
    meter = Meter()
    target = work / name
    if Path(extended_path(target)).exists():
        shutil.rmtree(extended_path(target))
    generated = meter.run(
        "generate", lambda: scale_dataset.generate(target, **spec, frames=40, participants=100)
    )
    root = Path(generated["project_root"])
    schema_dict = json.loads((root / "label_schema.json").read_text("utf-8"))
    project = json.loads((root / "project.json").read_text("utf-8"))
    schema = LabelSchema.from_dict(schema_dict)
    problems: list[str] = []

    cache = root / CACHE_DIRNAME
    shutil.rmtree(extended_path(cache), ignore_errors=True)
    # Three different costs. The first read of a file this machine has just
    # written is paid again by the on-access virus scan (measured ~40x per
    # open); a forced rescan of files already seen is the steady state; and
    # with its cache the index only stats folders.
    index = meter.run("index_cold", lambda: build_index(root, force=True))
    meter.run("index_rescan", lambda: build_index(root, force=True))
    meter.run("index_warm", lambda: build_index(root))
    if len(index) != spec["runs"] + spec["awaiting"]:
        problems.append(f"index saw {len(index)} takes, wrote {spec['runs'] + spec['awaiting']}")
    if len(index.published_runs()) != spec["runs"]:
        problems.append(f"index saw {len(index.published_runs())} versions, wrote {spec['runs']}")
    if len(index.awaiting_processing()) != spec["awaiting"]:
        problems.append(f"{len(index.awaiting_processing())} waiting, wrote {spec['awaiting']}")

    service = LibraryService()
    versions = meter.run("library", lambda: service.versions(index))
    rows = meter.run("dataset_rows", lambda: [_summarise(v, schema) for v in versions])
    meter.run("dataset_rows_again", lambda: [_summarise(v, schema) for v in versions])
    stats = meter.run("aggregate", lambda: aggregate(rows))
    # The screen's own path: DatasetViewModel.reload, with its row cache. The
    # first visit fills the cache; the second is what every later visit costs.
    from types import SimpleNamespace

    from kinecapture.dataset.workspace import ProjectWorkspace
    from kinecapture.studio.viewmodels.dataset import DatasetViewModel

    screen = DatasetViewModel(SimpleNamespace(workspace=ProjectWorkspace.open(root)))
    meter.run("dataset_screen_first", screen.reload)
    meter.run("dataset_screen_again", screen.reload)
    if screen.totals.value.movements != spec["segments"]:
        problems.append(
            f"Veri Seti screen counts {screen.totals.value.movements}, wrote {spec['segments']}"
        )
    movements = sum(r.movements for r in rows)
    if movements != spec["segments"]:
        problems.append(f"Veri Seti counts {movements} repetitions, wrote {spec['segments']}")
    classes_seen = len(stats.exercises)
    if sum(stats.exercises.values()) != spec["segments"]:
        problems.append("exercise distribution does not add up to the repetitions")

    rng = random.Random(7)
    sample_runs = rng.sample(generated["run_dirs"], min(50, len(generated["run_dirs"])))
    opens: list[float] = []

    def open_some() -> None:
        for directory in sample_runs:
            began = time.perf_counter()
            dataset = ReviewDataset(Path(directory), verify=True)
            dataset.window("joints", 0, 10)
            dataset.close()
            opens.append(time.perf_counter() - began)

    meter.run("review_open", open_some)

    releases = work / f"{name}_releases"
    report = meter.run(
        "export",
        lambda: build_release([Path(d) for d in generated["run_dirs"]], releases, schema),
    )
    refused = spec["runs"] and generated["deliberately_refused"]
    expected_refused = refused["no_athlete"] + refused["open_error"] if refused else 0
    if len(report.refused) != expected_refused:
        problems.append(f"{len(report.refused)} versions refused, expected {expected_refused}")
    oracle_problems = meter.run(
        "oracle",
        lambda: oracle.verify(
            report.release_dir, [Path(d) for d in generated["run_dirs"]], schema_dict,
            project=project,
        ),
    )
    problems.extend(oracle_problems[:20])

    package_files = package_bytes = 0
    for _name, path in __import__("kinecapture.core.paths", fromlist=["iter_files"]).iter_files(report.release_dir):
        package_files += 1
        package_bytes += path.stat().st_size

    result = {
        "scenario": name,
        "spec": spec,
        "generated": {k: v for k, v in generated.items() if k not in ("run_dirs",)},
        "phases": meter.phases,
        "review_open": {
            "count": len(opens),
            "mean_s": round(sum(opens) / len(opens), 4) if opens else None,
            "max_s": round(max(opens), 4) if opens else None,
        },
        "counts": {
            "takes": len(index),
            "versions": len(versions),
            "dataset_rows": len(rows),
            "repetitions": movements,
            "exercise_classes_seen": classes_seen,
            "error_classes_seen": len(stats.errors),
            "samples_exported": report.samples,
            "versions_refused": len(report.refused),
        },
        "package": {"files": package_files, "bytes": package_bytes},
        "oracle_problems": len(oracle_problems),
        "problems": problems,
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if not keep:
        shutil.rmtree(extended_path(target), ignore_errors=True)
        shutil.rmtree(extended_path(releases), ignore_errors=True)
    return 0 if not problems else 1


# ----------------------------------------------------------------- parent
def slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of log(time) on log(size): ~1 linear, ~2 quadratic."""
    import math

    usable = [(math.log(x), math.log(y)) for x, y in points if x > 0 and y > 0]
    if len(usable) < 2:
        return None
    mx = sum(x for x, _ in usable) / len(usable)
    my = sum(y for _, y in usable) / len(usable)
    num = sum((x - mx) * (y - my) for x, y in usable)
    den = sum((x - mx) ** 2 for x, _ in usable)
    return round(num / den, 2) if den else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--work", type=Path, default=Path(tempfile.gettempdir()) / "kcs")
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--keep", action="append", default=[])
    parser.add_argument("--child", default=None)
    parser.add_argument("--child-out", type=Path, default=None)
    args = parser.parse_args()

    if args.child:
        return child(args.child, args.work, args.child_out, args.child in args.keep)

    args.work.mkdir(parents=True, exist_ok=True)
    names = args.only or list(SCENARIOS)
    results: dict[str, Any] = {}
    if args.out.is_file():
        results = json.loads(args.out.read_text("utf-8")).get("scenarios", {})
    for name in names:
        child_out = args.out.with_name(f"{args.out.stem}_{name}.json")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), str(args.out),
                   "--work", str(args.work), "--child", name, "--child-out", str(child_out)]
        for kept in args.keep:
            command += ["--keep", kept]
        started = time.perf_counter()
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if child_out.is_file():
            results[name] = json.loads(child_out.read_text("utf-8"))
        else:
            results[name] = {"scenario": name, "failed": True,
                             "stderr": completed.stderr[-3000:], "code": completed.returncode}
        results[name]["exit_code"] = completed.returncode
        results[name]["wall_s"] = round(time.perf_counter() - started, 1)
        phases = results[name].get("phases", {})
        print(f"    exit={completed.returncode} " + " ".join(
            f"{k}={v['seconds']}s/{v['rss_peak_mb']}MB" for k, v in phases.items()), flush=True)
        if results[name].get("problems"):
            print("    PROBLEMS:", results[name]["problems"][:5], flush=True)
        curves: dict[str, Any] = {}
        for family, key in (("runs", "runs"), ("segments", "segments"), ("classes", "classes")):
            members = [r for n, r in results.items() if n.startswith(family + "_") and "phases" in r]
            for phase in ("index_cold", "index_rescan", "index_warm", "library", "dataset_rows",
                          "dataset_rows_again", "aggregate", "dataset_screen_first",
                          "dataset_screen_again", "export", "oracle"):
                points = [(r["spec"][key], r["phases"][phase]["seconds"]) for r in members if phase in r["phases"]]
                if len(points) >= 2:
                    curves.setdefault(family, {})[phase] = {"points": sorted(points), "loglog_slope": slope(points)}
        payload = {
            "machine": {"python": sys.version.split()[0], "platform": sys.platform,
                        "cpu_count": os.cpu_count()},
            "scenarios": results,
            "curves": curves,
        }
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
