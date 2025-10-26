# File Structure Overview

This project keeps a flat, easy to scan layout so every package stays small.

```
src/
  svg2ooxml/
    __init__.py          # package version
    animations/          # SMIL and keyframe conversion stubs
    batch/
      jobs/              # task definitions and orchestration
    clip/
      strategies/        # clipping strategy placeholders
    color/
      palettes/          # shared palette registration helpers
    common/              # shared types and utilities
    compat/              # compatibility adapters for legacy quirks
    core/                # orchestration entry points (converter stubs live here)
    css/                 # CSS parsing and cascading helpers
    drawingml/           # OOXML-specific writers
    elements/            # IR element factories
    filters/
      effects/           # filter mapping placeholders
    fonts/               # font discovery, embedding
    geometry/
      algorithms/        # geometry algorithms (SAT, intersections)
      clip/              # reusable clip helpers
      fractional/        # fractional EMU math
      paths/             # path parsing and normalization helpers
    io/
      api/               # HTTP/Bulk IO helpers
    ir/                  # intermediate representation models
    map/                 # SVG → DrawingML mapping entry points
    multipage/           # multi-slide splitting logic
    paint/
      fills/             # fill paint helpers
      strokes/           # stroke paint helpers
    performance/
      profiling/         # profiling hooks and timers
      metrics/           # metrics emission stubs
      cache/             # cache inspection helpers
    parser/
      colors/            # color parsing helpers
      geometry/          # matrix parsing and transform helpers
      references.py      # namespace + external reference helpers
      result.py          # parser result carrier
      svg_parser.py      # high-level SVG parser entry point
      units/             # unit conversion and viewBox helpers
      validators/        # structural validators
      xml/               # enhanced XML builder helpers
    pipeline/
      policies/          # policy registration scaffolding
      stages/            # pipeline stage definitions
    policy/              # reusable policy rules
      engine.py          # policy engine placeholder
      targets.py         # policy target definitions
    preprocessing/       # sanitizers and heuristics
    presentation/
      templates/         # PPTX template helpers
    services/
      providers/         # service provider placeholders
      registry/          # service locator stubs
      cache.py           # performance cache helpers
      conversion.py      # conversion service container stub
      setup.py           # service wiring hook
    text/
      layout/            # layout helpers
    transforms/
      decomposition/     # transform decomposition helpers
    units/
      converters/        # extended unit converters outside parser
    viewbox/
      strategies/        # viewBox strategy helpers
    api/
      routes/            # REST route placeholders
      models/            # API models
      services/          # API service layer
cli/
  commands/              # CLI command entry points
testing/
  fixtures/              # migrated test fixtures
  golden/                # golden outputs from svg2pptx
  visual/baseline/       # visual comparison baselines
tests/
  unit/                  # fast checks that mirror src/
    __init__.py
    core/test_pipeline.py
  integration/           # placeholder for multi-module tests
    __init__.py
  visual/                # visual regression harness
    __init__.py
    golden/.gitkeep
assets/.gitkeep          # sample SVGs or PPTX fixtures
examples/.gitkeep        # runnable demos
tools/.gitkeep           # developer scripts
tools/color_palette_report.py  # palette analysis helper using advanced colour engine
docs/guides/rasterization.md    # notes on Skia-powered raster fallbacks
reports/.gitkeep         # coverage and HTML reports
```

Keep modules short; split by behavior only when a file grows beyond a few focused functions. The placeholder files are meant to be replaced gradually—update this map when new modules appear so contributors always know where logic lives.
