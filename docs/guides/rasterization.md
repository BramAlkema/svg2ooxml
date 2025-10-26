# Rasterization Fallbacks

The DrawingML writer now supports bitmap fallbacks powered by
[`skia-python`](https://pypi.org/project/skia-python/). When policy metadata
marks a shape or filter with `suggest_fallback` set to `bitmap`/`rasterize`, the
writer uses Skia to render the IR element to a PNG and embeds it via the normal
picture template.

## Installing the optional stack

```
pip install -e .[render]
```

The `render` extra pulls in `skia-python` and `Pillow`. If Skia isn’t available
the writer falls back to vector output (and logs a warning), keeping the port
usable on minimal environments.

## What is supported?

- Solid fills and strokes for `Rectangle`, `Circle`, `Ellipse`, and `Path`
- Stroke width, join/cap, and dash arrays
- Clip paths and masks are preserved at the picture layer after rasterization

Gradients, patterns, and group-level rasterization will still fall back to the
vector pipeline for now.

## Policy integration

Rendering decisions continue to flow from the policy engine. The writer looks at
`metadata.policy.geometry.suggest_fallback` and only rasterizes when instructed.
The resulting media asset is added to the render result so packaging logic can
include the generated PNG.
