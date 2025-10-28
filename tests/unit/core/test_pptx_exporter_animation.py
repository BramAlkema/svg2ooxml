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

        def alpha(self, alpha: float) -> "_AdvancedColor":
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
    assert stage_totals.get("animation:fragment_bundle_emitted") == 1
    assert stage_totals.get("animation:timing_emitted") == 1
    assert "<p:timing" in render_result.slide_xml
    assert '<a:spTgt spid="' in render_result.slide_xml


def test_scale_animation_emits_animscale() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animScale" in render_result.slide_xml


def test_spline_easing_sets_accel() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1;1.5" dur="1s" begin="0s" calcMode="spline" keyTimes="0;1" keySplines="0.5 0.2 0.5 1"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "accel=\"20000\"" in render_result.slide_xml


def test_scale_animation_emits_segment_tavs() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1 1;1.5 2;0.5 0.5" keyTimes="0;0.4;1" keySplines="0.42 0 0.58 1;0.25 0.1 0.25 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<a:tav tm=") >= 3
    assert '<a:pt x="1.5" y="2"' in render_result.slide_xml
    assert '<a:pt x="0.5" y="0.5"' in render_result.slide_xml
    assert '<a:tavPr accel="' in render_result.slide_xml
    assert 'svg2:spline=' in render_result.slide_xml
    assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in render_result.slide_xml


def test_rotate_animation_emits_animrot() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="rotate" values="0;90" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animRot" in render_result.slide_xml


def test_rotate_animation_emits_segment_tavs() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="rotate" values="0;90;180" keyTimes="0;0.25;1" keySplines="0.42 0 0.58 1;0.25 0.1 0.25 1" calcMode="spline" dur="2s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<a:tav tm=") >= 3
    assert '<a:val val="0"/>' in render_result.slide_xml
    assert '<a:val val="5400000"/>' in render_result.slide_xml
    assert '<a:val val="10800000"/>' in render_result.slide_xml
    assert '<a:tavPr accel="' in render_result.slide_xml
    assert 'svg2:spline=' in render_result.slide_xml
    assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in render_result.slide_xml


def test_translate_animation_emits_anim_motion() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="translate" values="0 0; 10 5" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animMotion" in render_result.slide_xml
    assert "<a:by x=" in render_result.slide_xml


def test_animate_motion_path_emits_point_list() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="M 0 0 L 10 0 L 10 10" />
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animMotion" in render_result.slide_xml
    assert "<a:ptLst" in render_result.slide_xml
    assert render_result.slide_xml.count("<a:pt x=") >= 3


def test_numeric_attribute_animation_emits_anim() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" from="0" to="20" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:anim>" in render_result.slide_xml
    assert "<a:attrName>ppt_x</a:attrName>" in render_result.slide_xml
    assert '<a:val val="190500"' in render_result.slide_xml


def test_rotate_attribute_animation_uses_ppt_angle() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="rotate" values="0;90" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:anim>" in render_result.slide_xml
    assert "<a:attrName>ppt_angle</a:attrName>" in render_result.slide_xml
    assert '<a:val val="0"' in render_result.slide_xml
    assert '<a:val val="5400000"' in render_result.slide_xml

def test_width_animation_uses_ppt_width_attribute() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="width" values="10;20" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:anim>" in render_result.slide_xml
    assert "<a:attrName>ppt_w</a:attrName>" in render_result.slide_xml
    assert '<a:val val="95250"' in render_result.slide_xml


def test_stroke_width_animation_maps_to_ln_w() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000" stroke="#000">
        <animate attributeName="stroke-width" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:anim>" in render_result.slide_xml
    assert "<a:attrName>ln_w</a:attrName>" in render_result.slide_xml
    assert '<a:val val="9525"' in render_result.slide_xml
    assert '<a:val val="19050"' in render_result.slide_xml


def test_color_animation_emits_animclr() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000; #00ff00" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animClr" in render_result.slide_xml
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

    assert "<a:set" in render_result.slide_xml
    assert "<a:attrName>visibility</a:attrName>" in render_result.slide_xml
    assert 'a:val val="hidden"' in render_result.slide_xml


def test_set_animation_normalizes_numeric_value() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <set attributeName="x" to="10" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:set" in render_result.slide_xml
    assert "<a:attrName>ppt_x</a:attrName>" in render_result.slide_xml
    assert 'a:val val="95250"' in render_result.slide_xml


def test_numeric_animation_tav_list_emitted() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" values="0;10;20" keyTimes="0;0.5;1" keySplines="0.25 0.1 0.25 1; 0.42 0 0.58 1" calcMode="spline" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<a:tav tm=") >= 3
    assert '<a:tav tm="0"' in render_result.slide_xml
    assert 'tm="500"' in render_result.slide_xml
    assert 'tm="1000"' in render_result.slide_xml
    assert 'val="0"' in render_result.slide_xml
    assert 'val="95250"' in render_result.slide_xml
    assert 'val="190500"' in render_result.slide_xml
    assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in render_result.slide_xml
    assert 'svg2:spline="0.2500,0.1000,0.2500,1.0000"' in render_result.slide_xml
    assert 'svg2:segDur="500"' in render_result.slide_xml
    assert 'svg2:accel="10000"' in render_result.slide_xml
    assert '<a:tavPr accel="10000"' in render_result.slide_xml


def test_color_animation_tav_list_emitted() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000;#00ff00;#0000ff" keyTimes="0;0.25;1" keySplines="0.42 0 0.58 1; 0.25 0.1 0.25 1" calcMode="spline" dur="2s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<a:tav tm=") >= 3
    assert '<a:tav tm="0"' in render_result.slide_xml
    assert 'tm="500"' in render_result.slide_xml  # 0.25 * 2000ms
    assert 'tm="2000"' in render_result.slide_xml
    assert 'a:srgbClr val="FF0000"' in render_result.slide_xml
    assert 'a:srgbClr val="00FF00"' in render_result.slide_xml
    assert 'a:srgbClr val="0000FF"' in render_result.slide_xml
    assert 'xmlns:svg2="http://svg2ooxml.dev/ns/animation"' in render_result.slide_xml
    assert 'svg2:spline="0.4200,0.0000,0.5800,1.0000"' in render_result.slide_xml
    assert 'svg2:segDur="500"' in render_result.slide_xml
    assert 'svg2:segDur="1500"' in render_result.slide_xml
    assert '<a:tavPr accel="10000"' in render_result.slide_xml
    assert 'svg2:accel="10000"' in render_result.slide_xml


def test_motion_path_handles_relative_and_curves() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="2" height="2" fill="#000">
        <animateMotion dur="1s" path="m 0 0 c 0 10 10 10 10 0 l 0 10 z" />
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<a:animMotion" in render_result.slide_xml
    assert render_result.slide_xml.count("<a:pt x=") >= 5


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
    skipped_events = [
        event
        for event in report.stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert skipped_events
    assert skipped_events[0].metadata.get("reason") == "policy:fallback_mode=slide"
    bundle_events = [
        event
        for event in report.stage_events
        if event.stage == "animation" and event.action == "fragment_bundle_skipped"
    ]
    assert bundle_events
    assert bundle_events[0].metadata.get("skip_reason") == "policy:fallback_mode=slide"


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
    reasons = {
        event.metadata.get("reason")
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    }
    assert any(reason and reason.startswith("policy:spline_error>") for reason in reasons)
