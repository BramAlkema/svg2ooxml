"""Adapter to convert resvg gradient structures to IR paint objects.

This module bridges resvg's gradient representation (LinearGradient, RadialGradient
from src/svg2ooxml/core/resvg/painting/gradients.py) to the IR paint objects
(LinearGradientPaint, RadialGradientPaint from src/svg2ooxml/ir/paint.py) that
can then be converted to DrawingML using paint_runtime.py.

⚠️  **IMPORTANT**: Transform matrices are APPLIED (baked into coordinates) by this adapter!
The IR transform field is set to None since coordinates are already transformed.

❌ **KNOWN LIMITATION**: Radial gradients with non-uniform scale/skew transforms will render
incorrectly because:
  - Non-uniform scale (e.g., scale(2,1)) turns circles into ellipses
  - DrawingML radial gradients only support circular footprints
  - Current implementation computes single radius value (circle) not ellipse axes
  - Result: Stretched/skewed gradients will have wrong shape

📝 **See docs/tasks/resvg-transform-limitations.md** for:
  - Detailed analysis of non-uniform transform failures
  - Detection strategy for problematic transforms
  - Telemetry impact of transform=None
  - Follow-up tasks for gradient units/spread methods

Usage:
    from svg2ooxml.core.resvg.painting.gradients import LinearGradient
    from svg2ooxml.drawingml.bridges.resvg_gradient_adapter import (
        linear_gradient_to_paint,
        radial_gradient_to_paint,
    )
    from svg2ooxml.drawingml.paint_runtime import linear_gradient_to_fill

    # Convert resvg gradient to IR paint (transforms baked in)
    paint = linear_gradient_to_paint(resvg_gradient)

    # Convert IR paint to DrawingML XML
    drawingml = linear_gradient_to_fill(paint)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.gradients import LinearGradient, RadialGradient
    from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint, GradientStop

logger = logging.getLogger(__name__)


# ============================================================================
# Transform Classification (Phase 1: Detection & Telemetry)
# ============================================================================


@dataclass(frozen=True)
class TransformClass:
    """Classification of a 2D affine transform's linear part.

    Uses singular value decomposition to analyze transform properties:
    - non_uniform: Whether x-scale differs from y-scale
    - has_shear: Whether transform contains skew/shear
    - det_sign: -1 (reflection), 0 (degenerate), +1 (normal)
    - s1, s2: Singular values (principal stretch factors)
    - ratio: Anisotropy ratio (s1/s2), indicates how non-uniform the transform is

    Example:
        >>> cls = classify_linear(2.0, 0.0, 0.0, 2.0)  # Uniform 2x scale
        >>> assert not cls.non_uniform
        >>> assert cls.ratio == pytest.approx(1.0)

        >>> cls = classify_linear(2.0, 0.0, 0.0, 1.0)  # Non-uniform scale
        >>> assert cls.non_uniform
        >>> assert cls.ratio == pytest.approx(2.0)
    """
    non_uniform: bool      # True if x-scale != y-scale
    has_shear: bool        # True if transform has shear/skew
    det_sign: int          # -1 (reflection), 0 (degenerate), +1 (normal)
    s1: float              # Larger singular value (max stretch)
    s2: float              # Smaller singular value (min stretch)
    ratio: float           # s1/s2 (anisotropy ratio)


def classify_linear(a: float, b: float, c: float, d: float, eps: float = 1e-6) -> TransformClass:
    """Classify 2D linear transform using singular value analysis.

    Given 2x2 matrix [[a, c], [b, d]], computes:
    - Singular values s1, s2 (principal stretch factors)
    - Anisotropy ratio (how much it deviates from uniform scale)
    - Shear detection (does it skew?)
    - Determinant sign (reflection detection)

    Math: For 2×2 matrix J = [[a, c], [b, d]], singular values are eigenvalues of J^T J:
    λ± = √((A+C ± √((A+C)² - 4det²)) / 2)
    where A = a²+b², B = ac+bd, C = c²+d², det = ad-bc

    Args:
        a, b, c, d: Matrix elements [[a, c], [b, d]]
        eps: Numerical tolerance for comparisons

    Returns:
        TransformClass with classification results

    Example:
        >>> # Identity
        >>> cls = classify_linear(1.0, 0.0, 0.0, 1.0)
        >>> assert not cls.non_uniform and not cls.has_shear

        >>> # Uniform scale
        >>> cls = classify_linear(2.0, 0.0, 0.0, 2.0)
        >>> assert not cls.non_uniform

        >>> # Non-uniform scale
        >>> cls = classify_linear(2.0, 0.0, 0.0, 1.0)
        >>> assert cls.non_uniform and cls.ratio == pytest.approx(2.0)

        >>> # Rotation (uniform, no shear)
        >>> import math
        >>> c = math.cos(math.radians(45))
        >>> s = math.sin(math.radians(45))
        >>> cls = classify_linear(c, s, -s, c)
        >>> assert not cls.non_uniform and not cls.has_shear

        >>> # Skew (has shear)
        >>> cls = classify_linear(1.0, 0.0, 0.577, 1.0)  # skewX(30°)
        >>> assert cls.has_shear
    """
    # Compute eigenvalues of J^T J (squared singular values)
    # J^T J = [[a² + b², ac + bd], [ac + bd, c² + d²]]
    A = a*a + b*b
    B = a*c + b*d
    C = c*c + d*d
    trace = A + C
    detJ = a*d - b*c
    disc_sq = max(trace*trace - 4.0*(detJ*detJ), 0.0)
    sqrt_disc = disc_sq**0.5

    # Eigenvalues of J^T J
    lam_plus = 0.5*(trace + sqrt_disc)
    lam_minus = 0.5*(trace - sqrt_disc)

    # Singular values (square roots of eigenvalues)
    s1 = lam_plus**0.5 if lam_plus > 0 else 0.0
    s2 = lam_minus**0.5 if lam_minus > 0 else 0.0

    # Ensure s1 >= s2
    if s2 > s1:
        s1, s2 = s2, s1

    # Anisotropy ratio (avoid division by zero)
    ratio = max(s1, s2) / max(min(s1, s2), eps)

    # Shear detection: B (off-diagonal correlation) should be ~0 for pure scale+rotation
    has_shear = abs(B) > eps * (A + C + 1.0)

    # Determinant sign (reflection detection)
    det_sign = -1 if detJ < -eps else (1 if detJ > eps else 0)

    # Non-uniform if singular values differ significantly
    non_uniform = abs(s1 - s2) > eps * max(s1, s2, 1.0)

    return TransformClass(non_uniform, has_shear, det_sign, s1, s2, ratio)


def decide_radial_policy(a: float, b: float, c: float, d: float, mild_ratio: float = 1.02) -> tuple[str, TransformClass]:
    """Decide how to handle a radial gradient transform.

    Args:
        a, b, c, d: Matrix elements [[a, c], [b, d]]
        mild_ratio: Threshold for "mild anisotropy" (default 1.02 = 2% deviation)

    Returns:
        tuple[str, TransformClass]: ("policy_name", classification)

    Policies:
        - "vector_ok": Uniform scale/rotation, render as circle (perfect)
        - "vector_warn_mild_anisotropy": Slightly non-uniform (ratio ≤ mild_ratio),
          render as circle but emit warning in telemetry (acceptable approximation)
        - "rasterize_nonuniform": Significant non-uniformity or shear,
          fall back to rasterized gradient texture (preserves accuracy)

    Example:
        >>> # Uniform scale → vector_ok
        >>> policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 2.0)
        >>> assert policy == "vector_ok"

        >>> # Mild anisotropy → warn
        >>> policy, cls = decide_radial_policy(1.015, 0.0, 0.0, 1.0, mild_ratio=1.02)
        >>> assert policy == "vector_warn_mild_anisotropy"

        >>> # Severe anisotropy → rasterize
        >>> policy, cls = decide_radial_policy(2.0, 0.0, 0.0, 1.0)
        >>> assert policy == "rasterize_nonuniform"

        >>> # Skew → rasterize
        >>> policy, cls = decide_radial_policy(1.0, 0.0, 0.577, 1.0)  # skewX(30°)
        >>> assert policy == "rasterize_nonuniform"
    """
    cls = classify_linear(a, b, c, d)

    # Tier 0: Uniform scale + rotation → perfect circle
    if not cls.non_uniform:
        return "vector_ok", cls

    # Tier 1: Mild anisotropy, no shear → acceptable approximation
    if cls.ratio <= mild_ratio and not cls.has_shear:
        return "vector_warn_mild_anisotropy", cls

    # Tier 2: Significant non-uniformity or shear → rasterize
    return "rasterize_nonuniform", cls


# ============================================================================
# Gradient Conversion Functions
# ============================================================================


def linear_gradient_to_paint(gradient: "LinearGradient") -> "LinearGradientPaint":
    """Convert resvg LinearGradient to IR LinearGradientPaint.

    Args:
        gradient: Resvg LinearGradient with x1, y1, x2, y2, stops, etc.

    Returns:
        IR LinearGradientPaint compatible with paint_runtime.linear_gradient_to_fill()

    ⚠️  IMPORTANT LIMITATIONS:
        - **Stop offsets**: Clamped to [0, 1]. Resvg can emit values outside this range
          for repeated gradients, but DrawingML requires [0, 100000] (normalized).
        - **Transform matrices**: ✅ NOW APPLIED! Transforms are baked into the start/end
          coordinates before creating the IR object. The IR transform field is set to None
          since the coordinates are already transformed. This avoids needing paint_runtime
          to handle transforms.
          ⚠️  **Telemetry impact**: Setting transform=None loses information about whether
          gradient originally had a transform. See docs/tasks/resvg-transform-limitations.md
        - **Spread method**: ✅ NOW PRESERVED! Phase 4 adds spread_method field to IR.
          Values: "pad", "reflect", "repeat". Note: DrawingML may not support reflect/repeat,
          so paint_runtime may need fallback strategies for non-pad spread methods.
        - **Units**: ✅ NOW PRESERVED! Phase 4 adds gradient_units field to IR.
          Values: "userSpaceOnUse" or "objectBoundingBox". Note: Coordinates are already
          transformed, but this field is preserved for telemetry and future use.
        - **Gradient inheritance (href)**: Not resolved. If gradient references another via href,
          caller must resolve the chain before conversion.
    """
    from svg2ooxml.ir.paint import LinearGradientPaint, GradientStop as IRGradientStop

    # Convert stops with clamped offsets
    ir_stops = [
        IRGradientStop(
            offset=_clamp(stop.offset, 0.0, 1.0),  # Clamp to valid DrawingML range
            rgb=_color_to_hex(stop.color),
            opacity=stop.color.a,
        )
        for stop in gradient.stops
    ]

    # Ensure at least 2 stops (IR requirement)
    if len(ir_stops) < 2:
        # Add default stops if missing
        if len(ir_stops) == 0:
            ir_stops = [
                IRGradientStop(offset=0.0, rgb="000000", opacity=1.0),
                IRGradientStop(offset=1.0, rgb="FFFFFF", opacity=1.0),
            ]
        elif len(ir_stops) == 1:
            # Duplicate the single stop
            ir_stops.append(ir_stops[0])

    # Normalize gradient ID (None if empty/missing)
    grad_id = gradient.href if gradient.href and gradient.href.strip() else None

    # Apply transform to gradient coordinates (if present)
    # This bakes the transform into the coordinates, so paint_runtime doesn't need to handle it
    start = _apply_matrix_to_point(gradient.x1, gradient.y1, gradient.transform)
    end = _apply_matrix_to_point(gradient.x2, gradient.y2, gradient.transform)

    return LinearGradientPaint(
        stops=ir_stops,
        start=start,
        end=end,
        transform=None,  # Transform already applied to coordinates
        gradient_id=grad_id,
        # Phase 4: Preserve units and spread method
        gradient_units=gradient.units,
        spread_method=gradient.spread_method,
    )


def _calculate_raster_size(s1: float, s2: float, oversample: float = 2.0, min_size: int = 64, max_size: int = 4096) -> int:
    """Calculate optimal raster size for gradient texture.

    Args:
        s1: Larger singular value (max stretch factor)
        s2: Smaller singular value (min stretch factor)
        oversample: Oversampling factor for quality (default 2.0)
        min_size: Minimum texture size in pixels (default 64)
        max_size: Maximum texture size in pixels (default 4096)

    Returns:
        Clamped raster size in pixels

    Example:
        >>> # Uniform 2x scale
        >>> _calculate_raster_size(2.0, 2.0)
        64  # clamped to min

        >>> # Large non-uniform scale
        >>> _calculate_raster_size(1000.0, 500.0)
        4096  # clamped to max

        >>> # Moderate scale
        >>> _calculate_raster_size(50.0, 25.0)
        100  # ceil(50 * 2.0)
    """
    import math
    # Use max singular value (maximum stretch)
    max_stretch = max(s1, s2)
    # Calculate size with oversampling
    size = math.ceil(max_stretch * oversample)
    # Clamp to valid range
    return max(min_size, min(size, max_size))


def radial_gradient_to_paint(gradient: "RadialGradient") -> "RadialGradientPaint":
    """Convert resvg RadialGradient to IR RadialGradientPaint.

    Args:
        gradient: Resvg RadialGradient with cx, cy, r, fx, fy, stops, etc.

    Returns:
        IR RadialGradientPaint compatible with paint_runtime.radial_gradient_to_fill()

    ⚠️  IMPORTANT LIMITATIONS:
        - **Stop offsets**: Clamped to [0, 1]. Resvg can emit values outside this range
          for repeated gradients, but DrawingML requires [0, 100000] (normalized).
        - **Transform matrices**: ✅ NOW APPLIED! Transforms are baked into the center/radius/
          focal_point coordinates before creating the IR object. The radius is scaled by measuring
          the transformed distance from center to edge. The IR transform field is set to None
          since the coordinates are already transformed.
          ⚠️  **CRITICAL**: This approach ONLY works correctly for:
            - Translation (shifts circle)
            - Uniform scale (scales circle uniformly)
            - Rotation (rotates circle)
          ❌ **FAILS for non-uniform transforms**:
            - Non-uniform scale (e.g., scale(2,1)) turns circle into ellipse
            - Skew (e.g., skewX(30)) turns circle into ellipse
            - DrawingML radial gradients only support circular footprints, not ellipses!
            - Result: Incorrect gradient rendering for skewed/stretched shapes
          📝 See docs/tasks/resvg-transform-limitations.md for details and detection strategy
          ⚠️  **Telemetry impact**: Setting transform=None loses information about whether
          gradient originally had a transform.
        - **Spread method**: ✅ NOW PRESERVED! Phase 4 adds spread_method field to IR.
          Values: "pad", "reflect", "repeat". Note: DrawingML may not support reflect/repeat,
          so paint_runtime may need fallback strategies for non-pad spread methods.
        - **Units**: ✅ NOW PRESERVED! Phase 4 adds gradient_units field to IR.
          Values: "userSpaceOnUse" or "objectBoundingBox". Note: Coordinates are already
          transformed, but this field is preserved for telemetry and future use.
        - **Gradient inheritance (href)**: Not resolved. If gradient references another via href,
          caller must resolve the chain before conversion.
        - **Focal point (fx, fy)**: Transformed along with center. May have limited DrawingML support.
    """
    from svg2ooxml.ir.paint import RadialGradientPaint, GradientStop as IRGradientStop

    # Convert stops with clamped offsets
    ir_stops = [
        IRGradientStop(
            offset=_clamp(stop.offset, 0.0, 1.0),  # Clamp to valid DrawingML range
            rgb=_color_to_hex(stop.color),
            opacity=stop.color.a,
        )
        for stop in gradient.stops
    ]

    # Ensure at least 2 stops (IR requirement)
    if len(ir_stops) < 2:
        if len(ir_stops) == 0:
            ir_stops = [
                IRGradientStop(offset=0.0, rgb="000000", opacity=1.0),
                IRGradientStop(offset=1.0, rgb="FFFFFF", opacity=1.0),
            ]
        elif len(ir_stops) == 1:
            ir_stops.append(ir_stops[0])

    # Phase 1: Classify transform for telemetry and policy decisions
    transform_class = None
    policy_decision = None
    had_transform = gradient.transform is not None

    if had_transform:
        # Classify the transform using SVD analysis
        policy_decision, transform_class = decide_radial_policy(
            gradient.transform.a,
            gradient.transform.b,
            gradient.transform.c,
            gradient.transform.d,
        )

        # Phase 2: Emit warnings/trace logs based on policy decision
        if policy_decision == "vector_warn_mild_anisotropy":
            # Mild anisotropy: log warning with details
            logger.debug(
                "Radial gradient has mild anisotropy (ratio=%.3f): "
                "Rendering as circle (approximate). "
                "Transform: [[%.3f, %.3f], [%.3f, %.3f]], "
                "Singular values: s1=%.3f, s2=%.3f, "
                "Gradient ID: %s",
                transform_class.ratio,
                gradient.transform.a, gradient.transform.c,
                gradient.transform.b, gradient.transform.d,
                transform_class.s1, transform_class.s2,
                gradient.href or "(none)",
            )
        elif policy_decision == "rasterize_nonuniform":
            # Phase 3: Severe non-uniformity or shear → approximate with solid fill.
            # DrawingML radial gradients cannot represent anisotropic transforms,
            # so we fall back to an average stop color to avoid distortions.
            raster_size = _calculate_raster_size(transform_class.s1, transform_class.s2)

            # Compute average color from gradient stops as a crude approximation.
            total_r, total_g, total_b, total_a = 0.0, 0.0, 0.0, 0.0
            for stop in gradient.stops:
                total_r += stop.color.r
                total_g += stop.color.g
                total_b += stop.color.b
                total_a += stop.color.a
            count = len(gradient.stops)
            avg_r = int(total_r / count)
            avg_g = int(total_g / count)
            avg_b = int(total_b / count)
            avg_opacity = total_a / count

            avg_rgb = f"{avg_r:02X}{avg_g:02X}{avg_b:02X}"
            reason = "shear" if transform_class.has_shear else f"non-uniform scale (ratio={transform_class.ratio:.3f})"
            logger.info(
                "Radial gradient has %s: "
                "solid color fallback (avg of %d stops). "
                "Transform: [[%.3f, %.3f], [%.3f, %.3f]], "
                "Singular values: s1=%.3f, s2=%.3f, "
                "Raster size would be: %dpx, "
                "Gradient ID: %s",
                reason,
                count,
                gradient.transform.a, gradient.transform.c,
                gradient.transform.b, gradient.transform.d,
                transform_class.s1, transform_class.s2,
                raster_size,
                gradient.href or "(none)",
            )

            from svg2ooxml.ir.paint import SolidPaint
            return SolidPaint(rgb=avg_rgb, opacity=avg_opacity)

    # Apply transform to gradient coordinates (if present)
    # This bakes the transform into the coordinates, so paint_runtime doesn't need to handle it
    center = _apply_matrix_to_point(gradient.cx, gradient.cy, gradient.transform)

    # Transform radius by applying transform to a point at (cx + r, cy) and measuring distance
    import math
    if gradient.transform is not None:
        # Transform a point on the circle's edge
        edge_point = _apply_matrix_to_point(gradient.cx + gradient.r, gradient.cy, gradient.transform)
        # Calculate new radius as distance from transformed center to transformed edge
        dx = edge_point[0] - center[0]
        dy = edge_point[1] - center[1]
        radius = math.sqrt(dx * dx + dy * dy)
    else:
        radius = gradient.r

    # Use focal point if different from center, otherwise None
    focal_point = None
    if abs(gradient.fx - gradient.cx) > 1e-6 or abs(gradient.fy - gradient.cy) > 1e-6:
        focal_point = _apply_matrix_to_point(gradient.fx, gradient.fy, gradient.transform)

    # Normalize gradient ID (None if empty/missing)
    grad_id = gradient.href if gradient.href and gradient.href.strip() else None

    return RadialGradientPaint(
        stops=ir_stops,
        center=center,
        radius=radius,
        focal_point=focal_point,
        transform=None,  # Transform already applied to coordinates
        gradient_id=grad_id,
        # Phase 1: Telemetry fields
        gradient_transform=gradient.transform,  # Preserve original for telemetry
        original_transform=None,  # Shape transform (not available here, set by caller if needed)
        had_transform_flag=had_transform,
        transform_class=transform_class,
        policy_decision=policy_decision,
        # Phase 4: Preserve units and spread method
        gradient_units=gradient.units,
        spread_method=gradient.spread_method,
    )


def _apply_matrix_to_point(x: float, y: float, matrix) -> tuple[float, float]:
    """Apply resvg Matrix transform to a point.

    Args:
        x: X coordinate
        y: Y coordinate
        matrix: Resvg Matrix with a, b, c, d, e, f fields (or None)

    Returns:
        Transformed (x, y) tuple, or original coordinates if matrix is None

    Note:
        Uses SVG matrix convention:
        x' = a*x + c*y + e
        y' = b*x + d*y + f
    """
    if matrix is None:
        return (x, y)

    x_prime = matrix.a * x + matrix.c * y + matrix.e
    y_prime = matrix.b * x + matrix.d * y + matrix.f
    return (x_prime, y_prime)


def _matrix_to_numpy(matrix):
    """Convert resvg Matrix to numpy 3x3 affine transform matrix.

    Args:
        matrix: Resvg Matrix with a, b, c, d, e, f fields (or None)

    Returns:
        3x3 numpy array in standard affine form, or None if matrix is None:
        [[a, c, e],
         [b, d, f],
         [0, 0, 1]]

    Note:
        The resvg Matrix uses SVG matrix convention:
        | a  c  e |   |x|   |a*x + c*y + e|
        | b  d  f | × |y| = |b*x + d*y + f|
        | 0  0  1 |   |1|   |      1      |

    DEPRECATED: This function is no longer used for gradients.
    Transforms are now applied directly to coordinates in the adapter layer.
    Kept for potential future use with other IR objects.
    """
    if matrix is None:
        return None

    from svg2ooxml.ir.numpy_compat import np

    return np.array([
        [matrix.a, matrix.c, matrix.e],
        [matrix.b, matrix.d, matrix.f],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)


def _clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value to the given range [min_val, max_val].

    Args:
        value: Value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped value within [min_val, max_val]
    """
    return max(min_val, min(max_val, value))


def _color_to_hex(color) -> str:
    """Convert resvg Color to hex string (RRGGBB format).

    Args:
        color: Resvg Color object with r, g, b, a (0-255 range for RGB, 0-1 for alpha)

    Returns:
        Hex string in RRGGBB format (uppercase, no #)
    """
    # Resvg Color has r, g, b as floats 0-255
    r = int(max(0, min(255, color.r)))
    g = int(max(0, min(255, color.g)))
    b = int(max(0, min(255, color.b)))
    return f"{r:02X}{g:02X}{b:02X}"


__all__ = [
    "linear_gradient_to_paint",
    "radial_gradient_to_paint",
]
