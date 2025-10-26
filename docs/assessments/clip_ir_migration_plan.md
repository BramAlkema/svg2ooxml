# Clip Extractor & IR Converter Migration Plan

Date: 2025-XX-XX
Owners: svg2ooxml migration team

## Scope

This note outlines the steps required to port the clip-path extractor and IR
converter subsystems from svg2pptx into svg2ooxml.

## Legacy Components

- `core/parse_split/clip_parser.py` + `ClipPathExtractor` in `core/parse/parser.py`
- `core/parse/path_segments.py` and `core/paths/path_system.py`
- `core/parse_split/ir_converter.py` and `core/services/conversion_services.py`

## Target Modules

- `parser/reference_collector.py` – enrich with parsed clip geometry
- `geometry/paths/` – expose segment converters and coordinate helpers
- `map/ir_converter.py` – ingest parser references and emit IR scenes
- `services/conversion.py` – resolve dependencies needed during conversion

## Migration Steps

1. Port `SplitClipExtractor` logic into `parser/clip_extractor.py`, returning a
   lightweight data class with parsed path geometry.
2. Port path segment conversion helpers into `geometry/paths/segments.py` and
   expose mappings required by the clip extractor.
3. Rebuild the IR converter in `map/ir_converter.py`, consuming parser references
   and services (font, image, filters) via the new service container.
4. Update `SVGParser` to invoke the clip extractor and store the results within
   `ParserReferences`.
5. Add regression tests comparing clip-path and IR output between svg2pptx and
   svg2ooxml for a curated set of SVG fixtures.

## Dependencies

- Services ADR must be executed (filter/gradient/image providers available).
- Geometry/IR ADR provides the data models consumed by the converter.

## Open Questions

- Decide whether to keep EMF fallback support in the initial port or defer.
- Determine how much of the original logging/metrics to retain during the first pass.
