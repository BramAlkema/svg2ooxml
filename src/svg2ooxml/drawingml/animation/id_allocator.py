"""Pre-allocated ID generation for PowerPoint timing trees.

IDs are allocated top-down before building the XML tree so that the root
``<p:cTn>`` always gets id=1, mainSeq gets id=2, and animation elements
receive ascending IDs after the structural nodes — matching PowerPoint's
own output and the expectations of the ECMA-376 spec.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AnimationIDs",
    "TimingIDs",
    "TimingIDAllocator",
]


@dataclass(frozen=True, slots=True)
class AnimationIDs:
    """ID pair for a single animation element."""

    par: int
    behavior: int


@dataclass(frozen=True, slots=True)
class TimingIDs:
    """Complete set of IDs for a timing tree."""

    root: int
    main_seq: int
    click_group: int
    animations: list[AnimationIDs]


class TimingIDAllocator:
    """Allocate sequential IDs for a complete timing tree.

    Usage::

        allocator = TimingIDAllocator()
        ids = allocator.allocate(n_animations=3)
        # ids.root == 1, ids.main_seq == 2, ids.click_group == 3
        # ids.animations == [(4,5), (6,7), (8,9)]
    """

    def allocate(self, n_animations: int) -> TimingIDs:
        """Pre-allocate all IDs for *n_animations* in one pass."""
        counter = 0

        def next_id() -> int:
            nonlocal counter
            counter += 1
            return counter

        return TimingIDs(
            root=next_id(),
            main_seq=next_id(),
            click_group=next_id(),
            animations=[
                AnimationIDs(par=next_id(), behavior=next_id())
                for _ in range(n_animations)
            ],
        )
