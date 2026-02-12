from __future__ import annotations

import logging

from svg2ooxml.core.parser.batch.worker import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
