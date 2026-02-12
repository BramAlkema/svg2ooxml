"""Huey worker entrypoint for parser batch tasks."""

from __future__ import annotations

import logging

from .huey_app import huey


def main() -> None:
    consumer = huey.create_consumer()
    consumer.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
