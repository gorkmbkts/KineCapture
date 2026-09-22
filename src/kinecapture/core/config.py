"""Application configuration.

Two kinds of setting are deliberately kept apart:

* **User preferences** - window theme, preview throttle, log level, last opened
  project. These live in ``configs/default.yaml`` plus a per-user overlay and
  may change at any time without affecting stored data.
* **Capture provenance** - resolution, fps, depth mode, body format. Those are
  copied into each take's :class:`~kinecapture.domain.project.CaptureProfile`
  at record time, so changing a preference later never rewrites the description
  of an existing recording.

Runtime directories (data, logs) never live inside the source tree.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

from kinecapture import APP_NAME
from kinecapture.core.errors import ConfigError
from kinecapture.domain.enums import BackendKind
from kinecapture.domain.project import CaptureProfile

#: Location of the shipped defaults, relative to the repository root.
DEFAULT_CONFIG_RELATIVE_PATH = Path("configs") / "default.yaml"

#: Where per-user overrides and the "last opened project" pointer are stored.
USER_STATE_DIR = Path.home() / ".kinecapture"
USER_STATE_PATH = USER_STATE_DIR / "user_state.yaml"

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_VALID_THEMES = ("dark", "light")

#: Directory names that mean "this tree belongs to a test or a measurement run".
#: A configuration pointing its data at one of these is a sandbox, whatever it
#: calls itself, and a sandbox is never allowed to rewrite the real preferences.
_SANDBOX_MARKERS = ("pytest-of-", ".pytest_cache", "scratchpad")


def _is_sandbox_location(path: Optional[Path]) -> bool:
    """True when ``path`` lives in a temporary or obviously disposable tree."""
    if path is None:
        return False
    try:
        resolved = Path(os.path.abspath(str(path)))
    except (OSError, ValueError):  # pragma: no cover - malformed path
        return False
    parts = [part.lower() for part in resolved.parts]
    if any(
        marker in part for part in parts for marker in _SANDBOX_MARKERS
    ):
        return True
    try:
        temp_root = Path(os.path.abspath(tempfile.gettempdir()))
    except (OSError, ValueError):  # pragma: no cover - no temp dir
        return False
    try:
        return resolved.is_relative_to(temp_root)
    except (AttributeError, ValueError):  # pragma: no cover - Python < 3.9
        return False


def _project_root() -> Path:
    """Repository root: ``src/kinecapture/core/config.py`` -> four levels up."""
    return Path(__file__).resolve().parents[3]


def default_config_path() -> Path:
    return _project_root() / DEFAULT_CONFIG_RELATIVE_PATH


def _resolve_user_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def default_application_data_dir() -> Path:
    """Deterministic per-user application data directory.

    Identity data is intentionally separate from both datasets and user
    preferences so it cannot be mistaken for a scientific project.
    """
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base.expanduser() / "KineCapture"


def default_identity_database_path() -> Path:
    return default_application_data_dir() / "identity.sqlite3"


@dataclass
class MockSettings:
    """Settings for the synthetic backend (development and automated tests)."""

    width: int = 960
    height: int = 540
    fps: float = 30.0
    seed: int = 1234
    num_bodies: int = 1
    enable_depth: bool = True
    tracking_loss_every: int = 0
    low_confidence_every: int = 0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ConfigError("mock.width ve mock.height pozitif olmalıdır.")
        if self.fps <= 0:
            raise ConfigError("mock.fps 0'dan büyük olmalıdır.")
        if self.num_bodies < 1:
            raise ConfigError("mock.num_bodies en az 1 olmalıdır.")


@dataclass
class AppConfig:
    """Effective runtime settings."""

    app_name: str = APP_NAME
    backend: BackendKind = BackendKind.MOCK
    theme: str = "dark"
    language: str = "tr"
    preview_fps: float = 30.0
    log_level: str = "INFO"
    autosave_enabled: bool = True
    autosave_delay_ms: int = 800
    dataset_root: Path = field(
        default_factory=lambda: Path.home() / "KineCapture" / "datasets"
    )
    log_dir: Path = field(default_factory=lambda: Path.home() / "KineCapture" / "logs")
    last_project_path: Optional[Path] = None
    #: Injected in tests; defaults to the OS-local application data folder.
    #: This path is not written to the user preference file.
    identity_db_path: Optional[Path] = None
    #: Where :func:`save_user_state` writes. Part of the configuration rather
    #: than a module constant, because *every* other location this object
    #: carries - datasets, identity, logs - can be pointed at a sandbox, and a
    #: preference file that stayed global while they moved is exactly how a
    #: measurement run's temporary dataset root became the user's real one on
    #: 20 September. Code sets it; a settings file never can (see
    #: :meth:`from_mapping`), so a stale or hostile YAML cannot redirect it.
    user_state_path: Optional[Path] = None
    #: The only login value preferences may remember. Passwords are never saved.
    last_username: str = ""
    #: Feature ids the export screen was last configured with. A preference,
    #: not a contract: unknown ids are dropped when the registry loads them, so
    #: a stale settings file can never inject a feature that no longer exists.
    export_feature_ids: list[str] = field(default_factory=list)
    capture: CaptureProfile = field(default_factory=CaptureProfile)
    mock: MockSettings = field(default_factory=MockSettings)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.backend, str):
            try:
                self.backend = BackendKind(self.backend.lower())
            except ValueError as exc:
                raise ConfigError(
                    f"Bilinmeyen backend: {self.backend}. "
                    f"Geçerli değerler: {', '.join(b.value for b in BackendKind)}"
                ) from exc
        if isinstance(self.capture, Mapping):
            self.capture = CaptureProfile.for_new_capture(self.capture)
        if isinstance(self.mock, Mapping):
            known = {f.name for f in fields(MockSettings)}
            self.mock = MockSettings(**{k: v for k, v in self.mock.items() if k in known})

        self.dataset_root = _resolve_user_path(self.dataset_root)
        self.log_dir = _resolve_user_path(self.log_dir)
        if self.last_project_path is not None:
            self.last_project_path = _resolve_user_path(self.last_project_path)
        self.identity_db_path = _resolve_user_path(
            self.identity_db_path or default_identity_database_path()
        )
        self.user_state_path = _resolve_user_path(
            self.user_state_path or USER_STATE_PATH
        )

        if self.preview_fps <= 0:
            raise ConfigError("preview_fps 0'dan büyük olmalıdır.")
        if self.log_level not in _VALID_LOG_LEVELS:
            raise ConfigError(
                f"Geçersiz log_level: {self.log_level}. "
                f"Geçerli değerler: {', '.join(_VALID_LOG_LEVELS)}"
            )
        if self.theme not in _VALID_THEMES:
            raise ConfigError(
                f"Geçersiz tema: {self.theme}. "
                f"Geçerli değerler: {', '.join(_VALID_THEMES)}"
            )
        if self.autosave_delay_ms < 0:
            raise ConfigError("autosave_delay_ms negatif olamaz.")

    @property
    def is_sandboxed(self) -> bool:
        """True when this configuration's data lives in a disposable tree.

        Read by :func:`save_user_state`, which refuses to write such a
        configuration into the real per-user preference file.
        """
        return any(
            _is_sandbox_location(path)
            for path in (self.dataset_root, self.identity_db_path, self.log_dir)
        )

    @classmethod
    def sandboxed(cls, root: Path | str, **overrides: Any) -> "AppConfig":
        """A configuration whose *every* location is under ``root``.

        The one supported way for a test or a measurement script to build a
        window: datasets, identity, logs and the preference file move
        together. Moving three of the four is what leaked a temporary dataset
        root into the user's settings.
        """
        base = Path(root).expanduser()
        return cls(
            dataset_root=base / "datasets",
            identity_db_path=base / "identity.sqlite3",
            log_dir=base / "logs",
            user_state_path=base / "user_state.yaml",
            **overrides,
        )

    @property
    def preview_interval_ms(self) -> int:
        """GUI timer interval derived from the preview throttle (>= 1 ms)."""
        return max(1, int(round(1000.0 / self.preview_fps)))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AppConfig":
        # ``user_state_path`` is deliberately not loadable: a preferences file
        # that could name the preferences file is a file that can redirect
        # every later save away from itself.
        known = {
            f.name for f in fields(cls) if f.name not in ("extra", "user_state_path")
        }
        kwargs = {k: v for k, v in payload.items() if k in known}
        extra = {k: v for k, v in payload.items() if k not in known}
        config = cls(**kwargs)
        config.extra.update(extra)
        return config

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_name": self.app_name,
            "backend": self.backend.value,
            "theme": self.theme,
            "language": self.language,
            "preview_fps": self.preview_fps,
            "log_level": self.log_level,
            "autosave_enabled": self.autosave_enabled,
            "autosave_delay_ms": self.autosave_delay_ms,
            "dataset_root": str(self.dataset_root),
            "log_dir": str(self.log_dir),
            "last_project_path": (
                str(self.last_project_path) if self.last_project_path else None
            ),
            "identity_db_path": str(self.identity_db_path),
            "last_username": self.last_username,
            "export_feature_ids": list(self.export_feature_ids),
            "capture": self.capture.to_dict(),
            "mock": asdict(self.mock),
            **self.extra,
        }


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Ayar dosyası okunamadı: {path.name}",
            remedy="YAML sözdizimini kontrol edin.",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    except OSError as exc:
        raise ConfigError(
            f"Ayar dosyasına erişilemedi: {path.name}",
            details={"path": str(path), "error": str(exc)},
        ) from exc
    if not isinstance(raw, Mapping):
        raise ConfigError(f"Ayar dosyası bir sözlük içermelidir: {path.name}")
    return dict(raw)


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Merge ``overlay`` into ``base``, recursing into nested mappings."""
    result = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(dict(result[key]), value)
        else:
            result[key] = value
    return result


def load_config(
    path: Optional[Path] = None,
    *,
    include_user_state: bool = True,
    user_state_path: Optional[Path] = None,
) -> AppConfig:
    """Load shipped defaults, then the per-user overlay on top.

    A missing file is not an error: the dataclass defaults are usable on their
    own. A malformed file *is* an error, reported with the file path so the user
    can find it.
    """
    candidate = Path(path) if path is not None else default_config_path()
    state_path = Path(user_state_path) if user_state_path is not None else USER_STATE_PATH
    payload: dict[str, Any] = {}
    if candidate.is_file():
        payload = _read_yaml(candidate)
    if include_user_state and state_path.is_file():
        overlay = _read_yaml(state_path)
        if isinstance(overlay.get("capture"), Mapping):
            overlay["capture"] = CaptureProfile.for_new_capture(overlay["capture"]).to_dict()
        payload = _deep_merge(payload, overlay)
    try:
        config = AppConfig.from_mapping(payload)
        # The file it was read from is the file it will be written back to.
        config.user_state_path = _resolve_user_path(state_path)
        return config
    except ConfigError:
        raise
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"Ayar dosyasında geçersiz değer: {candidate.name}",
            details={"path": str(candidate), "error": str(exc)},
        ) from exc


def save_user_state(config: AppConfig) -> Path:
    """Persist the user-changeable subset of ``config``.

    Only preferences are written. Capture provenance is intentionally excluded:
    it belongs to takes already on disk, not to a global preference file.

    The destination is ``config.user_state_path``, so a configuration built for
    a sandbox saves inside that sandbox. Writing a sandboxed configuration to
    the *real* preference file is refused outright.
    """
    target = Path(config.user_state_path or USER_STATE_PATH)
    if config.is_sandboxed and not _is_sandbox_location(target):
        # A configuration whose datasets, identity or logs sit in a temporary
        # tree is a test or a measurement run. Letting one write a preference
        # file *outside* that tree is how ``dataset_root`` became a scratchpad
        # path on 20 September, and how the next recording was aimed at a
        # 281-character target the SDK could not open. The rule is one
        # sentence: sandboxed data saves to a sandboxed preference file, or it
        # does not save. A redirected preference file inside the sandbox -
        # what the test suite sets up - is fine, and stays fine.
        raise ConfigError(
            "Geçici veri köklü ayar gerçek kullanıcı tercihine yazılamaz.",
            remedy=(
                "Sanal çalışma için AppConfig.sandboxed(root) kullanın; "
                "tercih dosyası da o kökün altına yazılır."
            ),
            details={
                "user_state_path": str(target),
                "dataset_root": str(config.dataset_root),
                "identity_db_path": str(config.identity_db_path),
            },
        )
    state = {
        "backend": config.backend.value,
        "theme": config.theme,
        "language": config.language,
        "preview_fps": config.preview_fps,
        "log_level": config.log_level,
        "autosave_enabled": config.autosave_enabled,
        "autosave_delay_ms": config.autosave_delay_ms,
        "dataset_root": str(config.dataset_root),
        "last_project_path": (
            str(config.last_project_path) if config.last_project_path else None
        ),
        "last_username": config.last_username,
        "export_feature_ids": list(config.export_feature_ids),
        "capture": config.capture.to_dict(),
        "mock": asdict(config.mock),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".yaml.tmp")
    try:
        tmp.write_text(
            yaml.safe_dump(state, allow_unicode=True, sort_keys=True), encoding="utf-8"
        )
        tmp.replace(target)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ConfigError(
            "Kullanıcı ayarları kaydedilemedi.",
            details={"path": str(target), "error": str(exc)},
        ) from exc
    return target


__all__ = [
    "AppConfig",
    "ConfigError",
    "MockSettings",
    "USER_STATE_PATH",
    "default_application_data_dir",
    "default_config_path",
    "default_identity_database_path",
    "load_config",
    "save_user_state",
]
