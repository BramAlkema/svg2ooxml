"""Statistics helpers for the SVG parser."""

from lxml import etree

from .xml import walk


def compute_statistics(root: etree._Element) -> dict[str, int]:
    """Return basic statistics about the SVG tree with a single traversal."""

    element_count = 0
    namespaces: set[str] = set()

    for element in walk(root):
        element_count += 1
        tag = getattr(element, "tag", "")
        if isinstance(tag, str) and "}" in tag:
            namespaces.add(tag.split("}")[0][1:])

    return {
        "element_count": element_count,
        "namespace_count": len(namespaces),
    }


__all__ = ["compute_statistics"]
