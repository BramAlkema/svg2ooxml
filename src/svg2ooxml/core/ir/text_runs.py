"""Text run collection and resvg metadata helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.core.ir.text.font_metrics import create_run_from_style, merge_runs
from svg2ooxml.core.ir.text.layout import (
    normalize_text_segment,
    record_text_path_reference,
    resolve_text_length,
)
from svg2ooxml.ir.text import Run


class TextRunsMixin:
    """Legacy XML text-run helpers used by ``TextConverter``."""

    def _compute_text_style_with_inheritance(
        self, element: etree._Element
    ) -> dict[str, Any]:
        parent_style: dict[str, Any] | None = None
        parent = element.getparent()
        if isinstance(parent, etree._Element) and isinstance(parent.tag, str):
            parent_style = self._compute_text_style_with_inheritance(parent)
        return self._context.style_resolver.compute_text_style(
            element,
            context=self._context.css_context,
            parent_style=parent_style,
        )

    def _collect_text_runs(
        self,
        element: etree._Element,
        base_style: Mapping[str, Any],
    ) -> tuple[list[Run], dict[str, Any]]:
        segments: list[tuple[Mapping[str, Any], str]] = []
        metadata: dict[str, Any] = {}

        def visit(
            node: etree._Element, style: Mapping[str, Any], preserve_space: bool
        ) -> None:
            xml_space = node.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            text_segment = normalize_text_segment(
                node.text, preserve_space=node_preserve
            )
            if text_segment:
                segments.append((dict(style), text_segment))

            for child in node:
                local = self._context.local_name(getattr(child, "tag", "")).lower()
                if local == "tspan":
                    child_style = self._context.style_resolver.compute_text_style(
                        child,
                        context=self._context.css_context,
                        parent_style=style,
                    )
                    visit(child, child_style, node_preserve)
                elif local == "textpath":
                    child_style = self._context.style_resolver.compute_text_style(
                        child,
                        context=self._context.css_context,
                        parent_style=style,
                    )
                    href = child.get("{http://www.w3.org/1999/xlink}href") or child.get(
                        "href"
                    )
                    record_text_path_reference(
                        href,
                        metadata,
                        context=self._context,
                        text_path_positioner=self._text_path_positioner,
                    )
                    visit(child, child_style, node_preserve)
                else:
                    visit(child, style, node_preserve)
                tail_segment = normalize_text_segment(
                    child.tail, preserve_space=node_preserve
                )
                if tail_segment:
                    segments.append((dict(style), tail_segment))

        visit(element, base_style, False)

        runs: list[Run] = []
        for style, segment in segments:
            run = self._create_run_from_style(segment, style)
            if run.text:
                runs.append(run)
        runs = merge_runs(runs)
        return runs, metadata

    def _create_run_from_style(self, text: str, style: Mapping[str, Any]) -> Run:
        return create_run_from_style(
            text, style, resolve_text_length_fn=self._resolve_text_length
        )

    def _resolve_text_length(
        self,
        value: str | None,
        *,
        axis: str,
        font_size_pt: float,
    ) -> float:
        return resolve_text_length(
            value, axis=axis, font_size_pt=font_size_pt, context=self._context
        )

    def _attach_resvg_text_metadata(
        self,
        resvg_node: Any,
        metadata: dict[str, Any],
        *,
        text_scale: float = 1.0,
    ) -> None:
        if not hasattr(resvg_node, "text_content"):
            return
        try:
            from svg2ooxml.core.resvg.text.drawingml_generator import (
                DrawingMLTextGenerator,
            )
            from svg2ooxml.core.resvg.text.layout_analyzer import TextLayoutAnalyzer
        except Exception:
            return

        resvg_meta: dict[str, Any] = metadata.setdefault("resvg_text", {})
        analysis = TextLayoutAnalyzer().analyze(resvg_node)
        resvg_meta["complexity"] = analysis.complexity
        if analysis.details:
            resvg_meta["details"] = analysis.details
        resvg_meta["is_plain"] = analysis.is_plain

        if metadata.get("text_path_id"):
            resvg_meta["strategy"] = "text_path"
            return
        if not analysis.is_plain:
            resvg_meta["strategy"] = "emf"
            return

        paint_resolver = None
        tree = getattr(self._context, "resvg_tree", None)
        if tree is not None:
            from svg2ooxml.paint.resvg_bridge import _resolve_paint_reference

            def paint_resolver(ref):
                return _resolve_paint_reference(ref, tree)

        generator = DrawingMLTextGenerator(
            font_service=self._context.services.resolve("font"),
            embedding_engine=self._context.services.resolve("font_embedding"),
            paint_resolver=paint_resolver,
            text_scale=text_scale,
        )
        try:
            runs_xml = generator.generate_runs_xml(resvg_node)
        except Exception:
            resvg_meta["strategy"] = "error"
            return

        if runs_xml:
            resvg_meta["strategy"] = "runs"
            resvg_meta["runs_xml"] = runs_xml
        else:
            resvg_meta["strategy"] = "empty"
