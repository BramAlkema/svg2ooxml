"""Entry point for running the Huey consumer."""

from __future__ import annotations

import logging

from .queue import huey


def main() -> None:
    consumer = huey.create_consumer()
    consumer.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
