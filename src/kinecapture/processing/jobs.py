"""Restartable processing transactions with exact source coverage and provenance.

Every attempt has a unique directory. Only an atomically renamed, complete run
is consumable by annotation. Restart replays from the beginning so tracker
history is reconstructed; partial results are never appended to or overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Optional
import os
import time
import uuid
import threading
import numpy as np

from kinecapture import APP_VERSION, SKELETON_STREAM_SCHEMA_VERSION
from kinecapture.capture.subject_lock import SubjectLock
from kinecapture.core.fingerprint import hash_file, hash_payload, checksum_manifest
from kinecapture.core.jsonio import read_json, read_jsonl, write_json, JsonlWriter
from kinecapture.core.paths import long_path, ensure_dir, path_exists
from kinecapture.dataset.workspace import TakePaths
from kinecapture.domain.project import CaptureProfile, Take
from kinecapture.features.compute import FeatureContext, compute_features, FEATURE_FUNCTIONS, column_names
from kinecapture.recording.take_writer import ProxyVideoWriter
from kinecapture.recording.rgbd_archive import encode_depth_chunk, write_chunk, DEPTH_MAGIC, DepthCodec
from .sources import open_source

PROCESSING_SCHEMA_VERSION = "1.0.0"

@dataclass(frozen=True)
class ProcessingConfig:
    body_format: str = "BODY_38"
    body_model: str = "HUMAN_BODY_ACCURATE"
    depth_mode: str = "NEURAL_PLUS"
    body_fitting: bool = True
    allow_reduced_precision_inference: bool = False
    confidence_threshold: int = 40
    store_depth: bool = True
    store_proxy: bool = True
    compute_body: bool = True
    proxy_width: int = 640
    feature_ids: tuple[str, ...] = ("validity_masks", "frame_timing", "joint_angles_degrees")
    # Optional SDK OpenCV calibration override is identified by content, not just path.
    calibration_file: Optional[str] = None
    subject_anchors: tuple[dict, ...] = ()

    def profile(self, take: Take) -> CaptureProfile:
        unknown = set(self.feature_ids) - FEATURE_FUNCTIONS.keys()
        if unknown:
            raise ValueError(f"Unknown feature IDs: {sorted(unknown)}")
        return CaptureProfile(fps=take.capture_profile.fps, resolution=take.capture_profile.resolution,
            body_format=self.body_format, body_tracking_model=self.body_model,
            depth_mode=self.depth_mode, enable_body_fitting=self.body_fitting,
            allow_reduced_precision_inference=self.allow_reduced_precision_inference,
            detection_confidence=self.confidence_threshold, enable_depth=self.store_depth,
            enable_body_tracking=self.compute_body, store_skeleton=self.compute_body,
            store_proxy=self.store_proxy, preview_enabled=False, proxy_video_width=self.proxy_width,
            coordinate_system=take.capture_profile.coordinate_system,
            length_unit=take.capture_profile.length_unit, calibration_file=self.calibration_file)


def source_identity(paths: TakePaths, take: Take) -> dict:
    raw = Path(long_path(paths.raw_dir))
    files = {p.relative_to(raw).as_posix(): {"sha256": hash_file(p), "bytes": p.stat().st_size}
             for p in sorted(raw.rglob("*")) if p.is_file()}
    if not files:
        raise ValueError("No immutable raw source")
    return {"files": files, "fingerprint": hash_payload(files), "origin": take.origin.value,
            "capture_provenance": take.camera_info.to_dict() if take.camera_info else None}


def _associate_anchor(packet, anchors, lock, spec, issues):
    for anchor in anchors:
        if anchor["camera_timestamp_ns"] // 1000 != packet.camera_timestamp_ns // 1000:
            continue
        x, y = anchor["point_xy"]
        candidates = []
        for body in packet.bodies:
            points = body.joint_positions_2d
            if points is None:
                continue
            finite = points[np.isfinite(points).all(axis=1)]
            if len(finite) and (finite.min(axis=0) <= [x,y]).all() and (finite.max(axis=0) >= [x,y]).all():
                candidates.append(body)
        if len(candidates) == 1:
            lock.select(candidates[0], frame_index=packet.source_position,
                        timestamp_ns=packet.camera_timestamp_ns, spec=spec, method="source_image_anchor")
        else:
            issues.add("subject_anchor_unresolved")
            lock.clear()
    return lock.update(packet.bodies, frame_index=packet.source_position,
                       timestamp_ns=packet.camera_timestamp_ns).to_record()


class Cancelled(Exception):
    pass


def process_take(take_dir: Path, config: Optional[ProcessingConfig] = None, *,
                 cancel: Optional[threading.Event] = None, output_root: Optional[Path] = None,
                 source_factory: Callable = open_source, restart_of: Optional[str] = None) -> Path:
    config = config or ProcessingConfig()
    cancel = cancel or threading.Event()
    paths = TakePaths(Path(take_dir).resolve())
    take = Take.from_dict(read_json(paths.metadata))
    if take.state.value == "recording":
        raise ValueError("Recording must be closed before offline processing")
    profile = config.profile(take)
    source = source_identity(paths, take)
    parameters = asdict(config)
    calibration_hash = hash_file(Path(config.calibration_file)) if config.calibration_file else None
    anchors = read_json(paths.raw_dir / "subject_anchors.json") if path_exists(paths.raw_dir / "subject_anchors.json") else []
    if config.subject_anchors:
        anchors = list(config.subject_anchors)
    for anchor in anchors:
        if len(anchor.get("point_xy", [])) != 2 or not np.isfinite(anchor["point_xy"]).all():
            raise ValueError("Subject anchor needs a finite source-image point")
        if "camera_timestamp_ns" not in anchor:
            raise ValueError("Subject anchor needs a source timestamp")
    # Legacy sources carry only live skeleton timestamps. Never invent offset N-1.
    index_path = paths.raw_index if path_exists(paths.raw_index) else paths.skeleton_stream
    capture_rows = [r for r in read_jsonl(index_path, strict=True) if r.get("record") == "frame"] if path_exists(index_path) else []
    capture_by_time: dict[int, list[dict]] = {}
    for row in capture_rows:
        capture_by_time.setdefault(int(row["cam_ns"]) // 1000, []).append(row)
    base = Path(output_root).resolve() if output_root else paths.derived_dir / "processing"
    if base == paths.raw_dir or paths.raw_dir in base.parents:
        raise ValueError("Derived output may not be written under raw/")
    ensure_dir(base)
    run_id = "run_" + uuid.uuid4().hex[:16]
    stage = base / ("." + run_id + ".partial")
    final = base / run_id
    os.mkdir(long_path(stage))
    job = {"schema_version": PROCESSING_SCHEMA_VERSION, "app_version": APP_VERSION,
           "run_id": run_id, "take_id": take.take_id, "take_dir": str(paths.root),
           "state": "running", "restart_of": restart_of, "parameters": parameters,
           "source": source, "calibration_override_sha256": calibration_hash, "frames_processed": 0}
    write_json(stage / "job.json", job)
    started = time.perf_counter()
    issues: set[str] = set()
    stream = mapping = proxy = reader = None
    positions, timestamps, selected = [], [], []
    source_mapping = []
    matched_capture = set()
    lock = SubjectLock()
    depth_buffer, depth_positions = [], []
    depth_chunks = []

    def checkpoint():
        job.update(frames_processed=len(positions), elapsed_s=time.perf_counter()-started,
                   issues=sorted(issues))
        write_json(stage / "job.json", job, overwrite=True)

    def check_cancel():
        if cancel.is_set():
            raise Cancelled("Processing cancelled")

    def flush_depth():
        if not depth_buffer:
            return
        header, payload = encode_depth_chunk(np.stack(depth_buffer), DepthCodec.FLOAT32_LOSSLESS)
        header.update(positions=list(depth_positions), stream="depth", chunk_index=len(depth_chunks))
        directory = ensure_dir(stage / "depth")
        destination = directory / f"depth_{len(depth_chunks):06d}.kcd"
        write_chunk(destination, DEPTH_MAGIC, header, payload)
        depth_chunks.append(destination.name)
        depth_buffer.clear()
        depth_positions.clear()

    try:
        check_cancel()
        reader = source_factory(paths, take, profile)
        processing_info = reader.info
        expected_count = reader.expected_count
        job["processing_camera"] = processing_info.to_dict()
        job["source_frames_declared"] = expected_count
        spec = reader.spec
        job["skeleton_format"] = spec.name if spec else None
        if take.origin.value == "real":
            calibration = processing_info.extra.get("left_camera_calibration") or {}
            if not all(np.isfinite(calibration.get(k, np.nan)) and calibration.get(k, 0) > 0 for k in ("fx", "fy")):
                issues.add("calibration_invalid_or_missing")
        stream = JsonlWriter(stage / "skeleton.jsonl")
        mapping = JsonlWriter(stage / "source_map.jsonl")
        header = {"record": "header", "schema_version": SKELETON_STREAM_SCHEMA_VERSION,
                  "skeleton_format": spec.name if spec else "", "run_id": run_id,
                  "source_fingerprint": source["fingerprint"], "coordinate_system": processing_info.coordinate_system,
                  "length_unit": processing_info.length_unit, "target_fps": processing_info.target_fps}
        stream.write(header)
        mapping.write({"record": "header", "schema_version": PROCESSING_SCHEMA_VERSION,
                       "source_fingerprint": source["fingerprint"], "matching": "unique camera timestamp floor(ns/1000); no nearest or positional fallback"})
        if config.store_proxy:
            proxy = ProxyVideoWriter(stage / "proxy.mp4", fps=processing_info.target_fps, target_width=config.proxy_width)
        for packet in reader:
            check_cancel()
            pos = packet.source_position
            if pos is None or pos != len(positions):
                issues.add("source_position_discontinuity")
            if timestamps and packet.camera_timestamp_ns <= timestamps[-1]:
                issues.add("source_timestamp_non_monotonic")
            if timestamps and packet.camera_timestamp_ns - timestamps[-1] > 1.5e9 / processing_info.target_fps:
                issues.add("source_timestamp_gap")
            issues.update(packet.integrity_issues)
            if any(body.body_format != spec.name or body.num_joints != spec.num_joints for body in packet.bodies):
                raise ValueError("Body format/shape changed during processing")
            association = _associate_anchor(packet, anchors, lock, spec, issues)
            subject = next((b for b in packet.bodies if b.tracking_id == association.get("tracker_id")), None)
            matches = capture_by_time.get(packet.camera_timestamp_ns // 1000, [])
            captured = matches[0] if len(matches) == 1 else None
            if captured is None:
                issues.add("source_capture_timestamp_unmatched_or_ambiguous")
            else:
                matched_capture.add(captured["i"])
            row = {"record": "frame", "p": len(positions), "source_position": pos,
                   "cam_ns": packet.camera_timestamp_ns, "capture_frame_index": captured["i"] if captured else None,
                   "capture_timestamp_ns": captured["cam_ns"] if captured else None,
                   "proxy_position": len(positions) if proxy else None}
            mapping.write(row)
            source_mapping.append(row)
            stream.write({"record": "frame", "p": len(positions), "i": pos,
                          "source_position": pos, "cam_ns": packet.camera_timestamp_ns,
                          "host_ns": packet.host_timestamp_ns, "bodies": [b.to_record() for b in packet.bodies],
                          "subject": association, "integrity_issues": list(packet.integrity_issues)})
            if proxy:
                if packet.color_frame is None:
                    raise ValueError("Review proxy requested but RGB is absent")
                proxy.write(packet.color_frame)
            if config.store_depth:
                if packet.depth_frame is None:
                    issues.add("requested_depth_missing")
                else:
                    depth_buffer.append(packet.depth_frame)
                    depth_positions.append(pos)
                    if len(depth_buffer) >= 8:
                        flush_depth()
            positions.append(pos)
            timestamps.append(packet.camera_timestamp_ns)
            selected.append(subject)
            if len(positions) % 30 == 0:
                checkpoint()
        check_cancel()
        flush_depth()
        reader.close()
        reader = None
        stream.close()
        stream = None
        mapping.close()
        mapping = None
        if proxy:
            proxy.close()
            if proxy.unavailable_reason or proxy.frames_written != len(positions):
                issues.add("review_proxy_incomplete")
            proxy = None
        if not positions or expected_count != len(positions):
            issues.add("source_frame_count_mismatch")
        for anchor in anchors:
            if not any(ts // 1000 == anchor["camera_timestamp_ns"] // 1000 for ts in timestamps):
                issues.add("subject_anchor_outside_source")
        if len(matched_capture) != len(capture_rows):
            issues.add("capture_frames_unmatched")
        if source_identity(paths, take) != source:
            raise ValueError("Immutable raw source changed during processing")
        if config.calibration_file and hash_file(Path(config.calibration_file)) != calibration_hash:
            raise ValueError("Calibration changed during processing")
        if spec and positions:
            joints = np.full((len(positions), spec.num_joints, 3), np.nan, dtype=np.float32)
            confidences = np.full(joints.shape[:2], np.nan, dtype=np.float32)
            for i, body in enumerate(selected):
                if body is not None:
                    joints[i], confidences[i] = body.joint_positions_xyz, body.joint_confidences
            indices = np.asarray(positions, dtype=np.int64)
            stamps = np.asarray(timestamps, dtype=np.int64)
            context = FeatureContext(spec, joints, stamps, indices, processing_info.target_fps, confidences=confidences)
            features = compute_features(context, config.feature_ids)
            with open(long_path(stage / "arrays.npz"), "wb") as output:
                np.savez_compressed(output, joints=joints, confidences=confidences,
                    source_positions=indices, camera_timestamps_ns=stamps,
                    subject_present=np.array([b is not None for b in selected]),
                    **features.arrays)
            write_json(stage / "features.json", {"schema_version": "1.0.0", "feature_ids": list(config.feature_ids),
                "availability": features.availability_dict(), "reasons": features.reasons,
                "columns": column_names(spec), "subject_association": lock.provenance()})
            write_json(stage / "skeleton_spec.json", spec.to_dict())
        check_cancel()
        job.update(state="partial" if issues else "complete", issues=sorted(issues),
                   subject_status="associated" if any(b is not None for b in selected) else "needs_subject_selection",
                   depth_chunks=depth_chunks, capture_frames_unmatched=len(capture_rows)-len(matched_capture))
        gaps = np.diff(np.asarray(timestamps, dtype=np.int64)) / 1e6
        job["timestamp_qc"] = {"max_gap_ms": float(gaps.max()) if gaps.size else None,
                               "gap_std_ms": float(gaps.std()) if gaps.size else None,
                               "gaps_over_1_5_intervals": int((gaps > 1500/processing_info.target_fps).sum())}
        checkpoint()
        manifest = checksum_manifest({p.relative_to(Path(long_path(stage))).as_posix(): p
            for p in Path(long_path(stage)).rglob("*") if p.is_file() and p.name != "checksums.json"})
        write_json(stage / "checksums.json", manifest)
        if job["state"] == "complete":
            os.rename(long_path(stage), long_path(final))
            return final
        return stage
    except (Cancelled, KeyboardInterrupt) as exc:
        job.update(state="cancelled", error=str(exc))
    except Exception as exc:
        job.update(state="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        for owned in (stream, mapping, proxy, reader):
            if owned is not None:
                try:
                    owned.close()
                except Exception as exc:
                    job["close_error"] = str(exc)
    checkpoint()
    return stage


def restart_job(job_dir: Path, **kwargs) -> Path:
    old = read_json(Path(job_dir) / "job.json")
    paths = TakePaths(Path(old["take_dir"]))
    take = Take.from_dict(read_json(paths.metadata))
    if source_identity(paths, take) != old["source"]:
        raise ValueError("Restart refused: source fingerprint/provenance changed")
    return process_take(paths.root, ProcessingConfig(**old["parameters"]),
                        restart_of=old["run_id"], **kwargs)
