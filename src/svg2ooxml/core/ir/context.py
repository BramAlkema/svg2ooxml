"""Shared state and tracing helpers for IR conversion."""

from __future__ import annotations

import logging
import locale
import os
from typing import Any, Iterable, Mapping, TYPE_CHECKING

from svg2ooxml.css import StyleResolver
from svg2ooxml.common.style.resolver import StyleContext as CSSStyleContext
from svg2ooxml.core.masks import MaskProcessor
from svg2ooxml.core.parser import UnitConverter
from svg2ooxml.core.styling import StyleExtractor
from svg2ooxml.core.traversal.viewbox import ViewportEngine
from svg2ooxml.policy import PolicyContext, PolicyEngine
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - imported for type hints only
    from svg2ooxml.core.parser import ParseResult
    from svg2ooxml.core.tracing import ConversionTracer


class IRConverterContext:
    """Hold shared conversion state and tracing utilities."""

    def __init__(
        self,
        *,
        services: ConversionServices,
        unit_converter: UnitConverter | None = None,
        style_resolver: StyleResolver | None = None,
        logger: logging.Logger | None = None,
        policy_engine: PolicyEngine | None = None,
        policy_context: PolicyContext | None = None,
        tracer: "ConversionTracer | None" = None,
    ) -> None:
        self.services = services
        self.unit_converter = unit_converter or UnitConverter()

        resolved_style_resolver = style_resolver
        if resolved_style_resolver is None and services is not None:
            try:
                resolved_style_resolver = services.resolve("style_resolver")
            except AttributeError:  # pragma: no cover - defensive fallback
                resolved_style_resolver = None

        self.style_resolver = resolved_style_resolver or StyleResolver(self.unit_converter)
        self.style_extractor = StyleExtractor(self.style_resolver)
        self.tracer = tracer
        self.style_extractor.set_tracer(tracer)
        self.logger = logger or logging.getLogger(__name__)
        self.system_languages = self._detect_system_languages()

        self.policy_engine = policy_engine
        self.policy_context = policy_context

        self.css_context: CSSStyleContext | None = None
        self.conversion_context = None
        self.element_index: dict[str, Any] = {}
        self.viewport_engine = ViewportEngine()
        self._preloaded_stage_events: list[tuple[str, str, str | None, dict[str, Any]]] = []

        mask_processor = None
        if services is not None:
            mask_processor = getattr(services, "mask_processor", None)
            if mask_processor is None and hasattr(services, "resolve"):
                mask_processor = services.resolve("mask_processor")
        self.mask_processor = mask_processor or MaskProcessor(services)
        if hasattr(self.mask_processor, "set_tracer"):
            self.mask_processor.set_tracer(tracer)

        emf_adapter = None
        if services is not None:
            emf_adapter = getattr(services, "emf_path_adapter", None)
            if emf_adapter is None and hasattr(services, "resolve"):
                emf_adapter = services.resolve("emf_path_adapter")
        self.emf_adapter = emf_adapter

    def reset_tracer(self) -> None:
        if self.tracer is None:
            return
        self.tracer.reset()
        if self._preloaded_stage_events:
            for stage, action, subject, metadata in self._preloaded_stage_events:
                self.tracer.record_stage_event(
                    stage=stage,
                    action=action,
                    subject=subject,
                    metadata=metadata,
                )
            self._preloaded_stage_events.clear()

    def preload_stage_events(
        self,
        events: Iterable[tuple[str, str, str | None, dict[str, Any]]],
    ) -> None:
        self._preloaded_stage_events = [
            (stage, action, subject, dict(metadata) if isinstance(metadata, dict) else {})
            for stage, action, subject, metadata in events
        ]

    def prepare_style_context(self, result: "ParseResult") -> None:
        style_context = result.style_context
        if style_context is not None:
            conversion = style_context.conversion
            viewport_width = style_context.viewport_width
            viewport_height = style_context.viewport_height
        else:
            viewport_width = result.width_px or 0.0
            viewport_height = result.height_px or 0.0
            conversion = self.unit_converter.create_context(
                width=viewport_width,
                height=viewport_height,
                font_size=12.0,
                parent_width=viewport_width,
                parent_height=viewport_height,
            )
        self.css_context = CSSStyleContext(
            conversion=conversion,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
        self.conversion_context = conversion

    def trace_stage(
        self,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
        stage: str = "converter",
    ) -> None:
        tracer = self.tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage=stage, action=action, metadata=metadata, subject=subject)

    def trace_geometry_decision(
        self,
        element,
        decision: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        tracer = self.tracer
        if tracer is None:
            return
        tag = ""
        if hasattr(element, "tag") and isinstance(element.tag, str):
            tag = element.tag.split("}", 1)[-1]
        element_id = element.get("id") if hasattr(element, "get") else None
        tracer.record_geometry_decision(
            tag=tag,
            decision=decision,
            metadata=dict(metadata) if isinstance(metadata, dict) else metadata,
            element_id=element_id,
        )

    def policy_options(self, target: str) -> Mapping[str, Any] | None:
        if self.policy_context is None:
            return None
        return self.policy_context.get(target)

    def attach_policy_metadata(
        self,
        metadata: dict[str, Any],
        target: str,
        *,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        options = extra if extra is not None else self.policy_options(target)
        if not options:
            return
        policy_meta = metadata.setdefault("policy", {})
        existing = policy_meta.get(target)
        option_dict = dict(options)
        if existing is None:
            policy_meta[target] = option_dict
        else:
            existing.update(option_dict)

    @staticmethod
    def bitmap_fallback_limits(options: Mapping[str, Any] | None) -> tuple[int | None, int | None]:
        default_area = 1_500_000
        default_side = 2048

        def _coerce(value: Any, default: int) -> int | None:
            if value is None:
                return default
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return default
            if numeric <= 0:
                return None
            return int(numeric)

        if not options:
            return default_area, default_side

        max_area = _coerce(options.get("max_bitmap_area"), default_area)
        max_side = _coerce(options.get("max_bitmap_side"), default_side)
        return max_area, max_side

    @staticmethod
    def matrix_from_transform(transform_str: str | None):
        from svg2ooxml.common.geometry import Matrix2D, parse_transform_list

        if not transform_str or not transform_str.strip():
            return Matrix2D.identity()
        try:
            matrix = parse_transform_list(transform_str.strip())
        except Exception:
            matrix = None
        if matrix is None:
            return Matrix2D.identity()
        return matrix

    @staticmethod
    def local_name(tag: Any) -> str:
        if not isinstance(tag, str):
            return ""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def normalize_href_reference(href: str | None) -> str | None:
        if not href:
            return None
        token = href.strip()
        if token.startswith("url(") and token.endswith(")"):
            token = token[4:-1].strip().strip("\"'")
        if token.startswith("#"):
            return token[1:]
        return None

    @staticmethod
    def make_namespaced_tag(reference, local: str) -> str:
        tag = reference.tag
        if isinstance(tag, str) and "}" in tag:
            namespace = tag.split("}", 1)[0][1:]
            return f"{{{namespace}}}{local}"
        return local

    def _detect_system_languages(self) -> tuple[str, ...]:
        override = os.getenv("SVG2OOXML_SYSTEM_LANGUAGE")
        tokens: list[str] = []
        if override:
            tokens.extend(token.strip() for token in override.split(",") if token.strip())
        else:
            tokens.extend(self._environment_languages())
            if not tokens:
                detected = self._current_locale_language()
                if detected:
                    tokens.append(detected)
        if not tokens:
            tokens.append("en")

        normalized: list[str] = []
        for token in tokens:
            canonical = token.replace("_", "-").lower()
            if canonical and canonical not in normalized:
                normalized.append(canonical)
            if "-" in canonical:
                primary = canonical.split("-", 1)[0]
                if primary and primary not in normalized:
                    normalized.append(primary)
        if "en" not in normalized:
            normalized.append("en")
        return tuple(normalized)

    @staticmethod
    def _environment_languages() -> tuple[str, ...]:
        candidates: list[str] = []
        env_vars = ("LC_ALL", "LC_MESSAGES", "LC_CTYPE", "LANG", "LANGUAGE")
        for name in env_vars:
            raw_value = os.environ.get(name)
            if not raw_value:
                continue
            parts = raw_value.split(":") if name == "LANGUAGE" else [raw_value]
            for part in parts:
                token = part.strip()
                if not token:
                    continue
                normalized = locale.normalize(token)
                language = normalized.split(".", 1)[0] if normalized else ""
                if language and language not in candidates:
                    candidates.append(language)
            if candidates:
                break
        return tuple(candidates)

    @staticmethod
    def _current_locale_language() -> str | None:
        try:
            language, _ = locale.getlocale()
        except Exception:
            return None
        return language


__all__ = ["IRConverterContext"]
