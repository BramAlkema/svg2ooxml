# ADR-020: Rewrite PowerPoint Animation Timing XML Writer

- **Status:** Proposed
- **Date:** 2026-02-06
- **Owners:** svg2ooxml animation team
- **Depends on:** ADR-013 (animation & multi-slide port), ADR-drawingml-writer-export
- **Supersedes:** `docs/specs/animation-writer-refactoring-spec.md` (partially implemented)

## 1. Problem Statement

The animation timing writer in `src/svg2ooxml/drawingml/animation/` was restructured
into separate handler modules per the refactoring spec, but the core generation
approach did not change: handlers still build XML as f-strings, and the builders
convert those strings back to lxml trees through a fragile parse-and-graft cycle.
Recent commits (`f322496`, `65853a4`) required extensive trial-and-error to get
PowerPoint to accept the generated timing XML. This ADR documents the specific
failures and prescribes a rewrite of the XML generation layer, combined with
filling the remaining animation feature gaps.

### 1.1 Mixed XML Paradigms

Every handler's `build()` returns `str`. The `AnimationXMLBuilder` uses lxml
internally but calls `to_string()` on every builder method, returning strings. The
TAV builder and value formatters produce `etree._Element`. Handlers receive strings
from builders, wrap them in more f-strings with manual 40-space indentation, and
pass the combined string back to another builder that must re-parse it.

### 1.2 String→Parse→Graft Cycle

In `xml_builders.py` (`build_timing_container`, lines 53–67), each handler fragment
is wrapped in a temporary `<root xmlns:a="..." xmlns:p="...">`, parsed with
`etree.fromstring()`, the first child is extracted, duplicate namespace attributes
are manually stripped, and the child is appended to the lxml tree. The same pattern
is duplicated in `build_par_container` (lines 120–134). If a handler produces
malformed XML, the `except etree.XMLSyntaxError: continue` silently drops the
animation.

### 1.3 Scattered Unit Conversions

Each handler independently performs unit conversions with different approaches:

- `opacity.py` — `self._processor.parse_opacity()` returns PPT units as string
- `transform.py` line 207 — inline `int(round(from_scale[0] * 100000))`
- `transform.py` line 224 — `self._processor.format_ppt_angle()` for rotation delta
- `transform.py` line 268 — `int(round(self._units.to_emu(end_dx - start_dx, axis="x")))`
- `motion.py` lines 162–167 — px→EMU then divide by slide dimensions, importing
  `DEFAULT_SLIDE_SIZE` from `svg2ooxml.drawingml.writer` (cross-module dependency)
- `numeric.py` — delegates to `self._processor.normalize_numeric_value()` which
  checks `ANGLE_ATTRIBUTES` and `AXIS_MAP`

### 1.4 Magic Numbers

- `motion.py` line 183: `<p:rCtr x="4306" y="0"/>` — rotation center constant
  calibrated from golden master, no derivation documented.
- `writer.py` line 42: `self._id_counter = 1` — IDs start at 1. The timing
  container builder uses `timing_id` and `timing_id + 1` for root and mainSeq, but
  these are allocated *after* animation IDs, so the root ends up numbered higher
  than its children.
- Scale conversion uses `* 100000`, opacity uses `* 100000`, angles use `* 60000`.
  These are correct but unnamed.

### 1.5 Mock-Detection in Base Handler

`base.py` (lines 126–161) contains `_resolve_target_attribute()` and
`_resolve_animation_type()` with explicit `unittest.mock` module detection:

```python
module_name = getattr(target.__class__, "__module__", "")
if module_name != "unittest.mock":
    target_str = str(target)
```

This indicates tests were written with Mock objects instead of real
`AnimationDefinition` instances, and the production code was shaped to work around
mock behavior.

### 1.6 Incomplete Animation Support

| Feature | Status | Details |
|---------|--------|---------|
| Translate (multi-keyframe) | Missing | `_build_translate_behavior_content` only uses first/last pair |
| SkewX / SkewY | Missing | Not in `can_handle()`, IR defines the types |
| Matrix decomposition | Partial | Only handles pure translate/scale/rotate, drops composites |
| `rotate="auto"` | Missing | Motion handler ignores rotation entirely |
| Event-based `begin` | Missing | IR's `AnimationTiming.begin` is `float`, not rich enough |
| `calcMode="paced"` | Missing | Parsed in IR but no handler implements paced timing |
| `additive` / `accumulate` | Missing | Present on `AnimationDefinition`, never read by handlers |

### 1.7 ID Allocation Bug

`build_timing_container` uses `timing_id` for the root `<p:cTn>` and
`timing_id + 1` for mainSeq. But `_allocate_ids()` in `writer.py` allocates IDs
during handler building, so animation IDs are lower than the root and mainSeq IDs.
PowerPoint expects root=1, mainSeq=2, then animation IDs ascending from there.

### 1.8 Missing Click Group Wrapper

The current builder appends animation `<p:par>` elements directly into mainSeq's
`<p:childTnLst>`. Per ECMA-376 and PowerPoint's own output, animations should be
wrapped in an intermediate click-group `<p:par>` inside mainSeq. This does not
always break playback but produces non-conformant structure.

---

## 2. Decision

### 2.1 Core Principle: Element-Only Handlers, Single Serialization

All handlers return `etree._Element` instead of `str`. The `to_string()` call
happens exactly once, at the end of `DrawingMLAnimationWriter.build()`, after the
complete `<p:timing>` tree has been assembled in memory. No intermediate
serialization. No string wrapping. No re-parsing.

### 2.2 Handler Signature Change

```python
# Current
@abstractmethod
def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> str:

# New
@abstractmethod
def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> etree._Element | None:
```

Returning `None` replaces returning `""` for skipped or failed animations.

### 2.3 Builder Signature Change

All `AnimationXMLBuilder` methods that currently return `str` will return
`etree._Element`:

| Method | Current | New |
|--------|---------|-----|
| `build_timing_container` | `str` | `etree._Element` |
| `build_par_container` | `str` | `etree._Element` |
| `build_behavior_core` | `str` | `etree._Element` |

Methods already returning `etree._Element` are unchanged (`build_tav_element`,
`build_tav_list_container`, `build_numeric_value`, `build_color_value`,
`build_point_value`).

### 2.4 Writer Serialization Point

```python
class DrawingMLAnimationWriter:
    def build(self, animations, timeline, ...) -> str:
        elements: list[etree._Element] = []
        for animation in animations:
            element = handler.build(animation, par_id, behavior_id)
            if element is not None:
                elements.append(element)

        if not elements:
            return ""

        timing_tree = self._xml_builder.build_timing_tree(
            ids=self._id_allocator.allocate(len(elements)),
            animation_elements=elements,
            animated_shape_ids=animated_shape_ids,
        )
        return to_string(timing_tree)  # single serialization
```

---

## 3. Timing Tree Builder — ECMA-376 Compliant

### 3.1 Target Structure

```xml
<p:timing>
  <p:tnLst>
    <p:par>
      <p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
        <p:childTnLst>
          <p:seq concurrent="1" nextAc="seek">
            <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
              <p:childTnLst>
                <!-- Click group wrapper (all SVG auto-play anims in group 0) -->
                <p:par>
                  <p:cTn id="3" fill="hold">
                    <p:stCondLst>
                      <p:cond delay="0"/>
                    </p:stCondLst>
                    <p:childTnLst>
                      <!-- Individual animation <p:par> elements (id=4,6,8,...) -->
                    </p:childTnLst>
                  </p:cTn>
                </p:par>
              </p:childTnLst>
            </p:cTn>
            <p:prevCondLst>
              <p:cond evt="onPrev" delay="0">
                <p:tgtEl><p:sldTgt/></p:tgtEl>
              </p:cond>
            </p:prevCondLst>
            <p:nextCondLst>
              <p:cond evt="onNext" delay="0">
                <p:tgtEl><p:sldTgt/></p:tgtEl>
              </p:cond>
            </p:nextCondLst>
          </p:seq>
        </p:childTnLst>
      </p:cTn>
    </p:par>
  </p:tnLst>
  <p:bldLst>
    <p:bldP spid="N" grpId="0" animBg="1"/>
  </p:bldLst>
</p:timing>
```

### 3.2 ID Allocation Strategy

IDs will be pre-allocated top-down before building the tree:

```python
@dataclass(frozen=True)
class AnimationIDs:
    par: int
    behavior: int

@dataclass(frozen=True)
class TimingIDs:
    root: int            # 1
    main_seq: int        # 2
    click_group: int     # 3
    animations: list[AnimationIDs]  # (4,5), (6,7), ...

class TimingIDAllocator:
    def allocate(self, n_animations: int) -> TimingIDs:
        counter = 0
        def next_id():
            nonlocal counter
            counter += 1
            return counter

        return TimingIDs(
            root=next_id(),
            main_seq=next_id(),
            click_group=next_id(),
            animations=[
                AnimationIDs(par=next_id(), behavior=next_id())
                for _ in range(n_animations)
            ],
        )
```

This replaces the current `_next_id()` / `_allocate_ids()` approach that generates
IDs during building, resulting in out-of-order numbering.

---

## 4. Handler Rewrites

### 4.1 Common Pattern

Each handler builds a subtree of lxml elements and returns the root:

```python
class OpacityAnimationHandler(AnimationHandler):
    def build(self, animation, par_id, behavior_id):
        # Build behavior core as lxml element (not string)
        cBhvr = self._xml.build_behavior_core(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
        )

        # Build animation-specific element using lxml
        anim_effect = a_elem("animEffect", transition="in", filter="fade")
        anim_effect.append(cBhvr)

        # Build par container as lxml element
        return self._xml.build_par_container(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_effect,  # element, not string
        )
```

No f-strings. No indentation. No string concatenation.

### 4.2 Handler-Specific Changes

**OpacityAnimationHandler** (`opacity.py`):
- Remove f-string XML construction (lines 129–137 with 40-space indentation).
- Remove mock-detection calls. Access `animation.target_attribute` directly.
- Verify `<a:animEffect>` / `<a:fade>` structure against ECMA-376.

**ColorAnimationHandler** (`color.py`):
- Remove f-string XML (lines 157–181: 14 lines of f-string become 6 lines of
  `p_sub()` calls).
- Remove `textwrap.indent` for TAV list indentation — append lxml element directly.
- Remove manual `xmlns:svg2` declaration injection.

**NumericAnimationHandler** (`numeric.py`):
- Same f-string elimination as color handler.
- Remove duplicate `_escape_value` method — lxml handles attribute escaping.

**TransformAnimationHandler** (`transform.py`, 477 lines):
- **Scale**: Convert `<p:from x y>` / `<p:to x y>` from f-strings to `p_sub()`.
- **Rotate**: Convert `<p:animRot by>` from f-string to `p_elem("animRot", by=...)`.
- **Translate**: Extend for multi-keyframe support (section 5.1).
- **Matrix**: Improve decomposition (section 5.2).
- Remove all `to_string()` + `indent()` + re-parse cycles for TAV lists.

**MotionAnimationHandler** (`motion.py`):
- Convert `<a:animMotion>` f-string to lxml.
- Replace `rCtr x="4306"` magic number with named constant + derivation comment.
- Replace `DEFAULT_SLIDE_SIZE` import from `writer.py` — receive slide dimensions
  via `AnimationUnitConverter`.

**SetAnimationHandler** (`set.py`):
- Convert `<p:set>` f-string to lxml.
- Convert color/numeric value blocks from f-string to element construction.

### 4.3 Eliminating Mock-Detection

Remove `_resolve_target_attribute`, `_resolve_animation_type`, and
`_animation_type_to_str` from `base.py`. Tests will construct real
`AnimationDefinition` instances instead of using Mock objects.

Simplified base handler:

```python
class AnimationHandler(ABC):
    def __init__(self, xml: AnimationXMLBuilder, tav: TAVBuilder, units: AnimationUnitConverter):
        self._xml = xml
        self._tav = tav
        self._units = units

    @abstractmethod
    def can_handle(self, animation: AnimationDefinition) -> bool: ...

    @abstractmethod
    def build(self, animation: AnimationDefinition, par_id: int, behavior_id: int) -> etree._Element | None: ...
```

---

## 5. Filling Feature Gaps

### 5.1 Translate Animations (Multi-Keyframe)

Current `_build_translate_behavior_content` only uses first and last translation
pairs, computing a single `<p:by>` delta.

**Fix**: When a translate animation has >2 values, emit `<p:animMotion>` with a
`path` attribute containing M/L segments, coordinates normalized to slide fractions:

```python
def _build_translate_path(self, pairs: list[tuple[float, float]]) -> str:
    segments = []
    for i, (dx, dy) in enumerate(pairs):
        nx = self._units.px_to_slide_fraction(dx, axis="x")
        ny = self._units.px_to_slide_fraction(dy, axis="y")
        cmd = "M" if i == 0 else "L"
        segments.append(f"{cmd} {nx:.6f} {ny:.6f}")
    return " ".join(segments) + " E"
```

For 2-value translate animations, the existing `<p:by>` approach is correct and
simpler — keep it.

### 5.2 Matrix Decomposition

Current `_classify_matrix` handles only pure translate, scale, or rotation. A
rotated-then-translated matrix is dropped.

**Fix**: Implement proper SVG matrix decomposition (QR) into translate + rotate +
scale components:

```python
def decompose_matrix(a, b, c, d, e, f):
    tx, ty = e, f
    sx = math.sqrt(a*a + b*b)
    sy = math.sqrt(c*c + d*d)
    det = a*d - b*c
    if det < 0:
        sy = -sy
    angle = math.degrees(math.atan2(b, a))
    return (tx, ty), angle, (sx, sy)
```

When a matrix contains composite transforms, emit multiple behavior elements within
a single `<p:par>` container. PowerPoint supports multiple behaviors in one par.

### 5.3 Skew Handling

SVG `skewX(angle)` / `skewY(angle)` have no PowerPoint equivalent.

**Decision**: Skip with a logged warning and metadata annotation for the initial
implementation. Document in a `policy.animation_support_matrix` which SVG features
map to PPT elements and which are unsupported.

### 5.4 Event-Based Begin Triggers

SVG `begin="click"`, `begin="rect1.end+0.5s"` require a richer begin type in the
IR. Currently `AnimationTiming.begin` is `float`.

**Decision**: Defer IR changes to a separate effort. For the rewrite, preserve the
current `float` begin behavior. Document the mapping for future implementation:

| SVG `begin` | PPT `<p:cond>` |
|-------------|-----------------|
| `"0s"`, `"2s"` | `<p:cond delay="2000"/>` |
| `"click"` | `<p:cond evt="onClick" delay="0"><p:tgtEl><p:spTgt spid="..."/></p:tgtEl></p:cond>` |
| `"rect1.end"` | `<p:cond evt="onEnd" delay="0"><p:tgtEl><p:spTgt spid="rect1_id"/></p:tgtEl></p:cond>` |
| `"rect1.end+0.5s"` | Same with `delay="500"` |

### 5.5 Paced calcMode

SVG `calcMode="paced"` distributes velocity evenly across total distance. Implement
for numeric and translate animations by computing paced key times from value
distances:

```python
def compute_paced_key_times(values: list[float]) -> list[float]:
    distances = [0.0]
    for i in range(1, len(values)):
        distances.append(distances[-1] + abs(values[i] - values[i-1]))
    total = distances[-1]
    if total == 0:
        return [i / (len(values) - 1) for i in range(len(values))]
    return [d / total for d in distances]
```

Motion path paced mode requires arc-length parameterization — defer that.

### 5.6 Additive and Accumulate

- **`additive="sum"`**: Set `additive="sum"` on the behavior's `<p:cTn>`. PowerPoint
  supports this attribute.
- **`additive="replace"`**: Default, no attribute needed.
- **`accumulate="sum"`**: No direct PPT equivalent. Defer to future phase with
  pre-computation of accumulated values.

### 5.7 repeatCount and fill Correction

Current `build_behavior_core` hardcodes `repeatCount="0"` and `fill="hold"`
regardless of the animation's actual values. Fix:

- Map `FillMode.FREEZE` → `fill="hold"`, `FillMode.REMOVE` → omit `fill` attribute
  (PPT default is remove).
- Map `repeat_count=None` or `1` → omit `repeatCount`, `"indefinite"` →
  `repeatCount="indefinite"`, integer N → `repeatCount="{N*1000}"` (PPT uses
  1000ths).

---

## 6. Centralized Unit Conversion

Create `src/svg2ooxml/drawingml/animation/unit_conversion.py`:

```python
# Named constants
PPT_ANGLE_FACTOR = 60_000       # degrees → 60000ths of a degree
PPT_OPACITY_FACTOR = 100_000    # 0.0–1.0 → 0–100000
PPT_SCALE_FACTOR = 100_000      # 1.0 = 100% → 100000

class AnimationUnitConverter:
    """All SVG-to-PPT animation unit conversions in one place."""

    def __init__(
        self,
        slide_width_emu: int = 9_144_000,
        slide_height_emu: int = 6_858_000,
        dpi: float = 96.0,
    ):
        self._slide_w = slide_width_emu
        self._slide_h = slide_height_emu
        self._uc = UnitConverter(dpi=dpi)

    def opacity_to_ppt(self, value: float) -> int:
        """SVG 0.0–1.0 → PPT 0–100000."""
        return int(round(max(0.0, min(1.0, value)) * PPT_OPACITY_FACTOR))

    def degrees_to_ppt(self, degrees: float) -> int:
        """Degrees → PPT 60000ths of a degree."""
        return int(round(degrees * PPT_ANGLE_FACTOR))

    def px_to_emu(self, px: float, *, axis: str | None = None) -> int:
        """Pixels → EMU (integer)."""
        return int(round(self._uc.to_emu(px, axis=axis)))

    def scale_to_ppt(self, factor: float) -> int:
        """Scale factor (1.0 = 100%) → PPT 100000."""
        return int(round(factor * PPT_SCALE_FACTOR))

    def px_to_slide_fraction(self, px: float, *, axis: str) -> float:
        """Pixels → fraction of slide dimension (for motion paths)."""
        emu = self._uc.to_emu(px, axis=axis)
        dim = self._slide_w if axis in ("x", "width") else self._slide_h
        return emu / dim

    def normalize_attribute_value(self, ppt_attribute: str, raw_value: str) -> str:
        """Normalize a raw numeric value based on its PPT attribute name."""
        numeric = float(raw_value)
        if ppt_attribute in ANGLE_ATTRIBUTES:
            return str(self.degrees_to_ppt(numeric))
        axis = AXIS_MAP.get(ppt_attribute)
        return str(self.px_to_emu(numeric, axis=axis))
```

This replaces scattered conversion logic across `ValueProcessor`, `value_formatters`,
and inline handler code.

---

## 7. Testing Strategy

### 7.1 Golden Master XML Comparison

Create reference `<p:timing>` fragments from actual PowerPoint files:

1. Create animations manually in PowerPoint.
2. Extract `<p:timing>` from `ppt/slides/slide1.xml`.
3. Store as `tests/golden/animation/{test_name}.xml`.
4. Compare structurally (ignoring attribute order and whitespace).

### 7.2 Per-Handler Unit Tests

Each handler gets tests using real `AnimationDefinition` instances (no mocks):

```python
def make_opacity_animation(**overrides) -> AnimationDefinition:
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)

def test_opacity_returns_element():
    result = handler.build(make_opacity_animation(), par_id=4, behavior_id=5)
    assert isinstance(result, etree._Element)
    assert result.tag.endswith("}par")
```

### 7.3 Integration Regression

Existing tests at `tests/unit/core/test_pptx_exporter_animation.py` exercise the
full SVG→PPTX pipeline. These must continue to pass. Assertions checking for XML
substrings (`<a:animScale`, `<a:tav tm=`) remain valid since the element names and
attributes are unchanged.

### 7.4 Side-by-Side Comparison

During migration, run old and new code paths for each test input and diff the
serialized XML output (modulo whitespace and attribute order).

---

## 8. Migration Plan

### Phase 1: Infrastructure (Non-Breaking)

1. Create `AnimationUnitConverter` at `animation/unit_conversion.py` with tests.
2. Create `TimingIDAllocator` at `animation/id_allocator.py` with tests.
3. Add element-returning `build_timing_tree()` to `AnimationXMLBuilder` (alongside
   existing `build_timing_container()` that returns `str`).
4. Add `build_par_container_elem()` and `build_behavior_core_elem()` variants.

**No existing code changes. New code only.**

### Phase 2: Handler-by-Handler Migration

Migrate one handler at a time. Order (simplest → most complex):

1. **SetAnimationHandler** — simplest output structure
2. **OpacityAnimationHandler** — simple, well-defined PPT element
3. **ColorAnimationHandler** — introduces TAV list integration
4. **NumericAnimationHandler** — attribute-based dispatch
5. **MotionAnimationHandler** — path construction, slide dimension dependency
6. **TransformAnimationHandler** — multiple sub-types, most complex

For each handler:
- Write new `build()` returning `etree._Element | None`.
- Write tests with real `AnimationDefinition` instances.
- Verify integration tests still pass.

### Phase 3: Writer Cutover

1. Update `DrawingMLAnimationWriter.build()` to use `TimingIDAllocator`.
2. Switch from `list[str]` to `list[etree._Element]`.
3. Call `build_timing_tree()` instead of `build_timing_container()`.
4. Single `to_string()` at the end.
5. Remove old string-returning builder methods.

### Phase 4: Cleanup

1. Remove mock-detection methods from `base.py`.
2. Remove `ValueProcessor` methods replaced by `AnimationUnitConverter`.
3. Remove f-string indentation patterns.
4. Delete `xml_builders.py_new` (stale partial rewrite).
5. Update `docs/architecture/animation_setup.md`.

### Phase 5: Feature Gaps

After the XML rewrite is stable:

1. Multi-keyframe translate animations (section 5.1).
2. Matrix decomposition for composite transforms (section 5.2).
3. Paced calcMode for numeric values (section 5.5).
4. `additive` attribute passthrough (section 5.6).
5. `repeatCount` / `fill` correction (section 5.7).
6. Event-based begin triggers — requires IR changes (separate effort).

---

## 9. Consequences

### Positive

- **Eliminates the parse-graft cycle.** No more silent `XMLSyntaxError` swallowed by
  `continue`. Malformed output becomes a Python error, not a missing animation.
- **Single serialization point.** lxml handles all namespace declarations, attribute
  escaping, and prefix resolution consistently.
- **Real IR types in tests.** Eliminates mock-detection code and ensures handlers
  are tested against actual production data structures.
- **Centralized unit conversion.** Impossible for handlers to use inconsistent
  conversion logic.
- **Spec-correct timing tree.** Proper click group wrapping, sequential ID
  allocation, and correct `repeatCount`/`fill` handling.

### Negative

- **Breaking change for handler interface.** `build()` returns `etree._Element | None`
  instead of `str`. Internal-only — not part of the public API.
- **Large diff during migration.** Every file in the animation module is touched.
  Mitigated by incremental handler-by-handler approach.

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Integration test assertions break (whitespace) | High | Medium | Update assertions to structural XML comparison |
| ID renumbering breaks PowerPoint playback | Low | High | Test with actual PowerPoint; IDs are internal references |
| Namespace prefix changes in output | Medium | Low | `to_string()` already normalizes prefixes |

---

## 10. Open Questions

1. **Should the click group `<p:par>` be configurable?** Future work may need
   multiple click groups (for `begin="click"` animations). Initial implementation
   uses a single group.

2. **How should the `rCtr x="4306"` constant be handled?** Options: (a) keep as
   named constant with documentation, (b) derive from shape bounding box, (c) test
   if `x="0"` also works.

3. **Should `ValueProcessor` be fully merged into `AnimationUnitConverter`?** The
   parsing functions (`parse_color`, `parse_scale_pair`) are logically distinct from
   unit conversion and could remain as standalone functions in `common.conversions`.

---

## Files

### New
- `src/svg2ooxml/drawingml/animation/unit_conversion.py`
- `src/svg2ooxml/drawingml/animation/id_allocator.py`
- `tests/golden/animation/` (reference XML fragments)

### Modified (rewrite)
- `src/svg2ooxml/drawingml/animation/xml_builders.py`
- `src/svg2ooxml/drawingml/animation/handlers/base.py`
- `src/svg2ooxml/drawingml/animation/handlers/opacity.py`
- `src/svg2ooxml/drawingml/animation/handlers/color.py`
- `src/svg2ooxml/drawingml/animation/handlers/numeric.py`
- `src/svg2ooxml/drawingml/animation/handlers/transform.py`
- `src/svg2ooxml/drawingml/animation/handlers/motion.py`
- `src/svg2ooxml/drawingml/animation/handlers/set.py`
- `src/svg2ooxml/drawingml/animation/writer.py`
- `src/svg2ooxml/drawingml/animation/value_processors.py`
- `src/svg2ooxml/drawingml/animation/tav_builder.py`

### Delete
- `src/svg2ooxml/drawingml/animation/xml_builders.py_new` (stale)
