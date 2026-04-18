# __init__ Recovery Checklist

Date: 2025-XX-XX  
Owners: svg2ooxml migration team

## Background

The prior cleanup script cleared many package-level `__init__.py` files across
`src/svg2ooxml/`. Critical parser- and services-facing modules were restored
manually, but a wide set of ancillary packages (geometry, policy, map, IR,
etc.) still contain placeholder initializers, leaving their public exports
undefined. Before porting additional functionality we need a systematic plan to
rebuild these initializers so imports remain stable while we migrate code from
`svg2pptx`.

## Audit Summary

Running `rg "Placeholder module." src/svg2ooxml` highlights packages with empty
exports. Key areas still pending:

- `core/`, `pipeline/`, and subpackages (`pipeline/stages`, `pipeline/policies`)
- `geometry/` (root, `paths/`, `fractional/`, `algorithms/`, `clip/`)
- `ir/` and `elements/`
- `map/`
- `policy/` and `services/registry/`
- `paint/` (`fills/`, `strokes/`) and `color/palettes/`
- `api/`, `presentation/`, `batch/`, `multipage/`, `performance/`
- `transforms/`, `units/`, `viewbox/`, `text/`, `filters/`, `clip/`

These align with the outstanding porting work referenced in
`docs/adr/ADR-geometry-ir.md` and `docs/adr/ADR-policy-map.md`.

## Recovery Plan

1. **Rebuild initializers automatically.** Use `tools/rebuild_inits.py` to
   regenerate `__init__.py` files. Start with dry-run mode to inspect diffs:

   ```bash
   python tools/rebuild_inits.py --root src/svg2ooxml --dry-run
   ```

   When satisfied, run without `--dry-run` to write files. Backups are created
   as `__init__.py.bak` for manual review.

2. **Annotate placeholders with ADR TODOs.** As exports become concrete, add
   targeted TODO comments referencing the relevant ADR (e.g.,
   `TODO(ADR-geometry-ir)`) to guide ongoing porting.

3. **Restore curated exports.** For packages with deliberate public APIs (like
   `services`, `parser`, `geometry.paths`), compare regenerated exports with
   the legacy definitions in `svg2pptx` to ensure parity before deleting the
   backup files.

4. **Add regression tests.** Introduce smoke tests that import the rebuilt
   packages to guard against accidental wipes (`tests/unit/imports/test_packages.py`).

5. **Track progress.** Update this checklist and the component map
   (`docs/svg2pptx_component_map.md`) as packages regain stable initializers.

## Immediate Next Steps

- Run the rebuild script in dry-run mode and review the generated exports for
  `core`, `geometry`, `ir`, `map`, and `policy`.
- Confirm no namespace packages were intentionally left without an initializer.
- Schedule follow-up to replace placeholder docstrings with module-level
  guidance once exports are finalized.

