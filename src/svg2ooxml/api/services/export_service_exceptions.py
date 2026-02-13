"""Exceptions used by export service modules."""

from __future__ import annotations


class JobNotFoundError(Exception):
    """Raised when a job ID is not found in Firestore."""


__all__ = ["JobNotFoundError"]
