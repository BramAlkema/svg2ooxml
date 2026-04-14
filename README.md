<p align="center">
  <img src="assets/logo.png" alt="svg2ooxml" width="96">
</p>

<h1 align="center">svg2ooxml</h1>

<p align="center">
  <strong>Convert SVG to PowerPoint with native DrawingML fidelity.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/v/svg2ooxml" alt="PyPI"></a>
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/dm/svg2ooxml" alt="Downloads"></a>
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/pyversions/svg2ooxml" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
  <a href="https://github.com/BramAlkema/svg2ooxml/actions/workflows/test-suite.yml"><img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="Tests"></a>
</p>

---

Convert animated SVGs to native PowerPoint — programmatically, at scale, without Office. PowerPoint's own SVG import can't do animations, can't run headless, and can't batch.

svg2ooxml parses SVG markup, builds a typed intermediate representation, renders native DrawingML XML fragments, and packages them into valid `.pptx` files. 97% of the SVG feature set is covered. 525 W3C test SVGs pass OpenXML validation.

## Comparison

| Feature | svg2ooxml | [svg2pptx](https://pypi.org/project/svg2pptx/) | PowerPoint SVG import | [CairoSVG](https://pypi.org/project/cairosvg/) | LibreOffice |
|---|---|---|---|---|---|
| **Output format** | Native OOXML shapes | Native shapes (python-pptx) | Native shapes | PDF / PNG | Embedded image |
| **Animations** | Full SMIL → PowerPoint timing | None | None | N/A | None |
| **Gradients** | Linear, radial, pattern, transforms | None (first color only) | Basic | Good (raster) | Raster |
| **Filters** | Blur, shadow, color matrix + fallbacks | None | Partial | Good (raster) | Raster |
| **Clipping & masking** | Full fallback ladder | None | Basic | Good (raster) | Raster |
| **Text on curves** | WordArt with font embedding | None | Basic | Good (raster) | Raster |
| **CSS var() / calc()** | Resolved | None | None | None | None |
| **Per-char dx/dy/rotate** | Glyph outlines or native spacing | None | Flattened | Good (raster) | Raster |
| **Font embedding** | FontForge → EOT subset | System fonts | System fonts | N/A | N/A |
| **Bezier curves** | Exact (custGeom) | Approximated (line segments) | Exact | Exact (raster) | Raster |
| **Runs headless** | Yes (Python, Linux, container) | Yes | No (Windows + Office) | Yes | Yes (CLI) |
| **Batch speed** | ~800/min (75ms each) | Unknown | ~2/min (COM) | Fast (raster) | ~10/min |
| **OOXML validated** | 525/525 W3C SVGs pass | Unknown | N/A | N/A | N/A |
| **Security** | URI sanitization, SSRF blocking | None documented | N/A | N/A | N/A |
| **Accessibility** | title/desc → cNvPr descr | None | Discarded | N/A | N/A |
| **License** | AGPL-3.0 + Commercial | MIT | Proprietary | LGPL | MPL |
| **Price** | Free / from $5k/yr | Free | ~$150/yr (Office) | Free | Free |

**Key differentiators:** svg2ooxml is the only solution that converts SVG animations to native PowerPoint timing, handles the full CSS cascade (`var()`, `calc()`, `@media`), and validates output against both Python and .NET OOXML validators. Output is editable shapes, not rasterized images.

**Where others are better:** CairoSVG and LibreOffice produce pixel-perfect raster output because they use full rendering engines. svg2ooxml maps SVG features to the closest DrawingML equivalent, which may differ visually for complex filter chains. PowerPoint's native import has access to the actual text layout engine, so its text positioning may be more precise for system fonts.

## Features

- **Native DrawingML output** — shapes, text, and paths render as editable PowerPoint objects
- **SMIL animation support** — entrance, emphasis, exit, motion paths, rotate, scale, opacity, color
- **Empirical animation oracle** — structured SSOT of PowerPoint animation shapes that actually play at slideshow time, plus a [negative catalog](src/svg2ooxml/assets/animation_oracle/dead_paths.xml) of XML that parses but is silently dropped. Includes a companion [Claude skill](.claude/skills/pptx-animation/) for LLMs to emit working animation XML
- **Text rendering** — three-tier pipeline: native text with font embedding → WordArt for curves → Skia glyph outlines as last resort
- **SVG filter effects** — blur, drop shadow, color matrix, lighting, with EMF and raster fallbacks
- **Gradients & patterns** — linear, radial, pattern fills with userSpaceOnUse, focal point, transforms
- **CSS support** — custom properties (`var()`), `calc()`, `@media` queries, `oklab()`/`oklch()` colors
- **Masks & clipping** — clip paths, masks, group clips with native/EMF/raster fallback ladder
- **Compositing** — `mix-blend-mode`, `paint-order`, group opacity with overlap detection
- **Multi-slide export** — split multi-page SVGs into separate slides
- **Figma plugin** — browser-based export from Figma to PowerPoint
- **Extensible pipeline** — service registry with dependency injection for custom providers
- **Validated** — 525/525 W3C test SVGs pass both Python and .NET OpenXML validators

## Installation

```bash
pip install svg2ooxml
```

Optional extras for specific features:

```bash
pip install svg2ooxml[render]    # Skia rendering + visual comparison
pip install svg2ooxml[color]     # Advanced color space support
pip install svg2ooxml[slides]    # Google Slides integration
pip install svg2ooxml[api]       # FastAPI service
```

## Quick Start

### Python API

```python
from svg2ooxml import SvgToPptxExporter

exporter = SvgToPptxExporter()
exporter.export("input.svg", "output.pptx")
```

### CLI

```bash
svg2ooxml convert input.svg -o output.pptx
```

### Visual Review

Compare SVG source against the generated PowerPoint side-by-side:

```bash
svg2ooxml visual
```

## How It Works

```
SVG text
  → SVGParser.parse()            → ParseResult (lxml tree + metadata)
  → convert_parser_output()      → IRScene (typed intermediate representation)
  → DrawingMLWriter.render()     → DrawingMLRenderResult (XML fragments + assets)
  → PPTXPackageBuilder.write()   → .pptx file
```

## Development

```bash
./tools/bootstrap_venv.sh
source .venv/bin/activate
pip install -e .[dev,render,color,slides,api,cloud]
```

Use the project venv for all local Python, pytest, and visual-tool commands. On macOS, `./tools/bootstrap_venv.sh` now prefers Python 3.14 so Homebrew `fontforge` bindings and `skia-python` both load inside `.venv`.

```bash
pytest                            # full test suite
pytest -m "unit and not slow"     # fast dev loop
ruff check src tests              # lint
black src tests                   # format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Documentation

- [Architecture Decision Records](docs/adr/) — key design decisions
- [Roadmap](docs/ROADMAP.md) — project status and priorities
- [Testing guide](docs/testing.md) — test tiers and visual regression

## License

**Dual-licensed:**

- **Open source** — [AGPL-3.0](LICENSE) for open-source projects and personal use.
- **Commercial** — [Commercial License](LICENSE-COMMERCIAL.md) for proprietary software, SaaS, and embedding. Contact [license@svg2ooxml.com](mailto:license@svg2ooxml.com).

Documentation and content assets are licensed under [CC BY-NC-SA 4.0](LICENSE-CONTENT).
