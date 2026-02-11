# ADR-024: Batch Conversion Performance — Streaming, Caching, Parallelism

- **Status:** Proposed
- **Date:** 2026-02-07
- **Owners:** svg2ooxml team
- **Depends on:** ADR-023 (schema validation proved the need for fast corpus re-runs)
- **Related:** ADR-015 (queue/throttle/cache — API-side, not local batch)

## 1. Problem Statement

Full W3C corpus validation (526 SVGs → 5 PPTX batches) is the primary quality gate
for schema compliance. The current pipeline has three pain points:

1. **Memory** — `convert_pages()` accumulates all `DrawingMLRenderResult` objects in
   a list. For 105 slides per batch, peak memory is 1-4 GB. For the full 526-slide
   corpus in one deck: OOM.

2. **Speed** — Every run re-renders every SVG from scratch. The validate → tweak →
   re-validate development loop takes 2-3 minutes per full corpus pass.

3. **No parallelism** — Slides are independent but rendered sequentially. Modern
   machines have 8-16 cores sitting idle.

### 1.1 Current Architecture

```
SvgToPptxExporter.convert_pages(pages)
    for page in pages:                          # Sequential
        parse_result = parser.parse(svg)        # lxml fromstring
        ir_scene = convert(parse_result)        # IR conversion
        render_result = writer.render(ir_scene) # DrawingML generation
        render_results.append(render_result)    # ← Accumulates in memory
    builder.build_from_results(render_results)  # All slides → temp dir → ZIP
```

Memory profile: O(N) where N = number of slides. No release between iterations.

### 1.2 Measured Baselines

| Batch | Slides | PPTX Size | Est. Render Time |
|-------|--------|-----------|------------------|
| aa | 106 | 237 MB | ~20-35s |
| ab | 106 | 176 MB | ~20-35s |
| ac | 106 | 155 MB | ~20-35s |
| ad | 106 | 62 MB | ~15-25s |
| ae | 102 | 160 MB | ~20-35s |
| **Total** | **526** | **790 MB** | **~2-3 min** |

## 2. Decision

Three-phase approach ordered by impact/effort ratio.

### Phase 1: Streaming Build (fixes OOM)

Refactor `convert_pages()` and `PPTXPackageBuilder` to flush each slide to the temp
directory immediately, then release the `DrawingMLRenderResult` for GC.

**Current flow:**
```
render all → collect list → build_from_results(list) → ZIP
```

**New flow:**
```
builder.begin(temp_dir)
for page in pages:
    result = render(page)
    builder.add_slide(result)  # Write XML + media to temp dir
    del result                 # Release for GC
builder.finalize()             # ZIP temp dir
```

**Changes:**
- `PPTXPackageBuilder`: Add `begin()` / `add_slide()` / `finalize()` methods
- `PackagingContext`: Track media dedup across incremental `add_slide()` calls
- `convert_pages()`: Switch from list accumulation to streaming
- Backward compat: Keep `build_from_results()` as wrapper that calls the new API

**Memory profile:** O(1) steady state — only one slide in memory at a time.
Enables arbitrary deck sizes without OOM.

**Estimated effort:** Small-medium. The temp-dir staging pattern already exists;
`build_from_results` already writes slides to temp dir individually. The refactor
is mostly about splitting the loop boundary.

### Phase 2: Slide-Level Cache (fast re-runs)

Content-addressed disk cache keyed on `hash(svg_content + source_code_fingerprint)`.

**Cache key:**
```python
import hashlib

def slide_cache_key(svg_content: str, code_version: str) -> str:
    h = hashlib.sha256()
    h.update(svg_content.encode())
    h.update(code_version.encode())
    return h.hexdigest()
```

`code_version` = git commit hash of HEAD (or hash of all files under `src/`).
Any code change invalidates the entire cache — simple and correct.

**Cache storage:**
```
.cache/svg2ooxml/slides/
    <sha256>.pickle          # Pickled DrawingMLRenderResult
    <sha256>.meta.json       # SVG path, timestamp, code version
```

**Cache integration in convert_pages():**
```python
for page in pages:
    key = slide_cache_key(page.svg, code_version)
    cached = cache.get(key)
    if cached:
        builder.add_slide(cached)
        continue
    result = render(page)
    cache.put(key, result)
    builder.add_slide(result)
```

**Performance:**
- Cold (first run): Same speed + ~5% write overhead
- Warm (re-run, no code change): ~95% faster (disk reads only, ~3-5s total)
- After code change: Full cache miss, same as cold

**Cache invalidation:** Automatic via code_version in key. No manual purging needed.
Optional `--no-cache` flag and `cache clear` CLI command.

**Estimated effort:** Small. `DrawingMLRenderResult` is a dataclass with strings,
bytes, and simple types — pickle-friendly. Main work is the cache read/write layer.

### Phase 3: Parallel Rendering (cold run speedup)

Use `multiprocessing.Pool` to render slides in parallel. Each slide is independent
(no shared mutable state between renders).

**Architecture:**
```python
from multiprocessing import Pool

def render_slide(page: SvgPageSource) -> DrawingMLRenderResult:
    parser = SVGParser()
    writer = DrawingMLWriter()
    parse_result = parser.parse(page.svg)
    ir_scene = convert(parse_result)
    return writer.render(ir_scene)

with Pool(processes=cpu_count()) as pool:
    for result in pool.imap(render_slide, pages):
        builder.add_slide(result)  # Streaming add
```

**Considerations:**
- `DrawingMLWriter` must be instantiable per-worker (no shared state) — already true
- Template files read once per worker process (8 copies, ~40KB total — negligible)
- Results serialized via pickle across process boundary (~cost of cache write)
- `imap` preserves slide order while allowing parallel execution

**Expected speedup:**
- 8 cores → ~4-6x (overhead from process spawn + IPC serialization)
- 526 slides: ~2-3 min → ~30-45s cold

**Compatibility with streaming:** `pool.imap()` yields results in order → feeds
directly into `builder.add_slide()`. Streaming + parallel compose naturally.

**Compatibility with cache:** Check cache before submitting to pool. Only uncached
slides go through the pool. Warm cache bypasses parallelism entirely (not needed).

**Estimated effort:** Medium. Main risk is ensuring all per-slide state is
process-safe (no module-level mutable globals). Need to audit `ConversionServices`
and `PolicyEngine` for shared state.

## 3. Phase 4: lxml Micro-Optimizations

Lower-priority optimizations for the hot path. Implement after Phases 1-3
deliver the architectural wins.

### 3A. Fix _clone_element() roundtrip

**File:** `src/svg2ooxml/drawingml/bridges/resvg_paint_bridge.py:545`

```python
# Current — serialize + re-parse roundtrip
def _clone_element(node):
    return etree.fromstring(etree.tostring(node))

# Fix — use deepcopy (lxml supports it natively)
from copy import deepcopy
def _clone_element(node):
    return deepcopy(node)
```

**Impact:** ~5% on gradient-heavy SVGs. Zero risk — `deepcopy` is the documented
lxml cloning mechanism.

### 3B. Reduce graft_xml_fragment() roundtrips

**File:** `src/svg2ooxml/drawingml/xml_builder.py:161`

`graft_xml_fragment()` parses XML strings that were often just serialized from
lxml elements. Five call sites in filters/mappers. Two approaches:

- **Option A:** Pass lxml elements through the filter pipeline instead of strings.
  Large refactor — filters currently return XML strings.
- **Option B:** Cache parsed fragments by content hash. Small change, avoids
  re-parsing identical fragments across slides.

Recommend **Option B** for Phase 4, **Option A** as future architectural cleanup
(see ADR-021).

### 3C. paint_to_fill() element-based returns

**Files:** `paint_runtime.py`, `shapes_runtime.py`

Currently 19 `to_string()` calls per render — each paint/stroke/effect returns a
serialized XML string. Converting to element-based returns would eliminate these
serializations and defer to a single `to_string()` at the slide level.

**Impact:** ~8-10% overall, but requires significant refactoring of the shape
template system (currently string `.format()` based).

**Recommendation:** Defer to ADR-021 (eliminate string-parse-graft). The template
system and paint returns should be migrated together.

## 4. Predicted Performance

| Scenario | Time | Memory | Phase |
|----------|------|--------|-------|
| **Today** | ~2-3 min | 1-4 GB peak | — |
| Streaming only | ~2-3 min | ~100 MB steady | 1 |
| Streaming + cache (warm) | ~3-5s | ~100 MB steady | 1+2 |
| Streaming + parallel (8c) | ~30-45s | ~100 MB steady | 1+3 |
| All three (cold) | ~30-45s | ~100 MB steady | 1+2+3 |
| All three (warm) | ~3-5s | ~100 MB steady | 1+2+3 |
| + lxml fixes (cold) | ~25-40s | ~100 MB steady | 1+2+3+4 |

## 5. Implementation Order

| Phase | Errors Fixed | Effort | Depends On |
|-------|-------------|--------|------------|
| Phase 1: Streaming | OOM fix | Small-medium | None |
| Phase 2: Cache | Fast re-runs | Small | Phase 1 (streaming add_slide API) |
| Phase 3: Parallel | Cold speedup | Medium | Phase 1 (streaming) |
| Phase 4: lxml | Micro gains | Small (3A,3B) / Large (3C) | None |

Phase 4A (`_clone_element` fix) can land independently at any time.

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pickle compatibility of DrawingMLRenderResult | Cache/parallel broken | Add `__getstate__`/`__setstate__` if needed |
| Module-level mutable state in workers | Race conditions in parallel | Audit ConversionServices, PolicyEngine |
| Cache staleness after dependency change | Stale validation results | Include pip freeze hash in cache key |
| Large cache directory growth | Disk usage | LRU eviction, configurable max size |
| Streaming breaks existing build_from_results callers | API regression | Keep wrapper method, add deprecation warning |

## 7. Non-Goals

- Production API performance (covered by ADR-015)
- Visual regression pipeline speed (separate concern)
- Cloud Run autoscaling (GCP infrastructure deleted)
