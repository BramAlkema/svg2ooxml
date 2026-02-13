"""Source loading/splitting helpers for the convert CLI command."""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

import click

from svg2ooxml.core.multipage import split_svg_into_pages
from svg2ooxml.core.pptx_exporter import SvgPageSource


def looks_like_uri(value: str) -> bool:
    """Return whether a source string is an HTTP(S) URI."""

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def fetch_svg_from_uri(uri: str) -> str:
    """Download and decode SVG text from a remote URI."""

    try:
        with urlopen(uri) as response:  # type: ignore[call-arg]
            charset = "utf-8"
            if hasattr(response, "headers"):
                charset = response.headers.get_content_charset() or charset  # type: ignore[attr-defined]
            data = response.read()
    except (HTTPError, URLError, ValueError) as exc:  # pragma: no cover - network errors vary by env
        raise click.ClickException(f"Failed to fetch SVG from {uri}: {exc}") from exc

    try:
        return data.decode(charset or "utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - rare invalid charset
        raise click.ClickException(f"Failed to decode SVG from {uri}: {exc}") from exc


def derive_default_output(source_path: Path | None, source_uri: str | None) -> Path:
    """Return output PPTX path when no explicit output file is given."""

    if source_path is not None:
        return source_path.with_suffix(".pptx")

    parsed = urlparse(source_uri or "")
    stem = Path(parsed.path).stem or "document"
    return Path.cwd() / f"{stem}.pptx"


def derive_title(source_path: Path | None, source_uri: str | None, fallback: str | None = None) -> str:
    """Return default presentation title for the given source."""

    if fallback:
        return fallback
    if source_path is not None:
        return source_path.stem
    parsed = urlparse(source_uri or "")
    stem = Path(parsed.path).stem
    return stem or "remote_svg"


def load_source(source: str) -> tuple[str, str | None, Path | None]:
    """Return SVG text and metadata from local path or URI source."""

    if looks_like_uri(source):
        svg_text = fetch_svg_from_uri(source)
        parsed = urlparse(source)
        title = Path(parsed.path).stem or None
        return svg_text, title, None

    input_path = Path(source)
    if not input_path.exists():
        raise click.ClickException(f"Input path does not exist: {source}")
    try:
        svg_text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise click.ClickException(f"Failed to read SVG file {source}: {exc}") from exc

    return svg_text, input_path.stem, input_path


def split_pages(svg_text: str, base_title: str | None) -> list[SvgPageSource]:
    """Split a multipage SVG string into per-page slide sources."""

    pages = split_svg_into_pages(svg_text)
    result: list[SvgPageSource] = []
    for index, page in enumerate(pages, start=1):
        title = page.title or (f"{base_title} {index}" if base_title else f"Page {index}")
        name = f"page_{index}"
        result.append(SvgPageSource(svg_text=page.content, title=title, name=name))
    return result


__all__ = [
    "derive_default_output",
    "derive_title",
    "fetch_svg_from_uri",
    "load_source",
    "looks_like_uri",
    "split_pages",
]
