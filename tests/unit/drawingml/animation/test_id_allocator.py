"""Tests for TimingIDAllocator."""

from __future__ import annotations

import pytest

from svg2ooxml.drawingml.animation.id_allocator import (
    AnimationIDs,
    TimingIDAllocator,
    TimingIDs,
)


@pytest.fixture
def allocator() -> TimingIDAllocator:
    return TimingIDAllocator()


class TestTimingIDAllocator:
    def test_zero_animations(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(0)
        assert ids.root == 1
        assert ids.main_seq == 2
        assert ids.click_group == 3
        assert ids.animations == []

    def test_one_animation(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(1)
        assert ids.root == 1
        assert ids.main_seq == 2
        assert ids.click_group == 3
        assert len(ids.animations) == 1
        assert ids.animations[0].par == 4
        assert ids.animations[0].behavior == 5

    def test_three_animations(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(3)
        assert ids.root == 1
        assert ids.main_seq == 2
        assert ids.click_group == 3
        assert ids.animations[0] == AnimationIDs(par=4, behavior=5)
        assert ids.animations[1] == AnimationIDs(par=6, behavior=7)
        assert ids.animations[2] == AnimationIDs(par=8, behavior=9)

    def test_ids_are_strictly_sequential(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(5)
        all_ids = [ids.root, ids.main_seq, ids.click_group]
        for anim in ids.animations:
            all_ids.extend([anim.par, anim.behavior])
        assert all_ids == list(range(1, 14))

    def test_multiple_allocations_are_independent(self):
        a = TimingIDAllocator()
        ids1 = a.allocate(2)
        ids2 = a.allocate(2)
        # Each allocation starts from 1
        assert ids1.root == ids2.root == 1

    def test_frozen_dataclass(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(1)
        with pytest.raises(AttributeError):
            ids.root = 99  # type: ignore[misc]
        with pytest.raises(AttributeError):
            ids.animations[0].par = 99  # type: ignore[misc]

    def test_timing_ids_type(self, allocator: TimingIDAllocator):
        ids = allocator.allocate(2)
        assert isinstance(ids, TimingIDs)
        assert isinstance(ids.animations[0], AnimationIDs)
