"""Navigation relationship registration for DrawingML writer."""

from __future__ import annotations

from svg2ooxml.drawingml.assets import AssetRegistry
from svg2ooxml.drawingml.navigation import register_navigation
from svg2ooxml.drawingml.xml_builder import to_string


class NavigationRegistrar:
    """Register shape and text-run navigation assets for one render pass."""

    def __init__(self) -> None:
        self._assets: AssetRegistry | None = None
        self._next_index = 1

    def reset(self, assets: AssetRegistry | None) -> None:
        self._assets = assets
        self._next_index = 1

    def register_run_navigation(self, navigation, text_segment: str):
        return self.register_navigation_asset(navigation, scope="text_run", text=text_segment)

    def from_metadata(self, metadata: dict[str, object], *, scope: str) -> str:
        nav_data = metadata.get("navigation")
        if nav_data is None:
            return ""
        entries = nav_data if isinstance(nav_data, list) else [nav_data]
        for entry in entries:
            elem = self.register_navigation_asset(entry, scope=scope)
            if elem is not None:
                return to_string(elem)
        return ""

    def register_navigation_asset(self, navigation, *, scope: str, text: str | None = None):
        if navigation is None or self._assets is None:
            return None

        return register_navigation(
            navigation,
            scope=scope,
            text=text,
            allocate_rel_id=self._allocate_navigation_rid,
            add_asset=lambda asset: self._assets.add_navigation(
                relationship_id=asset.relationship_id,
                relationship_type=asset.relationship_type,
                target=asset.target,
                target_mode=asset.target_mode,
                action=asset.action,
                tooltip=asset.tooltip,
                history=asset.history,
                scope=asset.scope,
                text=asset.text,
            ),
        )

    def _allocate_navigation_rid(self) -> str:
        rid = f"rIdNav{self._next_index}"
        self._next_index += 1
        return rid


__all__ = ["NavigationRegistrar"]
