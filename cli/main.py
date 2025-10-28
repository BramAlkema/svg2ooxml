"""Command line entry point for svg2ooxml."""

from __future__ import annotations

from importlib import metadata

import click

from .commands.auth import auth
from .commands.convert import convert
from .commands.visual import visual


def _package_version() -> str:
    try:
        return metadata.version("svg2ooxml")
    except metadata.PackageNotFoundError:  # pragma: no cover - editable installs
        return "0.0.0"


@click.group()
@click.version_option(version=_package_version(), prog_name="svg2ooxml")
def cli() -> None:
    """SVG to Office Open XML conversion utilities."""


cli.add_command(convert)
cli.add_command(auth)
cli.add_command(visual)


def run_cli() -> None:
    """Invoke the CLI entry point."""

    cli()


__all__ = ["run_cli"]


if __name__ == "__main__":  # pragma: no cover - manual invocation
    run_cli()
