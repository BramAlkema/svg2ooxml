"""feComponentTransfer filter primitive."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from svg2ooxml.common.conversions.scale import PPT_SCALE, scale_to_ppt
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.filters.base import (
    Filter,
    FilterContext,
    FilterResult,
    stitch_blip_transforms,
)
from svg2ooxml.filters.utils import parse_float_list, parse_number

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
        policy = context.policy
        enable_native_color_transforms = bool(policy.get("enable_native_color_transforms", False))
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
        if self._is_identity_transfer(functions):
            metadata["native_support"] = True
            metadata["no_op"] = True
            metadata["reason"] = "identity_transfer"
            return FilterResult(
                success=True,
                drawingml="",
                fallback=None,
                metadata=metadata,
            )

        if enable_native_color_transforms:
            stitch_blip_transforms(metadata, self._blip_transform_candidates(functions))

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
                params["values"] = parse_float_list(node.get("tableValues"))
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
        tag_name = local_name(node.tag)
        if not tag_name.lower().startswith("fefunc"):
            return None
        suffix = tag_name[-1].lower()
        if suffix not in CHANNELS:
            return None
        return suffix

    def _summarise_function(self, func: ComponentFunction) -> str:
        parts = [func.channel, func.func_type]
        for key, value in func.params.items():
            parts.append(f"{key}={self._stringify(value)}")
        return ",".join(parts)

    def _is_identity_transfer(self, functions: list[ComponentFunction]) -> bool:
        if not functions:
            return True
        return all(self._is_identity_function(func) for func in functions)

    def _is_identity_function(self, func: ComponentFunction) -> bool:
        func_type = func.func_type
        params = func.params
        tol = 1e-6
        if func_type == "identity":
            return True
        if func_type == "linear":
            slope = float(params.get("slope", 1.0))
            intercept = float(params.get("intercept", 0.0))
            return abs(slope - 1.0) <= tol and abs(intercept) <= tol
        if func_type == "gamma":
            amplitude = float(params.get("amplitude", 1.0))
            exponent = float(params.get("exponent", 1.0))
            offset = float(params.get("offset", 0.0))
            return (
                abs(amplitude - 1.0) <= tol
                and abs(exponent - 1.0) <= tol
                and abs(offset) <= tol
            )
        if func_type in {"table", "discrete"}:
            values = params.get("values")
            if not isinstance(values, list) or len(values) < 2:
                return True
            n = len(values)
            for idx, raw in enumerate(values):
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    return False
                expected = idx / (n - 1)
                if abs(val - expected) > 1e-4:
                    return False
            return True
        return False

    def _stringify(self, value: object) -> str:
        if isinstance(value, list):
            return " ".join(self._stringify(item) for item in value)
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    @staticmethod
    def _blip_transform_candidates(functions: list[ComponentFunction]) -> list[dict[str, object]]:
        # Allowlist only: alpha linear scaling without offset.
        if len(functions) != 1:
            return []
        func = functions[0]
        if func.channel != "a" or func.func_type != "linear":
            return []
        try:
            slope = float(func.params.get("slope", 1.0))
            intercept = float(func.params.get("intercept", 0.0))
        except (TypeError, ValueError):
            return []
        if abs(intercept) > 1e-6:
            return []
        amount = max(0, min(scale_to_ppt(slope), 200000))
        if amount == PPT_SCALE:
            return []
        return [{"tag": "alphaModFix", "amt": amount}]


__all__ = ["ComponentTransferFilter"]
