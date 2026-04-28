"""Animation trigger and timing models."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.ir.animation_enums import BeginTriggerType, FillMode


@dataclass(slots=True)
class BeginTrigger:
    """Structured begin trigger extracted from SMIL begin expressions."""

    trigger_type: BeginTriggerType
    delay_seconds: float = 0.0
    target_element_id: str | None = None
    event_name: str | None = None
    repeat_iteration: int | str | None = None
    access_key: str | None = None
    wallclock_value: str | None = None


@dataclass(slots=True)
class AnimationTiming:
    """Timing definition for a single animation."""

    begin: float = 0.0
    duration: float = 1.0
    repeat_count: int | str = 1
    repeat_duration: float | None = None
    fill_mode: FillMode = FillMode.REMOVE
    begin_triggers: list[BeginTrigger] | None = None
    end_triggers: list[BeginTrigger] | None = None

    def get_end_time(self) -> float:
        """Return the absolute end time for an animation."""
        if self.repeat_count == "indefinite":
            repeated_end = float("inf")
        else:
            try:
                count = int(self.repeat_count)
                repeated_end = self.begin + (self.duration * count)
            except (ValueError, TypeError):
                repeated_end = self.begin + self.duration

        if self.repeat_duration is None:
            return repeated_end

        return min(repeated_end, self.begin + self.repeat_duration)

    def is_active_at_time(self, time: float) -> bool:
        """Return True when the animation is active at the supplied time."""
        if time < self.begin:
            return False

        end_time = self.get_end_time()
        if end_time == float("inf"):
            return True

        return time <= end_time

    def get_local_time(self, global_time: float) -> float:
        """Map a global timestamp to the animation's 0-1 progress space."""
        if global_time < self.begin:
            return 0.0

        local_time = global_time - self.begin
        if self.repeat_count == "indefinite":
            return (local_time % self.duration) / self.duration

        try:
            count = int(self.repeat_count)
            total_duration = self.duration * count
            if local_time >= total_duration:
                return 1.0 if self.fill_mode == FillMode.FREEZE else 0.0

            cycle_time = local_time % self.duration
            return cycle_time / self.duration
        except (ValueError, TypeError):
            if local_time >= self.duration:
                return 1.0 if self.fill_mode == FillMode.FREEZE else 0.0
            return local_time / self.duration


__all__ = ["AnimationTiming", "BeginTrigger"]
