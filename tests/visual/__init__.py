"""Visual regression testing tools for svg2ooxml.

This package provides utilities for visual comparison of rendered outputs,
enabling automated detection of visual regressions in PPTX generation.

Usage:
    from tools.visual.diff import VisualDiffer, DiffResult

    differ = VisualDiffer(threshold=0.95)
    result = differ.compare(baseline_image, actual_image)
    if not result.passed:
        result.save_diff("output/diff.png")
"""

__all__ = ["diff"]
