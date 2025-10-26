"""Optional bridge for SmartFont-like converters."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Mapping, Sequence

from svg2ooxml.ir.text import Run, TextFrame


class SmartFontBridge:
    """Integrate optional smart font converters into the text pipeline."""

    def __init__(self, services, logger: logging.Logger) -> None:
        self._logger = logger
        self._services = services
        self._converter = None
        if services is not None:
            self._converter = getattr(services, "resolve", lambda name, default=None: None)(
                "smart_font_converter"
            )

    def enhance_frame(
        self,
        frame: TextFrame,
        runs: Sequence[Run],
        decision: Any,
    ) -> TextFrame:
        if not self._converter:
            return frame

        context = {
            "policy": decision,
            "services": self._services,
        }
        try:
            result = self._converter.convert(frame, context)
        except Exception as exc:  # pragma: no cover - optional dependency
            self._logger.debug("Smart font converter failed: %s", exc)
            return frame

        if isinstance(result, TextFrame):
            return result

        metadata = dict(frame.metadata)
        smart_meta = metadata.setdefault("smart_font", {})
        if isinstance(result, Mapping):
            smart_meta.update({key: value for key, value in result.items() if key not in {"runs", "frame"}})
            replaced_frame = result.get("frame")
            if isinstance(replaced_frame, TextFrame):
                base_frame = replace(replaced_frame, metadata=metadata)
                return base_frame
        elif hasattr(result, "__dict__"):
            smart_meta["strategy"] = getattr(result, "strategy", "unknown")
            smart_meta["confidence"] = getattr(result, "confidence", 0.0)

        return replace(frame, metadata=metadata)


__all__ = ["SmartFontBridge"]
