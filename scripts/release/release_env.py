"""The release environment: a clone of KineSynth, trimmed to what runs.

``KineSynth`` is a research environment (pytorch and CUDA, jupyter, mlflow,
vtk, scipy ...) of about 9 GB. KineCapture imports PySide6, numpy, cv2, yaml,
psutil and pyzed and nothing else. The release environment is therefore:

1. ``conda create --prefix <prefix> --clone KineSynth --offline`` - the same
   builds of the same versions, nothing downloaded, KineSynth untouched;
2. the editable ``kinecapture`` removed (a wheel is installed instead, by
   ``build_installer.ps1``), and ``pyzed`` reinstalled from a copy of its own
   wheel so its metadata does not carry a path under the builder's profile;
   the SDK DLLs someone copied beside ``pyzed`` are removed - an installed
   release loads them from the ZED SDK the preflight verified;
3. trimmed: every conda and pip package outside the dependency closure of
   :data:`KEEP_CONDA` / :data:`KEEP_PIP` is removed. The closure is computed
   from the packages' own metadata, so nothing that stays loses a dependency.

Every command refuses to touch a prefix that does not carry the marker file
this script writes after cloning - KineSynth and base can never be targets.

    python release_env.py prepare --prefix C:\\KCBuild\\env --conda <conda.exe>
    python release_env.py check --prefix C:\\KCBuild\\env
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional

MARKER = ".kinecapture-release-env"
SOURCE_ENV = "KineSynth"
#: Conda roots of the runtime closure.
KEEP_CONDA = ("python", "pyyaml", "pip", "setuptools", "wheel")
#: pip roots: what the package imports, plus pyzed's declared requirement.
KEEP_PIP = ("pyside6", "numpy", "opencv-python", "psutil", "pyzed", "cython")
#: Test tools, kept only while the wheel's tests run in the clone.
TEST_PIP = ("pytest",)
EXPECTED = {
    "python": "3.11.14",
    "PySide6": "6.10.1",
    "numpy": "2.4.6",
    "opencv-python": "4.12.0.88",
    "pyzed": "5.4",
    "PyYAML": "6.0.3",
}


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ------------------------------------------------------------------- guards
def require_marker(prefix: Path) -> None:
    if not (prefix / MARKER).is_file():
        raise SystemExit(
            f"{prefix} bir yayın ortamı değil ({MARKER} yok). KineSynth veya base "
            "üzerinde çalışılmaz; önce 'prepare' ile klonlayın."
        )


def _is_protected(prefix: Path, conda: Path) -> bool:
    base = conda.resolve().parents[1]
    protected = {base.resolve(), (base / "envs" / SOURCE_ENV).resolve()}
    return prefix.resolve() in protected


# ----------------------------------------------------------------- metadata
def conda_packages(prefix: Path) -> dict[str, dict]:
    packages = {}
    for path in glob.glob(str(prefix / "conda-meta" / "*.json")):
        with open(path, encoding="utf-8") as stream:
            record = json.load(stream)
        packages[record["name"]] = record
    return packages


def pip_packages(prefix: Path) -> dict[str, dict]:
    """Distributions pip manages (INSTALLER != conda), with requirements."""
    packages = {}
    for info in glob.glob(str(prefix / "Lib" / "site-packages" / "*.dist-info")):
        installer = ""
        try:
            installer = Path(info, "INSTALLER").read_text(encoding="utf-8").strip()
        except OSError:
            pass
        if installer == "conda":
            continue
        name, version, requires = "", "", []
        try:
            for line in Path(info, "METADATA").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Name:") and not name:
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Version:") and not version:
                    version = line.split(":", 1)[1].strip()
                elif line.startswith("Requires-Dist:"):
                    spec = line.split(":", 1)[1].strip()
                    if "extra ==" in spec:
                        continue
                    match = re.match(r"[A-Za-z0-9._-]+", spec)
                    if match:
                        requires.append(_canonical(match.group(0)))
                elif not line.strip():
                    break
        except OSError:
            continue
        if name:
            packages[_canonical(name)] = {"name": name, "version": version, "requires": requires, "info": info}
    return packages


def closure(roots: Iterable[str], edges: dict[str, list[str]]) -> set[str]:
    keep, todo = set(), [r for r in roots if r in edges]
    while todo:
        name = todo.pop()
        if name in keep:
            continue
        keep.add(name)
        todo.extend(d for d in edges.get(name, ()) if d in edges and d not in keep)
    return keep


def plan(prefix: Path, *, keep_tests: bool) -> dict:
    conda = conda_packages(prefix)
    conda_edges = {
        name: [dep.split()[0] for dep in record.get("depends", [])] for name, record in conda.items()
    }
    keep_conda = closure(KEEP_CONDA, conda_edges)
    # A package conda installed is conda's to remove, even when its
    # dist-info lacks an INSTALLER file (``wheel`` here).
    conda_names = {_canonical(name) for name in conda}
    pip = {name: p for name, p in pip_packages(prefix).items() if name not in conda_names}
    roots = list(KEEP_PIP) + (list(TEST_PIP) if keep_tests else []) + ["kinecapture"]
    keep_pip = closure([_canonical(r) for r in roots], {n: p["requires"] for n, p in pip.items()})
    return {
        "keep_conda": sorted(keep_conda),
        "remove_conda": sorted(set(conda) - keep_conda),
        "keep_pip": sorted(keep_pip),
        "remove_pip": sorted(set(pip) - keep_pip),
        "pip_names": {n: p["name"] for n, p in pip.items()},
    }


# ----------------------------------------------------------------- commands
def _run(command: list[str], **kwargs) -> None:  # noqa: ANN003
    print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def clone(prefix: Path, conda: Path) -> None:
    if prefix.exists():
        require_marker(prefix)
        print(f"klon zaten var: {prefix}")
        return
    if _is_protected(prefix, conda):
        raise SystemExit(f"{prefix} korunan bir ortam; klon hedefi olamaz.")
    _run([str(conda), "create", "--prefix", str(prefix), "--clone", SOURCE_ENV, "--offline", "--yes", "--quiet"])
    (prefix / MARKER).write_text(
        "KineCapture yayın ortamı (KineSynth klonu). scripts/release/release_env.py yönetir.\n",
        encoding="utf-8",
    )


def detach_from_source(prefix: Path, pyzed_wheel: Optional[Path], wheels: Path) -> None:
    """Editable kinecapture out; pyzed reinstalled from a neutral path."""
    require_marker(prefix)
    python = prefix / "python.exe"
    pip = pip_packages(prefix)
    if "kinecapture" in pip:
        _run([str(python), "-m", "pip", "uninstall", "--yes", "--quiet", "kinecapture"])
    info = pip.get("pyzed", {}).get("info")
    direct = Path(info, "direct_url.json") if info else None
    if direct is not None and direct.is_file() and "Users" in direct.read_text(encoding="utf-8"):
        if pyzed_wheel is None or not pyzed_wheel.is_file():
            raise SystemExit("pyzed tekerleği bulunamadı (--pyzed-wheel).")
        wheels.mkdir(parents=True, exist_ok=True)
        local = wheels / pyzed_wheel.name
        shutil.copy2(pyzed_wheel, local)
        _run([str(python), "-m", "pip", "install", "--no-deps", "--force-reinstall", "--no-index", "--quiet", str(local)])
    folder = prefix / "Lib" / "site-packages" / "pyzed"
    for name in ("sl_zed64.dll", "sl_ai64.dll"):
        copy = folder / name
        if copy.exists():
            copy.unlink()
            print(f"  ZED SDK kopyası kaldırıldı: {copy}")


def trim(prefix: Path, conda: Path, *, keep_tests: bool) -> dict:
    require_marker(prefix)
    if _is_protected(prefix, conda):
        raise SystemExit("korunan ortam")
    result = plan(prefix, keep_tests=keep_tests)
    python = prefix / "python.exe"
    names = [result["pip_names"][n] for n in result["remove_pip"]]
    for start in range(0, len(names), 40):
        _run([str(python), "-m", "pip", "uninstall", "--yes", "--quiet", *names[start:start + 40]])
    if result["remove_conda"]:
        _run([str(conda), "remove", "--prefix", str(prefix), "--offline", "--force", "--yes", "--quiet",
              *result["remove_conda"]])
    return result


def _pip_check(python: Path) -> set[str]:
    result = subprocess.run([str(python), "-m", "pip", "check"], capture_output=True, text=True)
    return {line.strip() for line in result.stdout.splitlines() if line.strip() and "No broken" not in line}


def check(prefix: Path, baseline: Optional[Path] = None) -> list[str]:
    """Versions as expected and nothing broken; returns the problems.

    ``pip check`` is compared with the source environment's own: KineSynth
    carries opencv-python 4.12.0.88 (declares numpy<2.3) with numpy 2.4.6 and
    every test passes on that pair, so a conflict it already has is reported
    as known, and only a conflict the trimming introduced fails the build.
    """
    require_marker(prefix)
    python = prefix / "python.exe"
    probe = (
        "import json, platform, cv2, numpy, yaml, PySide6, psutil;"
        "from importlib.metadata import version;"
        "print(json.dumps({'python': platform.python_version(), 'PySide6': PySide6.__version__,"
        " 'numpy': numpy.__version__, 'opencv-python': version('opencv-python'), 'cv2': cv2.__version__,"
        " 'pyzed': version('pyzed'), 'PyYAML': yaml.__version__, 'psutil': psutil.__version__}))"
    )
    output = subprocess.run([str(python), "-B", "-c", probe], capture_output=True, text=True, check=True).stdout
    found = json.loads(output)
    problems = [
        f"{name}: {found.get(name)} (beklenen {want})"
        for name, want in EXPECTED.items() if found.get(name) != want
    ]
    conflicts = _pip_check(python)
    known = _pip_check(baseline) if baseline is not None and baseline.is_file() else set()
    for line in sorted(conflicts & known):
        print(f"bilinen (kaynak ortamda da var): {line}")
    problems += [f"pip check: {line}" for line in sorted(conflicts - known)]
    print(json.dumps(found, indent=1))
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["prepare", "plan", "trim", "check"])
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--conda", default=None, help="base kurulumundaki conda.exe")
    parser.add_argument("--pyzed-wheel", default=None)
    parser.add_argument("--wheels", default=None, help="tekerleklerin kopyalanacağı klasör")
    parser.add_argument("--keep-tests", action="store_true", help="pytest ve bağımlılıklarını koru")
    parser.add_argument("--baseline-python", default=None,
                        help="kaynak ortamın python.exe'si: pip check karşılaştırması için")
    args = parser.parse_args(argv)
    prefix = Path(args.prefix)
    conda = Path(args.conda) if args.conda else None
    if args.command == "plan":
        result = plan(prefix, keep_tests=args.keep_tests)
        result.pop("pip_names")
        print(json.dumps(result, indent=1))
        return 0
    if args.command == "check":
        problems = check(prefix, Path(args.baseline_python) if args.baseline_python else None)
        for problem in problems:
            print("SORUN: " + problem)
        return 1 if problems else 0
    if conda is None or not conda.is_file():
        raise SystemExit("--conda ile base kurulumundaki conda.exe verilmeli.")
    if args.command == "prepare":
        clone(prefix, conda)
        wheels = Path(args.wheels) if args.wheels else prefix.parent / "wheels"
        detach_from_source(prefix, Path(args.pyzed_wheel) if args.pyzed_wheel else None, wheels)
        return 0
    result = trim(prefix, conda, keep_tests=args.keep_tests)
    print(f"kaldırılan: {len(result['remove_conda'])} conda, {len(result['remove_pip'])} pip paketi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
