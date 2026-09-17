"""Is the person actually inside the picture, and did they stay inside it?

A solo operator cannot read the screen from the bottom of a squat, and the
bottom of a squat is exactly where the feet leave the frame. A live indicator
alone therefore answers the wrong question: by the time it can be read, the
moment it was reporting on is over.

So this answers two questions at once. :class:`Framing` is what is true right
now, for standing in front of the camera and getting into position.
:class:`FramingWatch` is what was the *worst* thing that happened in the last
few seconds, which is what you read after standing back up.

Positions come from the light preview pose, which is a two-dimensional
detection in the preview image. It is not the tracker, not an identity, and
never recorded - it is used here only to answer "can the camera see all of
you", which is a question about the picture.

No Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

import numpy as np

#: MediaPipe pose landmark indices, named at the one place that needs them.
#: ``27`` means nothing to a reader; ``LEFT_ANKLE`` means everything.
NOSE = 0
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_ANKLE, RIGHT_ANKLE = 27, 28
LEFT_FOOT, RIGHT_FOOT = 31, 32

#: The parts that have to be in shot for a full-body exercise recording, and
#: what to call them when one is not.
REQUIRED_PARTS: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("baş", (NOSE,)),
    ("omuzlar", (LEFT_SHOULDER, RIGHT_SHOULDER)),
    ("kalça", (LEFT_HIP, RIGHT_HIP)),
    ("ayaklar", (LEFT_ANKLE, RIGHT_ANKLE, LEFT_FOOT, RIGHT_FOOT)),
)

#: Distance from the edge, as a fraction of the shorter side, that counts as
#: out of shot. A joint sitting on the last few pixels of the sensor is one
#: step away from being gone, and its depth there is the least reliable.
SAFE_MARGIN = 0.02

#: A second band. Inside the picture, but with no room to move - which for a
#: squat means the next repetition may not be.
COMFORT_MARGIN = 0.07


@dataclass(frozen=True)
class Framing:
    """One reading. ``state`` drives the colour, the rest is what to read."""

    state: str = "no_camera"
    #: Short enough to be read from three metres away.
    text: str = "Kamera bağlı değil"
    #: What to do about it, when there is something to do.
    advice: str = ""
    #: Which named parts are out of shot, for the history to count.
    missing: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """Whether a recording started now would see the whole person."""
        return self.state in ("ok", "tight")


def _visible(points: np.ndarray, indices: Iterable[int]) -> list[np.ndarray]:
    out = []
    for index in indices:
        if index >= len(points):
            continue
        point = points[index]
        if np.isfinite(point).all():
            out.append(point)
    return out


def _side(point: np.ndarray, width: float, height: float, margin: float) -> str:
    """Which edge this point is past, or "" when it is comfortably inside."""
    x, y = float(point[0]), float(point[1])
    if y < margin:
        return "üst"
    if y > height - margin:
        return "alt"
    if x < margin:
        return "sol"
    if x > width - margin:
        return "sağ"
    return ""


#: What to do about a part that has gone past each edge. Written as an
#: instruction to the person in front of the camera, because that is who reads
#: it, and they are usually too far away to reach the mouse.
_ADVICE = {
    "alt": "Bir adım geri gidin veya kamerayı biraz yukarı kaldırın.",
    "üst": "Bir adım geri gidin veya kamerayı biraz aşağı indirin.",
    "sol": "Sağa doğru kayın.",
    "sağ": "Sola doğru kayın.",
}


def measure(preview, *, resolution: Optional[Sequence[int]] = None) -> Framing:
    """Read the live preview and say whether the whole person is in shot.

    ``preview`` is a ``PosePreview`` or ``None``. Nothing here is recorded and
    nothing here is an identity: the question is only about the picture.
    """
    if preview is None:
        return Framing(
            state="no_overlay",
            text="Kadraj kontrolü kapalı",
            advice="Hafif poz kaplaması olmadan kadraj ölçülemez.",
        )
    people = tuple(getattr(preview, "people", ()) or ())
    if not people:
        return Framing(state="no_person", text="Kadrajda kimse yok")
    if len(people) > 1:
        return Framing(
            state="crowded",
            text=f"Kadrajda {len(people)} kişi",
            advice="Kayıt tek kişilik; diğerleri kadrajdan çıkmalı.",
        )

    size = resolution if resolution is not None else getattr(preview.packet, "resolution", None)
    if not size or len(size) < 2 or not all(size[:2]):
        return Framing(state="no_camera", text="Görüntü boyutu bilinmiyor")
    width, height = float(size[0]), float(size[1])
    shorter = min(width, height)
    safe = shorter * SAFE_MARGIN
    comfort = shorter * COMFORT_MARGIN

    points = np.asarray(people[0].points, dtype=np.float32)
    missing: list[str] = []
    sides: list[str] = []
    unseen: list[str] = []
    tight: list[str] = []
    for name, indices in REQUIRED_PARTS:
        seen = _visible(points, indices)
        if not seen:
            # The detector did not find it at all, which at the edge of the
            # frame usually means it is outside one. Reported as its own case
            # rather than being called "in shot" by default.
            unseen.append(name)
            continue
        for point in seen:
            side = _side(point, width, height, safe)
            if side:
                missing.append(name)
                sides.append(side)
                break
        else:
            if any(_side(point, width, height, comfort) for point in seen):
                tight.append(name)

    if missing:
        edge = sides[0]
        parts = " ve ".join(dict.fromkeys(missing))
        return Framing(
            state="cut",
            text=f"{parts.capitalize()} kadraj dışında",
            advice=_ADVICE.get(edge, ""),
            missing=tuple(dict.fromkeys(missing)),
        )
    if unseen:
        parts = " ve ".join(dict.fromkeys(unseen))
        return Framing(
            state="cut",
            text=f"{parts.capitalize()} görünmüyor",
            advice="Kadraja tamamen girin; gerekiyorsa bir adım geri gidin.",
            missing=tuple(dict.fromkeys(unseen)),
        )
    if tight:
        parts = " ve ".join(dict.fromkeys(tight))
        return Framing(
            state="tight",
            text="Kadraj dar",
            advice=f"{parts.capitalize()} kenara çok yakın; bir adım geri gidin.",
        )
    return Framing(state="ok", text="Kadraj tamam")


@dataclass
class FramingWatch:
    """The last few seconds of framing, so a rehearsal can be read afterwards.

    This is the part that makes a solo recording checkable. You cannot read a
    live indicator from the bottom of a squat; you can stand up, walk to the
    screen and read what the last fifteen seconds were.
    """

    window_s: float = 15.0
    _samples: list[tuple[float, float, tuple[str, ...]]] = field(
        default_factory=list, repr=False
    )

    def observe(self, framing: Framing, *, now: float) -> None:
        """Record one reading, and forget anything older than the window."""
        if self._samples:
            # Each sample carries the time since the previous one, so gaps in
            # the preview are not counted as time spent in any state.
            gap = min(now - self._samples[-1][0], 0.5)
        else:
            gap = 0.0
        self._samples.append((now, gap, framing.missing))
        cutoff = now - self.window_s
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

    def reset(self) -> None:
        self._samples.clear()

    @property
    def observed_s(self) -> float:
        return sum(gap for _at, gap, _missing in self._samples)

    def seconds_out(self) -> dict[str, float]:
        """How long each named part spent out of shot, within the window."""
        totals: dict[str, float] = {}
        for _at, gap, missing in self._samples:
            for name in missing:
                totals[name] = totals.get(name, 0.0) + gap
        return {name: value for name, value in totals.items() if value > 0.0}

    @property
    def verdict(self) -> str:
        """One sentence to read after a rehearsal. Empty before there is one."""
        window = int(self.window_s)
        if self.observed_s < 1.0:
            return ""
        out = self.seconds_out()
        if not out:
            return f"Son {window} sn: kadraj tamam"
        worst = max(out.items(), key=lambda item: item[1])
        return f"Son {window} sn: {worst[0]} {worst[1]:.1f} sn kadraj dışındaydı"

    @property
    def clean(self) -> bool:
        """True when nothing left the frame during an observed window."""
        return self.observed_s >= 1.0 and not self.seconds_out()


__all__ = [
    "COMFORT_MARGIN",
    "Framing",
    "FramingWatch",
    "REQUIRED_PARTS",
    "SAFE_MARGIN",
    "measure",
]
