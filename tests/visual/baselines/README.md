# Visual Test Baselines

This directory contains baseline images for visual regression testing.

## Directory Structure

```
baselines/
├── resvg/                    # Resvg integration feature baselines
│   ├── blend_modes/
│   │   └── slide_1.png
│   ├── linear_gradients/
│   │   └── slide_1.png
│   ├── radial_gradients/
│   │   └── slide_1.png
│   ├── text_rendering/
│   │   └── slide_1.png
│   └── composite_filters/
│       └── slide_1.png
└── README.md                 # This file
```

## Generating Baselines

Baselines must be generated using LibreOffice to render PPTX files to PNG images.

### Prerequisites

1. Install LibreOffice:
   ```bash
   # macOS
   brew install --cask libreoffice
   
   # Ubuntu/Debian
   sudo apt-get install libreoffice
   ```

2. Install visual testing dependencies:
   ```bash
   pip install svg2ooxml[visual-testing]
   ```

3. Verify `soffice` is available:
   ```bash
   which soffice
   ```

### Regenerating Baselines

To regenerate baselines for the resvg test suite:

```bash
python tools/visual/update_baselines.py --suite resvg
```

**⚠️ Important**: Only regenerate baselines when:
- Adding new visual test fixtures
- Intentionally changing rendering behavior (with review)
- Fixing known visual bugs

### Version Control

Baselines are tracked in git to enable regression detection. When baselines change:

1. Review the visual differences carefully
2. Document why the change is expected in the commit message
3. Get peer review before merging

## Running Visual Tests

Run visual regression tests:

```bash
# Run all visual tests
pytest tests/visual/test_resvg_visual.py -v

# Run specific test class
pytest tests/visual/test_resvg_visual.py::TestBlendModes -v

# Skip if LibreOffice not available (tests auto-skip)
pytest tests/visual/ -v -m visual
```

### Test Thresholds

Different features use different SSIM thresholds for tolerance:

- **Blend modes**: 0.95 (strict)
- **Linear gradients**: 0.95 (strict)
- **Radial gradients**: 0.92 (tolerant - DrawingML limitations)
- **Text rendering**: 0.93 (tolerant - font rendering variations)
- **Composite filters**: 0.95 (strict)

### Interpreting Failures

When a visual test fails:

1. Check the diff image in `tmp_path/diff/{fixture}_diff.png`
2. Red overlay indicates regions with SSIM < 0.95
3. Review SSIM score and pixel diff percentage in test output
4. Determine if failure is expected (new feature) or regression (bug)

## Continuous Integration

Visual tests run automatically in CI when:
- Pull requests are opened
- Changes affect rendering code
- `@pytest.mark.visual` tests are modified

CI will fail if SSIM score falls below the threshold for any fixture.

## Troubleshooting

### "LibreOffice not available"
- Install LibreOffice and ensure `soffice` is on PATH
- Tests auto-skip if LibreOffice is not found

### "Baseline images missing"
- Run `python tools/visual/update_baselines.py --suite resvg`
- Baselines are not auto-generated to prevent accidental overwrites

### "SSIM score too low"
- Review diff image to understand what changed
- Check if rendering code was modified
- Verify baseline is from correct version
- Consider if threshold adjustment is needed (with justification)

## References

- Visual differ implementation: `tools/visual/diff.py`
- Test fixtures: `tests/visual/fixtures/resvg/`
- Test suite: `tests/visual/test_resvg_visual.py`
- Baseline update tool: `tools/visual/update_baselines.py`
