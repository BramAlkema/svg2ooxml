"""DrawingML text-run XML helpers."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, color_choice, to_string
from svg2ooxml.ir.text import Run, TextFrame


def build_runs_xml(runs: Iterable[Run], register_navigation=None) -> str:
    fragments: list[str] = []
    for run in runs:
        text = (run.text or "").replace("\r\n", "\n").replace("\r", "\n")
        parts = text.split("\n") if text else [""]
        navigation_handler = None
        if register_navigation is not None and getattr(run, "navigation", None) is not None:
            navigation_registered = False

            def _navigation_factory(segment_text: str, _run=run):
                nonlocal navigation_registered
                if navigation_registered:
                    return None
                navigation_registered = True
                return register_navigation(_run.navigation, segment_text)

            navigation_handler = _navigation_factory
        for index, segment in enumerate(parts):
            if index > 0:
                fragments.append("<a:br/>")
            fragments.append(run_fragment(run, segment, navigation_handler))
    return "".join(fragments)


def resolve_runs_xml(frame: TextFrame, register_navigation) -> str:
    # Prefer IR runs when they carry attributes (lang, font_variant) that
    # the pre-built resvg runs_xml would miss.
    ir_runs = frame.runs or []
    has_enriched_attrs = any(
        getattr(run, "language", None) or getattr(run, "font_variant", None)
        for run in ir_runs
    )
    if not has_enriched_attrs:
        resvg_runs = _resvg_runs_xml(frame, register_navigation)
        if resvg_runs:
            return resvg_runs
    runs_xml = build_runs_xml(ir_runs, register_navigation=register_navigation)
    if not runs_xml:
        runs_xml = build_runs_xml(
            [Run(text="", font_family="Arial", font_size_pt=12.0)],
            register_navigation=register_navigation,
        )
    return runs_xml


def run_fragment(run: Run, text_segment: str, navigation_factory) -> str:
    size = max(100, int(round(run.font_size_pt * 100)))
    attributes = [f'sz="{size}"']
    if run.bold:
        attributes.append('b="1"')
    if run.italic:
        attributes.append('i="1"')
    if run.underline:
        attributes.append('u="sng"')
    if run.strike:
        attributes.append('strike="sng"')
    if getattr(run, "kerning", None) is not None:
        kern_value = int(round(float(run.kerning) * 1000))
        attributes.append(f'kern="{kern_value}"')
    effective_spacing = getattr(run, "letter_spacing", None)
    word_spacing = getattr(run, "word_spacing", None)
    if word_spacing is not None and text_segment:
        # Approximate word-spacing by distributing it as extra letter-spacing
        # proportional to the number of spaces vs total characters.
        space_count = text_segment.count(" ")
        if space_count > 0 and len(text_segment) > 1:
            extra_per_char = (float(word_spacing) * space_count) / (len(text_segment) - 1)
            base = float(effective_spacing) if effective_spacing is not None else 0.0
            effective_spacing = base + extra_per_char
    if effective_spacing is not None:
        spacing_value = int(round(float(effective_spacing) * 1000))
        attributes.append(f'spc="{spacing_value}"')
    font_variant = getattr(run, "font_variant", None)
    if font_variant == "small-caps":
        attributes.append('cap="small"')
    baseline_shift = getattr(run, "baseline_shift", 0.0)
    if baseline_shift:
        # DrawingML baseline is percentage × 1000 (e.g. 30000 = 30% superscript).
        baseline_pct = int(round(baseline_shift * 1000))
        attributes.append(f'baseline="{baseline_pct}"')
    language = getattr(run, "language", None)
    if language:
        attributes.append(f'lang="{language}"')

    rgb = (run.rgb or "000000").upper()
    font_family = str(run.font_family or "Arial")
    east_asian = str(getattr(run, "east_asian_font", "") or run.font_family or "Arial")
    complex_script = str(getattr(run, "complex_script_font", "") or run.font_family or "Arial")

    r = a_elem("r")
    rPr = a_elem("rPr")
    for attr_str in attributes:
        if "=" in attr_str:
            key, val = attr_str.split("=", 1)
            rPr.set(key, val.strip('"'))

    # Outline must come before fill in DrawingML text runs.
    if run.has_stroke:
        ln_elem = a_sub(rPr, "ln", w=str(px_to_emu(run.stroke_width_px or 1.0)))
        strokeFill = a_sub(ln_elem, "solidFill")
        stroke_rgb = (run.stroke_rgb or "000000").upper()
        stroke_alpha = opacity_to_ppt(run.stroke_opacity or 1.0)
        strokeFill.append(
            color_choice(
                stroke_rgb,
                alpha=stroke_alpha if stroke_alpha < 100000 else None,
                theme_color=getattr(run, "stroke_theme_color", None),
            )
        )

    solidFill = a_sub(rPr, "solidFill")
    fill_alpha = opacity_to_ppt(run.fill_opacity)
    solidFill.append(
        color_choice(
            rgb,
            alpha=fill_alpha if fill_alpha < 100000 else None,
            theme_color=getattr(run, "theme_color", None),
        )
    )

    a_sub(rPr, "latin", typeface=font_family)
    a_sub(rPr, "ea", typeface=east_asian)
    a_sub(rPr, "cs", typeface=complex_script)

    if navigation_factory is not None:
        nav_elem = navigation_factory(text_segment)
        if nav_elem is not None:
            rPr.append(nav_elem)

    r.append(rPr)

    text_value = text_segment
    preserve = False
    if text_value == "":
        text_value = " "
        preserve = True
    elif text_value.startswith(" ") or text_value.endswith(" "):
        preserve = True

    t = a_elem("t")
    t.text = text_value
    if preserve:
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    r.append(t)

    return to_string(r)


def _resvg_runs_xml(frame: TextFrame, register_navigation) -> str:
    metadata = getattr(frame, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    resvg_text = metadata.get("resvg_text")
    if not isinstance(resvg_text, dict):
        return ""
    if resvg_text.get("strategy") != "runs":
        return ""
    runs_xml = resvg_text.get("runs_xml")
    if not isinstance(runs_xml, str) or not runs_xml.strip():
        return ""
    if register_navigation is not None and _frame_has_navigation(frame):
        return ""
    return runs_xml


def _frame_has_navigation(frame: TextFrame) -> bool:
    return any(getattr(run, "navigation", None) is not None for run in frame.runs or [])


__all__ = ["build_runs_xml", "resolve_runs_xml", "run_fragment"]
