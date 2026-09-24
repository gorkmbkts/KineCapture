"""``python -m kinecapture --self-check``: can this installation start?

Headless and console-free. Everything the application needs before its first
window is checked the way the application itself gets it - configuration and
resources through :mod:`importlib.resources`, the Qt platform plugin, the
fonts, the icons, the preview models, the ZED binding - and then the real
Studio window is built once, offscreen, on a throwaway configuration, so the
start-up path is exercised rather than described.

The result is a JSON report written to a file, because ``pythonw.exe`` has no
console to print it on, plus an exit code: 0 when everything required is in
order. Nothing is written to the user's data: the window is built on a
sandbox under the temp folder that is removed afterwards, and the user's
folders are only asked whether they could be written to.

The installer runs this after unpacking (``--expect-zed-sdk 5.4.1
--require-preview-models``) and refuses to call an installation finished
until it passes.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from kinecapture import APP_NAME, APP_VERSION


@dataclass
class Check:
    ok: bool
    detail: str = ""
    required: bool = True
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "required": self.required, "detail": self.detail, **self.data}


def _guard(name: str, function: Callable[[], Check], checks: dict[str, Check]) -> None:
    """Run one check; an exception is that check failing, not the whole run."""
    try:
        checks[name] = function()
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        checks[name] = Check(False, f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------- checks
def _python() -> Check:
    return Check(
        True,
        f"Python {platform.python_version()}",
        data={
            "executable": sys.executable,
            "prefix": sys.prefix,
            "windows": platform.platform(),
        },
    )


def _package() -> Check:
    import kinecapture

    location = Path(kinecapture.__file__).resolve().parent
    editable = (location.parent.parent / "pyproject.toml").is_file()
    return Check(
        True,
        f"{APP_NAME} {APP_VERSION}",
        data={"location": str(location), "from_checkout": editable},
    )


def _config() -> Check:
    from kinecapture.core.config import default_config_path, load_config

    path = default_config_path()
    if not path.is_file():
        return Check(False, f"Varsayılan ayar dosyası yok: {path}")
    config = load_config(path, include_user_state=False)
    return Check(
        True,
        "Paketle gelen varsayılan ayarlar okundu.",
        data={"path": str(path), "backend": config.backend.value},
    )


def _resources() -> Check:
    from importlib import resources

    from kinecapture.gui.assets import YTU_LOGO, asset_bytes
    from kinecapture.studio.theme import load_tokens, stylesheet_for
    from kinecapture.studio.views import iconset
    from kinecapture.studio.views.fonts import BRAND_FONT_FILE, font_bytes

    icons = iconset.available()
    icon_files = resources.files("kinecapture.studio.views.icons")
    missing: list[str] = [
        f"{iconset.ICON_NAMES.get(name, name)}.svg"
        for name in icons
        if not icon_files.joinpath(f"{iconset.ICON_NAMES.get(name, name)}.svg").is_file()
    ]
    if not asset_bytes(YTU_LOGO):
        missing.append(YTU_LOGO)
    if not font_bytes():
        missing.append(BRAND_FONT_FILE)
    for theme in ("dark", "light"):
        load_tokens(theme)
        if not stylesheet_for(theme):
            missing.append(f"stylesheet:{theme}")
    if len(icons) < 10:
        missing.append(f"icons ({len(icons)})")
    for package, name in (
        ("kinecapture.preview.vendor", "LICENSE"),
        ("kinecapture.studio.views.icons", "LICENSE.lucide.txt"),
        ("kinecapture.studio.views.fonts", "OFL.txt"),
    ):
        if not resources.files(package).joinpath(name).is_file():
            missing.append(name)
    if missing:
        return Check(False, "Eksik kaynak: " + ", ".join(missing))
    return Check(True, f"Tema, yazı tipi, logo ve {len(icons)} ikon bulundu.", data={"icons": len(icons)})


def _preview_models(required: bool) -> Check:
    from kinecapture.core.fingerprint import hash_file
    from kinecapture.preview.pose import PREVIEW_MODELS, find_model_dir, model_dirs

    directory = find_model_dir()
    if directory is None:
        return Check(
            False,
            "Hafif poz önizleme modelleri bulunamadı; kişi seçimi yapılamaz.",
            required=required,
            data={"searched": [str(p) for p in model_dirs()]},
        )
    wrong = [
        name for name, digest in PREVIEW_MODELS.items()
        if hash_file(directory / name) != digest
    ]
    if wrong:
        return Check(
            False,
            "Önizleme modeli beklenen içerikte değil: " + ", ".join(wrong),
            required=required,
            data={"directory": str(directory)},
        )
    return Check(True, "Önizleme modelleri doğrulandı.", required=required, data={"directory": str(directory)})


def _qt() -> Check:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import QLibraryInfo

    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    wanted = ["platforms/qwindows.dll"] if os.name == "nt" else []
    missing = [name for name in wanted if not (plugins / name).is_file()]
    if missing:
        return Check(False, f"Qt eklentisi eksik: {', '.join(missing)} ({plugins})")
    return Check(True, f"PySide6 {pyside_version}", data={"plugins": str(plugins)})


def _window() -> Check:
    """Build the real Studio window once, offscreen, on a throwaway config."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from kinecapture.core.config import AppConfig
    from kinecapture.studio.app import build_window
    from kinecapture.studio.views.theming import apply_application_theme

    application = QApplication.instance() or QApplication([sys.argv[0]])
    sandbox = Path(tempfile.mkdtemp(prefix="kinecapture_selfcheck_"))
    try:
        config = AppConfig.sandboxed(sandbox)
        apply_application_theme(config.theme)
        started = time.perf_counter()
        window = build_window(config, state_path=sandbox / "window_state.json")
        window.show()
        for _ in range(5):
            application.processEvents()
        page = window.viewmodel.active_page.value
        signed_in = window.viewmodel.session.user is not None
        window.close()
        window.deleteLater()
        application.processEvents()
        seconds = time.perf_counter() - started
        return Check(
            True,
            "Studio penceresi başsız kuruldu ve kapandı.",
            data={
                "platform": application.platformName(),
                "first_page": str(getattr(page, "value", page)),
                "signed_in": signed_in,
                "build_seconds": round(seconds, 3),
            },
        )
    finally:
        import shutil

        shutil.rmtree(sandbox, ignore_errors=True)


def _user_dirs() -> Check:
    """Could the application write where it keeps things? Nothing is created."""
    from kinecapture.core.config import AppConfig, USER_STATE_DIR, default_application_data_dir

    config = AppConfig()
    places = {
        "application_data": default_application_data_dir(),
        "datasets": config.dataset_root,
        "logs": config.log_dir,
        "preferences": USER_STATE_DIR,
    }
    report: dict[str, Any] = {}
    failing = []
    for name, path in places.items():
        probe = Path(path)
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        writable = os.access(probe, os.W_OK)
        report[name] = {"path": str(path), "nearest_existing": str(probe), "writable": writable}
        if not writable:
            failing.append(name)
    if failing:
        return Check(False, "Yazılamayan kullanıcı klasörü: " + ", ".join(failing), data=report)
    return Check(True, "Kullanıcı klasörleri yazılabilir.", data=report)


def _pyzed_version() -> Optional[str]:
    """The installed binding's own version, from its metadata (no import)."""
    try:
        from importlib.metadata import version

        return version("pyzed")
    except Exception:  # noqa: BLE001 - absent or unreadable metadata
        return None


def _same_minor(binding: str, sdk: str) -> bool:
    return binding.split(".")[:2] == sdk.split(".")[:2]


def _zed(expected: Optional[str]) -> Check:
    from kinecapture.camera.zed import (
        is_pyzed_available,
        pyzed_import_error,
        sdk_bin_directory,
        sdk_version,
    )

    required = expected is not None
    binding = _pyzed_version()
    directory = sdk_bin_directory()
    data: dict[str, Any] = {
        "pyzed_version": binding,
        "sdk_bin": str(directory) if directory else None,
    }
    if not is_pyzed_available():
        return Check(
            False,
            "ZED SDK Python modülü (pyzed) yüklenemedi; kamera kullanılamaz, "
            f"diğer ekranlar çalışır. Ayrıntı: {pyzed_import_error()}",
            required=required,
            data=data,
        )
    version = sdk_version()
    data["sdk_version"] = version
    if expected is not None and version != expected:
        return Check(
            False,
            f"ZED SDK {version} bulundu, {expected} gerekiyor.",
            required=True,
            data=data,
        )
    if expected is not None and (binding is None or version is None or not _same_minor(binding, version)):
        return Check(
            False,
            f"pyzed {binding} ile ZED SDK {version} aynı sürüm ailesinden değil.",
            required=True,
            data=data,
        )
    return Check(True, f"ZED SDK {version}, pyzed {binding}", required=required, data=data)


# --------------------------------------------------------------------- run
def run_self_check(
    report_path: Path,
    *,
    expect_zed_sdk: Optional[str] = None,
    require_preview_models: bool = False,
) -> int:
    """Run every check, write the report, return the process exit code."""
    import logging

    logger = logging.getLogger("kinecapture.self_check")
    logger.info("self-check başladı (%s)", sys.executable)
    started = time.perf_counter()
    checks: dict[str, Check] = {}
    _guard("python", _python, checks)
    _guard("package", _package, checks)
    _guard("config", _config, checks)
    _guard("resources", _resources, checks)
    _guard("preview_models", lambda: _preview_models(require_preview_models), checks)
    _guard("qt", _qt, checks)
    _guard("window", _window, checks)
    _guard("user_dirs", _user_dirs, checks)
    _guard("zed", lambda: _zed(expect_zed_sdk), checks)

    ok = all(check.ok for check in checks.values() if check.required)
    report = {
        "app": APP_NAME,
        "version": APP_VERSION,
        "ok": ok,
        "console": sys.stdout is not None and sys.stderr is not None,
        "seconds": round(time.perf_counter() - started, 3),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "checks": {name: check.to_dict() for name, check in checks.items()},
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, check in checks.items():
        level = logging.INFO if check.ok or not check.required else logging.ERROR
        logger.log(level, "self-check %s: %s %s", name, "OK" if check.ok else "HATA", check.detail)
    logger.info("self-check bitti: %s (%s)", "geçti" if ok else "başarısız", report_path)
    if sys.stdout is not None:
        for name, check in checks.items():
            mark = "OK  " if check.ok else ("HATA" if check.required else "not ")
            print(f"  [{mark}] {name:15} {check.detail}")
        print(f"\nRapor: {report_path}")
    return 0 if ok else 1


__all__ = ["Check", "run_self_check"]
