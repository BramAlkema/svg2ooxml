# Resvg Rendering Strategy

The resvg port adds a modern rendering lane that runs alongside the legacy
DrawingML/EMF pipeline. The goal is to use the highest‑fidelity output available
for each effect, falling back only when a feature is still missing or blocked by
policy.

## Rendering order of preference

1. **Native DrawingML** – filter primitives that already map cleanly into the
   existing registry stay native. We keep using those whenever the registry
   succeeds so PPTX consumers can edit the effect directly.
2. **Resvg promotion** – when a primitive (or stack of primitives) cannot be
   expressed natively, we ask the resvg planner/executor to render just that
   portion. Simple vector-friendly cases – for example `feFlood` + `feComposite`,
   chains that add `feOffset` or `feMerge`, standalone `feBlend`, `feComposite`,
   `feColorMatrix`, `feComponentTransfer`, or `feConvolveMatrix` – are promoted
   straight to EMF so the effect stays editable; more complex plans fall back to
   bounded PNGs while parity work continues.
3. **Legacy raster fallback** – only if both native and resvg fail do we fall
   back to the original rasterisation path (skia/placeholder glyphs).</br>

Every `FilterEffectResult` contains:

- `strategy` – what path produced the DrawingML hook (`native`, `vector`,
  `resvg`, `raster`, …).
- `fallback` – the actual asset type (`emf`, `bitmap`, `placeholder`).
- `metadata` – `renderer` (resvg/skia/native), the primitives that were executed,
  any raster attachments, and the resvg planner summary (`plan_primitives`,
  serialised `descriptor`) captured for telemetry.

The tracer (`ConversionTracer`) records the decisions (`resvg_attempt`,
`resvg_success`, `filter_effect`, etc.) so we can audit why a particular effect
fell back.

## Controlling the renderer

### Exporter flag

`SvgToPptxExporter` accepts an optional `filter_strategy`:

```python
exporter = SvgToPptxExporter(filter_strategy="resvg")
exporter.convert_file(...)
```

Available values:

| Strategy       | Behaviour                                                               |
| -------------- | ----------------------------------------------------------------------- |
| `auto`         | Native → resvg → legacy (default).                                      |
| `resvg`        | Prefer resvg; still runs native first for primitives with known output. |
| `resvg-only`   | Force resvg; skip native/legacy fallbacks (for targeted testing).       |
| `legacy`       | Skip resvg and rely on the classic registry/raster path.                |
| `vector`, `emf`| Force vector fallbacks (used by policy sandboxes).                      |
| `raster`       | Force raster fallbacks.                                                 |

Per-primitive policy overrides can further control promotion:

- `allow_promotion` – set `false` to keep a primitive on the bitmap path even
  when an EMF promotion is available.
- `max_arithmetic_coeff` – caps absolute coefficient values for
  `feComposite(operator="arithmetic")`; exceeding the limit forces the
  pipeline back to the raster lane.
- `max_offset_distance` – bounds `feOffset` promotions by total pixel distance.
- `max_merge_inputs` – limits how many inputs `feMerge` can fold into a
  promoted chain.
- `max_component_functions` / `max_component_table_values` – cap the complexity
  of `feComponentTransfer` promotions (number of functions and table samples).
- `max_convolve_kernel` / `max_convolve_order` – restrict the kernel footprint
  for `feConvolveMatrix` before falling back to raster.

Promotion metadata records the resolved resvg descriptor plus the planner
summary (`plan_primitives`) so tracers and downstream telemetry can see the
inputs, intermediate results, and why a promotion was accepted or declined.
When a policy override or limit blocks a promotion, the tracer emits
`resvg_promotion_policy_blocked` with the primitive, violated rule, limit, and
observed value so downstream consumers can tell why the chain reverted to a
raster fallback.

Conversion summaries expose aggregated `resvg_metrics` counters (attempts,
plans, promotions, policy blocks, lighting candidates, successes, failures) so
dashboards can track adoption and hot spots directly from Firestore job
records. See `docs/telemetry/resvg_metrics.md` for ingestion examples.

The exporter also records a `filter` stage event named `strategy_configured`
whenever the explicit flag is set.

### Policy overrides

The filter policy (`policy.rules._BASE_FILTER["strategy"]`) can override the
strategy on a per-document basis. When the exporter is created with
`filter_strategy="auto"` (default), the policy value wins; otherwise the explicit
strategy remains in control.

Toggling a strategy in tests or scripts:

```python
policy_overrides = {"filter": {"strategy": "legacy"}}
result = exporter.convert_string(svg_text, output, tracer=tracer, policy_overrides=policy_overrides)
```

### Visual baselines

Set `SVG2OOXML_VISUAL_FILTER_STRATEGY=resvg` (or `legacy`) before running
`tools/visual/update_baselines.py` to refresh golden images with the desired
renderer:

```bash
export SVG2OOXML_VISUAL_FILTER_STRATEGY=resvg
python tools/visual/update_baselines.py rect_scene --soffice /path/to/soffice
```

## Tracing the pipeline

Use `ConversionTracer` to inspect filter decisions:

```python
from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer

exporter = SvgToPptxExporter(filter_strategy="resvg")
tracer = ConversionTracer()
exporter._render_svg(svg_text, tracer)  # internal helper for diagnostics

report = tracer.report()
print([event.action for event in report.stage_events if event.stage == "filter"])
print([event.decision for event in report.paint_events if event.paint_type == "filter"])
```

Expect to see:

- `resvg_attempt` / `resvg_success` when the planner executed successfully.
- `resvg_plan_characterised` summarising the primitive stack (tags, inputs,
  extra metadata) emitted before promotion/rasterisation.
- `resvg_promoted_emf` when a promotion stays vector/EMF; metadata captures the
  primitive chain and planner extras.
- `resvg_promotion_policy_blocked` when a policy override forces the stack back
  to raster (includes the violated rule and thresholds).
- `resvg_lighting_promoted` / `resvg_lighting_candidate` when lighting primitives
  enter the promotion path (prototype coverage for diffuse/specular lighting).
- `filter_effect` when legacy/native registry handled a primitive.
- `media_registered` / `geometry_rasterized` when a bitmap asset was generated.

## Roadmap

- Promote resvg-rendered surfaces to EMF where fidelity allows, so filters that
  can be expressed as vector graphics stay editable.
- Add fine-grained policy rules per primitive (e.g., force raster when
  `feSpecularLighting` exceeds a budget).
- Expand integration coverage (`tests/integration/core/test_pipeline.py`) and
  visual baselines to compare `resvg` vs `legacy` output automatically.

Until then, keep running both strategies in staging. If resvg produces a
noticeable improvement for a document, the metadata logged in the tracer report
(`plan_primitives`, `renderer`, `fallback`) should provide enough detail to
understand why.
