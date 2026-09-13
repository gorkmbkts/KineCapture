"""Turn ``tokens.json`` into a Qt stylesheet.

Pure string work - no Qt import - so the generated sheet can be diffed, tested
and (later) swapped for a WinUI ``ResourceDictionary`` emitter that reads the
same tokens.

The generator is strict on purpose: an ``@Token@`` the token file does not
define raises instead of silently producing ``@KcTypo@`` in the stylesheet,
where Qt would drop the whole rule and leave a widget mysteriously unstyled.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from .tokens import ThemeTokens, TokenError, load_tokens

_PLACEHOLDER = re.compile(r"@([A-Za-z][A-Za-z0-9_]*)@")

#: A hex colour or a bare pixel size written straight into the template rather
#: than taken from a token. Used by the tests, kept here so the rule and the
#: generator cannot drift apart.
LITERAL_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(")


def load_template() -> str:
    return (
        resources.files("kinecapture.studio.theme")
        .joinpath("studio.qss.tmpl")
        .read_text(encoding="utf-8")
    )


def template_tokens(template: str | None = None) -> tuple[str, ...]:
    """Every token the template asks for, in first-seen order."""
    text = template if template is not None else load_template()
    seen: dict[str, None] = {}
    for match in _PLACEHOLDER.finditer(text):
        seen.setdefault(match.group(1), None)
    return tuple(seen)


def render(tokens: ThemeTokens, template: str | None = None) -> str:
    """Substitute every ``@Token@`` in the template with its value."""
    text = template if template is not None else load_template()
    values: Mapping[str, Any] = tokens.all_tokens

    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            missing.append(name)
            return match.group(0)
        return str(values[name])

    rendered = _PLACEHOLDER.sub(substitute, text)
    if missing:
        raise TokenError(
            "Şablonda tanımsız token var: " + ", ".join(sorted(set(missing)))
        )
    return rendered


@lru_cache(maxsize=8)
def stylesheet_for(theme: str | None = None) -> str:
    """The finished stylesheet for one theme. Cached; tokens never change at runtime."""
    return render(load_tokens(theme))


__all__ = [
    "LITERAL_COLOUR",
    "load_template",
    "render",
    "stylesheet_for",
    "template_tokens",
]
