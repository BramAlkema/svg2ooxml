# Raster Colour Normalization

The `ColorSpaceService` now supports multiple levels of raster normalization. Policies can choose between:

| Policy value | Effect |
|--------------|--------|
| `skip` | leave payload unchanged; metadata records the skip |
| `rgb` (default) | convert to sRGB if ICC profile or mode differs |
| `full` | force RGBA output for downstream effects that require alpha |
| `perceptual` | requires the `svg2ooxml[color]` extra; pixel data is converted into linear RGB using OKLab heuristics, producing consistent gradients when raster assets are composited |

Normalisation metadata is attached under `policy.image.colorspace_metadata`, including source/output formats, palette statistics, and (when enabled) perceptual transform details. For a command-line view of the same diagnostics, see [`color-advanced.md`](./color-advanced.md) and the `tools/color_palette_report.py` helper.

## Installing optional dependencies

```
pip install -e .[color] pillow
```

The `color` extra brings in NumPy + colorspacious; Pillow remains optional in core workflows but is recommended when exercising raster conversions.
