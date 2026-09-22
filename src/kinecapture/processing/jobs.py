"""Restartable processing transactions with exact source coverage and provenance.

Every attempt has a unique directory. Only an atomically renamed, complete run
is consumable by annotation. Restart replays from the beginning so tracker
history is reconstructed; partial results are never appended to or overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field, replace
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
import os
import time
import uuid
import threading
import numpy as np

from kinecapture import APP_VERSION, SKELETON_STREAM_SCHEMA_VERSION
from kinecapture.capture.subject_lock import SubjectLock
from kinecapture.core.fingerprint import hash_file, hash_payload, checksum_manifest
from kinecapture.core.ids import utc_now_iso
from kinecapture.core.jsonio import read_json, read_jsonl, write_json, JsonlWriter
from kinecapture.core.paths import long_path, ensure_dir, path_exists
from kinecapture.dataset.workspace import TakePaths
from kinecapture.domain.project import CaptureProfile, Take
from kinecapture.features.base import SourceField
from kinecapture.features.compute import FeatureContext, compute_features, FEATURE_FUNCTIONS, column_names
from kinecapture.recording.take_writer import ProxyVideoWriter
from kinecapture.recording.rgbd_archive import encode_depth_chunk, write_chunk, DEPTH_MAGIC, DepthCodec
from .arrays import write_arrays
from .floor import FloorPlane, detect_floor
from .sources import open_source
from .summary import (
    FLAG_CAPTURE_UNMATCHED,
    FLAG_INTEGRITY_ISSUE,
    FLAG_SUBJECT_AMBIGUOUS,
    build_summary,
)
from .thumbnails import DEFAULT_THUMBNAIL_COUNT, build_thumbnails

#: 1.1.0 is additive to the *consumer* contract and a change to the on-disk one:
#: arrays are now one memory-mappable ``.npy`` each instead of a single
#: compressed ``arrays.npz``, and a version also carries a timeline summary and
#: preview images. ``ReviewDataset`` reads both layouts, so every run produced
#: by 1.0.0 stays openable; nothing is migrated and nothing is rewritten.
#: 1.2.0 adds the ``floor_plane`` block: the plane the SDK measured, the
#: reference space it is expressed in, and - when it could not be measured -
#: the reason. Additive. A 1.1.0 run has no block, which reads as "nothing was
#: measured" rather than as a missing floor, and every existing reader is
#: unaffected.
#: 1.3.0 adds the ``subject_coverage`` block: how many of the processed frames
#: the chosen person was actually tracked in, beside the existing source-frame
#: coverage. Additive. The two were being reported under one sentence, so a
#: version that matched 1473 of 1475 source frames and held the subject in 622
#: of them said only "kaynak kapsamı doğrulanamadı". A 1.2.0 run has no block;
#: readers fall back to the run's own ``features.json``, which has always
#: carried the counters.
PROCESSING_SCHEMA_VERSION = "1.3.0"

#: How many frames the floor step may keep asking over. The SDK will not
#: answer until positional tracking reports OK, which is never true before the
#: first grab; measured on a real ZED recording it answers on the first frame
#: that is, in 0.3 s. The window is for a camera that needs longer to settle,
#: and it is small because a viewing aid must not slow down processing.
FLOOR_AFTER_FRAMES = 30

#: Issues that make a version unusable, as opposed to imperfect.
#:
#: Every issue is measured, written into ``job.json`` and shown on the library
#: screen. Only these hide the version, because only these mean the annotator
#: would be working against something that is wrong rather than something that
#: is incomplete. The 16 September takes are why the distinction exists: 521 of
#: 524 recorded frames matched the replayed source, every artefact was written
#: and verified, and the version still spent its life in a dot-prefixed staging
#: folder that no screen lists and no reader opens.
BLOCKING_ISSUES = frozenset({
    #: Nothing was decoded. There is no version, only an empty folder.
    "source_empty",
    #: Frame position is the annotation contract. If positions are not
    #: 0, 1, 2, ... then a label boundary does not identify a frame.
    "source_position_discontinuity",
    #: A proxy holding a different number of frames than the version would put
    #: picture N in front of someone labelling frame M.
    "review_proxy_desynchronised",
})

#: Frames to ignore before quoting a rate. The first inferences pay for model
#: warm-up, and an estimate built from them is wrong in the direction that
#: annoys people most - too pessimistic, then silently "early".
_RATE_WARMUP_FRAMES = 20

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
    #: Preview images for the library screen. Generated from the review proxy
    #: after it is closed, so a list never decodes video while it scrolls.
    thumbnail_count: int = DEFAULT_THUMBNAIL_COUNT
    #: ``tracker_joint_positions_2d`` is in the default set because the
    #: labelling screen draws the skeleton over the review video, and pixels
    #: cannot be recovered from 3D without the intrinsics the raw source may
    #: not carry. It is a raw passthrough - NaN when the tracker has none - so
    #: a run that cannot produce it still completes, and the screen then says
    #: the overlay is unavailable instead of inventing one.
    feature_ids: tuple[str, ...] = (
        "validity_masks",
        "frame_timing",
        "joint_angles_degrees",
        "tracker_joint_positions_2d",
    )
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


#: Optional tracker fields a body may carry, as ``BodyPose`` attribute ->
#: :class:`SourceField` key. Processing holds the selected bodies in memory, so
#: these are stacked directly instead of re-reading the skeleton stream.
_OPTIONAL_BODY_FIELDS: tuple[tuple[str, str], ...] = (
    ("joint_orientations", SourceField.JOINT_ORIENTATIONS.value),
    ("joint_positions_2d", SourceField.JOINT_POSITIONS_2D.value),
    ("joint_position_covariances", SourceField.JOINT_POSITION_COVARIANCES.value),
    ("local_joint_positions_xyz", SourceField.LOCAL_JOINT_POSITIONS.value),
    ("root_position", SourceField.ROOT_POSITION.value),
    ("root_orientation", SourceField.ROOT_ORIENTATION.value),
    ("tracker_root_velocity_xyz", SourceField.ROOT_VELOCITY.value),
    ("root_position_covariance", SourceField.ROOT_POSITION_COVARIANCE.value),
)


def _optional_body_arrays(selected: Sequence[Any]) -> dict[str, Optional[np.ndarray]]:
    """Stack each optional tracker field over frames, or report it absent.

    A field is ``None`` when *no* frame carried it - the tracker or the body
    format simply does not produce it, and the feature that wants it then says
    so with a reason. When some frames have it, the array is written with NaN
    in the frames that do not, so a gap stays a gap instead of being filled in.
    """
    arrays: dict[str, Optional[np.ndarray]] = {}
    for attribute, key in _OPTIONAL_BODY_FIELDS:
        sample = next(
            (getattr(b, attribute) for b in selected
             if b is not None and getattr(b, attribute) is not None),
            None,
        )
        if sample is None:
            arrays[key] = None
            continue
        template = np.asarray(sample, dtype=np.float32)
        stacked = np.full((len(selected), *template.shape), np.nan, dtype=np.float32)
        for index, body in enumerate(selected):
            value = getattr(body, attribute, None) if body is not None else None
            if value is not None:
                candidate = np.asarray(value, dtype=np.float32)
                if candidate.shape == template.shape:
                    stacked[index] = candidate
        arrays[key] = stacked
    return arrays


def source_identity(paths: TakePaths, take: Take) -> dict:
    raw = Path(long_path(paths.raw_dir))
    files = {p.relative_to(raw).as_posix(): {"sha256": hash_file(p), "bytes": p.stat().st_size}
             for p in sorted(raw.rglob("*")) if p.is_file()}
    if not files:
        raise ValueError("No immutable raw source")
    return {"files": files, "fingerprint": hash_payload(files), "origin": take.origin.value,
            "capture_provenance": take.camera_info.to_dict() if take.camera_info else None}


def _anchor_is_due(anchor, packet, *, first_frame: bool) -> bool:
    """Whether this anchor is the operator's answer for this frame.

    An exact timestamp match is the normal case. The exception is an anchor
    taken while the preview was running, *before* record was pressed - which
    is when picking the subject actually happens. Both 16 September takes
    carry one, 3.7 s and 1.6 s ahead of their first recorded frame. Discarding
    them produced a version whose joint arrays were NaN from end to end, with
    ``subject_anchor_outside_source`` as the only explanation. Such an anchor
    is applied to the first recorded frame instead, still has to pass the same
    containment test against a real body, and the offset is written down.
    """
    anchor_us = anchor["camera_timestamp_ns"] // 1000
    frame_us = packet.camera_timestamp_ns // 1000
    return anchor_us == frame_us or (first_frame and anchor_us < frame_us)


def _associate_anchor(packet, anchors, lock, spec, issues, applied, *, first_frame=False):
    for index, anchor in enumerate(anchors):
        if index in applied or not _anchor_is_due(anchor, packet, first_frame=first_frame):
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
        method = "source_image_anchor"
        if not candidates and len(packet.bodies) == 1:
            # One person in the frame leaves the click nothing else to mean.
            # Given its own method name so the provenance never claims the
            # stricter containment test was the thing that passed.
            candidates = list(packet.bodies)
            method = "sole_body_in_frame"
        offset_ms = (packet.camera_timestamp_ns - anchor["camera_timestamp_ns"]) / 1e6
        # Compared at microsecond resolution, the same grain the match uses.
        # The SVO stores timestamps in microseconds and replays them with the
        # last three digits zeroed, so an exact match still differs by a few
        # hundred nanoseconds - which is not an anchor taken before recording.
        preroll = anchor["camera_timestamp_ns"] // 1000 < packet.camera_timestamp_ns // 1000
        if len(candidates) == 1:
            if preroll:
                method += "_preroll"
                issues.add("subject_anchor_before_recording")
            lock.select(candidates[0], frame_index=packet.source_position,
                        timestamp_ns=packet.camera_timestamp_ns, spec=spec, method=method)
        else:
            issues.add("subject_anchor_unresolved")
            lock.clear()
            method = "unresolved"
        applied[index] = {"anchor": index, "position": packet.source_position,
                          "method": method, "offset_ms": round(offset_ms, 3)}
    return lock.update(packet.bodies, frame_index=packet.source_position,
                       timestamp_ns=packet.camera_timestamp_ns).to_record()


class Cancelled(Exception):
    pass


def _mean_confidence(body) -> float:  # noqa: ANN001 - Optional[BodyPose]
    """Mean joint confidence for one frame, or NaN when nothing was measured.

    NaN rather than 0.0: a frame where the subject was not found has *no*
    confidence, and painting that as zero confidence would tell the annotator
    the tracker did badly when in fact it said nothing at all.
    """
    if body is None:
        return float("nan")
    values = np.asarray(body.joint_confidences, dtype=np.float32)
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if finite.size else float("nan")


def process_take(take_dir: Path, config: Optional[ProcessingConfig] = None, *,
                 cancel: Optional[threading.Event] = None, pause: Optional[threading.Event] = None,
                 output_root: Optional[Path] = None,
                 source_factory: Callable = open_source, restart_of: Optional[str] = None) -> Path:
    """Process one take into a new versioned directory.

    ``pause`` is held rather than cancelled: a new live recording needs the GPU
    back, but throwing away twenty minutes of completed replay to get it would
    be an expensive way to free a resource. Pausing stops at a frame boundary
    with every stream still open, and resumes where it stopped.
    """
    config = config or ProcessingConfig()
    cancel = cancel or threading.Event()
    pause = pause or threading.Event()
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
           # When this attempt started. Several versions of one take share the
           # take's own timestamp, so without this a list of them can only be
           # sorted by the random hex in the folder name.
           "created_at": utc_now_iso(),
           "state": "running", "restart_of": restart_of, "parameters": parameters,
           "source": source, "calibration_override_sha256": calibration_hash,
           "frames_processed": 0, "paused": False, "rate_fps": None, "eta_s": None,
           "paused_s": 0.0}
    write_json(stage / "job.json", job)
    started = time.perf_counter()
    issues: set[str] = set()
    stream = mapping = proxy = reader = None
    positions, timestamps, selected = [], [], []
    source_mapping = []
    matched_capture = set()
    lock = SubjectLock()
    #: Anchor index -> where it landed and how. Written into the job file so a
    #: reader can see which frame the subject choice actually came from.
    anchors_applied: dict[int, dict[str, Any]] = {}
    depth_buffer, depth_positions = [], []
    depth_chunks = []
    # Per-frame signals for the timeline summary, collected as we go so the
    # pyramid costs one pass rather than a second read of everything.
    frame_flags: list[int] = []
    frame_confidence: list[float] = []
    rate = {"frames": 0, "since": started, "paused_total": 0.0}

    def progress() -> dict[str, Any]:
        """Real progress only. A percentage is quoted when the total is known.

        When the source never declared a frame count there is no honest
        denominator, so none is invented: the caller is given the processed
        count and ``total = None`` and says "işlenen N kare" instead.
        """
        done = len(positions)
        total = job.get("source_frames_declared")
        elapsed = time.perf_counter() - started - rate["paused_total"]
        measured = done - rate["frames"]
        window = time.perf_counter() - rate["since"]
        fps = (measured / window) if measured >= _RATE_WARMUP_FRAMES and window > 0 else None
        remaining = (int(total) - done) if isinstance(total, int) and total > done else None
        return {
            "frames_processed": done,
            "source_frames_declared": total,
            "elapsed_s": elapsed,
            "paused_s": rate["paused_total"],
            "rate_fps": fps,
            "eta_s": (remaining / fps) if (fps and remaining is not None) else None,
        }

    def checkpoint():
        job.update(issues=sorted(issues), **progress())
        write_json(stage / "job.json", job, overwrite=True)

    def check_cancel():
        if cancel.is_set():
            raise Cancelled("Processing cancelled")

    def wait_while_paused():
        """Hold at a frame boundary while ``pause`` is set.

        Cancelling wins over pausing: a paused job that is then cancelled must
        not sit here waiting for a resume that is never coming.
        """
        if not pause.is_set():
            return
        began = time.perf_counter()
        job.update(state="paused", paused=True, **progress())
        write_json(stage / "job.json", job, overwrite=True)
        while pause.is_set() and not cancel.is_set():
            pause.wait(0.1)
        rate["paused_total"] += time.perf_counter() - began
        # The rate window restarts: time spent paused is not time spent working,
        # and folding it in would quote an estimate nobody should trust.
        rate["frames"], rate["since"] = len(positions), time.perf_counter()
        job.update(state="running", paused=False, **progress())
        write_json(stage / "job.json", job, overwrite=True)
        check_cancel()

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
        # The floor is asked for a little later - see FLOOR_AFTER_FRAMES. The
        # SDK answers only once positional tracking reports OK, which it does
        # not before any frame has been grabbed: asking here returned
        # "not_found" on a recording whose floor is found on frame 0.
        floor = FloorPlane()
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
                       "source_fingerprint": source["fingerprint"], "matching": "camera timestamp floor(ns/1000); rows sharing a microsecond are claimed in acquisition order; no nearest or positional fallback"})
        if config.store_proxy:
            proxy = ProxyVideoWriter(stage / "proxy.mp4", fps=processing_info.target_fps, target_width=config.proxy_width)
        for packet in reader:
            check_cancel()
            wait_while_paused()
            if not floor.is_measured and len(positions) < FLOOR_AFTER_FRAMES:
                # Once tracking has settled, and only until it answers. On a
                # real recording this succeeds on the first attempt and costs
                # 0.3 s; the window exists for a camera that needs a moment.
                floor = detect_floor(getattr(reader, "backend", None))
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
            association = _associate_anchor(packet, anchors, lock, spec, issues,
                                            anchors_applied, first_frame=not positions)
            subject = next((b for b in packet.bodies if b.tracking_id == association.get("tracker_id")), None)
            matches = capture_by_time.get(packet.camera_timestamp_ns // 1000, [])
            if len(matches) > 1:
                # The camera stamped two consecutive frames with the same
                # microsecond - once in 524 frames and twice in 1648 on
                # 16 September. Refusing to match either of them threw away
                # both frames' coverage and called an ambiguity something that
                # order resolves: capture rows and replayed frames are each in
                # acquisition order, so the first unclaimed row is this one.
                issues.add("capture_timestamp_duplicated")
            captured = next((row for row in matches if row["i"] not in matched_capture), None)
            if captured is None:
                issues.add("source_capture_timestamp_unmatched_or_ambiguous")
            else:
                matched_capture.add(captured["i"])
            # Per-frame timeline signals. Recorded here because this is the only
            # place that sees the packet; deriving them later would mean reading
            # the whole skeleton stream back.
            flags = 0
            if captured is None:
                flags |= FLAG_CAPTURE_UNMATCHED
            if packet.integrity_issues:
                flags |= FLAG_INTEGRITY_ISSUE
            if association.get("state") in ("ambiguous", "reidentifying", "temporarily_lost"):
                flags |= FLAG_SUBJECT_AMBIGUOUS
            frame_flags.append(flags)
            frame_confidence.append(_mean_confidence(subject))
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
            if proxy.unavailable_reason:
                # No scrub video. The review screen says so; the skeleton, the
                # arrays and the previews are untouched by it.
                issues.add("review_proxy_unavailable")
            elif proxy.frames_written != len(positions):
                issues.add("review_proxy_desynchronised")
            proxy = None
        if not positions:
            issues.add("source_empty")
        elif expected_count != len(positions):
            issues.add("source_frame_count_mismatch")
        for index in range(len(anchors)):
            if index not in anchors_applied:
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
            # Optional tracker fields were being dropped here: without them the
            # raw-passthrough features could only ever emit NaN, so a run that
            # really did have 2D joints reported it as "not produced".
            present = np.array([b is not None for b in selected])
            context = FeatureContext(spec, joints, stamps, indices, processing_info.target_fps,
                confidences=confidences, raw=_optional_body_arrays(selected),
                body_present=present)
            features = compute_features(context, config.feature_ids)
            # One uncompressed .npy per array: a review screen reads the window
            # it is showing instead of decompressing the whole session (1.1.0).
            job["arrays"] = write_arrays(stage, {
                "joints": joints, "confidences": confidences,
                "source_positions": indices, "camera_timestamps_ns": stamps,
                "subject_present": present, **features.arrays})
            write_json(stage / "features.json", {"schema_version": "1.0.0", "feature_ids": list(config.feature_ids),
                "availability": features.availability_dict(), "reasons": features.reasons,
                "columns": column_names(spec), "subject_association": lock.provenance()})
            write_json(stage / "skeleton_spec.json", spec.to_dict())
            job["summary"] = build_summary(
                stage, present=present,
                confidence=np.asarray(frame_confidence, dtype=np.float32),
                flags=np.asarray(frame_flags, dtype=np.uint8),
                fps=processing_info.target_fps)
        check_cancel()
        # Previews come last: the proxy has to be closed before it can be read,
        # and a failure here must not cost the version that is already written.
        if config.thumbnail_count and positions:
            job["thumbnails"] = build_thumbnails(
                stage, stage / "proxy.mp4", len(positions), count=config.thumbnail_count)
        matched = len(matched_capture)
        # Coverage as numbers, not as a verdict. "521 of 524 frames matched"
        # is something an operator can weigh; "kapsam doğrulanamadı" is not.
        job["coverage"] = {
            "capture_frames": len(capture_rows),
            "matched_frames": matched,
            "unmatched_frames": len(capture_rows) - matched,
            "source_frames": len(positions),
            "declared_source_frames": expected_count,
            "matched_ratio": (matched / len(capture_rows)) if capture_rows else None,
        }
        job["subject_anchors"] = [anchors_applied[i] for i in sorted(anchors_applied)]
        # How much of the recording actually has the chosen person in it. A
        # different question from how much of the raw source was found again,
        # and the one an annotator is about to spend an hour on.
        counters = lock.provenance().get("counters", {})
        tracked = sum(1 for body in selected if body is not None)
        job["subject_coverage"] = {
            "frames": len(selected),
            "tracked_frames": tracked,
            "locked_frames": int(counters.get("locked_frames", 0)),
            "ambiguous_frames": int(counters.get("ambiguous_frames", 0)),
            "lost_frames": int(counters.get("lost_frames", 0)),
            "recoveries": int(counters.get("recoveries", 0)),
            "reassociations": int(counters.get("reassociations", 0)),
            "multi_person_frames": int(counters.get("multi_person_frames", 0)),
            "tracked_ratio": (tracked / len(selected)) if selected else None,
        }
        # Whatever the floor step concluded, including that it could not. A
        # plane found in camera space is a world floor only while the camera
        # is still, so what the recording did is recorded beside it.
        job["floor_plane"] = replace(
            floor, camera_moved=None if not positions else False
        ).to_dict()
        blocking = sorted(issues & BLOCKING_ISSUES)
        job.update(state="partial" if issues else "complete", issues=sorted(issues),
                   blocking_issues=blocking, published=not blocking,
                   subject_status="associated" if any(b is not None for b in selected) else "needs_subject_selection",
                   depth_chunks=depth_chunks, capture_frames_unmatched=len(capture_rows)-matched)
        gaps = np.diff(np.asarray(timestamps, dtype=np.int64)) / 1e6
        job["timestamp_qc"] = {"max_gap_ms": float(gaps.max()) if gaps.size else None,
                               "gap_std_ms": float(gaps.std()) if gaps.size else None,
                               "gaps_over_1_5_intervals": int((gaps > 1500/processing_info.target_fps).sum())}
        checkpoint()
        manifest = checksum_manifest({p.relative_to(Path(long_path(stage))).as_posix(): p
            for p in Path(long_path(stage)).rglob("*") if p.is_file() and p.name != "checksums.json"})
        write_json(stage / "checksums.json", manifest)
        # Publication is decided by usability, not by perfection. A version
        # that carries recorded caveats is still a version; one that cannot be
        # annotated correctly stays in staging, where nothing will open it.
        if not blocking:
            os.rename(long_path(stage), long_path(final))
            return final
        return stage
    except (Cancelled, KeyboardInterrupt) as exc:
        job.update(state="cancelled", published=False, error=str(exc))
    except Exception as exc:
        job.update(state="failed", published=False, error=f"{type(exc).__name__}: {exc}")
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
