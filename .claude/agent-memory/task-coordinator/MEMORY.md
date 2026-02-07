# Task Coordinator Memory

## Project Context: svg2ooxml Animation Rewrite

This project involves a comprehensive rewrite of PowerPoint animation timing XML generation. Key architectural insight: the current code mixes XML paradigms (lxml + f-strings), causing fragility and bugs.

## Animation Module Structure

**Location**: `/Users/ynse/projects/svg2ooxml/src/svg2ooxml/drawingml/animation/`

**Key Files**:
- `writer.py` - Main orchestrator, initializes handlers and generates timing XML
- `xml_builders.py` - XML construction utilities (currently string-based, target: element-based)
- `handlers/` - Specialized handlers per animation type (opacity, color, transform, motion, numeric, set)
- `handlers/base.py` - Abstract base class for all handlers

**Current Handler Pattern**:
- Handlers return `str` from `build()` method
- Use f-strings with manual 40-space indentation
- Parse-and-graft cycle: wrap in temp root, parse, extract child, strip namespaces
- Mock detection code exists (lines 126-170 in base.py) due to test practices

## Migration Strategy Insights

**Why Handler-by-Handler Order Matters**:
1. SetAnimationHandler - simplest structure, fewest dependencies
2. OpacityAnimationHandler - single well-defined PPT element
3. ColorAnimationHandler - introduces TAV list complexity
4. NumericAnimationHandler - attribute-based dispatch logic
5. MotionAnimationHandler - slide dimension dependencies
6. TransformAnimationHandler - largest file (477 lines), multiple sub-types

This ordering minimizes risk and allows learning from simpler cases before tackling complex ones.

**Critical Dependencies**:
- AnimationUnitConverter + TimingIDAllocator must be created BEFORE any handler migrations
- AnimationXMLBuilder element methods must exist BEFORE handlers can use them
- ALL handlers must be migrated BEFORE writer cutover (Phase 3)
- Cleanup phases (4.x) depend on successful cutover
- Feature gaps (5.x) are independent once cutover completes

## Task Dependency Pattern

Linear progression through phases with parallelizable cleanup/features at end:

```
Phase 1: Infrastructure (tasks can run in parallel: #2, #3)
  ↓
Phase 1.3: Builder methods (#4, needs #2 and #3)
  ↓
Phase 2: Handler migrations (strict sequence: #5 → #6 → #7 → #8 → #9 → #10)
  ↓
Phase 3: Writer cutover (#11, needs all handlers done)
  ↓
Phase 4 & 5: Cleanup and features (all depend on #11, but independent of each other)
```

**Golden Master Suite** (#19) can start after builder methods exist (#4), runs in parallel with handler migrations.

## ADR Reference

Full specification: `/Users/ynse/projects/svg2ooxml/docs/adr/ADR-020-animation-writer-rewrite.md`

Key problems solved:
- String→parse→graft cycle causing silent failures
- ID allocation bug (animations numbered before root/mainSeq)
- Scattered unit conversions across handlers
- Mock-detection in production code
- Missing ECMA-376 compliant click group wrapper

## Testing Strategy

**Three Test Levels**:
1. **Unit tests per handler** - Use real `AnimationDefinition` instances, no mocks
2. **Integration tests** - Existing suite at `tests/unit/core/test_pptx_exporter_animation.py`
3. **Golden master suite** - Compare against real PowerPoint XML extracts

Integration tests use substring assertions (e.g., `"<a:animScale"`) which remain valid since element names don't change, only the generation method.
