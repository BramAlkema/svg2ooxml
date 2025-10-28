"""Launch the visual comparison web server."""

from __future__ import annotations

import click


@click.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address for the web server")
@click.option("--port", default=8000, show_default=True, type=int, help="Port for the web server")
@click.option(
    "--reload/--no-reload",
    default=False,
    show_default=True,
    help="Enable uvicorn reload (development only)",
)
def visual(host: str, port: int, reload: bool) -> None:
    """Serve a browser-based SVG vs PPTX comparison tool."""

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - guard for missing extra
        raise click.ClickException(
            "uvicorn is required. Install svg2ooxml with the [api] extra."
        ) from exc

    uvicorn.run(
        "tools.visual.server:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


__all__ = ["visual"]

