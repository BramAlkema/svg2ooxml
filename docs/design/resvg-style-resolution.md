# Resvg-Dominant Style Resolution & Baking Policy

## Summary

The current rendering pipeline mixes two parallel worlds:

1. **Resvg normalisation** expands `<use>` elements, resolves presentation attributes, and stores fully merged styles in the resvg tree.
2. **Legacy traversal helpers** (e.g. `use_expander`, StyleResolver on raw `lxml` nodes) still mutate the SVG DOM and re-derive styles, ignoring the authoritative resvg nodes.

The mismatch shows up most obviously with stroke widths on `<use>` clones, but the same pattern will recur for gradients, filters, masks, text styling, and animation transforms. Rather than fixing each symptom piecemeal, we should make resvg the single source of truth and layer a consistent “native vs. bake” decision policy on top.

This document outlines how to centralise style resolution and bake decisions without touching code yet.

---

## Current Pain Points

| Area | What Happens Today | Result |
|------|--------------------|--------|
| `<use>` handling | Resvg expands clones, but traversal also expands them again | Element lookups point to DOM clones without resvg styles, leading to defaults (width = 1.0) |
| Style extraction | `extract_style()` falls back to DOM presentation attributes when resvg node lookup fails | Fully-resolved resvg stroke/fill information is ignored |
| Baking decisions | Each subsystem invents its own fallback logic (filters vs. masks vs. animation) | Inconsistent fidelity and duplicated heuristics |
| Diagnostics | Logging varies by subsystem | Hard to explain why something was baked vs. rendered natively |

---

## Target Architecture

### 1. Resvg-Dominant Style Resolution

* Treat the resvg tree as the authoritative representation after normalisation.
* Keep a stable `element → resvg node` mapping throughout traversal (no DOM rewriting once the lookup is built).
* Update `extract_style()` to **require** a resvg node. If none exists:
  * log a structured warning (`style-runtime/missing-resvg-node`)
  * fall back to a documented policy (e.g. default stroke width) rather than silently returning 1.0
* Retire legacy helpers (`use_expander.instantiate_use_target`, CSS reapplication) when resvg mode is active.

### 2. Unified Native / Vector-Bake / Raster-Bake Policy

* Define a capability matrix (YAML or Python data) listing SVG features and their DrawingML support status.
* Introduce a small `FidelityPolicy` service that evaluates a feature + context → `{Native, VectorBake, RasterBake}`.
* Plug the policy into style extraction, animation handlers, filter processors, etc., so every path asks the same question.

### 3. Shared Baking Helpers

* `core/baking/vector.py` – apply transforms or style adjustments to geometry before export (e.g. bake shear into path data).
* `core/baking/raster.py` – snapshot nodes with resvg/tiny-skia into EMF/bitmap assets.
* Both helpers should emit audit logs (feature, decision, rationale) so reviewers can trace fidelity decisions.

---

## Implementation Plan (High-Level)

1. **Document Capabilities**
   - Draft a table mapping SVG features (shear, perspective, complex filters, blend modes, etc.) to DrawingML native equivalents.
   - Add thresholds (e.g. `max_skew_deg: 3.0` for native before bake).

2. **Stabilise Resvg Lookup**
   - Audit traversal hooks to ensure they no longer mutate the DOM after `_build_resvg_lookup` runs.
   - Add assertions/logs when `extract_style()` cannot find a resvg node for an element with an ID.

3. **Policy Service Skeleton**
   - Create `policy/fidelity.py` with a placeholder interface:
     ```python
     class FidelityDecision(Enum):
         NATIVE = "native"
         VECTOR_BAKE = "vector_bake"
         RASTER_BAKE = "raster_bake"

     def resolve(feature: FeatureSignature, context: FeatureContext) -> FidelityDecision: ...
     ```
   - Feature signature should include the resvg node, requested operation, and any thresholds already breached (e.g. shear > 5°).

4. **Refactor Style Extraction**
   - Change `extract_style()` to:
     1. Fetch the resvg node.
     2. Merge paints/strokes from the resvg node.
     3. If policy requests baking, hand off to the vector/raster baking helpers instead of returning raw styles.

5. **Roll Out Gradually**
   - Start with `<use>` stroke-width regression as the pilot case.
   - Extend to gradients, filters, masks, and animation transforms once the policy API proves solid.

---

## Open Questions

1. **Element identity without IDs** – how should we map anonymous nodes between DOM and resvg tree? (Possible answer: rely on traversal order or resvg’s path).
2. **Partial resvg adoption** – during transition, we may need a guard so legacy mode still functions until every subsystem is resvg-aware.
3. **Telemetry** – where do we surface bake decisions (logs, devtools overlay, exported PPTX metadata)?

---

## Next Steps (Non-Code)

1. Review this plan with the rendering/animation owners and agree on the capability matrix format.
2. Gather a list of current bake fallbacks across the codebase to seed the policy table.
3. Outline the telemetry requirements (what info needs to surface in logs and reports).

Once stakeholders sign off, we can start implementing the policy service and refactoring style extraction with confidence that all subsystems will converge on the same fidelity decisions.
