# Specification: CSS Cascade for SVG `<use>` Elements

**Version:** 1.1
**Status:** Draft (Revised based on code review)
**Created:** 2025-11-03
**Last Updated:** 2025-11-03
**Author:** Generated with Claude Code

## REVISION SUMMARY

**Key Changes from v1.0:**

1. ✅ **Reuse Existing Infrastructure** - Leverage `StyleResolver`'s existing specificity calculation, selector matching, and caching instead of creating parallel logic

2. ✅ **Fix Cascade Sort** - Correct the existing `_collect_css_declarations` sorting to match CSS Cascade 4 spec with proper origin+importance ordering

3. ✅ **Correct Presentation Attribute Placement** - They sit in **author origin** between stylesheet rules and inline styles (NOT before user-agent styles)

4. ✅ **Preserve Typed Values** - Keep existing Paint object pipeline (no regression to string-only values)

5. ✅ **Simplified Implementation** - Only need to:
   - Add `CSSOrigin` enum to `resolver.py`
   - Fix cascade sort in `_collect_css_declarations()`
   - Handle presentation attributes with correct origin
   - **NO changes needed to `use_expander.py`** (already correct!)

**Estimated Effort Reduced:** 40 hours → **12 hours**

## 1. Overview

### 1.1 Problem Statement

The current implementation of SVG `<use>` element style resolution does not correctly handle CSS cascade and selector specificity according to the SVG specification. This results in incorrect styling of cloned elements, particularly when:

1. CSS selectors with different specificity levels target the original element
2. Inline styles conflict with CSS rules
3. Parent group styles need to be overridden by child-specific rules
4. Presentation attributes interact with CSS rules

**Failing Test:** `tests/integration/w3c/test_struct_use.py::test_struct_use_rectangles_are_green`

**Expected:** 3+ green rectangles with dark green strokes
**Actual:** Only 1 green rectangle, 2 are red

### 1.2 Goals

- **Primary:** Implement spec-compliant CSS cascade resolution for `<use>` elements
- **Secondary:** Pass W3C SVG test suite for `<use>` element styling
- **Tertiary:** Maintain backward compatibility with existing conversion behavior

### 1.3 Non-Goals

- Implementing full CSS3/4 cascade layers
- Supporting `:hover`, `:focus`, or other pseudo-classes on `<use>` elements (browser support varies)
- Implementing CSS animations/transitions for cloned elements

## 2. Background

### 2.1 SVG Specification Requirements

Per the SVG 2 specification:

1. **Cloned Elements Are Hidden from Selectors:**
   CSS selectors do NOT match elements in the cloned shadow tree created by `<use>`

2. **Inheritance Still Applies:**
   Cloned elements inherit styles from the `<use>` element as if they were children

3. **Computed Styles from Original Context:**
   Styles applied to the original (referenced) element should be computed in its original DOM context, then transferred to the clone

4. **Presentation Attribute Priority:**
   SVG2: Presentation attributes contribute to author-level cascade with specificity 0, AFTER all other author stylesheets

### 2.2 Current Implementation

**File:** `src/svg2ooxml/core/styling/use_expander.py`

```python
def _apply_computed_presentation(converter, source: etree._Element, clone: etree._Element):
    # Line 76: Computes paint style from original element
    paint_style = style_resolver.compute_paint_style(source, context=css_context)

    # Lines 87-109: Applies computed values to clone
    # BUT: Does not properly handle selector specificity
```

**File:** `src/svg2ooxml/common/style/resolver.py`

```python
class StyleResolver:
    # Uses tinycss2 for parsing
    # Has basic selector matching
    # MISSING: Proper specificity calculation
    # MISSING: Cascade ordering by origin/importance
```

### 2.3 Gap Analysis

| Feature | Required | Current Status | Gap |
|---------|----------|----------------|-----|
| Selector specificity calculation | ✅ | ✅ **Implemented** | None |
| Cascade ordering (origin, importance) | ✅ | ❌ **Incorrect** | **CRITICAL** |
| Presentation attribute priority | ✅ | ❌ **Missing** | HIGH |
| Inheritance from `<use>` element | ✅ | ✅ | None |
| Style isolation (no selector matching in clones) | ✅ | ✅ | None |
| Inline style priority | ✅ | ⚠️ **Partial** | MEDIUM |
| Typed value preservation (Paint objects) | ✅ | ✅ | None |
| Caching/memoization | ✅ | ✅ | None |

**Current Implementation:**
- `StyleResolver` already has specificity calculation (`_compute_specificity`)
- `StyleResolver` has selector matching and caching
- `StyleResolver` preserves typed values (Paint objects, floats)
- **BUT** cascade sort is incorrect (lines 536-543 in `resolver.py`)

**Current Sort Order** (WRONG):
```python
key=lambda item: (
    1 if item[0].important else 0,  # !important first (WRONG LEVEL)
    item[1],                         # specificity
    item[2],                         # rule order
    item[3],                         # declaration index
)
```

**Correct CSS Cascade 4 Sort Order** (per spec):
1. Origin and importance (user-agent normal < author normal < author inline < user-agent !important < author !important < user !important)
2. Context (encapsulation, not applicable to SVG)
3. Specificity
4. Source order

## 3. Technical Design

### 3.1 Design Principles

**REUSE EXISTING INFRASTRUCTURE:**
- Leverage `StyleResolver`'s existing specificity calculation
- Leverage `StyleResolver`'s existing selector matching and caching
- Leverage `StyleResolver`'s existing typed value pipeline (Paint objects)
- **DO NOT** create parallel parsing/matching logic

**FIX CASCADE SORT:**
- Correct the existing `_collect_css_declarations` sorting to match CSS Cascade 4 spec
- Add origin tracking to `CSSRule` and `CSSDeclaration`
- Handle presentation attributes with correct priority (author origin, specificity 0)

**ENHANCE USE EXPANSION:**
- Compute styles from original element's context (not clone's)
- Cache computed styles to avoid redundant work

### 3.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  SVG Parser (EXISTING)                       │
│  - Extracts <use> elements                                   │
│  - Extracts <style> blocks                                   │
│  - Feeds into StyleResolver                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│           StyleResolver (ENHANCED)                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ EXISTING (keep):                                     │   │
│  │ - tinycss2 parsing                                   │   │
│  │ - Selector specificity calculation                   │   │
│  │ - Selector matching with caching                     │   │
│  │ - Typed value pipeline (Paint objects)               │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ NEW/FIXED:                                           │   │
│  │ - Origin tracking (user-agent/author/inline/pres)    │   │
│  │ - Correct cascade sort (origin+importance first)     │   │
│  │ - Presentation attribute handling (specificity 0)    │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│            Use Element Expander (ENHANCED)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. Clone referenced element                         │   │
│  │ 2. Call StyleResolver in ORIGINAL element context   │   │
│  │ 3. Apply computed styles to clone                   │   │
│  │ 4. Merge <use> element attributes                   │   │
│  │ 5. DO NOT re-evaluate selectors on clone            │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Component Design

#### 3.3.1 Origin Tracking

**Modified:** `src/svg2ooxml/common/style/resolver.py`

Add origin enum and tracking:

```python
from enum import IntEnum

class CSSOrigin(IntEnum):
    """CSS cascade origin.

    Per CSS Cascade 4 spec, normal declarations from origins are ordered:
    user-agent < user < author

    And !important declarations reverse:
    author !important < user !important < user-agent !important

    For SVG, we don't have user stylesheets, so we track:
    - USER_AGENT: Default browser/renderer styles (rarely used in SVG)
    - AUTHOR: Stylesheet rules
    - PRESENTATION_ATTR: SVG presentation attributes (author origin, specificity 0)
    - INLINE: style="" attribute (author origin, specificity high)
    """
    USER_AGENT = 1
    AUTHOR = 2
    PRESENTATION_ATTR = 3  # Still author, but between stylesheets and inline
    INLINE = 4

@dataclass(frozen=True)
class CSSDeclaration:
    """Single CSS declaration with cascade metadata."""
    name: str
    value: str
    important: bool
    origin: CSSOrigin = CSSOrigin.AUTHOR  # NEW: track origin

@dataclass(frozen=True)
class CSSRule:
    """Qualified CSS rule with associated selectors."""
    selectors: tuple[CompiledSelector, ...]
    declarations: tuple[CSSDeclaration, ...]
    order: int
    origin: CSSOrigin = CSSOrigin.AUTHOR  # NEW: track origin
```

#### 3.3.2 Correct Cascade Sort

**Modified:** `src/svg2ooxml/common/style/resolver.py` (lines 536-543)

Fix `_collect_css_declarations` sort order:

```python
def _collect_css_declarations(self, element: etree._Element) -> list[CSSDeclaration]:
    if not self._css_rules:
        return []

    matches: list[tuple[CSSDeclaration, tuple[int, int, int], int, int, CSSOrigin]] = []
    for rule in self._css_rules:
        for selector in rule.selectors:
            if not selector.matches(element):
                continue
            for index, declaration in enumerate(rule.declarations):
                # Include origin in tuple
                matches.append((
                    declaration,
                    selector.specificity,
                    rule.order,
                    index,
                    declaration.origin,  # NEW
                ))

    if not matches:
        return []

    # CORRECT CASCADE SORT per CSS Cascade 4:
    matches.sort(
        key=lambda item: (
            # 1. Origin and importance (combined)
            _cascade_precedence(item[4], item[0].important),

            # 2. Specificity (for author-origin rules)
            item[1],  # (ids, classes, types) tuple

            # 3. Source order
            item[2],  # rule order
            item[3],  # declaration index within rule
        )
    )
    return [item[0] for item in matches]

def _cascade_precedence(origin: CSSOrigin, important: bool) -> int:
    """Calculate cascade precedence per CSS Cascade 4 spec.

    Normal declarations (importance=False):
        UA(1) < Author(2) < Presentation(3) < Inline(4)

    Important declarations (importance=True):
        UA !important stays at bottom, author origins reverse among themselves:
        UA(1) < Inline(12) < Presentation(13) < Author(14)

    Note: In our implementation, UA origin remains weakest for both normal and
    !important declarations. Only author-origin styles (Author/Presentation/Inline)
    reverse their relative order when !important.
    """
    if important:
        if origin == CSSOrigin.USER_AGENT:
            return 1  # UA !important stays at bottom (loses to all author !important)
        # Author origins reverse for !important: Inline < Presentation < Author
        # Map: Author(2)->14, Presentation(3)->13, Inline(4)->12
        return 16 - int(origin)
    else:
        # Normal order: higher origin wins
        return int(origin)
```

#### 3.3.3 Enhanced Use Element Expander

**Modified File:** `src/svg2ooxml/core/styling/use_expander.py`

```python
def _apply_computed_presentation(converter, source: etree._Element, clone: etree._Element) -> None:
    """Apply computed styles from source element's original context to clone.

    CHANGES:
    1. Use EXISTING StyleResolver.compute_paint_style() but with fixed cascade
    2. Compute styles in source element's DOM context (not clone's)
    3. Preserve typed values (Paint objects, floats)
    """
    clone.set("data-svg2ooxml-use-clone", "true")

    style_resolver: StyleResolver | None = getattr(converter, "_style_resolver", None)
    if style_resolver is None:
        return

    css_context = getattr(converter, "_css_context", None)

    try:
        # CRITICAL: Compute styles from ORIGINAL element (source), not clone
        # This uses the fixed cascade resolution in StyleResolver
        paint_style = style_resolver.compute_paint_style(source, context=css_context)
    except Exception:  # pragma: no cover - defensive
        return

    # Apply computed typed values to clone
    # NO CHANGE from current implementation - preserves Paint objects, floats, etc.
    def maybe_set(attr: str, value: object) -> None:
        if value is None:
            return
        if clone.get(attr) is not None:
            return
        clone.set(attr, str(value))

    fill_value = paint_style.get("fill")
    if isinstance(fill_value, str) and fill_value:
        maybe_set("fill", fill_value)

    stroke_value = paint_style.get("stroke")
    if isinstance(stroke_value, str) and stroke_value:
        maybe_set("stroke", stroke_value)

    # ... (rest of existing property application)
```

**Key Insight:** The existing code in `use_expander.py` is mostly correct! It already:
- Computes styles from the `source` element (original context) ✓
- Preserves typed values from `compute_paint_style()` ✓
- Doesn't override existing attributes on clone ✓

The only issue is that `StyleResolver.compute_paint_style()` uses incorrect cascade sort. Once we fix the cascade sort in `resolver.py`, `use_expander.py` will work correctly **with no changes needed**!

### 3.3 Algorithm: Cascade Resolution

```
For each CSS property on an element:

1. COLLECT all declarations that apply:
   a. Presentation attributes (specificity 0)
   b. User-agent stylesheet rules
   c. Author stylesheet rules
   d. Inline style="" attribute

2. FILTER rules whose selectors match the element:
   - For <use> clones: ONLY use original element's context
   - DO NOT evaluate selectors against cloned shadow tree

3. SORT declarations by priority:
   Primary:   Origin (user-agent < author < inline)
   Secondary: !important flag (normal < important)
   Tertiary:  Specificity (calculated from selector)
   Quaternary: Source order (later > earlier)

4. RETURN the highest priority declaration value
```

### 3.4 Data Structures

#### Selector Matching Cache

```python
@dataclass
class SelectorMatchCache:
    """Cache selector matching results to avoid re-evaluation."""

    _cache: dict[tuple[str, str], bool] = field(default_factory=dict)

    def matches(self, selector: str, element_id: str) -> bool:
        """Check if selector matches element (with caching)."""
        key = (selector, element_id)
        if key not in self._cache:
            self._cache[key] = self._evaluate_selector(selector, element_id)
        return self._cache[key]
```

## 4. Implementation Plan (REVISED)

### 4.1 Phase 1: Fix Cascade Sort (4 hours)

**Tasks:**

1. **Add `CSSOrigin` enum to `resolver.py`**
   - Add `CSSOrigin` IntEnum (USER_AGENT, AUTHOR, PRESENTATION_ATTR, INLINE)
   - Add `origin` field to `CSSDeclaration` dataclass
   - Add `origin` field to `CSSRule` dataclass
   - **Estimated:** 30 minutes

2. **Fix `_collect_css_declarations()` sort**
   - Add `_cascade_precedence()` helper function
   - Update sort key to use origin+importance first, then specificity
   - Update tuple to include origin
   - **Estimated:** 1 hour

3. **Handle presentation attributes with correct origin**
   - In `compute_paint_style()` and `compute_text_style()`
   - Mark presentation attributes as `CSSOrigin.PRESENTATION_ATTR`
   - Ensure they sort after stylesheet rules but before inline styles
   - **Estimated:** 1.5 hours

4. **Add unit tests**
   - Test cascade precedence function
   - Test origin+importance ordering
   - Test presentation attribute priority
   - Test !important handling across origins
   - **Estimated:** 1 hour

**Deliverables:**
- Fixed cascade sort in `StyleResolver`
- All unit tests passing
- No changes to use_expander.py needed!

### 4.2 Phase 2: Integration Testing (4 hours)

**Tasks:**

1. **Add integration tests for `<use>` cascade**
   - Test `<use>` with class selector
   - Test `<use>` with inline style override
   - Test `<use>` with presentation attributes
   - Test `<use>` with !important rules
   - Test nested `<use>` elements
   - **Estimated:** 2 hours

2. **Debug W3C test**
   - Run `test_struct_use_rectangles_are_green`
   - Analyze failures
   - Fix any edge cases discovered
   - **Estimated:** 2 hours

**Deliverables:**
- Comprehensive integration test suite
- W3C test closer to passing (may still have edge cases)

### 4.3 Phase 3: W3C Compliance & Polish (4 hours)

**Tasks:**

1. **Fix remaining W3C test edge cases**
   - Handle child selectors (`.class > rect`)
   - Handle group inheritance
   - Verify selector specificity edge cases
   - **Estimated:** 2 hours

2. **Performance verification**
   - Run benchmarks on large SVGs
   - Verify no >5% slowdown
   - Existing caching should handle performance
   - **Estimated:** 30 minutes

3. **Documentation**
   - Add code comments to cascade sort
   - Update this spec with final results
   - Document any remaining known limitations
   - **Estimated:** 1.5 hours

**Deliverables:**
- Passing W3C `struct-use-10-f` test ✅
- Performance validated ✅
- Complete documentation ✅

### 4.4 Task Breakdown

```yaml
tasks:
  - id: CSS-1
    title: Implement CSS Specificity Calculator
    file: src/svg2ooxml/common/style/specificity.py
    effort: 4h
    dependencies: []

  - id: CSS-2
    title: Implement CSS Cascade Resolver
    file: src/svg2ooxml/common/style/cascade.py
    effort: 6h
    dependencies: [CSS-1]

  - id: CSS-3
    title: Add Unit Tests for Cascade Engine
    file: tests/unit/common/style/test_cascade.py
    effort: 4h
    dependencies: [CSS-1, CSS-2]

  - id: CSS-4
    title: Integrate Cascade Resolver into Parser
    files:
      - src/svg2ooxml/core/parser/__init__.py
      - src/svg2ooxml/core/ir/converter.py
    effort: 3h
    dependencies: [CSS-2]

  - id: CSS-5
    title: Update Use Element Expander
    file: src/svg2ooxml/core/styling/use_expander.py
    effort: 4h
    dependencies: [CSS-4]

  - id: CSS-6
    title: Add Integration Tests
    file: tests/integration/test_use_cascade.py
    effort: 4h
    dependencies: [CSS-5]

  - id: CSS-7
    title: Fix W3C Test Failures
    file: tests/integration/w3c/test_struct_use.py
    effort: 8h
    dependencies: [CSS-6]

  - id: CSS-8
    title: Performance Optimization
    files:
      - src/svg2ooxml/common/style/cascade.py
      - src/svg2ooxml/common/style/specificity.py
    effort: 4h
    dependencies: [CSS-7]

  - id: CSS-9
    title: Documentation
    files:
      - docs/architecture/css-cascade.md
      - docs/specs/css-cascade-use-elements.md
    effort: 3h
    dependencies: [CSS-8]
```

## 5. Testing Strategy

### 5.1 Unit Tests

**File:** `tests/unit/common/style/test_specificity.py`

```python
def test_specificity_id_selector():
    assert Specificity.from_selector("#foo") == Specificity(ids=1, classes=0, types=0)

def test_specificity_class_selector():
    assert Specificity.from_selector(".bar") == Specificity(ids=0, classes=1, types=0)

def test_specificity_complex_selector():
    # #foo .bar > baz
    assert Specificity.from_selector("#foo .bar > baz") == Specificity(ids=1, classes=1, types=1)
```

**File:** `tests/unit/common/style/test_cascade.py`

```python
def test_cascade_origin_priority():
    resolver = CascadeResolver()
    resolver.add_rule(".foo", {"fill": "red"}, Origin.USER_AGENT)
    resolver.add_rule(".foo", {"fill": "green"}, Origin.AUTHOR)

    element = make_element_with_class("foo")
    assert resolver.compute_style(element, "fill") == "green"

def test_cascade_important_flag():
    resolver = CascadeResolver()
    resolver.add_rule(".foo", {"fill": "red !important"}, Origin.USER_AGENT)
    resolver.add_rule(".foo", {"fill": "green"}, Origin.AUTHOR)

    element = make_element_with_class("foo")
    assert resolver.compute_style(element, "fill") == "red"
```

### 5.2 Integration Tests

**File:** `tests/integration/test_use_cascade.py`

```python
def test_use_inherits_class_selector_style():
    svg = """
    <svg>
      <style>.rect { fill: green; }</style>
      <defs>
        <rect id="r" class="rect" width="10" height="10"/>
      </defs>
      <use href="#r" x="0" y="0"/>
    </svg>
    """
    pptx = convert_svg_to_pptx(svg)
    shapes = get_shapes(pptx)
    assert shapes[0].fill.color == "008000"  # green

def test_use_inline_style_overrides_class():
    svg = """
    <svg>
      <style>.rect { fill: green; }</style>
      <defs>
        <rect id="r" class="rect" style="fill: blue" width="10" height="10"/>
      </defs>
      <use href="#r" x="0" y="0"/>
    </svg>
    """
    pptx = convert_svg_to_pptx(svg)
    shapes = get_shapes(pptx)
    assert shapes[0].fill.color == "0000FF"  # blue
```

### 5.3 W3C Conformance Tests

**File:** `tests/integration/w3c/test_struct_use.py`

```python
def test_struct_use_rectangles_are_green():
    """W3C SVG Test: struct-use-10-f

    Tests CSS selector specificity and cascade for <use> elements.
    Should result in 3 green rectangles with dark green strokes.
    """
    # Existing test - should now PASS
```

## 6. Success Criteria

### 6.1 Functional Requirements

- ✅ CSS selector specificity correctly calculated
- ✅ Cascade origin priority respected (user-agent < author < inline)
- ✅ `!important` flag handled correctly
- ✅ Presentation attributes have correct priority (SVG2 spec)
- ✅ `<use>` elements inherit styles from original context
- ✅ Selectors do NOT match into cloned shadow tree

### 6.2 Test Requirements

- ✅ All new unit tests passing (>90% coverage)
- ✅ All integration tests passing
- ✅ W3C test `test_struct_use_rectangles_are_green` passing
- ✅ No regressions in existing tests

### 6.3 Performance Requirements

- ✅ Conversion time increase <10% for typical SVGs
- ✅ Memory usage increase <20%
- ✅ Cascade resolution cached where possible

## 7. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Breaking existing conversions | HIGH | MEDIUM | Extensive regression testing; feature flag for rollback |
| Performance degradation | MEDIUM | MEDIUM | Profiling; caching; optimization in Phase 3 |
| tinycss2 limitations | MEDIUM | LOW | Augment with custom selector parser if needed |
| Complex edge cases | MEDIUM | HIGH | Incremental implementation; prioritize common cases |
| W3C spec ambiguity | LOW | LOW | Reference multiple browser implementations |

## 8. Future Enhancements

### 8.1 Out of Scope (for now)

- CSS cascade layers (`@layer`)
- CSS scoping (`@scope`)
- Shadow DOM styling
- CSS custom properties (`--var`) inheritance into `<use>` clones
- Pseudo-class selectors (`:hover`, `:focus`)

### 8.2 Potential Follow-ups

1. **Full CSS3 Specificity:** Support attribute selectors, pseudo-elements
2. **CSS Variables:** Allow custom properties to inherit into clones
3. **Performance:** Pre-compute cascade for common selector patterns
4. **Debugging:** Add CSS cascade debugging output

## 9. References

- [SVG 2 Specification - The use element](https://www.w3.org/TR/SVG2/struct.html#UseElement)
- [CSS Cascade and Inheritance Level 4](https://www.w3.org/TR/css-cascade-4/)
- [CSS Selectors Level 3 - Specificity](https://www.w3.org/TR/selectors-3/#specificity)
- [O'Reilly Using SVG - The Cascade](https://oreillymedia.github.io/Using_SVG/extras/ch03-cascade.html)
- [W3C SVG Test Suite](https://github.com/w3c/svgwg/tree/main/tests)

## 10. Appendix

### 10.1 CSS Specificity Examples

```css
/* Specificity: (0, 0, 1) */
rect { fill: red; }

/* Specificity: (0, 1, 0) */
.green-rect { fill: green; }

/* Specificity: (0, 1, 1) */
rect.green-rect { fill: green; }

/* Specificity: (1, 0, 0) */
#my-rect { fill: blue; }

/* Specificity: (1, 1, 1) */
#my-rect.green-rect rect { fill: purple; }
```

### 10.2 Cascade Order Example

```css
/* 1. User-agent stylesheet (lowest priority) */
rect { fill: black; }

/* 2. Author stylesheet */
.rect { fill: blue; }

/* 3. Higher specificity author rule */
#my-rect { fill: green; }

/* 4. Inline style (highest priority, except...) */
<rect id="my-rect" class="rect" style="fill: red"/>

/* 5. !important overrides everything */
.rect { fill: purple !important; }

/* Final result: purple (due to !important) */
```

### 10.3 Code Review Checklist

- [ ] Specificity calculation matches CSS spec
- [ ] Cascade sorting algorithm correct
- [ ] `<use>` styles computed from original context
- [ ] Selectors don't match into cloned tree
- [ ] Presentation attributes have correct priority
- [ ] Inline styles override CSS rules
- [ ] `!important` flag handled correctly
- [ ] Performance tested with large SVGs
- [ ] Unit test coverage >90%
- [ ] Integration tests pass
- [ ] W3C tests pass
- [ ] Documentation complete
- [ ] No regressions in existing tests

---

**Estimated Total Effort:** 40 hours (1 week full-time)
**Complexity:** HIGH
**Priority:** MEDIUM
**Dependencies:** None (can be implemented independently)
