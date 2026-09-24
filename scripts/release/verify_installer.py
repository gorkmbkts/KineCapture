"""The built installer, end to end, as a throwaway Windows user on this PC.

    python verify_installer.py dist\\KineCapture-Setup-<v>.exe --out sonuc.json [--root C:\\KCVerify]

A second Windows account cannot be created from here, so its equivalent is
used: a fresh profile folder with a Turkish name and spaces, and every
location the installer and the application use - ``USERPROFILE``,
``LOCALAPPDATA``, ``APPDATA``, ``TEMP`` - pointed into it. The Apps & Features
entry uses a test-only key that is removed at the end. Steps:

1. ``/checkonly`` with this machine's real facts (must pass), and with a
   machine that has no ZED SDK (must fail and change nothing);
2. silent install into ``<profile>\\AppData\\Local\\Programs\\KineCapture``
   (the default) - preflight, unpack, conda-unpack, compileall, console-less
   self-check - then the shortcuts and the registry entry;
3. the installed Python runs ``smoke_installed.py``: zero state, the mock
   chain through export and the independent oracle, pyzed against the SDK;
4. the installed ``pythonw.exe -B -m kinecapture --self-check`` again, with no
   standard handles, like a Start-menu shortcut;
5. the installation folder is compared file by file (size, mtime) before 3
   and after 4: the application must not have written into it;
6. reinstall over it: user data untouched; uninstall: program files gone,
   data, datasets and logs still there.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


class User:
    def __init__(self, root: Path) -> None:
        self.profile = root / "Kullanıcılar" / "Görkem Bektaş Ş"
        self.local = self.profile / "AppData" / "Local"
        self.roaming = self.profile / "AppData" / "Roaming"
        self.temp = self.local / "Temp"
        for folder in (self.local, self.roaming, self.temp):
            folder.mkdir(parents=True, exist_ok=True)
        self.regkey = "KineCapture-Verify-" + uuid.uuid4().hex[:8]
        self.env = dict(os.environ)
        self.env.update(LOCALAPPDATA=str(self.local), APPDATA=str(self.roaming),
                        USERPROFILE=str(self.profile), TEMP=str(self.temp), TMP=str(self.temp))
        for name in ("PYTHONPATH", "PYTHONHOME", "CONDA_PREFIX", "CONDA_DEFAULT_ENV"):
            self.env.pop(name, None)
        self.target = self.local / "Programs" / "KineCapture"

    def registry(self) -> dict | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + self.regkey) as key:
                values, index = {}, 0
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
                             r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + self.regkey)
        except OSError:
            pass


def run_installer(user: User, installer: Path, *args: str, facts: dict | None = None,
                  timeout: float = 3600) -> tuple[int, dict, float]:
    report = user.temp / f"kurucu-{uuid.uuid4().hex[:8]}.json"
    command = [str(installer), "/silent", f"/report={report}", f"/regkey={user.regkey}", *args]
    if facts is not None:
        path = user.temp / f"olgular-{uuid.uuid4().hex[:8]}.json"
        path.write_text(json.dumps(facts), encoding="utf-8")
        command.append(f"/facts={path}")
    started = time.perf_counter()
    result = subprocess.run(command, env=user.env, timeout=timeout)
    seconds = time.perf_counter() - started
    parsed = json.loads(report.read_text("utf-8")) if report.is_file() else {}
    return result.returncode, parsed, seconds


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    result = {}
    for folder, _, files in os.walk("\\\\?\\" + str(root)):
        for name in files:
            path = os.path.join(folder, name)
            stat = os.stat(path)
            result[os.path.relpath(path, "\\\\?\\" + str(root))] = (stat.st_size, stat.st_mtime_ns)
    return result


def run_consoleless(exe: Path, args: list[str], env: dict, cwd: Path, timeout: float) -> int:
    """Start ``exe`` the way a shortcut does: no console, no standard handles."""

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD), ("lpReserved2", ctypes.c_void_p),
            ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    info = STARTUPINFO()
    info.cb = ctypes.sizeof(STARTUPINFO)
    info.dwFlags = 0x100  # STARTF_USESTDHANDLES, every handle null
    process = PROCESS_INFORMATION()
    command = subprocess.list2cmdline([str(exe), *args])
    block = "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper())) + "\0"
    ok = kernel.CreateProcessW(
        None, ctypes.create_unicode_buffer(command), None, None, False,
        0x08000000 | 0x00000400, ctypes.create_unicode_buffer(block), str(cwd),
        ctypes.byref(info), ctypes.byref(process),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CreateProcessW")
    try:
        if kernel.WaitForSingleObject(process.hProcess, int(timeout * 1000)) != 0:
            kernel.TerminateProcess(process.hProcess, 1)
            raise TimeoutError(str(exe))
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess(process.hProcess, ctypes.byref(code))
        return code.value
    finally:
        kernel.CloseHandle(process.hThread)
        kernel.CloseHandle(process.hProcess)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("installer", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(r"C:\KCVerify"))
    parser.add_argument("--expect-owner", default="")
    args = parser.parse_args(argv)
    installer = args.installer.resolve()
    root = args.root / time.strftime("%Y%m%d-%H%M%S")
    user = User(root)
    result: dict = {"installer": str(installer), "size_mb": round(installer.stat().st_size / 2**20),
                    "root": str(root), "steps": {}}
    steps = result["steps"]
    try:
        # 1. preflight only -------------------------------------------------
        code, report, seconds = run_installer(user, installer, "/checkonly")
        steps["checkonly_this_pc"] = {"ok": code == 0, "exit": code, "seconds": round(seconds, 1),
                                      "failing": [c["id"] for c in report.get("checks", []) if not c["ok"]],
                                      "found": {c["id"]: c["found"] for c in report.get("checks", [])}}
        before = set(p.name for p in user.local.iterdir())
        facts = dict(report.get("facts") or {})
        facts.update(zed_root=None, zed_header_version=None, zed_cmake_version=None,
                     zed_registry_version=None, zed_dlls_missing=None, zed_bin_on_path=False)
        code, report, _ = run_installer(user, installer, facts=facts)
        steps["no_sdk_install_refused"] = {
            "ok": code == 2 and not user.target.exists() and user.registry() is None
                  and set(p.name for p in user.local.iterdir()) == before,
            "exit": code, "failing": [c["id"] for c in report.get("checks", []) if not c["ok"]],
            "remedies": [c["remedy"] for c in report.get("checks", []) if not c["ok"]],
        }

        # 2. install --------------------------------------------------------
        code, report, seconds = run_installer(user, installer)
        link = user.roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "KineCapture.lnk"
        desktop = user.profile / "Desktop" / "KineCapture.lnk"
        entry = user.registry()
        steps["install"] = {
            "ok": code == 0 and (user.target / "env" / "pythonw.exe").is_file() and link.is_file()
                  and desktop.is_file() and entry is not None,
            "exit": code, "seconds": round(seconds, 1), "target": str(user.target),
            "verify": report.get("verify", []), "registry": entry,
            "size_mb": round(sum(s for s, _ in snapshot(user.target).values()) / 2**20),
        }
        if code != 0:
            raise SystemExit("kurulum başarısız; ayrıntı raporda")
        python = user.target / "env" / "python.exe"
        pythonw = user.target / "env" / "pythonw.exe"
        before_run = snapshot(user.target)

        # 3. smoke chain on the installed Python ----------------------------
        smoke_report = user.temp / "smoke.json"
        smoke_args = [str(python), "-B", str(HERE / "smoke_installed.py"), "--tests", str(REPO / "tests"),
                      "--report", str(smoke_report)]
        if args.expect_owner:
            smoke_args += ["--expect-owner", args.expect_owner]
        started = time.perf_counter()
        smoke = subprocess.run(smoke_args, env=user.env, cwd=str(user.profile), timeout=1800,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        smoke_result = json.loads(smoke_report.read_text("utf-8")) if smoke_report.is_file() else {}
        steps["smoke"] = {"ok": smoke.returncode == 0 and smoke_result.get("ok") is True,
                          "exit": smoke.returncode, "seconds": round(time.perf_counter() - started, 1),
                          "result": smoke_result, "stderr_tail": smoke.stderr[-800:]}

        # 4. console-less self-check, as a shortcut starts it ---------------
        check_report = user.temp / "self-check.json"
        started = time.perf_counter()
        code = run_consoleless(pythonw, ["-B", "-m", "kinecapture", "--self-check", "--report", str(check_report),
                                         "--expect-zed-sdk", "5.4.1", "--require-preview-models"],
                               user.env, user.profile, 600)
        check = json.loads(check_report.read_text("utf-8")) if check_report.is_file() else {}
        steps["self_check_consoleless"] = {
            "ok": code == 0 and check.get("ok") is True and check.get("console") is False,
            "exit": code, "seconds": round(time.perf_counter() - started, 1),
            "checks": {k: (v.get("ok"), v.get("detail")) for k, v in check.get("checks", {}).items()},
        }

        # 5. nothing written into the installation --------------------------
        after_run = snapshot(user.target)
        added = sorted(set(after_run) - set(before_run))
        removed = sorted(set(before_run) - set(after_run))
        changed = sorted(k for k in set(before_run) & set(after_run) if before_run[k] != after_run[k])
        steps["no_runtime_writes"] = {"ok": not (added or removed or changed), "added": added[:20],
                                      "removed": removed[:20], "changed": changed[:20],
                                      "files": len(after_run)}

        # 6. reinstall, then uninstall; data stays --------------------------
        identity = user.local / "KineCapture" / "identity.sqlite3"
        datasets = user.profile / "KineCapture" / "datasets"
        logs = user.profile / "KineCapture" / "logs"
        data_before = {p: p.stat().st_size for p in (identity,) if p.exists()}
        dataset_files = sum(1 for _ in datasets.rglob("*")) if datasets.exists() else 0
        code, report, seconds = run_installer(user, installer)
        marker = json.loads((user.target / "kinecapture-install.json").read_text("utf-8"))
        steps["reinstall"] = {
            "ok": code == 0 and marker.get("previous_version") is not None and identity.exists()
                  and sum(1 for _ in datasets.rglob("*")) == dataset_files,
            "exit": code, "seconds": round(seconds, 1), "previous_version": marker.get("previous_version"),
        }
        logs_before = logs.exists()
        uninstall = subprocess.run([str(user.target / "uninstall.exe"), "/uninstall", "/silent"],
                                   env=user.env, timeout=600)
        deadline = time.time() + 30
        while user.target.exists() and time.time() < deadline:
            time.sleep(0.5)
        steps["uninstall"] = {
            "ok": uninstall.returncode == 0 and not user.target.exists() and not link.exists()
                  and not desktop.exists() and user.registry() is None and identity.exists()
                  and all(p.stat().st_size >= s for p, s in data_before.items())
                  and sum(1 for _ in datasets.rglob("*")) == dataset_files
                  and (logs.exists() or not logs_before),
            "exit": uninstall.returncode, "target_left": user.target.exists(),
            "identity_kept": identity.exists(), "dataset_files_kept": sum(1 for _ in datasets.rglob("*")),
            "logs_before": logs_before, "logs_kept": logs.exists(),
        }
    except SystemExit as stop:
        result["stopped"] = str(stop)
    finally:
        user.forget()
        result["ok"] = bool(steps) and all(step.get("ok") for step in steps.values()) and "stopped" not in result
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, step in steps.items():
        print(f"  [{'TAMAM' if step.get('ok') else 'HATA '}] {name}")
    print(f"sonuç: {'geçti' if result['ok'] else 'BAŞARISIZ'} -> {args.out}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
