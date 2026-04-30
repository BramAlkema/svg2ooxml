"""Clipping and masking hooks for the IR converter."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.traversal import clipping
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.geometry_utils import is_axis_aligned
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef


class ClippingHooksMixin:
    """Mixin providing clipping and masking resolution methods."""

    def _resolve_clip_ref(
        self,
        element: etree._Element,
        *,
        use_transform: Matrix2D | None = None,
    ) -> ClipRef | None:
        clip_ref = clipping.resolve_clip_ref(
            element,
            clip_definitions=self._clip_definitions,
            services=self._services,
            logger=self._logger,
            tolerance=DEFAULT_TOLERANCE,
            is_axis_aligned=is_axis_aligned,
            use_transform=use_transform,
        )
        if clip_ref is not None:
            decision = (
                "emf"
                if getattr(clip_ref.strategy, "value", clip_ref.strategy) == "emf"
                else "native"
            )
            metadata = {
                "clip_id": clip_ref.clip_id,
                "strategy": getattr(clip_ref.strategy, "value", clip_ref.strategy),
                "custom_geometry": bool(clip_ref.custom_geometry_xml),
            }
            if clip_ref.clip_id:
                self._clip_usage.add(clip_ref.clip_id)
                self._trace_stage(
                    "clip_applied",
                    stage="clip",
                    subject=clip_ref.clip_id,
                    metadata={
                        "strategy": metadata["strategy"],
                        "custom_geometry": metadata["custom_geometry"],
                    },
                )
            self._trace_geometry_decision(element, decision, metadata)
        return clip_ref

    def _resolve_mask_ref(
        self, element: etree._Element
    ) -> tuple[MaskRef | None, MaskInstance | None]:
        mask_ref, mask_instance = clipping.resolve_mask_ref(
            element, mask_info=self._mask_info
        )
        if mask_ref is not None and mask_ref.mask_id:
            self._mask_usage.add(mask_ref.mask_id)
            self._trace_stage(
                "mask_applied",
                stage="mask",
                subject=mask_ref.mask_id,
                metadata={"has_definition": mask_ref.definition is not None},
            )
        return mask_ref, mask_instance
