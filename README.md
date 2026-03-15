<p align="center">
  <img src="https://raw.githubusercontent.com/BramAlkema/svg2ooxml/main/assets/logo.png" alt="svg2ooxml" width="96">
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
  <a href="https://github.com/BramAlkema/svg2ooxml/actions/workflows/workflow.yml"><img src="https://github.com/BramAlkema/svg2ooxml/actions/workflows/workflow.yml/badge.svg" alt="CI"></a>
</p>

---

svg2ooxml parses SVG markup, builds a typed intermediate representation, renders native DrawingML XML fragments, and packages them into valid `.pptx` files. Shapes, text, gradients, filters, masks, clipping paths, and SMIL animations are converted to editable PowerPoint objects — not rasterized images.

## Features

- **Native DrawingML output** — shapes, text, and paths render as editable PowerPoint objects
- **SMIL animation support** — entrance, emphasis, exit, and motion path animations
- **SVG filter effects** — blur, drop shadow, color matrix, and compositing
- **Gradients & patterns** — linear, radial, and pattern fills with correct coordinate transforms
- **Masks & clipping** — SVG clip paths and masks mapped to OOXML equivalents
- **Multi-slide export** — split multi-page SVGs into separate slides
- **Figma plugin** — browser-based export from Figma to PowerPoint
- **Extensible pipeline** — service registry with dependency injection for custom providers

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
pip install -r requirements-dev.txt
```

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

Source code is licensed under [AGPL-3.0-only](LICENSE). Documentation and content assets are licensed under [CC BY-NC-SA 4.0](LICENSE-CONTENT).
