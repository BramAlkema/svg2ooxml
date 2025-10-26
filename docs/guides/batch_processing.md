## Batch Processing Quickstart

svg2ooxml now generates real PPTX artifacts for parser batch jobs. The batch
helpers consume the parser, IR converter, DrawingML writer, and PPTX packager,
using the `assets/pptx_templates/` library as the single source of truth for
static OOXML parts.

### Running the regression tests

```
pytest tests/unit/parser/batch/test_tasks.py
pytest tests/unit/io/test_adapters.py -k pptx
```

These tests ensure we emit a slide package, populate the expected DrawingML, and
exercise the richer gradient/pattern/image processors via the unit suite.

### Huey remains optional

Huey is still guarded behind a `try/except` import in `parser.batch`. When Huey
is not installed the tasks run inline and log a message, so local development
does not require the queue. If you install Huey, `convert_single_svg_task`
becomes available and the batch pipeline can enqueue jobs as before.

### Output locations

Batch conversions accept an `output_path` or `output_dir` inside the
`conversion_options` dictionary. When nothing is provided the pipeline writes a
temporary file under the system temp directory using the SVG stem and a unique
suffix.
