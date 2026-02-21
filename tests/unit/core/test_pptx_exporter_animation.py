from __future__ import annotations

import importlib
import sys

try:
    advanced_mod = importlib.import_module("svg2ooxml.color.advanced")
except ImportError:  # pragma: no cover - optional dependency omitted
    import types

    advanced_mod = types.ModuleType("svg2ooxml.color.advanced")
    sys.modules["svg2ooxml.color.advanced"] = advanced_mod

if not getattr(advanced_mod, "COLOR_ENGINE_AVAILABLE", False):

    class _AdvancedColor:
        def __init__(self, value) -> None:
            self._value = value

        def alpha(self, alpha: float) -> _AdvancedColor:
            return self

        def rgba(self) -> tuple[int, int, int, int]:
            return (0, 0, 0, 255)

    advanced_mod.AdvancedColor = _AdvancedColor  # type: ignore[attr-defined]
    advanced_mod.COLOR_ENGINE_AVAILABLE = False  # type: ignore[attr-defined]

    def _require_color_engine() -> None:
        raise RuntimeError("Advanced color engine unavailable")

    advanced_mod.require_color_engine = _require_color_engine  # type: ignore[attr-defined]

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer


def _render(svg: str):
    exporter = SvgToPptxExporter()
    tracer = ConversionTracer()
    render_result, scene = exporter._render_svg(svg, tracer)  # type: ignore[attr-defined]
    return render_result, scene, tracer


def test_render_svg_emits_animation_metadata() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1" dur="2s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, scene, tracer = _render(svg)

    assert scene.metadata is not None
    animation_meta = scene.metadata.get("animation")
    assert animation_meta is not None
    assert animation_meta["definition_count"] == 1
    assert animation_meta["definitions"][0]["element_id"] == "rect1"
    assert animation_meta["summary"]["total_animations"] == 1
    assert animation_meta["timeline"]

    stage_totals = tracer.report().stage_totals
    assert stage_totals.get("animation:parsed") == 1
    assert stage_totals.get("animation:mapped_animation") == 1
    assert stage_totals.get("animation:fragment_emitted") == 1
    assert stage_totals.get("animation:timing_emitted") == 1
    assert "<p:timing" in render_result.slide_xml
    assert '<p:spTgt spid="' in render_result.slide_xml


def test_animation_parse_fallback_reasons_are_traced() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10;20" keyTimes="0;0.7;0.2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    _, scene, tracer = _render(svg)

    assert scene.metadata is not None
    animation_meta = scene.metadata.get("animation")
    assert animation_meta is not None
    assert animation_meta["summary"]["fallback_reasons"]["key_times_not_ascending"] == 1

    fallback_events = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "parse_fallback"
    ]
    assert fallback_events
    assert any(
        event.metadata.get("reason") == "key_times_not_ascending"
        and event.metadata.get("count") == 1
        for event in fallback_events
    )


def test_scale_animation_emits_animscale() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animScale" in render_result.slide_xml


def test_spline_easing_on_scale_uses_from_to() -> None:
    """animScale uses from/to attributes — tavLst is schema-invalid for animScale."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1;1.5" dur="1s" begin="0s" calcMode="spline" keyTimes="0;1" keySplines="0.5 0.2 0.5 1"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animScale" in render_result.slide_xml
    assert "<p:from" in render_result.slide_xml
    assert "<p:to" in render_result.slide_xml


def test_scale_animation_uses_from_to_not_tavlst() -> None:
    """ECMA-376 CT_TLAnimateScaleBehavior only allows cBhvr/from/to/by — no tavLst."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1 1;1.5 2;0.5 0.5" keyTimes="0;0.4;1" keySplines="0.42 0 0.58 1;0.25 0.1 0.25 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    # animScale uses first/last values for from/to
    assert "<p:animScale" in render_result.slide_xml
    assert "<p:from" in render_result.slide_xml
    assert "<p:to" in render_result.slide_xml
    # tavLst is NOT valid in animScale per ECMA-376
    assert "<p:tavLst" not in render_result.slide_xml


def test_rotate_animation_emits_animrot() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="rotate" values="0;90" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animRot" in render_result.slide_xml


def test_rotate_animation_uses_by_not_tavlst() -> None:
    """ECMA-376 CT_TLAnimateRotationBehavior only allows cBhvr + by — no tavLst."""
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="rotate" values="0;90;180" keyTimes="0;0.25;1" keySplines="0.42 0 0.58 1;0.25 0.1 0.25 1" calcMode="spline" dur="2s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animRot" in render_result.slide_xml
    # animRot uses by= attribute for rotation delta
    assert 'by="' in render_result.slide_xml
    # tavLst is NOT valid in animRot per ECMA-376
    assert "<p:tavLst" not in render_result.slide_xml


def test_translate_animation_emits_anim_motion() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="translate" values="0 0; 10 5" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animMotion" in render_result.slide_xml
    assert "<p:by x=" in render_result.slide_xml


def test_animate_motion_path_emits_point_list() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="M 0 0 L 10 0 L 10 10" />
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animMotion" in render_result.slide_xml
    assert 'path="M' in render_result.slide_xml
    assert 'ptsTypes=' in render_result.slide_xml


def test_motion_rotate_auto_emits_fidelity_downgrade_trace() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="M0,0 L0,100" rotate="auto" />
      </rect>
    </svg>
    """

    _, _, tracer = _render(svg)
    events = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fidelity_downgrade"
    ]
    assert events
    assert any(
        event.metadata.get("reason") == "rotate_auto_approximated"
        and event.metadata.get("rotate_mode") == "auto"
        for event in events
    )


def test_translate_discrete_calc_mode_expands_path_points() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="translate" values="0 0;10 0;10 10" keyTimes="0;0.4;1" calcMode="discrete" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)
    assert "<p:animMotion" in render_result.slide_xml
    # Discrete approximation duplicates boundary timestamps.
    assert render_result.slide_xml.count(" L ") > 2


def test_motion_discrete_calc_mode_expands_path_points() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="M0,0 L100,0" keyTimes="0;0.4;1" calcMode="discrete" />
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)
    assert "<p:animMotion" in render_result.slide_xml
    assert render_result.slide_xml.count(" L ") > 1


def test_begin_click_emits_onclick_condition() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1" begin="click" dur="1s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:timing" in render_result.slide_xml
    assert 'evt="onClick"' in render_result.slide_xml
    assert "<p:tgtEl><p:spTgt spid=" in render_result.slide_xml


def test_begin_click_with_offset_emits_onclick_condition_with_delay() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1" begin="click+0.5s" dur="1s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:timing" in render_result.slide_xml
    assert 'evt="onClick"' in render_result.slide_xml
    assert 'delay="500"' in render_result.slide_xml


def test_begin_element_end_with_offset_emits_onend_condition() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1" begin="0s" dur="1s"/>
      </rect>
      <rect id="rect2" x="20" width="10" height="10" fill="#000">
        <animate attributeName="x" values="20;30" begin="rect1.end+0.5s" dur="1s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:timing" in render_result.slide_xml
    assert 'evt="onEnd"' in render_result.slide_xml
    assert 'delay="500"' in render_result.slide_xml


def test_numeric_attribute_animation_emits_anim() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" from="0" to="20" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:anim>" in render_result.slide_xml
    assert '<p:attrName>ppt_x</p:attrName>' in render_result.slide_xml
    assert '<p:fltVal val="190500"/>' in render_result.slide_xml


def test_rotate_attribute_animation_uses_ppt_angle() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="rotate" values="0;90" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:anim>" in render_result.slide_xml
    assert '<p:attrName>ppt_angle</p:attrName>' in render_result.slide_xml
    assert '<p:fltVal val="0"/>' in render_result.slide_xml
    assert '<p:fltVal val="5400000"/>' in render_result.slide_xml

def test_width_animation_uses_ppt_width_attribute() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="width" values="10;20" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:anim>" in render_result.slide_xml
    assert '<p:attrName>ppt_w</p:attrName>' in render_result.slide_xml
    assert '<p:fltVal val="95250"/>' in render_result.slide_xml


def test_stroke_width_animation_maps_to_ln_w() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000" stroke="#000">
        <animate attributeName="stroke-width" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:anim>" in render_result.slide_xml
    assert '<p:attrName>ln_w</p:attrName>' in render_result.slide_xml
    assert '<p:fltVal val="9525"/>' in render_result.slide_xml
    assert '<p:fltVal val="19050"/>' in render_result.slide_xml


def test_color_animation_emits_animclr() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000; #00ff00" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animClr" in render_result.slide_xml
    assert 'a:srgbClr val="FF0000"' in render_result.slide_xml
    assert 'a:srgbClr val="00FF00"' in render_result.slide_xml


def test_set_animation_emits_set_element() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <set attributeName="visibility" to="hidden" begin="0.5s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:set>" in render_result.slide_xml
    assert '<p:attrName>visibility</p:attrName>' in render_result.slide_xml
    assert '<p:strVal val="hidden"/>' in render_result.slide_xml


def test_set_animation_normalizes_numeric_value() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <set attributeName="x" to="10" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:set>" in render_result.slide_xml
    assert '<p:attrName>ppt_x</p:attrName>' in render_result.slide_xml
    assert '<p:strVal val="95250"/>' in render_result.slide_xml


def test_numeric_animation_tav_list_emitted() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10;20" keyTimes="0;0.5;1" keySplines="0.25 0.1 0.25 1; 0.42 0 0.58 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count('tm="') >= 3
    assert 'tm="0"' in render_result.slide_xml
    assert 'tm="50000"' in render_result.slide_xml    # 0.5 * 100000
    assert 'tm="100000"' in render_result.slide_xml
    assert 'val="0"' in render_result.slide_xml
    assert 'val="95250"' in render_result.slide_xml
    assert 'val="190500"' in render_result.slide_xml


def test_numeric_discrete_calc_mode_emits_step_boundaries() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10;20" keyTimes="0;0.4;1" calcMode="discrete" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count('tm="40000"') >= 2
    assert render_result.slide_xml.count('tm="100000"') >= 2


def test_numeric_paced_calc_mode_uses_distance_weighted_key_times() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10;40" keyTimes="0;0.5;1" calcMode="paced" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    # Distances are 10 then 30, so paced midpoint should be 25%.
    assert 'tm="25000"' in render_result.slide_xml
    assert 'tm="50000"' not in render_result.slide_xml


def test_color_animation_uses_from_to_without_tav_list() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000;#00ff00;#0000ff" keyTimes="0;0.25;1" keySplines="0.42 0 0.58 1; 0.25 0.1 0.25 1" calcMode="spline" dur="2s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animClr" in render_result.slide_xml
    assert "<p:tavLst" not in render_result.slide_xml
    assert "<p:from" in render_result.slide_xml
    assert "<p:to" in render_result.slide_xml
    assert 'a:srgbClr val="FF0000"' in render_result.slide_xml
    assert 'a:srgbClr val="0000FF"' in render_result.slide_xml


def test_color_discrete_calc_mode_still_omits_tav_list() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000;#00ff00;#0000ff" keyTimes="0;0.4;1" calcMode="discrete" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animClr" in render_result.slide_xml
    assert "<p:tavLst" not in render_result.slide_xml


def test_motion_path_handles_relative_and_curves() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="m 0 0 c 0 10 10 10 10 0 l 0 10 z" />
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animMotion" in render_result.slide_xml
    assert 'path="M' in render_result.slide_xml


def test_policy_can_disable_native_spline_output() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10" keyTimes="0;1" keySplines="0.25 0.1 0.25 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    exporter = SvgToPptxExporter()
    tracer = ConversionTracer()
    overrides = {"animation": {"allow_native_splines": False, "fallback_mode": "slide"}}
    render_result, scene = exporter._render_svg(svg, tracer, policy_overrides=overrides)  # type: ignore[attr-defined]

    assert "<p:timing" not in render_result.slide_xml
    policy_meta = scene.metadata.get("policy", {}) if scene.metadata else {}
    animation_policy = policy_meta.get("animation", {})
    assert animation_policy.get("fallback_mode") == "slide"
    report = tracer.report()
    # The pipeline now reports per-fragment skips when policy disables native timing.
    skipped_events = [
        event
        for event in report.stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert skipped_events


def test_policy_spline_error_fallback() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10" keyTimes="0;1" keySplines="0.9 0 0.1 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    exporter = SvgToPptxExporter()
    tracer = ConversionTracer()
    overrides = {"animation": {"max_spline_error": 0.05}}
    render_result, _ = exporter._render_svg(svg, tracer, policy_overrides=overrides)  # type: ignore[attr-defined]

    assert "<p:timing" not in render_result.slide_xml
    # The pipeline emits fragment_skipped events when spline error exceeds the threshold.
    skipped_events = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert skipped_events
