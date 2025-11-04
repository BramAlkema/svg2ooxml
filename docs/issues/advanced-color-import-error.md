# AdvancedColor Import Error Blocking API Tests

**Status**: Blocking
**Priority**: High
**Created**: 2025-11-03
**Component**: color.advanced module initialization

## Problem

The `svg2ooxml.api.services.converter` module cannot be imported due to a missing `AdvancedColor` symbol in the `svg2ooxml.color.advanced` package.

```python
ImportError: cannot import name 'AdvancedColor' from 'svg2ooxml.color.advanced'
```

## Impact

- **Blocks**: End-to-end API integration tests
- **Affected**: `tests/integration/test_webfont_embedding_e2e.py`
- **Workaround**: Use service-layer integration tests instead

## Root Cause

The `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/color/advanced/__init__.py` file uses lazy imports (PEP 562) and doesn't export `AdvancedColor` in its `__all__` list.

Current `__all__` includes:
- `Color`
- `ColorAccessibility`
- `ColorBatch`
- etc.

But **NOT** `AdvancedColor`.

## Current Test Status

✅ **Working**:
- Unit tests: 60/60 passing
  - FontLoader: 29 tests
  - WebFontProvider: 23 tests
  - Service-layer integration: 8 tests

❌ **Blocked**:
- Full E2E PPTX embedding tests (requires API layer)

## Solution Options

### Option 1: Add AdvancedColor to __all__ (Recommended)

Update `src/svg2ooxml/color/advanced/__init__.py`:

```python
__all__ = [
    'AdvancedColor',  # ADD THIS
    'BlendMode',
    'Color',
    # ... rest
]

_symbol_map = {
    'AdvancedColor': 'core',  # ADD THIS - map to correct module
    'ColorAccessibility': 'accessibility',
    # ... rest
}
```

### Option 2: Fix the import in converter

Update the import statement in `src/svg2ooxml/api/services/converter.py` to import from the specific submodule instead of the package.

### Option 3: Skip API tests temporarily

Continue using service-layer integration tests until the color module is fixed.

## Verification

After fix, verify with:

```bash
python -c "from svg2ooxml.color.advanced import AdvancedColor; print('OK')"
python -m pytest tests/integration/test_webfont_embedding_e2e.py -v
```

## Related Files

- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/color/advanced/__init__.py`
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/api/services/converter.py`
- `/Users/ynse/projects/svg2ooxml/tests/integration/test_webfont_embedding_e2e.py`

## Notes

- This is a **pre-existing issue** not related to web font implementation
- Web font functionality is fully tested at the service layer
- The issue only affects the API wrapper layer
