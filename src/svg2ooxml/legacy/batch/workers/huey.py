"""Placeholder for Huey batch worker."""

from __future__ import annotations


def start_worker(*_args, **_kwargs) -> None:
    raise NotImplementedError("Batch worker not ported yet.")


__all__ = ["start_worker"]
