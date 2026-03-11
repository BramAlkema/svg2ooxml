# Office Profile and svgBlip Extensions Specification

**Status**: Draft
**Created**: 2026-03-11
**Owner**: DrawingML + Packaging
**Priority**: High (Office fidelity and package interoperability)

---

## 1. Overview

`svg2ooxml` currently emits primarily ECMA-style PresentationML/DrawingML. That keeps schema output conservative, but it does not model several Microsoft Office extension behaviors that PowerPoint uses for image rendering fidelity and editability metadata.

This spec defines three deliverables:

1. `office_profile` that gates Office extension emission and MC (`mc:Ignorable`) markup.
2. `svgBlip` image path for SVG images, with PNG fallback packaging.
3. Tests that lock extension contracts (`mc:Ignorable`, `useLocalDpi` / image DPI settings, `svgBlip` package shape).

---

## 2. Problem Statement

Current implementation gaps:

- No first-class Office extension profile switch.
- No `mc` namespace management in slide/presentation roots.
- SVG images are packaged as regular media and referenced via plain `<a:blip>` only.
- No explicit contract tests for Office extension structures.

Representative code locations:

- Slide root template: `assets/pptx_templates/slide_template.xml`
- Picture rendering: `src/svg2office/drawingml/image.py`
- Media registration: `src/svg2office/drawingml/writer.py`
- Package assembly/writing: `src/svg2office/io/pptx_assembly.py`, `src/svg2office/io/pptx_writer.py`
- XML namespace helpers: `src/svg2office/drawingml/xml_builder.py`

---

## 3. Goals and Non-Goals

### 3.1 Goals

- Add a deterministic profile switch for Office extension markup.
- Emit `svgBlip` extension metadata for SVG picture content while preserving fallback rendering.
- Ensure extension prefixes are declared and marked ignorable when required.
- Add test coverage for package structure and XML extension contracts.

### 3.2 Non-Goals

- Full Office extension coverage across all shape/effect domains.
- Changing default behavior for non-Office consumers in this phase.
- Replacing existing EMF/raster fallback architecture.

---

## 4. Configuration Model

### 4.1 New setting: `office_profile`

Introduce profile values:

- `ecma_strict` (default): current behavior, no Office-only extension emission.
- `office_compat`: enable Office extension emission for targeted features in this spec.

### 4.2 Surface area

Plumb `office_profile` through:

- `SvgToPptxExporter(...)`
- `PPTXPackageBuilder(...)`
- `DrawingMLWriter(...)`

Optional environment override:

- `SVG2OOXML_OFFICE_PROFILE=ecma_strict|office_compat`

Optional CLI switch (follow-up, but in scope for spec):

- `--office-profile ecma_strict|office_compat`

### 4.3 Behavioral gate

All Office extension emission MUST be guarded behind `office_profile == "office_compat"`.

---

## 5. XML and Namespace Contract

### 5.1 Namespace additions (when profile is `office_compat`)

Add support for extension namespaces in XML builder/constants:

- `mc`: `http://schemas.openxmlformats.org/markup-compatibility/2006`
- `a14`: `http://schemas.microsoft.com/office/drawing/2010/main`
- `asvg`: `http://schemas.microsoft.com/office/drawing/2016/SVG/main`
- `p14`: `http://schemas.microsoft.com/office/powerpoint/2010/main`

### 5.2 MC ignorable rules

When a part contains extension elements/attributes in one or more extension namespaces, the part root MUST include:

- namespace declarations for those prefixes
- `mc:Ignorable` listing those prefixes

Root-level targets in this phase:

- `p:sld` (`slide*.xml`) for `a14` and `asvg`
- `p:presentation` (and/or `p:presentationPr`/`presProps` as implemented) for `p14` settings

No extension prefixes or `mc:Ignorable` are emitted in `ecma_strict`.

---

## 6. svgBlip Functional Contract

### 6.1 Trigger condition

When rendering `Image` IR with `format == "svg"` and profile is `office_compat`, use the `svgBlip` path.

### 6.2 Package shape

For each SVG picture:

- Package SVG source in `/ppt/media/*.svg`.
- Package PNG fallback in `/ppt/media/*.png`.
- Add two slide relationships:
  - PNG relationship (`rIdPng`) for `<a:blip r:embed="rIdPng">`
  - SVG relationship (`rIdSvg`) for `svgBlip` extension payload

### 6.3 DrawingML shape markup

In `p:pic/p:blipFill/a:blip`:

- Keep base `r:embed` on PNG fallback.
- Add `a:extLst/a:ext` for `svgBlip` child with SVG relationship id.
- Add `a14:useLocalDpi` extension payload according profile/image settings.

Conceptual structure:

```xml
<a:blip r:embed="rIdPng">
  <a:extLst>
    <a:ext uri="{SVG_BLIP_EXT_URI}">
      <asvg:svgBlip r:embed="rIdSvg"/>
    </a:ext>
    <a:ext uri="{USE_LOCAL_DPI_EXT_URI}">
      <a14:useLocalDpi val="0"/>
    </a:ext>
  </a:extLst>
</a:blip>
```

Where `SVG_BLIP_EXT_URI` and `USE_LOCAL_DPI_EXT_URI` are constants sourced from Open Specs and represented as named constants in code.

### 6.4 Data model changes

Extend media asset metadata to model paired fallback/source IDs for SVG picture output.

Recommended shape:

- Keep existing `MediaAsset` for binary payloads.
- Add SVG pair metadata on image/asset context, for example:
  - `svg_fallback_rel_id`
  - `svg_source_rel_id`
  - `svg_source_filename`

Exact struct can be dataclass fields or a typed metadata payload; contract requires deterministic mapping and serialization.

---

## 7. Presentation Image Settings Contract

When `office_profile == "office_compat"`, emit PowerPoint image extension settings:

- `discardImageEditData`
- `defaultImageDpi`

Location and extension container must follow Open Specs for Presentation image extensions (`p14`-namespaced payload under extension list). Implementation can target `presentation.xml` and/or `presProps.xml` as long as generated output matches Open Specs and PowerPoint acceptance.

Required behavior:

- Settings are absent in `ecma_strict`.
- Settings are present and schema-valid in `office_compat`.

---

## 8. Implementation Plan

### Phase 1: Profile plumbing and namespace scaffolding

1. Add `office_profile` to exporter/builder/writer construction and context.
2. Add extension namespace constants and registration support.
3. Introduce helper to apply `mc:Ignorable` prefix lists to part roots.

### Phase 2: svgBlip writer and packaging path

1. Add profile-aware SVG image registration path:
   - register SVG media
   - generate/register PNG fallback media
   - return paired relationship metadata
2. Extend picture rendering to serialize `a:blip` extension list payload.
3. Ensure content types and slide rel writing support the paired assets.

### Phase 3: Presentation image settings and tests

1. Add `p14` image settings in package writing stage when `office_compat`.
2. Add unit + integration tests (see Section 9).
3. Gate with OpenXML audit and regression suites.

---

## 9. Test Specification

### 9.1 Unit tests

Add/extend tests under:

- `tests/unit/drawingml/`
- `tests/unit/io/`

Cases:

1. `office_profile=ecma_strict` does not emit extension namespaces or `mc:Ignorable`.
2. `office_profile=office_compat` emits required extension namespaces and `mc:Ignorable` on parts using extension payloads.
3. SVG image shape emits:
   - base `<a:blip r:embed="...">` for PNG fallback
   - `svgBlip` extension entry with separate SVG relationship ID
4. `a14:useLocalDpi` extension appears under `a:blip` extension list in `office_compat`.
5. Presentation image settings (`discardImageEditData`, `defaultImageDpi`) appear only in `office_compat`.

### 9.2 Integration tests

Add/extend package-level tests under `tests/unit/io/test_pptx_writer.py` and/or `tests/integration/test_pptx_exporter.py`:

1. Convert fixture with embedded SVG image.
2. Assert package contains both `.svg` and `.png` media parts.
3. Assert slide rels include both IDs and correct relationship targets.
4. Assert slide XML contains `svgBlip` extension and MC declarations.
5. Assert OpenXML audit passes (where audit tool is configured).

### 9.3 Golden checks

Add one small golden fixture for extensionized picture XML in `tests/visual/golden/` or unit golden snapshots to lock element ordering and extension URIs.

---

## 10. Backward Compatibility

- Default profile remains `ecma_strict`; existing output stays unchanged.
- `office_compat` is opt-in until validation is complete.
- Existing tests for non-extension rendering must continue to pass unchanged.

---

## 11. Risks and Mitigations

1. **Risk**: Missing/incorrect `mc:Ignorable` causes parser issues.  
   **Mitigation**: Central helper enforces root declaration from used prefix set.

2. **Risk**: Relationship ID mismatches between base blip and `svgBlip`.  
   **Mitigation**: Pair IDs in a single typed payload and assert in tests.

3. **Risk**: Inconsistent part-level settings for image DPI/edit-data.  
   **Mitigation**: Add explicit package-level assertions in integration tests.

4. **Risk**: Non-Office consumer regressions.  
   **Mitigation**: Keep default `ecma_strict` and gate everything behind profile.

---

## 12. Acceptance Criteria

1. `office_profile` is plumbed end-to-end and defaults to `ecma_strict`.
2. `office_compat` emits valid `mc` + ignorable extension markup where required.
3. SVG images in `office_compat` package as `.svg` + `.png` with correct `svgBlip` linkage.
4. `useLocalDpi` and presentation image settings are emitted only in `office_compat`.
5. New unit/integration tests pass and OpenXML audit remains green.

---

## 13. Normative References

- MS-ODRAWXML overview:  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/06cff208-c6e1-4db7-bb68-665135e5f0de
- `svgBlip` type/namespace entry points (MS-ODRAWXML):  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/a807ad3a-1f35-4540-9237-353ed61c93ea
- `a14:useLocalDpi` extension semantics:  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/7e1f1524-1569-4aa2-a6c9-aab2d855bd48
- PowerPoint image extension behaviors (`discardImageEditData`, `defaultImageDpi`):  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/3c206095-ec1d-44a8-a21d-77796c03d59e
- PowerPoint image extensions overview:  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/b9ff79b4-5e24-4c85-b567-e5f43d498375
- Markup Compatibility / extension model context:  
  https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oextxml/c528c6ad-080b-48ac-85a8-052ad01da58e
