"""The architectural boundary that makes a WinUI 3 port a one-layer rewrite.

``studio/services`` and ``studio/viewmodels`` must be importable and usable
with **no Qt at all**. This is checked the only way that cannot rot: a
subprocess where importing PySide6 raises, so a stray ``from PySide6 import``
anywhere in either package - now or in any later phase - fails the build.

The second rule checked here is that no view writes a literal colour. The whole
point of ``tokens.json`` is that one edit re-themes the product; a hard-coded
``#1a1c20`` in a widget silently opts that widget out.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from kinecapture.studio.theme import (
    TokenError,
    colour_tokens,
    load_tokens,
    render,
    stylesheet_for,
    template_tokens,
    theme_names,
)
from kinecapture.studio.theme.generator import LITERAL_COLOUR

STUDIO = Path(__file__).resolve().parents[1] / "src" / "kinecapture" / "studio"

_QT_FREE_PROGRAM = """
import sys

class _Blocked:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)

    def find_spec(self, name, path=None, target=None):
        if name == "PySide6" or name.startswith("PySide6."):
            raise AssertionError("Qt import edildi: " + name)
        if name == "shiboken6" or name.startswith("shiboken6."):
            raise AssertionError("Qt import edildi: " + name)
        return None

sys.meta_path.insert(0, _Blocked())

import kinecapture.studio.services as services
import kinecapture.studio.viewmodels as viewmodels
import kinecapture.studio.theme as theme

assert not any(m == "PySide6" or m.startswith("PySide6.") for m in sys.modules), sorted(
    m for m in sys.modules if m.startswith("PySide6")
)

# Not just importable - usable. Build a viewmodel and drive it.
from kinecapture.studio.viewmodels.observable import Observable
from kinecapture.studio.viewmodels.navigation import DESTINATIONS

seen = []
value = Observable(0)
value.subscribe(seen.append)
value.set(1)
value.set(1)
assert seen == [1], seen
assert len(DESTINATIONS) == 8, len(DESTINATIONS)
assert theme.stylesheet_for("dark")

print("QT_FREE_OK")
"""


def test_services_and_viewmodels_import_without_qt() -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-c", _QT_FREE_PROGRAM],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "QT_FREE_OK" in result.stdout


def _qt_imports(path: Path) -> list[str]:
    """Qt modules imported by ``path``, found in the syntax tree.

    Parsed rather than grepped: the docstrings in these files legitimately talk
    *about* PySide6, and a test that cannot tell an explanation from an import
    would train everyone to stop mentioning the rule it enforces.
    """
    import ast

    found: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(
                alias.name
                for alias in node.names
                if alias.name.split(".")[0] in {"PySide6", "shiboken6"}
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"PySide6", "shiboken6"}:
                found.append(node.module)
    return found


@pytest.mark.parametrize("package", ["services", "viewmodels", "theme"])
def test_lower_layers_import_no_qt(package: str) -> None:
    """A syntax-tree check, so the failure names the offending file directly."""
    offenders = {
        path.name: imports
        for path in sorted((STUDIO / package).rglob("*.py"))
        if (imports := _qt_imports(path))
    }
    assert not offenders, f"{package}/ içinde Qt importu: {offenders}"


# ------------------------------------------------------------------- tokens


def test_every_theme_defines_the_same_colour_tokens() -> None:
    expected = set(colour_tokens())
    for name in theme_names():
        assert set(load_tokens(name).colours) == expected, name


def test_template_resolves_completely_in_every_theme() -> None:
    for name in theme_names():
        sheet = stylesheet_for(name)
        assert "@" not in sheet.split("*/", 1)[1], name


def test_generator_refuses_an_unknown_token() -> None:
    with pytest.raises(TokenError):
        render(load_tokens("dark"), template="QWidget { color: @KcNoSuchToken@; }")


def test_unknown_theme_falls_back_instead_of_raising() -> None:
    """A stale preference must not stop the application from starting."""
    assert load_tokens("solarized-banana").name == load_tokens(None).name


def test_views_write_no_literal_colours() -> None:
    offenders: list[str] = []
    for path in sorted((STUDIO / "views").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if LITERAL_COLOUR.search(code):
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"Token yerine literal renk: {offenders}"


def test_stylesheet_template_writes_no_literal_colours() -> None:
    from kinecapture.studio.theme.generator import load_template

    body = load_template().split("*/", 1)[1]
    assert not LITERAL_COLOUR.search(body)


def test_every_template_token_exists_in_the_token_file() -> None:
    known = set(load_tokens("dark").all_tokens)
    missing = [name for name in template_tokens() if name not in known]
    assert not missing, missing
