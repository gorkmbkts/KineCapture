"""Turning labelled versions into a dataset package.

This is the last place a mistake can still be caught, and the first place one
becomes permanent: after a release is written, a model is trained on it and
nothing in the pipeline looks at the labels again.

So the rule here is that **nothing is exported quietly**. Every version is
either in the package or in the manifest's refusal list with a reason a person
can act on. A version is never dropped for being inconvenient, never included
because it was "probably fine", and never repaired on the way out.

Four gates, in the order they can fail:

1. The processing run must be complete and promoted, and its derived files
   must still match their checksums.
2. Somebody must have said who the recording is about, and every stretch the
   tracker was unsure about must have an answer.
3. The annotation document must validate against this version - every anchor
   resolving to a real frame in it, every interval inside its movement.
4. Each movement must be ready: classified, reviewed, and with no
   half-finished error interval.

Arrays are **sliced**, never recomputed. The version computed its features
over the whole recording; cutting a window out of that is not the same as
recomputing the window in isolation, and the manifest says which one happened
so nobody has to guess.

No Qt, no SDK.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np

from kinecapture import APP_VERSION
from kinecapture.core.fingerprint import hash_payload
from kinecapture.core.jsonio import write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.domain.labels import LabelSchema
from kinecapture.processing.annotations import (
    CANONICAL_ANNOTATION_SCHEMA_VERSION,
    Correctness,
    JointStatus,
    MovementSample,
    Readiness,
    load_annotations,
    validate_document,
)
from kinecapture.processing.review import ReviewDataset
from kinecapture.processing.subject_review import (
    SUBJECT_REVIEW_SCHEMA_VERSION,
    load_subject_review,
)

logger = logging.getLogger(__name__)

CANONICAL_RELEASE_SCHEMA_VERSION = "1.0.0"

#: Arrays copied per sample when the version has them. Anything absent stays
#: absent: a missing signal is reported in the manifest, never zero-filled.
SAMPLE_ARRAYS = (
    "joints",
    "confidences",
    "joint_positions_2d",
    "camera_timestamps_ns",
    "source_positions",
    "subject_present",
)

#: How a joint status is written into the per-interval target arrays.
JOINT_STATUS_CODES = {
    JointStatus.SELECTED.value: 1,
    JointStatus.NOT_APPLICABLE.value: 0,
    JointStatus.INDETERMINATE.value: -1,
    JointStatus.UNREVIEWED.value: -2,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Refusal(str, Enum):
    """Why a version did not make it into the package."""

    RUN_NOT_COMPLETE = "run_not_complete"
    DERIVED_CHECKSUM_FAILED = "derived_checksum_failed"
    NO_SUBJECT_DATA = "no_subject_data"
    ATHLETE_NOT_CHOSEN = "athlete_not_chosen"
    UNANSWERED_SUBJECT_QUESTIONS = "unanswered_subject_questions"
    ANNOTATION_INVALID = "annotation_invalid"
    NO_READY_SAMPLES = "no_ready_samples"
    OPEN_ERRORS = "open_errors"


REFUSAL_TEXT = {
    Refusal.RUN_NOT_COMPLETE: "İşleme sürümü tamamlanmamış.",
    Refusal.DERIVED_CHECKSUM_FAILED: "Türetilmiş dosyalar kendi checksum'ına uymuyor.",
    Refusal.NO_SUBJECT_DATA: "Bu sürümde hiç kişi seçilmemiş; eklem dizileri boş.",
    Refusal.ATHLETE_NOT_CHOSEN: "Sürümün sporcusu seçilmemiş.",
    Refusal.UNANSWERED_SUBJECT_QUESTIONS: "Yanıtlanmamış belirsiz aralık var.",
    Refusal.ANNOTATION_INVALID: "Etiket dosyası bu sürümle tutarlı değil.",
    Refusal.NO_READY_SAMPLES: "Dışa aktarılacak hazır hareket yok.",
    Refusal.OPEN_ERRORS: "Sınıfsız hata aralığı olan hareket var.",
}


@dataclass(frozen=True)
class CanonicalExportOptions:
    """What to put in the package."""

    #: Movements marked excluded by the annotator are never written.
    include_excluded: bool = False
    #: Per-frame error targets alongside the interval-space evidence. The
    #: interval form is lossless and always written; this is a convenience.
    store_dense_error_targets: bool = True
    #: Confidence arrays. Off makes smaller packages, at the cost of the one
    #: signal that says how much to trust a frame.
    store_confidences: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "include_excluded": self.include_excluded,
            "store_dense_error_targets": self.store_dense_error_targets,
            "store_confidences": self.store_confidences,
            "note": self.note,
        }


@dataclass
class VersionReport:
    """What happened to one version, whether or not it was exported."""

    run_id: str
    directory: str
    take_id: str = ""
    accepted: bool = False
    refusals: tuple[Refusal, ...] = ()
    detail: tuple[str, ...] = ()
    samples_written: int = 0
    samples_skipped: tuple[dict[str, Any], ...] = ()
    annotation_revision: int = 0
    subject_revision: int = 0
    source_fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "take_id": self.take_id,
            "directory": self.directory,
            "accepted": self.accepted,
            "refusals": [r.value for r in self.refusals],
            "refusal_text": [REFUSAL_TEXT[r] for r in self.refusals],
            "detail": list(self.detail),
            "samples_written": self.samples_written,
            "samples_skipped": list(self.samples_skipped),
            "annotation_revision": self.annotation_revision,
            "subject_revision": self.subject_revision,
            "source_fingerprint": self.source_fingerprint,
        }


@dataclass
class ExportReport:
    """The whole build, as the screen shows it and the manifest records it."""

    release_dir: Optional[Path] = None
    versions: list[VersionReport] = field(default_factory=list)
    samples: int = 0
    started_at: str = ""
    finished_at: str = ""

    @property
    def accepted(self) -> list[VersionReport]:
        return [v for v in self.versions if v.accepted]

    @property
    def refused(self) -> list[VersionReport]:
        return [v for v in self.versions if not v.accepted]

    @property
    def is_empty(self) -> bool:
        return self.samples == 0


# --------------------------------------------------------------------- gate
def inspect_version(
    directory: Path,
    schema: LabelSchema,
    *,
    verify: bool = True,
) -> tuple[VersionReport, Optional[dict[str, Any]]]:
    """Decide whether one version may be exported, and say why not.

    Returns the report and, when it passed, everything the writer needs so the
    version is opened and validated exactly once.
    """
    directory = Path(directory)
    report = VersionReport(run_id=directory.name, directory=str(directory))
    refusals: list[Refusal] = []
    detail: list[str] = []

    try:
        dataset = ReviewDataset(directory, verify=verify)
    except ValueError as exc:
        message = str(exc)
        refusals.append(
            Refusal.DERIVED_CHECKSUM_FAILED
            if "checksum" in message.lower()
            else Refusal.RUN_NOT_COMPLETE
        )
        detail.append(message)
        report.refusals = tuple(refusals)
        report.detail = tuple(detail)
        return report, None
    except (FileNotFoundError, OSError) as exc:
        report.refusals = (Refusal.RUN_NOT_COMPLETE,)
        report.detail = (str(exc),)
        return report, None

    try:
        report.run_id = dataset.run_id
        report.take_id = str(dataset.job.get("take_id", ""))
        report.source_fingerprint = dataset.source_fingerprint

        if str(dataset.job.get("subject_status", "")) == "needs_subject_selection":
            # Every array in such a run is NaN. Nothing downstream can use it,
            # and no decision made later can fill it in.
            refusals.append(Refusal.NO_SUBJECT_DATA)

        subject = load_subject_review(
            dataset.take_dir, dataset.run_id, dataset.source_fingerprint
        )
        report.subject_revision = subject.revision
        if subject.athlete_tracker_id is None:
            refusals.append(Refusal.ATHLETE_NOT_CHOSEN)
        if subject.unanswered:
            refusals.append(Refusal.UNANSWERED_SUBJECT_QUESTIONS)
            detail.append(f"{len(subject.unanswered)} aralık yanıtsız")

        document = load_annotations(
            dataset.take_dir, dataset.run_id, dataset.source_fingerprint
        )
        report.annotation_revision = document.revision
        problems = validate_document(
            document,
            resolve=dataset.position_of_anchor,
            frames=dataset.frames,
            known_exercises=schema.exercise_codes(),
            known_error_classes=schema.error_type_codes(),
        )
        if problems:
            refusals.append(Refusal.ANNOTATION_INVALID)
            detail.extend(p["message"] for p in problems[:5])

        ready, skipped = _partition(document.samples, schema)
        report.samples_skipped = tuple(skipped)
        if any(s["reason"] == Readiness.UNCLASSIFIED_ERROR.value for s in skipped):
            refusals.append(Refusal.OPEN_ERRORS)
        if not ready:
            refusals.append(Refusal.NO_READY_SAMPLES)

        report.refusals = tuple(dict.fromkeys(refusals))
        report.detail = tuple(detail)
        report.accepted = not refusals
        if not report.accepted:
            dataset.close()
            return report, None
        return report, {
            "dataset": dataset,
            "document": document,
            "subject": subject,
            "ready": ready,
        }
    except Exception:
        dataset.close()
        raise


def _partition(
    samples: Sequence[MovementSample], schema: LabelSchema
) -> tuple[list[MovementSample], list[dict[str, Any]]]:
    """Split into what may be written and what may not, with the reason."""
    ready: list[MovementSample] = []
    skipped: list[dict[str, Any]] = []
    known = schema.exercise_codes()
    for sample in samples:
        if sample.excluded:
            skipped.append({"sample_id": sample.sample_id, "reason": "excluded"})
            continue
        readiness = sample.readiness(known)
        if readiness is Readiness.READY:
            ready.append(sample)
        else:
            skipped.append({"sample_id": sample.sample_id, "reason": readiness.value})
    return ready, skipped


# -------------------------------------------------------------------- build
def build_release(
    directories: Iterable[Path],
    releases_dir: Path,
    schema: LabelSchema,
    *,
    options: Optional[CanonicalExportOptions] = None,
    verify: bool = True,
    name: Optional[str] = None,
    operator: str = "",
) -> ExportReport:
    """Write one dataset package from the given processing versions.

    Built in a staging directory and moved into place at the end, so an
    interrupted export leaves no half-written release for someone to train on.
    """
    options = options or CanonicalExportOptions()
    releases_dir = Path(releases_dir)
    ensure_dir(releases_dir)
    report = ExportReport(started_at=_utc_now())

    release_name = name or _next_name(releases_dir)
    staging = releases_dir / f".{release_name}.partial"
    if path_exists(staging):
        shutil.rmtree(long_path(staging), ignore_errors=True)
    ensure_dir(staging)
    samples_dir = ensure_dir(staging / "samples")

    mapping = schema.label_mapping()
    exercise_index = mapping["exercise"]["code_to_index"]
    error_index = {
        code: position for position, code in enumerate(sorted(schema.error_type_codes()))
    }

    entries: list[dict[str, Any]] = []
    try:
        for directory in directories:
            version_report, opened = inspect_version(directory, schema, verify=verify)
            report.versions.append(version_report)
            if opened is None:
                continue
            dataset = opened["dataset"]
            try:
                written = _write_version(
                    dataset,
                    opened["ready"],
                    samples_dir,
                    entries,
                    exercise_index=exercise_index,
                    error_index=error_index,
                    options=options,
                    subject=opened["subject"],
                    document=opened["document"],
                )
                version_report.samples_written = written
                report.samples += written
            finally:
                dataset.close()

        manifest = _manifest(
            release_name,
            report,
            entries,
            mapping,
            error_index,
            options,
            operator,
        )
        write_json(staging / "manifest.json", manifest)
        write_json(staging / "samples.json", {"samples": entries})

        final = releases_dir / release_name
        if path_exists(final):
            raise FileExistsError(f"Bu isimde bir sürüm zaten var: {release_name}")
        import os

        os.rename(long_path(staging), long_path(final))
        report.release_dir = final
    except Exception:
        shutil.rmtree(long_path(staging), ignore_errors=True)
        raise
    report.finished_at = _utc_now()
    return report


def _write_version(
    dataset: ReviewDataset,
    ready: Sequence[MovementSample],
    samples_dir: Path,
    entries: list[dict[str, Any]],
    *,
    exercise_index: dict[str, int],
    error_index: dict[str, int],
    options: CanonicalExportOptions,
    subject: Any,
    document: Any,
) -> int:
    store = dataset.array_store
    available = set(store.keys)
    written = 0

    for sample in ready:
        start = dataset.position_of_anchor(sample.start)
        end = dataset.position_of_anchor(sample.end)
        if end < start:
            raise ValueError(f"Ters aralık dışa aktarıma ulaştı: {sample.sample_id}")
        # Inclusive boundaries, everywhere: the end frame belongs to the
        # movement, so the slice runs to end + 1.
        stop = end + 1
        frames = stop - start

        payload: dict[str, np.ndarray] = {}
        missing: list[str] = []
        for key in SAMPLE_ARRAYS:
            if key == "confidences" and not options.store_confidences:
                continue
            if key not in available:
                missing.append(key)
                continue
            payload[key] = np.ascontiguousarray(store.window(key, start, stop))

        intervals = _intervals_of(
            dataset, sample, start, end, error_index
        )
        payload["error_intervals"] = np.asarray(
            [[i["class_index"], i["relative_start"], i["relative_end"]] for i in intervals],
            dtype=np.int32,
        ).reshape(-1, 3)
        payload["error_interval_joint_status"] = np.asarray(
            [JOINT_STATUS_CODES.get(i["joint_status"], -2) for i in intervals],
            dtype=np.int8,
        )
        if options.store_dense_error_targets:
            payload["error_per_frame"] = _dense(intervals, frames, len(error_index))

        sample_dir = ensure_dir(samples_dir / sample.sample_id)
        for key, array in payload.items():
            with open(long_path(sample_dir / f"{key}.npy"), "wb") as stream:
                np.save(stream, array, allow_pickle=False)

        entries.append({
            "sample_id": sample.sample_id,
            "run_id": dataset.run_id,
            "take_id": str(dataset.job.get("take_id", "")),
            "source_fingerprint": dataset.source_fingerprint,
            "annotation_revision": document.revision,
            "subject_revision": subject.revision,
            "athlete_tracker_id": subject.athlete_tracker_id,
            "exercise": sample.exercise,
            "exercise_index": exercise_index.get(sample.exercise, -1),
            "correctness": sample.correctness.value,
            "frames": frames,
            "version_positions": [start, end],
            "source_positions": [
                int(sample.start.source_position),
                int(sample.end.source_position),
            ],
            "camera_timestamps_ns": [
                int(sample.start.camera_timestamp_ns),
                int(sample.end.camera_timestamp_ns),
            ],
            "reviewed_at": sample.reviewed_at,
            "note": sample.note,
            "error_intervals": intervals,
            "missing_arrays": missing,
            "directory": f"samples/{sample.sample_id}",
        })
        written += 1
    return written


def _intervals_of(
    dataset: ReviewDataset,
    sample: MovementSample,
    start: int,
    end: int,
    error_index: dict[str, int],
) -> list[dict[str, Any]]:
    """Error intervals as indices **relative to the sample**, inclusive.

    Relative, because a consumer holds the sample's arrays and nothing else;
    absolute version positions would be meaningless to them. The absolute
    anchors stay in the entry so the two can always be reconciled.
    """
    out: list[dict[str, Any]] = []
    for interval in sample.errors:
        first = dataset.position_of_anchor(interval.start)
        last = dataset.position_of_anchor(interval.end)
        if first < start or last > end:
            raise ValueError(
                f"Hata aralığı hareketin dışına taşıyor: {interval.interval_id}"
            )
        if interval.error_class not in error_index:
            raise ValueError(f"Bilinmeyen hata sınıfı: {interval.error_class}")
        out.append({
            "interval_id": interval.interval_id,
            "error_class": interval.error_class,
            "class_index": error_index[interval.error_class],
            "relative_start": first - start,
            "relative_end": last - start,
            "joint_status": interval.joint_status.value,
            "affected_roles": list(interval.affected_roles),
            "note": interval.note,
        })
    return out


def _dense(
    intervals: Sequence[dict[str, Any]], frames: int, classes: int
) -> np.ndarray:
    """``[T, C]`` multi-hot. Zero means "no error of that class here"."""
    dense = np.zeros((frames, max(0, classes)), dtype=np.int8)
    for interval in intervals:
        index = int(interval["class_index"])
        if 0 <= index < classes:
            first = max(0, int(interval["relative_start"]))
            last = min(frames - 1, int(interval["relative_end"]))
            if last >= first:
                dense[first : last + 1, index] = 1
    return dense


def _manifest(
    name: str,
    report: ExportReport,
    entries: Sequence[dict[str, Any]],
    mapping: dict[str, Any],
    error_index: dict[str, int],
    options: CanonicalExportOptions,
    operator: str,
) -> dict[str, Any]:
    accepted = [v.to_dict() for v in report.accepted]
    refused = [v.to_dict() for v in report.refused]
    return {
        "schema_version": CANONICAL_RELEASE_SCHEMA_VERSION,
        "annotation_schema_version": CANONICAL_ANNOTATION_SCHEMA_VERSION,
        "subject_schema_version": SUBJECT_REVIEW_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "release": name,
        "created_at": _utc_now(),
        "operator": operator,
        "options": options.to_dict(),
        "counts": {
            "versions_accepted": len(accepted),
            "versions_refused": len(refused),
            "samples": len(entries),
        },
        "label_mapping": mapping,
        "error_mapping": {
            "classes": sorted(error_index, key=error_index.get),
            "code_to_index": dict(error_index),
        },
        "versions": accepted,
        # Refusals are part of the package on purpose. "Why is this athlete
        # missing from the dataset" must be answerable from the release itself.
        "refused_versions": refused,
        "boundary_contract": (
            "Hareket ve hata aralıklarının iki ucu da dahildir; hata aralığı "
            "indeksleri örneğin kendi başlangıcına görelidir."
        ),
        "feature_provenance": (
            "Diziler sürümün tamamı üzerinde hesaplanıp örneğe göre "
            "dilimlenmiştir; örnek başına yeniden hesaplanmamıştır."
        ),
        "content_fingerprint": hash_payload(
            {
                "samples": [
                    {
                        "sample_id": e["sample_id"],
                        "run_id": e["run_id"],
                        "source_fingerprint": e["source_fingerprint"],
                        "exercise": e["exercise"],
                        "correctness": e["correctness"],
                        "source_positions": e["source_positions"],
                        "error_intervals": [
                            [i["error_class"], i["relative_start"], i["relative_end"]]
                            for i in e["error_intervals"]
                        ],
                    }
                    for e in entries
                ],
                "mapping": mapping,
            }
        ),
    }


def _next_name(releases_dir: Path) -> str:
    existing = {
        entry.name
        for entry in Path(long_path(releases_dir)).iterdir()
        if entry.is_dir() and entry.name.startswith("v")
    } if path_exists(releases_dir) else set()
    index = 1
    while f"v{index:04d}" in existing:
        index += 1
    return f"v{index:04d}"


__all__ = [
    "CANONICAL_RELEASE_SCHEMA_VERSION",
    "CanonicalExportOptions",
    "ExportReport",
    "JOINT_STATUS_CODES",
    "REFUSAL_TEXT",
    "Refusal",
    "SAMPLE_ARRAYS",
    "VersionReport",
    "build_release",
    "inspect_version",
]
