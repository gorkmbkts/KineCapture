"""Design tokens: the single source of truth for colour, metric and type.

``tokens.json`` is data, this module is the reader. Neither imports Qt, so the
same file can be turned into a WinUI ``ResourceDictionary`` later without
touching anything else.

Every value in the interface comes from here. A widget that writes its own
``#1a1c20`` breaks the one guarantee this file exists to give - that the whole
product can be re-themed from one place - so
``tests/test_studio_layers.py`` fails the build when one does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

TOKENS_SCHEMA_VERSION = "1.1.0"

#: Tokens whose colour is allowed to mean something. Documented here as well as
#: in ``tokens.json`` because this is the list code reads.
SEMANTIC_COLOURS = {
    "KcStatusRecording": "kayıt ve hata",
    "KcStatusWarning": "uyarı ve belirsizlik",
    "KcStatusLive": "canlı ve tamam",
    "KcAccentPrimary": "seçim ve odak",
}

#: Movement-class colours, in the order classes are assigned them. A class
#: keeps its colour for the life of the project, so this order is a contract:
#: reordering it would repaint every timeline a user has learned to read.
CLASS_COLOURS = tuple(f"KcClassColour{index}" for index in range(1, 9))

#: Error-class colours. A separate family on purpose - warm against the cool
#: movement set - so the two kinds of interval are distinguishable before any
#: label is read.
FAULT_COLOURS = tuple(f"KcFaultColour{index}" for index in range(1, 7))


def class_colour_token(index: int, *, fault: bool = False) -> str:
    """The colour token for the ``index``-th class of its kind.

    Wraps around rather than running out: a project with more classes than
    colours reuses them in the same order every time, which keeps the mapping
    stable instead of leaving the extra classes unpainted.
    """
    palette = FAULT_COLOURS if fault else CLASS_COLOURS
    return palette[int(index) % len(palette)]


class TokenError(ValueError):
    """A token was asked for that ``tokens.json`` does not define."""


@dataclass(frozen=True)
class ThemeTokens:
    """One resolved theme: colours plus the shared metrics and typography."""

    name: str
    label: str
    is_dark: bool
    colours: Mapping[str, str]
    metrics: Mapping[str, int]
    typography: Mapping[str, Any]

    def colour(self, token: str) -> str:
        try:
            return self.colours[token]
        except KeyError as exc:  # pragma: no cover - guarded by tests
            raise TokenError(f"Tanımsız renk token'ı: {token}") from exc

    def metric(self, token: str) -> int:
        try:
            return int(self.metrics[token])
        except KeyError as exc:  # pragma: no cover - guarded by tests
            raise TokenError(f"Tanımsız ölçü token'ı: {token}") from exc

    def type_value(self, token: str) -> Any:
        try:
            return self.typography[token]
        except KeyError as exc:  # pragma: no cover - guarded by tests
            raise TokenError(f"Tanımsız tipografi token'ı: {token}") from exc

    def font_size(self, token: str) -> int:
        return int(self.type_value(token))

    def resolve(self, token: str) -> Any:
        """Look a token up in whichever group owns it."""
        for group in (self.colours, self.metrics, self.typography):
            if token in group:
                return group[token]
        raise TokenError(f"Tanımsız token: {token}")

    @property
    def all_tokens(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self.typography)
        merged.update(self.metrics)
        merged.update(self.colours)
        return merged


@lru_cache(maxsize=1)
def _document() -> dict[str, Any]:
    text = (
        resources.files("kinecapture.studio.theme")
        .joinpath("tokens.json")
        .read_text(encoding="utf-8")
    )
    document = json.loads(text)
    version = document.get("schema_version")
    if version != TOKENS_SCHEMA_VERSION:
        raise TokenError(
            f"tokens.json sürümü {version}, beklenen {TOKENS_SCHEMA_VERSION}"
        )
    return document


def theme_names() -> tuple[str, ...]:
    return tuple(_document()["themes"])


def default_theme_name() -> str:
    return str(_document()["default_theme"])


@lru_cache(maxsize=8)
def load_tokens(theme: str | None = None) -> ThemeTokens:
    """Resolve one theme. An unknown name falls back to the default theme.

    Falling back rather than raising is deliberate: a stale preference file
    naming a theme that no longer exists must not stop the application from
    starting.
    """
    document = _document()
    themes = document["themes"]
    name = theme if theme in themes else document["default_theme"]
    entry = themes[name]
    return ThemeTokens(
        name=name,
        label=str(entry["label"]),
        is_dark=bool(entry["is_dark"]),
        colours=dict(entry["colours"]),
        metrics=dict(document["metrics"]),
        typography=dict(document["typography"]),
    )


def colour_tokens() -> tuple[str, ...]:
    """Colour token names, identical in every theme (verified by tests)."""
    themes = _document()["themes"]
    return tuple(sorted(next(iter(themes.values()))["colours"]))


__all__ = [
    "CLASS_COLOURS",
    "FAULT_COLOURS",
    "class_colour_token",
    "SEMANTIC_COLOURS",
    "TOKENS_SCHEMA_VERSION",
    "ThemeTokens",
    "TokenError",
    "colour_tokens",
    "default_theme_name",
    "load_tokens",
    "theme_names",
]
