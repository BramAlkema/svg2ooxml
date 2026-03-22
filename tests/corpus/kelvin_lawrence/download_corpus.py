"""Download Kelvin Lawrence SVG samples for validation testing.

Source: https://www.kelvinlawrence.net/svg/
These files are NOT redistributed — this script fetches them on demand.

Usage:
    python -m tests.corpus.kelvin_lawrence.download_corpus
"""

from __future__ import annotations

import re
from pathlib import Path

CORPUS_DIR = Path(__file__).parent
BASE_URL = "https://www.kelvinlawrence.net/svg"

# Representative subset: 45 samples across all SVG feature categories
SAMPLES = [
    # Animations
    "animate-spin.svg", "animate-orbit.html", "animate-gradient.html",
    "animate-opacity.html", "animate-curtain.html", "animate-path.html",
    "animate-color1.html", "animate-size.html",
    # Transforms
    "transform-skewXY.html", "transform-scale.html",
    "transform-matrix.html", "transform-flip.html",
    # Text
    "text-path.html", "text-path2.html", "text-rotated.html",
    "text-span.html", "text-vertical.html",
    # Gradients
    "linear-gradients.html", "radial1.html",
    "linear-gradients-repeat.html",
    # Filters
    "filter-blur.html", "filter-blend-multiply.html",
    "filter-color-matrix.html", "filter-turbulence.html",
    "filter-lighting.html", "filter-saturate.html",
    # Clipping & Masking
    "clip-complex.html", "clip-text.html", "clip-ring.html",
    "mask-gradient.html", "mask1.html", "mask-image.html",
    # Patterns
    "pattern1.html", "pattern2.html",
    # Shapes & Paths
    "bezier-art1.html", "arcs.html", "basic-shapes.html",
    "fill-rule.html", "stroke-dasharray.html", "line-dash.html",
    # Complex compositions
    "sierpinski-depth7-filled.html", "koch.html",
    "circle-art1.html", "diamonds-128-color.html", "mosaic.html",
]


def _extract_svg(html: str) -> str | None:
    """Extract <svg>...</svg> from HTML wrapper."""
    m = re.search(r"(<svg[^>]*>.*?</svg>)", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    svg = m.group(1)
    if not svg.startswith("<?xml"):
        svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg
    if "xmlns=" not in svg.split(">")[0]:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    if "xlink:" in svg and "xmlns:xlink" not in svg.split(">")[0]:
        svg = svg.replace(
            "<svg", '<svg xmlns:xlink="http://www.w3.org/1999/xlink"', 1
        )
    return svg


def download(*, force: bool = False) -> list[Path]:
    """Download samples and return list of SVG paths."""
    import time
    import urllib.request

    downloaded: list[Path] = []
    for i, name in enumerate(SAMPLES):
        out = CORPUS_DIR / Path(name).with_suffix(".svg").name
        if out.exists() and not force:
            downloaded.append(out)
            continue
        url = f"{BASE_URL}/{name}"
        if i > 0:
            time.sleep(0.3)  # rate limit courtesy
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  SKIP {name}: {e}")
            continue
        if name.endswith(".svg"):
            out.write_text(content)
        else:
            svg = _extract_svg(content)
            if svg:
                out.write_text(svg)
            else:
                print(f"  SKIP {name}: no SVG found")
                continue
        downloaded.append(out)
    return downloaded


def corpus_svgs() -> list[Path]:
    """Return cached SVGs, downloading if needed."""
    existing = sorted(CORPUS_DIR.glob("*.svg"))
    if len(existing) >= len(SAMPLES) * 0.8:
        return existing
    return download()


if __name__ == "__main__":
    paths = download(force=True)
    print(f"Downloaded {len(paths)} SVGs to {CORPUS_DIR}")
