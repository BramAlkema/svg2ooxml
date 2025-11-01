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
   portion. Today we package the result as a bounded bitmap; future work will
   promote resvg output to EMF when we can preserve fidelity.
3. **Legacy raster fallback** – only if both native and resvg fail do we fall
   back to the original rasterisation path (skia/placeholder glyphs).</br>

Every `FilterEffectResult` contains:

- `strategy` – what path produced the DrawingML hook (`native`, `vector`,
  `resvg`, `raster`, …).
- `fallback` – the actual asset type (`emf`, `bitmap`, `placeholder`).
- `metadata` – `renderer` (resvg/skia/native), the primitives that were executed,
  and any raster attachments.

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
