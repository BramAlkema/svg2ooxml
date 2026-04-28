<p align="center">
  <img src="https://raw.githubusercontent.com/BramAlkema/svg2ooxml/main/assets/logo.png" alt="svg2ooxml" width="96">
</p>

<h1 align="center">svg2ooxml</h1>

<p align="center">
  <strong>SVG-to-PowerPoint converter with native, editable PresentationML output.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/v/svg2ooxml" alt="PyPI"></a>
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/dm/svg2ooxml" alt="Downloads"></a>
  <a href="https://pypi.org/project/svg2ooxml/"><img src="https://img.shields.io/pypi/pyversions/svg2ooxml" alt="Python"></a>
  <a href="https://github.com/BramAlkema/svg2ooxml/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-blue.svg" alt="License: AGPL-3.0"></a>
</p>

---

svg2ooxml parses SVG markup, builds a typed intermediate representation, renders native DrawingML XML fragments, and packages them into valid `.pptx` files. Shapes, text, gradients, filters, masks, clipping paths, and SMIL animations are converted to editable PowerPoint objects — not rasterized images.

svg2ooxml is the converter package. PowerPoint behavior research, authored control decks, and durable oracle evidence are maintained in the companion repository `openxml-audit` so the package documentation can stay focused on conversion.

The same distribution also carries `figma2gslides`, a tool package built on top
of the converter for Figma and Google Slides workflows. It is intentionally
separate from the supported `svg2ooxml` converter API.

## Features

- **Native DrawingML output** — shapes, text, and paths render as editable PowerPoint objects
- **SMIL animation support** — entrance, emphasis, exit, and motion path animations
- **SVG filter effects** — blur, drop shadow, color matrix, and compositing
- **Gradients & patterns** — linear, radial, and pattern fills with correct coordinate transforms
- **Masks & clipping** — SVG clip paths and masks mapped to OOXML equivalents
- **Multi-slide export** — split multi-page SVGs into separate slides
- **Extensible pipeline** — service registry with dependency injection for custom providers

## Installation

```bash
pip install svg2ooxml
```

Optional extras:

```bash
pip install svg2ooxml[render]    # Skia rendering + visual comparison
pip install svg2ooxml[color]     # Advanced color space support
pip install svg2ooxml[figma2gslides]  # Figma/Google Slides tool runtime
```

## Current Release

`0.7.6` is an architecture/dedupe release after the large-file split work:
geometry, WordArt, gradient, filter, resvg, animation, and PPTX internals are
split into smaller modules with shared helper paths, while base installs avoid
eager optional render dependencies.

## Quick Start

```python
from svg2ooxml import SvgToPptxExporter

exporter = SvgToPptxExporter()
exporter.export("input.svg", "output.pptx")
```

### CLI

```bash
svg2ooxml convert input.svg -o output.pptx
```

## How It Works

```
SVG text
  → SVGParser.parse()            → ParseResult (lxml tree + metadata)
  → convert_parser_output()      → IRScene (typed intermediate representation)
  → DrawingMLWriter.render()     → DrawingMLRenderResult (XML fragments + assets)
  → PPTXPackageBuilder.write()   → .pptx file
```

## Links

- [GitHub](https://github.com/BramAlkema/svg2ooxml)
- [Documentation guide](https://github.com/BramAlkema/svg2ooxml/blob/main/docs/README.md)
- [Testing guide](https://github.com/BramAlkema/svg2ooxml/blob/main/docs/testing.md)
- [Animation documentation map](https://github.com/BramAlkema/svg2ooxml/blob/main/docs/internals/animation-documentation-map.md)
- [Changelog](https://github.com/BramAlkema/svg2ooxml/releases)
- [openxml-audit](https://github.com/BramAlkema/openxml-audit)

## License

Dual-licensed: [AGPL-3.0](https://github.com/BramAlkema/svg2ooxml/blob/main/LICENSE) for open source, [Commercial License](https://github.com/BramAlkema/svg2ooxml/blob/main/LICENSE-COMMERCIAL.md) for proprietary use. Contact license@svg2ooxml.com.
