"""What actually ends up inside a built distribution.

The university crest is loaded through ``importlib.resources``, which works
perfectly from a checkout whether or not the packaging declares it. The failure
mode is therefore invisible in development and total in an install: the wheel
ships without the PNG and the crest silently disappears for every user who did
not clone the repository. Only a real build catches that, so these tests do one
- inside ``tmp_path``, from a copy of the sources, so neither the build's
intermediate folders nor its output land in the working tree.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import textwrap
import zipfile
from pathlib import Path

import pytest

from kinecapture.gui.assets import YTU_LOGO, asset_bytes

ROOT = Path(__file__).resolve().parents[1]
ASSET_MEMBER = f"kinecapture/gui/assets/{YTU_LOGO}"

#: Driven through the PEP 517 backend the project itself declares, rather than
#: through a build front-end that may or may not be installed. This is the same
#: code path pip takes, so a package-data mistake shows up here exactly as it
#: would for a user running ``pip install``.
_BUILD_SCRIPT = textwrap.dedent(
    """
    import sys
    from setuptools import build_meta

    kind, out_dir = sys.argv[1], sys.argv[2]
    builder = build_meta.build_wheel if kind == "wheel" else build_meta.build_sdist
    print(builder(out_dir))
    """
)


@pytest.fixture(scope="module")
def source_copy(tmp_path_factory):
    """A throwaway copy of everything the build needs, and nothing else."""
    staging = tmp_path_factory.mktemp("packaging") / "source"
    staging.mkdir()
    for name in ("pyproject.toml", "README.md"):
        shutil.copy2(ROOT / name, staging / name)
    shutil.copytree(
        ROOT / "src",
        staging / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return staging


def build(kind: str, source: Path) -> Path:
    """Build one distribution inside the copy and return its path."""
    out_dir = source.parent / f"dist-{kind}"
    out_dir.mkdir(exist_ok=True)
    script = source.parent / "run_build.py"
    script.write_text(_BUILD_SCRIPT, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(script), kind, str(out_dir)],
        cwd=source,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, (
        f"the {kind} could not be built:\n{completed.stdout}\n{completed.stderr}"
    )
    name = completed.stdout.strip().splitlines()[-1]
    built = out_dir / name
    assert built.is_file(), f"the backend reported {name!r} but it is not there"
    return built


def test_the_wheel_carries_the_logo(source_copy):
    wheel = build("wheel", source_copy)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert ASSET_MEMBER in names, (
            "package-data does not put the crest in the wheel; an installed "
            "application would start without a logo"
        )
        data = archive.read(ASSET_MEMBER)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data == asset_bytes(YTU_LOGO), "the wheel copy must not be re-encoded"


def test_the_sdist_carries_the_logo(source_copy):
    sdist = build("sdist", source_copy)
    with tarfile.open(sdist) as archive:
        members = archive.getnames()
    assert any(name.endswith(ASSET_MEMBER) for name in members), (
        "the source distribution is missing the crest"
    )


def test_the_build_leaves_the_working_tree_alone(source_copy, tmp_path):
    """The test must not be the reason ``git status`` is dirty.

    setuptools writes ``build/`` and ``*.egg-info/`` next to whatever it is
    building. Those belong in the throwaway copy, so the assertion is that
    the build happened there - not that the repository is free of artifacts
    an editable install may have left long before this ran.
    """
    wheel = build("wheel", source_copy)
    assert source_copy in wheel.parents or source_copy.parent in wheel.parents
    assert ROOT not in wheel.parents

    residue = list(source_copy.glob("*.egg-info")) + list(
        source_copy.glob("src/*.egg-info")
    )
    assert residue, "the build really did run inside the copy"


def test_the_asset_is_declared_as_package_data():
    """The cheap check, so a missing declaration is caught without a build."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"kinecapture.gui.assets" = ["*.png"]' in pyproject


def test_the_assets_directory_is_an_importable_package():
    """``importlib.resources`` needs a package, not just a folder."""
    assert (ROOT / "src" / "kinecapture" / "gui" / "assets" / "__init__.py").is_file()


def test_the_logo_resolves_without_the_repository_layout():
    """No path built from ``__file__`` up to a checkout folder."""
    import inspect

    from kinecapture.gui import assets

    source = inspect.getsource(assets)
    assert "resources.files" in source
    assert "parents[" not in source, "no walking up to a repository root"
    assert asset_bytes(YTU_LOGO)
