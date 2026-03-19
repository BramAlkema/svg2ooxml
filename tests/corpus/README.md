# SVG2OOXML Corpus Testing

Corpus testing infrastructure for comprehensive evaluation of SVG→PPTX conversion quality using real-world SVG files from design tools like Figma, Sketch, and Adobe Illustrator.

## Overview

The corpus testing system:
- Processes collections of real-world SVG files through the conversion pipeline
- Collects detailed metrics on rendering decisions (native/EMF/raster rates)
- Measures visual fidelity using SSIM (Structural Similarity Index)
- Generates comprehensive reports comparing against quality targets
- Supports both legacy and resvg rendering modes

## Directory Structure

```
tests/corpus/
├── README.md                    # This file
├── run_corpus.py                # Main corpus test runner
├── real_world/                  # Real-world SVG corpus
│   ├── corpus_metadata.json     # Metadata and expected metrics
│   ├── *.svg                    # Source SVG files
│   └── baselines/               # Baseline images for visual comparison
│       └── {deck_name}/
│           └── slide_1.png
├── output/                      # Generated PPTX files and renders
│   └── {deck_name}_{mode}.pptx
└── corpus_report.json           # Latest test report
```

## W3C SVG Test Suite Integration

The repository includes 447 non-animation tests from the W3C SVG 1.1 Test Suite! See [W3C Corpus Documentation](w3c/README.md) for details.

**Quick start**:
```bash
# Run W3C gradient tests
./tests/corpus/run_w3c_corpus.sh gradients

# Run all W3C test categories
./tests/corpus/run_w3c_corpus.sh all
```

## Quick Start

### 1. Install Dependencies

```bash
# Visual testing dependencies (optional, for SSIM metrics)
pip install svg2ooxml[visual-testing]

# LibreOffice (required for visual fidelity checks)
# macOS: brew install --cask libreoffice
# Ubuntu: sudo apt-get install libreoffice
```

### 2. Run Corpus Tests

```bash
# Run with resvg mode (default)
python tests/corpus/run_corpus.py

# Run with legacy mode
python tests/corpus/run_corpus.py --mode legacy

# Specify custom paths
python tests/corpus/run_corpus.py \
  --corpus-dir tests/corpus/real_world \
  --output-dir tests/corpus/output \
  --report tests/corpus/corpus_report.json

# Metrics-only run (skip writing PPTX files)
python tests/corpus/run_corpus.py --skip-pptx
# Note: --skip-pptx disables OpenXML audit and visual checks.

# Deterministic sampling (run a stable subset)
python tests/corpus/run_corpus.py --sample-size 50 --sample-seed 1234
```

### 3. View Results

```bash
# Check exit code
echo $?  # 0 if all targets met, 1 otherwise

# View report
cat tests/corpus/corpus_report.json
```

## OpenXML Audit

If you have an OpenXML validator CLI available, you can run the OpenXML audit
alongside the corpus run:

```bash
OPENXML_VALIDATOR=openxml-audit python tests/corpus/run_corpus.py --openxml-audit
```

Install the maintained validator from PyPI and point `OPENXML_VALIDATOR` at the
CLI name:

```bash
python -m pip install openxml-audit
OPENXML_VALIDATOR=openxml-audit python tests/corpus/run_corpus.py --openxml-audit
```

To enforce audit gating in CI, require the audit to run and set a minimum pass
rate:

```bash
OPENXML_VALIDATOR=openxml-audit \
  python tests/corpus/run_corpus.py \
    --openxml-audit \
    --openxml-required \
    --openxml-min-pass-rate 0.98
```

To run the same W3C animation gate profiles locally (required profiles or full
animation profile), use:

```bash
# required profiles (gradients + shapes + animation sample 20/40)
tools/run_w3c_animation_gate_local.sh required

# full animation profile (40/40)
tools/run_w3c_animation_gate_local.sh full

# both
tools/run_w3c_animation_gate_local.sh all
```

## Corpus Metadata Schema

The `corpus_metadata.json` file defines the test corpus structure:

```json
{
  "decks": [
    {
      "deck_name": "figma_design_system_sample",
      "source": "Figma",
      "svg_file": "figma_design_system_sample.svg",
      "description": "Sample design system components",
      "expected_native_rate": 0.85,
      "expected_emf_rate": 0.10,
      "expected_raster_rate": 0.05,
      "features": ["linear_gradients", "text", "basic_shapes"],
      "complexity": "medium",
      "created_date": "2025-01-04",
      "license": "MIT / CC-BY / Sample"
    }
  ],
  "targets": {
    "native_rate": 0.80,
    "emf_rate_max": 0.15,
    "raster_rate_max": 0.05,
    "visual_fidelity_min": 0.90
  },
  "sample": {
    "size": 50,
    "seed": 1234
  }
}
```

### Required Fields

- `deck_name`: Unique identifier for the test deck
- `source`: Tool that exported the SVG (Figma, Sketch, Illustrator, etc.)
- `svg_file`: Filename of the SVG file (relative to corpus directory)

### Optional Fields

- `description`: Human-readable description of the test case
- `expected_native_rate`: Expected percentage of native rendering (0.0-1.0)
- `expected_emf_rate`: Expected percentage of EMF fallback (0.0-1.0)
- `expected_raster_rate`: Expected percentage of raster fallback (0.0-1.0)
- `features`: List of SVG features used (for filtering/analysis)
- `complexity`: Complexity level (low, medium, high)
- `created_date`: When the test case was added (YYYY-MM-DD)
- `license`: License information for the source file
- `notes`: Additional notes about the test case

### Optional Top-Level Fields

- `sample`: Default deterministic sampling configuration (`size`, `seed`).

## Adding New Corpus Files

### 1. Obtain Real-World SVG

Export an SVG from a design tool:
- **Figma**: File → Export → SVG
- **Sketch**: Export → SVG
- **Illustrator**: File → Export → Export As → SVG

Ensure you have permission to use the file for testing.

### 2. Add SVG to Corpus

```bash
# Copy SVG file
cp ~/Downloads/my_design.svg tests/corpus/real_world/

# Give it a descriptive name
mv tests/corpus/real_world/my_design.svg \
   tests/corpus/real_world/figma_dashboard_mockup.svg
```

### 3. Update Metadata

Edit `tests/corpus/real_world/corpus_metadata.json` and add an entry:

```json
{
  "deck_name": "figma_dashboard_mockup",
  "source": "Figma",
  "svg_file": "figma_dashboard_mockup.svg",
  "description": "Dashboard mockup with charts and data visualization",
  "features": ["linear_gradients", "radial_gradients", "masks", "text"],
  "complexity": "high",
  "created_date": "2025-01-04",
  "license": "Internal use only"
}
```

### 4. Generate Baseline (Optional)

If you want visual fidelity tracking:

```bash
# Run corpus test to generate PPTX
python tests/corpus/run_corpus.py

# Render PPTX to baseline image
mkdir -p tests/corpus/real_world/baselines/figma_dashboard_mockup
soffice --headless --convert-to png \
  --outdir tests/corpus/real_world/baselines/figma_dashboard_mockup \
  tests/corpus/output/figma_dashboard_mockup_resvg.pptx

# Rename to expected filename
mv tests/corpus/real_world/baselines/figma_dashboard_mockup/figma_dashboard_mockup_resvg-1.png \
   tests/corpus/real_world/baselines/figma_dashboard_mockup/slide_1.png
```

## Interpreting Corpus Reports

The corpus runner generates a JSON report with detailed metrics:

```json
{
  "timestamp": "2025-01-04T12:34:56.789Z",
  "mode": "resvg",
  "total_decks": 3,
  "successful_decks": 3,
  "failed_decks": 0,
  "avg_native_rate": 0.85,
  "avg_emf_rate": 0.10,
  "avg_raster_rate": 0.05,
  "avg_ssim_score": 0.95,
  "targets_met": {
    "native_rate": true,
    "emf_rate": true,
    "raster_rate": true,
    "visual_fidelity": true
  },
  "summary": "Corpus test completed: 3/3 decks successful\n..."
}
```

### Key Metrics

**Rendering Rates** (higher native is better):
- `native_rate`: Percentage of elements rendered natively in DrawingML
- `emf_rate`: Percentage requiring EMF fallback (complex features)
- `raster_rate`: Percentage requiring raster fallback (unsupported features)

**Visual Fidelity**:
- `ssim_score`: Structural Similarity Index (0.0-1.0, higher is better)
- `visual_fidelity_passed`: Whether SSIM score meets minimum threshold

**Performance**:
- `conversion_time_ms`: Time to convert SVG to IR and render to DrawingML

### Targets

The report compares metrics against targets defined in `corpus_metadata.json`:

- ✅ **PASS**: Metric meets or exceeds target
- ❌ **FAIL**: Metric does not meet target

Default targets:
- Native rate: ≥80%
- EMF rate: ≤15%
- Raster rate: ≤5%
- Visual fidelity (SSIM): ≥0.90
- OpenXML audit pass rate: optional, enforced via `--openxml-min-pass-rate`

## Troubleshooting

### No visual fidelity metrics

**Symptom**: `ssim_score: null` in report

**Cause**: Missing dependencies or baselines

**Solution**:
```bash
# Install visual testing dependencies
pip install svg2ooxml[visual-testing]

# Generate baselines (see "Generate Baseline" above)
```

### LibreOffice not found

**Symptom**: "LibreOffice not available" warning

**Cause**: `soffice` not in PATH

**Solution**:
```bash
# macOS
brew install --cask libreoffice

# Ubuntu/Debian
sudo apt-get install libreoffice

# Verify installation
which soffice
```

### Telemetry metrics are placeholder values

**Symptom**: All decks report same metrics (100 total, 85 native, etc.)

**Cause**: Telemetry extraction not yet implemented (marked as TODO in code)

**Solution**: This is expected in the current implementation. Actual telemetry extraction will be implemented in a future update.

### Tests fail with import errors

**Symptom**: `ModuleNotFoundError: No module named 'svg2ooxml'`

**Cause**: Running outside virtual environment

**Solution**:
```bash
source .venv/bin/activate
python tests/corpus/run_corpus.py
```

## CI Integration

Corpus testing can be integrated into CI pipelines for continuous quality monitoring:

```yaml
# .github/workflows/corpus.yml
name: Corpus Testing

on: [push, pull_request]

jobs:
  corpus:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Install LibreOffice
        run: sudo apt-get install -y libreoffice

      - name: Install Python dependencies
        run: |
          pip install -e ".[visual-testing]"

      - name: Run corpus tests
        run: |
          python tests/corpus/run_corpus.py --mode resvg

      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: corpus-report
          path: tests/corpus/corpus_report.json
```

## Future Enhancements

- **Automated corpus collection**: Scripts to batch-export from design tools
- **Telemetry extraction**: Real metrics from render results (currently placeholder)
- **Performance benchmarking**: Track conversion time trends over commits
- **Feature coverage tracking**: Ensure corpus covers all SVG features
- **Regression detection**: Alert on metric degradation between commits
- **HTML report generation**: Interactive web-based report viewer

## Related Documentation

- [Visual Regression Testing](../visual/baselines/README.md)
- [Resvg Integration Tasks](../../docs/tasks/resvg-integration-tasks.md)
- [Visual Differ Tool](../visual/differ.py)
