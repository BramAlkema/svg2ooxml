"""Run the extracted figma2gslides API locally.

This wrapper keeps the app entrypoint under the app-owned surface rather than
at the repository root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from figma2gslides.app import app  # noqa: F401


if __name__ == "__main__":  # pragma: no cover - manual invocation
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("figma2gslides.app:app", host="0.0.0.0", port=port, log_level="info")
