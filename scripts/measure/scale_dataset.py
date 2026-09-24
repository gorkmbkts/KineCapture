"""Seeded synthetic project at scale, for the release gate's A3 measurements.

    python scripts/measure/scale_dataset.py <out-dir> --runs 30000 --segments 30000
        --classes 100 [--frames 40] [--participants 100] [--seed 23]
        [--awaiting 0] [--skeleton BODY_18]

Writes one project under ``<out-dir>/datasets`` with ``--runs`` takes, each
holding one published processing version (``run_<id>``) that ``ReviewDataset``
opens and ``build_release`` exports - the same files, the same schema, a real
checksum manifest - but no raw recording, no proxy video and no depth: the
sizes that matter here are counts, not megabytes. ``--segments`` labelled
repetitions are spread over the versions, each with a movement class and zero
to two error intervals drawn from ``--classes`` movement and ``--classes``
error classes (Turkish names, spaces and punctuation included). About one in a
hundred versions is left with no athlete chosen and one in a hundred with an
unclassified error, so the refusal paths run at scale too. ``--awaiting`` adds
takes that have been recorded but not processed, which is what fills the
processing queue.

The project itself - project file, label schema, participants, sessions - is
created through the application's own ``ProjectWorkspace``; only the per-take
bulk is written directly, because 30 000 takes through the capture pipeline
would measure the capture pipeline.

Deterministic: the same arguments and seed produce the same ids, labels and
arrays. Refuses to write anywhere but a temporary or scratch folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture import APP_VERSION
from kinecapture.core.paths import long_path
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.enums import ConsentStatus, DataOrigin, TakeState
from kinecapture.domain.labels import LabelSchema
from kinecapture.domain.project import Take
from kinecapture.processing.jobs import PROCESSING_SCHEMA_VERSION
from kinecapture.visualization.skeleton_spec import spec_for_zed_body_format

FIXED_TIME = "2026-09-23T12:00:00.000+00:00"
FPS = 30

_EXERCISE_WORDS = ("Squat", "Lunge", "Köprü", "Çömelme", "Sıçrama", "Şınav",
                   "Ağırlık kaldırma", "Öne eğilme", "Diz çekme", "Yan adım")
_ERROR_WORDS = ("Diz içe çöküyor", "Topuk kalkıyor", "Gövde öne eğik",
                "Kalça düşüyor", "Omuz yükseliyor", "Ayak dışa dönük",
                "Bel çukuru artıyor", "Baş öne düşüyor", "Diz kilitleniyor",
                "Dirsek açılıyor")
_SIDES = ("sol", "sağ", "iki taraf", "ön", "arka")


def _refuse_real_location(root: Path) -> None:
    resolved = os.path.abspath(str(root)).lower()
    temp = os.path.abspath(tempfile.gettempdir()).lower()
    if not (resolved.startswith(temp) or "scratchpad" in resolved or "pytest-of-" in resolved):
        raise SystemExit(
            f"Ölçek verisi yalnız geçici bir klasöre yazılır; reddedildi: {root}"
        )


_EXTENDED = "\\\\?\\"


def _extended(path: Path) -> str:
    """Always extended-length prefixed: a walk below it may pass MAX_PATH."""
    text = os.path.abspath(str(path))
    return text if text.startswith(_EXTENDED) else _EXTENDED + text


def _write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    with open(long_path(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(long_path(path)).read_bytes()).hexdigest()


def class_names(count: int, words: tuple[str, ...]) -> list[str]:
    """``count`` distinct, human-looking class names with Turkish letters."""
    names = []
    for index in range(count):
        word = words[index % len(words)]
        side = _SIDES[(index // len(words)) % len(_SIDES)]
        names.append(f"{word} ({side}) — {index:03d}")
    return names


def make_schema(classes: int) -> LabelSchema:
    schema = LabelSchema.default()
    for name in class_names(classes, _EXERCISE_WORDS):
        schema.add_exercise(name)
    for index, name in enumerate(class_names(classes, _ERROR_WORDS)):
        if index % 4 == 0:
            schema.add_error_type_with_roles(name, ("left_knee",))
        else:
            schema.add_error_type(name)
    return schema


def _anchor(fingerprint: str, position: int) -> dict[str, Any]:
    return {
        "source_fingerprint": fingerprint,
        "source_position": int(position),
        "camera_timestamp_ns": int(position * (1_000_000_000 // FPS)),
    }


def _segments(
    rng: np.random.Generator,
    count: int,
    frames: int,
    fingerprint: str,
    exercises: list[str],
    errors: list[str],
    *,
    open_error: bool,
) -> list[dict[str, Any]]:
    samples = []
    span = max(1, frames // max(1, count))
    for index in range(count):
        start = min(frames - 1, index * span)
        end = min(frames - 1, start + max(0, span - 1))
        intervals = []
        for number in range(int(rng.integers(0, 3))):
            first = int(rng.integers(start, end + 1))
            last = int(rng.integers(first, end + 1))
            code = errors[int(rng.integers(0, len(errors)))]
            selected = number == 0 and bool(rng.integers(0, 2))
            intervals.append({
                "interval_id": f"err_{index:06d}{number}{fingerprint[-12:]}",
                "start": _anchor(fingerprint, first),
                "end": _anchor(fingerprint, last),
                "error_class": code,
                "affected_roles": ["left_knee"] if selected else [],
                "joint_status": "selected" if selected else "not_applicable",
                "note": "",
                **({"roles_origin": "reviewed", "roles_revision": 0} if selected else {}),
            })
        if open_error and index == 0:
            intervals.append({
                "interval_id": f"err_open{fingerprint[-8:]}",
                "start": _anchor(fingerprint, start),
                "end": _anchor(fingerprint, start),
                "error_class": "",
                "affected_roles": [],
                "joint_status": "unreviewed",
                "note": "",
            })
        samples.append({
            "sample_id": f"mov_{fingerprint[-12:]}{index:05d}",
            "start": _anchor(fingerprint, start),
            "end": _anchor(fingerprint, end),
            "exercise": exercises[int(rng.integers(0, len(exercises)))],
            "errors": intervals,
            "reviewed_at": FIXED_TIME,
            "note": "",
            "excluded": False,
            "derived_correctness": "incorrect" if intervals else "correct",
        })
    return samples


def write_run(
    take_dir: Path,
    take: Take,
    run_id: str,
    *,
    frames: int,
    skeleton: str,
    rng: np.random.Generator,
    samples: int,
    exercises: list[str],
    errors: list[str],
    athlete: bool,
    open_error: bool,
) -> Path:
    """One published, checksummed, labelled processing version."""
    spec = spec_for_zed_body_format(skeleton)
    run_dir = take_dir / "derived" / "processing" / run_id
    Path(long_path(run_dir / "arrays")).mkdir(parents=True)
    fingerprint = "sha256:" + hashlib.sha256(run_id.encode()).hexdigest()

    positions = np.arange(frames, dtype=np.int64)
    stamps = positions * (1_000_000_000 // FPS)
    joints = (rng.standard_normal((frames, spec.num_joints, 3)) * 0.05).astype(np.float32)
    joints += np.linspace(0, 1, spec.num_joints, dtype=np.float32)[None, :, None]
    joints[::7, 0] = np.nan  # gaps stay gaps
    confidences = np.full((frames, spec.num_joints), 0.9, dtype=np.float32)
    present = np.ones(frames, dtype=bool)
    arrays = {
        "joints": joints, "confidences": confidences, "source_positions": positions,
        "camera_timestamps_ns": stamps, "subject_present": present,
    }
    index = {}
    for key, value in arrays.items():
        with open(long_path(run_dir / "arrays" / f"{key}.npy"), "wb") as stream:
            np.save(stream, value, allow_pickle=False)
        index[key] = {"file": f"arrays/{key}.npy", "dtype": str(value.dtype),
                      "shape": list(value.shape), "bytes": int(value.nbytes)}
    _write_json(run_dir / "arrays" / "index.json", {
        "schema_version": "1.0.0", "layout": "one uncompressed .npy per array; memory-mappable",
        "arrays": index})

    with open(long_path(run_dir / "source_map.jsonl"), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"record": "header", "schema_version": PROCESSING_SCHEMA_VERSION,
                                 "source_fingerprint": fingerprint}) + "\n")
        for p in range(frames):
            stream.write(json.dumps({"record": "frame", "p": p, "source_position": p,
                                     "cam_ns": int(stamps[p]), "capture_frame_index": p,
                                     "capture_timestamp_ns": int(stamps[p]),
                                     "proxy_position": None}) + "\n")
    _write_json(run_dir / "skeleton_spec.json", spec.to_dict())
    job = {
        "schema_version": PROCESSING_SCHEMA_VERSION, "app_version": APP_VERSION,
        "run_id": run_id, "take_id": take.take_id, "take_dir": str(take_dir),
        "created_at": FIXED_TIME, "state": "complete", "restart_of": None,
        "parameters": {"body_format": skeleton, "store_depth": False, "store_proxy": False},
        "source": {"files": {}, "fingerprint": fingerprint, "origin": "synthetic",
                   "capture_provenance": None},
        "frames_processed": frames, "source_frames_declared": frames,
        "skeleton_format": spec.name, "issues": [], "blocking_issues": [],
        "published": True, "subject_status": "associated",
        "coverage": {"capture_frames": frames, "matched_frames": frames, "unmatched_frames": 0,
                     "source_frames": frames, "declared_source_frames": frames, "matched_ratio": 1.0},
        "subject_coverage": {"frames": frames, "tracked_frames": frames, "locked_frames": frames,
                             "ambiguous_frames": 0, "lost_frames": 0, "recoveries": 0,
                             "reassociations": 0, "multi_person_frames": 0, "tracked_ratio": 1.0},
        "arrays": {"schema_version": "1.0.0", "arrays": index},
        "scale_test": "scripts/measure/scale_dataset.py",
    }
    _write_json(run_dir / "job.json", job)
    files = {}
    root = Path(_extended(run_dir))
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {
                "present": True, "size_bytes": path.stat().st_size, "checksum": _sha256(path)}
    _write_json(run_dir / "checksums.json", {"algorithm": "sha256", "files": files})

    annotations = take_dir / "annotations" / "processing"
    Path(long_path(annotations)).mkdir(parents=True, exist_ok=True)
    if samples:
        _write_json(annotations / f"{run_id}.json", {
            "schema_version": "1.2.0", "contract": "canonical_source_boundaries_inclusive",
            "processing_run": run_id, "source_fingerprint": fingerprint, "revision": 2,
            "annotator": "scale-test", "updated_at": FIXED_TIME,
            "samples": _segments(rng, samples, frames, fingerprint, exercises, errors,
                                 open_error=open_error),
        })
    _write_json(annotations / f"{run_id}.subject.json", {
        "schema_version": "1.0.0", "processing_run": run_id, "source_fingerprint": fingerprint,
        "athlete_tracker_id": 1 if athlete else None, "chosen_at": FIXED_TIME if athlete else "",
        "annotator": "scale-test", "updated_at": FIXED_TIME, "revision": 2,
        "intervals": [], "decisions": [], "policy": "scale test",
    })
    return run_dir


def generate(
    out: Path,
    *,
    runs: int,
    segments: int,
    classes: int,
    frames: int = 40,
    participants: int = 100,
    seed: int = 23,
    awaiting: int = 0,
    skeleton: str = "BODY_18",
    name: Optional[str] = None,
) -> dict[str, Any]:
    out = Path(out)
    _refuse_real_location(out)
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    dataset_root = out / "datasets"
    workspace = ProjectWorkspace.create(
        dataset_root, name or f"Ölçek projesi {runs} kayıt · {classes} sınıf"
    )
    schema = make_schema(classes)
    workspace.save_label_schema(schema)
    exercises = list(schema.exercise_codes())
    errors = list(schema.error_type_codes())

    sessions = []
    for _ in range(max(1, min(participants, runs + awaiting))):
        participant = workspace.create_participant()
        sessions.append(workspace.create_session(
            participant.participant_id, operator="scale-test", consent=ConsentStatus.GRANTED))

    per_run = [segments // runs + (1 if i < segments % runs else 0) for i in range(runs)] if runs else []
    run_dirs: list[str] = []
    refused = {"no_athlete": 0, "open_error": 0}
    for number in range(runs + awaiting):
        session = sessions[number % len(sessions)]
        take_id = f"take_20260923T{number // 3600 % 24:02d}{number // 60 % 60:02d}{number % 60:02d}_{number:05x}"
        take = Take(
            take_id=take_id, session_id=session.session_id,
            participant_id=session.participant_id, project_id=workspace.project.project_id,
            index_in_session=number // len(sessions) + 1, started_at=FIXED_TIME,
            ended_at=FIXED_TIME, state=TakeState.FINALIZED, origin=DataOrigin.SYNTHETIC,
            processing_status="awaiting_processing", skeleton_format="",
        )
        take.metrics.frames_written = frames
        take.metrics.duration_s = frames / FPS
        take_dir = workspace.take_dir(session.participant_id, session.session_id, take_id)
        Path(long_path(take_dir / "raw")).mkdir(parents=True)
        _write_json(take_dir / "take.json", take.to_dict())
        if number >= runs:
            continue  # recorded, waiting for processing
        athlete = number % 100 != 37
        open_error = number % 100 == 71 and per_run[number] > 0
        refused["no_athlete"] += int(not athlete)
        refused["open_error"] += int(open_error)
        run_dir = write_run(
            take_dir, take, f"run_{number:016x}", frames=frames, skeleton=skeleton, rng=rng,
            samples=per_run[number], exercises=exercises, errors=errors,
            athlete=athlete, open_error=open_error,
        )
        run_dirs.append(str(run_dir))
    size = 0
    files = 0
    for path in Path(_extended(workspace.root)).rglob("*"):
        if path.is_file():
            files += 1
            size += path.stat().st_size
    return {
        "project_root": str(workspace.root),
        "dataset_root": str(dataset_root),
        "runs": runs, "awaiting": awaiting, "segments": segments, "classes": classes,
        "frames": frames, "participants": len(sessions), "skeleton": skeleton, "seed": seed,
        "deliberately_refused": refused,
        "files": files, "bytes": size,
        "seconds": round(time.perf_counter() - started, 2),
        "run_dirs": run_dirs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--runs", type=int, required=True)
    parser.add_argument("--segments", type=int, required=True)
    parser.add_argument("--classes", type=int, default=100)
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--participants", type=int, default=100)
    parser.add_argument("--awaiting", type=int, default=0)
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--skeleton", default="BODY_18")
    args = parser.parse_args()
    result = generate(
        args.out, runs=args.runs, segments=args.segments, classes=args.classes,
        frames=args.frames, participants=args.participants, seed=args.seed,
        awaiting=args.awaiting, skeleton=args.skeleton,
    )
    summary = {k: v for k, v in result.items() if k != "run_dirs"}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
