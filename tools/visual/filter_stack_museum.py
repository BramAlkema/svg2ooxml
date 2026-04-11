"""Generate a PPTX museum of stacked SVG filter recipes for PowerPoint study."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter


@dataclass(frozen=True)
class StackVariant:
    label: str
    note: str
    filter_xml: str


@dataclass(frozen=True)
class StackCase:
    case_id: str
    title: str
    chain: str
    rationale: str
    scene_kind: str
    variants: tuple[StackVariant, ...]


def build_stack_cases() -> list[StackCase]:
    """Return the first curated museum set, seeded from measured filter usage."""

    return [
        StackCase(
            case_id="flood_blur_merge_halo",
            title="Flood + Blur + Merge Halo",
            chain="feFlood > feGaussianBlur > feMerge",
            rationale="Common editable halo candidate. We want to learn when PowerPoint glow is close enough.",
            scene_kind="halo_badge",
            variants=(
                StackVariant(
                    label="Soft halo",
                    note="blur 2, alpha 0.45",
                    filter_xml=(
                        "<filter id='f1' x='-40%' y='-40%' width='180%' height='180%'>"
                        "  <feFlood flood-color='#5BC0EB' flood-opacity='0.45' result='flood'/>"
                        "  <feGaussianBlur in='flood' stdDeviation='2' result='halo'/>"
                        "  <feMerge><feMergeNode in='halo'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Medium halo",
                    note="blur 6, alpha 0.75",
                    filter_xml=(
                        "<filter id='f2' x='-60%' y='-60%' width='220%' height='220%'>"
                        "  <feFlood flood-color='#00C2FF' flood-opacity='0.75' result='flood'/>"
                        "  <feGaussianBlur in='flood' stdDeviation='6' result='halo'/>"
                        "  <feMerge><feMergeNode in='halo'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Heavy halo",
                    note="blur 12, alpha 1.0",
                    filter_xml=(
                        "<filter id='f3' x='-80%' y='-80%' width='260%' height='260%'>"
                        "  <feFlood flood-color='#9B5DE5' flood-opacity='1.0' result='flood'/>"
                        "  <feGaussianBlur in='flood' stdDeviation='12' result='halo'/>"
                        "  <feMerge><feMergeNode in='halo'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="flood_blend_modes",
            title="Flood + Blend Modes",
            chain="feFlood > feBlend",
            rationale="High-frequency paint logic family. We need to see which modes look plausibly editable via fillOverlay-style output.",
            scene_kind="blend_texture",
            variants=(
                StackVariant(
                    label="Multiply",
                    note="warm tint over source",
                    filter_xml=(
                        "<filter id='f1' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feFlood flood-color='#E76F51' flood-opacity='0.55' result='flood'/>"
                        "  <feBlend in='SourceGraphic' in2='flood' mode='multiply'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Screen",
                    note="cool lift over source",
                    filter_xml=(
                        "<filter id='f2' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feFlood flood-color='#4CC9F0' flood-opacity='0.65' result='flood'/>"
                        "  <feBlend in='SourceGraphic' in2='flood' mode='screen'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Lighten",
                    note="green lift over source",
                    filter_xml=(
                        "<filter id='f3' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feFlood flood-color='#80ED99' flood-opacity='0.6' result='flood'/>"
                        "  <feBlend in='SourceGraphic' in2='flood' mode='lighten'/>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="gradient_blend_approximation",
            title="Gradient Blend Approximation",
            chain="SourceGraphic > feBlend",
            rationale="Diagnostic companion for feBlend. Direct should refuse gradient-average overlay approximation; mimic may use it.",
            scene_kind="blend_texture",
            variants=(
                StackVariant(
                    label="Multiply self",
                    note="gradient average overlay",
                    filter_xml=(
                        "<filter id='f1' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feBlend in='SourceGraphic' in2='SourceGraphic' mode='multiply'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Screen self",
                    note="gradient average overlay",
                    filter_xml=(
                        "<filter id='f2' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feBlend in='SourceGraphic' in2='SourceGraphic' mode='screen'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Lighten self",
                    note="gradient average overlay",
                    filter_xml=(
                        "<filter id='f3' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feBlend in='SourceGraphic' in2='SourceGraphic' mode='lighten'/>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="flood_composite_ops",
            title="Flood + Composite Operators",
            chain="feFlood > feComposite",
            rationale="Another top family. This shows which operator semantics survive or collapse inside PowerPoint.",
            scene_kind="composite_cutout",
            variants=(
                StackVariant(
                    label="Over",
                    note="tint layer over source",
                    filter_xml=(
                        "<filter id='f1' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feFlood flood-color='#F94144' flood-opacity='0.45' result='flood'/>"
                        "  <feComposite in='flood' in2='SourceGraphic' operator='over'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="In",
                    note="flood masked by source alpha",
                    filter_xml=(
                        "<filter id='f2' x='-10%' y='-10%' width='120%' height='120%'>"
                        "  <feFlood flood-color='#F9C74F' flood-opacity='0.9' result='flood'/>"
                        "  <feComposite in='flood' in2='SourceGraphic' operator='in'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Out",
                    note="outside-only layer",
                    filter_xml=(
                        "<filter id='f3' x='-35%' y='-35%' width='170%' height='170%'>"
                        "  <feFlood flood-color='#577590' flood-opacity='0.9' result='flood'/>"
                        "  <feComposite in='flood' in2='SourceGraphic' operator='out'/>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="shadow_stack",
            title="Offset + Blur + Flood + Composite + Merge",
            chain="feOffset > feGaussianBlur > feFlood > feComposite > feMerge",
            rationale="Classic shadow stack. Strong candidate for editable shadow/glow synthesis.",
            scene_kind="shadow_corner",
            variants=(
                StackVariant(
                    label="Short shadow",
                    note="dx 6, dy 6, blur 3",
                    filter_xml=(
                        "<filter id='f1' x='-35%' y='-35%' width='170%' height='190%'>"
                        "  <feOffset in='SourceAlpha' dx='6' dy='6' result='off'/>"
                        "  <feGaussianBlur in='off' stdDeviation='3' result='blur'/>"
                        "  <feFlood flood-color='#0B132B' flood-opacity='0.35' result='color'/>"
                        "  <feComposite in='color' in2='blur' operator='in' result='shadow'/>"
                        "  <feMerge><feMergeNode in='shadow'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Soft shadow",
                    note="dx 10, dy 10, blur 6",
                    filter_xml=(
                        "<filter id='f2' x='-45%' y='-45%' width='190%' height='220%'>"
                        "  <feOffset in='SourceAlpha' dx='10' dy='10' result='off'/>"
                        "  <feGaussianBlur in='off' stdDeviation='6' result='blur'/>"
                        "  <feFlood flood-color='#1D3557' flood-opacity='0.32' result='color'/>"
                        "  <feComposite in='color' in2='blur' operator='in' result='shadow'/>"
                        "  <feMerge><feMergeNode in='shadow'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Glow-shadow",
                    note="dx 0, dy 12, blur 10",
                    filter_xml=(
                        "<filter id='f3' x='-55%' y='-55%' width='210%' height='240%'>"
                        "  <feOffset in='SourceAlpha' dx='0' dy='12' result='off'/>"
                        "  <feGaussianBlur in='off' stdDeviation='10' result='blur'/>"
                        "  <feFlood flood-color='#457B9D' flood-opacity='0.4' result='color'/>"
                        "  <feComposite in='color' in2='blur' operator='in' result='shadow'/>"
                        "  <feMerge><feMergeNode in='shadow'/><feMergeNode in='SourceGraphic'/></feMerge>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="diffuse_lighting_composite",
            title="Diffuse Lighting + Composite",
            chain="feDiffuseLighting > feComposite",
            rationale="Lighting is costly and often rasterized. We want direct visual evidence of what a glow-based mimic can or cannot fake.",
            scene_kind="diffuse_relief",
            variants=(
                StackVariant(
                    label="Warm top-left",
                    note="az 315, el 45",
                    filter_xml=(
                        "<filter id='f1' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feDiffuseLighting in='SourceAlpha' surfaceScale='4' diffuseConstant='1.1' lighting-color='#FFD6A5' result='light'>"
                        "    <feDistantLight azimuth='315' elevation='45'/>"
                        "  </feDiffuseLighting>"
                        "  <feComposite in='light' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Cool side light",
                    note="az 20, el 35",
                    filter_xml=(
                        "<filter id='f2' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feDiffuseLighting in='SourceAlpha' surfaceScale='4' diffuseConstant='1.2' lighting-color='#CDEBFF' result='light'>"
                        "    <feDistantLight azimuth='20' elevation='35'/>"
                        "  </feDiffuseLighting>"
                        "  <feComposite in='light' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="High sun",
                    note="az 270, el 70",
                    filter_xml=(
                        "<filter id='f3' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feDiffuseLighting in='SourceAlpha' surfaceScale='5' diffuseConstant='1.0' lighting-color='#FFF2B2' result='light'>"
                        "    <feDistantLight azimuth='270' elevation='70'/>"
                        "  </feDiffuseLighting>"
                        "  <feComposite in='light' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
            ),
        ),
        StackCase(
            case_id="specular_lighting_composite",
            title="Specular Lighting + Composite",
            chain="feSpecularLighting > feComposite",
            rationale="Specular is where fake editable lighting usually breaks. This belongs in the museum before more implementation.",
            scene_kind="specular_relief",
            variants=(
                StackVariant(
                    label="Broad sheen",
                    note="exp 12, white",
                    filter_xml=(
                        "<filter id='f1' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feSpecularLighting in='SourceAlpha' surfaceScale='4' specularConstant='1' specularExponent='12' lighting-color='#FFFFFF' result='spec'>"
                        "    <feDistantLight azimuth='320' elevation='45'/>"
                        "  </feSpecularLighting>"
                        "  <feComposite in='spec' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Tight sheen",
                    note="exp 24, ice blue",
                    filter_xml=(
                        "<filter id='f2' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feSpecularLighting in='SourceAlpha' surfaceScale='5' specularConstant='1.1' specularExponent='24' lighting-color='#DFF4FF' result='spec'>"
                        "    <feDistantLight azimuth='25' elevation='38'/>"
                        "  </feSpecularLighting>"
                        "  <feComposite in='spec' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
                StackVariant(
                    label="Hot sparkle",
                    note="exp 35, warm",
                    filter_xml=(
                        "<filter id='f3' x='-20%' y='-20%' width='140%' height='140%'>"
                        "  <feSpecularLighting in='SourceAlpha' surfaceScale='6' specularConstant='1.2' specularExponent='35' lighting-color='#FFF2D8' result='spec'>"
                        "    <feDistantLight azimuth='300' elevation='55'/>"
                        "  </feSpecularLighting>"
                        "  <feComposite in='spec' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
                        "</filter>"
                    ),
                ),
            ),
        ),
    ]


def build_case_svg(case: StackCase) -> str:
    """Return one SVG museum page for a stack family."""

    if len(case.variants) != 3:
        raise ValueError(f"Stack case {case.case_id} must define exactly 3 variants")

    filter_defs = "\n".join(f"      {variant.filter_xml}" for variant in case.variants)
    panel_titles = [
        ("Reference", "unfiltered source", None),
        (case.variants[0].label, case.variants[0].note, "f1"),
        (case.variants[1].label, case.variants[1].note, "f2"),
        (case.variants[2].label, case.variants[2].note, "f3"),
    ]

    panel_markup: list[str] = []
    panel_xs = [40, 365, 690, 1015]
    panel_y = 170
    panel_w = 305
    panel_h = 500
    for x, (label, note, filter_id) in zip(panel_xs, panel_titles, strict=True):
        scene_markup = _build_panel_scene(case.scene_kind, filter_id)
        panel_markup.append(
            f"""
    <g transform="translate({x},{panel_y})">
      <rect x="0" y="0" width="{panel_w}" height="{panel_h}" rx="28" fill="#FFFDF8" stroke="#D8D1C5" stroke-width="2"/>
      <text x="24" y="42" font-size="24" font-weight="700" fill="#1E1E1E">{_escape_xml(label)}</text>
      <text x="24" y="72" font-size="16" fill="#6B6257">{_escape_xml(note)}</text>
      <g transform="translate(38,126)">
        <rect x="0" y="0" width="232" height="186" rx="24" fill="#F3EFE7" stroke="#ECE5D8"/>
{scene_markup}
      </g>
    </g>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1360" height="760" viewBox="0 0 1360 760">
  <defs>
    <linearGradient id="subjectGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#4D96FF"/>
      <stop offset="55%" stop-color="#5EEAD4"/>
      <stop offset="100%" stop-color="#FFE082"/>
    </linearGradient>
    <linearGradient id="shadowGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#6CCFF6"/>
      <stop offset="100%" stop-color="#F4D35E"/>
    </linearGradient>
    <linearGradient id="blendGrad" x1="0%" y1="10%" x2="100%" y2="90%">
      <stop offset="0%" stop-color="#3A86FF"/>
      <stop offset="45%" stop-color="#8338EC"/>
      <stop offset="100%" stop-color="#FFBE0B"/>
    </linearGradient>
    <linearGradient id="compositeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#FF7B00"/>
      <stop offset="50%" stop-color="#FFB703"/>
      <stop offset="100%" stop-color="#219EBC"/>
    </linearGradient>
    <linearGradient id="reliefGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#355070"/>
      <stop offset="100%" stop-color="#6D597A"/>
    </linearGradient>
    <linearGradient id="specGrad" x1="0%" y1="20%" x2="100%" y2="80%">
      <stop offset="0%" stop-color="#264653"/>
      <stop offset="55%" stop-color="#335C67"/>
      <stop offset="100%" stop-color="#3A506B"/>
    </linearGradient>
{filter_defs}
  </defs>
  <rect x="0" y="0" width="1360" height="760" fill="#F6F2EA"/>
  <text x="40" y="56" font-size="34" font-weight="700" fill="#1E1E1E">{_escape_xml(case.title)}</text>
  <text x="40" y="90" font-size="18" fill="#554B42">{_escape_xml(case.chain)}</text>
  <text x="40" y="120" font-size="18" fill="#7A7065">{_escape_xml(case.rationale)}</text>
  {"".join(panel_markup)}
</svg>
"""


def _build_panel_scene(scene_kind: str, filter_id: str | None) -> str:
    filter_attr = f" filter='url(#{filter_id})'" if filter_id else ""
    builders = {
        "halo_badge": _scene_halo_badge,
        "shadow_corner": _scene_shadow_corner,
        "blend_texture": _scene_blend_texture,
        "composite_cutout": _scene_composite_cutout,
        "diffuse_relief": _scene_diffuse_relief,
        "specular_relief": _scene_specular_relief,
    }
    try:
        builder = builders[scene_kind]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unknown scene kind: {scene_kind}") from exc
    return builder(filter_attr)


def _scene_halo_badge(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <circle cx="96" cy="74" r="60" fill="#F7F1E7" stroke="#E4DBCF" stroke-width="2"/>
          <g{filter_attr}>
            <path fill-rule="evenodd"
                  d="M96 74 m-52 0 a52 52 0 1 0 104 0 a52 52 0 1 0 -104 0
                     M96 74 m-24 0 a24 24 0 1 1 48 0 a24 24 0 1 1 -48 0"
                  fill="url(#subjectGrad)" stroke="#17324D" stroke-width="7"/>
            <circle cx="165" cy="118" r="16" fill="#F28F3B" stroke="#17324D" stroke-width="5"/>
          </g>
        </g>"""


def _scene_shadow_corner(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <path d="M26 24 H184" stroke="#D7CEC2" stroke-width="2" stroke-dasharray="7 6"/>
          <path d="M26 24 V146" stroke="#D7CEC2" stroke-width="2" stroke-dasharray="7 6"/>
          <rect x="48" y="42" width="126" height="86" rx="20" fill="none" stroke="#E6DDD2" stroke-width="2"/>
          <g{filter_attr}>
            <path d="M46 36 h86 c18 0 32 14 32 32 v16 h-58 c-10 0 -18 8 -18 18 v24 H46 Z"
                  fill="url(#shadowGrad)" stroke="#17324D" stroke-width="7" stroke-linejoin="round"/>
            <circle cx="158" cy="114" r="13" fill="#F4A261" stroke="#17324D" stroke-width="5"/>
          </g>
        </g>"""


def _scene_blend_texture(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <rect x="26" y="20" width="180" height="134" rx="28" fill="#FAF6EF" stroke="#E6DDD2" stroke-width="2"/>
          <g{filter_attr}>
            <rect x="38" y="30" width="156" height="114" rx="26" fill="url(#blendGrad)" stroke="#17324D" stroke-width="8"/>
            <path d="M52 110 L104 40 H138 L86 110 Z" fill="#0B132B" opacity="0.36"/>
            <rect x="60" y="44" width="90" height="14" rx="7" fill="#FFFFFF" opacity="0.45"/>
            <circle cx="95" cy="100" r="23" fill="#06D6A0" opacity="0.4"/>
            <circle cx="150" cy="92" r="25" fill="#FF006E" opacity="0.45"/>
          </g>
        </g>"""


def _scene_composite_cutout(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <path d="M116 18 V154" stroke="#D7CEC2" stroke-width="2" stroke-dasharray="6 6"/>
          <g{filter_attr}>
            <path d="M116 32 L132 66 L170 70 L142 95 L150 136 L116 116 L82 136 L90 95 L62 70 L100 66 Z"
                  fill="url(#compositeGrad)" stroke="#17324D" stroke-width="7" stroke-linejoin="round"/>
            <circle cx="60" cy="124" r="14" fill="#8ECAE6" stroke="#17324D" stroke-width="5"/>
          </g>
        </g>"""


def _scene_diffuse_relief(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <rect x="26" y="20" width="180" height="134" rx="28" fill="#FAF6EF" stroke="#E6DDD2" stroke-width="2"/>
          <g{filter_attr}>
            <rect x="38" y="30" width="156" height="114" rx="24" fill="url(#reliefGrad)" stroke="#17324D" stroke-width="8"/>
            <rect x="56" y="42" width="18" height="90" rx="9" fill="#FFFFFF" opacity="0.18"/>
            <rect x="82" y="42" width="18" height="90" rx="9" fill="#FFFFFF" opacity="0.35"/>
            <rect x="108" y="42" width="18" height="90" rx="9" fill="#FFFFFF" opacity="0.55"/>
            <rect x="134" y="42" width="18" height="90" rx="9" fill="#FFFFFF" opacity="0.75"/>
            <circle cx="164" cy="70" r="18" fill="#FFFFFF" opacity="0.42"/>
          </g>
        </g>"""


def _scene_specular_relief(filter_attr: str) -> str:
    return f"""
        <g transform="translate(18,16)">
          <rect x="26" y="20" width="180" height="134" rx="28" fill="#FAF6EF" stroke="#E6DDD2" stroke-width="2"/>
          <g{filter_attr}>
            <rect x="40" y="38" width="152" height="98" rx="49" fill="url(#specGrad)" stroke="#17324D" stroke-width="8"/>
            <circle cx="74" cy="86" r="14" fill="#FFFFFF" opacity="0.22"/>
            <circle cx="110" cy="68" r="10" fill="#FFFFFF" opacity="0.68"/>
            <circle cx="142" cy="96" r="16" fill="#FFFFFF" opacity="0.9"/>
            <path d="M62 56 C86 38 124 38 156 64" fill="none" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round" opacity="0.3"/>
          </g>
        </g>"""


def build_manifest(cases: list[StackCase], *, render_tiers: bool) -> dict[str, Any]:
    """Return a serializable manifest for generated museum artifacts."""

    return {
        "name": "filter-stack-museum",
        "render_tiers": render_tiers,
        "case_count": len(cases),
        "expected_slide_count": len(cases) * (4 if render_tiers else 1),
        "cases": [asdict(case) for case in cases],
    }


def write_museum(
    output_dir: Path,
    *,
    render_tiers: bool = True,
) -> Path:
    """Generate the museum deck and supporting source files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    svg_dir = output_dir / "svgs"
    svg_dir.mkdir(parents=True, exist_ok=True)

    cases = build_stack_cases()
    pages: list[SvgPageSource] = []
    for case in cases:
        svg_text = build_case_svg(case)
        svg_path = svg_dir / f"{case.case_id}.svg"
        svg_path.write_text(svg_text, encoding="utf-8")
        pages.append(
            SvgPageSource(
                svg_text=svg_text,
                title=case.title,
                name=case.case_id,
                metadata={
                    "source_path": str(svg_path),
                    "museum_case": case.case_id,
                    "museum_chain": case.chain,
                },
            )
        )

    exporter = SvgToPptxExporter()
    pptx_path = output_dir / "filter-stack-museum.pptx"
    result = exporter.convert_pages(
        pages,
        pptx_path,
        render_tiers=render_tiers,
    )

    manifest = build_manifest(cases, render_tiers=render_tiers)
    manifest["pptx_path"] = str(result.pptx_path)
    manifest["actual_slide_count"] = result.slide_count
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        _build_readme(cases, render_tiers=render_tiers, slide_count=result.slide_count),
        encoding="utf-8",
    )
    return result.pptx_path


def _build_readme(cases: list[StackCase], *, render_tiers: bool, slide_count: int) -> str:
    tier_note = (
        "Each logical case expands to 4 slides: Direct, Mimic, EMF, Bitmap."
        if render_tiers
        else "Each logical case emits a single slide."
    )
    lines = [
        "# Filter Stack Museum",
        "",
        tier_note,
        "",
        f"- Cases: {len(cases)}",
        f"- Slides: {slide_count}",
        "",
        "## Families",
        "",
    ]
    for case in cases:
        lines.append(f"- `{case.case_id}`: {case.chain} — {case.rationale}")
    lines.append("")
    return "\n".join(lines)


def _escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return (
        Path(__file__).resolve().parents[2]
        / "reports"
        / "visual"
        / "powerpoint"
        / f"filter-stack-museum-{stamp}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a PPTX museum of stacked SVG filter recipes.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_default_output_dir(),
        help="Directory where the PPTX, SVG sources, and manifest will be written.",
    )
    parser.add_argument(
        "--no-render-tiers",
        action="store_true",
        help="Emit one slide per case instead of direct/mimic/emf/bitmap tiered slides.",
    )
    args = parser.parse_args()

    pptx_path = write_museum(
        args.output_dir,
        render_tiers=not args.no_render_tiers,
    )
    print(pptx_path)


if __name__ == "__main__":
    main()
