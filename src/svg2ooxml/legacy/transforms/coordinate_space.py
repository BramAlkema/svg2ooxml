"""Current-transformation-matrix stack utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .matrix import Matrix


def _as_matrix(value: Matrix | Iterable[float] | None) -> Matrix:
    if value is None:
        return Matrix.identity()
    if isinstance(value, Matrix):
        return value
    values = list(value)
    if len(values) != 6:
        raise ValueError("Iterable transform must contain 6 values")
    return Matrix.from_values(*values)


@dataclass(slots=True)
class CoordinateSpace:
    """Maintain a CTM stack while traversing the SVG DOM."""

    _stack: list[Matrix] = field(default_factory=lambda: [Matrix.identity()])

    # ------------------------------------------------------------------ #
    # Stack operations                                                   #
    # ------------------------------------------------------------------ #

    def push(self, transform: Matrix | Iterable[float] | None) -> None:
        """Push a new transform on the stack."""
        current = self._stack[-1]
        composed = current.multiply(_as_matrix(transform))
        self._stack.append(composed)

    def push_absolute(self, transform: Matrix | Iterable[float]) -> None:
        """Push a transform without composing with the current CTM."""
        self._stack.append(_as_matrix(transform))

    def pop(self) -> None:
        """Pop the most recent transform, keeping the base viewport intact."""
        if len(self._stack) <= 1:
            raise ValueError("Cannot pop the root viewport transform")
        self._stack.pop()

    def reset(self) -> None:
        """Reset the stack back to the viewport transform."""
        if len(self._stack) > 1:
            root = self._stack[0]
            self._stack = [root]

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #

    @property
    def current(self) -> Matrix:
        return self._stack[-1]

    @property
    def depth(self) -> int:
        return len(self._stack)

    def is_identity(self) -> bool:
        return self.current.is_identity()

    # ------------------------------------------------------------------ #
    # Application helpers                                                #
    # ------------------------------------------------------------------ #

    def apply_point(self, x: float, y: float) -> tuple[float, float]:
        return self.current.transform_point(x, y)

    def apply_points(self, points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
        return self.current.transform_points(points)

    def iter(self) -> Iterator[Matrix]:
        return iter(self._stack)


__all__ = ["CoordinateSpace"]
