# ADR-021: Eliminate String-Parse-Graft XML Generation

- **Status:** Proposed
- **Date:** 2026-02-07
- **Owners:** svg2ooxml team
- **Depends on:** ADR-020 (animation writer rewrite — proves the pattern)

## 1. Problem Statement

Throughout the codebase, XML fragments are built as strings, wrapped in a
temporary namespace root, parsed with `etree.fromstring()`, and loop-appended
into an lxml tree. This pattern:

- **Silently drops malformed XML** — a single misquoted attribute produces an
  `XMLSyntaxError` that callers typically swallow or ignore.
- **Duplicates namespace boilerplate** — the same wrapper template appears 20+
  times across 13 files.
- **Defeats lxml's type safety** — string concatenation gives no compile-time
  or runtime guarantees about element structure.
- **Costs unnecessary allocations** — every fragment round-trips through
  serialize → encode → parse → extract → append.

ADR-020 eliminated this pattern from the animation module. This ADR extends the
same approach to the rest of the codebase.

### 1.1 Inventory of Affected Sites

**Pipeline mappers (`core/pipeline/mappers/`):**

| File | Lines | What it grafts |
|---|---|---|
| `path_mapper.py` | 109, 116, 123, 129 | clip XML, geometry XML, fill XML, effects XML |
| `group_mapper.py` | 52 | child shape XML |
| `image_mapper.py` | 153 | clip XML |

**DrawingML runtime (`drawingml/`):**

| File | Lines | What it grafts |
|---|---|---|
| `paint_runtime.py` | 67, 73, 131, 137 | tail/head markers, pattern fill, gradient fill |
| `shapes_runtime.py` | 571 | hyperlink/navigation XML |
| `mask_writer.py` | 171 | geometry XML |

**Services:**

| File | Lines | What it grafts |
|---|---|---|
| `gradient_service.py` | 310, 333 | gradient stop list (linear and radial) |

**Filters (`filters/`):**

| File | Lines | What it grafts |
|---|---|---|
| `primitives/composite.py` | 376, 390 | effect list children |
| `utils/dml.py` | 79 | effect list children |

**Other:**

| File | Lines | What it grafts |
|---|---|---|
| `core/masks/baker.py` | 30 | combined mask content |

Total: **21 sites across 11 files** (excluding animation, already migrated).

## 2. Design

### 2.1 Upstream Functions Return `etree._Element`

Every function that currently returns an XML string should instead return an
`etree._Element` (or `list[etree._Element]`). The caller appends the element
directly — no parsing required.

This is the same change ADR-020 made for animation handlers: `build()` returns
`etree._Element | None`, and `to_string()` is called once at the final
serialization boundary.

### 2.2 Extraction Utility for Transitional Period

During migration, introduce a helper to replace the 20 identical wrapper
templates:

```python
# src/svg2ooxml/drawingml/xml_builder.py

def graft_xml_fragment(
    parent: etree._Element,
    xml: str,
    ns: str = "http://schemas.openxmlformats.org/drawingml/2006/main",
) -> None:
    """Parse an XML fragment string and append children to parent.

    Temporary bridge during migration from string-returning functions
    to element-returning functions. New code should NOT use this.
    """
    wrapped = f'<root xmlns:a="{ns}">{xml}</root>'
    temp = etree.fromstring(wrapped.encode("utf-8"))
    for child in temp:
        parent.append(child)
```

This collapses 21 copy-pasted blocks to single-line calls, making the remaining
migration targets visible and mechanical.

### 2.3 Serialization Boundary

`to_string()` should only be called at the package-writing boundary in
`io/pptx_writer.py`. Interior modules pass elements, never strings.

## 3. Migration Plan

### Phase 1: Extract helper (low risk)

Replace all 21 wrap-parse-graft blocks with calls to `graft_xml_fragment()`.
No behavior change — pure mechanical refactor.

**Files:** all 11 listed in Section 1.1

### Phase 2: Migrate producers (per-module, incremental)

Convert string-returning functions to element-returning, starting with the
highest-traffic paths:

1. `gradient_service.py` — `_serialise_stop()` and `_extract_gradient_stops()`
   return elements instead of strings
2. `paint_runtime.py` — marker/fill/gradient helpers return elements
3. `path_mapper.py` — clip/geometry providers return elements
4. `filters/utils/dml.py` and `filters/primitives/composite.py`
5. `mask_writer.py`, `shapes_runtime.py`, `group_mapper.py`, `image_mapper.py`

Each module is independently convertible. After a module's producers return
elements, its `graft_xml_fragment()` calls become direct `parent.append()`.

### Phase 3: Remove helper

Once all producers return elements, delete `graft_xml_fragment()`.

## 4. Testing Strategy

- Existing unit and integration tests provide regression coverage.
- Golden master XML comparison (as established in ADR-020 Phase 5.6) can be
  extended to cover gradient, paint, and filter output.
- Each phase should run the full test suite before merge.

## 5. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Namespace differences after migration | `p_elem()`/`a_elem()` already use Clark notation; `to_string()` handles prefix mapping |
| Large diff across many files | Phase 1 is mechanical and reviewable; Phase 2 is per-module |
| Breaking callers that expect strings | Search for all call sites before converting; Python type checker catches mismatches |

## 6. Decision

Adopt the three-phase approach. Phase 1 (extract helper) is low-risk and can
ship immediately. Phase 2 modules are prioritised by bug frequency and
contributor pain, not all-at-once.
