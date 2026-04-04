#!/usr/bin/env python3
"""Named SVG corpus sources for visual auditing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CorpusSource:
    name: str
    repo_url: str
    checkout_dir_name: str
    svg_subpaths: tuple[str, ...]
    description: str


KNOWN_CORPORA: dict[str, CorpusSource] = {
    "resvg-test-suite": CorpusSource(
        name="resvg-test-suite",
        repo_url="https://github.com/linebender/resvg-test-suite.git",
        checkout_dir_name="resvg-test-suite",
        svg_subpaths=("tests",),
        description="resvg renderer stress suite with real SVG support edge cases.",
    ),
}


def default_external_corpus_root() -> Path:
    """Return the default root used for external corpora checkouts."""
    return Path(
        os.getenv(
            "SVG2OOXML_EXTERNAL_CORPUS_ROOT",
            "/tmp/svg2ooxml_external_corpora",
        )
    )


def list_named_corpora() -> tuple[str, ...]:
    """Return known corpus names in declaration order."""
    return tuple(KNOWN_CORPORA)


def corpus_checkout_dir(name: str, *, root: Path | None = None) -> Path:
    """Return the checkout directory for a named corpus."""
    source = _lookup_corpus(name)
    base_root = root or default_external_corpus_root()
    return base_root / source.checkout_dir_name


def resolve_named_corpus_inputs(
    names: list[str] | tuple[str, ...],
    *,
    root: Path | None = None,
) -> list[Path]:
    """Resolve named corpus checkouts to SVG input directories."""
    base_root = root or default_external_corpus_root()
    resolved: list[Path] = []
    for name in names:
        source = _lookup_corpus(name)
        checkout = base_root / source.checkout_dir_name
        if not checkout.exists():
            raise FileNotFoundError(
                f"Named corpus '{name}' is not checked out at {checkout}. "
                f"Clone {source.repo_url} there or run the bootstrap helper."
            )
        for subpath in source.svg_subpaths:
            candidate = checkout / subpath
            if not candidate.exists():
                raise FileNotFoundError(
                    f"Named corpus '{name}' is missing expected path {candidate}."
                )
            resolved.append(candidate)
    return resolved


def describe_named_corpora() -> dict[str, dict[str, str]]:
    """Return a serializable description of known corpora."""
    return {
        name: {
            "repo_url": source.repo_url,
            "checkout_dir_name": source.checkout_dir_name,
            "svg_subpaths": ", ".join(source.svg_subpaths),
            "description": source.description,
        }
        for name, source in KNOWN_CORPORA.items()
    }


def _lookup_corpus(name: str) -> CorpusSource:
    try:
        return KNOWN_CORPORA[name]
    except KeyError as exc:
        available = ", ".join(KNOWN_CORPORA)
        raise KeyError(
            f"Unknown named corpus '{name}'. Available: {available}"
        ) from exc


__all__ = [
    "CorpusSource",
    "KNOWN_CORPORA",
    "corpus_checkout_dir",
    "default_external_corpus_root",
    "describe_named_corpora",
    "list_named_corpora",
    "resolve_named_corpus_inputs",
]
