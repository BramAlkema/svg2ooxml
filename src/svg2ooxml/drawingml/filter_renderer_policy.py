"""Policy helpers for DrawingML filter rendering."""

from __future__ import annotations

from svg2ooxml.filters.base import FilterContext, FilterResult


class FilterRendererPolicyMixin:
    def _strategy_from_policy(self, result: FilterResult, policy: dict[str, object] | None) -> str:
        if policy is None:
            return "native"
        prefer_vector = bool(policy.get("prefer_emf_blend_modes"))
        if prefer_vector and result.metadata.get("filter_type") in {"blend", "component_transfer"}:
            return "vector"
        return "native"

    def _policy_from_context(self, context: FilterContext | None) -> dict[str, object] | None:
        if context is None:
            return None
        options = getattr(context, "options", None)
        if isinstance(options, dict):
            policy_opts = options.get("policy")
            if isinstance(policy_opts, dict):
                filter_policy = policy_opts.get("filter")
                if isinstance(filter_policy, dict):
                    return {**policy_opts, **filter_policy}
                return policy_opts
        return None


__all__ = ["FilterRendererPolicyMixin"]
