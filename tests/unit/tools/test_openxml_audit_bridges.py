from __future__ import annotations

import pytest
from tools.ppt_research import (
    powerpoint_oracle,
    powerpoint_oracle_starter_deck,
    powerpoint_timing_oracle_deck,
    pptx_lab,
)


def _required_attr(module, name: str):
    try:
        return getattr(module, name)
    except ModuleNotFoundError as exc:
        pytest.skip(str(exc))


def test_pptx_lab_bridge_exposes_compare() -> None:
    assert callable(_required_attr(pptx_lab, "compare_pptx_packages"))


def test_powerpoint_oracle_bridge_exposes_normalizer() -> None:
    assert callable(_required_attr(powerpoint_oracle, "_normalize_timing_tree"))


def test_powerpoint_oracle_starter_deck_bridge_exposes_builder() -> None:
    assert callable(
        _required_attr(
            powerpoint_oracle_starter_deck,
            "build_oracle_starter_deck",
        )
    )


def test_powerpoint_timing_oracle_deck_bridge_exposes_builder() -> None:
    assert callable(
        _required_attr(
            powerpoint_timing_oracle_deck,
            "build_timing_oracle_deck",
        )
    )
