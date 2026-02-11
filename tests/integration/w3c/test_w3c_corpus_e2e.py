from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.corpus.run_corpus import CorpusRunner

CORPUS_DIR = Path("tests/svg")
METADATA_PATH = Path("tests/corpus/w3c_corpus_metadata.json")


def _load_metadata(limit: int) -> dict:
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if limit > 0:
        data["decks"] = data.get("decks", [])[:limit]
    return data


@pytest.mark.integration
@pytest.mark.slow
def test_w3c_corpus_e2e(tmp_path) -> None:
    if not CORPUS_DIR.exists() or not METADATA_PATH.exists():
        pytest.skip("W3C corpus fixtures are unavailable in this checkout.")

    limit = int(os.environ.get("SVG2OOXML_W3C_E2E_LIMIT", "20"))
    timeout_s = float(os.environ.get("SVG2OOXML_W3C_E2E_TIMEOUT", "60"))
    bail = os.environ.get("SVG2OOXML_W3C_E2E_BAIL", "1") not in {"0", "false", "False"}
    workers = 1 if bail else int(os.environ.get("SVG2OOXML_W3C_E2E_WORKERS", "4"))

    metadata = _load_metadata(limit)
    metadata_path = tmp_path / "w3c_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    output_dir = tmp_path / "w3c_output"

    runner = CorpusRunner(
        corpus_dir=CORPUS_DIR,
        output_dir=output_dir,
        mode="resvg",
        metadata_file=metadata_path,
    )

    report = runner.run_all(
        workers=workers,
        buffer=max(2, workers * 2),
        timeout_s=timeout_s,
        bail=bail,
    )

    assert report.failed_decks == 0, report.summary
