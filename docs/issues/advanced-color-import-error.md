# AdvancedColor Import Error Blocking API Tests

**Status**: Resolved
**Priority**: High (historical)
**Created**: 2025-11-03
**Component**: color.advanced module initialization

## Problem

This issue was reported when `AdvancedColor` was missing from the
`svg2ooxml.color.advanced` exports. The current package now defines
`AdvancedColor` and exports it directly, so the import is no longer blocked.

```python
ImportError: cannot import name 'AdvancedColor' from 'svg2ooxml.color.advanced'
```

## Impact

- **Unblocked**: End-to-end API integration tests can import the API layer
- **Affected**: `tests/integration/test_webfont_embedding_e2e.py` (previously)

## Root Cause

The auto-generated advanced color package previously omitted the
`AdvancedColor` alias from its public exports. The current
`src/svg2ooxml/color/advanced/__init__.py` now defines `AdvancedColor`
explicitly (with an optional-engine fallback) and includes it in `__all__`.

## Current Test Status

✅ **Working**:
- Unit tests: 60/60 passing
  - FontLoader: 29 tests
  - WebFontProvider: 23 tests
  - Service-layer integration: 8 tests

✅ **Unblocked**:
- Full E2E PPTX embedding tests (requires API layer)

## Resolution

- `AdvancedColor` is defined in `src/svg2ooxml/color/advanced/__init__.py` with
  a fallback class when the optional engine is unavailable.
- `__all__` now includes `AdvancedColor`, and unit coverage in
  `tests/unit/color/test_advanced_exports.py` guards the export.

## Verification

After verifying the exports, run:

```bash
PYTHONPATH=src python3 -c "from svg2ooxml.color.advanced import AdvancedColor; print('OK')"
PYTHONPATH=src python3 -m pytest tests/integration/test_webfont_embedding_e2e.py -v
```

## Related Files

- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/color/advanced/__init__.py`
- `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/api/services/converter.py`
- `/Users/ynse/projects/svg2ooxml/tests/integration/test_webfont_embedding_e2e.py`

## Notes

- Web font functionality is fully tested at the service layer.
- Keep the export guard tests so future `rebuild_inits.py` runs do not regress.
