"""Animation policy evaluation and skip logic.

This module determines whether animations should be skipped based on:
- Fallback mode settings
- Spline approximation errors
- Feature support flags

Policy decisions are centralized here for easier testing and maintenance.

Note: Event-based begin triggers are partially supported through begin trigger
mapping; unsupported cases are explicitly skipped with policy reasons.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from svg2ooxml.common.interpolation import BezierEasing

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["AnimationPolicy"]


class AnimationPolicy:
    """Evaluate animation policy decisions.

    This class encapsulates all policy logic for determining whether
    animations should be skipped or processed.

    Example:
        >>> policy = AnimationPolicy({"fallback_mode": "native"})
        >>> should_skip, reason = policy.should_skip(animation, max_error=0.05)
        >>> if should_skip:
        ...     print(f"Skipping: {reason}")
    """

    def __init__(self, options: Mapping[str, Any]):
        """Initialize policy with options.

        Args:
            options: Policy options including:
                - fallback_mode: "native" or other (default: "native")
                - allow_native_splines: Enable spline support (default: True)
                - max_spline_error: Max acceptable spline error (optional)
        """
        self._options = dict(options)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def should_skip(
        self,
        animation: AnimationDefinition,
        max_error: float,
    ) -> tuple[bool, str | None]:
        """Determine if animation should be skipped.

        Args:
            animation: Animation definition to evaluate
            max_error: Maximum spline approximation error (0.0 if no splines)

        Returns:
            (should_skip, reason) tuple where:
            - should_skip: True if animation should be skipped
            - reason: Skip reason string or None

        Example:
            >>> policy = AnimationPolicy({})
            >>> should_skip, reason = policy.should_skip(animation, 0.0)
        """
        skip_reason = self._policy_skip_reason(animation, max_error)
        should_skip = skip_reason is not None
        return (should_skip, skip_reason)

    def should_suppress_timing(self) -> bool:
        """Determine if timing XML generation should be suppressed.

        Timing is globally suppressed only when native timing is explicitly
        disabled via fallback mode.

        Other constraints (native splines, max spline error) are handled as
        per-fragment skip decisions in ``should_skip()``.

        Returns:
            True if timing should be suppressed, False otherwise
        """
        # Check fallback mode
        fallback_mode = str(self._options.get("fallback_mode", "native")).lower()
        if fallback_mode != "native":
            return True

        return False

    def estimate_spline_error(
        self,
        animation: AnimationDefinition,
    ) -> float:
        """Estimate maximum spline approximation error.

        Args:
            animation: Animation definition with key_splines

        Returns:
            Maximum error across all splines (0.0 if no splines)

        Example:
            >>> policy = AnimationPolicy({})
            >>> error = policy.estimate_spline_error(animation)
        """
        return self._estimate_max_error(animation)

    # ------------------------------------------------------------------ #
    # Policy Logic                                                       #
    # ------------------------------------------------------------------ #

    def _policy_skip_reason(
        self,
        animation: AnimationDefinition,
        max_error: float,
    ) -> str | None:
        """Determine skip reason based on policy.

        Args:
            animation: Animation to evaluate
            max_error: Maximum spline error

        Returns:
            Skip reason string or None if should not skip
        """
        fallback_mode = str(self._options.get("fallback_mode", "native")).lower()
        if fallback_mode != "native":
            return "fallback_mode_not_native"

        raw_animation_type = getattr(animation, "animation_type", None)
        animation_type = getattr(raw_animation_type, "value", raw_animation_type)
        if (
            animation_type == "animate"
            and getattr(animation, "target_attribute", None) == "stroke-width"
        ):
            return "dead_path_stroke_weight"

        # Unsupported begin="indefinite" has no native PowerPoint equivalent.
        begin_triggers = getattr(
            getattr(animation, "timing", None), "begin_triggers", None
        )
        if not isinstance(begin_triggers, list):
            begin_triggers = []
        for trigger in begin_triggers:
            trigger_type = getattr(
                getattr(trigger, "trigger_type", None), "value", None
            )
            if trigger_type == "indefinite":
                return "unsupported_begin_indefinite"
            if trigger_type in {"access_key", "wallclock", "event", "element_repeat"}:
                return f"unsupported_begin_{trigger_type}"
            if trigger_type in {"element_begin", "element_end"} and not getattr(
                trigger, "target_element_id", None
            ):
                return "unsupported_begin_target_missing"

        end_triggers = getattr(getattr(animation, "timing", None), "end_triggers", None)
        if not isinstance(end_triggers, list):
            end_triggers = []
        for trigger in end_triggers:
            trigger_type = getattr(
                getattr(trigger, "trigger_type", None), "value", None
            )
            if trigger_type in {
                "access_key",
                "wallclock",
                "event",
                "element_repeat",
                "indefinite",
            }:
                return f"unsupported_end_{trigger_type}"
            if trigger_type in {"element_begin", "element_end"} and not getattr(
                trigger, "target_element_id", None
            ):
                return "unsupported_end_target_missing"

        allow_native_flag = self._coerce_bool_option(
            self._options.get("allow_native_splines"),
            True,
        )
        has_splines = bool(getattr(animation, "key_splines", None))
        if not allow_native_flag and has_splines:
            return "native_splines_disabled"

        threshold_value = self._options.get("max_spline_error")
        if threshold_value is not None:
            threshold = self._coerce_float_option(threshold_value, 0.0)
            if max_error > threshold:
                return "spline_error_exceeds_threshold"

        return None

    # ------------------------------------------------------------------ #
    # Spline Error Estimation                                            #
    # ------------------------------------------------------------------ #

    def _estimate_max_error(self, animation: AnimationDefinition) -> float:
        """Estimate maximum spline error across all keyframes.

        Args:
            animation: Animation with key_splines

        Returns:
            Maximum error (0.0 if no splines)
        """
        if not animation.key_splines:
            return 0.0

        return max(
            self._estimate_spline_error(spline) for spline in animation.key_splines
        )

    def _estimate_spline_error(
        self, spline: list[float], *, samples: int = 20
    ) -> float:
        """Estimate approximation error for a single Bezier spline.

        Compares the cubic Bezier easing curve to linear interpolation
        by sampling at multiple points and finding the maximum deviation.

        Args:
            spline: Cubic Bezier control points [x1, y1, x2, y2]
            samples: Number of sample points to evaluate

        Returns:
            Maximum absolute error (0.0 if invalid spline)

        Example:
            >>> policy = AnimationPolicy({})
            >>> error = policy._estimate_spline_error([0.42, 0, 0.58, 1])
        """
        if len(spline) != 4:
            return 0.0

        max_error = 0.0
        for index in range(1, samples):
            progress = index / samples
            eased = BezierEasing.evaluate(progress, spline)
            error = abs(eased - progress)
            max_error = max(max_error, error)

        return max_error

    # ------------------------------------------------------------------ #
    # Option Coercion Helpers                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _coerce_bool_option(value: Any, default: bool) -> bool:
        """Coerce option value to boolean.

        Handles various input types:
        - bool: Return as-is
        - int/float: Convert to bool
        - str: Parse "true"/"false", "yes"/"no", "1"/"0", etc.
        - None: Return default

        Args:
            value: Option value
            default: Default if value is None or unparseable

        Returns:
            Boolean value

        Example:
            >>> AnimationPolicy._coerce_bool_option("yes", False)
            True
            >>> AnimationPolicy._coerce_bool_option(None, False)
            False
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return default

    @staticmethod
    def _coerce_float_option(value: Any, default: float) -> float:
        """Coerce option value to float.

        Args:
            value: Option value
            default: Default if value is None or unparseable

        Returns:
            Float value

        Example:
            >>> AnimationPolicy._coerce_float_option("0.05", 0.0)
            0.05
            >>> AnimationPolicy._coerce_float_option(None, 0.1)
            0.1
        """
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
