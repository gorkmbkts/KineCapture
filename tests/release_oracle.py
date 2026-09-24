"""An independent reader for the canonical dataset package.

Written for the 23 September 2026 release gate. It re-derives, from the
project's own files on disk, what a package *should* contain and compares that
with what the package *does* contain.

It deliberately imports nothing from ``kinecapture``. A mistake shared by the
exporter and its checker passes silently, so the checker may not share code
with the thing it checks - only the written contract. Everything here is plain
``json``, ``hashlib`` and ``numpy``: the same tools a person training a model
on the package would have.

The contract it encodes (canonical release 1.2.0):

* a version is refused - with a reason in the manifest - when it is not a
  finished, published run, when its derived files fail their own checksums,
  when nobody was tracked, when no athlete was chosen or a question about the
  athlete is open, when its labels do not validate against it, when it has a
  repetition with an unclassified error, or when nothing in it is ready;
* a repetition is ready when it is not excluded, carries a known movement
  class, has only classified errors and has been reviewed;
* boundaries are inclusive at both ends; error intervals are relative to their
  repetition; arrays are the version's own frames, sliced, never recomputed,
  and a missing measurement stays NaN;
* every sample names its participant, session, project, data origin and
  skeleton, and every file in the package is covered by ``checksums.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np

#: Arrays a sample carries when the version has them.
SAMPLE_ARRAYS = (
    "joints",
    "confidences",
    "joint_positions_2d",
    "camera_timestamps_ns",
    "source_positions",
    "subject_present",
)

#: How a joint status is written into ``error_interval_joint_status.npy``.
JOINT_STATUS_CODES = {"selected": 1, "not_applicable": 0, "indeterminate": -1, "unreviewed": -2}

#: Top-level manifest fields that are *expected* to differ between two builds
#: of the same input.
VOLATILE_MANIFEST_FIELDS = ("created_at",)


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _long(path: Path) -> Path:
    """Always the extended-length form on Windows.

    Not only for long paths: a short folder walked with ``rglob`` silently
    skips whatever lies past MAX_PATH below it, which is exactly the mistake
    this reader exists to catch in others.
    """
    text = str(Path(path).absolute())
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        return Path("\\\\?\\" + text)
    return Path(text)


# ------------------------------------------------------------------ inputs
@dataclass
class RunOnDisk:
    """One processing version, read the way a consumer would read it."""

    directory: Path
    job: dict
    take_dir: Path
    take: dict
    positions: list[int]
    stamps: list[int]
    arrays: dict[str, np.ndarray]
    annotations: Optional[dict]
    subject: Optional[dict]
    skeleton: Optional[dict]
    checksum_failures: list[str] = field(default_factory=list)

    @property
    def run_id(self) -> str:
        return str(self.job["run_id"])

    @property
    def fingerprint(self) -> str:
        return str(self.job["source"]["fingerprint"])

    def resolve(self, anchor: dict) -> int:
        """Exact anchor lookup; raises ``KeyError`` for anything inexact."""
        if str(anchor["source_fingerprint"]) != self.fingerprint:
            raise KeyError("another source")
        key = (int(anchor["source_position"]), int(anchor["camera_timestamp_ns"]))
        if not hasattr(self, "_where"):
            where: dict[tuple[int, int], list[int]] = {}
            for index, pair in enumerate(zip(self.positions, self.stamps)):
                where.setdefault(pair, []).append(index)
            self._where = where
        matches = self._where.get(key, [])
        if len(matches) != 1:
            raise KeyError(f"unresolved anchor {key}")
        return matches[0]


def read_run(directory: Path) -> RunOnDisk:
    directory = Path(directory)
    job = _load(_long(directory / "job.json"))
    # The take this run physically sits in. The run records where it was
    # produced, but a project that has been moved or copied lives here now.
    take_dir = directory.parents[2]
    if not (_long(take_dir / "take.json")).is_file():
        take_dir = Path(job["take_dir"])
    take = _load(_long(take_dir / "take.json"))

    positions: list[int] = []
    stamps: list[int] = []
    with open(_long(directory / "source_map.jsonl"), encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("record") != "frame":
                continue
            positions.append(int(row["source_position"]))
            stamps.append(int(row["cam_ns"]))

    arrays: dict[str, np.ndarray] = {}
    index_path = _long(directory / "arrays" / "index.json")
    if index_path.is_file():
        for key, entry in _load(index_path)["arrays"].items():
            arrays[key] = np.load(_long(directory / entry["file"]), allow_pickle=False)

    failures: list[str] = []
    checksums_path = _long(directory / "checksums.json")
    if checksums_path.is_file():
        for name, entry in _load(checksums_path)["files"].items():
            target = _long(directory / name)
            if not entry.get("present", True):
                continue
            if not target.is_file():
                failures.append(f"{name}: missing")
                continue
            algorithm, _, expected = str(entry["checksum"]).partition(":")
            if algorithm != "sha256" or _sha256(target) != expected:
                failures.append(f"{name}: checksum")

    def sidecar(suffix: str) -> Optional[dict]:
        path = _long(take_dir / "annotations" / "processing" / f"{job['run_id']}{suffix}")
        return _load(path) if path.is_file() else None

    skeleton_path = _long(directory / "skeleton_spec.json")
    return RunOnDisk(
        directory=directory,
        job=job,
        take_dir=take_dir,
        take=take,
        positions=positions,
        stamps=stamps,
        arrays=arrays,
        annotations=sidecar(".json"),
        subject=sidecar(".subject.json"),
        skeleton=_load(skeleton_path) if skeleton_path.is_file() else None,
        checksum_failures=failures,
    )


# ----------------------------------------------------------------- the rules
def _sample_reason(sample: dict, exercises: Sequence[str]) -> str:
    if sample.get("excluded"):
        return "excluded"
    exercise = str(sample.get("exercise") or "")
    if not exercise or exercise not in exercises:
        return "no_exercise"
    if any(not str(e.get("error_class") or "") for e in sample.get("errors") or ()):
        return "unclassified_error"
    if not str(sample.get("reviewed_at") or ""):
        return "unreviewed"
    return "ready"


def _annotation_problems(run: RunOnDisk, exercises, errors) -> list[str]:
    problems: list[str] = []
    document = run.annotations or {}
    if document.get("contract") not in (None, "", "canonical_source_boundaries_inclusive"):
        problems.append("contract")
    samples = document.get("samples") or []
    ids = [str(s.get("sample_id")) for s in samples]
    if len(ids) != len(set(ids)):
        problems.append("duplicate_sample_id")
    for sample in samples:
        try:
            start, end = run.resolve(sample["start"]), run.resolve(sample["end"])
        except KeyError:
            problems.append("sample_anchor_unresolved")
            continue
        if start > end:
            problems.append("sample_reversed")
        exercise = str(sample.get("exercise") or "")
        if exercise and exercise not in exercises:
            problems.append("unknown_exercise")
        interval_ids = [str(e.get("interval_id")) for e in sample.get("errors") or ()]
        if len(interval_ids) != len(set(interval_ids)):
            problems.append("duplicate_interval_id")
        for error in sample.get("errors") or ():
            try:
                first, last = run.resolve(error["start"]), run.resolve(error["end"])
            except KeyError:
                problems.append("interval_anchor_unresolved")
                continue
            if not (start <= first <= last <= end):
                problems.append("interval_outside_sample")
            code = str(error.get("error_class") or "")
            if code and code not in errors:
                problems.append("unknown_error_class")
            roles = list(error.get("affected_roles") or ())
            status = str(error.get("joint_status") or "unreviewed")
            if (status == "selected") != bool(roles):
                problems.append("roles_status_mismatch")
    return problems


def expected_refusals(run: RunOnDisk, exercises, errors) -> list[str]:
    """The refusal codes the contract demands for one version, in order."""
    job = run.job
    if job.get("state") not in ("complete", "partial") or job.get("blocking_issues"):
        return ["run_not_complete"]
    if run.checksum_failures:
        return ["derived_checksum_failed"]
    refusals: list[str] = []
    if job.get("subject_status") == "needs_subject_selection":
        refusals.append("no_subject_data")
    subject = run.subject or {}
    if subject.get("athlete_tracker_id") is None:
        refusals.append("athlete_not_chosen")
    answered = {
        str(d["interval_id"])
        for d in subject.get("decisions") or ()
        if str(d.get("verdict", "unanswered")) != "unanswered" and d.get("decided_at")
    }
    if any(str(i["interval_id"]) not in answered for i in subject.get("intervals") or ()):
        refusals.append("unanswered_subject_questions")
    if _annotation_problems(run, exercises, errors):
        refusals.append("annotation_invalid")
    reasons = [
        _sample_reason(s, exercises) for s in (run.annotations or {}).get("samples") or ()
    ]
    if "unclassified_error" in reasons:
        refusals.append("open_errors")
    if "ready" not in reasons:
        refusals.append("no_ready_samples")
    return list(dict.fromkeys(refusals))


# ------------------------------------------------------------ the package
@dataclass
class Expectation:
    """What a package built from these runs must contain."""

    accepted: list[str]
    refused: dict[str, list[str]]
    skipped: dict[str, dict[str, str]]
    entries: list[dict]
    arrays: dict[str, dict[str, np.ndarray]]
    exercise_classes: list[str]
    error_classes: list[str]
    skeletons: dict[str, dict]


def expect(
    run_dirs: Iterable[Path],
    schema: dict,
    *,
    store_confidences: bool = True,
    store_dense: bool = True,
    include_excluded: bool = False,
) -> Expectation:
    """Everything the contract says a package of ``run_dirs`` must hold."""
    del include_excluded  # excluded repetitions are never written
    exercises = sorted(str(o["code"]) for o in schema.get("exercises") or ())
    errors = sorted(str(o["code"]) for o in schema.get("error_types") or ())
    exercise_index = {code: i for i, code in enumerate(exercises)}
    error_index = {code: i for i, code in enumerate(errors)}

    accepted: list[str] = []
    refused: dict[str, list[str]] = {}
    skipped: dict[str, dict[str, str]] = {}
    entries: list[dict] = []
    arrays: dict[str, dict[str, np.ndarray]] = {}
    skeletons: dict[str, dict] = {}

    for directory in run_dirs:
        run = read_run(Path(directory))
        refusals = expected_refusals(run, exercises, errors)
        samples = (run.annotations or {}).get("samples") or []
        skipped[run.run_id] = {
            str(s["sample_id"]): reason
            for s in samples
            if (reason := _sample_reason(s, exercises)) != "ready"
        }
        if refusals:
            refused[run.run_id] = refusals
            continue
        accepted.append(run.run_id)
        if run.skeleton is not None:
            skeletons[str(run.job.get("skeleton_format"))] = run.skeleton
        for sample in samples:
            if _sample_reason(sample, exercises) != "ready":
                continue
            start, end = run.resolve(sample["start"]), run.resolve(sample["end"])
            frames = end - start + 1
            intervals = []
            for error in sample.get("errors") or ():
                first, last = run.resolve(error["start"]), run.resolve(error["end"])
                origin = str(error.get("roles_origin") or "unknown")
                intervals.append({
                    "interval_id": str(error["interval_id"]),
                    "error_class": str(error["error_class"]),
                    "class_index": error_index[str(error["error_class"])],
                    "relative_start": first - start,
                    "relative_end": last - start,
                    "joint_status": str(error.get("joint_status") or "unreviewed"),
                    "affected_roles": list(error.get("affected_roles") or ()),
                    "roles_origin": origin,
                    "roles_revision": int(error.get("roles_revision") or 0),
                    "roles_reviewed": origin == "reviewed",
                    "note": str(error.get("note") or ""),
                })
            payload: dict[str, np.ndarray] = {}
            missing: list[str] = []
            for key in SAMPLE_ARRAYS:
                if key == "confidences" and not store_confidences:
                    continue
                if key not in run.arrays:
                    missing.append(key)
                    continue
                payload[key] = run.arrays[key][start : end + 1]
            payload["error_intervals"] = np.asarray(
                [[i["class_index"], i["relative_start"], i["relative_end"]] for i in intervals],
                dtype=np.int32,
            ).reshape(-1, 3)
            payload["error_interval_joint_status"] = np.asarray(
                [JOINT_STATUS_CODES.get(i["joint_status"], -2) for i in intervals],
                dtype=np.int8,
            )
            if store_dense:
                dense = np.zeros((frames, len(errors)), dtype=np.int8)
                for i in intervals:
                    dense[i["relative_start"] : i["relative_end"] + 1, i["class_index"]] = 1
                payload["error_per_frame"] = dense
            sample_id = str(sample["sample_id"])
            arrays[sample_id] = payload
            subject = run.subject or {}
            entries.append({
                "sample_id": sample_id,
                "run_id": run.run_id,
                "take_id": str(run.job.get("take_id", "")),
                "participant_id": str(run.take["participant_id"]),
                "session_id": str(run.take["session_id"]),
                "project_id": str(run.take["project_id"]),
                "origin": str(run.job["source"].get("origin", "")),
                "skeleton_format": str(run.job.get("skeleton_format") or ""),
                "source_fingerprint": run.fingerprint,
                "processing_state": str(run.job.get("state", "")),
                "processing_issues": list(run.job.get("issues") or ()),
                "processing_coverage": dict(run.job.get("coverage") or {}),
                "annotation_revision": int((run.annotations or {}).get("revision", 1) or 1),
                "subject_revision": int(subject.get("revision", 1)),
                "athlete_tracker_id": subject.get("athlete_tracker_id"),
                "exercise": str(sample["exercise"]),
                "exercise_index": exercise_index[str(sample["exercise"])],
                "correctness": "incorrect" if intervals else "correct",
                "frames": frames,
                "version_positions": [start, end],
                "source_positions": [
                    int(sample["start"]["source_position"]),
                    int(sample["end"]["source_position"]),
                ],
                "camera_timestamps_ns": [
                    int(sample["start"]["camera_timestamp_ns"]),
                    int(sample["end"]["camera_timestamp_ns"]),
                ],
                "reviewed_at": str(sample.get("reviewed_at") or ""),
                "note": str(sample.get("note") or ""),
                "error_intervals": intervals,
                "missing_arrays": missing,
                "directory": f"samples/{sample_id}",
            })
    return Expectation(
        accepted=accepted,
        refused=refused,
        skipped=skipped,
        entries=entries,
        arrays=arrays,
        exercise_classes=exercises,
        error_classes=errors,
        skeletons=skeletons,
    )


def _same_array(actual: np.ndarray, wanted: np.ndarray) -> bool:
    if actual.dtype != wanted.dtype or actual.shape != wanted.shape:
        return False
    if np.issubdtype(wanted.dtype, np.floating):
        # NaN where the version had NaN, and nowhere else. A filled gap is a
        # measurement nobody made.
        return bool(
            np.array_equal(np.isnan(actual), np.isnan(wanted))
            and np.array_equal(actual, wanted, equal_nan=True)
        )
    return bool(np.array_equal(actual, wanted))


def verify(
    release_dir: Path,
    run_dirs: Iterable[Path],
    schema: dict,
    *,
    project: Optional[dict] = None,
    store_confidences: bool = True,
    store_dense: bool = True,
    check_arrays: bool = True,
) -> list[str]:
    """Every way the package at ``release_dir`` departs from the contract.

    An empty list means the package is exactly what its inputs say it must be.
    """
    problems: list[str] = []
    release_dir = Path(release_dir)
    wanted = expect(
        run_dirs, schema, store_confidences=store_confidences, store_dense=store_dense
    )
    manifest = _load(_long(release_dir / "manifest.json"))
    samples = _load(_long(release_dir / "samples.json"))["samples"]

    # -- versions ---------------------------------------------------------
    accepted = [v["run_id"] for v in manifest["versions"]]
    if accepted != wanted.accepted:
        problems.append(f"accepted versions {accepted} != {wanted.accepted}")
    for version in manifest["refused_versions"]:
        want = wanted.refused.get(version["run_id"])
        if want is None:
            problems.append(f"{version['run_id']} refused but should be accepted")
        elif version["refusals"] != want:
            problems.append(
                f"{version['run_id']} refusals {version['refusals']} != {want}"
            )
        if len(version.get("refusal_text") or ()) != len(version["refusals"]):
            problems.append(f"{version['run_id']} refusal without its text")
    listed_refused = {v["run_id"] for v in manifest["refused_versions"]}
    for run_id in wanted.refused:
        if run_id not in listed_refused:
            problems.append(f"{run_id} should be refused and listed")
    for version in manifest["versions"] + manifest["refused_versions"]:
        skipped = {s["sample_id"]: s["reason"] for s in version["samples_skipped"]}
        if skipped != wanted.skipped.get(version["run_id"], {}):
            problems.append(
                f"{version['run_id']} skipped {skipped} != "
                f"{wanted.skipped.get(version['run_id'])}"
            )

    # -- counts and class maps -----------------------------------------------
    counts = manifest["counts"]
    if counts["samples"] != len(wanted.entries) or len(samples) != len(wanted.entries):
        problems.append(
            f"sample count {counts['samples']}/{len(samples)} != {len(wanted.entries)}"
        )
    if counts["versions_accepted"] != len(wanted.accepted):
        problems.append("versions_accepted count")
    if counts["versions_refused"] != len(wanted.refused):
        problems.append("versions_refused count")
    participants = {e["participant_id"] for e in wanted.entries}
    if counts.get("participants") != len(participants):
        problems.append(f"participants count {counts.get('participants')} != {len(participants)}")
    synthetic = sum(1 for e in wanted.entries if e["origin"] == "synthetic")
    if counts.get("samples_synthetic") != synthetic:
        problems.append(f"samples_synthetic {counts.get('samples_synthetic')} != {synthetic}")
    exercise_map = manifest["label_mapping"]["exercise"]
    if exercise_map["classes"] != wanted.exercise_classes:
        problems.append("exercise class list")
    if exercise_map["code_to_index"] != {c: i for i, c in enumerate(wanted.exercise_classes)}:
        problems.append("exercise class -> index")
    error_map = manifest["error_mapping"]
    if error_map["classes"] != wanted.error_classes:
        problems.append("error class list")
    if error_map["code_to_index"] != {c: i for i, c in enumerate(wanted.error_classes)}:
        problems.append("error class -> index")
    if manifest["label_mapping"]["error_types"]["code_to_index"] != error_map["code_to_index"]:
        problems.append("the two error maps disagree")

    # -- provenance -------------------------------------------------------
    for key in ("schema_version", "annotation_schema_version", "subject_schema_version", "app_version"):
        if not manifest.get(key):
            problems.append(f"manifest has no {key}")
    if manifest.get("schema_version") != "1.2.0":
        problems.append(f"release schema {manifest.get('schema_version')} != 1.2.0")
    if project is not None:
        listed = manifest.get("projects") or {}
        if listed.get(project["project_id"]) != project["name"]:
            problems.append(f"project {project['project_id']} not named in the manifest")
    for name, spec in wanted.skeletons.items():
        if (manifest.get("skeletons") or {}).get(name) != spec:
            problems.append(f"skeleton {name} missing or different in the manifest")

    # -- samples ------------------------------------------------------------
    by_id = {e["sample_id"]: e for e in samples}
    if len(by_id) != len(samples):
        problems.append("duplicate sample ids in samples.json")
    for want in wanted.entries:
        got = by_id.get(want["sample_id"])
        if got is None:
            problems.append(f"{want['sample_id']} missing from the package")
            continue
        for key, value in want.items():
            if got.get(key) != value:
                problems.append(
                    f"{want['sample_id']}.{key}: {got.get(key)!r} != {value!r}"
                )
        extra = set(got) - set(want)
        if extra:
            problems.append(f"{want['sample_id']} has undocumented fields {sorted(extra)}")
        if not check_arrays:
            continue
        folder = _long(release_dir / got["directory"])
        present = {p.stem for p in folder.glob("*.npy")}
        if present != set(wanted.arrays[want["sample_id"]]):
            problems.append(
                f"{want['sample_id']} arrays {sorted(present)} != "
                f"{sorted(wanted.arrays[want['sample_id']])}"
            )
        for key, array in wanted.arrays[want["sample_id"]].items():
            path = folder / f"{key}.npy"
            if not path.is_file():
                continue
            actual = np.load(path, allow_pickle=False)
            if not _same_array(actual, array):
                problems.append(f"{want['sample_id']}/{key}.npy differs from the version")
    unexpected = set(by_id) - {e["sample_id"] for e in wanted.entries}
    if unexpected:
        problems.append(f"samples that should not be there: {sorted(unexpected)}")

    # -- checksums ------------------------------------------------------------
    problems.extend(verify_checksums(release_dir))
    return problems


def verify_checksums(release_dir: Path) -> list[str]:
    """Every file listed, every listed file present and unchanged."""
    release_dir = Path(release_dir)
    path = _long(release_dir / "checksums.json")
    if not path.is_file():
        return ["package has no checksums.json"]
    listed = _load(path)
    if listed.get("algorithm") != "sha256":
        return [f"checksum algorithm {listed.get('algorithm')!r}"]
    problems: list[str] = []
    root = _long(release_dir)
    on_disk = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.name != "checksums.json"
    }
    files = listed.get("files") or {}
    if set(files) != on_disk:
        problems.append(
            f"checksums cover {len(files)} files, package has {len(on_disk)}: "
            f"{sorted(set(files) ^ on_disk)[:5]}"
        )
    for name, entry in files.items():
        target = root / name
        if not target.is_file() or not entry.get("present", False):
            continue
        algorithm, _, digest = str(entry.get("checksum", "")).partition(":")
        if (
            algorithm != "sha256"
            or target.stat().st_size != entry["size_bytes"]
            or _sha256(target) != digest
        ):
            problems.append(f"{name} does not match its checksum")
    return problems


def package_bytes(release_dir: Path) -> dict[str, bytes]:
    """Every file of a package, for a byte-level comparison of two builds.

    The two fields that are *meant* to differ - the build time, and therefore
    the manifest's own checksum - are normalised out; everything else must be
    identical to the byte.
    """
    root = _long(release_dir)
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        if name == "manifest.json":
            manifest = json.loads(data.decode("utf-8"))
            for key in VOLATILE_MANIFEST_FIELDS:
                manifest.pop(key, None)
            data = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
        elif name == "checksums.json":
            listed = json.loads(data.decode("utf-8"))
            listed.get("files", {}).pop("manifest.json", None)
            data = json.dumps(listed, sort_keys=True, ensure_ascii=False).encode("utf-8")
        out[name] = data
    return out


__all__ = [
    "Expectation",
    "RunOnDisk",
    "expect",
    "expected_refusals",
    "package_bytes",
    "read_run",
    "verify",
    "verify_checksums",
]
