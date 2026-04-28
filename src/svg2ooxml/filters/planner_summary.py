"""Filter plan summary and metadata serialisation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PlanSummaryMixin:
    """Produce lightweight debug summaries for render filter plans."""

    def plan_summary(self, plan: Any) -> list[dict[str, Any]]:
        return [
            {
                key: value
                for key, value in {
                    "tag": primitive_plan.tag,
                    "inputs": list(primitive_plan.inputs),
                    "result": primitive_plan.result_name,
                    "metadata": (
                        self.serialise_plan_extra(primitive_plan.extra)
                        if primitive_plan.extra
                        else None
                    ),
                }.items()
                if value is not None and value != []
            }
            for primitive_plan in plan.primitives
        ]

    @staticmethod
    def serialise_plan_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
        def _coerce(value: Any) -> Any:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, Mapping):
                return {k: _coerce(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_coerce(v) for v in value]
            return str(value)

        return {key: _coerce(val) for key, val in extra.items()}

    @staticmethod
    def plan_has_turbulence(plan: Any) -> bool:
        return any(
            primitive.tag.lower() == "feturbulence" for primitive in plan.primitives
        )


__all__ = ["PlanSummaryMixin"]
