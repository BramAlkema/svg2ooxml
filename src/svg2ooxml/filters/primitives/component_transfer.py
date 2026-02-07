"""feComponentTransfer filter primitive."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number

CHANNELS = {"r", "g", "b", "a"}


@dataclass
class ComponentFunction:
    channel: str
    func_type: str
    params: dict[str, object] = field(default_factory=dict)


class ComponentTransferFilter(Filter):
    primitive_tags = ("feComponentTransfer",)
    filter_type = "component_transfer"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        functions = self._parse_functions(primitive)
        metadata: dict[str, object] = {
            "filter_type": self.filter_type,
            "functions": [
                {
                    "channel": func.channel,
                    "type": func.func_type,
                    "params": dict(func.params),
                }
                for func in functions
            ],
        }
        summary = ";".join(self._summarise_function(func) for func in functions) or "identity"
        metadata["summary"] = summary
        metadata["native_support"] = False
        drawingml = ""
        warnings = ["feComponentTransfer rendered via EMF fallback"]
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback="emf",
            metadata=metadata,
            warnings=warnings,
        )

    def _parse_functions(self, primitive: etree._Element) -> list[ComponentFunction]:
        functions: list[ComponentFunction] = []
        for node in primitive:
            if not hasattr(node, "tag"):
                continue
            channel = self._channel_for_func(node)
            if channel is None:
                continue
            func_type = (node.get("type") or "identity").strip().lower()
            params: dict[str, object] = {}
            if func_type in {"table", "discrete"}:
                params["values"] = self._parse_float_list(node.get("tableValues"))
            elif func_type == "linear":
                params["slope"] = parse_number(node.get("slope"), default=1.0)
                params["intercept"] = parse_number(node.get("intercept"))
            elif func_type == "gamma":
                params["amplitude"] = parse_number(node.get("amplitude"), default=1.0)
                params["exponent"] = parse_number(node.get("exponent"), default=1.0)
                params["offset"] = parse_number(node.get("offset"))
            func = ComponentFunction(channel=channel, func_type=func_type, params=params)
            functions.append(func)
        return functions

    def _channel_for_func(self, node: etree._Element) -> str | None:
        local_name = node.tag.split("}", 1)[-1] if "}" in node.tag else node.tag
        if not local_name.lower().startswith("fefunc"):
            return None
        suffix = local_name[-1].lower()
        if suffix not in CHANNELS:
            return None
        return suffix

    def _parse_float_list(self, payload: str | None) -> list[float]:
        if not payload:
            return []
        values: list[float] = []
        for token in payload.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        return values

    def _summarise_function(self, func: ComponentFunction) -> str:
        parts = [func.channel, func.func_type]
        for key, value in func.params.items():
            parts.append(f"{key}={self._stringify(value)}")
        return ",".join(parts)

    def _stringify(self, value: object) -> str:
        if isinstance(value, list):
            return " ".join(self._stringify(item) for item in value)
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)


__all__ = ["ComponentTransferFilter"]
