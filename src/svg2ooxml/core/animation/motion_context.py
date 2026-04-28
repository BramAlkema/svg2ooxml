"""Motion-space and transform metadata helpers for SMIL parsing."""

from __future__ import annotations

from collections.abc import Sequence

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.ir.animation import AnimationType, TransformType

from . import targeting
from .parser_types import ANIMATION_TAGS

_LOCAL_MOTION_ATTRIBUTES = frozenset(
    {
        "x",
        "y",
        "cx",
        "cy",
        "x1",
        "x2",
        "y1",
        "y2",
        "width",
        "height",
        "w",
        "h",
        "rx",
        "ry",
    }
)

_TRANSFORM_TYPES = {
    "translate": TransformType.TRANSLATE,
    "scale": TransformType.SCALE,
    "rotate": TransformType.ROTATE,
    "skewx": TransformType.SKEWX,
    "skewy": TransformType.SKEWY,
    "matrix": TransformType.MATRIX,
}


def resolve_motion_path_reference(
    animation_element: etree._Element,
    href: str,
) -> str | None:
    """Resolve <mpath href="#..."> references to path data."""
    target_id = local_url_id(href)
    if not target_id:
        return None

    root = animation_element.getroottree().getroot()
    target = targeting.lookup_element_by_id(root, target_id)
    if target is None:
        return None

    if etree.QName(target).localname.lower() != "path":
        return None

    path_data = target.get("d")
    if not path_data:
        return None
    return path_data.strip()


def resolve_motion_space_matrix(
    animation_element: etree._Element,
    *,
    animation_type: AnimationType,
    target_attribute: str | None = None,
    transform_type: TransformType | None = None,
    animation_tags: Sequence[str] = ANIMATION_TAGS,
) -> tuple[float, float, float, float, float, float] | None:
    if not animation_uses_local_motion_space(
        animation_type=animation_type,
        target_attribute=target_attribute,
        transform_type=transform_type,
    ):
        return None

    target = targeting.resolve_target_element(
        animation_element,
        animation_tags=animation_tags,
    )
    if target is None:
        return None

    matrix = Matrix2D.identity()
    lineage = [*target.iterancestors()][::-1]
    lineage.append(target)

    for node in lineage:
        transform_attr = node.get("transform")
        if transform_attr:
            matrix = matrix.multiply(parse_transform_list(transform_attr))

    if matrix.is_identity():
        return None
    return matrix.as_tuple()


def animation_uses_local_motion_space(
    *,
    animation_type: AnimationType,
    target_attribute: str | None,
    transform_type: TransformType | None,
) -> bool:
    if animation_type == AnimationType.ANIMATE_MOTION:
        return True

    if animation_type == AnimationType.ANIMATE_TRANSFORM:
        return transform_type in {
            TransformType.TRANSLATE,
            TransformType.SCALE,
        }

    if animation_type != AnimationType.ANIMATE:
        return False

    return (target_attribute or "") in _LOCAL_MOTION_ATTRIBUTES


def parse_transform_type(
    element: etree._Element,
    animation_type: AnimationType,
) -> TransformType | None:
    if animation_type != AnimationType.ANIMATE_TRANSFORM:
        return None

    attr = (element.get("type") or "").lower()
    return _TRANSFORM_TYPES.get(attr)


def parse_motion_rotate(
    element: etree._Element,
    animation_type: AnimationType,
) -> str | None:
    if animation_type != AnimationType.ANIMATE_MOTION:
        return None

    rotate = element.get("rotate")
    if rotate is None:
        return None

    rotate = rotate.strip()
    if not rotate:
        return None
    return rotate


__all__ = [
    "animation_uses_local_motion_space",
    "parse_motion_rotate",
    "parse_transform_type",
    "resolve_motion_path_reference",
    "resolve_motion_space_matrix",
]
