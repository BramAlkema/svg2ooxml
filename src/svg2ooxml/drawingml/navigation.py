"""Navigation utilities shared by DrawingML writer components."""

from __future__ import annotations

import html
from collections.abc import Callable

from lxml import etree

_DANGEROUS_SCHEMES = ("javascript:", "data:", "vbscript:", "file:")
_SSRF_BLOCKLIST = ("169.254.169.254", "metadata.google", "metadata.azure",
                   "localhost", "127.0.0.1", "0.0.0.0", "[::1]")

from svg2ooxml.core.pipeline.navigation import (
    BookmarkTarget,
    CustomShowTarget,
    NavigationAction,
    NavigationKind,
    NavigationSpec,
    SlideTarget,
)
from svg2ooxml.drawingml.assets import NavigationAsset
from svg2ooxml.drawingml.xml_builder import a_elem

__all__ = [
    "normalize_navigation",
    "register_navigation",
]


def normalize_navigation(navigation: object) -> NavigationSpec | None:
    """Return a NavigationSpec from either an existing spec or mapping."""

    if navigation is None:
        return None
    if isinstance(navigation, NavigationSpec):
        return navigation
    if isinstance(navigation, dict):
        return _spec_from_dict(navigation)
    return None


def register_navigation(
    navigation: object,
    *,
    scope: str,
    text: str | None,
    allocate_rel_id: Callable[[], str],
    add_asset: Callable[[NavigationAsset], None],
) -> etree._Element | None:
    """Normalize navigation metadata, register the asset, return element."""

    spec = normalize_navigation(navigation)
    if spec is None:
        return None

    result = _build_navigation_asset(
        spec,
        allocate_rel_id=allocate_rel_id,
        scope=scope,
        text=text,
    )
    if result is None:
        return None
    asset_data, nav_elem = result

    if asset_data is not None:
        add_asset(asset_data)
    return nav_elem


def _build_navigation_asset(
    spec: NavigationSpec,
    *,
    allocate_rel_id: Callable[[], str],
    scope: str,
    text: str | None = None,
) -> tuple[NavigationAsset | None, etree._Element | None]:
    """Create a NavigationAsset plus the corresponding hyperlink element."""

    relationship_id: str | None = None
    relationship_type: str | None = None
    target: str | None = None
    target_mode: str | None = None

    if spec.kind == NavigationKind.EXTERNAL and spec.href:
        href_lower = spec.href.strip().lower()
        if (href_lower.startswith(_DANGEROUS_SCHEMES)
                or any(t in href_lower for t in _SSRF_BLOCKLIST)):
            return None
        relationship_id = allocate_rel_id()
        relationship_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
        target = spec.href
        target_mode = "External"
    elif spec.kind == NavigationKind.SLIDE and spec.slide:
        relationship_id = allocate_rel_id()
        relationship_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
        target = f"../slides/slide{spec.slide.index}.xml"

    action_uri = _action_uri_for_spec(spec)
    tooltip = spec.tooltip
    history = bool(spec.visited)
    text_snippet = text.strip() if isinstance(text, str) else text
    if text_snippet == "":
        text_snippet = None

    asset = NavigationAsset(
        relationship_id=relationship_id,
        relationship_type=relationship_type,
        target=target,
        target_mode=target_mode,
        action=action_uri,
        tooltip=tooltip,
        history=history,
        scope=scope,
        text=text_snippet,
    )

    nav_elem = _build_navigation_elem(asset)
    if nav_elem is None and not asset.requires_relationship() and action_uri is None:
        return None, None
    return asset, nav_elem


def _spec_from_dict(data: dict[str, object]) -> NavigationSpec | None:
    kind_value = data.get("kind")
    if not isinstance(kind_value, str):
        return None
    try:
        kind = NavigationKind(kind_value)
    except ValueError:
        return None

    tooltip = data.get("tooltip") if isinstance(data.get("tooltip"), str) else None
    visited = bool(data.get("visited", True))

    kwargs: dict[str, object] = {
        "kind": kind,
        "tooltip": tooltip,
        "visited": visited,
    }

    if kind == NavigationKind.EXTERNAL:
        href = data.get("href")
        if not isinstance(href, str) or not href.strip():
            return None
        kwargs["href"] = href.strip()
    elif kind == NavigationKind.SLIDE:
        slide_dict = data.get("slide") if isinstance(data.get("slide"), dict) else None
        index = None
        if slide_dict is not None:
            index = slide_dict.get("index")
        if index is None:
            index = data.get("slide_index")
        if index is None:
            return None
        try:
            kwargs["slide"] = SlideTarget(index=int(index))
        except (TypeError, ValueError):
            return None
    elif kind == NavigationKind.ACTION:
        action_value = data.get("action")
        if not isinstance(action_value, str):
            return None
        try:
            action = NavigationAction(action_value)
        except ValueError:
            try:
                action = NavigationAction(action_value.lower())
            except ValueError:
                return None
        kwargs["action"] = action
    elif kind == NavigationKind.BOOKMARK:
        bookmark_dict = data.get("bookmark") if isinstance(data.get("bookmark"), dict) else None
        name = bookmark_dict.get("name") if bookmark_dict else data.get("bookmark_name")
        if not isinstance(name, str) or not name:
            return None
        kwargs["bookmark"] = BookmarkTarget(name=name)
    elif kind == NavigationKind.CUSTOM_SHOW:
        custom_dict = data.get("custom_show") if isinstance(data.get("custom_show"), dict) else None
        name = custom_dict.get("name") if custom_dict else data.get("custom_show_name")
        if not isinstance(name, str) or not name:
            return None
        kwargs["custom_show"] = CustomShowTarget(name=name)
    else:
        return None

    try:
        return NavigationSpec(**kwargs)
    except ValueError:
        return None


def _action_uri_for_spec(spec: NavigationSpec) -> str | None:
    """Generate PowerPoint action URI for navigation specs.

    Only ACTION navigation (next/previous slide) generates ppaction:// URLs.
    BOOKMARK and CUSTOM_SHOW navigation don't have direct PowerPoint equivalents
    and would generate invalid ppaction:// URLs that PowerPoint strips during repair.

    Per ECMA-376, ppaction://hlinkshowjump only supports the 'jump' parameter with
    values: nextslide, previousslide, firstslide, lastslide, endshow.
    The 'bookmark' and 'show' parameters are not part of the specification.
    """
    if spec.kind == NavigationKind.ACTION and spec.action is not None:
        return f"ppaction://hlinkshowjump?jump={spec.action.value}"
    # BOOKMARK and CUSTOM_SHOW don't generate action URIs
    # These would require PowerPoint-specific bookmark/show setup which differs from SVG
    return None


def _build_navigation_elem(asset: NavigationAsset) -> etree._Element | None:
    """Build an ``a:hlinkClick`` element, or *None* if not applicable."""
    if not asset.relationship_id and not asset.action:
        return None

    hlinkClick = a_elem("hlinkClick")

    if asset.relationship_id:
        hlinkClick.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", asset.relationship_id)

    if asset.tooltip:
        hlinkClick.set("tooltip", html.escape(asset.tooltip, quote=False))

    hlinkClick.set("history", "1" if asset.history else "0")

    if asset.action:
        hlinkClick.set("action", html.escape(asset.action, quote=False))

    return hlinkClick
