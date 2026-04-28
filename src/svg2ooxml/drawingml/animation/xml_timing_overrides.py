"""Post-build timing override helpers for animation XML."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_P, p_sub

from .timing_conditions import append_end_conditions
from .timing_values import format_duration_ms

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import BeginTrigger


class AnimationTimingOverrideMixin:
    """Apply SMIL timing overrides to generated animation fragments."""

    def apply_native_timing_overrides(
        self,
        *,
        par: etree._Element,
        repeat_duration_ms: int | None = None,
        restart: str | None = None,
        end_triggers: list[BeginTrigger] | None = None,
        default_target_shape: str | None = None,
    ) -> None:
        """Apply optional SMIL timing fields to a generated animation fragment."""
        ctn = par.find(f"{{{NS_P}}}cTn")
        if ctn is None:
            return

        if restart in {"always", "whenNotActive", "never"}:
            ctn.set("restart", restart)

        if repeat_duration_ms is not None:
            repeat_duration = format_duration_ms(repeat_duration_ms, minimum=1)
            targets = self._repeat_duration_targets(par, fallback=ctn)
            for target in targets:
                target.set("repeatDur", repeat_duration)

        if end_triggers:
            end_cond_lst = ctn.find(f"{{{NS_P}}}endCondLst")
            if end_cond_lst is None:
                end_cond_lst = p_sub(ctn, "endCondLst")
            self._append_end_conditions(
                end_cond_lst=end_cond_lst,
                end_triggers=end_triggers,
                default_target_shape=default_target_shape,
            )

    @staticmethod
    def _repeat_duration_targets(
        par: etree._Element,
        *,
        fallback: etree._Element,
    ) -> list[etree._Element]:
        targets = [
            ctn
            for ctn in par.iter(f"{{{NS_P}}}cTn")
            if ctn.get("repeatCount") is not None
        ]
        return targets or [fallback]

    def _append_end_conditions(
        self,
        *,
        end_cond_lst: etree._Element,
        end_triggers: list[BeginTrigger],
        default_target_shape: str | None,
    ) -> None:
        """Append native-compatible end conditions from parsed SMIL end tokens."""
        append_end_conditions(
            end_cond_lst=end_cond_lst,
            end_triggers=end_triggers,
            default_target_shape=default_target_shape,
        )


__all__ = ["AnimationTimingOverrideMixin"]
