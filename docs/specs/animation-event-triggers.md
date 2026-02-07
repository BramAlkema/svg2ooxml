# Animation Event-Based Begin Triggers

**Status:** Future work
**Related:** `docs/adr/ADR-020-animation-writer-rewrite.md` (Section 5.4)

## Current State

`AnimationTiming.begin` (`src/svg2ooxml/ir/animation.py:51`) is a `float` representing seconds. Only time-based delays are supported:

```python
@dataclass
class AnimationTiming:
    begin: float = 0.0   # seconds from slide load
    duration: float = 1.0
    ...
```

This means SVG animations like `begin="click"`, `begin="rect1.end"`, or `begin="rect1.end+0.5s"` are either silently dropped during IR construction or treated as `begin=0`.

## SVG Begin Value Syntax

Per the SVG/SMIL specification, `begin` accepts a semicolon-separated list of:

| SVG syntax | Meaning |
|---|---|
| `0s`, `2s`, `500ms` | Time offset from document/slide start |
| `indefinite` | Only starts via scripting (no PowerPoint equivalent) |
| `click` | On click of the animated element |
| `rect1.click` | On click of element `rect1` |
| `rect1.begin` | When `rect1`'s animation begins |
| `rect1.end` | When `rect1`'s animation ends |
| `rect1.end+0.5s` | When `rect1`'s animation ends, plus 500ms |
| `rect1.begin-1s` | 1 second before `rect1`'s animation begins |

## PowerPoint `<p:cond>` Mapping

PowerPoint uses `<p:cond>` elements inside `<p:stCondLst>` to express triggers:

### Time-based (already supported)

```xml
<p:stCondLst>
  <p:cond delay="2000"/>  <!-- 2 seconds -->
</p:stCondLst>
```

### Click on animated element

SVG: `begin="click"`

```xml
<p:stCondLst>
  <p:cond evt="onClick" delay="0">
    <p:tgtEl>
      <p:spTgt spid="{shape_id}"/>
    </p:tgtEl>
  </p:cond>
</p:stCondLst>
```

### Click on another element

SVG: `begin="rect1.click"`

```xml
<p:stCondLst>
  <p:cond evt="onClick" delay="0">
    <p:tgtEl>
      <p:spTgt spid="{rect1_shape_id}"/>
    </p:tgtEl>
  </p:cond>
</p:stCondLst>
```

### After another animation ends

SVG: `begin="rect1.end"` or `begin="rect1.end+500ms"`

```xml
<p:stCondLst>
  <p:cond evt="onEnd" delay="500">
    <p:tgtEl>
      <p:spTgt spid="{rect1_shape_id}"/>
    </p:tgtEl>
  </p:cond>
</p:stCondLst>
```

### After another animation begins

SVG: `begin="rect1.begin"`

```xml
<p:stCondLst>
  <p:cond evt="onBegin" delay="0">
    <p:tgtEl>
      <p:spTgt spid="{rect1_shape_id}"/>
    </p:tgtEl>
  </p:cond>
</p:stCondLst>
```

## Required IR Changes

### 1. Replace `begin: float` with a rich type

```python
@dataclass
class BeginTrigger:
    """Represents an SVG begin trigger."""
    trigger_type: BeginTriggerType  # TIME, CLICK, ELEMENT_BEGIN, ELEMENT_END
    delay_seconds: float = 0.0
    target_element_id: str | None = None  # for element-relative triggers

class BeginTriggerType(Enum):
    TIME = "time"
    CLICK = "click"
    ELEMENT_BEGIN = "element_begin"
    ELEMENT_END = "element_end"
```

### 2. Update `AnimationTiming`

```python
@dataclass
class AnimationTiming:
    begin: float | BeginTrigger | list[BeginTrigger] = 0.0
    # ... rest unchanged
```

Backward compatibility: `float` values still work as time-based delays.

### 3. SVG parser changes

The SVG animation parser needs to:

1. Parse `begin` attribute values with the full SMIL syntax
2. Split on `;` for multiple begin conditions
3. Recognize event references (`click`, `id.begin`, `id.end`)
4. Extract offset values (`+0.5s`, `-1s`)
5. Resolve element IDs to shape IDs using the element-to-shape mapping

Location: `src/svg2ooxml/core/ir/` (SVG-to-IR conversion)

### 4. Writer changes

`build_behavior_core_elem()` in `xml_builders.py` currently hardcodes:

```python
st_cond_lst = p_sub(cTn, "stCondLst")
p_sub(st_cond_lst, "cond", delay="0")
```

This needs to dispatch based on trigger type to generate the appropriate `<p:cond>` structure.

### 5. Timing tree changes

Event-triggered animations may need different `nodeType` values or placement in the timing tree. Click-triggered animations typically go in separate click groups rather than the auto-play group.

## Limitations

- `begin="indefinite"` has no PowerPoint equivalent (requires JS scripting)
- Multiple begin conditions (semicolon-separated) map to multiple `<p:cond>` elements but PowerPoint behavior may differ from SVG
- Negative offsets (`begin="rect1.end-1s"`) require careful handling when the referenced animation hasn't started yet

## Implementation Priority

This should be implemented after the core animation writer rewrite is complete and stable. The suggested order:

1. Parse `begin` values in SVG parser (IR enrichment)
2. Add `BeginTrigger` type to IR
3. Update `build_behavior_core_elem()` to handle triggers
4. Update timing tree builder for click groups
5. Add integration tests with multi-animation SVGs
