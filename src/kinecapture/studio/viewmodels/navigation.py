"""The workflow the navigation bar describes.

The order is the product: **Projeler → Yakalama → Verileri Hesapla → İşlenen
Videolar → Etiketleme → Veri Seti → Dışa Aktarım → Ayarlar**. Someone reading
the bar left to right should be able to work out what the application does and
in what order, without being told.

A destination can be *gated*: visible, in its real position, but not enterable
yet, with a sentence saying what is missing. Hiding it instead would make the
workflow look shorter than it is and leave the user wondering where the step
they were told about went.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Destination:
    key: str
    title: str
    icon: str
    #: One line under the page title. Says what the screen is for.
    subtitle: str = ""
    #: Which phase delivers it. Shown on the placeholder while it is pending.
    phase: str = ""


DESTINATIONS: tuple[Destination, ...] = (
    Destination(
        key="projects",
        title="Projeler",
        icon="folder",
        subtitle="Proje, katılımcı ve oturumlar",
        phase="F4",
    ),
    Destination(
        key="capture",
        title="Yakalama",
        icon="record",
        subtitle="Ham kayıt alın; iskelet sonra hesaplanır",
        phase="F5",
    ),
    Destination(
        key="processing",
        title="Verileri Hesapla",
        icon="cpu",
        subtitle="Ham kayıtlardan iskelet ve derinlik üretin",
        phase="F6",
    ),
    Destination(
        key="library",
        title="İşlenen Videolar",
        icon="film",
        subtitle="Tamamlanmış işleme sürümleri",
        phase="F7",
    ),
    Destination(
        key="review",
        title="Etiketleme",
        icon="tag",
        subtitle="Hareket ve hata aralıklarını işaretleyin",
        phase="F8",
    ),
    Destination(
        key="dataset",
        title="Veri Seti",
        icon="grid",
        subtitle="Bütün kayıtların kalite ve kapsam görünümü",
        phase="F11",
    ),
    Destination(
        key="export",
        title="Dışa Aktarım",
        icon="export",
        subtitle="Sürümlü veri seti paketleri",
        phase="F11",
    ),
    Destination(
        key="settings",
        title="Ayarlar",
        icon="settings",
        subtitle="Kayıt, önizleme, işleme ve görünüm",
        phase="F4",
    ),
)

DEFAULT_DESTINATION = DESTINATIONS[0].key

_BY_KEY = {destination.key: destination for destination in DESTINATIONS}


def destination(key: str) -> Optional[Destination]:
    return _BY_KEY.get(key)


def is_known(key: str) -> bool:
    return key in _BY_KEY


__all__ = [
    "DEFAULT_DESTINATION",
    "DESTINATIONS",
    "Destination",
    "destination",
    "is_known",
]
