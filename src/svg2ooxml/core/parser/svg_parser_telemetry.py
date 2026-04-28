"""Tracing and metrics summary helpers for the public SVG parser."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from svg2ooxml.core.tracing import ConversionTracer


class SVGParserTelemetryMixin:
    @staticmethod
    def _trace(
        tracer: ConversionTracer | None,
        action: str,
        *,
        metadata: dict[str, Any] | None = None,
        subject: str | None = None,
    ) -> None:
        if tracer is None:
            return
        tracer.record_stage_event(
            stage="parser",
            action=action,
            metadata=metadata,
            subject=subject,
        )

    @staticmethod
    def _summarize_preparse(
        report: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not report:
            return None
        summary: dict[str, object] = {}
        for key in (
            "removed_bom",
            "encoding_replacements",
            "added_xml_declaration",
            "error",
        ):
            if key in report:
                summary[key] = report[key]

        by_char = report.get("encoding_replacements_by_char")
        if isinstance(by_char, dict) and by_char:
            summary["encoding_replacements_by_char"] = by_char

        return summary or None

    @staticmethod
    def _summarize_normalization(
        changes: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if not changes:
            return None

        summary: dict[str, object] = {}
        if "namespaces_fixed" in changes:
            summary["namespaces_fixed"] = bool(changes["namespaces_fixed"])

        attributes_added = changes.get("attributes_added")
        if isinstance(attributes_added, list) and attributes_added:
            summary["attributes_added"] = len(attributes_added)

        structure_fixes = changes.get("structure_fixes")
        if isinstance(structure_fixes, list) and structure_fixes:
            summary["structure_fixes"] = len(structure_fixes)

        summary["whitespace_normalized"] = bool(
            changes.get("whitespace_normalized")
        )
        summary["comments_filtered"] = bool(changes.get("comments_filtered"))

        encoding_fixes = changes.get("encoding_fixes")
        if isinstance(encoding_fixes, list) and encoding_fixes:
            total_encoding_fix = 0
            for entry in encoding_fixes:
                if isinstance(entry, dict):
                    total_encoding_fix += int(entry.get("text_nodes", 0))
                    total_encoding_fix += int(entry.get("tail_nodes", 0))
                    total_encoding_fix += int(entry.get("attributes", 0))
            if total_encoding_fix:
                summary["encoding_fix_nodes"] = total_encoding_fix

        log_entries = changes.get("log")
        if isinstance(log_entries, list) and log_entries:
            action_counts: dict[str, int] = {}
            for entry in log_entries:
                if isinstance(entry, dict):
                    action = entry.get("action")
                    if isinstance(action, str) and action:
                        action_counts[action] = action_counts.get(action, 0) + 1
            if action_counts:
                summary["actions"] = action_counts

        return summary or None


__all__ = ["SVGParserTelemetryMixin"]
