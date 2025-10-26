"""Smart font converter integration layer."""

from __future__ import annotations

import importlib
import logging
from dataclasses import replace
from typing import Any, Iterable

from svg2ooxml.ir.text import TextFrame
from svg2ooxml.services.fonts.service import FontMatch, FontQuery

_LOGGER = logging.getLogger(__name__)

GENERIC_FALLBACKS = {
    "sans-serif": ("Arial", "Helvetica", "Segoe UI", "Calibri"),
    "serif": ("Times New Roman", "Georgia", "Cambria"),
    "monospace": ("Courier New", "Consolas", "Source Code Pro"),
    "cursive": ("Comic Sans MS", "Brush Script MT"),
    "fantasy": ("Impact", "Papyrus"),
}


class BasicSmartFontConverter:
    """Lightweight stand-in for advanced font conversion pipelines."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or _LOGGER

    def convert(self, frame: TextFrame, context: dict[str, Any] | None = None) -> TextFrame:
        context = context or {}
        metadata = dict(frame.metadata)
        smart_meta = metadata.setdefault("smart_font", {})

        smart_meta.setdefault("strategy", "basic")
        smart_meta.setdefault("confidence", 0.0)
        policy = context.get("policy")
        if policy is not None:
            smart_meta.setdefault("policy_hint", getattr(policy, "name", str(policy)))

        services = context.get("services")
        if services is not None:
            smart_meta.setdefault("services_linked", True)

        return replace(frame, metadata=metadata)


def load_svg2pptx_converter(services: Any, *, logger: logging.Logger) -> Any | None:
    """Attempt to load the svg2pptx smart font converter if available."""

    module_candidates = [
        "svg2pptx.core.converters.font.smart_converter",
        "svg2pptx.core.map.font_mapper_adapter",
    ]

    for module_name in module_candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        converter_cls = getattr(module, "SmartFontConverter", None)
        if converter_cls is None:
            continue
        try:
            return converter_cls(services, None)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Failed to initialise SmartFontConverter from %s: %s", module_name, exc)
    return None


def build_smart_font_converter(services: Any, *, logger: logging.Logger | None = None) -> Any:
    """Return the richest smart font converter available."""

    logger = logger or _LOGGER
    converter = load_svg2pptx_converter(services, logger=logger)
    if converter is not None:
        logger.debug("svg2pptx SmartFontConverter loaded successfully")
        return converter
    logger.debug("Falling back to native SmartFontConverter")
    return SmartFontConverter(services, None, logger=logger)


class SmartFontConverter:
    """Evaluate text runs to determine concrete font usage."""

    def __init__(self, services: Any, policy: Any | None = None, *, logger: logging.Logger | None = None) -> None:
        self._services = services
        self._policy = policy
        self._logger = logger or _LOGGER

    def convert(self, frame: TextFrame, context: dict[str, Any] | None = None) -> TextFrame:
        context = context or {}
        services = context.get("services") or self._services
        font_service = None
        if services is not None:
            font_service = getattr(services, "font_service", None)
            if font_service is None and hasattr(services, "resolve"):
                font_service = services.resolve("font")

        runs = frame.runs or []
        if not runs:
            return frame

        enriched = []
        matched = 0

        for index, run in enumerate(runs):
            report: dict[str, Any] = {
                "index": index,
                "requested_family": run.font_family,
                "weight": run.weight_class,
                "style": "italic" if run.italic else "normal",
                "language": run.language,
            }

            match = None
            if font_service is not None:
                try:
                    query = FontQuery(
                        family=run.font_family,
                        weight=run.weight_class,
                        style="italic" if run.italic else "normal",
                        language=run.language,
                        fallback_chain=_fallback_chain(run.font_family),
                    )
                    match = font_service.find_font(query)
                except Exception as exc:  # pragma: no cover - defensive
                    self._logger.debug("Font lookup failed for %s: %s", run.font_family, exc)

            if match is not None:
                matched += 1
                _apply_match_metadata(report, match)
            else:
                report["resolved_family"] = None

            enriched.append(report)

        total = len(runs)
        confidence = matched / total if total else 0.0

        metadata = dict(frame.metadata)
        smart_meta = metadata.setdefault("smart_font", {})
        smart_meta.update(
            {
                "strategy": "lookup",
                "confidence": round(confidence, 3),
                "matched_runs": matched,
                "total_runs": total,
                "runs": enriched,
            }
        )

        if self._policy is not None:
            smart_meta.setdefault("policy_hint", getattr(self._policy, "name", str(self._policy)))

        return replace(frame, metadata=metadata)


def _apply_match_metadata(report: dict[str, Any], match: FontMatch) -> None:
    report["resolved_family"] = match.family
    report["source"] = match.found_via
    report["embedding_allowed"] = match.embedding_allowed
    report["weight"] = match.weight
    report["style"] = match.style
    if match.path:
        report["path"] = match.path
    if match.metadata:
        report["provider_metadata"] = dict(match.metadata)


def _fallback_chain(family: str) -> tuple[str, ...]:
    generic = GENERIC_FALLBACKS.get(family.lower())
    if generic:
        return generic
    # Provide minimal universal fallbacks.
    return ("Arial", "Helvetica", "Times New Roman", "Courier New")


__all__ = ["BasicSmartFontConverter", "SmartFontConverter", "build_smart_font_converter"]
