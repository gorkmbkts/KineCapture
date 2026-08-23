"""Versioned dataset releases.

A release is one **movement sample** per example, exported as ``float32
[T, J, 3]`` in the capture's *native* joint order and *raw* coordinates, plus
the temporal error intervals localised inside that movement.

Label contract
--------------
Each example carries:

* ``exercise`` - the movement class;
* ``correctness`` - a **binary** verdict, ``correct`` or ``incorrect``;
* ``error_intervals`` - zero or more ``(error class, start, end)`` spans inside
  the example, given both in take-absolute positions and in positions relative
  to the exported array, so a consumer never has to guess or recompute.

Only samples the review screen calls ready are exported; ready is decided by
:func:`kinecapture.domain.project.evaluate_sample`, the same function the UI
uses, so "labelled" on screen and "eligible" here cannot drift apart.

Boundary convention (identical in the UI, the sidecar and here): positions are
0-based indices into the take's pose stream and ranges are **inclusive at both
ends**, so ``joints[start:end + 1]`` is the span.

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
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

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
from kinecapture.domain.project import MovementSample, evaluate_sample
from kinecapture.features.base import Availability, SourceField
from kinecapture.features.compute import FeatureContext, compute_features
from kinecapture.features.registry import get_feature, order_features
from kinecapture.features.spec import availability_counter, build_feature_spec
from kinecapture.playback.take_reader import load_skeleton_stream
from kinecapture.visualization.mapping import JointMapping, find_mapping
from kinecapture.visualization.skeleton_spec import SkeletonSpec, try_get_skeleton_spec

#: Optional tracker fields, and how each one survives a joint mapping.
#: ``BodyPose`` attribute -> (:class:`SourceField` key, per-joint?).
_RAW_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("joint_orientations", SourceField.JOINT_ORIENTATIONS.value, True),
    ("joint_positions_2d", SourceField.JOINT_POSITIONS_2D.value, True),
    (
        "joint_position_covariances",
        SourceField.JOINT_POSITION_COVARIANCES.value,
        True,
    ),
    ("local_joint_positions_xyz", SourceField.LOCAL_JOINT_POSITIONS.value, True),
    ("root_position", SourceField.ROOT_POSITION.value, False),
    ("root_orientation", SourceField.ROOT_ORIENTATION.value, False),
    ("tracker_root_velocity_xyz", SourceField.ROOT_VELOCITY.value, False),
    ("root_position_covariance", SourceField.ROOT_POSITION_COVARIANCE.value, False),
)

#: Per-joint raw fields whose meaning survives a pure index permutation. A
#: field not listed here is dropped when a mapping is active rather than being
#: carried onto a skeleton whose parent chain it does not describe.
_MAPPABLE_RAW_FIELDS: frozenset[str] = frozenset(
    {
        SourceField.JOINT_POSITIONS_2D.value,
        SourceField.JOINT_POSITION_COVARIANCES.value,
    }
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
    #: Include samples the review screen does not call ready. Off by default:
    #: the release then contains exactly what the UI shows as finished.
    include_unready: bool = False
    include_excluded_samples: bool = False
    min_frames_per_sample: int = 4
    target_skeleton_format: Optional[str] = None
    store_confidences: bool = True
    #: Emit the per-frame ``error_multi_hot`` target array alongside the
    #: interval list. Costs ``T x C`` bytes per sample and saves every consumer
    #: from rebuilding the same thing.
    store_error_target_arrays: bool = True
    #: Additional feature ids from :mod:`kinecapture.features.registry`. Empty
    #: by default, so an export that ticks nothing produces exactly the
    #: canonical release it always produced.
    feature_ids: tuple[str, ...] = ()
    #: Which preset the selection came from, for provenance only. The resolved
    #: ids above are authoritative; a stale preset name can never change what
    #: gets written.
    feature_preset: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.feature_ids = tuple(self.feature_ids or ())

    def resolved_feature_ids(self) -> tuple[str, ...]:
        """The full, ordered selection actually computed.

        ``store_confidences`` predates the registry and stays the switch for
        the confidence array, so the two cannot disagree about it.
        """
        wanted = set(self.feature_ids)
        if self.store_confidences:
            wanted.add("joint_confidences")
        else:
            wanted.discard("joint_confidences")
        return order_features(wanted)

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.__dict__)
        payload["feature_ids"] = list(self.feature_ids)
        payload["resolved_feature_ids"] = list(self.resolved_feature_ids())
        return payload


@dataclass
class ExportResult:
    """Outcome of a completed export."""

    release_name: str
    path: Path
    sample_count: int
    excluded_count: int
    error_interval_count: int
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
    @property
    def _error_vocabulary(self) -> tuple[str, ...]:
        return self.workspace.label_schema.error_type_codes()

    def select_rows(self, rows: Optional[Sequence[TakeRow]] = None) -> list[TakeRow]:
        """Takes eligible under the current options."""
        candidates = list(rows) if rows is not None else list(self.index.rows)
        if not self.options.include_synthetic:
            candidates = [row for row in candidates if not row.take.is_synthetic]
        if self.options.include_unready:
            return [row for row in candidates if row.take.usable_for_export]
        return exportable_rows(candidates)

    def _partition_samples(
        self, row: TakeRow
    ) -> tuple[list[MovementSample], list[dict[str, Any]]]:
        """Split a take's samples into exported and rejected-with-a-reason.

        A sample the user has not finished is not silently absent from the
        release: it is listed in ``excluded.json`` with the same wording the
        review screen shows, so "why is my movement missing?" has an answer.
        """
        selected: list[MovementSample] = []
        rejected: list[dict[str, Any]] = []
        for sample in row.samples:
            if not (self.options.include_excluded_samples or sample.is_active):
                rejected.append(
                    {
                        "take_id": row.take.take_id,
                        "sample_id": sample.sample_id,
                        "reason": "sample_excluded_by_user",
                        "message": (
                            f"Hareket {sample.index}: kullanıcı tarafından "
                            "datasetten çıkarıldı."
                        ),
                    }
                )
                continue
            readiness, problems = evaluate_sample(
                sample, known_error_codes=self._error_vocabulary
            )
            if not self.options.include_unready and not readiness.is_ready:
                rejected.append(
                    {
                        "take_id": row.take.take_id,
                        "sample_id": sample.sample_id,
                        "reason": f"sample_{readiness.value}",
                        "message": (
                            f"Hareket {sample.index}: "
                            + (
                                " ".join(p.message for p in problems)
                                or "etiket tamamlanmamış."
                            )
                        ),
                    }
                )
                continue
            selected.append(sample)
        return sorted(selected, key=lambda s: s.start_frame), rejected

    def _selected_samples(self, row: TakeRow) -> list[MovementSample]:
        """Just the exportable samples, for progress counting and previews."""
        return self._partition_samples(row)[0]

    def _rejected_takes(
        self,
        rows: Optional[Sequence[TakeRow]],
        selected: Sequence[TakeRow],
    ) -> list[dict[str, Any]]:
        """Takes that never got as far as sample selection, and why.

        Without this, a whole take vanishing from a release would look like a
        bug rather than a filter doing its job.
        """
        considered = list(rows) if rows is not None else list(self.index.rows)
        chosen = {row.take.take_id for row in selected}
        rejected: list[dict[str, Any]] = []
        for row in considered:
            if row.take.take_id in chosen:
                continue
            take = row.take
            if take.is_synthetic and not self.options.include_synthetic:
                reason, message = (
                    "take_synthetic_excluded",
                    "Sentetik kayıt; 'Sentetik kayıtları dahil et' kapalı.",
                )
            elif not take.usable_for_export:
                reason, message = (
                    "take_not_usable",
                    f"Kayıt durumu '{take.state.value}', kalite "
                    f"'{take.quality.value}'.",
                )
            else:
                reason, message = (
                    "take_without_ready_sample",
                    "Bu kayıtta export'a hazır hareket yok.",
                )
            rejected.append(
                {
                    "take_id": take.take_id,
                    "reason": reason,
                    "message": f"{row.participant_code}: {message}",
                }
            )
        return rejected

    #: Pre-redesign name, kept for older callers.
    _selected_segments = _selected_samples

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
            "Dataset sürümü yayımlandı: %s (%d örnek, %d hata aralığı)",
            name,
            result.sample_count,
            result.error_interval_count,
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
        total = max(1, sum(len(self._selected_samples(row)) for row in selected))

        manifest_samples: list[dict[str, Any]] = []
        fingerprint_keys: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = self._rejected_takes(rows, selected)
        warnings: list[str] = []

        # Column order of the per-frame error target. Fixed by the project's
        # label mapping so every release indexes classes identically.
        error_classes = sorted(self._error_vocabulary)
        error_index = {code: position for position, code in enumerate(error_classes)}

        def report(done: int, message: str) -> None:
            if progress is not None and not progress(done, total, message):
                raise ExportCancelled(
                    "Dışa aktarma kullanıcı tarafından iptal edildi.",
                    remedy="Hazırlanan geçici dosyalar silindi.",
                )

        spec_seen: dict[str, SkeletonSpec] = {}
        mapping_used: Optional[JointMapping] = None
        completed = 0
        interval_total = 0

        feature_ids = self.options.resolved_feature_ids()
        availability: dict[str, dict[str, int]] = {
            feature_id: availability_counter() for feature_id in feature_ids
        }
        source_fields: dict[str, int] = {}
        resolved_angles: Optional[list[dict[str, Any]]] = None

        for row in selected:
            take = row.take
            samples, rejected = self._partition_samples(row)
            excluded.extend(rejected)
            if not samples:
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
                completed += len(samples)
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
                            "Bilinmeyen iskelet biçimi: "
                            f"{take.skeleton_format or stream.skeleton_format!r}"
                        ),
                    }
                )
                completed += len(samples)
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
                    completed += len(samples)
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
            for field_name in stream.optional_field_names(tracking_id):
                source_fields[field_name] = source_fields.get(field_name, 0) + 1
            for sample in samples:
                completed += 1
                # Bounds are stream positions, inclusive. Clamping guards a
                # sidecar written against a stream later truncated by an
                # interrupted recording.
                last = max(0, stream.frame_count - 1)
                start = min(max(0, sample.start_frame), last)
                end = min(max(start, sample.end_frame), last)
                joints = stream.joint_array(tracking_id, start=start, end=end)

                if joints.shape[0] < self.options.min_frames_per_sample:
                    excluded.append(
                        {
                            "take_id": take.take_id,
                            "sample_id": sample.sample_id,
                            "reason": "too_few_frames",
                            "message": (
                                f"Hareket {sample.index}: {joints.shape[0]} kare, "
                                f"en az {self.options.min_frames_per_sample} gerekli."
                            ),
                        }
                    )
                    continue
                if joints.shape[1] == 0:
                    excluded.append(
                        {
                            "take_id": take.take_id,
                            "sample_id": sample.sample_id,
                            "reason": "no_body_in_interval",
                            "message": f"Hareket {sample.index}: aralıkta gövde yok.",
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

                frame_window = stream.frames[start : end + 1]
                intervals, dropped = self._resolve_intervals(
                    sample, start, end, frame_window, error_index
                )
                excluded.extend(dropped)
                interval_total += len(intervals)

                sample_id = f"{take.take_id}__{sample.sample_id}"
                sample_path = samples_dir / f"{sample_id}.npz"
                frame_indices = np.asarray(
                    [f.frame_index for f in frame_window], dtype=np.int64
                )
                timestamps = np.asarray(
                    [f.camera_timestamp_ns for f in frame_window], dtype=np.int64
                )
                payload: dict[str, np.ndarray] = {
                    "joints_xyz": joints.astype(np.float32),
                    "frame_indices": frame_indices,
                    "camera_timestamps_ns": timestamps,
                }

                # ---- selected features -------------------------------
                context = FeatureContext(
                    spec=output_spec,
                    joints=joints.astype(np.float32),
                    timestamps_ns=timestamps,
                    frame_indices=frame_indices,
                    target_fps=float(take.capture_profile.fps or 0.0),
                    confidences=(
                        confidences.astype(np.float32)
                        if confidences is not None
                        else None
                    ),
                    raw=self._raw_arrays(stream, tracking_id, start, end, mapping),
                    mapping_active=mapping is not None,
                    **stream.body_state_arrays(tracking_id, start=start, end=end),
                )
                computed = compute_features(context, feature_ids)
                payload.update(computed.arrays)
                if not self.options.store_confidences:
                    payload.pop("joint_confidences", None)
                for feature_id, level in computed.availability.items():
                    availability[feature_id][level.value] += 1
                if resolved_angles is None:
                    resolved_angles = context.resolved_angles

                # (class index, relative start, relative end), inclusive.
                payload["error_intervals"] = np.asarray(
                    [
                        [i["class_index"], i["relative_start"], i["relative_end"]]
                        for i in intervals
                    ],
                    dtype=np.int32,
                ).reshape(-1, 3)

                if self.options.store_error_target_arrays:
                    payload["error_multi_hot"] = self._error_multi_hot(
                        intervals, frames=int(joints.shape[0]), classes=len(error_classes)
                    )

                with open(long_path(sample_path), "wb") as handle:
                    np.savez_compressed(handle, **payload)

                entry = self._sample_entry(
                    sample_id=sample_id,
                    row=row,
                    sample=sample,
                    joints=joints,
                    output_spec=output_spec,
                    file_name=f"samples/{sample_path.name}",
                    positions=(start, end),
                    camera_frame_range=(
                        int(frame_indices[0]),
                        int(frame_indices[-1]),
                    ),
                    intervals=intervals,
                )
                entry["features"] = computed.availability_dict()
                entry["feature_availability_ratio"] = dict(computed.ratios)
                entry["feature_notes"] = dict(computed.reasons)
                entry["array_keys"] = sorted(payload)
                # Hashed here, while the file is the thing that was just
                # written. Computing it after the fingerprint - as an earlier
                # version did - left the fingerprint blind to the array
                # contents it is supposed to identify.
                entry["checksum"] = hash_file(sample_path)
                manifest_samples.append(entry)
                fingerprint_keys.append(self._fingerprint_key(entry))
                report(completed, f"{row.participant_code} / hareket {sample.index}")

        if not manifest_samples:
            # An empty release is never published. Say *why* it is empty: the
            # exclusion reasons are the actionable part, not the empty count.
            reasons = sorted({item["reason"] for item in excluded})
            remedy = (
                "Filtreleri gevşetin veya en az bir hareketi tam etiketleyip "
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
            error_classes=error_classes,
            interval_total=interval_total,
            feature_ids=feature_ids,
            availability=availability,
            source_fields=source_fields,
            resolved_angles=resolved_angles,
        )

    # --------------------------------------------------------- raw fields
    @staticmethod
    def _raw_arrays(
        stream: Any,
        tracking_id: Optional[int],
        start: int,
        end: int,
        mapping: Optional[JointMapping],
    ) -> dict[str, Optional[np.ndarray]]:
        """Collect the optional tracker arrays for one sample's frame window.

        Per-joint fields are carried through an active joint mapping only when
        a pure index permutation preserves their meaning. Local joint
        quaternions and parent-relative positions are described relative to the
        *source* skeleton's parent chain, so on a target skeleton with a
        different chain they would be numerically present and semantically
        wrong; they are dropped instead, and the feature that needs them
        reports itself unavailable with that reason.
        """
        arrays: dict[str, Optional[np.ndarray]] = {}
        for attribute, key, per_joint in _RAW_FIELDS:
            values = stream.optional_body_array(
                tracking_id, attribute, start=start, end=end
            )
            if values is None:
                arrays[key] = None
                continue
            if per_joint and mapping is not None:
                if key not in _MAPPABLE_RAW_FIELDS:
                    arrays[key] = None
                    continue
                values = mapping.apply_per_joint(values)
            arrays[key] = values
        return arrays

    # ------------------------------------------------------- error intervals
    def _resolve_intervals(
        self,
        sample: MovementSample,
        start: int,
        end: int,
        frame_window: Sequence[Any],
        error_index: dict[str, int],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Turn a sample's error intervals into export records.

        Returns the usable records and the ones that had to be dropped, each
        with a reason. An interval is never silently reshaped into something
        that would misrepresent where the error actually was.
        """
        resolved: list[dict[str, Any]] = []
        dropped: list[dict[str, Any]] = []

        for interval in sample.sorted_intervals():
            if not interval.error_code:
                dropped.append(
                    {
                        "take_id": sample.take_id,
                        "sample_id": sample.sample_id,
                        "interval_id": interval.interval_id,
                        "reason": "interval_without_class",
                        "message": "Hata aralığına sınıf atanmamış.",
                    }
                )
                continue
            if interval.error_code not in error_index:
                dropped.append(
                    {
                        "take_id": sample.take_id,
                        "sample_id": sample.sample_id,
                        "interval_id": interval.interval_id,
                        "reason": "unknown_error_class",
                        "message": (
                            f"'{interval.error_code}' hata sınıfı etiket şemasında yok."
                        ),
                    }
                )
                continue
            if interval.end_frame < interval.start_frame:
                dropped.append(
                    {
                        "take_id": sample.take_id,
                        "sample_id": sample.sample_id,
                        "interval_id": interval.interval_id,
                        "reason": "interval_reversed",
                        "message": "Hata aralığının bitişi başlangıcından önce.",
                    }
                )
                continue
            if interval.start_frame < start or interval.end_frame > end:
                dropped.append(
                    {
                        "take_id": sample.take_id,
                        "sample_id": sample.sample_id,
                        "interval_id": interval.interval_id,
                        "reason": "interval_outside_sample",
                        "message": (
                            f"Hata aralığı ({interval.start_frame}-"
                            f"{interval.end_frame}) hareketin ({start}-{end}) dışında."
                        ),
                    }
                )
                continue

            relative_start = interval.start_frame - start
            relative_end = interval.end_frame - start
            resolved.append(
                {
                    "interval_id": interval.interval_id,
                    "error_code": interval.error_code,
                    "class_index": error_index[interval.error_code],
                    "start_position": interval.start_frame,
                    "end_position": interval.end_frame,
                    "relative_start": relative_start,
                    "relative_end": relative_end,
                    "num_frames": relative_end - relative_start + 1,
                    "start_camera_frame": int(
                        frame_window[relative_start].frame_index
                    ),
                    "end_camera_frame": int(frame_window[relative_end].frame_index),
                    "start_timestamp_ns": int(
                        frame_window[relative_start].camera_timestamp_ns
                    ),
                    "end_timestamp_ns": int(
                        frame_window[relative_end].camera_timestamp_ns
                    ),
                    "source": interval.source.value,
                    "note": interval.note,
                }
            )
        return resolved, dropped

    @staticmethod
    def _error_multi_hot(
        intervals: Sequence[dict[str, Any]], *, frames: int, classes: int
    ) -> np.ndarray:
        """``uint8 [T, C]`` per-frame error target.

        Column order matches ``label_mapping.json``'s
        ``error_types.code_to_index``. Overlapping intervals simply set several
        columns on the same frame, which is exactly what "two errors at once"
        should mean.
        """
        target = np.zeros((frames, max(0, classes)), dtype=np.uint8)
        for interval in intervals:
            column = int(interval["class_index"])
            if 0 <= column < classes:
                target[
                    int(interval["relative_start"]) : int(interval["relative_end"]) + 1,
                    column,
                ] = 1
        return target

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
        error_classes: Sequence[str],
        interval_total: int,
        feature_ids: Sequence[str],
        availability: Mapping[str, Mapping[str, int]],
        source_fields: Mapping[str, int],
        resolved_angles: Optional[Sequence[Mapping[str, Any]]],
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
        feature_spec = build_feature_spec(
            feature_ids=feature_ids,
            specs=specs,
            preset_id=self.options.feature_preset,
            availability=availability,
            sample_count=len(samples),
            mapping=mapping.to_dict() if mapping else None,
            resolved_angles=resolved_angles,
            source_fields=source_fields,
        )
        # The feature component carries the definitions and their parameters,
        # so bumping a feature's version or changing an algorithm parameter
        # changes the release fingerprint even when every sample is identical.
        fingerprint = dataset_fingerprint(
            fingerprint_keys,
            export_config=export_config,
            skeleton_spec=skeleton_block["formats"],
            label_schema=label_mapping,
            features={
                "selected": list(feature_ids),
                "definitions": [
                    get_feature(feature_id).fingerprint_key()
                    for feature_id in feature_ids
                ],
            },
        )

        write_json(staging / "skeleton_spec.json", skeleton_block)
        write_json(staging / "label_mapping.json", label_mapping)
        write_json(staging / "feature_spec.json", feature_spec)
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
                "label_contract": {
                    "level_1": (
                        "Her örnek bir hareket sample'ıdır: exercise + ikili "
                        "correctness taşır."
                    ),
                    "level_2": (
                        "error_intervals, hareketin içindeki zamansal hata "
                        "aralıklarıdır. Bir aralık tek bir hata sınıfı taşır; "
                        "aynı anda görülen farklı sınıflar çakışan aralıklarla "
                        "ifade edilir."
                    ),
                    "boundaries": (
                        "start/end konumları her iki uçta DAHİLDİR. "
                        "start_position/end_position kayıt içindeki mutlak "
                        "akış konumudur; relative_start/relative_end ise "
                        "joints_xyz dizisindeki indekstir "
                        "(joints_xyz[relative_start:relative_end + 1])."
                    ),
                    "arrays": {
                        "error_intervals": (
                            "int32 [K, 3] = (class_index, relative_start, "
                            "relative_end), her iki uç dahil."
                        ),
                        "error_multi_hot": (
                            "uint8 [T, C]; sütun sırası "
                            "label_mapping.error_types.code_to_index ile aynıdır. "
                            "Çakışan aralıklar aynı karede birden çok sütunu 1 yapar."
                        )
                        if self.options.store_error_target_arrays
                        else "yazılmadı (store_error_target_arrays=False)",
                    },
                    "error_classes": list(error_classes),
                    "movement_phase": (
                        "Bu sürümde hareket fazı etiketi yoktur; iki seviyeli "
                        "etiket modelinde kaldırılmıştır."
                    ),
                },
                "feature_contract": {
                    "document": "feature_spec.json",
                    "preset": self.options.feature_preset,
                    "selected_feature_ids": list(feature_ids),
                    "feature_versions": {
                        feature_id: get_feature(feature_id).version
                        for feature_id in feature_ids
                    },
                    "array_keys": [
                        key
                        for feature_id in feature_ids
                        for key in get_feature(feature_id).array_keys
                    ],
                    "availability": {
                        feature_id: dict(counts)
                        for feature_id, counts in sorted(availability.items())
                    },
                    "source_field_availability": dict(sorted(source_fields.items())),
                    "note": (
                        "Canonical diziler (joints_xyz, frame_indices, "
                        "camera_timestamps_ns) her sürümde bulunur; buradaki "
                        "özellikler onların yerine geçmez, yanlarına yazılır. "
                        "Seçilen anahtar kümesi bütün örnek dosyalarında "
                        "aynıdır; bir örnekte üretilemeyen özellik NaN/False "
                        "olarak yazılır ve availability'de raporlanır."
                    ),
                },
                "export_config": export_config,
                "counts": {
                    "samples": len(samples),
                    "error_intervals": interval_total,
                    "excluded": len(excluded),
                    "participants": len({s["participant_id"] for s in samples}),
                    "sessions": len({s["session_id"] for s in samples}),
                    "takes": len({s["take_id"] for s in samples}),
                },
                "samples": samples,
            },
        )
        write_json(
            staging / "excluded.json", {"count": len(excluded), "items": excluded}
        )

        report = self._validate(
            staging, samples, warnings, error_classes, feature_ids, availability
        )
        write_json(staging / "validation_report.json", report)
        return ExportResult(
            release_name=name,
            path=staging,
            sample_count=len(samples),
            excluded_count=len(excluded),
            error_interval_count=interval_total,
            fingerprint=fingerprint["fingerprint"],
            validation_passed=bool(report["passed"]),
            warnings=list(report["warnings"]),
        )

    @staticmethod
    def _fingerprint_key(entry: dict[str, Any]) -> dict[str, Any]:
        """The identity of one sample for fingerprinting purposes.

        Includes the error intervals, so adding, removing, re-classifying or
        moving an interval provably changes the release fingerprint.
        """
        return {
            "sample_id": entry["sample_id"],
            "participant_id": entry["participant_id"],
            "session_id": entry["session_id"],
            "take_id": entry["take_id"],
            "movement_sample_id": entry["movement_sample_id"],
            "num_frames": entry["num_frames"],
            "num_joints": entry["num_joints"],
            "exercise": entry["exercise"],
            "correctness": entry["correctness"],
            "skeleton_format": entry["skeleton_format"],
            "error_intervals": [
                [
                    interval["error_code"],
                    interval["relative_start"],
                    interval["relative_end"],
                ]
                for interval in entry["error_intervals"]
            ],
            # The written file's own digest. This is what makes the fingerprint
            # sensitive to the array *contents*, not merely to the metadata
            # describing them.
            "checksum": entry.get("checksum"),
            "array_keys": list(entry.get("array_keys") or ()),
        }

    def _sample_entry(
        self,
        *,
        sample_id: str,
        row: TakeRow,
        sample: MovementSample,
        joints: np.ndarray,
        output_spec: SkeletonSpec,
        file_name: str,
        positions: tuple[int, int],
        camera_frame_range: tuple[int, int],
        intervals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        take = row.take
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
            "movement_sample_id": sample.sample_id,
            "movement_index": sample.index,
            "num_frames": int(joints.shape[0]),
            "num_joints": int(joints.shape[1]),
            # Absolute positions in the take's pose stream, inclusive.
            "start_position": positions[0],
            "end_position": positions[1],
            # The camera's own frame numbers for the same span.
            "start_camera_frame": camera_frame_range[0],
            "end_camera_frame": camera_frame_range[1],
            "skeleton_format": output_spec.name,
            "coordinate_system": output_spec.coordinate_system,
            "length_unit": output_spec.length_unit,
            # ---- level 1: the movement label ----
            "exercise": sample.exercise,
            "correctness": sample.correctness.value,
            # ---- level 2: temporal error localisation ----
            "error_intervals": intervals,
            "error_classes": sorted({i["error_code"] for i in intervals}),
            "has_error_localisation": bool(intervals),
            "label_source": sample.source.value,
            "annotator": sample.annotator,
            "note": sample.note,
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
        self,
        staging: Path,
        samples: list[dict[str, Any]],
        warnings: list[str],
        error_classes: Sequence[str],
        feature_ids: Sequence[str] = (),
        availability: Optional[Mapping[str, Mapping[str, int]]] = None,
    ) -> dict[str, Any]:
        """Re-read every written sample and check it against its manifest entry."""
        errors: list[dict[str, Any]] = []
        checks: list[dict[str, Any]] = []
        all_warnings = list(warnings)
        joint_counts: set[int] = set()
        empty_samples = 0
        localised = 0
        vocabulary = set(error_classes)

        for entry in samples:
            sample_id = entry["sample_id"]
            path = staging / entry["file"]
            if not path_exists(path):
                errors.append({"sample_id": sample_id, "issue": "file_missing"})
                continue
            with np.load(long_path(path)) as payload:
                joints = payload["joints_xyz"]
                if joints.dtype != np.float32:
                    errors.append(
                        {
                            "sample_id": sample_id,
                            "issue": "dtype_mismatch",
                            "expected": "float32",
                            "actual": str(joints.dtype),
                        }
                    )
                if joints.ndim != 3 or joints.shape[2] != 3:
                    errors.append(
                        {
                            "sample_id": sample_id,
                            "issue": "shape_invalid",
                            "actual": list(joints.shape),
                        }
                    )
                    continue
                frames = int(joints.shape[0])
                if frames != entry["num_frames"]:
                    errors.append(
                        {
                            "sample_id": sample_id,
                            "issue": "frame_count_mismatch",
                            "expected": entry["num_frames"],
                            "actual": frames,
                        }
                    )
                joint_counts.add(int(joints.shape[1]))
                if not np.isfinite(joints).any():
                    empty_samples += 1

                errors.extend(
                    self._validate_intervals(entry, payload, frames, vocabulary)
                )

                errors.extend(
                    self._validate_features(entry, payload, frames, feature_ids)
                )

            if entry["error_intervals"]:
                localised += 1
            # The checksum was taken when the file was written and hashed into
            # the fingerprint; re-hashing here proves the published bytes are
            # still the ones the fingerprint covers.
            recorded = entry.get("checksum")
            actual = hash_file(path)
            if recorded and recorded != actual:
                errors.append(
                    {
                        "sample_id": sample_id,
                        "issue": "checksum_changed_after_write",
                        "expected": recorded,
                        "actual": actual,
                    }
                )
            entry["checksum"] = actual

        # --- label-level consistency, mirroring the UI's readiness rule ------
        for entry in samples:
            correctness = entry["correctness"]
            count = len(entry["error_intervals"])
            if correctness == "correct" and count:
                errors.append(
                    {
                        "sample_id": entry["sample_id"],
                        "issue": "correct_with_error_intervals",
                        "detail": f"{count} hata aralığı",
                    }
                )
            if correctness == "incorrect" and not count:
                errors.append(
                    {
                        "sample_id": entry["sample_id"],
                        "issue": "incorrect_without_error_interval",
                    }
                )
            if correctness not in ("correct", "incorrect"):
                errors.append(
                    {
                        "sample_id": entry["sample_id"],
                        "issue": "correctness_not_binary",
                        "actual": correctness,
                    }
                )

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
        incorrect = sum(1 for s in samples if s["correctness"] == "incorrect")
        if incorrect and not localised:
            all_warnings.append(
                "Hiçbir hatalı örnekte zamansal hata aralığı yok; zamansal "
                "yerelleştirme eğitilemez."
            )

        checks.append(
            {
                "check": "array_contract",
                "passed": not any(
                    e["issue"]
                    in ("dtype_mismatch", "shape_invalid", "frame_count_mismatch")
                    for e in errors
                ),
                "detail": "Her örnek float32 [T, J, 3] ve manifest ile tutarlı.",
            }
        )
        checks.append(
            {
                "check": "error_interval_bounds",
                "passed": not any(
                    e["issue"].startswith("interval_") for e in errors
                ),
                "detail": (
                    "Her hata aralığı diziyle örtüşüyor ve göreli sınırları "
                    "mutlak sınırlarıyla birebir eşleşiyor."
                ),
            }
        )
        checks.append(
            {
                "check": "correctness_consistency",
                "passed": not any(
                    e["issue"]
                    in (
                        "correct_with_error_intervals",
                        "incorrect_without_error_interval",
                        "correctness_not_binary",
                    )
                    for e in errors
                ),
                "detail": (
                    "Doğru örneklerde hata aralığı yok, hatalı örneklerin "
                    "hepsinde en az bir aralık var, karar ikili."
                ),
            }
        )
        # --- feature availability across the whole release ------------------
        counts = dict(availability or {})
        never: list[str] = []
        partial: list[str] = []
        for feature_id in feature_ids:
            entry_counts = counts.get(feature_id) or {}
            absent = int(entry_counts.get(Availability.ABSENT.value, 0))
            partly = int(entry_counts.get(Availability.PARTIAL.value, 0))
            if samples and absent >= len(samples):
                never.append(feature_id)
            elif partly:
                partial.append(feature_id)
        for feature_id in never:
            # A selected feature that came out nowhere is a failed export, not
            # a quiet success: the user asked for data that does not exist.
            errors.append(
                {
                    "issue": "feature_never_available",
                    "feature_id": feature_id,
                    "detail": (
                        f"'{get_feature(feature_id).label}' hiçbir örnekte "
                        "üretilemedi."
                    ),
                }
            )
        if partial:
            all_warnings.append(
                "Bazı özellikler yalnız kısmen üretilebildi: "
                + ", ".join(sorted(partial))
                + ". Ayrıntı feature_spec.json içindeki availability bloğunda."
            )
        if feature_ids:
            checks.append(
                {
                    "check": "feature_contract",
                    "passed": not any(
                        e["issue"].startswith("feature_") for e in errors
                    ),
                    "detail": (
                        "Seçilen her özellik bütün örneklerde aynı anahtarlarla, "
                        "beyan edilen dtype ve şekilde yazıldı; maskeler NaN "
                        "düzeniyle tutarlı."
                    ),
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
            "error_interval_count": sum(
                len(s["error_intervals"]) for s in samples
            ),
            "samples_with_localisation": localised,
            "errors": errors,
            "warnings": all_warnings,
            "checks": checks,
        }

    #: Float array -> the mask that must agree with its NaN pattern.
    _MASK_PAIRS: tuple[tuple[str, str], ...] = (
        ("joint_displacement_xyz", "joint_displacement_valid_mask"),
        ("joint_velocity_xyz", "joint_velocity_valid_mask"),
        ("joint_acceleration_xyz", "joint_acceleration_valid_mask"),
        ("joint_jerk_magnitude", "joint_jerk_valid_mask"),
        ("joint_angles_rad", "joint_angle_valid_mask"),
        ("joint_angular_velocity_rad_s", "joint_angular_velocity_valid_mask"),
        ("bone_vectors_xyz", "bone_valid_mask"),
        ("segment_distances", "segment_distance_valid_mask"),
        ("bilateral_angle_difference_rad", "bilateral_angle_valid_mask"),
        ("bilateral_speed_difference", "bilateral_speed_valid_mask"),
        ("bilateral_mirror_distance", "bilateral_mirror_valid_mask"),
        ("quaternion_angular_speed_rad_s", "quaternion_angular_speed_valid_mask"),
    )

    @classmethod
    def _validate_features(
        cls,
        entry: dict[str, Any],
        payload: Any,
        frames: int,
        feature_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Check one sample's feature arrays against their declared contracts.

        Three things are checked, because each has silently produced wrong
        datasets elsewhere: a declared array that is simply not there, an array
        whose dtype is not what the spec says it is, and a validity mask that
        disagrees with its own array's NaN pattern.
        """
        sample_id = entry["sample_id"]
        problems: list[dict[str, Any]] = []
        stored = set(payload.files) if hasattr(payload, "files") else set(payload)

        for feature_id in feature_ids:
            definition = get_feature(feature_id)
            for contract in definition.arrays:
                if contract.key not in stored:
                    problems.append(
                        {
                            "sample_id": sample_id,
                            "issue": "feature_array_missing",
                            "feature_id": feature_id,
                            "array": contract.key,
                        }
                    )
                    continue
                array = np.asarray(payload[contract.key])
                if str(array.dtype) != contract.dtype:
                    problems.append(
                        {
                            "sample_id": sample_id,
                            "issue": "feature_dtype_mismatch",
                            "array": contract.key,
                            "expected": contract.dtype,
                            "actual": str(array.dtype),
                        }
                    )
                if (
                    contract.time_alignment == "per_frame"
                    and array.ndim >= 1
                    and int(array.shape[0]) != frames
                ):
                    problems.append(
                        {
                            "sample_id": sample_id,
                            "issue": "feature_frame_count_mismatch",
                            "array": contract.key,
                            "expected": frames,
                            "actual": int(array.shape[0]),
                        }
                    )

        for value_key, mask_key in cls._MASK_PAIRS:
            if value_key not in stored or mask_key not in stored:
                continue
            values = np.asarray(payload[value_key])
            mask = np.asarray(payload[mask_key], dtype=bool)
            finite = np.isfinite(values)
            if finite.ndim > mask.ndim:
                finite = finite.all(axis=-1)
            if finite.shape != mask.shape or not np.array_equal(finite, mask):
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "feature_mask_nan_mismatch",
                        "array": value_key,
                        "mask": mask_key,
                    }
                )
        return problems

    @staticmethod
    def _validate_intervals(
        entry: dict[str, Any],
        payload: Any,
        frames: int,
        vocabulary: set[str],
    ) -> list[dict[str, Any]]:
        """Check one sample's intervals against the array actually written."""
        sample_id = entry["sample_id"]
        problems: list[dict[str, Any]] = []
        stored = np.asarray(payload["error_intervals"]).reshape(-1, 3)

        if stored.shape[0] != len(entry["error_intervals"]):
            problems.append(
                {
                    "sample_id": sample_id,
                    "issue": "interval_count_mismatch",
                    "expected": len(entry["error_intervals"]),
                    "actual": int(stored.shape[0]),
                }
            )

        for position, interval in enumerate(entry["error_intervals"]):
            rel_start = int(interval["relative_start"])
            rel_end = int(interval["relative_end"])
            if rel_end < rel_start:
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "interval_reversed",
                        "interval_id": interval["interval_id"],
                    }
                )
            if rel_start < 0 or rel_end >= frames:
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "interval_out_of_array",
                        "interval_id": interval["interval_id"],
                        "detail": f"[{rel_start}, {rel_end}] vs T={frames}",
                    }
                )
            # Absolute and relative bounds must describe the same span.
            if (
                interval["start_position"] - entry["start_position"] != rel_start
                or interval["end_position"] - entry["start_position"] != rel_end
            ):
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "interval_relative_absolute_mismatch",
                        "interval_id": interval["interval_id"],
                    }
                )
            if interval["error_code"] not in vocabulary:
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "interval_unknown_class",
                        "interval_id": interval["interval_id"],
                        "detail": interval["error_code"],
                    }
                )
            if position < stored.shape[0]:
                row = stored[position]
                if (
                    int(row[1]) != rel_start
                    or int(row[2]) != rel_end
                    or int(row[0]) != int(interval["class_index"])
                ):
                    problems.append(
                        {
                            "sample_id": sample_id,
                            "issue": "interval_array_manifest_mismatch",
                            "interval_id": interval["interval_id"],
                        }
                    )

        if "error_multi_hot" in payload:
            multi_hot = np.asarray(payload["error_multi_hot"])
            if multi_hot.shape[0] != frames:
                problems.append(
                    {
                        "sample_id": sample_id,
                        "issue": "interval_target_length_mismatch",
                        "expected": frames,
                        "actual": int(multi_hot.shape[0]),
                    }
                )
            else:
                expected_on = sum(
                    i["relative_end"] - i["relative_start"] + 1
                    for i in entry["error_intervals"]
                )
                if expected_on and not multi_hot.any():
                    problems.append(
                        {
                            "sample_id": sample_id,
                            "issue": "interval_target_empty",
                        }
                    )
        return problems

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
