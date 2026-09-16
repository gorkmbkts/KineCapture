"""What the six helper windows show, gathered without Qt.

These windows exist to answer "why" questions that the main screens
deliberately do not clutter themselves with: why is the camera not connecting,
where did this number come from, what exactly was recorded. Each one is a
read-only view over something that already exists on disk or in memory - none
of them computes a new fact, and none of them can change anything.

Every section returns plain rows so the window is a table and the test is a
list comparison. Absent values say so; nothing here fills a blank with a
plausible default, because the whole point of these windows is to be believed.
"""

from __future__ import annotations

import logging
import platform
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.core.jsonio import read_json
from kinecapture.core.logging import ROOT_LOGGER_NAME, log_file_path
from kinecapture.core.paths import long_path, path_exists

#: How many log lines the console keeps. Enough to cover a session's worth of
#: work, small enough that the window never becomes the memory problem.
LOG_BUFFER = 2000

MISSING = "—"


@dataclass(frozen=True)
class Row:
    """One ``label: value`` line, with the explanation behind it."""

    label: str
    value: str = MISSING
    detail: str = ""
    level: str = "neutral"   # neutral | ready | warning | error

    @property
    def is_missing(self) -> bool:
        return self.value in ("", MISSING)


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[Row, ...] = ()
    note: str = ""


def _text(value: Any) -> str:
    if value is None or value == "":
        return MISSING
    if isinstance(value, bool):
        return "evet" if value else "hayır"
    if isinstance(value, (list, tuple)):
        return " × ".join(str(v) for v in value) if value else MISSING
    return str(value)


# --------------------------------------------------------------- log console
class LogBuffer(logging.Handler):
    """Keeps the last lines the application logged, for the Log Konsolu.

    Attached to the application's own logger rather than reading the file, so
    the window works before a log file exists and keeps working if the disk
    the file lives on fills up.
    """

    def __init__(self, capacity: int = LOG_BUFFER) -> None:
        super().__init__()
        self.records: deque[tuple[str, str, str, str]] = deque(maxlen=capacity)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stamp = datetime.fromtimestamp(record.created, timezone.utc).strftime(
                "%H:%M:%S"
            )
            self.records.append(
                (stamp, record.levelname, record.name, self.format(record))
            )
        except Exception:  # noqa: BLE001 - a logging handler must never raise
            pass

    def install(self) -> "LogBuffer":
        logging.getLogger(ROOT_LOGGER_NAME).addHandler(self)
        return self

    def remove(self) -> None:
        logging.getLogger(ROOT_LOGGER_NAME).removeHandler(self)

    def lines(self, *, minimum: str = "DEBUG", contains: str = "") -> list[str]:
        order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        floor = order.get(minimum.upper(), 0)
        needle = contains.lower()
        out: list[str] = []
        for stamp, level, name, message in self.records:
            if order.get(level, 0) < floor:
                continue
            line = f"{stamp}  {level:<8} {name}  {message}"
            if needle and needle not in line.lower():
                continue
            out.append(line)
        return out


def log_file_section() -> Section:
    path = log_file_path()
    root = logging.getLogger(ROOT_LOGGER_NAME)
    level = logging.getLevelName(root.getEffectiveLevel())
    return Section(
        "Günlük",
        (
            Row(
                "Kayıt seviyesi",
                str(level),
                detail=(
                    "Konsol yalnız uygulamanın bu seviyede ürettiği satırları "
                    "görebilir. Daha ayrıntısı için seviyeyi düşürmek gerekir; "
                    "pencere kendi başına seviyeyi değiştirmez."
                ),
                level="warning" if root.getEffectiveLevel() > logging.INFO else "neutral",
            ),
            Row("Dosya", _text(path)),
            Row(
                "Boyut",
                f"{Path(long_path(path)).stat().st_size / 1024:.0f} KB"
                if path and path_exists(path)
                else MISSING,
            ),
        ),
        note="Konsol uygulamanın kendi kaydedicisinden okur; dosya olmasa da çalışır.",
    )


# ---------------------------------------------------------------- device info
def device_sections(camera_info: Any) -> tuple[Section, ...]:
    """What the connected camera says about itself."""
    if camera_info is None:
        return (
            Section(
                "Cihaz",
                (Row("Durum", "bağlı değil"),),
                note="Kamera bağlandığında bu pencere doldurulur.",
            ),
        )
    extra = dict(getattr(camera_info, "extra", {}) or {})
    identity = Section(
        "Cihaz",
        (
            Row("Model", _text(getattr(camera_info, "model", None))),
            Row("Arka uç", _text(getattr(camera_info, "backend", None))),
            Row("Seri numarası", _text(getattr(camera_info, "serial_number", None))),
            Row("Firmware", _text(getattr(camera_info, "firmware_version", None))),
            Row("SDK", _text(getattr(camera_info, "sdk_version", None))),
            Row(
                "Köken",
                _text(getattr(getattr(camera_info, "origin", None), "value", None)),
                detail="Sentetik bir cihaz her yerde böyle işaretlenir.",
            ),
        ),
    )
    capture = Section(
        "Yakalama",
        (
            Row("Çözünürlük", _text(getattr(camera_info, "resolution", None))),
            Row("Hedef FPS", _text(getattr(camera_info, "target_fps", None))),
            Row("Koordinat sistemi", _text(getattr(camera_info, "coordinate_system", None))),
            Row("Uzunluk birimi", _text(getattr(camera_info, "length_unit", None))),
        ),
    )
    return (identity, capture, Section("Ek alanlar", _rows_from(extra)))


def _rows_from(payload: Any, prefix: str = "") -> tuple[Row, ...]:
    """Flatten a mapping into rows, one leaf per row."""
    rows: list[Row] = []
    if isinstance(payload, dict):
        for key in sorted(payload, key=str):
            rows.extend(_rows_from(payload[key], f"{prefix}{key}."))
    elif isinstance(payload, (list, tuple)) and payload and isinstance(payload[0], dict):
        for index, item in enumerate(payload):
            rows.extend(_rows_from(item, f"{prefix}{index}."))
    else:
        rows.append(Row(prefix.rstrip("."), _text(payload)))
    return tuple(rows)


# ------------------------------------------------------------- raw parameters
def raw_parameter_sections(run_dir: Optional[Path]) -> tuple[Section, ...]:
    """Every setting a processing version was produced with, verbatim.

    Verbatim on purpose: this window exists so a disagreement about what a
    version was made with can be settled by reading, not by remembering.
    """
    if run_dir is None or not path_exists(Path(run_dir) / "job.json"):
        return (Section("Parametreler", (Row("Sürüm", "seçilmedi"),)),)
    job = dict(read_json(Path(run_dir) / "job.json"))
    return (
        Section("Sürüm", (
            Row("run_id", _text(job.get("run_id"))),
            Row("Durum", _text(job.get("state"))),
            Row("Şema", _text(job.get("schema_version"))),
            Row("Uygulama", _text(job.get("app_version"))),
            Row("İskelet biçimi", _text(job.get("skeleton_format"))),
            Row("İşlenen kare", _text(job.get("frames_processed"))),
        )),
        Section("İstenen parametreler", _rows_from(job.get("parameters") or {})),
        Section("İşleme kamerası", _rows_from(job.get("processing_camera") or {})),
        Section("Zaman damgası QC", _rows_from(job.get("timestamp_qc") or {})),
    )


# ---------------------------------------------------------------- provenance
def provenance_sections(run_dir: Optional[Path]) -> tuple[Section, ...]:
    """Where a version's numbers came from, and what they are not."""
    if run_dir is None or not path_exists(Path(run_dir) / "job.json"):
        return (Section("Köken", (Row("Sürüm", "seçilmedi"),)),)
    run_dir = Path(run_dir)
    job = dict(read_json(run_dir / "job.json"))
    source = dict(job.get("source") or {})
    features_path = run_dir / "features.json"
    features = dict(read_json(features_path)) if path_exists(features_path) else {}

    sections = [
        Section("Ham kaynak", (
            Row("Parmak izi", _text(source.get("fingerprint")),
                detail="Etiketler bu parmak izine bağlıdır; başka bir kayda taşınmaz."),
            Row("Kayıt dizini", _text(job.get("take_dir"))),
            Row("Bildirilen kare", _text(job.get("source_frames_declared"))),
        )),
        Section("Sorunlar", tuple(
            Row(code, "var", level="warning") for code in job.get("issues") or ()
        ) or (Row("Sorun", "yok", level="ready"),)),
    ]
    if features:
        sections.append(
            Section("Özellik kökeni", _rows_from(features.get("availability") or {}),
                    note="Hesaplanamayan bir özellik NaN kalır; sıfırla doldurulmaz.")
        )
        association = features.get("subject_association") or {}
        if association:
            sections.append(Section("Kişi eşleştirme", _rows_from({
                "state": association.get("state"),
                "tracker_id": association.get("current_tracker_id"),
                "counters": association.get("counters"),
            })))
    depth = run_dir / "depth"
    if path_exists(depth):
        sections.append(Section("Derinlik", (
            Row("Köken", "reconstructed_offline",
                detail="Kayıt anında ölçülen derinlik değil; SVO tekrar "
                       "oynatıldığında aynı değerler dönmez.",
                level="warning"),
        )))
    return tuple(sections)


# ------------------------------------------------------------- source audit
def source_audit_sections(run_dir: Optional[Path]) -> tuple[Section, ...]:
    """Whether a version's derived files still are what they were."""
    if run_dir is None:
        return (Section("Kaynak denetimi", (Row("Sürüm", "seçilmedi"),)),)
    run_dir = Path(run_dir)
    manifest_path = run_dir / "checksums.json"
    if not path_exists(manifest_path):
        return (
            Section(
                "Kaynak denetimi",
                (Row("checksums.json", "yok", level="warning"),),
                note="Bu sürüm doğrulanamaz; yeniden işlemek gerekir.",
            ),
        )
    from kinecapture.core.fingerprint import verify_checksum_manifest

    manifest = dict(read_json(manifest_path))
    mismatches = verify_checksum_manifest(manifest, run_dir)
    rows = [
        Row("Algoritma", _text(manifest.get("algorithm", "sha256"))),
        Row("Dosya sayısı", _text(len(manifest.get("files") or {}))),
        Row(
            "Doğrulama",
            "başarısız" if mismatches else "geçti",
            level="error" if mismatches else "ready",
            detail="Türetilmiş dosyalar yazıldıkları andaki hâlleriyle aynı."
            if not mismatches
            else "Aşağıdaki dosyalar değişmiş; bu sürüm dışa aktarılmamalı.",
        ),
    ]
    rows.extend(
        Row(str(problem.get("file", "?")), str(problem.get("issue", "uyuşmuyor")),
            level="error")
        for problem in mismatches
    )
    return (Section("Kaynak denetimi", tuple(rows)),)


# ------------------------------------------------------------- environment
def environment_sections() -> tuple[Section, ...]:
    """The bits of the machine that explain most failures."""
    return (
        Section("Uygulama", (
            Row("Ad", APP_NAME),
            Row("Sürüm", APP_VERSION),
        )),
        Section("Python", (
            Row("Sürüm", sys.version.split()[0]),
            Row("Yorumlayıcı", sys.executable),
        )),
        Section("Makine", (
            Row("İşletim sistemi", f"{platform.system()} {platform.release()}"),
            Row("Mimari", platform.machine()),
        )),
    )


#: The four things the diagnostics window can be doing. A failure is one of
#: them, and it must never be shown as "not run yet": the audit found exactly
#: that hiding a real ``TypeError`` behind an idle-looking window.
DIAGNOSTICS_STATES = ("idle", "running", "done", "failed")


def diagnostics_sections(
    report: Any, *, state: str = "done", error: str = ""
) -> tuple[Section, ...]:
    """A :class:`DiagnosticsReport` as rows, worst first."""
    if state == "running":
        return (
            Section(
                "Tanılama",
                (Row("Durum", "çalışıyor", level="warning"),),
                note="Ortam, paketler ve SDK okunuyor.",
            ),
        )
    if state == "failed":
        return (
            Section(
                "Tanılama",
                (
                    Row(
                        "Durum",
                        "başarısız",
                        detail=error or "Sebep bildirilmedi.",
                        level="error",
                    ),
                    Row("Hata", error or MISSING, level="error"),
                ),
                note="'Yenile' ile yeniden denenebilir.",
            ),
        )
    if report is None:
        return (
            Section(
                "Tanılama",
                (Row("Durum", "henüz çalıştırılmadı"),),
                note="'Yenile' tanılamayı başlatır.",
            ),
        )
    order = {"blocked": 0, "warning": 1, "unknown": 2, "ready": 3}
    level_map = {"blocked": "error", "warning": "warning", "ready": "ready"}
    checks = sorted(
        report.checks, key=lambda c: order.get(c.level.value, 9)
    )
    rows = tuple(
        Row(
            check.name,
            check.value or check.message,
            detail=check.remedy or check.message,
            level=level_map.get(check.level.value, "neutral"),
        )
        for check in checks
    )
    return (
        Section("Genel", (Row("Sonuç", report.level.value),)),
        Section("Kontroller", rows),
    )


def sections_as_text(sections: Iterable[Section]) -> str:
    """The whole window as text, for pasting into a bug report."""
    lines: list[str] = []
    for section in sections:
        lines.append(f"== {section.title}")
        for row in section.rows:
            lines.append(f"   {row.label}: {row.value}")
            if row.detail:
                lines.append(f"      {row.detail}")
        if section.note:
            lines.append(f"   ({section.note})")
        lines.append("")
    return "\n".join(lines).strip()


__all__ = [
    "LOG_BUFFER",
    "MISSING",
    "LogBuffer",
    "Row",
    "Section",
    "device_sections",
    "diagnostics_sections",
    "environment_sections",
    "log_file_section",
    "provenance_sections",
    "raw_parameter_sections",
    "sections_as_text",
    "source_audit_sections",
]
