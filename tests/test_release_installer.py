"""Release gate B2/B4/B5: the installer program, its preflight and the scan.

Everything runs the real installer binary, compiled from
``scripts/release/installer/KineCaptureSetup.cs`` with the C# compiler that
ships with Windows, carrying a tiny payload built by the same code as the
release payload. Every location it touches is redirected into the test's own
folder (``LOCALAPPDATA``, ``APPDATA``, ``USERPROFILE``, ``TEMP``), and the
Apps & Features entry uses a test-only key that is removed afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "release"))

import installer_tools as tools  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows kurucusu")

GOOD = {
    "os_64bit": True, "os_major": 10, "os_build": 22631,
    "zed_root": r"C:\Program Files (x86)\ZED SDK", "zed_root_source": "test",
    "zed_header_version": "5.4.1", "zed_cmake_version": "5.4.1", "zed_registry_version": "5.4.1",
    "zed_cuda_major": 13, "zed_bin": r"C:\Program Files (x86)\ZED SDK\bin",
    "zed_dlls_missing": [], "zed_bin_on_path": True,
    "gpus": [{"name": "NVIDIA GeForce RTX 3060", "vendor": "NVIDIA", "driver_wmi": "32.0.15.8088", "nvidia": True}],
    "nvidia_driver": "580.88", "driver_dlls_missing": [], "vc_dlls_missing": [],
    "vc_redist_version": "v14.40.33810.00", "target_free_bytes": 50 * 2**30,
}


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def build(tmp_path_factory):
    try:
        tools.find_csc()
    except FileNotFoundError:
        pytest.skip("Windows'un .NET Framework C# derleyicisi yok")
    root = tmp_path_factory.mktemp("kurucu")
    stub = tools.compile_stub(root / "setup-stub.exe")
    probe = Path(os.environ["WINDIR"]) / "System32" / "where.exe"
    environment = [
        ("python-yerine.txt", b"deneme ortami\n"),
        ("Lib/site-packages/kinecapture/__init__.py", b"APP_VERSION = '0.0-test'\n"),
        ("Lib/site-packages/paket/derin/" + "k" * 10 + "/modul.py", b"x = 1\n"),
        ("probe.exe", probe.read_bytes()),
        ("Lib/site-packages/paket/__pycache__/eski.cpython-311.pyc", b"bytecode"),
        ("conda-meta/history", b"# cmd: C:\\Users\\birisi\\conda create\n"),
    ]
    install = {
        "product": "KineCapture", "version": "0.0-test",
        "launch_exe": "env/probe.exe", "launch_args": "/?",
        "requirements": {"zed_sdk": "5.4.1", "cuda_major": 13},
        "post_install": [
            {"title": "Test adımı", "exe": "env/probe.exe", "args": "/q probe.exe", "cwd": "env", "timeout_s": 60},
        ],
        "verify": [
            {"title": "Test doğrulaması", "exe": "env/probe.exe", "args": "/q probe.exe", "cwd": "env", "timeout_s": 60},
        ],
    }
    manifest = tools.compose(root / "payload.zip", environment=environment, install=install, username="")
    installer = tools.assemble(stub, root / "payload.zip", root / "KineCapture-Setup-test.exe")
    failing = dict(install, verify=[
        {"title": "Başarısız doğrulama", "exe": "env/probe.exe", "args": "/q bulunmayan-dosya-xyz", "cwd": "env", "timeout_s": 60},
    ])
    tools.compose(root / "payload-fail.zip", environment=environment, install=failing, username="")
    broken = tools.assemble(stub, root / "payload-fail.zip", root / "KineCapture-Setup-bozuk.exe")
    return {"stub": stub, "installer": installer, "broken": broken, "manifest": manifest, "root": root}


class Machine:
    """A throwaway Windows user: every location the installer uses, redirected."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.profile = root / "Kullanıcılar" / "Görkem Ş"
        self.local = self.profile / "AppData" / "Local"
        self.roaming = self.profile / "AppData" / "Roaming"
        self.temp = self.local / "Temp"
        for folder in (self.local, self.roaming, self.temp):
            folder.mkdir(parents=True, exist_ok=True)
        self.regkey = "KineCapture-Test-" + uuid.uuid4().hex[:10]
        self.env = dict(os.environ)
        self.env.update(
            LOCALAPPDATA=str(self.local), APPDATA=str(self.roaming), USERPROFILE=str(self.profile),
            TEMP=str(self.temp), TMP=str(self.temp),
        )

    @property
    def default_target(self) -> Path:
        return self.local / "Programs" / "KineCapture"

    @property
    def start_menu_link(self) -> Path:
        return self.roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "KineCapture.lnk"

    def run(self, exe: Path, *args: str, facts: dict | None = None, timeout: float = 120) -> tuple[int, dict]:
        report = self.root / f"rapor-{uuid.uuid4().hex[:8]}.json"
        command = [str(exe), "/silent", f"/report={report}", f"/regkey={self.regkey}", *args]
        if facts is not None:
            path = self.root / f"olgular-{uuid.uuid4().hex[:8]}.json"
            path.write_text(json.dumps(facts), encoding="utf-8")
            command.append(f"/facts={path}")
        result = subprocess.run(command, env=self.env, timeout=timeout, capture_output=True)
        parsed = json.loads(report.read_text("utf-8")) if report.is_file() else {}
        return result.returncode, parsed

    def registry(self) -> dict | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + self.regkey) as key:
                values = {}
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        return values
                    values[name] = value
                    index += 1
        except FileNotFoundError:
            return None

    def forget(self) -> None:
        import winreg

        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Uninstall\\" + self.regkey)
        except OSError:
            pass


@pytest.fixture
def machine(tmp_path):
    box = Machine(tmp_path)
    yield box
    box.forget()


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


def _failing(report: dict) -> set[str]:
    return {check["id"] for check in report["checks"] if not check["ok"]}


# ----------------------------------------------------------------- preflight
def test_every_rule_passes_on_a_good_machine(build, machine) -> None:
    code, report = machine.run(build["stub"], "/checkonly", facts=GOOD)
    assert code == 0, report
    assert _failing(report) == set()
    assert {c["id"] for c in report["checks"]} == {
        "os", "zed_sdk", "zed_dlls", "zed_path", "gpu", "driver", "cuda_runtime", "vcredist", "disk", "path_length",
    }


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"zed_root": None, "zed_header_version": None, "zed_cmake_version": None,
          "zed_registry_version": None, "zed_cuda_major": None, "zed_dlls_missing": None,
          "zed_bin_on_path": False}, {"zed_sdk", "zed_dlls", "zed_path"}),
        ({"zed_header_version": "5.4.0", "zed_cmake_version": "5.4.0", "zed_registry_version": "5.4.0"}, {"zed_sdk"}),
        ({"zed_header_version": "5.4.2", "zed_cmake_version": "5.4.2", "zed_registry_version": "5.4.2"}, {"zed_sdk"}),
        ({"zed_registry_version": "5.4.0"}, {"zed_sdk"}),
        ({"zed_dlls_missing": ["sl_ai64.dll"]}, {"zed_dlls"}),
        ({"zed_bin_on_path": False}, {"zed_path"}),
        ({"nvidia_driver": "577.00"}, {"driver"}),
        ({"nvidia_driver": "579.99"}, {"driver"}),
        ({"gpus": [{"name": "Intel(R) UHD Graphics", "vendor": "Intel", "nvidia": False}],
          "nvidia_driver": None}, {"gpu", "driver"}),
        ({"gpus": [], "nvidia_driver": None}, {"gpu", "driver"}),
        ({"zed_cuda_major": 11}, {"driver"}),
        ({"driver_dlls_missing": ["nvcuda.dll"]}, {"cuda_runtime"}),
        ({"vc_dlls_missing": ["mfc140.dll"]}, {"vcredist"}),
        ({"os_build": 9600, "os_major": 6}, {"os"}),
        ({"os_64bit": False}, {"os"}),
    ],
    ids=[
        "sdk_yok", "sdk_5.4.0", "sdk_5.4.2", "sdk_tutarsiz", "sdk_dll_eksik", "sdk_path_disinda",
        "surucu_eski", "surucu_esikte", "gpu_intel", "gpu_yok", "cuda_bilinmiyor", "cuda_dll_eksik",
        "vcredist_eksik", "windows_8", "windows_32bit",
    ],
)
def test_each_missing_requirement_is_named_and_nothing_else(build, machine, change, expected) -> None:
    facts = {**GOOD, **change}
    code, report = machine.run(build["stub"], "/checkonly", facts=facts)
    assert code == 2
    assert _failing(report) == expected
    for check in report["checks"]:
        if not check["ok"]:
            assert check["found"] and check["needed"] and check["remedy"], check


def test_the_driver_minimum_follows_the_sdks_cuda(build, machine) -> None:
    """CUDA 12 builds of the SDK need 527.41 on Windows; CUDA 13 builds R580."""
    code, report = machine.run(build["stub"], "/checkonly", facts={**GOOD, "zed_cuda_major": 12, "nvidia_driver": "527.41"})
    assert code == 0, _failing(report)
    code, report = machine.run(build["stub"], "/checkonly", facts={**GOOD, "zed_cuda_major": 12, "nvidia_driver": "527.37"})
    assert _failing(report) == {"driver"}
    code, report = machine.run(build["stub"], "/checkonly", facts={**GOOD, "nvidia_driver": "560.94"})
    assert _failing(report) == {"driver"}
    assert "580.00" in next(c["needed"] for c in report["checks"] if c["id"] == "driver")


def test_disk_and_path_length_use_the_payloads_own_numbers(build, machine) -> None:
    manifest = build["manifest"]
    code, report = machine.run(build["installer"], "/checkonly", f"/dir={machine.root / 'KC'}",
                               facts={**GOOD, "target_free_bytes": 1024})
    assert code == 2 and _failing(report) == {"disk"}
    deep = machine.root / ("d" * (259 - manifest.max_relative_path))
    code, report = machine.run(build["installer"], "/checkonly", f"/dir={deep}", facts=GOOD)
    assert code == 2 and _failing(report) == {"path_length"}


def test_a_check_changes_nothing_but_its_log(build, machine) -> None:
    before = _snapshot(machine.root)
    log = machine.temp / "denetim.log"
    code, report = machine.run(build["installer"], "/checkonly", f"/log={log}", facts={**GOOD, "zed_root": None})
    assert code == 2
    created = _snapshot(machine.root) - before
    assert created == {
        str(log.relative_to(machine.root)),
        *(n for n in created if n.startswith("rapor-") or n.startswith("olgular-")),
    }
    assert "EKSİK" in log.read_text("utf-8")
    assert machine.registry() is None


def test_a_failed_preflight_installs_nothing(build, machine) -> None:
    code, _ = machine.run(build["installer"], facts={**GOOD, "nvidia_driver": "470.00"})
    assert code == 2
    assert not machine.default_target.exists()
    assert not machine.start_menu_link.exists()
    assert machine.registry() is None


def _fake_sdk(root: Path, version: tuple[int, int, int], *, dlls=True, cuda=13) -> Path:
    header = root / "include" / "sl"
    header.mkdir(parents=True)
    (header / "Camera.hpp").write_text(
        "// test\n#define ZED_SDK_MAJOR_VERSION {}\n#define ZED_SDK_MINOR_VERSION {}\n"
        "#define ZED_SDK_PATCH_VERSION {}\n#define ZED_SDK_BUILD_ID \"test\"\n".format(*version),
        encoding="utf-8",
    )
    (root / "zed-config-version.cmake").write_text('set(PACKAGE_VERSION "{}.{}.{}")\n'.format(*version))
    (root / "zed-config.cmake").write_text(f"        SET(ZED_CUDA_VERSION {cuda})\n")
    (root / "bin").mkdir()
    if dlls:
        for name in ("sl_zed64.dll", "sl_ai64.dll", "nvinfer_10.dll", "nvinfer_plugin_10.dll", "nvonnxparser_10.dll"):
            (root / "bin" / name).write_bytes(b"MZ")
    return root


@pytest.mark.parametrize(
    "version, dlls, ok",
    [((5, 4, 1), True, True), ((5, 4, 0), True, False), ((5, 4, 1), False, False)],
    ids=["5.4.1", "5.4.0", "dll_eksik"],
)
def test_the_sdk_version_is_read_from_the_sdks_own_files(build, machine, version, dlls, ok) -> None:
    sdk = _fake_sdk(machine.root / "Sahte ZED SDK", version, dlls=dlls)
    code, report = machine.run(build["stub"], "/checkonly", f"/sdkroot={sdk}")
    facts = report["facts"]
    assert facts["zed_header_version"] == "{}.{}.{}".format(*version)
    assert facts["zed_cmake_version"] == "{}.{}.{}".format(*version)
    assert facts["zed_cuda_major"] == 13
    checks = {c["id"]: c["ok"] for c in report["checks"]}
    assert checks["zed_sdk"] is (version == (5, 4, 1))
    assert checks["zed_dlls"] is dlls
    # the fake SDK's bin is not on PATH, so that one check always fails here
    assert checks["zed_path"] is False


def test_this_machines_driver_is_read_like_nvidia_smi_reads_it(build, machine) -> None:
    code, report = machine.run(build["stub"], "/checkonly")
    facts = report["facts"]
    if not facts.get("nvidia_smi_driver"):
        pytest.skip("bu makinede nvidia-smi yok")
    assert facts["nvidia_driver"] == facts["nvidia_smi_driver"]


# --------------------------------------------------- install and uninstall
def test_install_reinstall_and_uninstall_keep_the_users_data(build, machine) -> None:
    target = machine.root / "Program Klasörü" / "Görkem Ş" / "KineCapture"
    data = machine.local / "KineCapture" / "identity.sqlite3"
    dataset = machine.profile / "KineCapture" / "datasets" / "projects" / "prj_1" / "project.json"
    for path in (data, dataset):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"korunacak veri")

    code, report = machine.run(build["installer"], f"/dir={target}", facts=GOOD)
    assert code == 0, report
    assert (target / "env" / "probe.exe").is_file()
    assert (target / "env" / "Lib" / "site-packages" / "kinecapture" / "__init__.py").is_file()
    assert not (target / "env" / "conda-meta" / "history").exists()
    assert not list(target.rglob("*.pyc")), "bytecode is compiled on the target, never shipped"
    assert (target / "uninstall.exe").is_file()
    marker = json.loads((target / "kinecapture-install.json").read_text("utf-8"))
    assert marker["version"] == "0.0-test" and marker["registry_key"] == machine.regkey
    assert machine.start_menu_link.is_file()
    assert (machine.profile / "Desktop" / "KineCapture.lnk").is_file()
    entry = machine.registry()
    assert entry is not None and entry["InstallLocation"] == str(target)
    assert entry["UninstallString"] == f'"{target / "uninstall.exe"}" /uninstall'

    # a file the user left in the folder is theirs
    (target / "notlarım.txt").write_text("benim", encoding="utf-8")

    code, report = machine.run(build["installer"], f"/dir={target}", facts=GOOD)
    assert code == 0, report
    marker = json.loads((target / "kinecapture-install.json").read_text("utf-8"))
    assert marker["previous_version"] == "0.0-test"
    assert data.read_bytes() == b"korunacak veri" and dataset.read_bytes() == b"korunacak veri"
    assert (target / "notlarım.txt").is_file()

    result = subprocess.run([str(target / "uninstall.exe"), "/uninstall", "/silent"], env=machine.env, timeout=120)
    assert result.returncode == 0
    deadline = time.time() + 20
    while (target / "uninstall.exe").exists() and time.time() < deadline:
        time.sleep(0.5)
    assert not (target / "env").exists()
    assert not (target / "uninstall.exe").exists()
    assert (target / "notlarım.txt").is_file(), "the uninstaller removes program files only"
    assert not machine.start_menu_link.exists()
    assert not (machine.profile / "Desktop" / "KineCapture.lnk").exists()
    assert machine.registry() is None
    assert data.read_bytes() == b"korunacak veri" and dataset.read_bytes() == b"korunacak veri"


def test_an_empty_folder_is_removed_with_the_installation(build, machine) -> None:
    code, _ = machine.run(build["installer"], "/nodesktop", facts=GOOD)
    assert code == 0
    target = machine.default_target
    assert (target / "env").is_dir()
    subprocess.run([str(target / "uninstall.exe"), "/uninstall", "/silent"], env=machine.env, timeout=120, check=True)
    deadline = time.time() + 20
    while target.exists() and time.time() < deadline:
        time.sleep(0.5)
    assert not target.exists()


def test_a_folder_with_someone_elses_files_is_refused(build, machine) -> None:
    target = machine.root / "Belgelerim"
    target.mkdir()
    (target / "tez.docx").write_bytes(b"x")
    code, _ = machine.run(build["installer"], f"/dir={target}", facts=GOOD)
    assert code == 3
    assert sorted(p.name for p in target.iterdir()) == ["tez.docx"]
    assert machine.registry() is None


def test_a_failed_verification_rolls_everything_back(build, machine) -> None:
    target = machine.root / "Geri Alma" / "KineCapture"
    code, report = machine.run(build["broken"], f"/dir={target}", facts=GOOD)
    assert code == 3
    assert not target.exists()
    assert not machine.start_menu_link.exists()
    assert machine.registry() is None


# ------------------------------------------------------------------- scanning
def test_the_scan_names_every_kind_of_forbidden_file(tmp_path) -> None:
    environment = [
        ("Lib/site-packages/ok.py", b"print('tamam')\n"),
        ("share/identity.sqlite3", b"x"),
        ("veriler/take.db", b"x"),
        ("veriler/kayit.svo2", b"x"),
        ("datasets/p/run_0123456789abcdef/job.json", b"{}"),
        ("logs/kinecapture.log", b"x"),
        ("etc/identity", b"x"),
        ("Lib/site-packages/paket/yol.txt", "C:\\Users\\kullanici\\x".encode("utf-8")),
        ("Lib/site-packages/paket/geniş.bin", "C:\\Users\\kullanici".encode("utf-16-le")),
        ("Lib/site-packages/paket/kullanicix.json", b"{}"),
        ("Lib/site-packages/kinecapture/ayar.py", b'parola = "cokgizlisifre"\n'),
        ("Lib/site-packages/kinecapture/identity/service.py", b"def f(): pass\n"),
        # a state name, not a password: must not be flagged
        ("Lib/site-packages/kinecapture/auth.py", b'CHANGE_PASSWORD = "change_password"\n'),
        # the CI machine that built a third-party DLL: listed, not a failure
        ("Library/bin/qt.dll", b"\x00C:\\Users\\runneradmin\\work\\qt\\build\x00"),
        # pip's launcher made for the builder's interpreter: left out entirely
        ("Scripts/pyside6-uic.exe", b"MZ#!C:\\Users\\kullanici\\KineSynth\\python.exe"),
        ("Scripts/conda-unpack.exe", b"MZ launcher"),
        ("Library/bin/libssl.pdb", b"C:\\Users\\TASK_1~1\\x"),
    ]
    manifest = tools.compose(tmp_path / "p.zip", environment=environment, install={"product": "KineCapture"},
                             username="kullanicix", profiles={"kullanici"})
    rules = {(f.rule, f.path) for f in manifest.findings}
    assert ("data_file", "env/share/identity.sqlite3") in rules
    assert ("data_file", "env/veriler/take.db") in rules
    assert ("data_file", "env/veriler/kayit.svo2") in rules
    assert ("run_dir", "env/datasets/p/run_0123456789abcdef/job.json") in rules
    assert ("data_file", "env/logs/kinecapture.log") in rules
    assert ("identity", "env/etc/identity") in rules
    assert ("user_path", "env/Lib/site-packages/paket/yol.txt") in rules
    assert ("user_path", "env/Lib/site-packages/paket/geniş.bin") in rules
    assert ("username", "env/Lib/site-packages/paket/kullanicix.json") in rules
    assert ("password_suspect", "env/Lib/site-packages/kinecapture/ayar.py") in rules
    flagged = {path for _, path in rules}
    assert "env/Lib/site-packages/ok.py" not in flagged
    assert "env/Lib/site-packages/kinecapture/identity/service.py" not in flagged
    assert "env/Lib/site-packages/kinecapture/auth.py" not in flagged
    assert "env/Library/bin/qt.dll" not in flagged
    assert manifest.foreign_user_paths["runneradmin"]["example"] == "env/Library/bin/qt.dll"
    shipped = {entry["path"] for entry in manifest.files}
    assert "env/Scripts/pyside6-uic.exe" not in shipped
    assert "env/Scripts/conda-unpack.exe" in shipped
    assert "env/Library/bin/libssl.pdb" not in shipped


def test_a_path_into_a_profile_on_this_machine_fails_the_scan(tmp_path) -> None:
    """Whatever the file: the build machine's own profiles must not appear."""
    environment = [
        ("Library/bin/araç.dll", "\x00C:\\Users\\Görkem Ş\\AppData\\x".encode("utf-16-le")),
        ("share/ayar.txt", b"yol = C:/Users/TEMP.GORKI/Desktop"),
    ]
    manifest = tools.compose(tmp_path / "p.zip", environment=environment, install={"product": "KineCapture"},
                             username="", profiles={"Görkem Ş", "TEMP.GORKI"})
    assert {(f.rule, f.path) for f in manifest.findings} == {
        ("user_path", "env/Library/bin/araç.dll"),
        ("user_path", "env/share/ayar.txt"),
    }
    assert manifest.foreign_user_paths == {}


def test_a_seed_that_is_not_a_digest_fails_the_scan(tmp_path) -> None:
    bad = json.dumps({"username": "gorkembektas", "password": "duz-metin"}).encode("utf-8")
    manifest = tools.compose(tmp_path / "p.zip", environment=[], install={"product": "KineCapture"},
                             extras={"share/kinecapture/owner_seed.json": bad}, username="")
    assert any(f.rule == "owner_seed" for f in manifest.findings)
    assert any(f.rule == "password_suspect" for f in manifest.findings)


def test_conda_unpack_only_rewrites_files_the_payload_carries(tmp_path) -> None:
    """Found by the first real install: conda-unpack stopped on a debug symbol
    that the payload leaves out. Its records must follow the payload."""
    script = (
        "import os\n"
        "_prefix_records = [\n"
        "('Library/bin/libssl.dll', 'C:\\\\\\\\build\\\\\\\\_h_env', 'binary'),\n"
        "('Library/bin/libssl.pdb', 'C:\\\\\\\\build\\\\\\\\_h_env', 'binary'),\n"
        "('Scripts\\\\pyside6-uic.exe', 'C:\\\\\\\\KCBuild\\\\\\\\env', 'binary'),\n"
        "]\n"
        "print('kayıt', len(_prefix_records))\n"
    ).encode("utf-8")
    environment = [
        ("Library/bin/libssl.dll", b"MZ"),
        ("Library/bin/libssl.pdb", b"pdb"),
        ("Scripts/pyside6-uic.exe", b"MZ"),
        ("Scripts/conda-unpack-script.py", script),
    ]
    manifest = tools.compose(tmp_path / "p.zip", environment=environment, install={"product": "KineCapture"},
                             username="")
    assert sorted(manifest.unpack_records_dropped) == ["Library/bin/libssl.pdb", "Scripts\\pyside6-uic.exe"]
    import zipfile

    with zipfile.ZipFile(tmp_path / "p.zip") as payload:
        written = payload.read("env/Scripts/conda-unpack-script.py").decode("utf-8")
    namespace: dict = {}
    exec(compile(written.replace("print(", "(lambda *a: None)("), "unpack", "exec"), namespace)  # noqa: S102
    assert [record[0] for record in namespace["_prefix_records"]] == ["Library/bin/libssl.dll"]


def test_the_owner_seed_may_carry_a_name_that_contains_the_build_user(tmp_path) -> None:
    """``gorkembektas`` contains ``gorke``: the owner's own name in the seed is
    not a leak - the same name anywhere else still is."""
    from kinecapture.identity.passwords import hash_password
    from kinecapture.identity.seed import OwnerSeed, seed_document

    seed = OwnerSeed(username="kullanicixbektas", first_name="Kullanıcı", last_name="X",
                     title="Test", digest=hash_password("yalniz-test-icin-7Q"))
    data = json.dumps(seed_document(seed, created_at="2026-09-24T00:00:00Z", generator="test")).encode("utf-8")
    manifest = tools.compose(
        tmp_path / "p.zip",
        environment=[("Lib/site-packages/paket/yol.txt", b"kullanicix burada")],
        install={"product": "KineCapture"},
        extras={"share/kinecapture/owner_seed.json": data},
        username="kullanicix",
    )
    assert {(f.rule, f.path) for f in manifest.findings} == {("username", "env/Lib/site-packages/paket/yol.txt")}


def test_the_payload_trailer_round_trips(build) -> None:
    offset, length = tools.read_trailer(build["installer"])
    assert offset == build["stub"].stat().st_size
    with tools.open_payload(build["installer"]) as payload:
        install = json.loads(payload.read("install.json"))
    assert install["requirements"]["max_relative_path"] == build["manifest"].max_relative_path
    assert install["files"] == len(build["manifest"].files)


def test_the_longest_path_counts_the_bytecode_compileall_will_write(tmp_path) -> None:
    folder = "Lib/site-packages/paket"
    manifest = tools.compose(tmp_path / "p.zip", environment=[(f"{folder}/m.py", b"")],
                             install={"product": "KineCapture"}, username="")
    assert manifest.max_relative_path == len(f"env/{folder}/__pycache__/m.cpython-311.pyc")
