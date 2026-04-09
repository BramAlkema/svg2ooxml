"""Helpers for building PPTX packages from SVG fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.drawingml.writer import DrawingMLWriter
from svg2ooxml.io.pptx_assembly import PPTXPackageBuilder
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.services import configure_services


class VisualBuildError(RuntimeError):
    """Raised when a visual test cannot build the PPTX fixture."""


@dataclass
class PptxBuildResult:
    pptx_path: Path
    slide_count: int


class PptxBuilder:
    """Build PPTX packages from SVG snippets using the svg2ooxml pipeline."""

    def __init__(
        self,
        *,
        filter_strategy: str | None = "resvg",
        geometry_mode: str | None = "resvg",
        slide_size_mode: str | None = "same",
        allow_promotion: bool = True,
    ) -> None:
        self._parser = SVGParser(ParserConfig())
        self._writer = DrawingMLWriter()
        self._builder = PPTXPackageBuilder(slide_size_mode=slide_size_mode)
        self._filter_strategy = filter_strategy
        self._geometry_mode = geometry_mode
        self._slide_size_mode = slide_size_mode or "same"
        self._allow_promotion = allow_promotion

    def build_from_svg(
        self,
        svg_text: str,
        output_path: Path,
        *,
        source_path: Path | None = None,
        tracer: Any | None = None,
        animations: list | None = None, # Add animations parameter
    ) -> PptxBuildResult:
        """Parse *svg_text*, convert to IR, and materialise a PPTX file."""

        parse_result = self._parser.parse(
            svg_text, 
            source_path=str(source_path) if source_path else None,
            tracer=tracer,
        )
        if not parse_result.success or parse_result.svg_root is None:
            raise VisualBuildError(f"SVG parsing failed: {parse_result.error_message}")

        # Use the parser's services which includes the StyleResolver with loaded CSS rules.
        services = parse_result.services
        if services is None:
            services = configure_services(
                filter_strategy=self._filter_strategy,
                geometry_mode=self._geometry_mode,
            )
        else:
            if self._filter_strategy and services.filter_service is not None:
                services.filter_service.set_strategy(self._filter_strategy)
            
            # Apply policy overrides
            policy_context = getattr(services, "policy_context", None)
            if policy_context:
                # Update geometry policy
                if self._geometry_mode:
                    geometry_policy = policy_context.get("geometry", {})
                    if isinstance(geometry_policy, dict):
                        geometry_policy["geometry_mode"] = self._geometry_mode
                
                # Update filter policy to disable promotions if requested
                if not self._allow_promotion:
                    filter_policy = policy_context.get("filter", {})
                    if isinstance(filter_policy, dict):
                        # Disable global promotion
                        filter_policy["allow_promotion"] = False
                        # Also disable promotion for all primitives
                        primitives = filter_policy.setdefault("primitives", {})
                        # Apply to common primitives
                        for p in ["fediffuselighting", "fespecularlighting", "fegaussianblur", "feoffset", "fecomposite", "feblend"]:
                            primitives.setdefault(p, {})["allow_promotion"] = False

        if parse_result.width_px is not None:
            setattr(services, "viewport_width", parse_result.width_px)
        if parse_result.height_px is not None:
            setattr(services, "viewport_height", parse_result.height_px)

        scene = convert_parser_output(parse_result, services=services, tracer=tracer)
        render_result = self._writer.render_scene_from_ir(
            scene,
            tracer=tracer,
            animations=animations,
        )

        pptx_path = self._builder.build_from_results(
            [render_result],
            output_path,
            slide_size_mode=self._slide_size_mode,
        )
        return PptxBuildResult(pptx_path=pptx_path, slide_count=1)


__all__ = ["PptxBuilder", "PptxBuildResult", "VisualBuildError"]
