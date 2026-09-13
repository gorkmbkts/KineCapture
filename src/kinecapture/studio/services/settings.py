"""Settings as data: what each one is, what it costs, and how it is written.

Every setting is declared once, with the sentence that explains it. The screen
renders the declarations; it does not know what a depth mode is. That keeps the
explanation next to the value it explains instead of in a tooltip somebody
forgets to update.

Three rules this module exists to keep:

* **Nothing is written until everything validates.** A settings page that
  half-applies a change leaves the application in a state the user never asked
  for.
* **An invalid value never locks the application.** It is reported against the
  field that caused it and the old value stays in force.
* **Costly options say so.** Turning on a live product is a real cost in frames
  per second and gigabytes, and the interface has to say that before it is
  switched on, not after.

No Qt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from kinecapture.core.config import AppConfig, save_user_state
from kinecapture.core.errors import KineCaptureError, ValidationError
from kinecapture.domain.project import CaptureProfile
from kinecapture.processing.jobs import ProcessingConfig

logger = logging.getLogger(__name__)

#: Settings groups, in the order the screen shows them.
GROUP_ORDER = ("capture", "preview", "processing", "data", "appearance", "advanced")

GROUP_TITLES = {
    "capture": "Kayıt",
    "preview": "Önizleme",
    "processing": "İşleme",
    "data": "Veri",
    "appearance": "Görünüm",
    "advanced": "Gelişmiş",
}

GROUP_SUBTITLES = {
    "capture": "Kameradan ne kaydedileceği ve nereye yazılacağı",
    "preview": "Ekranda gördüğünüz görüntü; kaydedilen veri değildir",
    "processing": "Kayıttan sonra iskeletin nasıl hesaplanacağı",
    "data": "Projelerin ve kayıtların bulunduğu klasör",
    "appearance": "Tema ve dil",
    "advanced": "Tanılama ve sorun giderme",
}


@dataclass(frozen=True)
class Choice:
    value: Any
    label: str
    #: Shown next to the option when it is not free.
    cost: str = ""


@dataclass(frozen=True)
class SettingField:
    """One setting, with the sentence that says what it is for."""

    key: str
    group: str
    label: str
    help_text: str
    kind: str  # "choice" | "bool" | "int" | "float" | "path" | "text"
    choices: tuple[Choice, ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    suffix: str = ""
    #: Set when switching this on costs frames per second or disk space.
    cost_note: str = ""
    #: Set when the value is shown but cannot be edited here.
    read_only: bool = False


def _capture_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="capture.resolution",
            group="capture",
            label="Çözünürlük",
            help_text=(
                "Kameradan istenen görüntü boyutu. Kamera bu değeri "
                "desteklemiyorsa kendi seçtiğini bildirir ve kayıt bunu ayrıca "
                "saklar; sessizce düşürülmez."
            ),
            kind="choice",
            choices=(
                Choice("HD720", "HD720  1280×720"),
                Choice("HD1080", "HD1080  1920×1080", "daha yavaş"),
                Choice("HD2K", "HD2K  2208×1242", "belirgin şekilde daha yavaş"),
                Choice("VGA", "VGA  672×376"),
            ),
        ),
        SettingField(
            key="capture.fps",
            group="capture",
            label="Hedef FPS",
            help_text=(
                "Saniyede istenen kare sayısı. Gerçekte ulaşılan hız kayıt "
                "sırasında ayrıca ölçülür ve kaydın yanına yazılır."
            ),
            kind="int",
            minimum=1,
            maximum=120,
            suffix=" FPS",
        ),
        SettingField(
            key="capture.native_compression",
            group="capture",
            label="SVO2 sıkıştırması",
            help_text=(
                "Ham stereo kaydın sıkıştırması. H264 kayıplıdır; kayıpsız "
                "seçenekler ölçülerek çok daha büyük dosya üretir. Codec "
                "başlatılamazsa kayıt hata verir, sessizce kayıplıya geçilmez."
            ),
            kind="choice",
            choices=(
                Choice("H264_LOSSLESS", "H264 kayıpsız", "≈1,1 GB/dk — ölçüldü"),
                Choice("H264", "H264", "≈0,1 GB/dk — kayıplı"),
                Choice("LOSSLESS", "PNG kayıpsız", "≈3,0 GB/dk — ölçüldü"),
            ),
        ),
        SettingField(
            key="capture.enable_body_tracking",
            group="capture",
            label="Canlı iskelet",
            help_text=(
                "Kayıt sırasında iskeleti de hesaplar. Varsayılan kapalıdır: "
                "iskelet kayıttan sonra, daha iyi bir modelle ve kare "
                "atlamadan hesaplanır."
            ),
            kind="bool",
            cost_note="Kayıt hızını belirgin biçimde düşürür.",
        ),
        SettingField(
            key="capture.depth_archive",
            group="capture",
            label="Canlı derinlik arşivi",
            help_text=(
                "Kayıt anında ölçülen derinliği ayrıca saklar. Kapalıyken "
                "derinlik ham kayıttan yeniden üretilir; bu ikisi aynı değer "
                "değildir ve çıktı 'offline yeniden üretildi' olarak işaretlenir."
            ),
            kind="choice",
            choices=(
                Choice("none", "Kapalı  (önerilen)"),
                Choice("float32_lossless", "Kayıpsız float32", "≈3,5 GB/dk — ölçüldü"),
                Choice("uint16_quantised", "Nicemlenmiş uint16", "≈1,6 GB/dk — kayıplı"),
            ),
            cost_note="Diske çok yer yazar ve kayıt hattına yük bindirir.",
        ),
        SettingField(
            key="capture.min_free_disk_minutes",
            group="capture",
            label="En az boş disk süresi",
            help_text=(
                "Hedef diskte bu kadar dakikalık kayıt yeri yoksa kayıt "
                "başlatılmaz. İş ortasında yer bitmesindense hiç başlamaması "
                "tercih edilir."
            ),
            kind="float",
            minimum=0.0,
            maximum=600.0,
            suffix=" dk",
        ),
    )


def _preview_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="capture.preview_enabled",
            group="preview",
            label="Önizleme",
            help_text=(
                "Kayıt sırasında ekranda görüntü gösterir. Kapatmak kayda "
                "ayrılan kaynağı artırır; kaydedilen veriyi değiştirmez."
            ),
            kind="bool",
        ),
        SettingField(
            key="capture.preview_fps",
            group="preview",
            label="Önizleme hızı",
            help_text=(
                "Saniyede kaç önizleme karesi gösterileceği. Kayıt hızından "
                "bağımsızdır: atlanan önizleme karesi veri kaybı değildir ve "
                "ayrı sayılır."
            ),
            kind="float",
            minimum=1.0,
            maximum=60.0,
            suffix=" FPS",
        ),
        SettingField(
            key="capture.preview_width",
            group="preview",
            label="Önizleme genişliği",
            help_text="Önizleme görüntüsünün piksel genişliği. Küçük olması kayda yer bırakır.",
            kind="int",
            minimum=160,
            maximum=1920,
            suffix=" px",
        ),
        SettingField(
            key="preview.pose_enabled",
            group="preview",
            label="Hafif 2B iskelet kaplaması",
            help_text=(
                "Önizlemenin üstüne CPU'da çalışan hafif bir 2B poz çizer. "
                "Bu yalnızca kadrajı kontrol etmek içindir: metrik iskelet "
                "değildir ve katılımcı kimliği taşımaz."
            ),
            kind="bool",
        ),
    )


def _processing_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="processing.body_format",
            group="processing",
            label="İskelet biçimi",
            help_text=(
                "Kaç eklemli iskelet üretileceği. BODY_38 squat gibi önden "
                "görünen hareketlerde kayıtlı veride BODY_34'ten belirgin "
                "biçimde daha iyi sonuç verdi; BODY_34 daha hızlıdır."
            ),
            kind="choice",
            choices=(
                Choice("BODY_38", "BODY_38  38 eklem  (önerilen)"),
                Choice("BODY_34", "BODY_34  34 eklem", "daha hızlı"),
                Choice("BODY_18", "BODY_18  18 eklem", "en hızlı, en az ayrıntı"),
            ),
        ),
        SettingField(
            key="processing.body_model",
            group="processing",
            label="Model seviyesi",
            help_text="Vücut takibi modelinin doğruluk/hız dengesi.",
            kind="choice",
            choices=(
                Choice("HUMAN_BODY_ACCURATE", "Doğru  (önerilen)"),
                Choice("HUMAN_BODY_MEDIUM", "Orta", "daha hızlı"),
                Choice("HUMAN_BODY_FAST", "Hızlı", "en hızlı, en az doğru"),
            ),
        ),
        SettingField(
            key="processing.depth_mode",
            group="processing",
            label="Derinlik modu",
            help_text=(
                "Ham kayıttan derinliğin nasıl yeniden üretileceği. İşleme "
                "kayıttan sonra çalıştığı için buradaki yavaşlık kayıt hızını "
                "etkilemez."
            ),
            kind="choice",
            choices=(
                Choice("NEURAL_PLUS", "NEURAL_PLUS  (önerilen)"),
                Choice("NEURAL", "NEURAL", "daha hızlı"),
                Choice("QUALITY", "QUALITY"),
                Choice("PERFORMANCE", "PERFORMANCE", "en hızlı"),
            ),
        ),
        SettingField(
            key="processing.body_fitting",
            group="processing",
            label="Gövde oturtma (fitting)",
            help_text=(
                "Eksik eklemleri insan kinematiği kısıtlarıyla tamamlar. "
                "Açık olması genelde daha kararlı iskelet verir."
            ),
            kind="bool",
        ),
        SettingField(
            key="processing.allow_reduced_precision_inference",
            group="processing",
            label="Düşük hassasiyetli çıkarım",
            help_text=(
                "Modeli daha düşük sayısal hassasiyetle çalıştırır. Hızlandırır, "
                "sonucu değiştirebilir; varsayılan kapalıdır."
            ),
            kind="bool",
            cost_note="Sonucu değiştirebilir.",
        ),
        SettingField(
            key="processing.confidence_threshold",
            group="processing",
            label="Algılama güven eşiği",
            help_text=(
                "Bu değerin altındaki algılamalar yok sayılır. Yükseltmek "
                "yanlış algılamayı azaltır, kişiyi kaybetme riskini artırır."
            ),
            kind="int",
            minimum=0,
            maximum=100,
        ),
        SettingField(
            key="processing.thumbnail_count",
            group="processing",
            label="Önizleme görüntüsü sayısı",
            help_text=(
                "İşlenen her sürüm için üretilecek küçük görüntü sayısı. "
                "İlk, orta ve son kare her zaman üretilir."
            ),
            kind="int",
            minimum=0,
            maximum=60,
        ),
        SettingField(
            key="processing.max_concurrent_jobs",
            group="processing",
            label="Eşzamanlı iş sayısı",
            help_text=(
                "Aynı anda kaç kaydın işleneceği. Tek GPU'da birden fazla iş "
                "genelde toplam süreyi kısaltmaz."
            ),
            kind="int",
            minimum=1,
            maximum=4,
        ),
    )


def _data_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="dataset_root",
            group="data",
            label="Veri klasörü",
            help_text=(
                "Projelerin ve kayıtların yazıldığı klasör. Değiştirmek mevcut "
                "verilerinizi taşımaz; eski klasör olduğu yerde kalır."
            ),
            kind="path",
        ),
        SettingField(
            key="log_dir",
            group="data",
            label="Log klasörü",
            help_text="Tanılama kayıtlarının yazıldığı klasör.",
            kind="path",
        ),
    )


def _appearance_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="theme",
            group="appearance",
            label="Tema",
            help_text="Arayüzün açık mı koyu mu görüneceği.",
            kind="choice",
            choices=(Choice("dark", "Koyu"), Choice("light", "Açık")),
        ),
        SettingField(
            key="language",
            group="appearance",
            label="Dil",
            help_text="Arayüz dili. Şu an yalnızca Türkçe mevcut.",
            kind="choice",
            choices=(Choice("tr", "Türkçe"),),
            read_only=True,
        ),
    )


def _advanced_fields() -> tuple[SettingField, ...]:
    return (
        SettingField(
            key="log_level",
            group="advanced",
            label="Log seviyesi",
            help_text=(
                "Ne kadar ayrıntı kaydedileceği. Bir sorunu bildirirken DEBUG "
                "seviyesinde bir tekrar üretim çok yardımcı olur."
            ),
            kind="choice",
            choices=(
                Choice("INFO", "INFO  (önerilen)"),
                Choice("DEBUG", "DEBUG", "çok fazla kayıt üretir"),
                Choice("WARNING", "WARNING"),
                Choice("ERROR", "ERROR"),
            ),
        ),
        SettingField(
            key="backend",
            group="advanced",
            label="Kamera kaynağı",
            help_text=(
                "Gerçek ZED kamera yerine sentetik kaynak kullanır. Sentetik "
                "veriyle üretilen her şey baştan sona 'sentetik' olarak "
                "işaretlenir."
            ),
            kind="choice",
            choices=(Choice("zed", "ZED 2i"), Choice("mock", "Sentetik (test)")),
        ),
        SettingField(
            key="autosave_enabled",
            group="advanced",
            label="Otomatik kaydetme",
            help_text="Etiketleme sırasında değişiklikleri kendiliğinden diske yazar.",
            kind="bool",
        ),
    )


def all_fields() -> tuple[SettingField, ...]:
    return (
        *_capture_fields(),
        *_preview_fields(),
        *_processing_fields(),
        *_data_fields(),
        *_appearance_fields(),
        *_advanced_fields(),
    )


FIELDS_BY_KEY = {field.key: field for field in all_fields()}


@dataclass(frozen=True)
class SettingsSnapshot:
    """The current value of every setting, keyed the same way as the fields."""

    values: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class SettingsService:
    """Reads and writes settings, validating everything before writing anything."""

    def __init__(
        self,
        config: AppConfig,
        *,
        processing: Optional[ProcessingConfig] = None,
        save: Optional[Callable[[AppConfig], Any]] = None,
    ) -> None:
        self.config = config
        self.processing = processing or ProcessingConfig()
        self._save = save or save_user_state

    # ----------------------------------------------------------------- read
    def snapshot(self) -> SettingsSnapshot:
        capture = self.config.capture
        values: dict[str, Any] = {
            "dataset_root": str(self.config.dataset_root),
            "log_dir": str(self.config.log_dir),
            "theme": self.config.theme,
            "language": self.config.language,
            "log_level": self.config.log_level,
            "backend": getattr(self.config.backend, "value", self.config.backend),
            "autosave_enabled": self.config.autosave_enabled,
            "preview.pose_enabled": bool(
                self.config.extra.get("preview_pose_enabled", True)
            ),
        }
        for name in (
            "resolution",
            "fps",
            "native_compression",
            "enable_body_tracking",
            "depth_archive",
            "min_free_disk_minutes",
            "preview_enabled",
            "preview_fps",
            "preview_width",
        ):
            values[f"capture.{name}"] = getattr(capture, name)
        for name in (
            "body_format",
            "body_model",
            "depth_mode",
            "body_fitting",
            "allow_reduced_precision_inference",
            "confidence_threshold",
            "thumbnail_count",
        ):
            values[f"processing.{name}"] = getattr(self.processing, name)
        values["processing.max_concurrent_jobs"] = int(
            self.config.extra.get("max_concurrent_jobs", 1)
        )
        return SettingsSnapshot(values)

    def groups(self) -> tuple[tuple[str, tuple[SettingField, ...]], ...]:
        fields = all_fields()
        return tuple(
            (group, tuple(f for f in fields if f.group == group))
            for group in GROUP_ORDER
        )

    # ---------------------------------------------------------------- write
    def validate(self, changes: dict[str, Any]) -> dict[str, str]:
        """Check every change. Returns ``{key: message}`` for the bad ones.

        Runs over the whole set before anything is applied, so the user sees
        every problem at once instead of fixing them one reload at a time.
        """
        problems: dict[str, str] = {}
        for key, value in changes.items():
            field = FIELDS_BY_KEY.get(key)
            if field is None:
                problems[key] = "Bilinmeyen ayar."
                continue
            if field.read_only:
                problems[key] = "Bu ayar buradan değiştirilemez."
                continue
            message = _validate_one(field, value)
            if message:
                problems[key] = message
        if problems:
            return problems
        # The dataclasses validate themselves; build them and see rather than
        # duplicating their rules here, where the two copies would drift.
        try:
            self._apply_to_copies(changes)
        except (ValidationError, KineCaptureError) as exc:
            field_name = getattr(exc, "details", {}).get("field") or ""
            key = next(
                (k for k in changes if k.endswith(f".{field_name}") or k == field_name),
                next(iter(changes), ""),
            )
            problems[key] = str(exc)
        except (TypeError, ValueError) as exc:
            problems[next(iter(changes), "")] = str(exc)
        return problems

    def apply(self, changes: dict[str, Any]) -> SettingsSnapshot:
        """Validate everything, then write. Raises if anything is invalid.

        All-or-nothing: a partially applied settings change is a state the user
        never chose.
        """
        problems = self.validate(changes)
        if problems:
            raise ValidationError(
                "Bazı ayarlar geçersiz; hiçbiri kaydedilmedi.",
                code="settings_invalid",
                details={"fields": problems},
            )
        capture, processing, extra = self._apply_to_copies(changes)
        for key, value in changes.items():
            if "." not in key:
                if key == "backend":
                    self.config.backend = value
                else:
                    setattr(self.config, key, _coerce_top_level(key, value))
        self.config.capture = capture
        self.config.extra.update(extra)
        self.processing = processing
        try:
            self._save(self.config)
        except Exception as exc:  # noqa: BLE001 - a preference file is not worth a crash
            logger.warning("Ayarlar diske yazılamadı: %s", exc)
        return self.snapshot()

    def _apply_to_copies(
        self, changes: dict[str, Any]
    ) -> tuple[CaptureProfile, ProcessingConfig, dict[str, Any]]:
        capture_changes = {
            key.split(".", 1)[1]: value
            for key, value in changes.items()
            if key.startswith("capture.")
        }
        processing_changes = {
            key.split(".", 1)[1]: value
            for key, value in changes.items()
            if key.startswith("processing.") and key != "processing.max_concurrent_jobs"
        }
        extra: dict[str, Any] = {}
        if "preview.pose_enabled" in changes:
            extra["preview_pose_enabled"] = bool(changes["preview.pose_enabled"])
        if "processing.max_concurrent_jobs" in changes:
            extra["max_concurrent_jobs"] = int(changes["processing.max_concurrent_jobs"])
        capture = replace(self.config.capture, **capture_changes) if capture_changes else self.config.capture
        processing = (
            replace(self.processing, **processing_changes)
            if processing_changes
            else self.processing
        )
        return capture, processing, extra


def _validate_one(field: SettingField, value: Any) -> str:
    if field.kind == "choice":
        allowed = {choice.value for choice in field.choices}
        if value not in allowed:
            return f"Geçerli değerler: {', '.join(str(v) for v in sorted(allowed))}"
        return ""
    if field.kind == "bool":
        return "" if isinstance(value, bool) else "Açık veya kapalı olmalı."
    if field.kind in ("int", "float"):
        try:
            number = int(value) if field.kind == "int" else float(value)
        except (TypeError, ValueError):
            return "Sayı olmalı."
        if field.minimum is not None and number < field.minimum:
            return f"En az {field.minimum:g} olmalı."
        if field.maximum is not None and number > field.maximum:
            return f"En çok {field.maximum:g} olmalı."
        return ""
    if field.kind == "path":
        text = str(value).strip()
        if not text:
            return "Bir klasör seçin."
        try:
            Path(text).expanduser()
        except (OSError, ValueError):
            return "Bu yol kullanılamıyor."
        return ""
    return "" if str(value).strip() else "Boş bırakılamaz."


def _coerce_top_level(key: str, value: Any) -> Any:
    if key in ("dataset_root", "log_dir"):
        return Path(str(value)).expanduser()
    if key == "autosave_enabled":
        return bool(value)
    return value


__all__ = [
    "Choice",
    "FIELDS_BY_KEY",
    "GROUP_ORDER",
    "GROUP_SUBTITLES",
    "GROUP_TITLES",
    "SettingField",
    "SettingsService",
    "SettingsSnapshot",
    "all_fields",
]
