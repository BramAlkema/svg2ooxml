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

### Queue integration

Batch helpers now live under `svg2ooxml.core.parser.batch`. They execute inline
by default so local development and regression tests do not require a queue.
Production deployments should wrap `convert_single_svg` or `process_svg_batch`
with their scheduling system (e.g., Google Cloud Tasks) when asynchronous
processing is desired.

To run a Huey worker for parser batch tasks:

```
python cli/run_batch_worker.py
```

By default this uses a SQLite-backed Huey database in the project temp
directory. To point it at Redis, set `SVG2OOXML_BATCH_REDIS_URL` (or `REDIS_URL`).

### CLI: split → stitch → audit

For a quick end-to-end run (bundle + stitch + OpenXML audit):

```
python tools/batch_run.py \
  --metadata tests/corpus/w3c_corpus_metadata.json \
  --corpus-dir tests/svg \
  --sample-size 10 \
  --sample-seed 1234 \
  --output /tmp/w3c_parallel.pptx \
  --bundle-dir /tmp/w3c_parallel_bundles \
  --openxml-validator /path/to/openxml-audit \
  --openxml-policy strict \
  --openxml-required \
  --inline
```

### Output locations

Batch conversions accept an `output_path` or `output_dir` inside the
`conversion_options` dictionary. When nothing is provided the pipeline writes a
temporary file under the system temp directory using the SVG stem and a unique
suffix.

### API parallel switches

These environment variables control whether the export API uses the parallel
batch path.

- `SVG2OOXML_PARALLEL_FORCE`: Force parallel conversion regardless of frame count.
- `SVG2OOXML_PARALLEL_ENABLE`: Enable parallel conversion (default `true`).
- `SVG2OOXML_PARALLEL_DISABLE`: Disable parallel conversion (default `false`).
- `SVG2OOXML_PARALLEL_SLIDE_THRESHOLD`: Minimum frames before parallel conversion (default `25`).
- `SVG2OOXML_PARALLEL_TIMEOUT_S`: Optional timeout for batch conversion.
- `SVG2OOXML_PARALLEL_BAIL`: Stop on first failure (default `true`).
- `SVG2OOXML_BUNDLE_DIR`: Override bundle directory for batch artifacts.
- `OPENXML_VALIDATOR`: Path to the `openxml-audit` binary.
- `OPENXML_POLICY`: OpenXML policy (default `strict`).
- `OPENXML_REQUIRED`: Require a passing OpenXML audit (default `false`).

Notes:
- `SVG2OOXML_PARALLEL_DISABLE` overrides `SVG2OOXML_PARALLEL_FORCE`.
