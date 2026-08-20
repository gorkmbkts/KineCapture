"""Environment and pre-capture diagnostics.

One report answers two questions: *can this machine run the application* and
*is it safe to start recording right now*. Every check returns a
:class:`HealthLevel`, a plain sentence, and - when something is wrong - a remedy
the user can actually act on.

Nothing here raises, and nothing here contains personal data, so the report can
be copied into a support message as-is.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from kinecapture import APP_NAME, APP_VERSION
from kinecapture.domain.enums import BackendKind, HealthLevel

#: Packages the application cannot start without.
_REQUIRED_MODULES = (("PySide6", "PySide6"), ("numpy", "NumPy"), ("yaml", "PyYAML"))

#: Packages that degrade a feature but do not block start-up.
_OPTIONAL_MODULES = (("cv2", "OpenCV (proxy video)"),)

#: Free space below which recording is refused outright.
_DISK_BLOCKED_GB = 1.0
#: Free space below which recording is allowed but warned about.
_DISK_WARNING_GB = 10.0

#: Rough bytes per second of a HD720/30 SVO2 recording plus its sidecars,
#: measured on this machine (3.3 MB for 60 frames at HD720/H264 + skeleton).
_BYTES_PER_SECOND_ESTIMATE = 1_700_000


@dataclass
class CheckResult:
    """One diagnostic line."""

    name: str
    level: HealthLevel
    message: str
    remedy: str = ""
    value: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.level is HealthLevel.READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "remedy": self.remedy,
            "value": self.value,
            "details": self.details,
        }


@dataclass
class DiagnosticsReport:
    """A full report plus its overall verdict."""

    app_name: str = APP_NAME
    app_version: str = APP_VERSION
    platform: str = ""
    python_version: str = ""
    python_executable: str = ""
    conda_env: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def level(self) -> HealthLevel:
        """The worst level in the report."""
        if any(c.level is HealthLevel.BLOCKED for c in self.checks):
            return HealthLevel.BLOCKED
        if any(c.level is HealthLevel.WARNING for c in self.checks):
            return HealthLevel.WARNING
        if not self.checks:
            return HealthLevel.UNKNOWN
        return HealthLevel.READY

    @property
    def is_blocked(self) -> bool:
        return self.level is HealthLevel.BLOCKED

    def by_name(self, name: str) -> Optional[CheckResult]:
        return next((c for c in self.checks if c.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "platform": self.platform,
            "python_version": self.python_version,
            "python_executable": self.python_executable,
            "conda_env": self.conda_env,
            "level": self.level.value,
            "checks": [c.to_dict() for c in self.checks],
        }

    def as_text(self) -> str:
        """Plain-text rendering, safe to paste into a support message."""
        marks = {
            HealthLevel.READY: "[ OK ]",
            HealthLevel.WARNING: "[WARN]",
            HealthLevel.BLOCKED: "[STOP]",
            HealthLevel.UNKNOWN: "[ ?? ]",
        }
        lines = [
            f"{self.app_name} {self.app_version} - ortam tanılaması",
            "=" * 66,
            f"Platform     : {self.platform}",
            f"Python       : {self.python_version}",
            f"Interpreter  : {self.python_executable}",
            f"Conda env    : {self.conda_env or '(bilinmiyor)'}",
            "",
            f"Genel durum  : {self.level.value.upper()}",
            "",
        ]
        for check in self.checks:
            value = f" - {check.value}" if check.value else ""
            lines.append(f"{marks[check.level]} {check.name}{value}")
            lines.append(f"       {check.message}")
            if check.remedy:
                lines.append(f"       -> {check.remedy}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _conda_env_name() -> str:
    name = os.environ.get("CONDA_DEFAULT_ENV", "")
    if name:
        return name
    # Fall back to the interpreter path: `.../envs/<name>/python.exe`.
    parts = Path(sys.executable).parts
    if "envs" in parts:
        index = parts.index("envs")
        if index + 1 < len(parts):
            return parts[index + 1]
    return ""


def check_interpreter() -> CheckResult:
    """Confirm the app is running inside the expected environment."""
    env = _conda_env_name()
    detail = f"Python {sys.version.split()[0]} @ {sys.executable}"
    if env.lower() == "kinesynth":
        return CheckResult(
            name="Python ortamı",
            level=HealthLevel.READY,
            message=f"KineSynth environment kullanılıyor. {detail}",
            value=env,
        )
    return CheckResult(
        name="Python ortamı",
        level=HealthLevel.WARNING,
        message=(
            f"Beklenen 'KineSynth' environment yerine '{env or 'bilinmeyen'}' "
            f"kullanılıyor. {detail}"
        ),
        remedy="Uygulamayı scripts\\run_app.ps1 ile başlatın.",
        value=env or "?",
    )


def _probe_module(module_name: str, label: str, *, required: bool) -> CheckResult:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        return CheckResult(
            name=label,
            level=HealthLevel.BLOCKED if required else HealthLevel.WARNING,
            message=f"Yüklenemedi: {type(exc).__name__}: {exc}",
            remedy=(
                'conda run -n KineSynth python -m pip install -e ".[dev]"'
                if required
                else "Bu paket olmadan bazı özellikler devre dışı kalır."
            ),
        )
    version = getattr(module, "__version__", "") or ""
    return CheckResult(
        name=label,
        level=HealthLevel.READY,
        message=f"Kullanılabilir{f' (sürüm {version})' if version else ''}.",
        value=version,
    )


def check_packages() -> list[CheckResult]:
    results = [
        _probe_module(name, label, required=True) for name, label in _REQUIRED_MODULES
    ]
    results.extend(
        _probe_module(name, label, required=False) for name, label in _OPTIONAL_MODULES
    )
    return results


def check_zed_sdk() -> list[CheckResult]:
    """ZED SDK, ``pyzed`` and camera availability - each reported separately."""
    from kinecapture.camera.zed import (
        is_pyzed_available,
        list_devices,
        pyzed_import_error,
        sdk_version,
    )

    results: list[CheckResult] = []
    if not is_pyzed_available():
        results.append(
            CheckResult(
                name="ZED SDK (pyzed)",
                level=HealthLevel.WARNING,
                message=(
                    "ZED Python modülü bulunamadı. Sentetik backend ile "
                    "çalışmaya devam edilebilir."
                ),
                remedy=(
                    "ZED SDK kurulumundaki get_python_api.py betiğini KineSynth "
                    "environment içinde çalıştırın."
                ),
                details={"import_error": pyzed_import_error()},
            )
        )
        results.append(
            CheckResult(
                name="ZED kamera",
                level=HealthLevel.WARNING,
                message="SDK olmadan kamera sorgulanamıyor.",
                remedy="Önce ZED SDK Python bağlamasını kurun.",
            )
        )
        return results

    version = sdk_version() or "bilinmiyor"
    results.append(
        CheckResult(
            name="ZED SDK (pyzed)",
            level=HealthLevel.READY,
            message=f"ZED SDK {version} kullanılabilir.",
            value=version,
        )
    )

    devices = list_devices()
    if not devices:
        results.append(
            CheckResult(
                name="ZED kamera",
                level=HealthLevel.WARNING,
                message="Bağlı ZED kamera bulunamadı.",
                remedy="Kamerayı USB 3.0 portuna takın.",
            )
        )
        return results

    available = [d for d in devices if d["state"].upper().endswith("AVAILABLE")]
    if not available:
        results.append(
            CheckResult(
                name="ZED kamera",
                level=HealthLevel.BLOCKED,
                message="Kamera bulundu fakat başka bir uygulama tarafından kullanılıyor.",
                remedy="Kamerayı kullanan diğer uygulamaları kapatın.",
                details={"devices": devices},
            )
        )
        return results

    first = available[0]
    results.append(
        CheckResult(
            name="ZED kamera",
            level=HealthLevel.READY,
            message=f"{first['model']} hazır (S/N {first['serial_number']}).",
            value=first["model"],
            details={"devices": devices},
        )
    )
    return results


def check_dataset_root(path: Path) -> list[CheckResult]:
    """Writability and free space of the dataset root."""
    path = Path(path).expanduser()
    results: list[CheckResult] = []

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".kinecapture_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        results.append(
            CheckResult(
                name="Veri klasörü",
                level=HealthLevel.READY,
                message=f"Yazılabilir: {path}",
                value=str(path),
            )
        )
    except OSError as exc:
        results.append(
            CheckResult(
                name="Veri klasörü",
                level=HealthLevel.BLOCKED,
                message=f"Yazılamıyor: {path}",
                remedy="Klasör iznini kontrol edin veya farklı bir konum seçin.",
                details={"error": str(exc)},
            )
        )
        return results

    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        results.append(
            CheckResult(
                name="Disk alanı",
                level=HealthLevel.WARNING,
                message="Boş alan okunamadı.",
                details={"error": str(exc)},
            )
        )
        return results

    free_gb = usage.free / 1024**3
    minutes = usage.free / _BYTES_PER_SECOND_ESTIMATE / 60
    estimate = f"{free_gb:.1f} GB boş (~{minutes:.0f} dakika HD720/30 kayıt)"
    if free_gb < _DISK_BLOCKED_GB:
        level, remedy = HealthLevel.BLOCKED, "Kayıt için yer açın."
    elif free_gb < _DISK_WARNING_GB:
        level, remedy = HealthLevel.WARNING, "Uzun oturumlar için yer açmayı düşünün."
    else:
        level, remedy = HealthLevel.READY, ""
    results.append(
        CheckResult(
            name="Disk alanı",
            level=level,
            message=estimate,
            remedy=remedy,
            value=f"{free_gb:.1f} GB",
            details={
                "free_bytes": usage.free,
                "total_bytes": usage.total,
                "estimated_minutes": round(minutes, 1),
            },
        )
    )
    return results


def check_backend(kind: BackendKind) -> CheckResult:
    """Probe the selected backend without opening hardware."""
    from kinecapture.camera import create_backend

    try:
        backend = create_backend(kind)
        result = backend.is_available()
    except Exception as exc:
        return CheckResult(
            name="Seçili backend",
            level=HealthLevel.BLOCKED,
            message=f"Backend hazırlanamadı: {exc}",
            value=str(kind),
        )
    return CheckResult(
        name="Seçili backend",
        level=result.level,
        message=result.message,
        remedy=result.remedy,
        value=kind.value if isinstance(kind, BackendKind) else str(kind),
        details=dict(result.details),
    )


def collect_diagnostics(
    *, dataset_root: Optional[Path] = None, backend: Optional[BackendKind] = None
) -> DiagnosticsReport:
    """Assemble the full report. Never raises."""
    report = DiagnosticsReport(
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        python_executable=sys.executable,
        conda_env=_conda_env_name(),
    )
    report.checks.append(check_interpreter())
    report.checks.extend(check_packages())
    report.checks.extend(check_zed_sdk())
    if dataset_root is not None:
        report.checks.extend(check_dataset_root(dataset_root))
    if backend is not None:
        report.checks.append(check_backend(backend))
    return report


def estimate_recording_minutes(free_bytes: int) -> float:
    """How long a HD720/30 recording fits in ``free_bytes``."""
    return free_bytes / _BYTES_PER_SECOND_ESTIMATE / 60.0


__all__ = [
    "CheckResult",
    "DiagnosticsReport",
    "check_backend",
    "check_dataset_root",
    "check_interpreter",
    "check_packages",
    "check_zed_sdk",
    "collect_diagnostics",
    "estimate_recording_minutes",
]
