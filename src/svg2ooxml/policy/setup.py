"""Policy engine setup helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .engine import PolicyEngine, PolicyProvider
from .providers.animation import AnimationPolicyProvider
from .providers.filter import FilterPolicyProvider
from .providers.image import ImagePolicyProvider
from .providers.mask import MaskPolicyProvider
from .providers.path import PathPolicyProvider
from .providers.text import TextPolicyProvider
from .targets import TargetRegistry

DEFAULT_PROVIDERS: Sequence[PolicyProvider] = (
    ImagePolicyProvider(),
    TextPolicyProvider(),
    PathPolicyProvider(),
    MaskPolicyProvider(),
    FilterPolicyProvider(),
    AnimationPolicyProvider(),
)


def build_policy_engine(
    policy_name: str | None = None,
    *,
    providers: Iterable[PolicyProvider] | None = None,
    target_registry: TargetRegistry | None = None,
) -> PolicyEngine:
    """Create a policy engine pre-wired with default providers."""

    registry = target_registry or TargetRegistry.default()
    engine = PolicyEngine(
        providers=list(providers) if providers is not None else list(DEFAULT_PROVIDERS),
        target_registry=registry,
    )
    if policy_name:
        engine.set_policy(policy_name)
    return engine


__all__ = ["DEFAULT_PROVIDERS", "build_policy_engine"]
