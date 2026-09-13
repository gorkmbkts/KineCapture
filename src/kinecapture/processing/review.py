"""SDK-free reader for a pinned processing version and canonical annotations."""
from pathlib import Path
import numpy as np

from kinecapture.core.jsonio import read_json, read_jsonl, write_json
from kinecapture.core.paths import long_path, ensure_dir
from kinecapture.core.fingerprint import verify_checksum_manifest
from kinecapture.playback.take_reader import load_skeleton_stream, ProxyVideoReader


class ReviewDataset:
    def __init__(self, directory: Path, *, verify: bool = True):
        self.directory = Path(directory)
        self.job = read_json(self.directory / "job.json")
        if self.job["state"] != "complete":
            raise ValueError("Only a complete processing version can be annotated")
        if verify and verify_checksum_manifest(read_json(self.directory / "checksums.json"), self.directory):
            raise ValueError("Derived checksum verification failed")
        self.mapping = [r for r in read_jsonl(self.directory / "source_map.jsonl", strict=True) if r.get("record") == "frame"]
        self.stream = load_skeleton_stream(self.directory / "skeleton.jsonl")
        self.video = None

    def open_video(self):
        self.video = ProxyVideoReader(self.directory / "proxy.mp4")
        return self.video

    def arrays(self):
        with open(long_path(self.directory / "arrays.npz"), "rb") as file:
            with np.load(file, allow_pickle=False) as archive:
                return {k: archive[k] for k in archive.files}

    def anchor_at(self, position: int) -> dict:
        if not 0 <= position < len(self.mapping):
            raise IndexError("Preview position outside source map")
        row = self.mapping[position]
        return {"source_fingerprint": self.job["source"]["fingerprint"],
                "source_position": row["source_position"], "camera_timestamp_ns": row["cam_ns"]}

    def position_of_anchor(self, anchor: dict) -> int:
        if anchor["source_fingerprint"] != self.job["source"]["fingerprint"]:
            raise ValueError("Annotation belongs to another raw source")
        matches = [i for i, row in enumerate(self.mapping)
                   if row["source_position"] == anchor["source_position"] and row["cam_ns"] == anchor["camera_timestamp_ns"]]
        if len(matches) != 1:
            raise ValueError("Canonical annotation boundary is not uniquely mapped")
        return matches[0]

    def save_annotations(self, samples: list[dict]) -> Path:
        """New sidecar contract; legacy segments.json is never migrated implicitly."""
        for sample in samples:
            start, end = (self.position_of_anchor(sample[k]) for k in ("start", "end"))
            if start > end:
                raise ValueError("Annotation interval is reversed")
            for interval in sample.get("errors", []):
                a, b = (self.position_of_anchor(interval[k]) for k in ("start", "end"))
                if not start <= a <= b <= end:
                    raise ValueError("Error interval is outside its movement sample")
        directory = ensure_dir(Path(self.job["take_dir"]) / "annotations" / "processing")
        target = directory / (self.job["run_id"] + ".json")
        write_json(target, {"schema_version": "1.0.0", "contract": "canonical_source_boundaries_inclusive",
                           "processing_run": self.job["run_id"], "samples": samples}, overwrite=True)
        return target

    def close(self):
        if self.video:
            self.video.close()
