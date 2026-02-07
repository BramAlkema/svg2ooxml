"""Tests for timing_utils — paced calcMode keyTime computation."""

from __future__ import annotations

import pytest

from svg2ooxml.drawingml.animation.timing_utils import (
    compute_paced_key_times,
    compute_paced_key_times_2d,
)


class TestComputePacedKeyTimes:
    def test_equal_spacing(self):
        """Equal distances produce equal keyTimes."""
        result = compute_paced_key_times([0.0, 10.0, 20.0, 30.0])
        assert result is not None
        assert len(result) == 4
        assert result == pytest.approx([0.0, 1 / 3, 2 / 3, 1.0])

    def test_unequal_spacing(self):
        """Unequal distances produce proportional keyTimes."""
        # Distances: 10, 30 — total 40
        result = compute_paced_key_times([0.0, 10.0, 40.0])
        assert result is not None
        assert len(result) == 3
        assert result[0] == 0.0
        assert result[1] == pytest.approx(0.25)  # 10/40
        assert result[2] == 1.0

    def test_two_values(self):
        """Two values: keyTimes are [0, 1]."""
        result = compute_paced_key_times([0.0, 100.0])
        assert result is not None
        assert result == [0.0, 1.0]

    def test_fewer_than_two_returns_none(self):
        assert compute_paced_key_times([42.0]) is None
        assert compute_paced_key_times([]) is None

    def test_all_equal_returns_none(self):
        """Zero total distance: returns None (fallback to equal spacing)."""
        result = compute_paced_key_times([5.0, 5.0, 5.0])
        assert result is None

    def test_negative_values(self):
        """Distances are absolute, negative values handled correctly."""
        # Values: 10, 0, -10 — distances: 10, 10
        result = compute_paced_key_times([10.0, 0.0, -10.0])
        assert result is not None
        assert result == pytest.approx([0.0, 0.5, 1.0])

    def test_starts_at_zero_ends_at_one(self):
        result = compute_paced_key_times([0.0, 1.0, 100.0, 200.0])
        assert result is not None
        assert result[0] == 0.0
        assert result[-1] == 1.0


class TestComputePacedKeyTimes2D:
    def test_equal_distances(self):
        """Equal 2D distances produce equal keyTimes."""
        # Square path: each segment is length 10
        pairs = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        result = compute_paced_key_times_2d(pairs)
        assert result is not None
        assert len(result) == 4
        assert result == pytest.approx([0.0, 1 / 3, 2 / 3, 1.0])

    def test_unequal_distances(self):
        """Euclidean distances produce proportional keyTimes."""
        # (0,0) -> (3,4) = distance 5; (3,4) -> (3,4+12) = distance 12
        pairs = [(0.0, 0.0), (3.0, 4.0), (3.0, 16.0)]
        result = compute_paced_key_times_2d(pairs)
        assert result is not None
        assert result[0] == 0.0
        assert result[1] == pytest.approx(5.0 / 17.0)
        assert result[2] == 1.0

    def test_fewer_than_two_returns_none(self):
        assert compute_paced_key_times_2d([(0.0, 0.0)]) is None
        assert compute_paced_key_times_2d([]) is None

    def test_all_same_point_returns_none(self):
        result = compute_paced_key_times_2d([(5.0, 5.0), (5.0, 5.0), (5.0, 5.0)])
        assert result is None
