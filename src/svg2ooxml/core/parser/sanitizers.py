"""SVG sanitiser helpers invoked before parsing."""

from __future__ import annotations


def sanitize_svg(*_args, **_kwargs) -> None:
    """Clean SVG content before parsing (migration placeholder)."""

    raise NotImplementedError("SVG sanitizers not ported yet.")


__all__ = ["sanitize_svg"]
