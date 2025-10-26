<|file_separator|># ADR: Parser & Batch Integration Port

- **Status:** In Progress
- **Date:** 2025-03-29
- **Owners:** svg2ooxml migration team
- **Depends on:** ADR-parser-core, ADR-policy-map, ADR-geometry-ir
- **Blocks:** ADR-huey-batch, ADR-end-to-end

## Context

The svg2pptx parser is more than a DOM loader: it normalizes SVG, injects services, and hands the result to `SplitIRConverter`, while the batch/Huey preprocessors wrap the parser so jobs flowing through the queue produce IR+service bundles ready for the mapper. The current svg2ooxml tree only exposes a simplified parser (`parser/svg_parser.py`) with placeholder wiring and no batch entry point, leaving large parts of the original surface area (path segment converters, traversal helpers, hyperlink metadata, preprocessing payloads, Huey job orchestration) unported.

We need the parser to be a faithful drop-in for the original clean-slate preprocessors so we can run e2e integration tests (CLI/API/Huey). That requires:

- Porting the split parser helpers (`core/parse_split/*`) and aligning them with our new IR stack (`map/converter/*`).
- Mirroring the preprocessor contracts used by the batch pipeline (`core/batch/*`, job payload schemas, Huey tasks).
- Ensuring services (filters, gradients, patterns, images) are injected identically so parser outputs can flow directly into the mapper and downstream batch steps.
- Providing tests at unit and integration levels so the parser can be exercised without Huey, plus optional Huey-enabled test fixtures.

## Decision

1. **Finalize parser package layout**

   ```
   src/svg2ooxml/parser/
       core/
           svg_parser.py          # Public parser façade mirroring svg2pptx SVGParser
           normalization.py       # Safe normalization helpers
           validator.py           # Structural validation
           path_segments.py       # Ported PathSegmentConverter + utilities
       split/
           element_traversal.py
           hyperlinks.py
           style_context.py
           xml_parser.py
           constants.py
           clip_parser.py
           __init__.py            # Re-exports for core.svg_parser
       preprocess/
           payload.py             # Job payload / metadata DTOs
           result_builder.py      # Glue between parser result and IR converter
           services.py            # Parser-facing service bootstrap (wraps services.setup)
       batch/
           huey_app.py            # SqliteHuey configuration
           tasks.py               # Parser-driven Huey tasks
           coordinator.py         # Task orchestration helpers
           worker.py              # CLI worker entrypoint
   ```

   - `parser/core/svg_parser.py` owns orchestration: DOM normalization, validation, collecting references, delegating to the IR converter (`map.ir_converter`) and exposing a `ParseResult` equivalent to the svg2pptx struct.
   - `parser/split/*` houses direct ports from `core/parse_split`, keeping filenames small by splitting large modules (e.g., break legacy `ir_converter.py` into traversal + hyperlink + style context modules; actual IR conversion logic now lives in `map/converter/core.py`).
   - `parser/preprocess` captures the “parser hooks” Huey and API code expect: request DTOs, wrapper functions returning parser + IR outputs, and service bootstrapping (including clip/gradient/pattern dictionaries required by downstream steps).

2. **Align parser services/contracts**

   - `parser/preprocess/services.py` creates a canonical function `build_parser_services()` that returns `(ConversionServices, ParserHooks)`; it wraps `services.configure_services()` and plugs in processors (gradient/pattern/image) ported from svg2pptx `core/elements`.
   - `parser/core/svg_parser.SVGParser` accepts a `ConversionServices` instance (defaulting to `build_parser_services()`), stores it on the parse result, and registers clip/gradient/pattern/filter dictionaries exactly as svg2pptx did.
   - Parser result dataclass includes: `svg_root`, `statistics`, `references` (clip/mask/symbol/etc.), `services`, `style_context`, `ir_scene` (optional, depending on whether the caller wants IR conversion immediately).

3. **Huey/batch integration**

   - Port `core/batch/huey_app.py`, `tasks.py`, and `coordinator.py` into `parser/batch/` with minimal changes, replacing svg2pptx imports with svg2ooxml equivalents.
   - Provide a lightweight dependency flag so the rest of the library works without Huey installed; fall back to “simple mode” for direct parser usage.
   - Expose a public helper `svg2ooxml.parser.batch.enqueue_conversion_job()` replicating the svg2pptx API so existing entry points can be ported with find/replace.

4. **Testing strategy**

   - `tests/unit/parser/core/` covers normalization, validator, path segments, reference collection, and parser façade behaviours.
   - `tests/integration/parser/` exercises end-to-end parse → IR conversion (without Huey).
   - `tests/integration/batch/` gated by `requires_huey` marker spins up SqliteHuey, enqueues a job, and asserts parser outputs are persisted (mirrors svg2pptx tests).
   - Provide fixtures for sample SVGs and expected IR JSON to keep regression coverage high.

5. **Documentation & fixtures**

   - Update `docs/structure.md` and `docs/adr/ADR-parser-core.md` to reference the new packages.
   - Document developer workflow in `docs/guides/batch-processing.md` (svg2ooxml version) describing how to run Huey worker, enqueue jobs, and inspect outputs.

## Consequences

- **Pros**
  - Parser becomes a drop-in replacement for svg2pptx’s preprocessor layer, enabling full fidelity testing and regression comparisons.
  - Batch/Huey surfaces are ready for pipeline integration once mapping and PPTX writers land.
  - Clear package boundaries allow selective testing (unit vs integration vs Huey), improving stability for contributors without Huey installed.

- **Cons**
  - Porting introduces many modules at once; ensuring parity requires careful reviews and incremental testing.
  - Huey remains an optional dependency; we must guard imports and tests to avoid breaking environments without it.
  - Maintaining both parser and mapping stacks in parallel increases initial complexity until the full pipeline is ported.

## Migration Plan

1. ✅ Mirror `core/parse_split` modules under `parser/split/`, trimming dead code and injecting svg2ooxml imports.
2. ✅ Port `core/parse/path_segments.py` and supporting geometry utilities into `parser/core/path_segments.py`; update unit tests.
3. ✅ Expand `parser/core/svg_parser.py` using svg2pptx logic, delegating IR conversion to `map.convert_parser_output`.
4. ✅ Import and adapt `core/batch/*` modules into `parser/batch/`, wiring them to the new parser/preprocessor services (Huey optional via in-memory backend).
5. ✅ Implement `parser/preprocess/services.py` and job payload helpers; update parser result structure.

## Status Notes

- Mapper/writer integration: batch outputs currently produce IR + media metadata; swapping to full PPTX packaging is scheduled alongside the exporter ADR.
- Gradient/pattern/image processors are already wired via `configure_services`; no further action required here.
- Documentation: `docs/guides/batch_processing.md` covers Huey and inline execution; keep it in sync as CLI options evolve.
- Blob persistence for embedded media now flows through the PPTX packager; revisit larger asset lifecycle questions once exporter parity is complete.
- Open TODO: add Huey-enabled regression coverage after queue runners are ported (track in BATCH-9).
