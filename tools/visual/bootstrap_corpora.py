#!/usr/bin/env python3
"""Clone or update named external SVG corpora used by visual tooling."""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path

from tools.visual.corpus_sources import (
    KNOWN_CORPORA,
    corpus_checkout_dir,
    default_external_corpus_root,
    list_named_corpora,
)

logger = logging.getLogger("bootstrap_corpora")


def ensure_corpus_checkout(
    name: str,
    *,
    root: Path | None = None,
    update: bool = False,
) -> Path:
    """Clone the corpus if missing, optionally update an existing checkout."""
    source = KNOWN_CORPORA[name]
    checkout = corpus_checkout_dir(name, root=root)
    checkout.parent.mkdir(parents=True, exist_ok=True)

    if checkout.exists():
        if update:
            logger.info("Updating %s in %s", name, checkout)
            subprocess.run(
                ["git", "-C", str(checkout), "pull", "--ff-only"],
                check=True,
            )
        else:
            logger.info("Using existing checkout for %s at %s", name, checkout)
        return checkout

    logger.info("Cloning %s into %s", name, checkout)
    subprocess.run(
        ["git", "clone", "--depth", "1", source.repo_url, str(checkout)],
        check=True,
    )
    return checkout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "names",
        nargs="*",
        choices=list_named_corpora(),
        default=list(list_named_corpora()),
        help="Named corpora to clone or update.",
    )
    parser.add_argument(
        "--root",
        default=str(default_external_corpus_root()),
        help="Directory to hold the external corpus checkouts.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Pull the latest changes for an existing checkout.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    root = Path(args.root)
    for name in args.names:
        ensure_corpus_checkout(name, root=root, update=args.update)


if __name__ == "__main__":
    main()
