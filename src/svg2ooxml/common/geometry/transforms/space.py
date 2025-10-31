"""CTM stack utilities backed by :class:`Matrix2D`."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .matrix import Matrix2D


def _as_matrix(value: Matrix2D | Iterable[float]) -> Matrix2D:
    if isinstance(value, Matrix2D):
        return value
    values = list(value)
    if len(values) != 6:
        raise ValueError("Iterable transform must contain 6 values")
    return Matrix2D.from_values(*values)


def _clone(matrix: Matrix2D) -> Matrix2D:
    return Matrix2D.from_values(*matrix.as_tuple())


@dataclass(slots=True)
class CoordinateSpace:
    """Maintain a CTM stack while traversing SVG content."""

    _stack: list[Matrix2D] = field(default_factory=lambda: [Matrix2D.identity()])

    # ------------------------------------------------------------------ #
    # Stack operations                                                   #
    # ------------------------------------------------------------------ #

    def push(self, transform: Matrix2D | Iterable[float] | None) -> None:
        """Compose the provided transform with the current CTM."""
        current = self._stack[-1]
        if transform is None:
            composed = _clone(current)
        else:
            composed = current.multiply(_as_matrix(transform))
        self._stack.append(composed)

    def push_absolute(self, transform: Matrix2D | Iterable[float]) -> None:
        """Push a transform without composing with the current CTM."""
        self._stack.append(_as_matrix(transform))

    def pop(self) -> None:
        """Pop the most recent transform, keeping the viewport intact."""
        if len(self._stack) <= 1:
            raise ValueError("Cannot pop the root viewport transform")
        self._stack.pop()

    def reset(self) -> None:
        """Reset the stack to its initial viewport transform."""
        if len(self._stack) > 1:
            root = self._stack[0]
            self._stack = [_clone(root)]

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #

    @property
    def current(self) -> Matrix2D:
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
        return self.current.transform_xy(x, y)

    def apply_points(self, points: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
        return [self.apply_point(x, y) for x, y in points]

    def iter(self) -> Iterator[Matrix2D]:
        return iter(self._stack)


__all__ = ["CoordinateSpace"]
