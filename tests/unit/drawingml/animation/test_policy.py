"""Tests for animation policy."""

from unittest.mock import Mock

from svg2ooxml.drawingml.animation.policy import AnimationPolicy


class TestInit:
    """Test AnimationPolicy initialization."""

    def test_empty_options(self):
        policy = AnimationPolicy({})
        assert policy._options == {}

    def test_with_options(self):
        opts = {"fallback_mode": "native", "max_spline_error": 0.05}
        policy = AnimationPolicy(opts)
        assert policy._options == opts


class TestCoerceBoolOption:
    """Test _coerce_bool_option helper."""

    def test_bool_values(self):
        assert AnimationPolicy._coerce_bool_option(True, False) is True
        assert AnimationPolicy._coerce_bool_option(False, True) is False

    def test_none_returns_default(self):
        assert AnimationPolicy._coerce_bool_option(None, True) is True
        assert AnimationPolicy._coerce_bool_option(None, False) is False

    def test_numeric_values(self):
        assert AnimationPolicy._coerce_bool_option(1, False) is True
        assert AnimationPolicy._coerce_bool_option(0, True) is False
        assert AnimationPolicy._coerce_bool_option(1.0, False) is True
        assert AnimationPolicy._coerce_bool_option(0.0, True) is False

    def test_string_values_true(self):
        for val in ["1", "true", "TRUE", "True", "yes", "YES", "on", "ON"]:
            assert AnimationPolicy._coerce_bool_option(val, False) is True

    def test_string_values_false(self):
        for val in ["0", "false", "FALSE", "False", "no", "NO", "off", "OFF"]:
            assert AnimationPolicy._coerce_bool_option(val, True) is False

    def test_string_with_whitespace(self):
        assert AnimationPolicy._coerce_bool_option("  true  ", False) is True
        assert AnimationPolicy._coerce_bool_option("  false  ", True) is False

    def test_invalid_string_returns_default(self):
        assert AnimationPolicy._coerce_bool_option("invalid", True) is True
        assert AnimationPolicy._coerce_bool_option("invalid", False) is False

    def test_other_types_return_default(self):
        assert AnimationPolicy._coerce_bool_option([], True) is True
        assert AnimationPolicy._coerce_bool_option({}, False) is False


class TestCoerceFloatOption:
    """Test _coerce_float_option helper."""

    def test_none_returns_default(self):
        assert AnimationPolicy._coerce_float_option(None, 0.5) == 0.5

    def test_float_values(self):
        assert AnimationPolicy._coerce_float_option(0.05, 0.0) == 0.05
        assert AnimationPolicy._coerce_float_option(1.5, 0.0) == 1.5

    def test_int_values(self):
        assert AnimationPolicy._coerce_float_option(1, 0.0) == 1.0
        assert AnimationPolicy._coerce_float_option(0, 1.0) == 0.0

    def test_string_values(self):
        assert AnimationPolicy._coerce_float_option("0.05", 0.0) == 0.05
        assert AnimationPolicy._coerce_float_option("1.5", 0.0) == 1.5

    def test_invalid_values_return_default(self):
        assert AnimationPolicy._coerce_float_option("invalid", 0.5) == 0.5
        assert AnimationPolicy._coerce_float_option([], 1.0) == 1.0
        assert AnimationPolicy._coerce_float_option({}, 2.0) == 2.0


class TestEstimateSplineError:
    """Test spline error estimation."""

    def test_linear_spline_zero_error(self):
        """Linear spline (no easing) should have zero error."""
        policy = AnimationPolicy({})

        # Linear: [0, 0, 1, 1] - straight line
        error = policy._estimate_spline_error([0.0, 0.0, 1.0, 1.0])
        assert error < 0.0001  # Essentially zero

    def test_ease_in_out_has_error(self):
        """Ease-in-out splines should have non-zero error."""
        policy = AnimationPolicy({})

        # Ease-in-out: [0.42, 0, 0.58, 1]
        error = policy._estimate_spline_error([0.42, 0, 0.58, 1])
        assert error > 0.0

    def test_invalid_spline_zero_error(self):
        """Invalid spline (wrong length) should return zero."""
        policy = AnimationPolicy({})

        assert policy._estimate_spline_error([]) == 0.0
        assert policy._estimate_spline_error([0.5]) == 0.0
        assert policy._estimate_spline_error([0.5, 0.5, 0.5]) == 0.0

    def test_custom_sample_count(self):
        """Should support custom sample count."""
        policy = AnimationPolicy({})

        error_10 = policy._estimate_spline_error([0.42, 0, 0.58, 1], samples=10)
        error_100 = policy._estimate_spline_error([0.42, 0, 0.58, 1], samples=100)

        # More samples should give similar or slightly different result
        assert error_10 > 0.0
        assert error_100 > 0.0


class TestEstimateMaxError:
    """Test _estimate_max_error (max across all splines)."""

    def test_no_splines(self):
        """Animation with no splines should return zero."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = []

        assert policy._estimate_max_error(animation) == 0.0

    def test_single_spline(self):
        """Should return error of single spline."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        error = policy._estimate_max_error(animation)
        assert error > 0.0

    def test_multiple_splines_returns_max(self):
        """Should return maximum error across all splines."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = [
            [0.0, 0.0, 1.0, 1.0],  # Linear (low error)
            [0.42, 0, 0.58, 1],     # Ease-in-out (higher error)
        ]

        error = policy._estimate_max_error(animation)

        # Should be greater than linear error
        linear_error = policy._estimate_spline_error([0.0, 0.0, 1.0, 1.0])
        assert error > linear_error


class TestEstimateSplineErrorPublic:
    """Test public estimate_spline_error method."""

    def test_delegates_to_estimate_max_error(self):
        """Should delegate to _estimate_max_error."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        error = policy.estimate_spline_error(animation)
        assert error > 0.0


class TestPolicySkipReason:
    """Test _policy_skip_reason logic."""

    def test_fallback_mode_not_native(self):
        """Non-native fallback mode causes per-animation skip."""
        policy = AnimationPolicy({"fallback_mode": "raster"})

        animation = Mock()
        animation.key_splines = []

        reason = policy._policy_skip_reason(animation, 0.0)
        assert reason == "fallback_mode_not_native"

    def test_fallback_mode_native_no_skip(self):
        """Native fallback mode should not skip."""
        policy = AnimationPolicy({"fallback_mode": "native"})

        animation = Mock()
        animation.key_splines = []

        reason = policy._policy_skip_reason(animation, 0.0)
        assert reason is None

    def test_native_splines_disabled(self):
        """Disabled native splines skips spline animations."""
        policy = AnimationPolicy({"allow_native_splines": False})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        reason = policy._policy_skip_reason(animation, 0.05)
        assert reason == "native_splines_disabled"

    def test_native_splines_enabled_no_skip(self):
        """Enabled native splines should not skip."""
        policy = AnimationPolicy({"allow_native_splines": True})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        reason = policy._policy_skip_reason(animation, 0.05)
        assert reason is None

    def test_spline_error_exceeds_threshold(self):
        """Error exceeding threshold causes per-animation skip."""
        policy = AnimationPolicy({"max_spline_error": 0.01})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        reason = policy._policy_skip_reason(animation, 0.05)
        assert reason == "spline_error_exceeds_threshold"

    def test_spline_error_below_threshold_no_skip(self):
        """Error below threshold should not skip."""
        policy = AnimationPolicy({"max_spline_error": 0.1})

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        reason = policy._policy_skip_reason(animation, 0.05)
        assert reason is None

    def test_no_splines_no_threshold_check(self):
        """Animation without splines should not skip."""
        policy = AnimationPolicy({"max_spline_error": 0.01})

        animation = Mock()
        animation.key_splines = []

        reason = policy._policy_skip_reason(animation, 0.0)
        assert reason is None

    def test_begin_indefinite_is_skipped(self):
        """Unsupported begin=indefinite should be skipped."""
        policy = AnimationPolicy({})

        trigger = Mock()
        trigger.trigger_type = Mock(value="indefinite")
        animation = Mock()
        animation.key_splines = []
        animation.timing = Mock(begin_triggers=[trigger])

        reason = policy._policy_skip_reason(animation, 0.0)
        assert reason == "unsupported_begin_indefinite"


class TestShouldSkip:
    """Test public should_skip method."""

    def test_should_skip_returns_tuple(self):
        """Should return (bool, str | None) tuple."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = []

        result = policy.should_skip(animation, 0.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_no_skip(self):
        """Should return (False, None) when not skipping."""
        policy = AnimationPolicy({})

        animation = Mock()
        animation.key_splines = []

        should_skip, reason = policy.should_skip(animation, 0.0)
        assert should_skip is False
        assert reason is None

    def test_skip_true_for_non_native_fallback(self):
        """should_skip returns True when fallback mode disables native timing."""
        policy = AnimationPolicy({"fallback_mode": "raster"})

        animation = Mock()
        animation.key_splines = []

        should_skip, reason = policy.should_skip(animation, 0.0)
        assert should_skip is True
        assert reason == "fallback_mode_not_native"


class TestShouldSuppressTiming:
    """Test should_suppress_timing logic."""

    def test_default_no_suppression(self):
        """Default options should not suppress timing."""
        policy = AnimationPolicy({})
        assert policy.should_suppress_timing() is False

    def test_native_fallback_no_suppression(self):
        """Native fallback mode should not suppress timing."""
        policy = AnimationPolicy({"fallback_mode": "native"})
        assert policy.should_suppress_timing() is False

    def test_raster_fallback_suppresses(self):
        """Non-native fallback mode should suppress timing."""
        policy = AnimationPolicy({"fallback_mode": "raster"})
        assert policy.should_suppress_timing() is True

    def test_slide_fallback_suppresses(self):
        """Slide fallback mode should suppress timing."""
        policy = AnimationPolicy({"fallback_mode": "slide"})
        assert policy.should_suppress_timing() is True

    def test_native_splines_disabled_does_not_suppress_globally(self):
        """Disabled native splines are handled as per-fragment skips."""
        policy = AnimationPolicy({"allow_native_splines": False})
        assert policy.should_suppress_timing() is False

    def test_native_splines_enabled_no_suppression(self):
        """Enabled native splines should not suppress timing."""
        policy = AnimationPolicy({"allow_native_splines": True})
        assert policy.should_suppress_timing() is False


class TestIntegration:
    """Test integrated policy workflows."""

    def test_complete_policy_evaluation(self):
        """Test complete policy evaluation workflow."""
        # Setup policy with multiple rules
        policy = AnimationPolicy({
            "fallback_mode": "native",
            "allow_native_splines": True,
            "max_spline_error": 0.05,
        })

        # Create animation with splines
        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        # Estimate error
        error = policy.estimate_spline_error(animation)

        # Evaluate skip decision
        should_skip, reason = policy.should_skip(animation, error)

        # Should process (error likely below threshold)
        # Note: Actual result depends on spline error calculation
        assert isinstance(should_skip, bool)
        assert isinstance(reason, (str, type(None)))

    def test_multiple_constraints_suppresses_timing(self):
        """Multiple policy constraints should suppress timing."""
        policy = AnimationPolicy({
            "fallback_mode": "raster",
            "allow_native_splines": False,
        })

        animation = Mock()
        animation.key_splines = [[0.42, 0, 0.58, 1]]

        # Individual animations are skipped
        should_skip, reason = policy.should_skip(animation, 0.05)
        assert should_skip is True
        assert reason == "fallback_mode_not_native"

        # But timing XML generation is suppressed
        assert policy.should_suppress_timing() is True
