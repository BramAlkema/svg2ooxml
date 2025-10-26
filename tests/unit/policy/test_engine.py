"""Tests for the policy engine and providers."""

from svg2ooxml.policy.engine import PolicyEngine
from svg2ooxml.policy.providers.image import ImagePolicyProvider
from svg2ooxml.policy.targets import PolicyTarget, TargetRegistry


class CountingProvider(ImagePolicyProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def evaluate(self, target, options):
        self.calls.append(target.name)
        return super().evaluate(target, options)


def test_engine_uses_registered_providers_once_per_target() -> None:
    registry = TargetRegistry()
    registry.register(PolicyTarget("image"))
    provider = CountingProvider()

    engine = PolicyEngine(providers=[provider], target_registry=registry)

    context = engine.evaluate()

    assert provider.calls == ["image"]
    assert "image" in context.selections


def test_engine_uses_loaded_policy_options() -> None:
    provider = CountingProvider()
    engine = PolicyEngine(providers=[provider])
    engine.set_policy("high")

    context = engine.evaluate(PolicyTarget("image"))

    assert context.get("image")["colorspace_normalization"] == "perceptual"
