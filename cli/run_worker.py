
from __future__ import annotations

import logging
from svg2ooxml.api.background import worker

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    worker.main()
