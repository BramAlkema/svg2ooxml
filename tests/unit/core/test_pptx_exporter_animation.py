from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest
from lxml import etree as ET

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

_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _render(svg: str):
    exporter = SvgToPptxExporter()
    tracer = ConversionTracer()
    render_result, scene = exporter._render_svg(svg, tracer)  # type: ignore[attr-defined]
    return render_result, scene, tracer


def _motion_paths(slide_xml: str) -> list[str]:
    return re.findall(r'<p:animMotion[^>]* path="([^"]+)"', slide_xml)


def _shape_offset(slide_xml: str, shape_id: int) -> tuple[int, int]:
    match = re.search(
        rf'<p:cNvPr id="{shape_id}"[^>]*>.*?<a:off x="([0-9]+)" y="([0-9]+)"',
        slide_xml,
        flags=re.DOTALL,
    )
    assert match is not None
    return (int(match.group(1)), int(match.group(2)))


def _shape_extent(slide_xml: str, shape_id: int) -> tuple[int, int]:
    match = re.search(
        rf'<p:cNvPr id="{shape_id}"[^>]*>.*?<a:ext cx="([0-9]+)" cy="([0-9]+)"',
        slide_xml,
        flags=re.DOTALL,
    )
    assert match is not None
    return (int(match.group(1)), int(match.group(2)))


def _onclick_shape_ids_inside_groups(slide_xml: str) -> set[str]:
    root = ET.fromstring(slide_xml.encode("utf-8"))
    click_shape_ids = {
        sp_tgt.get("spid")
        for sp_tgt in root.xpath(".//p:cond[@evt='onClick']//p:spTgt", namespaces=_NS)
        if sp_tgt.get("spid")
    }
    grouped_shape_ids = {
        c_nv_pr.get("id")
        for c_nv_pr in root.xpath(".//p:grpSp//p:sp/p:nvSpPr/p:cNvPr", namespaces=_NS)
        if c_nv_pr.get("id")
    }
    return click_shape_ids & grouped_shape_ids


def _timing_shape_ids_inside_groups(slide_xml: str) -> set[str]:
    root = ET.fromstring(slide_xml.encode("utf-8"))
    timing_shape_ids = {
        sp_tgt.get("spid")
        for sp_tgt in root.xpath(".//p:timing//p:spTgt", namespaces=_NS)
        if sp_tgt.get("spid")
    }
    grouped_shape_ids = {
        c_nv_pr.get("id")
        for c_nv_pr in root.xpath(".//p:grpSp//p:sp/p:nvSpPr/p:cNvPr", namespaces=_NS)
        if c_nv_pr.get("id")
    }
    return timing_shape_ids & grouped_shape_ids


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
    assert animation_meta["definitions"][0]["native_match"]["level"] == "exact-native"
    assert animation_meta["definitions"][0]["native_match"]["reason"] == "opacity-authored-fade"
    assert animation_meta["native_match_summary"]["total"] == 1
    assert animation_meta["native_match_summary"]["by_level"]["exact-native"] == 1
    assert animation_meta["summary"]["total_animations"] == 1
    assert animation_meta["timeline"]

    stage_totals = tracer.report().stage_totals
    assert stage_totals.get("animation:parsed") == 1
    assert stage_totals.get("animation:mapped_animation") == 1
    assert stage_totals.get("animation:fragment_emitted") == 1
    assert stage_totals.get("animation:timing_emitted") == 1
    assert "<p:timing" in render_result.slide_xml
    assert '<p:spTgt spid="' in render_result.slide_xml


def test_render_svg_animation_metadata_serializes_timing_plumbing() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1"
                 begin="rect1.repeat(3)+2s;accessKey(a)"
                 end="wallclock(2000-01-01T00:00:00Z)"
                 repeatDur="5s" dur="2s"/>
      </rect>
    </svg>
    """

    _, scene, _ = _render(svg)

    animation_meta = scene.metadata["animation"]
    timing = animation_meta["definitions"][0]["timing"]
    assert timing["repeat_duration"] == 5.0
    assert timing["begin_triggers"][0]["trigger_type"] == "element_repeat"
    assert timing["begin_triggers"][0]["target_element_id"] == "rect1"
    assert timing["begin_triggers"][0]["repeat_iteration"] == 3
    assert timing["begin_triggers"][1]["trigger_type"] == "access_key"
    assert timing["begin_triggers"][1]["access_key"] == "a"
    assert timing["end_triggers"][0]["trigger_type"] == "wallclock"
    assert timing["end_triggers"][0]["wallclock_value"] == "2000-01-01T00:00:00Z"


def test_render_svg_emits_native_repeat_restart_and_end_conditions() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1"
                 begin="0s"
                 end="1s;rect1.click+250ms"
                 repeatCount="indefinite"
                 repeatDur="5s"
                 restart="whenNotActive"
                 dur="2s"/>
      </rect>
    </svg>
    """

    render_result, scene, _ = _render(svg)

    assert 'repeatCount="indefinite"' in render_result.slide_xml
    assert 'repeatDur="5000"' in render_result.slide_xml
    assert 'restart="whenNotActive"' in render_result.slide_xml
    assert "<p:endCondLst>" in render_result.slide_xml
    assert '<p:cond delay="1000"/>' in render_result.slide_xml
    assert 'evt="onClick"' in render_result.slide_xml
    assert 'delay="250"' in render_result.slide_xml

    native_match = scene.metadata["animation"]["definitions"][0]["native_match"]
    assert native_match["level"] == "exact-native"
    assert "end-condition-native" in native_match["limitations"]
    assert "repeat-duration-native" in native_match["limitations"]
    assert "restart-native" in native_match["limitations"]


def test_use_inherits_defs_owned_animations() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <defs>
        <rect id="base" width="10" height="10" fill="#000">
          <animateColor attributeName="fill" from="#000000" to="#00ff00" dur="1s" begin="0s"/>
        </rect>
      </defs>
      <use id="inst" href="#base" x="5">
        <animate attributeName="x" values="5;10" dur="1s" begin="0s"/>
      </use>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    stage_totals = tracer.report().stage_totals
    assert stage_totals.get("animation:mapped_animation") == 2
    assert stage_totals.get("animation:unmapped_animation") is None
    assert "<p:animClr" in render_result.slide_xml
    assert "<p:animMotion" in render_result.slide_xml


def test_use_line_endpoint_animation_composes_into_motion_and_scale() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <defs>
        <line id="base" x1="30" y1="50" x2="10" y2="10" stroke="#000" stroke-width="3">
          <animate attributeName="x1" from="30" to="50" dur="1s" begin="0s" fill="freeze"/>
        </line>
      </defs>
      <use id="inst" href="#base">
        <animate attributeName="x" from="10" to="20" dur="1s" begin="0s" fill="freeze"/>
      </use>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    assert render_result.slide_xml.count("<p:animMotion") == 1
    assert render_result.slide_xml.count("<p:animScale") == 1
    assert 'path="M 0 0 L 0.2 0 E"' in render_result.slide_xml
    assert '<p:to x="200000" y="100000"/>' in render_result.slide_xml
    assert "<p:attrName>stroke.weight</p:attrName>" not in render_result.slide_xml
    assert "<p:attrName>x1</p:attrName>" not in render_result.slide_xml

    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert not skipped


def test_multi_keyframe_line_endpoint_animation_is_not_collapsed_to_linear_scale() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <defs>
        <line id="base" x1="30" y1="50" x2="10" y2="10" stroke="#000" stroke-width="3">
          <animate attributeName="x1" values="30;40;50" keyTimes="0;0.2;1" dur="1s" begin="0s" fill="freeze"/>
        </line>
      </defs>
      <use id="inst" href="#base">
        <animate attributeName="x" from="10" to="20" dur="1s" begin="0s" fill="freeze"/>
      </use>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    assert render_result.slide_xml.count("<p:animMotion") == 1
    assert "<p:animScale" not in render_result.slide_xml
    assert "<p:attrName>x1</p:attrName>" not in render_result.slide_xml

    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert any(
        event.metadata.get("attribute") == "x1"
        and event.metadata.get("reason") == "no_handler_found"
        for event in skipped
    )


def test_circle_stacked_position_and_scale_uses_sampled_motion_path() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <g transform="translate(20 0) scale(1.3 1.3)">
        <defs>
          <circle id="base" cx="20" cy="100" r="10" fill="#105D8C" stroke="#000">
            <animate attributeName="cy" from="100" to="130" dur="3s" begin="0s" fill="freeze"/>
            <animateTransform attributeName="transform" type="scale" from="1" to="1.5" additive="sum" dur="3s" begin="0s" fill="freeze"/>
          </circle>
        </defs>
        <use href="#base">
          <animate attributeName="x" from="10" to="70" dur="3s" begin="0s" fill="freeze"/>
        </use>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    paths = _motion_paths(render_result.slide_xml)
    assert len(paths) == 1
    assert paths[0].count(" L ") > 1
    assert "0.189583 0.343056 E" in paths[0]
    assert render_result.slide_xml.count("<p:animScale") == 1
    assert _shape_offset(render_result.slide_xml, 2) != (0, 0)


def test_image_stacked_y_and_scale_uses_sampled_motion_path() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <g transform="translate(20 0) scale(1.3 1.3)">
        <defs>
          <image id="base" x="230" y="20" width="40" height="80"
            href="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAYAAAC09K7GAAAAFUlEQVR4nGP8z8DwnwEJMCFzsAoAAGFrAgT6YybLAAAAAElFTkSuQmCC">
            <animate attributeName="y" from="5" to="145" dur="3s" begin="0s" fill="freeze"/>
          </image>
        </defs>
        <use href="#base">
          <animateTransform attributeName="transform" type="scale" from="1 .25" to="1 1" additive="sum" dur="3s" begin="0s" fill="freeze"/>
        </use>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    paths = _motion_paths(render_result.slide_xml)
    assert len(paths) == 1
    assert paths[0].count(" L ") > 1
    assert "0 0.627431 E" in paths[0]
    assert render_result.slide_xml.count("<p:animScale") == 1
    assert _shape_offset(render_result.slide_xml, 2) != (0, 0)
    assert _shape_extent(render_result.slide_xml, 2) == (495300, 371475)


def test_motion_and_origin_rotate_stack_uses_sampled_orbit_path() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <g transform="translate(20 0) scale(1.3 1.3)">
        <defs>
          <polyline id="base" fill="none" stroke="#105D8C" stroke-width="2"
            points="200,20 200,40 220,40 220,60">
            <animateMotion path="M 0 0 l 0 100" begin="0s" dur="3s" fill="freeze"/>
          </polyline>
        </defs>
        <use href="#base">
          <animateTransform attributeName="transform" type="rotate" from="0" to="15" additive="sum" dur="3s" begin="0s" fill="freeze"/>
        </use>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    paths = _motion_paths(render_result.slide_xml)
    assert len(paths) == 1
    assert paths[0].count(" L ") > 1
    assert "-0.117514 0.540155 E" in paths[0] or "-0.117515 0.540156 E" in paths[0]
    assert render_result.slide_xml.count("<p:animRot") == 1
    assert _shape_offset(render_result.slide_xml, 2) != (0, 0)


def test_polyline_stroke_width_and_opacity_still_materializes_line_segments() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <polyline id="base" fill="none" stroke="#105D8C" stroke-width="2"
        points="10,10 20,20 30,10">
        <animate attributeName="stroke-width" from="2" to="4" dur="1s" begin="0s" fill="freeze"/>
        <animate attributeName="opacity" from="1" to="0.5" dur="1s" begin="0s" fill="freeze"/>
      </polyline>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    assert render_result.slide_xml.count("<p:cxnSp>") == 2
    assert "<a:custGeom" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:attrName>stroke.weight</p:attrName>") == 2
    assert render_result.slide_xml.count("<p:attrName>style.opacity</p:attrName>") == 2

    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert not skipped


def test_motion_animation_metadata_infers_triangle_heading() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <path id="triangle" d="M-15,0 L0,-30 L15,0 z" fill="blue" stroke="green">
        <animateMotion path="M25,225 C25,175 125,150 175,200" rotate="auto" dur="6s" begin="0s" fill="freeze"/>
      </path>
    </svg>
    """

    _, scene, _ = _render(svg)

    animation_meta = scene.metadata.get("animation")
    assert animation_meta is not None
    assert animation_meta["definitions"][0]["element_heading_deg"] == pytest.approx(-90.0)


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


def test_scale_animation_emits_origin_compensation_motion_when_center_known() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <rect id="rect1" x="20" y="10" width="10" height="10" fill="#000">
        <animateTransform attributeName="transform" type="scale" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animScale" in render_result.slide_xml
    assert '<p:animMotion origin="layout" path="M 0 0 L 0.25 0.15 E"' in render_result.slide_xml


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
    assert 'path="M 0 0 L 1 0.5 E"' in render_result.slide_xml
    assert "<p:by x=" not in render_result.slide_xml


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
    assert "pathEditMode=\"relative\"" in render_result.slide_xml


def test_animate_motion_projects_path_into_shape_position_space() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <path id="ship" d="M-30,0 L0,-60 L30,0 z" fill="#00f" stroke="#080" stroke-width="6">
        <animateMotion dur="1s" path="M90,258 L390,180" fill="freeze" />
      </path>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert '<a:off x="571500" y="1885950"/>' in render_result.slide_xml
    assert '<p:animMotion origin="layout" path="M 0 0 L 0.625 -0.216667 E"' in render_result.slide_xml


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


def test_motion_rotate_auto_with_turn_emits_stacked_rotation() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <path id="ship" d="M-10,0 L0,-20 L10,0 z" fill="#00f">
        <animateMotion dur="1s" path="M10,10 L90,10 L90,90" rotate="auto" fill="freeze" />
      </path>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animMotion" in render_result.slide_xml
    assert "<p:animRot" in render_result.slide_xml


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


def test_begin_click_with_offset_and_spaces_emits_onclick_condition_with_delay() -> (
    None
):
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0;1" begin="click + 0.5s" dur="1s"/>
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


def test_begin_animation_id_end_remaps_to_owning_shape() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate id="grow" attributeName="width" values="10;20" begin="0s" dur="1s"/>
      </rect>
      <rect id="rect2" x="20" width="10" height="10" fill="#000">
        <animate attributeName="x" values="20;30" begin="grow.end+0.5s" dur="1s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:timing" in render_result.slide_xml
    assert 'evt="onEnd"' in render_result.slide_xml
    assert 'delay="500"' in render_result.slide_xml
    # rect1 is shape 2 in the emitted slide.
    assert '<p:spTgt spid="2"/>' in render_result.slide_xml


def test_begin_indefinite_remaps_to_bookmark_button_click_trigger() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">
      <rect id="target" x="0" y="0" width="40" height="40" fill="#fff">
        <animate id="fadein" attributeName="fill" from="#fff" to="blue" begin="indefinite" dur="3s" fill="freeze"/>
      </rect>
      <a xlink:href="#fadein">
        <rect id="button" x="60" y="0" width="30" height="30" fill="green"/>
      </a>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    assert 'evt="onClick"' in render_result.slide_xml
    assert '<p:spTgt spid="3"/>' in render_result.slide_xml
    assert '<p:bldP spid="3" grpId="7" animBg="1"/>' in render_result.slide_xml
    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert not any(
        event.metadata.get("reason") == "unsupported_begin_indefinite"
        for event in skipped
    )


def test_bookmark_click_triggers_are_not_nested_inside_groups() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">
      <g id="outer">
        <rect id="target" x="0" y="0" width="40" height="40" fill="#fff">
          <animate id="fadein" attributeName="fill" from="#fff" to="blue" begin="indefinite" dur="3s" fill="freeze"/>
        </rect>
        <g id="buttons">
          <a xlink:href="#fadein">
            <rect id="button" x="60" y="0" width="30" height="30" fill="green"/>
          </a>
        </g>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert 'evt="onClick"' in render_result.slide_xml
    assert not _onclick_shape_ids_inside_groups(render_result.slide_xml)


def test_begin_indefinite_bookmark_trigger_preserves_chained_begin() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="100">
      <rect id="target" x="0" y="0" width="40" height="40" fill="#fff">
        <animate id="fadein" attributeName="fill" from="#fff" to="blue" begin="indefinite" dur="3s" fill="freeze"/>
      </rect>
      <rect id="other" x="0" y="50" width="40" height="40" fill="#fff">
        <animate attributeName="fill" from="#fff" to="red" begin="fadein.begin" dur="3s" fill="freeze"/>
      </rect>
      <a xlink:href="#fadein">
        <rect id="button" x="60" y="0" width="30" height="30" fill="green"/>
      </a>
    </svg>
    """

    render_result, _, tracer = _render(svg)

    assert 'evt="onClick"' in render_result.slide_xml
    assert 'evt="onBegin"' in render_result.slide_xml
    assert '<p:spTgt spid="4"/>' in render_result.slide_xml
    assert '<p:spTgt spid="2"/>' in render_result.slide_xml
    assert '<p:bldP spid="4" grpId="8" animBg="1"/>' in render_result.slide_xml
    assert '<p:bldP spid="2" grpId="10" animBg="1"/>' in render_result.slide_xml
    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    assert not skipped


def test_skew_transform_reports_specific_reason_codes() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <line id="line1" x1="10" y1="10" x2="50" y2="10" stroke="#000" stroke-width="4">
        <animateTransform attributeName="transform" type="skewX" values="0;45;-45;0" begin="0s" dur="4s"/>
      </line>
      <line id="line2" x1="10" y1="40" x2="50" y2="40" stroke="#000" stroke-width="4">
        <animateTransform attributeName="transform" type="skewY" values="0;30;-30;0" begin="0s" dur="4s"/>
      </line>
    </svg>
    """

    _, _, tracer = _render(svg)

    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    reasons = {event.metadata.get("reason") for event in skipped}
    assert "unsupported_transform_skewx" in reasons
    assert "unsupported_transform_skewy" in reasons
    assert "no_handler_found" not in reasons


def test_color_property_animation_reports_specific_reason_code() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <rect id="rect1" color="black" fill="blue" x="10" y="10" width="60" height="40">
        <animateColor attributeName="color" from="blue" to="cyan" begin="0s" dur="5s" fill="freeze"/>
      </rect>
    </svg>
    """

    _, _, tracer = _render(svg)

    skipped = [
        event
        for event in tracer.report().stage_events
        if event.stage == "animation" and event.action == "fragment_skipped"
    ]
    reasons = {event.metadata.get("reason") for event in skipped}
    assert "unsupported_attribute_color" in reasons
    assert "no_handler_found" not in reasons


def test_numeric_attribute_animation_emits_anim() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" from="0" to="20" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    # Position animations use <p:animMotion> with a path
    assert "<p:animMotion" in render_result.slide_xml


def test_position_animation_uses_relative_delta_from_nonzero_start() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="x" from="20" to="30" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert '<p:animMotion origin="layout" path="M 0 0 L ' in render_result.slide_xml
    assert 'path="M 0 0 L 1.000000 0.000000 E"' in render_result.slide_xml


def test_position_animation_projects_group_transform_into_motion_delta() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <g transform="scale(2 3)">
        <rect id="rect1" width="10" height="10" fill="#000">
          <animate attributeName="x" from="0" to="10" dur="1s" begin="0s"/>
          <animate attributeName="y" from="0" to="10" dur="1s" begin="0s"/>
        </rect>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert 'path="M 0 0 L 0.2 0.3 E"' in render_result.slide_xml


def test_translate_transform_projects_group_transform_into_motion_delta() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <g transform="scale(2 3)">
        <rect id="rect1" width="10" height="10" fill="#000">
          <animateTransform attributeName="transform" type="translate"
                            from="0 0" to="10 5" dur="1s" begin="0s"/>
        </rect>
      </g>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert 'path="M 0 0 L 0.2 0.15 E"' in render_result.slide_xml


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
    assert "<p:attrName>ppt_angle</p:attrName>" in render_result.slide_xml
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

    # Width animations use <p:animScale>
    assert "<p:animScale" in render_result.slide_xml


def test_symmetric_multi_keyframe_width_animation_uses_autoreverse_scale() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="width" values="10;40;10" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:animScale" in render_result.slide_xml
    assert '<p:by x="400000" y="100000"/>' in render_result.slide_xml
    assert '<p:attrName>ScaleX</p:attrName>' not in render_result.slide_xml
    assert '<p:attrName>ScaleY</p:attrName>' not in render_result.slide_xml
    assert 'autoRev="1"' in render_result.slide_xml


def test_multi_keyframe_width_animation_with_custom_key_times_uses_segmented_scale() -> (
    None
):
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="width" values="10;40;10" keyTimes="0;0.3;1" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<p:animScale") == 2
    assert "<p:attrName>ppt_w</p:attrName>" not in render_result.slide_xml
    assert "<p:tav " not in render_result.slide_xml
    assert render_result.slide_xml.count('animBg="1"') == 2


def test_animate_elem_10_linear_calc_mode_uses_playable_scale_and_retimed_motion() -> None:
    svg = Path("tests/svg/animate-elem-10-t.svg").read_text(encoding="utf-8")

    render_result, _, _ = _render(svg)

    assert "<p:attrName>ppt_h</p:attrName>" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:animScale") == 3
    assert render_result.slide_xml.count(" L ") > 3


def test_animate_elem_11_paced_calc_mode_uses_playable_scale_and_retimed_motion() -> None:
    svg = Path("tests/svg/animate-elem-11-t.svg").read_text(encoding="utf-8")

    render_result, _, _ = _render(svg)

    assert "<p:attrName>ppt_h</p:attrName>" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:animScale") == 3
    assert render_result.slide_xml.count(" L ") > 3


def test_animate_elem_29_b_bookmark_buttons_are_top_level_shapes() -> None:
    svg = Path("tests/svg/animate-elem-29-b.svg").read_text(encoding="utf-8")

    render_result, _, _ = _render(svg)

    assert "<p:grpSp>" not in render_result.slide_xml
    assert not _onclick_shape_ids_inside_groups(render_result.slide_xml)
    assert render_result.slide_xml.count("<p:attrName>fill.opacity</p:attrName>") == 2


def test_animate_elem_19_linear_calc_mode_targets_top_level_shape() -> None:
    svg = Path("tests/svg/animate-elem-19-t.svg").read_text(encoding="utf-8")

    render_result, _, _ = _render(svg)

    assert not _timing_shape_ids_inside_groups(render_result.slide_xml)
    assert "<p:attrName>ppt_w</p:attrName>" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:animScale") == 3


def test_multi_keyframe_opacity_animation_uses_transparency_effect() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0.1;1;0.1" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert '<p:animEffect filter="image" prLst="opacity: 1">' in render_result.slide_xml
    assert 'rctx="IE"' in render_result.slide_xml
    assert '<p:strVal val="0.1"/>' in render_result.slide_xml
    assert "<p:anim>" not in render_result.slide_xml
    assert "<p:attrName>style.opacity</p:attrName>" in render_result.slide_xml


def test_simple_fade_out_animation_uses_exit_fade_effect() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="1;0" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert '<p:animEffect transition="out" filter="fade">' in render_result.slide_xml
    assert 'presetClass="exit"' in render_result.slide_xml
    assert "<p:anim>" not in render_result.slide_xml


def test_timing_tree_uses_powerpoint_autostart_wrapper() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="opacity" values="0.1;1;0.1" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert 'delay="indefinite"' in render_result.slide_xml
    assert 'evt="onBegin"' in render_result.slide_xml
    main_seq_marker = 'nodeType="mainSeq"'
    main_seq_index = render_result.slide_xml.index(main_seq_marker)
    id_attr_index = render_result.slide_xml.rfind('id="', 0, main_seq_index)
    id_start = id_attr_index + len('id="')
    id_end = render_result.slide_xml.index('"', id_start)
    main_seq_id = render_result.slide_xml[id_start:id_end]
    assert f'<p:tn val="{main_seq_id}"/>' in render_result.slide_xml


def test_stroke_width_animation_maps_to_stroke_weight() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000" stroke="#000">
        <animate attributeName="stroke-width" values="1;2" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:anim>" in render_result.slide_xml
    assert "<p:attrName>stroke.weight</p:attrName>" in render_result.slide_xml
    assert '<p:fltVal val="9525"/>' in render_result.slide_xml
    assert '<p:fltVal val="19050"/>' in render_result.slide_xml


def test_use_alias_x_and_y_motion_collapse_into_single_diagonal_path() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">
      <defs>
        <circle id="baseCircle" cx="100" cy="100" r="10" fill="#00f">
          <animate attributeName="cy" values="100;130" dur="1s" begin="0s"/>
        </circle>
      </defs>
      <use id="useCircle" href="#baseCircle" x="10">
        <animate attributeName="x" values="10;70" dur="1s" begin="0s"/>
      </use>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert render_result.slide_xml.count("<p:animMotion") == 1
    assert (
        '<p:animMotion origin="layout" path="M 0 0 L 0.125 0.0833333 E"'
        in render_result.slide_xml
    )


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
    assert "<p:attrName>style.visibility</p:attrName>" in render_result.slide_xml
    assert '<p:strVal val="hidden"/>' in render_result.slide_xml


def test_display_animations_compile_to_native_visibility_sets() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <g id="gate" display="none">
        <circle cx="10" cy="10" r="5" fill="#ff0000"/>
        <animate attributeName="display" from="none" to="inline" begin="0s" dur="2s" fill="freeze"/>
      </g>
    </svg>
    """

    render_result, scene, _ = _render(svg)

    assert "<p:attrName>display</p:attrName>" not in render_result.slide_xml
    assert "<p:attrName>visibility</p:attrName>" not in render_result.slide_xml
    assert "<p:attrName>style.visibility</p:attrName>" in render_result.slide_xml
    assert '<p:strVal val="visible"/>' in render_result.slide_xml
    assert scene.metadata is not None
    animation_definitions = scene.metadata["animation"]["definitions"]
    assert all(defn["target_attribute"] != "display" for defn in animation_definitions)


def test_animate_elem_31_t_rewrites_display_to_native_visibility() -> None:
    svg = Path("tests/svg/animate-elem-31-t.svg").read_text(encoding="utf-8")

    render_result, scene, _ = _render(svg)

    assert "<p:attrName>display</p:attrName>" not in render_result.slide_xml
    assert "<p:attrName>visibility</p:attrName>" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:attrName>style.visibility</p:attrName>") >= 8
    assert '<p:strVal val="hidden"/>' in render_result.slide_xml
    assert '<p:strVal val="visible"/>' in render_result.slide_xml
    assert scene.metadata is not None
    targets = {
        definition["target_attribute"]
        for definition in scene.metadata["animation"]["definitions"]
    }
    assert "display" not in targets
    assert "visibility" not in targets


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
    assert "<p:attrName>ppt_x</p:attrName>" in render_result.slide_xml
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
    assert 'tm="50000"' in render_result.slide_xml  # 0.5 * 100000
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


def test_color_animation_segments_multi_keyframe_values() -> None:
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
    assert render_result.slide_xml.count("<p:animClr") == 2
    assert 'a:srgbClr val="FF0000"' in render_result.slide_xml
    assert 'a:srgbClr val="00FF00"' in render_result.slide_xml
    assert 'a:srgbClr val="0000FF"' in render_result.slide_xml
    assert 'dur="500"' in render_result.slide_xml
    assert 'dur="1500"' in render_result.slide_xml


def test_color_discrete_calc_mode_emits_set_steps() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
      <rect id="rect1" width="10" height="10" fill="#000">
        <animate attributeName="fill" values="#ff0000;#00ff00;#0000ff" keyTimes="0;0.4;1" calcMode="discrete" dur="1s" begin="0s"/>
      </rect>
    </svg>
    """

    render_result, _, _ = _render(svg)

    assert "<p:tavLst" not in render_result.slide_xml
    assert "<p:animClr" not in render_result.slide_xml
    assert render_result.slide_xml.count("<p:set>") == 3
    assert render_result.slide_xml.count("<p:clrVal>") == 3


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
