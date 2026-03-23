"""Font similarity mapping for intelligent fallback selection.

When a requested font isn't available, this maps it to a visually similar
alternative based on font classification (geometric sans, humanist sans,
neo-grotesque, slab serif, etc.).
"""

from __future__ import annotations

# Classification → ordered fallback list (most similar first)
# Each entry: (category_name, set_of_families, ordered_fallbacks)
_FONT_CATEGORIES: list[tuple[str, frozenset[str], tuple[str, ...]]] = [
    (
        "geometric_sans",
        frozenset({
            "gotham", "gotham thin", "gotham light", "gotham medium", "gotham bold", "gotham black",
            "proxima nova", "proxima nova thin", "proxima nova light",
            "avenir", "avenir next", "avenir light",
            "century gothic", "futura", "futura pt",
            "brandon grotesque", "comfortaa", "josefin sans",
            "neuzeit grotesk", "spartan",
        }),
        ("Montserrat", "Raleway", "Nunito Sans", "Century Gothic", "Futura", "Arial"),
    ),
    (
        "humanist_sans",
        frozenset({
            "gill sans", "gill sans mt", "frutiger", "myriad", "myriad pro",
            "optima", "segoe ui", "trebuchet ms", "lucida grande", "lucida sans",
            "tahoma", "verdana", "cantarell", "cabin",
        }),
        ("Open Sans", "Source Sans Pro", "Noto Sans", "Segoe UI", "Verdana", "Arial"),
    ),
    (
        "neo_grotesque",
        frozenset({
            "helvetica", "helvetica neue", "arial", "univers", "akzidenz grotesk",
            "aktiv grotesk", "inter", "roboto", "san francisco", "sf pro",
            "sf pro text", "sf pro display", "nimbus sans",
        }),
        ("Arial", "Helvetica", "Roboto", "Inter", "Nimbus Sans", "Liberation Sans"),
    ),
    (
        "slab_serif",
        frozenset({
            "rockwell", "clarendon", "courier", "courier new",
            "memphis", "sentinel", "archer", "museo slab", "zilla slab",
        }),
        ("Roboto Slab", "Zilla Slab", "Courier New", "Georgia"),
    ),
    (
        "oldstyle_serif",
        frozenset({
            "garamond", "adobe garamond", "eb garamond", "palatino", "palatino linotype",
            "book antiqua", "minion", "minion pro", "bembo", "sabon",
            "caslon", "adobe caslon", "hoefler text", "baskerville",
            "georgia", "times", "times new roman",
        }),
        ("EB Garamond", "Palatino", "Georgia", "Times New Roman", "Noto Serif"),
    ),
    (
        "modern_serif",
        frozenset({
            "bodoni", "bodoni mt", "didot", "walbaum",
            "playfair display", "libre bodoni", "ogg",
        }),
        ("Playfair Display", "Libre Bodoni", "Didot", "Georgia", "Times New Roman"),
    ),
    (
        "monospace",
        frozenset({
            "consolas", "menlo", "monaco", "fira code", "fira mono",
            "source code pro", "jetbrains mono", "sf mono",
            "inconsolata", "ubuntu mono", "droid sans mono",
            "andale mono", "lucida console",
        }),
        ("Courier New", "Consolas", "Menlo", "Monaco", "Liberation Mono"),
    ),
    (
        "display_condensed",
        frozenset({
            "impact", "oswald", "barlow condensed", "roboto condensed",
            "din condensed", "trade gothic", "franklin gothic",
        }),
        ("Oswald", "Roboto Condensed", "Arial Narrow", "Impact"),
    ),
]

# Build lookup: normalized family → fallback list
_SIMILARITY_MAP: dict[str, tuple[str, ...]] = {}
for _cat_name, _families, _fallbacks in _FONT_CATEGORIES:
    for _family in _families:
        _SIMILARITY_MAP[_family] = _fallbacks


def get_similar_fonts(family: str) -> tuple[str, ...]:
    """Return visually similar font families for *family*, most similar first.

    Returns an empty tuple if the font isn't in any known category.
    """
    key = family.lower().strip()
    return _SIMILARITY_MAP.get(key, ())


__all__ = ["get_similar_fonts"]
