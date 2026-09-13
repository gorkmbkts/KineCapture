"""Sequential sources; processing throughput never controls source frame selection."""
from pathlib import Path
from kinecapture.camera.zed import ZedCameraBackend
from kinecapture.camera.mock import MockCameraBackend
from kinecapture.core.jsonio import read_jsonl
from kinecapture.domain.models import FramePacket
from kinecapture.domain.enums import DataOrigin
from kinecapture.recording.rgbd_archive import RgbdArchiveReader


class SvoSource:
    def __init__(self, paths, take, profile):
        self.backend = ZedCameraBackend(profile, svo_path=paths.native_recording)
        self.info = self.backend.connect()
        self.expected_count = self.backend.source_frame_count
        self.spec = self.backend.skeleton_spec()
        self.backend.start_preview()

    def __iter__(self):
        while True:
            try:
                packet = self.backend.grab_frame()
            except EOFError:
                return
            if packet is None:
                raise RuntimeError("Offline source returned no frame without EOF")
            yield packet

    def close(self):
        self.backend.disconnect()


class SyntheticSource:
    """Replay stored colour and regenerate explicitly synthetic algorithm-v1 poses."""
    def __init__(self, paths, take, profile):
        if take.camera_info is None:
            raise ValueError("Synthetic replay requires camera provenance")
        info = take.camera_info
        extra = info.extra
        self.backend = MockCameraBackend(width=info.resolution[0], height=info.resolution[1],
            fps=info.target_fps, seed=extra["seed"], num_bodies=extra.get("num_bodies", 1),
            tracking_loss_every=extra.get("tracking_loss_every", 0),
            low_confidence_every=extra.get("low_confidence_every", 0), profile=profile)
        self.info = self.backend.connect()
        self.info.extra["processing_source"] = "synthetic_generator_v1; stored RGB used verbatim"
        self.spec = self.backend.skeleton
        self.rows = [r for r in read_jsonl(paths.raw_index, strict=True) if r.get("record") == "frame"]
        self.expected_count = len(self.rows)
        self.archive = RgbdArchiveReader(paths.rgbd_dir)
        self.profile = profile

    def __iter__(self):
        colors = iter(self.archive.iter_color())
        for row in self.rows:
            position, rgb = next(colors, (None, None))
            if position != row["p"]:
                raise ValueError("Synthetic raw colour coverage mismatch")
            index = row["i"]
            bodies = tuple(body for slot in range(self.backend._num_bodies)
                if (body := self.backend._render_body(index, slot)) is not None) if self.profile.computes_body else ()
            yield FramePacket(index, row["host_ns"], row["cam_ns"], rgb,
                depth_frame=self.backend._render_depth(index) if self.profile.retrieves_depth else None,
                bodies=bodies, source_position=position, source_resolution=self.info.resolution,
                origin=DataOrigin.SYNTHETIC)

    def close(self):
        self.backend.disconnect()


def open_source(paths, take, profile):
    return SyntheticSource(paths, take, profile) if take.origin is DataOrigin.SYNTHETIC else SvoSource(paths, take, profile)
