from __future__ import annotations

from pathlib import Path

from PIL import Image
from tools.visual.w3c_proof_deck import (
    _build_montage,
    _detect_animation_duration,
    _resolve_scenarios,
    _save_apng,
    _select_sample_indices,
)


def test_select_sample_indices_spreads_evenly() -> None:
    assert _select_sample_indices(10, 4) == [0, 3, 6, 9]
    assert _select_sample_indices(3, 6) == [0, 1, 2]


def test_resolve_scenarios_applies_limit() -> None:
    scenarios = _resolve_scenarios(
        {"b": Path("b.svg"), "a": Path("a.svg"), "c": Path("c.svg")},
        requested_names=None,
        limit=2,
        animated=True,
    )
    assert [scenario.name for scenario in scenarios] == ["a", "b"]
    assert all(scenario.animated for scenario in scenarios)


def test_detect_animation_duration_uses_svg_timing_cap() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <rect id="r" x="0" y="0" width="10" height="10">
        <animate attributeName="x" from="0" to="50" dur="8s" />
      </rect>
    </svg>
    """
    assert _detect_animation_duration(
        svg,
        default_duration=4.0,
        max_duration=5.0,
    ) == 5.0


def test_build_montage_and_apng(tmp_path: Path) -> None:
    frame_paths: list[Path] = []
    for index in range(4):
        path = tmp_path / f"frame_{index:04d}.png"
        Image.new("RGB", (120, 90), color=(index * 40, 20, 100)).save(path)
        frame_paths.append(path)

    montage = _build_montage(
        frame_paths,
        tmp_path / "montage.png",
        fps=4.0,
        max_frames=4,
    )
    apng = _save_apng(frame_paths, tmp_path / "preview.apng", fps=4.0)

    assert montage.exists()
    assert apng.exists()
    with Image.open(montage) as image:
        assert image.width > 0
        assert image.height > 0
