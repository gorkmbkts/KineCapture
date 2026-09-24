"""Building the KineCapture installer: compile, compose, scan, assemble.

The installer is one file: a small .NET Framework program
(``installer/KineCaptureSetup.cs``, compiled with the ``csc.exe`` every
Windows 10/11 already has) followed by a ZIP payload and a 16-byte trailer
(payload length, ``KCSETUP1``). Nothing here downloads anything.

The payload is the release environment packed by ``conda-pack`` plus an
``install.json`` that tells the installer what to run after unpacking and how
to verify the result. While the payload is written every file is listed in a
content manifest and scanned; a single finding fails the build:

* data that must never ship: ``*.sqlite3``, ``*.db``, ``*.svo``, ``*.svo2``,
  ``run_*`` folders, ``*.log`` files, identity data;
* the build machine's Windows user name or a ``C:\\Users\\...`` path, in a
  file name or anywhere in a file's bytes (UTF-8 and UTF-16);
* anything that looks like a plaintext password (see :func:`password_suspects`);
* an owner seed that is not a digest-only seed.

Standard library only; used by ``build_installer.ps1`` and by the tests.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tarfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional, Union

REPO = Path(__file__).resolve().parents[2]
INSTALLER_DIR = Path(__file__).resolve().parent / "installer"
SOURCE = INSTALLER_DIR / "KineCaptureSetup.cs"
APP_MANIFEST = INSTALLER_DIR / "app.manifest"
MAGIC = b"KCSETUP1"
REFERENCES = (
    "System.Management.dll",
    "System.Web.Extensions.dll",
    "System.IO.Compression.dll",
    "System.IO.Compression.FileSystem.dll",
    "System.Windows.Forms.dll",
    "System.Drawing.dll",
    "Microsoft.CSharp.dll",
    "System.Core.dll",
)
PYC_TAG = "cpython-311"
#: Folders compileall leaves alone at install time: test suites of the
#: packages, a few of which do not even compile on this Python.
COMPILE_EXCLUDE = r"[\\/](tests?|testing|test_data|idle_test)[\\/]"


# ---------------------------------------------------------------- compiling
def find_csc() -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for bits in ("Framework64", "Framework"):
        candidate = windir / "Microsoft.NET" / bits / "v4.0.30319" / "csc.exe"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(".NET Framework 4 C# derleyicisi (csc.exe) bulunamadı.")


def compile_stub(out: Path, *, icon: Optional[Path] = None, source: Path = SOURCE) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(find_csc()), "-nologo", "-codepage:65001", "-target:winexe", "-platform:anycpu",
        "-optimize+", f"-out:{out}",
    ]
    if APP_MANIFEST.is_file():
        command.append(f"-win32manifest:{APP_MANIFEST}")
    if icon is not None and Path(icon).is_file():
        command.append(f"-win32icon:{icon}")
    command += [f"-reference:{name}" for name in REFERENCES]
    command.append(str(source))
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError("Kurucu derlenemedi:\n" + result.stdout + result.stderr)
    return out


def assemble(stub: Path, payload: Path, out: Path) -> Path:
    """``stub`` + ``payload`` + (payload length, MAGIC) -> ``out``."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    length = Path(payload).stat().st_size
    temporary = out.with_name(out.name + ".partial")
    with open(temporary, "wb") as target:
        for part in (stub, payload):
            with open(part, "rb") as source:
                while chunk := source.read(1 << 22):
                    target.write(chunk)
        target.write(struct.pack("<q", length) + MAGIC)
    os.replace(temporary, out)
    return out


def read_trailer(installer: Path) -> tuple[int, int]:
    """(offset, length) of the payload inside ``installer``."""
    with open(installer, "rb") as stream:
        stream.seek(-16, os.SEEK_END)
        trailer = stream.read(16)
        size = stream.tell()
    if trailer[8:] != MAGIC:
        raise ValueError("Kurulum yükü bulunamadı.")
    length = struct.unpack("<q", trailer[:8])[0]
    return size - 16 - length, length


def open_payload(installer: Path) -> zipfile.ZipFile:
    offset, length = read_trailer(installer)
    stream = open(installer, "rb")
    stream.seek(offset)
    data = io.BytesIO(stream.read(length)) if length < (64 << 20) else _Window(stream, offset, length)
    return zipfile.ZipFile(data)


class _Window(io.RawIOBase):
    """A read-only view of ``length`` bytes at ``offset`` (large payloads)."""

    def __init__(self, stream, offset: int, length: int) -> None:  # noqa: ANN001
        self._stream, self._offset, self._length, self._position = stream, offset, length, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, position: int, whence: int = 0) -> int:
        base = {0: 0, 1: self._position, 2: self._length}[whence]
        self._position = max(0, base + position)
        return self._position

    def readinto(self, buffer) -> int:  # noqa: ANN001
        left = self._length - self._position
        if left <= 0:
            return 0
        self._stream.seek(self._offset + self._position)
        data = self._stream.read(min(len(buffer), left))
        buffer[: len(data)] = data
        self._position += len(data)
        return len(data)


# -------------------------------------------------------------------- icon
def render_icon(out: Path) -> Optional[Path]:
    """The application's crest as a multi-size ``.ico`` (PNG entries)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtWidgets import QApplication

        from kinecapture.studio.theme import load_tokens
        from kinecapture.studio.views.brand import crest_pixmap
    except Exception:  # noqa: BLE001 - the icon is decoration; the build goes on
        return None
    application = QApplication.instance() or QApplication([])  # noqa: F841 - pixmaps need it
    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = crest_pixmap(load_tokens("light"), size=size, plate=True)
        if pixmap is None:
            return None
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.toImage().save(buffer, "PNG")
        buffer.close()
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    directory, blobs = b"", b""
    offset = 6 + 16 * len(images)
    for size, png in images:
        edge = 0 if size >= 256 else size
        directory += struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + directory + blobs)
    return out


# ------------------------------------------------------------------ scanning
@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"rule": self.rule, "path": self.path, "detail": self.detail}


_DATA_SUFFIXES = (".sqlite3", ".db", ".svo", ".svo2", ".log")
_CODE_SUFFIXES = (".py", ".pyi", ".pyc", ".pyd", ".dll", ".h", ".hpp", ".cmake", ".html", ".txt", ".js")
_RUN_DIR = re.compile(r"^run_[0-9a-z]+$", re.IGNORECASE)
_PASSWORD_JSON = re.compile(rb'"(?:password|parola|sifre|\xc5\x9fifre)"\s*:\s*"([^"]{1,256})"', re.IGNORECASE)
_PASSWORD_ASSIGN = re.compile(
    rb"""(?<![A-Za-z0-9_])(?:password|parola|sifre)\s*[:=]\s*["']([^"'\s]{6,})["']""", re.IGNORECASE
)
_USER_SEGMENT = re.compile(rb"[Cc]:(?:\\\\|\\|/)+[Uu][Ss][Ee][Rr][Ss](?:\\\\|\\|/)+([^\\/\s\"'<>:*?|\x00]{1,64})")
#: Profiles every Windows has; a path under one of them says nothing about
#: who built the release. Every other profile on the build machine does.
_STANDARD_PROFILES = {"all users", "default", "default user", "public", "desktop.ini"}


def name_findings(relative: str, *, username: str) -> list[Finding]:
    """Rules on the path alone. ``relative`` uses forward slashes."""
    findings = []
    lower = relative.lower()
    base = lower.rsplit("/", 1)[-1]
    if base.endswith(_DATA_SUFFIXES):
        findings.append(Finding("data_file", relative, "veri/log dosyası kurucuya giremez"))
    for part in lower.split("/")[:-1]:
        if _RUN_DIR.match(part):
            findings.append(Finding("run_dir", relative, f"işleme klasörü: {part}"))
            break
    if "identity" in base and not base.endswith(_CODE_SUFFIXES):
        findings.append(Finding("identity", relative, "kimlik verisi olabilir"))
    if username and username.lower() in lower:
        findings.append(Finding("username", relative, "dosya adında kullanıcı adı"))
    if "c:/users/" in lower or "c:\\users\\" in lower:
        findings.append(Finding("user_path", relative, "dosya adında kullanıcı klasörü"))
    return findings


_PATTERNS: dict = {}


def profile_pattern(names: Iterable[str], *, paths: bool = True) -> "re.Pattern[bytes]":
    """One regular expression for every spelling of ``names`` in a file.

    ``C:\\Users\\<name>`` with ``\\``, ``/`` or JSON's ``\\\\``, in UTF-8 and
    UTF-16LE. ``IGNORECASE`` folds ASCII only on bytes, so the name itself is
    also spelled as given, lower and upper case - which is what catches a
    Turkish ``Ş``/``ş`` that bytes-level case folding would miss.
    """
    key = (tuple(sorted(names)), paths)
    cached = _PATTERNS.get(key)
    if cached is not None:
        return cached
    alternatives = set()
    for name in names:
        for variant in {name, name.lower(), name.upper()}:
            texts = [variant]
            if paths:
                texts = [f"c:{sep}users{sep}{variant}" for sep in ("\\", "/", "\\\\")]
            for text in texts:
                for encoding in ("utf-8", "utf-16-le"):
                    alternatives.add(re.escape(text.encode(encoding)))
    pattern = re.compile(b"|".join(sorted(alternatives, key=len, reverse=True)), re.IGNORECASE)
    _PATTERNS[key] = pattern
    return pattern


def local_profiles() -> set[str]:
    """This machine's user profiles, minus the ones every Windows has."""
    root = Path(os.environ.get("SystemDrive", "C:") + "\\Users")
    try:
        names = {entry.name for entry in root.iterdir()}
    except OSError:
        names = set()
    return {name for name in names if name.lower() not in _STANDARD_PROFILES}


def content_findings(
    relative: str, data: bytes, *, username: str, profiles: Iterable[str] = (),
    foreign: Optional[dict] = None,
) -> list[Finding]:
    """The build machine's user in a file's bytes (UTF-8 and UTF-16).

    Two rules fail the build: the build user's name anywhere, and a path into
    any profile that exists on the build machine. A ``C:\\Users\\<name>`` path
    to a profile that does not exist here - the CI machine that compiled a
    third-party DLL (``runneradmin``, ``TASK_1~1``, ``qt``), an example in a
    docstring (``foo``, ``<username>``) - says nothing about this machine; it
    is counted in ``foreign`` and listed in the scan report, not hidden.
    """
    findings = []
    names = {p for p in profiles if p} | ({username} if username else set())
    if username:
        match = profile_pattern([username], paths=False).search(data)
        if match:
            context = data[max(0, match.start() - 40):match.end() + 40]
            findings.append(Finding("username", relative, _printable(context)))
    if names:
        match = profile_pattern(names).search(data)
        if match:
            context = data[max(0, match.start() - 20):match.end() + 40]
            findings.append(Finding("user_path", relative, _printable(context)))
    # A file that already fails needs no list of other people's paths; its
    # UTF-16 text, stripped of NULs, would only list the local name garbled.
    if foreign is not None and not findings:
        local = {p.lower() for p in profiles} | ({username.lower()} if username else set())
        for text in (data, data.replace(b"\x00", b"")):
            for match in _USER_SEGMENT.finditer(text):
                name = match.group(1).decode("utf-8", "replace")
                if name.lower() in local or name.lower() in _STANDARD_PROFILES:
                    continue
                entry = foreign.setdefault(name, {"count": 0, "example": relative})
                entry["count"] += 1
    return findings


def password_suspects(relative: str, data: bytes) -> list[Finding]:
    """Heuristic, stated as such: a JSON value or an assignment that pairs a
    password-like key with a literal. Applied to the application's own files
    and to every JSON/YAML/INI/text file at the top of the payload; third-
    party code is full of test fixtures that would drown a real finding."""
    findings = []
    for pattern in (_PASSWORD_JSON, _PASSWORD_ASSIGN):
        for match in pattern.finditer(data):
            findings.append(Finding("password_suspect", relative, _printable(match.group(0)[:80])))
    return findings


def _printable(data: bytes) -> str:
    return data.decode("utf-8", "replace").replace("\x00", "").replace("\n", " ")[:160]


def _wants_password_scan(relative: str) -> bool:
    lower = relative.lower()
    if "/site-packages/kinecapture/" in lower and not lower.endswith(".pyc"):
        return True
    if lower.startswith("env/share/kinecapture/"):
        return True
    return lower.count("/") <= 1 and lower.endswith((".json", ".yaml", ".yml", ".ini", ".cfg", ".txt"))


# ------------------------------------------------------------------ payload
@dataclass
class Manifest:
    files: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    unpacked_bytes: int = 0
    max_relative_path: int = 0
    #: ``C:\Users\<name>`` paths to profiles that do not exist on the build
    #: machine (third-party build machines, docstring examples): name ->
    #: {count, example}. Reported, not a failure.
    foreign_user_paths: dict = field(default_factory=dict)
    #: conda-unpack records removed because their file is not in the payload.
    unpack_records_dropped: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "files": len(self.files),
            "unpacked_bytes": self.unpacked_bytes,
            "max_relative_path": self.max_relative_path,
            "excluded": self.excluded,
            "unpack_records_dropped": self.unpack_records_dropped,
            "findings": [f.to_dict() for f in self.findings],
            "foreign_user_paths": self.foreign_user_paths,
            "entries": self.files,
        }


Source = Union[Path, bytes]


class PayloadWriter:
    """Writes the payload ZIP and, file by file, its manifest and scan."""

    def __init__(
        self, out: Path, *, username: str, profiles: Iterable[str] = (),
        compile_exclude: str = COMPILE_EXCLUDE,
    ) -> None:
        self.out = Path(out)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.zip = zipfile.ZipFile(self.out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True)
        self.username = username
        self.profiles = tuple(profiles)
        self.manifest = Manifest()
        self._compile_exclude = re.compile(compile_exclude)

    def add(self, arcname: str, data: bytes) -> None:
        arcname = arcname.replace("\\", "/")
        self.manifest.findings += name_findings(arcname, username=self.username)
        self.manifest.findings += content_findings(
            arcname, _without_owner_identity(arcname, data), username=self.username,
            profiles=self.profiles, foreign=self.manifest.foreign_user_paths,
        )
        if _wants_password_scan(arcname):
            self.manifest.findings += password_suspects(arcname, data)
        info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        already = _incompressible(arcname)
        self.zip.writestr(info, data, compress_type=zipfile.ZIP_STORED if already else zipfile.ZIP_DEFLATED,
                          compresslevel=None if already else 6)
        self.manifest.files.append(
            {"path": arcname, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
        self.manifest.unpacked_bytes += len(data)
        self._track_length(arcname)

    def _track_length(self, arcname: str) -> None:
        length = len(arcname)
        lower = arcname.lower()
        if lower.endswith(".py") and lower.startswith("env/lib/") and not self._compile_exclude.search(arcname):
            folder, name = arcname.rsplit("/", 1)
            # compileall will write folder/__pycache__/<stem>.cpython-311.pyc
            length = len(folder) + len("/__pycache__/") + len(name[:-3]) + len(f".{PYC_TAG}.pyc")
        self.manifest.max_relative_path = max(self.manifest.max_relative_path, length)

    def close(self) -> Manifest:
        self.zip.close()
        return self.manifest


SEED_ARCNAME = "env/share/kinecapture/owner_seed.json"


def _without_owner_identity(arcname: str, data: bytes) -> bytes:
    """The seed's own name fields blanked before the build-user scan.

    The owner's username (``gorkembektas``) contains the build machine's user
    name (``gorke``); in the one file whose purpose is to carry it, that is
    not a leak. Every other byte of the seed is still scanned, and
    :func:`_check_seed` validates the file field by field.
    """
    if arcname != SEED_ARCNAME:
        return data
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data
    if not isinstance(document, dict):
        return data
    for key in ("username", "first_name", "last_name"):
        if isinstance(document.get(key), str):
            document[key] = ""
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


def _incompressible(name: str) -> bool:
    return name.lower().endswith((".zip", ".whl", ".gz", ".xz", ".bz2", ".png", ".jpg", ".onnx", ".7z"))


def default_exclude(relative: str) -> Optional[str]:
    """Why ``relative`` (inside the environment) stays out, or ``None``."""
    lower = relative.lower()
    if "/__pycache__/" in f"/{lower}" or lower.endswith((".pyc", ".pyo")):
        return "bytecode: kurulumda hedef yolla derlenir"
    if lower == "conda-meta/history":
        return "conda geçmişi: derleme makinesinin yollarını taşır"
    if lower.startswith("lib/site-packages/pyzed/") and lower.endswith(".dll"):
        return "ZED SDK ikilileri: hedefte SDK'nın kendisinden yüklenir"
    if lower.startswith("scripts/") and lower.endswith(".exe") and lower != "scripts/conda-unpack.exe":
        # pip's launchers carry the absolute path of the interpreter they were
        # made for - the builder's KineSynth - and point nowhere once installed.
        return "komut başlatıcısı: derleme makinesinin yorumlayıcı yolunu taşır, uygulama kullanmaz"
    if lower.endswith(".pdb"):
        return "hata ayıklama sembolü: çalışma anında gerekmez"
    return None


UNPACK_SCRIPT = "Scripts/conda-unpack-script.py"


def filter_unpack_script(data: bytes, shipped: set) -> tuple[bytes, list]:
    """Drop conda-unpack's records for files the payload does not carry.

    ``conda-pack`` lists every file whose prefix ``conda-unpack`` must rewrite;
    a file left out of the payload (a launcher carrying the builder's path, a
    debug symbol, a stray ``*.pyc.<pid>``) would make it stop with
    ``FileNotFoundError`` - found by the first real install, 24 September 2026.
    """
    import ast

    lines = data.decode("utf-8").splitlines(keepends=True)
    kept, dropped, inside = [], [], False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("_prefix_records = ["):
            inside = True
        elif inside and stripped == "]":
            inside = False
        elif inside and stripped.startswith("(") and stripped.endswith("),"):
            path = ast.literal_eval(stripped[:-1])[0]
            if path.replace("\\", "/") not in shipped:
                dropped.append(path)
                continue
        kept.append(line)
    return "".join(kept).encode("utf-8"), dropped


def iter_tar(tar_path: Path) -> Iterator[tuple[str, bytes]]:
    with tarfile.open(tar_path, "r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            yield member.name.lstrip("./"), stream.read()


def compose(
    out: Path,
    *,
    environment: Iterable[tuple[str, bytes]],
    install: dict,
    extras: Optional[dict[str, Source]] = None,
    username: str,
    profiles: Iterable[str] = (),
    exclude: Callable[[str], Optional[str]] = default_exclude,
    required_margin: float = 0.25,
) -> Manifest:
    """Write the payload: ``env/`` from ``environment``, ``extras`` on top of
    it (keys relative to ``env/``), then ``install.json`` with the sizes the
    installer's preflight needs. ``profiles`` are the build machine's user
    profiles (:func:`local_profiles`); a path into any of them fails."""
    writer = PayloadWriter(out, username=username, profiles=profiles)
    extras = dict(extras or {})
    unpack_script: Optional[bytes] = None
    try:
        for relative, data in environment:
            reason = exclude(relative)
            if reason is not None:
                writer.manifest.excluded.append(f"{relative}: {reason}")
                continue
            if relative in extras:
                continue  # replaced below
            if relative == UNPACK_SCRIPT:
                unpack_script = data  # written last, when the payload is known
                continue
            writer.add("env/" + relative, data)
        for relative, source in sorted(extras.items()):
            data = source if isinstance(source, bytes) else Path(source).read_bytes()
            writer.add("env/" + relative, data)
        if unpack_script is not None:
            shipped = {entry["path"][len("env/"):] for entry in writer.manifest.files}
            filtered, dropped = filter_unpack_script(unpack_script, shipped)
            writer.manifest.unpack_records_dropped = dropped
            writer.add("env/" + UNPACK_SCRIPT, filtered)
        manifest = writer.manifest
        unpacked = manifest.unpacked_bytes
        install = dict(install)
        install["unpacked_bytes"] = unpacked
        install["files"] = len(manifest.files)
        requirements = dict(install.get("requirements", {}))
        requirements["required_bytes"] = int(unpacked * (1 + required_margin)) + (512 << 20)
        requirements["max_relative_path"] = manifest.max_relative_path
        install["requirements"] = requirements
        writer.zip.writestr("install.json", json.dumps(install, ensure_ascii=False, indent=1))
    finally:
        manifest = writer.close()
    _check_seed(extras, manifest)
    return manifest


def _check_seed(extras: dict, manifest: Manifest) -> None:
    for relative, source in extras.items():
        if not relative.endswith("owner_seed.json"):
            continue
        data = source if isinstance(source, bytes) else Path(source).read_bytes()
        try:
            from kinecapture.identity.seed import parse_owner_seed

            parse_owner_seed(json.loads(data.decode("utf-8")))
        except Exception as exc:  # noqa: BLE001
            manifest.findings.append(Finding("owner_seed", relative, f"özet dışı ya da geçersiz tohum: {exc}"))
    for entry in manifest.files:
        if entry["path"].endswith("owner_seed.json") and entry["path"] != "env/share/kinecapture/owner_seed.json":
            manifest.findings.append(Finding("owner_seed", entry["path"], "tohum yalnız share/kinecapture altında olur"))


def installer_install_json(version: str, *, zed_sdk: str, cuda_major: int, owner_seed: bool) -> dict:
    return {
        "product": "KineCapture",
        "version": version,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "launch_exe": "env/pythonw.exe",
        "launch_args": "-B -m kinecapture",
        "icon": "env/share/kinecapture/kinecapture.ico",
        "owner_seed": owner_seed,
        "requirements": {"zed_sdk": zed_sdk, "cuda_major": cuda_major},
        "post_install": [
            {
                "title": "Ortam yolları bu klasöre göre düzeltiliyor (conda-unpack)",
                "exe": "env/Scripts/conda-unpack.exe", "args": "", "cwd": "env", "timeout_s": 1200,
            },
            {
                "title": "Python modülleri derleniyor",
                "exe": "env/python.exe",
                "args": f'-m compileall -q -j 0 -x "{COMPILE_EXCLUDE}" Lib',
                "cwd": "env", "timeout_s": 2400,
            },
        ],
        "verify": [
            {
                "title": "Kurulum sonrası öz-denetim (konsolsuz, başsız)",
                "exe": "env/pythonw.exe",
                "args": f'-B -m kinecapture --self-check --report "{{report}}" --expect-zed-sdk {zed_sdk} --require-preview-models',
                "cwd": "env", "timeout_s": 900,
            },
        ],
    }


def write_reports(manifest: Manifest, installer: Path) -> tuple[Path, Path]:
    base = Path(installer).with_suffix("")
    manifest_path = base.with_name(base.name + ".manifest.json")
    scan_path = base.with_name(base.name + ".scan.json")
    manifest_path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    scan = {
        "ok": not manifest.findings,
        "findings": [f.to_dict() for f in manifest.findings],
        "rules": [
            "*.sqlite3, *.db, *.svo, *.svo2, *.log dosyaları",
            "run_* klasörleri",
            "kod olmayan 'identity' adlı dosyalar",
            "derleme makinesinin Windows kullanıcı adı (her yerde) ve bu makinede var olan bir "
            "profile giden C:\\Users\\<ad> yolu (ad ve içerik, UTF-8/UTF-16)",
            "düz metin parola şüphesi (uygulama dosyaları ve üst düzey metin dosyaları; sezgisel)",
            "özet dışı sahip tohumu",
        ],
        "foreign_user_paths_note": (
            "Bu makinede olmayan profillere giden C:\\Users\\<ad> yolları: üçüncü taraf ikililerin "
            "derlendiği makineler ve belge örnekleri. Başarısızlık değil; adıyla listelenir."
        ),
        "foreign_user_paths": manifest.foreign_user_paths,
        "excluded": manifest.excluded,
    }
    scan_path.write_text(json.dumps(scan, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest_path, scan_path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 22):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------- repository
#: Where a literal password is a test fixture by design: sandbox accounts the
#: tests and measurement scripts create and sign in with, never a real one.
TEST_AREAS = ("tests/", "scripts/measure/")


def scan_repository(repo: Path = REPO) -> dict:
    """Every file git tracks or would add: plaintext-password suspects and
    seed files. Test fixtures are listed apart; anything else fails."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=repo, capture_output=True, check=True,
    ).stdout.split(b"\x00")
    failures, fixtures, seeds, scanned = [], [], [], 0
    for raw in listed:
        if not raw:
            continue
        relative = raw.decode("utf-8", "replace")
        if fnmatch.fnmatch(relative.rsplit("/", 1)[-1].lower(), "owner_seed*.json"):
            seeds.append(relative)
        path = repo / relative
        try:
            if not path.is_file() or path.stat().st_size > (8 << 20):
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:4096]:
            continue  # binary
        scanned += 1
        for finding in password_suspects(relative, data):
            target = fixtures if relative.startswith(TEST_AREAS) else failures
            target.append(finding.to_dict())
    return {
        "ok": not failures and not seeds,
        "scanned_files": scanned,
        "failures": failures,
        "test_fixtures": fixtures,
        "seed_files_in_repository": seeds,
        "note": "Sezgisel: parola benzeri bir anahtarla eşleşen düz metin değer. Testlerdeki "
                "parolalar geçici sandbox hesaplarınındır (görevin izin verdiği test parolası).",
    }


# ---------------------------------------------------------------------- CLI
def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="KineCapture kurucu araçları")
    sub = parser.add_subparsers(dest="command", required=True)
    repo_scan = sub.add_parser("scan-repo", help="depoda düz metin parola ve tohum dosyası taraması")
    repo_scan.add_argument("--out", default=None)
    build = sub.add_parser("build", help="yükü oluştur, tara, kurucuyu birleştir")
    build.add_argument("--tar", required=True, help="conda-pack --format tar çıktısı")
    build.add_argument("--out", required=True, help="kurucu .exe yolu")
    build.add_argument("--work", required=True, help="ara dosyalar klasörü")
    build.add_argument("--version", required=True)
    build.add_argument("--zed-sdk", default="5.4.1")
    build.add_argument("--cuda-major", type=int, default=13)
    build.add_argument("--models", required=True, help="önizleme modelleri klasörü")
    build.add_argument("--owner-seed", default=None)
    build.add_argument("--username", default=os.environ.get("USERNAME", ""))
    args = parser.parse_args(argv)
    if args.command == "scan-repo":
        result = scan_repository()
        text = json.dumps(result, ensure_ascii=False, indent=1)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(f"taranan dosya: {result['scanned_files']}; başarısız: {len(result['failures'])}; "
              f"test parolası: {len(result['test_fixtures'])}; depodaki tohum: {len(result['seed_files_in_repository'])}")
        for finding in result["failures"]:
            print(f"  [{finding['rule']}] {finding['path']}: {finding['detail']}".encode("ascii", "backslashreplace").decode("ascii"))
        return 0 if result["ok"] else 2

    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    icon = render_icon(work / "kinecapture.ico")
    stub = compile_stub(work / "setup-stub.exe", icon=icon)
    from kinecapture.preview.pose import PREVIEW_MODELS

    extras: dict[str, Source] = {}
    for name, pinned in PREVIEW_MODELS.items():
        model = Path(args.models) / name
        digest = "sha256:" + sha256_file(model)
        if digest != pinned:
            raise SystemExit(f"Önizleme modeli beklenen özetle eşleşmiyor: {model}")
        extras[f"share/kinecapture/models/{name}"] = model
    if icon is not None:
        extras["share/kinecapture/kinecapture.ico"] = icon
    if args.owner_seed:
        extras["share/kinecapture/owner_seed.json"] = Path(args.owner_seed)
    install = installer_install_json(
        args.version, zed_sdk=args.zed_sdk, cuda_major=args.cuda_major, owner_seed=bool(args.owner_seed)
    )
    started = time.perf_counter()
    profiles = local_profiles()
    manifest = compose(
        work / "payload.zip", environment=iter_tar(Path(args.tar)), install=install, extras=extras,
        username=args.username, profiles=profiles,
    )
    out = Path(args.out)
    manifest_path, scan_path = write_reports(manifest, out)
    print(f"yük: {len(manifest.files)} dosya, {manifest.unpacked_bytes / 2**30:.2f} GB açık, "
          f"en uzun yol {manifest.max_relative_path}, {time.perf_counter() - started:.0f} s")
    print(f"dışarıda bırakılan: {len(manifest.excluded)}")
    print(f"taranan yerel profiller: {len(profiles)}; yabancı derleme yolları: "
          + ", ".join(f"{name} ({entry['count']})" for name, entry in sorted(manifest.foreign_user_paths.items())))
    if manifest.findings:
        print(f"TARAMA BAŞARISIZ: {len(manifest.findings)} bulgu -> {scan_path}")
        for finding in manifest.findings[:40]:
            print(f"  [{finding.rule}] {finding.path}: {finding.detail}".encode("ascii", "backslashreplace").decode("ascii"))
        return 2
    assemble(stub, work / "payload.zip", out)
    print(f"kurucu: {out} ({out.stat().st_size / 2**20:.0f} MB) sha256={sha256_file(out)}")
    print(f"manifest: {manifest_path}")
    print(f"tarama: {scan_path} (bulgu yok)")
    return 0


if __name__ == "__main__":
    try:
        import kinecapture  # noqa: F401 - the build uses the installed wheel
    except ImportError:
        sys.path.insert(0, str(REPO / "src"))
    raise SystemExit(_main())
