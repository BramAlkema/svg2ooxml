"""Animation scene snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AnimationScene:
    """Snapshot of all animated element states at a specific time."""

    time: float
    element_states: dict[str, dict[str, str]] = field(default_factory=dict)

    def set_element_property(
        self, element_id: str, property_name: str, value: str
    ) -> None:
        state = self.element_states.setdefault(element_id, {})
        state[property_name] = value

    def get_element_property(self, element_id: str, property_name: str) -> str | None:
        return self.element_states.get(element_id, {}).get(property_name)

    def get_all_animated_elements(self) -> list[str]:
        return list(self.element_states.keys())

    def merge_scene(self, other: AnimationScene) -> None:
        for element_id, properties in other.element_states.items():
            state = self.element_states.setdefault(element_id, {})
            state.update(properties)


__all__ = ["AnimationScene"]
