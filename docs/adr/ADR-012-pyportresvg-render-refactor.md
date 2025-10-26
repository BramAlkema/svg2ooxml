# ADR-012: Replace Renderer With PyPortResvg-Inspired Stack

## Status
Accepted – this ADR drives the _render refactor_ epic.

## Context
- The existing pipeline builds directly from raw XML nodes through `shape_converters` into DrawingML, with isolated modules for masks, clip paths, filters, and raster fallbacks. The code evolved feature-by-feature and now suffers from repeated geometry math, inconsistent mask policies, and limited filter coverage.
- resvg/usvg demonstrate a clean architecture: parse + normalise into a canonical tree, tessellate geometry once, render via Skia/tiny-skia, reuse the same primitives for masks, clips, filters, and final raster surfaces.
- `pyportresvg` is a Python-first port of the resvg stack (NumPy + skia-python) and proves that approach works natively. It includes:
  * Parser & normalisation layers (attribute cascade, transform flattening).
  * Tessellation (fill + stroke) and geometry helpers.
  * Rendering pipeline handling fills, strokes, filters, masks, clips, markers.
  * Surface abstraction that returns RGBA arrays suitable for packaging.
- Rather than incrementally bolting more functionality onto the current svg2ooxml modules, we will replace entire subsystems with pyportresvg-inspired equivalents, reducing technical debt and enabling cross-platform raster parity.

## Decision
Create a new `svg2ooxml.render` package that ports the pyportresvg pipeline, then progressively replace existing parser/geometry/mask/filter code to depend on it. No backward compatibility shims: the old modules will be retired once replacements land.

Key components:

1. **Normalization (`render/normalize.py`)**  
   - Parse `lxml` SVG input, resolve CSS/presentation attributes, flatten transforms, convert all shapes into canonical path primitives, and emit a `NormalizedSvgTree`.
   - Replace the ad-hoc combination of `parser/style`, `parser/clip_extractor`, and geometry approximations.

2. **Geometry & Tessellation (`render/geometry.py`)**  
   - Port pyportresvg tessellation (based on lyon) to handle fills and strokes uniformly.
   - Offers stroke outline generation, winding rule evaluation, and curve flattening for raster fallbacks.

3. **Paint & Gradient Normalization (`render/paint.py`)**  
   - Resolve paint servers, gradients, and patterns into concrete fill/stroke styles with transforms.
   - Simplifies downstream export (DrawingML & raster) by providing fully computed paint objects.

4. **Surface & Rasterizer (`render/surface.py`, `render/rasterizer.py`)**  
   - Wrap skia-python surfaces, provide drawing primitives (fill path, stroke path, image blit).
   - Expose hooks for filters, masks, markers, and direct RGBA extraction.

5. **Mask/Clip Pipeline (`render/mask_clip.py`)**  
   - Compute mask and clip alpha bitmaps via tessellator + rasterizer, with caching.
   - Provides PNG/EMF emission for fallback assets used by DrawingML writer (replacing `mask_writer` logic).

6. **Filter Planner & Executor (`render/filters.py`)**  
   - Determine filter primitive subregions, colour interpolation, and CPU-friendly rendering order.
   - Works on the normalized tree, enabling vector vs raster fallback decisions aligned with resvg.

7. **Integration Facade (`render/pipeline.py`)**  
   - High-level `render(tree: NormalizedSvgTree, *, modes=...) -> Surface` entry point.
   - Serves future CLI/preview features and internal raster fallbacks.


## Detailed Design

### Module Layout
```
src/svg2ooxml/render/
├── __init__.py
├── normalize.py      # SVG -> NormalizedSvgTree
├── geometry.py       # tessellation & path helpers
├── paint.py          # gradients/patterns normalisation
├── surface.py        # Skia surface abstraction
├── rasterizer.py     # draw operations
├── mask_clip.py      # masks & clips rasterisation
├── filters.py        # filter planning/rendering
├── pipeline.py       # render entry point & context orchestration
└── types.py          # shared dataclasses/enums
```

### Normalization Skeleton (`normalize.py`)
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

@dataclass(slots=True)
class NormalizedNode:
    tag: str
    transform: np.ndarray
    geometry: object | None
    fill: object | None
    stroke: object | None
    clip_href: str | None
    mask_href: str | None
    filter_href: str | None
    children: list["NormalizedNode"] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedSvgTree:
    root: NormalizedNode
    viewport_width: float
    viewport_height: float
    definitions: dict[str, NormalizedNode] = field(default_factory=dict)


def normalize_svg(svg_root) -> NormalizedSvgTree:
    """Convert an lxml SVG element into a normalized node tree.

    Tasks:
      - Resolve presentation attributes & CSS cascades.
      - Flatten transforms into node-local geometry.
      - Convert rect/circle/ellipse/line/poly* into path primitives.
      - Extract definitions (gradients, masks, patterns, filters) keyed by ID.
    """
    raise NotImplementedError("Wire in parser cascade + normalization here.")
```

### Geometry & Tessellation Skeleton (`geometry.py`)
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

@dataclass(slots=True)
class TessellationResult:
    contours: Sequence[np.ndarray]            # Nx2 float arrays
    winding_rule: str                         # 'nonzero'/'evenodd'
    stroke_outline: Sequence[np.ndarray] | None = None


class Tessellator:
    """Lyon-inspired tessellator (port from pyportresvg)."""

    def tessellate_fill(self, geometry) -> TessellationResult:
        raise NotImplementedError

    def tessellate_stroke(self, geometry, stroke_style) -> TessellationResult:
        raise NotImplementedError
```

### Paint Normalisation Skeleton (`paint.py`)
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

@dataclass(slots=True)
class SolidPaint:
    color: tuple[float, float, float]
    opacity: float


@dataclass(slots=True)
class LinearGradient:
    stops: Sequence[tuple[float, tuple[float, float, float], float]]
    start: tuple[float, float]
    end: tuple[float, float]
    transform: np.ndarray

# RadialGradient, PatternPaint, etc…

def resolve_fill(node, tree) -> object | None:
    """Return a concrete paint object for the node's fill (Solid/Gradient/Pattern)."""
    raise NotImplementedError
```

### Surface & Rasterizer Skeleton (`surface.py`, `rasterizer.py`)
```python
# surface.py
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import skia

@dataclass(slots=True)
class Surface:
    _surface: skia.Surface
    width: int
    height: int
    scale: float = 1.0

    @classmethod
    def make(cls, width: int, height: int, *, scale: float = 1.0) -> "Surface":
        surface = skia.Surface(int(width * scale), int(height * scale))
        return cls(surface, width, height, scale=scale)

    def canvas(self) -> skia.Canvas:
        return self._surface.getCanvas()

    def snapshot_rgba(self) -> np.ndarray:
        image = self._surface.makeImageSnapshot()
        return np.frombuffer(image.tobytes(), dtype=np.uint8).reshape((self.height, self.width, 4))
```

```python
# rasterizer.py
from __future__ import annotations

from dataclasses import dataclass

import skia

from .geometry import TessellationResult
from .surface import Surface

@dataclass(slots=True)
class Viewport:
    width: int
    height: int

    @classmethod
    def from_normalized_tree(cls, tree) -> "Viewport":
        return cls(int(tree.viewport_width), int(tree.viewport_height))


class Rasterizer:
    def draw_fill(self, surface: Surface, tess: TessellationResult, paint: skia.Paint) -> None:
        path = build_skia_path(tess)
        surface.canvas().drawPath(path, paint)

    def draw_stroke(self, surface: Surface, tess: TessellationResult, paint: skia.Paint) -> None:
        path = build_skia_path(tess)
        surface.canvas().drawPath(path, paint)

def build_skia_path(tess: TessellationResult) -> skia.Path:
    raise NotImplementedError
```

### Mask & Clip Skeleton (`mask_clip.py`)
```python
from __future__ import annotations

import numpy as np

from .geometry import Tessellator
from .rasterizer import Rasterizer, Viewport
from .surface import Surface

def rasterize_mask(node, tree, *, tessellator: Tessellator, rasterizer: Rasterizer, viewport: Viewport) -> np.ndarray:
    """Return an alpha mask (float32 array)."""
    raise NotImplementedError

def rasterize_clip(node, tree, *, tessellator: Tessellator, rasterizer: Rasterizer, viewport: Viewport) -> np.ndarray:
    raise NotImplementedError

def export_mask_png(alpha: np.ndarray) -> bytes:
    """Encode alpha channel as PNG bytes."""
    raise NotImplementedError
```

### Filter Planner Skeleton (`filters.py`)
```python
from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class FilterPlan:
    primitives: list
    bounding_box: tuple[float, float, float, float]

def plan_filter(node) -> FilterPlan | None:
    raise NotImplementedError

def apply_filter(surface, plan: FilterPlan):
    raise NotImplementedError
```

### Pipeline Skeleton (`pipeline.py`)
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .normalize import NormalizedSvgTree
from .geometry import Tessellator
from .paint import resolve_fill, resolve_stroke
from .rasterizer import Rasterizer, Viewport
from .surface import Surface

@dataclass(slots=True)
class RenderContext:
    tessellator: Tessellator
    rasterizer: Rasterizer


def render(tree: NormalizedSvgTree, context: Optional[RenderContext] = None) -> Surface:
    viewport = Viewport.from_normalized_tree(tree)
    surface = Surface.make(viewport.width, viewport.height)
    context = context or RenderContext(tessellator=Tessellator(), rasterizer=Rasterizer())
    # Walk the tree, calling tessellator/rasterizer for fills/strokes/masks/filters.
    raise NotImplementedError
```

## Replacement Strategy

1. **Bootstrap render package** with skeletons (above). Existing modules continue to work until we fill in implementations.
2. **Normalise & adapt converters**
   - Port normalisation logic (pyportresvg/usvg) and update `IRConverter` to consume `NormalizedSvgTree` instead of raw lxml nodes where feasible (start with masks/clips to minimise blast radius).
3. **Replace geometry & raster operations**
   - Swap manual segment builders in converters and rasterizer for `render.geometry.Tessellator`.
   - Replace `drawingml/rasterizer.py` with `render.rasterizer.Surface`.
4. **Mask/Clip integration**
   - Rewire `drawingml/mask_writer.py` to call `render.mask_clip`, removing bespoke EMF/PNG paths.
5. **Filter planner adoption**
   - Implement `render.filters` and update policy/raster fallbacks to rely on real filter complexity.
6. **Cleanup**
   - Delete superseded modules (`mask_generator`, old tessellation helpers, bespoke rasterizers) after verifying parity.

## Consequences
- **Positive**
  - Single rendering pipeline shared across masks, clips, filters, and fallback rasterisation.
  - Cleaner parser interface (normalized tree) reduces duplicate transform/presentation logic.
  - Anchor for future features (visual preview, resvg parity) with well-defined modules.
- **Negative**
  - New dependencies on skia-python and NumPy in the core path.
  - Large refactor touches critical converter code; we must have solid regression coverage (unit + integration + visual).
  - Learning curve for contributors shifting from ad-hoc geometry code to tessellator/pipeline abstractions.

## References
- pyportresvg repository (`src/pyportresvg/*`)
- resvg/usvg source for normalisation and filter planning
- svg2ooxml issues: mask fallback ladder, filter parity, raster fallback fidelity.
