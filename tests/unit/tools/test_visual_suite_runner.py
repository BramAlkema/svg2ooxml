from __future__ import annotations

from pathlib import Path

import pytest

from tools.visual.stress_suite import SCENARIOS as STRESS_SCENARIOS
from tools.visual.suite_runner import _resolve_cli_output_dir, resolve_scenarios
from tools.visual.w3c_animation_suite import SCENARIOS as W3C_ANIMATION_SCENARIOS
from tools.visual.w3c_suite import SCENARIOS as W3C_SCENARIOS


def test_resolve_scenarios_preserves_declaration_order() -> None:
    scenarios = {
        "first": Path("one.svg"),
        "second": Path("two.svg"),
    }

    assert resolve_scenarios(scenarios, None) == [
        ("first", Path("one.svg")),
        ("second", Path("two.svg")),
    ]


def test_resolve_scenarios_rejects_unknown_name() -> None:
    with pytest.raises(SystemExit, match="Unknown scenario 'bogus'"):
        resolve_scenarios({"known": Path("known.svg")}, ["bogus"])


def test_stress_suite_scenarios_exist() -> None:
    missing = [name for name, path in STRESS_SCENARIOS.items() if not path.exists()]

    assert missing == []


def test_w3c_suite_scenarios_exist() -> None:
    missing = [name for name, path in W3C_SCENARIOS.items() if not path.exists()]

    assert missing == []


def test_w3c_animation_suite_scenarios_exist() -> None:
    missing = [
        name for name, path in W3C_ANIMATION_SCENARIOS.items() if not path.exists()
    ]

    assert missing == []


def test_w3c_animation_suite_excludes_interaction_and_dom_cases() -> None:
    assert W3C_ANIMATION_SCENARIOS
    assert not any(name.startswith("animate-dom-") for name in W3C_ANIMATION_SCENARIOS)
    assert not any(
        name.startswith("animate-interact-") for name in W3C_ANIMATION_SCENARIOS
    )
    assert not any(
        name.startswith("animate-script-") for name in W3C_ANIMATION_SCENARIOS
    )
    assert not any(
        name.startswith("animate-struct-") for name in W3C_ANIMATION_SCENARIOS
    )


def test_resolve_cli_output_dir_uses_powerpoint_reports_subtree() -> None:
    output_dir = _resolve_cli_output_dir(
        output=None,
        renderer_name="powerpoint",
        default_output="reports/visual/stress",
    )

    assert output_dir == Path("reports/visual/powerpoint/stress")
