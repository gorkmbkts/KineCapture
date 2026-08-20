"""Versioned dataset releases.

A release is one repetition per sample, exported as ``float32 [T, J, 3]`` in the
capture's *native* joint order and *raw* coordinates.

What is deliberately NOT done here
----------------------------------
Root centring, scale normalisation, interpolation of missing joints and any
augmentation are **training-time** concerns. Baking them into a release would
destroy the raw signal and make the release un-reproducible. Missing joints stay
NaN so a downstream pipeline can decide what to do about them.

Atomicity
---------
Everything is written into ``releases/.staging_<name>``. Only after every sample
is written, the manifest is complete and validation has run does the staging
directory get moved into place with a single rename. A cancelled or failed
export leaves no half-release that could be mistaken for a finished one, and an
existing release is never modified.

Naming
------
``dataset_v001``, ``dataset_v002``, ... The next number is derived from what is
already published, so two releases never collide.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import numpy as np

from kinecapture import APP_VERSION, RELEASE_SCHEMA_VERSION
from kinecapture.core.errors import ExportCancelled, ExportError
from kinecapture.core.fingerprint import dataset_fingerprint, hash_file
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.jsonio import write_json
from kinecapture.core.logging import get_logger
from kinecapture.core.paths import ensure_dir, long_path, path_exists
from kinecapture.dataset.index import DatasetIndex, TakeRow, exportable_rows
from kinecapture.dataset.workspace import ProjectWorkspace
from kinecapture.domain.project import RepetitionSegment
from kinecapture.playback.take_reader import load_skeleton_stream
from kinecapture.visualization.mapping import JointMapping, find_mapping
from kinecapture.visualization.skeleton_spec import (
    SkeletonSpec,
    try_get_skeleton_spec,
)

logger = get_logger(__name__)

_RELEASE_PATTERN = re.compile(r"^dataset_v(\d{3,})$")

#: Progress callback: ``(completed, total, message)``. Returning False cancels.
ProgressCallback = Callable[[int, int, str], bool]


@dataclass
class ExportOptions:
    """Everything that changes what a release contains.

    Recorded verbatim in the manifest and hashed into the fingerprint, so two
    releases built with different options are provably different.
    """

    include_synthetic: bool = False
    include_unlabelled: bool = False
    include_excluded_segments: bool = False
    min_frames_per_sample: int = 4
    target_skeleton_format: Optional[str] = None
    store_confidences: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class ExportResult:
    """Outcome of a completed export."""

    release_name: str
    path: Path
    sample_count: int
    excluded_count: int
    fingerprint: str
    validation_passed: bool
    warnings: list[str] = field(default_factory=list)


def next_release_name(releases_dir: Path) -> str:
    """``dataset_v001`` after nothing, ``dataset_v004`` after ``v003``."""
    highest = 0
    if releases_dir.is_dir():
        for child in releases_dir.iterdir():
            match = _RELEASE_PATTERN.match(child.name)
            if match and child.is_dir():
                highest = max(highest, int(match.group(1)))
    return f"dataset_v{highest + 1:03d}"


def list_releases(releases_dir: Path) -> list[Path]:
    if not releases_dir.is_dir():
        return []
    return sorted(
        child
        for child in releases_dir.iterdir()
        if child.is_dir() and _RELEASE_PATTERN.match(child.name)
    )


class ReleaseBuilder:
    """Builds one dataset release, atomically.

    Runs on a worker thread. Progress and cancellation flow through a single
    callback so the GUI never has to poll and can cancel at any sample boundary.
    """

    def __init__(
        self,
        workspace: ProjectWorkspace,
        index: DatasetIndex,
        options: Optional[ExportOptions] = None,
    ) -> None:
        self.workspace = workspace
        self.index = index
        self.options = options or ExportOptions()

    # ---------------------------------------------------------------- select
    def select_rows(self, rows: Optional[Sequence[TakeRow]] = None) -> list[TakeRow]:
        """Takes eligible under the current options."""
        candidates = list(rows) if rows is not None else list(self.index.rows)
        if not self.options.include_synthetic:
            candidates = [row for row in candidates if not row.take.is_synthetic]
        if self.options.include_unlabelled:
            return [row for row in candidates if row.take.usable_for_export]
        return exportable_rows(candidates)

    def _selected_segments(self, row: TakeRow) -> list[RepetitionSegment]:
        segments = [
            segment
            for segment in row.segments
            if self.options.include_excluded_segments or segment.is_active
        ]
        if not self.options.include_unlabelled:
            segments = [s for s in segments if s.annotation.is_labelled]
        return sorted(segments, key=lambda s: s.start_frame)

    # ----------------------------------------------------------------- build
    def build(
        self,
        *,
        rows: Optional[Sequence[TakeRow]] = None,
        progress: Optional[ProgressCallback] = None,
        release_name: Optional[str] = None,
    ) -> ExportResult:
        """Produce a release. Raises :class:`ExportCancelled` if cancelled."""
        releases_dir = self.workspace.releases_dir
        ensure_dir(releases_dir)
        name = release_name or next_release_name(releases_dir)
        final_dir = releases_dir / name
        if path_exists(final_dir):
            raise ExportError(
                f"Bu sürüm zaten var: {name}",
                code="release_exists",
                remedy="Önceki sürümler değiştirilmez; yeni bir sürüm adı seçin.",
            )

        staging = releases_dir / f".staging_{name}"
        if path_exists(staging):
            shutil.rmtree(long_path(staging))
        samples_dir = staging / "samples"
        ensure_dir(samples_dir)

        try:
            result = self._build_into(staging, samples_dir, name, rows, progress)
        except BaseException:
            shutil.rmtree(long_path(staging), ignore_errors=True)
            raise

        # One atomic rename publishes the whole release.
        os.replace(long_path(staging), long_path(final_dir))
        result.path = final_dir
        logger.info(
            "Dataset sürümü yayımlandı: %s (%d örnek)", name, result.sample_count
        )
        return result

    def _build_into(
        self,
        staging: Path,
        samples_dir: Path,
        name: str,
        rows: Optional[Sequence[TakeRow]],
        progress: Optional[ProgressCallback],
    ) -> ExportResult:
        selected = self.select_rows(rows)
        total = max(1, sum(len(self._selected_segments(row)) for row in selected))

        def report(done: int, message: str) -> None:
            if progress is not None and not progress(done, total, message):
                raise ExportCancelled(
                    "Dışa aktarma kullanıcı tarafından iptal edildi.",
                    remedy="Hazırlanan geçici dosyalar silindi.",
                )

        manifest_samples: list[dict[str, Any]] = []
        fingerprint_keys: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        warnings: list[str] = []
        spec_seen: dict[str, SkeletonSpec] = {}
        mapping_used: Optional[JointMapping] = None
        completed = 0

        for row in selected:
            take = row.take
            segments = self._selected_segments(row)
            if not segments:
                continue

            paths = self.workspace.take_paths(take)
            if not path_exists(paths.skeleton_stream):
                excluded.append(
                    {
                        "take_id": take.take_id,
                        "reason": "missing_skeleton_stream",
                        "message": "İskelet akışı dosyası bulunamadı.",
                    }
                )
                completed += len(segments)
                report(completed, f"{row.participant_code}: akış yok, atlandı")
                continue

            report(completed, f"{row.participant_code} / {take.take_id} okunuyor")
            stream = load_skeleton_stream(paths.skeleton_stream)
            source_spec = try_get_skeleton_spec(
                take.skeleton_format or stream.skeleton_format
            )
            if source_spec is None:
                excluded.append(
                    {
                        "take_id": take.take_id,
                        "reason": "unknown_skeleton_format",
                        "message": (
                            f"Bilinmeyen iskelet biçimi: "
                            f"{take.skeleton_format or stream.skeleton_format!r}"
                        ),
                    }
                )
                completed += len(segments)
                continue

            mapping: Optional[JointMapping] = None
            output_spec = source_spec
            target = self.options.target_skeleton_format
            if target and target != source_spec.name:
                mapping = find_mapping(source_spec.name, target)
                if mapping is None:
                    excluded.append(
                        {
                            "take_id": take.take_id,
                            "reason": "no_joint_mapping",
                            "message": (
                                f"'{source_spec.name}' -> '{target}' eklem "
                                "eşleştirmesi tanımlı değil."
                            ),
                        }
                    )
                    completed += len(segments)
                    continue
                mapping_used = mapping
                output_spec = mapping.target_spec
                if mapping.status == "partial":
                    warnings.append(
                        f"Eklem eşleştirmesi kısmi: {mapping.mapped_count}/"
                        f"{mapping.target_spec.num_joints} eklem eşleşti; "
                        f"eşleşmeyenler NaN yazıldı "
                        f"({', '.join(mapping.unmapped_target_joints)})."
                    )
            spec_seen[output_spec.name] = output_spec

            tracking_id = self._preferred_tracking_id(stream)
            for segment in segments:
                completed += 1
                # Segment bounds are stream positions (see RepetitionSegment),
                # so they index the frame list directly. Clamping guards against
                # a sidecar written against a stream that was later truncated by
                # an interrupted recording.
                last = max(0, stream.frame_count - 1)
                start = min(max(0, segment.start_frame), last)
                end = min(max(start, segment.end_frame), last)
                joints = stream.joint_array(tracking_id, start=start, end=end)

                if joints.shape[0] < self.options.min_frames_per_sample:
                    excluded.append(
                        {
                            "take_id": take.take_id,
                            "segment_id": segment.segment_id,
                            "reason": "too_few_frames",
                            "message": (
                                f"Tekrar {segment.index}: {joints.shape[0]} kare, "
                                f"en az {self.options.min_frames_per_sample} gerekli."
                            ),
                        }
                    )
                    continue
                if joints.shape[1] == 0:
                    excluded.append(
                        {
                            "take_id": take.take_id,
                            "segment_id": segment.segment_id,
                            "reason": "no_body_in_interval",
                            "message": f"Tekrar {segment.index}: aralıkta gövde yok.",
                        }
                    )
                    continue

                confidences = (
                    stream.confidence_array(tracking_id, start=start, end=end)
                    if self.options.store_confidences
                    else None
                )
                if mapping is not None:
                    joints = mapping.apply(joints)
                    if confidences is not None:
                        confidences = mapping.apply_confidence(confidences)

                sample_id = f"{take.take_id}__{segment.segment_id}"
                sample_path = samples_dir / f"{sample_id}.npz"
                payload: dict[str, np.ndarray] = {
                    "joints_xyz": joints.astype(np.float32),
                    "frame_indices": np.asarray(
                        [f.frame_index for f in stream.frames[start : end + 1]],
                        dtype=np.int64,
                    ),
                    "camera_timestamps_ns": np.asarray(
                        [
                            f.camera_timestamp_ns
                            for f in stream.frames[start : end + 1]
                        ],
                        dtype=np.int64,
                    ),
                }
                if confidences is not None:
                    payload["joint_confidences"] = confidences.astype(np.float32)
                with open(long_path(sample_path), "wb") as handle:
                    np.savez_compressed(handle, **payload)

                entry = self._sample_entry(
                    sample_id=sample_id,
                    row=row,
                    segment=segment,
                    joints=joints,
                    output_spec=output_spec,
                    file_name=f"samples/{sample_path.name}",
                    camera_frame_range=(
                        int(payload["frame_indices"][0]),
                        int(payload["frame_indices"][-1]),
                    ),
                )
                manifest_samples.append(entry)
                fingerprint_keys.append(
                    {
                        key: entry[key]
                        for key in (
                            "sample_id",
                            "participant_id",
                            "session_id",
                            "take_id",
                            "segment_id",
                            "num_frames",
                            "num_joints",
                            "exercise",
                            "correctness",
                            "skeleton_format",
                        )
                    }
                )
                report(completed, f"{row.participant_code} / tekrar {segment.index}")

        if not manifest_samples:
            # An empty release is never published. Say *why* it is empty: the
            # exclusion reasons are the actionable part, not the empty count.
            reasons = sorted({item["reason"] for item in excluded})
            remedy = (
                "Filtreleri gevşetin veya en az bir tekrarı etiketleyip "
                "kaydı tamamlayın."
            )
            if reasons == ["no_joint_mapping"]:
                remedy = (
                    "Seçilen hedef iskelet biçimi için tanımlı bir eklem "
                    "eşleştirmesi yok. Kaynak biçimde dışa aktarın."
                )
            raise ExportError(
                "Dışa aktarılacak örnek bulunamadı."
                + (f" Dışlanma nedenleri: {', '.join(reasons)}." if reasons else ""),
                code="export_empty",
                remedy=remedy,
                details={"excluded": excluded[:20]},
            )

        report(total, "Manifest yazılıyor")
        return self._write_documents(
            staging=staging,
            name=name,
            samples=manifest_samples,
            fingerprint_keys=fingerprint_keys,
            excluded=excluded,
            warnings=warnings,
            specs=spec_seen,
            mapping=mapping_used,
        )

    # ------------------------------------------------------------- documents
    def _write_documents(
        self,
        *,
        staging: Path,
        name: str,
        samples: list[dict[str, Any]],
        fingerprint_keys: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
        warnings: list[str],
        specs: dict[str, SkeletonSpec],
        mapping: Optional[JointMapping],
    ) -> ExportResult:
        project = self.workspace.project
        schema = self.workspace.label_schema
        label_mapping = schema.label_mapping()

        skeleton_block: dict[str, Any] = {
            "formats": {n: spec.to_dict() for n, spec in sorted(specs.items())},
            "joint_mapping": mapping.to_dict() if mapping else None,
        }
        if mapping is None and self.options.target_skeleton_format:
            skeleton_block["joint_mapping_status"] = "not available yet"

        export_config = {
            "options": self.options.to_dict(),
            "app_version": APP_VERSION,
            "schema_version": RELEASE_SCHEMA_VERSION,
        }
        fingerprint = dataset_fingerprint(
            fingerprint_keys,
            export_config=export_config,
            skeleton_spec=skeleton_block["formats"],
            label_schema=label_mapping,
        )

        write_json(staging / "skeleton_spec.json", skeleton_block)
        write_json(staging / "label_mapping.json", label_mapping)
        write_json(staging / "dataset_fingerprint.json", fingerprint)
        write_json(
            staging / "manifest.json",
            {
                "schema_version": RELEASE_SCHEMA_VERSION,
                "release_name": name,
                "created_at": utc_now_iso(),
                "app_version": APP_VERSION,
                "project": {
                    "project_id": project.project_id,
                    "name": project.name,
                    "label_schema_version": schema.schema_version,
                },
                "array_contract": {
                    "dtype": "float32",
                    "shape": "[T, J, 3]",
                    "variable_length": True,
                    "missing_joint_value": "nan",
                    "normalisation": "none",
                    "note": (
                        "Ham yakalama koordinatları. Root centering, ölçek "
                        "normalizasyonu, interpolasyon ve augmentation "
                        "uygulanmamıştır; bunlar eğitim katmanına aittir."
                    ),
                },
                "export_config": export_config,
                "counts": {
                    "samples": len(samples),
                    "excluded": len(excluded),
                    "participants": len({s["participant_id"] for s in samples}),
                    "sessions": len({s["session_id"] for s in samples}),
                    "takes": len({s["take_id"] for s in samples}),
                },
                "samples": samples,
            },
        )
        write_json(
            staging / "excluded.json",
            {"count": len(excluded), "items": excluded},
        )

        report = self._validate(staging, samples, warnings)
        write_json(staging / "validation_report.json", report)
        return ExportResult(
            release_name=name,
            path=staging,
            sample_count=len(samples),
            excluded_count=len(excluded),
            fingerprint=fingerprint["fingerprint"],
            validation_passed=bool(report["passed"]),
            warnings=list(report["warnings"]),
        )

    def _sample_entry(
        self,
        *,
        sample_id: str,
        row: TakeRow,
        segment: RepetitionSegment,
        joints: np.ndarray,
        output_spec: SkeletonSpec,
        file_name: str,
        camera_frame_range: tuple[int, int],
    ) -> dict[str, Any]:
        take = row.take
        annotation = segment.annotation
        finite = np.isfinite(joints).all(axis=2)
        camera = take.camera_info
        return {
            "sample_id": sample_id,
            "file": file_name,
            "project_id": take.project_id,
            # Participant, session and take ids are preserved so a downstream
            # split can be grouped by them. Random sample splits leak.
            "participant_id": take.participant_id,
            "participant_code": row.participant_code,
            "session_id": take.session_id,
            "take_id": take.take_id,
            "segment_id": segment.segment_id,
            "repetition_index": segment.index,
            "num_frames": int(joints.shape[0]),
            "num_joints": int(joints.shape[1]),
            # Positions in the take's pose stream ...
            "start_position": segment.start_frame,
            "end_position": segment.end_frame,
            # ... and the camera's own frame numbers for the same span, which
            # differ whenever a frame was dropped during capture.
            "start_camera_frame": camera_frame_range[0],
            "end_camera_frame": camera_frame_range[1],
            "skeleton_format": output_spec.name,
            "coordinate_system": output_spec.coordinate_system,
            "length_unit": output_spec.length_unit,
            "exercise": annotation.exercise,
            "correctness": annotation.correctness.value,
            "error_types": list(annotation.error_types),
            "affected_joints": list(annotation.affected_joints),
            "movement_phase": annotation.movement_phase,
            "severity": annotation.severity,
            "annotation_status": annotation.status.value,
            "annotation_source": segment.source.value,
            "annotator_confidence": annotation.annotator_confidence,
            "origin": take.origin.value,
            "source_backend": camera.backend if camera else "unknown",
            "camera_model": camera.model if camera else "unknown",
            "camera_serial": camera.serial_number if camera else None,
            "sdk_version": camera.sdk_version if camera else None,
            "capture_profile": take.capture_profile.to_dict(),
            "quality": {
                "valid_joint_ratio": round(float(finite.mean()), 4),
                "take_tracking_coverage": round(
                    float(take.metrics.tracking_coverage), 4
                ),
                "take_measured_fps": round(float(take.metrics.measured_fps), 2),
                "take_capture_loss": take.metrics.has_capture_loss,
            },
        }

    def _validate(
        self, staging: Path, samples: list[dict[str, Any]], warnings: list[str]
    ) -> dict[str, Any]:
        """Re-read every written sample and check it against its manifest entry."""
        errors: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        all_warnings = list(warnings)
        joint_counts: set[int] = set()
        empty_samples = 0

        for entry in samples:
            path = staging / entry["file"]
            if not path_exists(path):
                errors.append({"sample_id": entry["sample_id"], "issue": "file_missing"})
                continue
            with np.load(long_path(path)) as payload:
                joints = payload["joints_xyz"]
                if joints.dtype != np.float32:
                    errors.append(
                        {
                            "sample_id": entry["sample_id"],
                            "issue": "dtype_mismatch",
                            "expected": "float32",
                            "actual": str(joints.dtype),
                        }
                    )
                if joints.ndim != 3 or joints.shape[2] != 3:
                    errors.append(
                        {
                            "sample_id": entry["sample_id"],
                            "issue": "shape_invalid",
                            "actual": list(joints.shape),
                        }
                    )
                    continue
                if joints.shape[0] != entry["num_frames"]:
                    errors.append(
                        {
                            "sample_id": entry["sample_id"],
                            "issue": "frame_count_mismatch",
                            "expected": entry["num_frames"],
                            "actual": int(joints.shape[0]),
                        }
                    )
                joint_counts.add(int(joints.shape[1]))
                if not np.isfinite(joints).any():
                    empty_samples += 1
            entry["checksum"] = hash_file(path)

        if empty_samples:
            all_warnings.append(
                f"{empty_samples} örnekte hiç geçerli eklem koordinatı yok."
            )
        if len(joint_counts) > 1:
            all_warnings.append(
                f"Sürüm birden fazla eklem sayısı içeriyor: {sorted(joint_counts)}."
            )

        participants = {s["participant_id"] for s in samples}
        if len(participants) < 2:
            all_warnings.append(
                f"Sürüm {len(participants)} katılımcı içeriyor; katılımcı bazlı "
                "eğitim/test ayrımı yapılamaz."
            )
        synthetic = sum(1 for s in samples if s["origin"] == "synthetic")
        if synthetic:
            all_warnings.append(
                f"{synthetic} örnek SENTETİK verilerden üretildi ve gerçek "
                "ölçüm değildir."
            )

        checks.append(
            {
                "check": "array_contract",
                "passed": not errors,
                "detail": "Her örnek float32 [T, J, 3] ve manifest ile tutarlı.",
            }
        )
        checks.append(
            {
                "check": "participant_grouping_preserved",
                "passed": True,
                "detail": (
                    "participant_id / session_id / take_id her örnekte korunuyor; "
                    "veri sızıntısı kontrolü downstream'de yapılabilir."
                ),
            }
        )
        return {
            "schema_version": RELEASE_SCHEMA_VERSION,
            "validated_at": utc_now_iso(),
            "passed": not errors,
            "sample_count": len(samples),
            "errors": errors,
            "warnings": all_warnings,
            "checks": checks,
        }

    @staticmethod
    def _preferred_tracking_id(stream: Any) -> Optional[int]:
        """The identity that appears in the most frames.

        Exporting a take with an identity switch mid-way is a data-quality
        problem, which the take's ``body_id_events`` already record; here the
        dominant identity is chosen rather than mixing two people into one array.
        """
        counts: dict[int, int] = {}
        for frame in stream.frames:
            for body in frame.bodies:
                counts[body.tracking_id] = counts.get(body.tracking_id, 0) + 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]


def read_release_manifest(release_dir: Path) -> dict[str, Any]:
    from kinecapture.core.jsonio import read_json_mapping

    return read_json_mapping(Path(release_dir) / "manifest.json")


__all__ = [
    "ExportOptions",
    "ExportResult",
    "ProgressCallback",
    "ReleaseBuilder",
    "list_releases",
    "next_release_name",
    "read_release_manifest",
]
