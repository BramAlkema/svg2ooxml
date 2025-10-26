#!/usr/bin/env python3
"""
CSS Named Colors Lookup Table

Complete CSS Level 4 named colors based on:
https://developer.mozilla.org/en-US/docs/Web/CSS/named-color

This module provides the standard CSS named colors as RGB tuples
for accurate color parsing in SVG to PPTX conversion.
"""

from typing import Dict, Tuple


# CSS Level 4 Named Colors
# Source: Mozilla Developer Network - CSS named colors
# https://developer.mozilla.org/en-US/docs/Web/CSS/named-color
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

CSS_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    'aliceblue': _hex_to_rgb('#f0f8ff'),
    'antiquewhite': _hex_to_rgb('#faebd7'),
    'aqua': _hex_to_rgb('#00ffff'),
    'aquamarine': _hex_to_rgb('#7fffd4'),
    'azure': _hex_to_rgb('#f0ffff'),
    'beige': _hex_to_rgb('#f5f5dc'),
    'bisque': _hex_to_rgb('#ffe4c4'),
    'black': _hex_to_rgb('#000000'),
    'blanchedalmond': _hex_to_rgb('#ffebcd'),
    'blue': _hex_to_rgb('#0000ff'),
    'blueviolet': _hex_to_rgb('#8a2be2'),
    'brown': _hex_to_rgb('#a52a2a'),
    'burlywood': _hex_to_rgb('#deb887'),
    'cadetblue': _hex_to_rgb('#5f9ea0'),
    'chartreuse': _hex_to_rgb('#7fff00'),
    'chocolate': _hex_to_rgb('#d2691e'),
    'coral': _hex_to_rgb('#ff7f50'),
    'cornflowerblue': _hex_to_rgb('#6495ed'),
    'cornsilk': _hex_to_rgb('#fff8dc'),
    'crimson': _hex_to_rgb('#dc143c'),
    'cyan': _hex_to_rgb('#00ffff'),
    'darkblue': _hex_to_rgb('#00008b'),
    'darkcyan': _hex_to_rgb('#008b8b'),
    'darkgoldenrod': _hex_to_rgb('#b8860b'),
    'darkgray': _hex_to_rgb('#a9a9a9'),
    'darkgreen': _hex_to_rgb('#006400'),
    'darkgrey': _hex_to_rgb('#a9a9a9'),
    'darkkhaki': _hex_to_rgb('#bdb76b'),
    'darkmagenta': _hex_to_rgb('#8b008b'),
    'darkolivegreen': _hex_to_rgb('#556b2f'),
    'darkorange': _hex_to_rgb('#ff8c00'),
    'darkorchid': _hex_to_rgb('#9932cc'),
    'darkred': _hex_to_rgb('#8b0000'),
    'darksalmon': _hex_to_rgb('#e9967a'),
    'darkseagreen': _hex_to_rgb('#8fbc8f'),
    'darkslateblue': _hex_to_rgb('#483d8b'),
    'darkslategray': _hex_to_rgb('#2f4f4f'),
    'darkslategrey': _hex_to_rgb('#2f4f4f'),
    'darkturquoise': _hex_to_rgb('#00ced1'),
    'darkviolet': _hex_to_rgb('#9400d3'),
    'deeppink': _hex_to_rgb('#ff1493'),
    'deepskyblue': _hex_to_rgb('#00bfff'),
    'dimgray': _hex_to_rgb('#696969'),
    'dimgrey': _hex_to_rgb('#696969'),
    'dodgerblue': _hex_to_rgb('#1e90ff'),
    'firebrick': _hex_to_rgb('#b22222'),
    'floralwhite': _hex_to_rgb('#fffaf0'),
    'forestgreen': _hex_to_rgb('#228b22'),
    'fuchsia': _hex_to_rgb('#ff00ff'),
    'gainsboro': _hex_to_rgb('#dcdcdc'),
    'ghostwhite': _hex_to_rgb('#f8f8ff'),
    'gold': _hex_to_rgb('#ffd700'),
    'goldenrod': _hex_to_rgb('#daa520'),
    'gray': _hex_to_rgb('#808080'),
    'green': _hex_to_rgb('#008000'),
    'greenyellow': _hex_to_rgb('#adff2f'),
    'grey': _hex_to_rgb('#808080'),
    'honeydew': _hex_to_rgb('#f0fff0'),
    'hotpink': _hex_to_rgb('#ff69b4'),
    'indianred': _hex_to_rgb('#cd5c5c'),
    'indigo': _hex_to_rgb('#4b0082'),
    'ivory': _hex_to_rgb('#fffff0'),
    'khaki': _hex_to_rgb('#f0e68c'),
    'lavender': _hex_to_rgb('#e6e6fa'),
    'lavenderblush': _hex_to_rgb('#fff0f5'),
    'lawngreen': _hex_to_rgb('#7cfc00'),
    'lemonchiffon': _hex_to_rgb('#fffacd'),
    'lightblue': _hex_to_rgb('#add8e6'),
    'lightcoral': _hex_to_rgb('#f08080'),
    'lightcyan': _hex_to_rgb('#e0ffff'),
    'lightgoldenrodyellow': _hex_to_rgb('#fafad2'),
    'lightgray': _hex_to_rgb('#d3d3d3'),
    'lightgreen': _hex_to_rgb('#90ee90'),
    'lightgrey': _hex_to_rgb('#d3d3d3'),
    'lightpink': _hex_to_rgb('#ffb6c1'),
    'lightsalmon': _hex_to_rgb('#ffa07a'),
    'lightseagreen': _hex_to_rgb('#20b2aa'),
    'lightskyblue': _hex_to_rgb('#87cefa'),
    'lightslategray': _hex_to_rgb('#778899'),
    'lightslategrey': _hex_to_rgb('#778899'),
    'lightsteelblue': _hex_to_rgb('#b0c4de'),
    'lightyellow': _hex_to_rgb('#ffffe0'),
    'lime': _hex_to_rgb('#00ff00'),
    'limegreen': _hex_to_rgb('#32cd32'),
    'linen': _hex_to_rgb('#faf0e6'),
    'magenta': _hex_to_rgb('#ff00ff'),
    'maroon': _hex_to_rgb('#800000'),
    'mediumaquamarine': _hex_to_rgb('#66cdaa'),
    'mediumblue': _hex_to_rgb('#0000cd'),
    'mediumorchid': _hex_to_rgb('#ba55d3'),
    'mediumpurple': _hex_to_rgb('#9370db'),
    'mediumseagreen': _hex_to_rgb('#3cb371'),
    'mediumslateblue': _hex_to_rgb('#7b68ee'),
    'mediumspringgreen': _hex_to_rgb('#00fa9a'),
    'mediumturquoise': _hex_to_rgb('#48d1cc'),
    'mediumvioletred': _hex_to_rgb('#c71585'),
    'midnightblue': _hex_to_rgb('#191970'),
    'mintcream': _hex_to_rgb('#f5fffa'),
    'mistyrose': _hex_to_rgb('#ffe4e1'),
    'moccasin': _hex_to_rgb('#ffe4b5'),
    'navajowhite': _hex_to_rgb('#ffdead'),
    'navy': _hex_to_rgb('#000080'),
    'oldlace': _hex_to_rgb('#fdf5e6'),
    'olive': _hex_to_rgb('#808000'),
    'olivedrab': _hex_to_rgb('#6b8e23'),
    'orange': _hex_to_rgb('#ffa500'),
    'orangered': _hex_to_rgb('#ff4500'),
    'orchid': _hex_to_rgb('#da70d6'),
    'palegoldenrod': _hex_to_rgb('#eee8aa'),
    'palegreen': _hex_to_rgb('#98fb98'),
    'paleturquoise': _hex_to_rgb('#afeeee'),
    'palevioletred': _hex_to_rgb('#db7093'),
    'papayawhip': _hex_to_rgb('#ffefd5'),
    'peachpuff': _hex_to_rgb('#ffdab9'),
    'peru': _hex_to_rgb('#cd853f'),
    'pink': _hex_to_rgb('#ffc0cb'),
    'plum': _hex_to_rgb('#dda0dd'),
    'powderblue': _hex_to_rgb('#b0e0e6'),
    'purple': _hex_to_rgb('#800080'),
    'rebeccapurple': _hex_to_rgb('#663399'),
    'red': _hex_to_rgb('#ff0000'),
    'rosybrown': _hex_to_rgb('#bc8f8f'),
    'royalblue': _hex_to_rgb('#4169e1'),
    'saddlebrown': _hex_to_rgb('#8b4513'),
    'salmon': _hex_to_rgb('#fa8072'),
    'sandybrown': _hex_to_rgb('#f4a460'),
    'seagreen': _hex_to_rgb('#2e8b57'),
    'seashell': _hex_to_rgb('#fff5ee'),
    'sienna': _hex_to_rgb('#a0522d'),
    'silver': _hex_to_rgb('#c0c0c0'),
    'skyblue': _hex_to_rgb('#87ceeb'),
    'slateblue': _hex_to_rgb('#6a5acd'),
    'slategray': _hex_to_rgb('#708090'),
    'slategrey': _hex_to_rgb('#708090'),
    'snow': _hex_to_rgb('#fffafa'),
    'springgreen': _hex_to_rgb('#00ff7f'),
    'steelblue': _hex_to_rgb('#4682b4'),
    'tan': _hex_to_rgb('#d2b48c'),
    'teal': _hex_to_rgb('#008080'),
    'thistle': _hex_to_rgb('#d8bfd8'),
    'tomato': _hex_to_rgb('#ff6347'),
    'turquoise': _hex_to_rgb('#40e0d0'),
    'violet': _hex_to_rgb('#ee82ee'),
    'wheat': _hex_to_rgb('#f5deb3'),
    'white': _hex_to_rgb('#ffffff'),
    'whitesmoke': _hex_to_rgb('#f5f5f5'),
    'yellow': _hex_to_rgb('#ffff00'),
    'yellowgreen': _hex_to_rgb('#9acd32'),

    # Special cases
    'transparent': (0, 0, 0),  # Special case handled separately with alpha=0
}

def get_css_color(color_name: str) -> tuple[int, int, int]:
    """
    Get RGB tuple for CSS named color.

    Args:
        color_name: CSS color name (case-insensitive)

    Returns:
        RGB tuple or None if color not found

    Examples:
        >>> get_css_color('lightblue')
        (173, 216, 230)
        >>> get_css_color('DARKBLUE')
        (0, 0, 139)
    """
    return CSS_NAMED_COLORS.get(color_name.lower())

def is_css_color(color_name: str) -> bool:
    """
    Check if string is a valid CSS named color.

    Args:
        color_name: Color name to check

    Returns:
        True if valid CSS color name
    """
    return color_name.lower() in CSS_NAMED_COLORS

# Alias for backward compatibility
NAMED_COLORS = CSS_NAMED_COLORS

__all__ = ['CSS_NAMED_COLORS', 'get_css_color', 'is_css_color', 'NAMED_COLORS']