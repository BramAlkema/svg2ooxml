# Advanced Colour Toolkit

The ported svg2pptx colour engine lives under `svg2ooxml.color.advanced` and
provides a fluent API for perceptual operations. Install the optional stack via:

```bash
pip install -e .[color]
# optional rasterization helpers
pip install -e .[render]
```

This pulls in NumPy, colorspacious, and Pillow so harmonies and raster analysis
work out of the box.

## Working with `AdvancedColor`

```python
from svg2ooxml.color import AdvancedColor

accent = AdvancedColor("#336699")
print(accent.lighten(0.15).hex(include_hash=True))  # '#5a8dc0'

complement = accent.darken(0.2).saturate(0.25)
print(complement.rgba())  # (33, 61, 91, 1.0)
```

The API mirrors svg2pptx: conversions to OKLab/OKLCh, delta-E calculations, and
pixel-safe hex output are all available. Combine it with `ColorHarmony` to
generate palettes quickly:

```python
from svg2ooxml.color import ColorHarmony

harmony = ColorHarmony(accent)
print([color.hex(include_hash=True) for color in harmony.triadic()])
```

Batch workflows benefit from `ColorBatch`, which vectorises heavy operations:

```python
from svg2ooxml.color import ColorBatch

batch = ColorBatch(["#e63946", "#457b9d", "#1d3557"])
for colour in batch.lighten(0.08).to_colors():
    print(colour.hex(include_hash=True))
```

## Palette report helper

`tools/color_palette_report.py` wraps the advanced stack in a small CLI.

```
python tools/color_palette_report.py --image assets/example.png
python tools/color_palette_report.py "#ff6b6b" "#ffe66d" "#4ecdc4"
```

The report surfaces palette summaries (OKLab statistics, recommended colour
space), harmony suggestions, and preview transformations. When Pillow is
available, `--image` samples pixels before running the analysis.

## Raster perceptual mode

Set `policy.image.colorspace_normalization` to `perceptual` to linearise raster
payloads through the advanced engine. The `ColorSpaceService` records metadata
under `policy.image.colorspace_metadata` so downstream tooling can inspect
profiles, conversions, and palette diagnostics.

## Reference

- `svg2ooxml.color.advanced.core.Color` – fluent API
- `svg2ooxml.color.advanced.harmony.ColorHarmony` – harmony helpers
- `svg2ooxml.color.advanced.batch.ColorBatch` – vectorised manipulation
- `svg2ooxml.color.analysis.summarize_palette` – shared palette statistics
For raster reports that mirror policy behaviour, see the
[`rasterization`](./rasterization.md) guide.
