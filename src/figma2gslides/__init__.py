"""Tool-layer package for Figma and Google Slides workflows.

``figma2gslides`` is intentionally packaged from this repository as a tool on
top of ``svg2ooxml``. Importing this package stays lightweight; runtime entry
points such as ``figma2gslides.app:app`` may require the ``figma2gslides`` extra.
"""

TOOL_NAME = "figma2gslides"
TOOL_SURFACE = "svg2ooxml-tool"

__all__ = ["TOOL_NAME", "TOOL_SURFACE"]
