# W3C SVG Test Suite Corpus

This directory contains corpus metadata and test results for the W3C SVG Test Suite integration.

## Overview

The svg2ooxml project includes 525 SVG files from the W3C SVG 1.1 Test Suite (447 non-animation tests). These provide comprehensive coverage of SVG features and are excellent for measuring conversion quality.

## Quick Start

### Run All Test Categories

```bash
./tests/corpus/run_w3c_corpus.sh all
```

### Run Specific Category

```bash
./tests/corpus/run_w3c_corpus.sh gradients
./tests/corpus/run_w3c_corpus.sh shapes
./tests/corpus/run_w3c_corpus.sh paths
```

### Run with Different Mode

```bash
./tests/corpus/run_w3c_corpus.sh gradients --mode legacy
```

## Available Categories

| Category | Tests | Description | Expected Native Rate |
|----------|-------|-------------|---------------------|
| `gradients` | 23 | Linear and radial gradients | 80% |
| `shapes` | 30 | Basic shapes (rect, circle, ellipse) | 95% |
| `paths` | 19 | Path data and complex paths | 90% |
| `text` | 20 | Text rendering and fonts | 80% |
| `masking` | 14 | Masks and clip-paths | 75% |
| `painting` | 25 | Fill, stroke, markers | 85% |
| `filters` | 15 | Filter effects | 50% |

## Manual Usage

### 1. Generate Metadata

```bash
python tests/corpus/add_w3c_corpus.py \
  --category pservers-grad \
  --limit 25 \
  --output tests/corpus/w3c/w3c_gradients_metadata.json
```

### 2. Run Corpus Test

```bash
python tests/corpus/run_corpus.py \
  --corpus-dir tests/corpus/w3c \
  --metadata tests/corpus/w3c/w3c_gradients_metadata.json \
  --output-dir tests/corpus/w3c/output_gradients \
  --report tests/corpus/w3c/report_gradients.json \
  --mode resvg
```

### 3. View Results

```bash
cat tests/corpus/w3c/report_gradients.json
```

## Test Categories Reference

### Gradients (`pservers-grad`)
- Linear and radial gradients
- Gradient transforms
- `objectBoundingBox` vs `userSpaceOnUse`
- Gradient stops and colors
- Expected: 80% native, 15% EMF, 5% raster

### Shapes (`shapes`)
- Basic shapes: rect, circle, ellipse, line, polyline, polygon
- Rounded corners
- Stroke and fill properties
- Expected: 95% native, 5% EMF, 0% raster

### Paths (`paths-data`)
- Complex path data
- Bezier curves (cubic and quadratic)
- Arc commands
- Path transforms
- Expected: 90% native, 10% EMF, 0% raster

### Text (`text`)
- Text positioning and alignment
- Font properties (family, size, weight, style)
- Text transforms
- Text on path (`textPath`) - usually EMF fallback
- Expected: 80% native, 15% EMF, 5% raster

### Masking (`masking`)
- Mask elements
- Clip-path elements
- Mask/clip-path with transforms
- Expected: 75% native, 20% EMF, 5% raster

### Painting (`painting`)
- Fill and fill-rule (evenodd, nonzero)
- Stroke properties (width, dasharray, linecap, linejoin)
- Markers (start, mid, end) - often EMF fallback
- Expected: 85% native, 10% EMF, 5% raster

### Filters (`filters`)
- Filter primitives (blur, composite, blend, etc.)
- Filter regions and transforms
- Most filters require EMF/raster fallback
- Expected: 50% native, 40% EMF, 10% raster

## Interpreting Results

### Success Metrics

A test passes if:
- Native rate ≥ expected rate (category-specific)
- EMF rate ≤ maximum threshold
- Raster rate ≤ 5%
- No conversion errors

### Common Issues

**"Failed to convert <element>: name 'chain' is not defined"**
- Non-blocking error in gradient/paint chain resolution
- Tests still complete successfully
- To be fixed in future update

**High EMF rates**
- Expected for complex features (markers, filters, textPath)
- Indicates fallback to EMF vector rendering
- Better than raster fallback

**High raster rates**
- Indicates features not supported in native DrawingML or EMF
- May impact visual quality
- Review which features trigger raster fallback

## Output Structure

```
tests/corpus/w3c/
├── README.md                         # This file
├── w3c_gradients_metadata.json       # Generated metadata
├── report_gradients.json             # Test report
└── output_gradients/                 # Generated PPTX files
    ├── pservers-grad-01-b_resvg.pptx
    ├── pservers-grad-02-b_resvg.pptx
    └── ...
```

## CI Integration

Add to `.github/workflows/corpus.yml`:

```yaml
name: W3C Corpus Testing

on: [push, pull_request]

jobs:
  w3c-corpus:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install dependencies
        run: pip install -e .

      - name: Run W3C corpus tests
        run: |
          ./tests/corpus/run_w3c_corpus.sh gradients --mode resvg
          ./tests/corpus/run_w3c_corpus.sh shapes --mode resvg

      - name: Upload reports
        uses: actions/upload-artifact@v3
        with:
          name: w3c-reports
          path: tests/corpus/w3c/report_*.json
```

## Adding More Categories

To add a new category to the convenience script:

1. Edit `tests/corpus/run_w3c_corpus.sh`
2. Add a new case to the switch statement:

```bash
mycategory)
    run_category "my-prefix" "mycategory" 20 "$@"
    ;;
```

3. Update `tests/corpus/add_w3c_corpus.py` with category info:

```python
category_info = {
    # ...
    "my-prefix": {
        "features": ["feature1", "feature2"],
        "expected_native_rate": 0.85,
        "expected_emf_rate": 0.10,
        "expected_raster_rate": 0.05,
        "complexity": "medium",
    },
}
```

## License

W3C SVG Test Suite files are licensed under the [W3C Test Suite License](https://www.w3.org/Consortium/Legal/2008/04-testsuite-license).

## References

- [W3C SVG Test Suite](https://www.w3.org/Graphics/SVG/Test/)
- [SVG 1.1 Specification](https://www.w3.org/TR/SVG11/)
- [Corpus Testing README](../README.md)
