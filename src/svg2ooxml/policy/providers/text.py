"""Text policy provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from svg2ooxml.policy.engine import PolicyProvider
from svg2ooxml.policy.targets import PolicyTarget
from svg2ooxml.policy.text_policy import TextPolicyDecision, resolve_text_policy


class TextPolicyProvider(PolicyProvider):
    """Return structured text policy decisions based on global quality presets."""

    def supports(self, target: PolicyTarget) -> bool:
        return target.name == "text"

    def evaluate(self, target: PolicyTarget, options: Mapping[str, Any]) -> Mapping[str, Any]:
        quality = str(options.get("quality", "balanced"))
        overrides = {
            key: value for key, value in options.items() if key.startswith("text.")
        }

        env_dirs = os.getenv("SVG2OOXML_FONT_DIRS")
        if env_dirs and "text.font_dirs" not in overrides:
            overrides["text.font_dirs"] = env_dirs

        disable_wordart = os.getenv("SVG2OOXML_DISABLE_WORDART")
        if disable_wordart and "text.wordart.enable" not in overrides:
            if disable_wordart.strip().lower() in {"1", "true", "yes", "on"}:
                overrides["text.wordart.enable"] = False

        decision: TextPolicyDecision = resolve_text_policy(quality, overrides or None)

        payload = decision.to_mapping()
        payload["decision"] = decision
        return payload


__all__ = ["TextPolicyProvider"]
