# ADR-026: Dependency Footprint and Python Version Alignment

- **Status:** Proposed
- **Date:** 2026-02-12
- **Owners:** svg2ooxml team
- **Related:** ADR-017 (resvg rendering strategy), ADR-019 (font embedding engine), ADR-024 (batch conversion performance)

## 1. Problem Statement

We need to decide which external dependencies are truly required for production
quality, which are optional, and which are test-only. The goal is a single,
repeatable runtime that avoids Python-version conflicts (notably FontForge vs
skia-python) while preserving output fidelity and validation coverage.

## 2. Context

### 2.1 What each dependency enables (current code paths)

- **skia-python**: raster fallback for shapes, gradients, and effects that cannot
  be represented natively or via resvg. See `src/svg2ooxml/drawingml/rasterizer.py`.
- **resvg** (binary or bindings): modern rendering lane for filters and
  primitives, used as a primary fallback. See `docs/resvg.md`.
- **FontForge**: WOFF/WOFF2 decoding and glyph subsetting for font embedding.
  See `src/svg2ooxml/services/fonts/` and ADR-019.
- **LibreOffice (soffice)**: visual regression testing only. See
  `tests/visual/` and `tools/visual/`.
- **OpenXML audit / validator**: correctness gate for PPTX outputs during CI
  and corpus testing. See `tests/corpus/` and `openxml-audit` integration.
- **scikit-image / Pillow / numpy**: visual diff tooling and raster processing
  in tests and render helpers.

### 2.2 Python version alignment facts (external)

- skia-python publishes wheels and declares support for Python 3.8-3.13.
- Ubuntu 22.04 (Jammy) ships Python 3.10 as the default python3 package; newer
  Python versions are available but not the system default.
- FontForge Python bindings are packaged against the system Python in each OS.
  Example: Fedora 42 packages python3-fontforge for Python 3.13, while Ubuntu
  22.04 packages target its default Python 3.10.

## 3. Decision

### 3.1 Dependency tiers

**Required for production runtime**

- **resvg**: required for modern filter handling and consistent output
  strategies.
- **skia-python**: required for raster fallback until resvg or native coverage
  closes all gaps.

**Optional (feature-dependent, not required for base runtime)**

- **FontForge**: required for WOFF2 decoding and aggressive subsetting. If
  absent, we allow direct embedding, skip WOFF2, and log a warning.
- **scikit-image / Pillow / numpy**: not required for headless production
  conversion if resvg + native paths are sufficient; required for visual tests
  and some render utilities.

**Test-only**

- **LibreOffice (soffice)**: required only for visual regression baselines.
- **OpenXML audit / validator**: required in CI and W3C corpus gating, not in
  production runtime.

### 3.2 Single-Python runtime strategy

- Target **Python 3.13** as the single runtime for the core pipeline, aligned
  with `pyproject.toml`.
- Use an OS image that ships Python 3.13 and has working FontForge bindings if
  we want FontForge in the same container.
- For Ubuntu 22.04, avoid installing FontForge bindings into the Python 3.13
  runtime; treat FontForge as optional or run it in a sidecar environment.

## 4. Rationale

- Removing skia-python would eliminate the only raster fallback, which would
  reduce output fidelity for effects not covered by native or resvg.
- Removing resvg would regress filter fidelity and go against the established
  roadmap (ADR-017).
- FontForge is valuable for WOFF2 and subsetting, but it is not required to
  produce a PPTX; graceful degradation is acceptable for environments where
  bindings are unavailable.
- LibreOffice and OpenXML audit are essential for QA and correctness, but they
  are not runtime dependencies for conversion.

## 5. Consequences

- The runtime base stays focused: resvg + skia + core Python deps.
- FontForge becomes an optional capability with explicit warnings and test skips
  when unavailable.
- CI and W3C corpus runners remain the place where LibreOffice and OpenXML audit
  are guaranteed.

## 6. Alternatives Considered

1. **Drop skia-python and rely solely on resvg**
   - Rejected: resvg does not yet cover every raster-needed case.

2. **Force FontForge into the core runtime**
   - Rejected: OS-level Python version coupling would block a 3.13-only runtime
     for Ubuntu 22.04 images.

3. **Split runtimes** (core conversion vs font tooling)
   - Viable: run font subsetting in a sidecar/container with its system Python,
     but this adds operational complexity. Kept as a fallback option.

## 7. Action Items

- Keep `requires-python = ">=3.13"` and update container guidance to favor
  a 3.13-native base image if FontForge is needed in the same container.
- Document FontForge as optional with explicit behavior when missing.
- Continue to gate OpenXML audit and visual regression in CI, not production.

## 8. References

- skia-python PyPI and release notes (Python 3.13 support, wheels)
- Ubuntu Python version availability (Jammy default Python 3.10)
- Fedora package metadata for python3-fontforge (Python 3.13 bindings)
