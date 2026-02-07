# ADR-019: EOT-Based Font Embedding Pipeline

- **Status:** Proposed
- **Date:** 2025-11-09
- **Owners:** Font/Presentation Platform
- **Depends on:** ADR-text-fonts-and-wordart, ADR-drawingml-writer-export
- **Replaces:** None

## Context

Recent PowerPoint repairs and Google Slides rejections exposed that our current
"embedded" fonts are raw TTF/OTF streams saved with `.odttf` extensions. That
violates ECMA-376 and PowerPoint's expectations: embedded fonts must be
obfuscated EOT payloads placed under `/ppt/fonts/fontN.fntdata`, registered with
`application/x-fontdata`, and wired through `<p:embeddedFontLst>` with dedicated
relationships. Without those pieces, PowerPoint strips the fonts on open and the
Drive pipeline rejects the package.

SVG inputs can reference fonts in multiple formats (TTF, OTF, WOFF, WOFF2, data
URIs). Our loader already normalises those into OpenType byte streams, but the
final PPTX package still has to present them as EOT `.fntdata` parts because
PresentationML ignores raw OpenType/WOFF payloads. The ADR therefore mandates an
explicit OpenType → EOT conversion step before packaging.

We already have the upstream pieces (FontService discovery, FontEmbeddingEngine
subsetting, PPTXPackageBuilder asset wiring), but we lack a compliant EOT
converter and metadata propagation (GUIDs, relationships, presentation XML
updates). Mozilla's `eottool.py` (BSD/MIT) provides a reference implementation we
can vendor. We must integrate it so our pipeline emits the same artifacts that
PowerPoint generates.

## Decision

Adopt an EOT-based embedding workflow inside svg2ooxml so every embedded font is
subset, converted, and packaged exactly per ECMA-376 / PowerPoint behavior:

1. Continue subsetting fonts via fontTools, respecting `OS/2.fsType` and the
   existing `FontEmbeddingRequest` options.
2. Vendor Mozilla's `eottool` (parser + compressor) under
   `src/svg2ooxml/services/fonts/eot.py` and expose a `ttf_to_eot(bytes) -> bytes`
   helper.
3. Extend `FontEmbeddingEngine` so `subset_font()` returns both the subset bytes
   and the derived EOT bytes + GUID metadata required for packaging.
4. Update `PPTXPackageBuilder._write_font_parts()` to write `.fntdata` files,
   register the `application/x-fontdata` default/overrides in
   `[Content_Types].xml`, add `Relationship Type=".../relationships/font"`
   entries pointing to `ppt/fonts/fontN.fntdata`, and build `<p:embeddedFont>`
   elements (`<p:regular>`, `<p:bold>`, etc.) referencing those rIds.
5. Record the GUID used for each font inside the theme/presentation where the
   spec requires (theme extension or presentation font table) so PowerPoint can
   tie the relationship to the obfuscated bytes.
6. Trace the pipeline (metrics + logging) so we can prove fonts stayed embedded
   through PowerPoint/Drive validation.

## Implementation Script

Follow these concrete steps to land the feature:

1. **Vendor the converter**
   - Copy Mozilla's `eotfile.py` + `eotcompressor.py` into
     `src/svg2ooxml/services/fonts/_vendor/` (keep license header).
   - Wrap them with `eot.py` exposing `build_eot(ttf_bytes, family, style) -> EotResult`.
   - Add unit tests under `tests/unit/services/fonts/test_eot.py` covering
     round-trips and known header bytes.

2. **Extend the embedding engine**
   - In `embedding.py`, introduce an `EmbeddedFontPayload` dataclass containing
     `subset_bytes`, `eot_bytes`, `guid`, `subset_prefix`, `style_flags`.
   - Update `_subset_with_fontforge()` to feed the subset bytes into
     `build_eot()` along with font metadata and capture the GUID from the EOT
     header.
   - Persist the new payload in `FontEmbeddingResult.packaging_metadata` so the
     PPTX writer can access `eot_bytes` and GUID info.

3. **Package `.fntdata` parts**
   - Modify `_write_font_parts()` in `pptx_writer.py` to:
     - Write `fonts/fontN.fntdata` using `eot_bytes`.
     - Generate deterministic filenames (e.g., `font{index}.fntdata`) and trace
       them for debugging.
     - Emit `_PackagedFont` records capturing `relationship_id`, `typeface`,
       style flags, GUID, and part name.

4. **Wire XML + relationships**
   - Ensure `[Content_Types].xml` declares `Extension="fntdata"` with
     `application/x-fontdata` and per-part overrides.
   - Create presentation relationships of type
     `http://schemas.openxmlformats.org/officeDocument/2006/relationships/font`
     pointing to `fonts/fontN.fntdata`.
   - Update `/ppt/presentation.xml` to contain `<p:embeddedFontLst>` with one
     `<p:embeddedFont>` per used typeface; add `<p:regular>`, `<p:bold>`, etc.
     children with the appropriate `r:id`.
   - Store the obfuscation GUID where PowerPoint expects it (theme extension or
     presentation font table) so round-trips keep the fonts.

5. **Validation + tooling**
   - Add integration tests that generate a PPTX with a known custom font, unzip
     it, and assert that `ppt/fonts/*.fntdata` starts with an EOT header and that
     presentation XML contains matching relationships.
   - Document the workflow in `docs/FONT_EMBEDDING_ANALYSIS.md` and add a new
     entry under `docs/FONT_EMBEDDING_EXPLORATION_INDEX.md` pointing to this ADR.
   - Create a manual test script (e.g., `tools/verify_font_embedding.py`) that
     regenerates `tests/struct-use-10-f_new.pptx`, opens it via PowerPoint (manual
     step), and dumps relationship + GUID info for inspection.

## Consequences

### Positive
- Matches PowerPoint/ECMA expectations so embedded fonts survive repairs and are
  accepted by Google Drive/Slides.
- Keeps the entire pipeline Python-native (no external binaries) by vendoring
  the Mozilla converter.
- Builds on existing subsetting + packaging code, so minimal duplication.

### Negative
- Slightly larger binary footprint due to vendored eottool.
- Additional CPU time for EOT conversion during exports.
- Need to maintain GUID bookkeeping between embedding engine and PPTX writer.

## Open Questions
1. Do we need to persist font GUIDs inside the theme or can they live solely in
   presentation.xml for our target apps? (Spec implies theme extension is
   required; confirm via real PPTX samples.)
2. Should we expose policy toggles to skip embedding for restricted fonts and
   fall back to system substitution automatically?
3. How do we cache EOT outputs (by glyph set hash) to avoid redundant work
   across multiple slides referencing the same subset?

## References
- docs/FONT_EMBEDDING_ANALYSIS.md – current pipeline overview.
- docs/FONT_EMBEDDING_EXPLORATION_INDEX.md – research index.
- Mozilla `eottool.py` (Bugzilla attachment 361505) – reference converter.
- ECMA-376 §21.1.7.6 – OOXML font embedding and obfuscation.
- Microsoft docs on `<p:embeddedFontLst>` and font relationships.
