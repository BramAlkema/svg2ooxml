## Resvg vs. Legacy Pipeline Overlap

The current codebase is running two partially independent render pipelines side by side:

| Concern | Legacy path (svg2pptx era) | Resvg/usvg path | Bridging today | Duplication impact |
| --- | --- | --- | --- | --- |
| **Parsing & tree normalisation** | `parser.*`, `render/normalize.py` build `NormalizedSvgTree` with custom CSS cascade, geometry extraction, paint parsing | `core/resvg/parser/*`, `core/resvg/usvg_tree.py` build a usvg-compatible tree with full inheritance/unit resolution | `IRConverter._build_resvg_lookup` computes a map from DOM nodes → resvg nodes | Every node is visited twice; discrepancies between cascades (e.g. inheritance, `use` expansion) are possible |
| **Geometry** | `geometry/paths/parser.py`, `ShapeConversionMixin._convert_*` flatten and approximate paths; `render/geometry.py` tessellates for raster fallbacks | `core/resvg/geometry/*` keeps curves exact until tessellation; `geometry/paths/resvg_bridge.py` exposes primitives | Path converter now prefers resvg segments but falls back to legacy parser | We still maintain and test both parsers; policy hooks run post-fallback so path metadata can diverge |
| **Paint & stroke resolution** | `StyleExtractor._resolve_paint/_resolve_stroke` consult services (`gradient_service`, `pattern_service`) and reapply opacity | `core/resvg/painting/paint.py` resolves fills/strokes including inheritance and gradients; `paint/resvg_bridge.py` converts to IR paints | `styles_runtime.extract_style` swaps in resvg paints where a node mapping exists; gradient & pattern services now share resvg descriptors, policy metadata reads descriptor payloads directly, and the fallback ladder is native → EMF → bitmap | Remaining work: promote mesh gradients to native resvg descriptors (drop the temporary DOM clone) and prune the last parser-era helpers once mesh/pattern analysis no longer needs them |
| **Filter definitions** | Parser captures raw `<filter>` elements, stored on services; registry works directly with `etree` nodes | `usvg_tree.Tree.filters` contains typed primitives | `FilterService` now stores resvg `ResolvedFilter` descriptors and only materialises XML when invoking the legacy registry; raster/vector fallbacks run on the resvg descriptors | Legacy DOM copies are eliminated, but we still mirror the svg2pptx filter renderer until its parity is validated |
| **Clip & mask data** | Legacy parser once emitted clip/mask geometry for services | Resvg tree has mask/clip nodes and converter now derives definitions directly | Traversal now relies solely on resvg-derived definitions; parser collectors were removed | Resvg is the single source of truth; remaining cleanup is focused on asset packaging |
| **Policy metadata** | Converters annotate IR elements based on legacy-derived geometry/paints | Resvg descriptors (e.g. filter primitives) now copied into metadata, but decision logic still uses legacy metrics | Partial: filters feed extra data, other domains untouched | Policies risk conflicting signals; we calculate some things twice |

### Observed duplications and risks

1. **CSS/presentation cascade runs twice.** A given node is normalised first by the legacy cascade and then by usvg. Subtle differences (e.g., shorthand expansion, white-space rules) can change fills or transforms depending on which output a downstream subsystem consumes.
2. **Path parsing duplication.** Even when resvg successfully normalises a path, we still keep the legacy parser, tessellators, and policy adapters alive for fallback paths, inflating test surface and maintenance.
3. **Filter registry duplication.** Filter definitions now exist in three forms: raw DOM (`ParseResult.filters`), resvg descriptors, and materialised `etree` copies registered with the service. Strategy decisions still stem from the legacy DOM, so the richer metadata isn’t fully used yet.
4. **Filter services still depend on parser-era registries.** Gradients and patterns now hydrate directly from resvg descriptors, but filters continue to mirror raw DOM alongside the typed resvg tree. Until we collapse the duplicate stores, updates in one registry won’t automatically propagate to the other.
5. **Mask/clip geometry divergence.** Resvg nodes contain transform-aware geometry for masks/clips, but mask processing still uses the legacy extractor. Cached mask assets may therefore disagree with geometry used for policies.

### Sanity checks performed

- Verified resvg bridges are now hit for anonymous nodes and `<use>` expansions by injecting signature-based matching and propagating `use_source` through the resvg tree.
- Confirmed filter resolution receives IR bounding boxes and resvg primitive metadata, and that metadata is written back onto IR elements.
- Smoke-tested style extraction to ensure both gradient references and solid fills produced by resvg replace the legacy style results without losing policy metadata.

### Recommendations to converge

1. **Define a single source of truth per concern.** Decide whether paints/paths/filters should originate from resvg by default. Once flipped, remove the legacy equivalent modules to avoid drift.
2. **Wire resvg outputs directly into services.** Replace gradient/pattern/filter service registries with adapters over the resvg tree so policy hooks always see the same data the renderer will use.
3. **Retire `render/normalize.py`.** As soon as clips/masks consume resvg geometry, delete the legacy normaliser and associated helper modules; keep only thin compatibility wrappers for any code still expecting its API.
4. **Update policies & tests to consume new metadata.** The filter policy should read the resvg descriptor we now attach; geometry/paint policies need similar updates once their data originates from resvg.
5. **Add regression checks.** Consider fixtures that compare legacy vs resvg outputs for a sample SVG set; this will make it safe to remove redundant code without surprises.

Tracking these TODOs in a dedicated migration ticket (or extending ADR-012) will help keep the team aligned as we collapse the dual architecture. A follow-up PR can start by removing the legacy path parser once resvg coverage is proven end-to-end.
