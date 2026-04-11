from __future__ import annotations

from tools.visual.filter_stack_museum import (
    build_case_svg,
    build_manifest,
    build_stack_cases,
)


def test_stack_museum_cases_have_unique_ids() -> None:
    cases = build_stack_cases()
    assert cases
    assert len({case.case_id for case in cases}) == len(cases)
    assert all(len(case.variants) == 3 for case in cases)
    assert all(case.scene_kind for case in cases)


def test_stack_museum_svg_contains_reference_and_filters() -> None:
    case = build_stack_cases()[0]
    svg = build_case_svg(case)

    assert "Reference" in svg
    assert "url(#f1)" in svg
    assert "url(#f2)" in svg
    assert "url(#f3)" in svg
    assert "feFlood" in svg
    assert "feGaussianBlur" in svg
    assert "feMerge" in svg
    assert "fill-rule=\"evenodd\"" in svg


def test_stack_museum_uses_distinct_scene_templates() -> None:
    cases = build_stack_cases()
    svgs = {case.case_id: build_case_svg(case) for case in cases}

    assert "stroke-dasharray=\"7 6\"" in svgs["shadow_stack"]
    assert "opacity=\"0.75\"" in svgs["diffuse_lighting_composite"]
    assert "opacity=\"0.9\"" in svgs["specular_lighting_composite"]
    assert "fill=\"#FF006E\"" in svgs["flood_blend_modes"]
    assert "feBlend in='SourceGraphic' in2='SourceGraphic' mode='multiply'" in svgs["gradient_blend_approximation"]


def test_stack_museum_manifest_counts_render_tiers() -> None:
    cases = build_stack_cases()
    manifest = build_manifest(cases, render_tiers=True)

    assert manifest["case_count"] == len(cases)
    assert manifest["expected_slide_count"] == len(cases) * 4
