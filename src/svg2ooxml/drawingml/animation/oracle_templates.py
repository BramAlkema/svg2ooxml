"""Safe template helpers for animation oracle XML snippets."""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "find_template_tokens",
    "render_xml_template",
    "resolve_oracle_child_path",
]

_TOKEN_RE = re.compile(r"\{([A-Z0-9_]+)\}")


def find_template_tokens(text: str) -> set[str]:
    """Return placeholder tokens used by an oracle template."""
    return set(_TOKEN_RE.findall(text))


def render_xml_template(text: str, substitutions: Mapping[str, object]) -> str:
    """Render an XML template with escaped token values.

    Oracle snippets place tokens in XML attributes and text nodes. Treat every
    substitution as XML data, not markup, so runtime values cannot break out of
    their template slot.
    """
    missing = find_template_tokens(text) - set(substitutions)
    if missing:
        raise ValueError(f"Missing oracle template tokens: {', '.join(sorted(missing))}")

    rendered = text
    for key, value in substitutions.items():
        rendered = rendered.replace("{" + key + "}", _escape_xml_value(value))

    unresolved = find_template_tokens(rendered)
    if unresolved:
        raise ValueError(
            f"Unresolved oracle template tokens: {', '.join(sorted(unresolved))}"
        )
    return rendered


def resolve_oracle_child_path(root: Path, *parts: str) -> Path:
    """Resolve a path under *root*, rejecting absolute/path-traversal inputs."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Oracle path escapes root: {candidate}") from exc
    return candidate


def _escape_xml_value(value: object) -> str:
    return html.escape(str(value), quote=True)
