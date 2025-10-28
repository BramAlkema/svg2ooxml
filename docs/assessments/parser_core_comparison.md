# Parser Core Comparison (svg2pptx vs svg2ooxml)

Date: 2025-XX-XX
Owners: svg2ooxml migration team

## Overview

This document captures the current gap between the production parser in `svg2pptx`
and the new modular parser under `src/svg2ooxml/parser`. It provides the critical
assessment requested before we continue porting additional functionality.

## Feature Matrix

| Concern | svg2pptx Implementation | svg2ooxml Status | Notes / Gaps |
|---------|------------------------|------------------|--------------|
| XML parsing & error recovery | `SplitXMLParser` with recover mode, statistics, validation | `dom_loader.XMLParser` mirrors config & stats | Parity achieved |
| Safe iteration helpers | `core/parser/xml_utils.py` | Formerly in `legacy/parser/xml/safe_iter.py`; now part of core parser | Used by normalization |
| Normalization | `SafeSVGNormalizer` (namespace rebuild, attribute fixes, whitespace, structural pruning, encoding fixes, logging) | Ported version covers namespaces, attribute defaults, whitespace, comment filtering, basic pruning | Encoding fixes and logging fidelity still missing |
| Style context & unit conversion | `StyleContextBuilder` + unit converter + CSS style resolver (`StyleResolver`) | Viewport + `ConversionContext` created, CSS resolver not yet wired | Text styling, em/% units, inheritance pending |
| Clip/mask reference collection | `ClipPathExtractor` plus `_collect_*` helpers | `reference_collector.collect_references` gathers clip/mask/symbol/gradient/pattern/filter | Needs clip child processing, tie into IR converter |
| Hyperlink processing | `SplitHyperlinkProcessor` | Partially ported (`HyperlinkProcessor` attaches navigation metadata, including inline/group `data-*` attributes) | Remaining to wire into policy-driven fallbacks |
| IR conversion | `SplitIRConverter`, `PathSegmentConverter`, coordinate space | Not ported (placeholder only) | Major blocker for pipeline |
| Service integration | Conversion services mutate parser (filter/gradient/image) | Not yet integrated | Later via ADR-policy-map |
| Statistics & result payload | `ParseResult` includes counts, references, normalization data | Same shape plus new reference dictionaries | Need to add elapsed time/logging |
| Tests | Extensive regression & integration suites | Unit tests covering modules | Regression fixtures pending once mapper lands |

## Immediate Observations

1. **CSS & Style Resolver** – The tinycss2-backed resolver is now wired in
   svg2ooxml. We still need broader property coverage (shorthands, font
   fallbacks) and integration tests comparing outputs with svg2pptx.
2. **Clip/Masks Geometry** – Reference collection now generates clip path geometry
   via the clip extractor, exposing bounding boxes and segments to downstream
   code.
3. **Normalization Depth** – Encoding fixes, change logging, and container
   heuristics now exist, but we still need to audit svg2pptx for any remaining
   structural edge cases (e.g., image/link sanitizers) before declaring parity.
4. **Reference Enrichment** – Clip references should eventually run through the
   ported `SplitClipExtractor` / `PathSegmentConverter` so path data is available
   for the mapper. Current collection only captures raw XML elements.
5. **Service Wiring** – Without filter/gradient/image services registered the
   parser remains isolated. ADR-policy-map must be executed before mapping tests.

## Recommended Next Steps

1. Expand CSS resolver coverage (shorthands, font fallbacks) and add regression
   comparisons with svg2pptx.
2. Review the legacy normalization routines for encoding/logging heuristics and
   migrate missing pieces.
3. Flesh out fractional EMU precision tracking and advanced transform/path helpers
   (the current stubs cover the minimum to feed ReferenceCollector).
4. Once services/mappers are ported, verify parser-to-service wiring with full
   conversion tests.
5. Plan the migration of `SplitClipExtractor`, `SplitIRConverter`, and path
   segment helpers as part of the geometry/IR ADR.
6. Execute ADR-policy-map to introduce service setup before the mapper port.
7. Once the above is complete, run sample SVGs through both implementations and
   diff outputs to confirm fidelity.

## Public API Surface (2025-XX-XX)

- `svg2pptx` exposed only `SVGParser`, `ParseResult`, and `SVGNormalizer`
  through `core/parse/__init__.py`. The svg2ooxml initializer now re-exports a
  broader set of helpers (normalizer configuration, reference collectors,
  geometry utilities) to ease incremental testing while placeholders remain.
- Lazy exports (PEP 562) keep import times low while still allowing targeted
  module access for the remaining shim layers. Legacy helpers such as
  `parser.clip_paths` have now been removed; callers should transition to the
  resvg-backed data exposed during conversion.
- We retained `parse_color` as a compatibility shim for existing tests; the
  legacy parser sourced color parsing indirectly, so we can reevaluate the
  public surface once the port stabilizes.

## ADR Updates

Append the observations above to `docs/adr/ADR-parser-core.md` so future work is
anchored to this assessment.
