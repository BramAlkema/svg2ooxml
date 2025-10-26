"""Tests for placeholder policy rules."""

from svg2ooxml.policy.rules import DEFAULT_POLICY, load_policy


def test_load_policy_returns_default_when_name_matches() -> None:
    policy = load_policy()

    assert policy is DEFAULT_POLICY
    assert policy.options["quality"] == "balanced"


def test_load_policy_returns_new_policy_for_custom_name() -> None:
    policy = load_policy("custom")

    assert policy.name == "custom"
    assert policy.options["quality"] == "custom"
