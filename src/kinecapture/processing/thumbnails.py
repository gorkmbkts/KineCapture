"""Small preview images, generated once at processing time.

The library screen shows a card per processed version. Decoding a frame out of
a proxy video while a list is scrolling is exactly the kind of work that turns
a smooth list into a stuttering one, so it is not done there: the images are
written next to the version, and the screen only reads files.

Three are guaranteed - first, middle, last - because those answer "did this
recording actually contain what I think it did?" on their own. The rest are
evenly spaced.

OpenCV is optional at runtime, the same way it is for the proxy writer: if it
is missing or cannot encode, the version is still complete and the reason is
recorded. A missing thumbnail is a degraded list, not lost data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np

from kinecapture.core.jsonio import read_json, write_json
from kinecapture.core.paths import ensure_dir, long_path, path_exists

logger = logging.getLogger(__name__)

THUMBNAIL_SCHEMA_VERSION = "1.0.0"
THUMBNAIL_DIRNAME = "thumbs"
THUMBNAIL_INDEX_FILE = "index.json"
DEFAULT_THUMBNAIL_COUNT = 12
DEFAULT_THUMBNAIL_WIDTH = 256


def planned_positions(frames: int, count: int = DEFAULT_THUMBNAIL_COUNT) -> list[int]:
    """Which frames to capture: always first, middle and last, then even spacing."""
    if frames <= 0:
        return []
    if frames == 1:
        return [0]
    wanted = max(3, int(count))
    positions = {0, frames // 2, frames - 1}
    positions.update(
        int(round(index * (frames - 1) / (wanted - 1))) for index in range(wanted)
    )
    return sorted(p for p in positions if 0 <= p < frames)


def build_thumbnails(
    directory: Path,
    video_path: Path,
    frames: int,
    *,
    count: int = DEFAULT_THUMBNAIL_COUNT,
    width: int = DEFAULT_THUMBNAIL_WIDTH,
) -> dict[str, Any]:
    """Write the previews for one version. Returns the index document.

    Each wanted frame is **seeked** to rather than decoded past. Measured on a
    302-frame proxy: 45 ms seeking against 92 ms decoding sequentially - and
    the gap only widens, because seeking costs one decode per preview while
    reading straight through costs one per frame in the file. On an hour-long
    proxy that is the difference between a fraction of a second and a minute.

    A seek can land a frame or two off in a codec with sparse keyframes. That
    is fine for a preview and is not hidden: the index records the position the
    decoder actually reported, not the one that was asked for.
    """
    wanted = planned_positions(frames, count)
    index: dict[str, Any] = {
        "schema_version": THUMBNAIL_SCHEMA_VERSION,
        "source": video_path.name,
        "width": int(width),
        "requested": wanted,
        "entries": [],
        "unavailable_reason": "",
    }
    if not wanted:
        index["unavailable_reason"] = "Kare yok."
        _write_index(directory, index)
        return index
    if not path_exists(video_path):
        index["unavailable_reason"] = "Önizleme videosu üretilmedi."
        _write_index(directory, index)
        return index

    try:
        import cv2  # noqa: PLC0415 - optional at runtime
    except ImportError as exc:  # pragma: no cover - opencv is present here
        index["unavailable_reason"] = f"opencv-python bulunamadı: {exc}"
        _write_index(directory, index)
        return index

    target = ensure_dir(Path(directory) / THUMBNAIL_DIRNAME)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        index["unavailable_reason"] = "Önizleme videosu açılamadı."
        _write_index(directory, index)
        return index

    entries: list[dict[str, Any]] = []
    missed = 0
    try:
        for requested in wanted:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(requested))
            landed = int(capture.get(cv2.CAP_PROP_POS_FRAMES))
            ok, frame = capture.read()
            if not ok or frame is None:
                missed += 1
                continue
            position = landed if landed >= 0 else requested
            name = f"t_{position:06d}.webp"
            if _write_image(cv2, target / name, frame, width):
                entries.append(
                    {
                        "position": int(position),
                        "requested": int(requested),
                        "file": f"{THUMBNAIL_DIRNAME}/{name}",
                    }
                )
            else:
                missed += 1
    finally:
        capture.release()

    index["entries"] = entries
    if missed:
        # Said out loud rather than passed off as a complete set: the proxy is
        # shorter or less seekable than the run claims, and someone should know.
        index["unavailable_reason"] = f"{missed} önizleme üretilemedi."
    _write_index(directory, index)
    return index


def _write_image(cv2: Any, path: Path, frame: np.ndarray, width: int) -> bool:
    height = max(1, int(round(frame.shape[0] * width / max(1, frame.shape[1]))))
    small = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".webp", small, [int(cv2.IMWRITE_WEBP_QUALITY), 85])
    if not ok:
        logger.warning("Önizleme kodlanamadı: %s", path.name)
        return False
    # Written through the file object so the Windows extended-length prefix
    # applies; cv2.imwrite would not accept it.
    with open(long_path(path), "wb") as stream:
        stream.write(buffer.tobytes())
    return True


def _write_index(directory: Path, index: dict[str, Any]) -> None:
    target = ensure_dir(Path(directory) / THUMBNAIL_DIRNAME)
    write_json(target / THUMBNAIL_INDEX_FILE, index)


class ThumbnailIndex:
    """Reader. Returns paths; decoding is the view's business."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        path = self.directory / THUMBNAIL_DIRNAME / THUMBNAIL_INDEX_FILE
        self.index: dict[str, Any] = (
            dict(read_json(path)) if path_exists(path) else {"entries": []}
        )
        self._positions = [int(e["position"]) for e in self.index.get("entries", [])]

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(self._positions)

    @property
    def unavailable_reason(self) -> str:
        return str(self.index.get("unavailable_reason", ""))

    def path_for(self, position: int) -> Optional[Path]:
        for entry in self.index.get("entries", []):
            if int(entry["position"]) == int(position):
                return self.directory / entry["file"]
        return None

    def nearest(self, position: int) -> Optional[Path]:
        """The closest preview to ``position``, or ``None`` if there are none."""
        if not self._positions:
            return None
        best = min(self._positions, key=lambda value: abs(value - int(position)))
        return self.path_for(best)

    def cover(self) -> Optional[Path]:
        """The one image that represents this version in a list: the middle frame."""
        if not self._positions:
            return None
        return self.nearest(self._positions[len(self._positions) // 2])


__all__ = [
    "DEFAULT_THUMBNAIL_COUNT",
    "DEFAULT_THUMBNAIL_WIDTH",
    "THUMBNAIL_DIRNAME",
    "THUMBNAIL_SCHEMA_VERSION",
    "ThumbnailIndex",
    "build_thumbnails",
    "planned_positions",
]
