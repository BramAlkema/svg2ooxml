# Z-Order Preservation Specification

**Status:** Draft
**Date:** 2026-03-24
**Context:** Gallardo SVG shows some shapes layered in wrong order. The DrawingML writer flattens all IR Group hierarchies into a flat `<p:spTree>` without `<p:grpSp>` nesting. While the flattening itself preserves order within each group, the overall z-order can diverge from the SVG document order.

## 1. Problem

SVG renders elements in document order (later elements on top). The conversion pipeline preserves this through:
- SVG parse → element tree (document order)
- IR conversion → IRScene with Group/Path hierarchy (preserves tree order)
- DrawingML writer → flat `spTree` (recursively flattens groups)

The flattening in `_render_elements()` (writer.py:337) is order-preserving for direct children. But z-order issues arise when:

1. **Bitmap fallback shapes** are emitted as `<p:pic>` elements that may land at different z-positions than the original shape would have
2. **GroupNode expansion** in `_convert_resvg_children` creates shapes from `<use>` clones that may interleave with shapes from different groups
3. **EMF fallback shapes** replace native shapes but may have different z-ordering within their group

## 2. Current Architecture

```
IR Scene:
  Group (layer6)        → children flattened into spTree positions 0-2
    Path A
    Path B
    Path C
  Group (layer3)        → children flattened into spTree positions 3-114
    Path D
    Group (sub)          → children flattened inline
      Path E
      Path F
    Path G
```

Result in spTree: A, B, C, D, E, F, G — correct order.

But if Path E triggers bitmap fallback, it becomes a `<p:pic>` that may have a different shape ID, affecting interleaving.

## 3. Root Causes to Investigate

### 3.1. _convert_resvg_children interleaving
When a `<use>` element expands to a GroupNode with children, `_convert_resvg_children` creates shapes that are returned as a flat list to `_convert_via_resvg`. These shapes then become children of an IR Group. The Group's children should be in the same order as the resvg tree's children — but is this guaranteed?

### 3.2. Bitmap fallback z-position
When a shape falls back to EMF/bitmap, it's replaced by an Image IR node. This Image is emitted as `<p:pic>` at the same position in the spTree as the original shape would have been. This should be z-order correct.

### 3.3. Group opacity rasterization
When a group is rasterized (overlapping children + opacity), it replaces the entire group with a single `<p:pic>`. This preserves z-order since the pic takes the group's position.

## 4. Possible Fix: Emit `<p:grpSp>` for SVG groups

Instead of flattening all groups, emit `<p:grpSp>` elements in the spTree for IR Groups that have children. This would:
- Preserve the SVG group hierarchy in the PPTX
- Maintain correct z-ordering automatically
- Enable group-level transforms, clip paths, and masks in PowerPoint

Drawback: PowerPoint handles `<p:grpSp>` differently from flat shapes — some features may not work correctly when nested.

## 5. Simpler Fix: Verify flat order

Add a post-processing step that verifies the flat spTree order matches the IR scene's depth-first traversal order. If any shape is out of position, log a warning.

## 6. Exit Criteria

- Gallardo SVG renders with correct front-to-back layering
- No shape appears in front of shapes that should be on top of it
- Test with overlapping shapes at different z-levels
