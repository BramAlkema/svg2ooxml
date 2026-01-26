import sys
from pathlib import Path
from lxml import etree

# Setup paths
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

from svg2ooxml.core.ir.resvg_bridge import ResvgBridge
from svg2ooxml.core.ir.context import IRConverterContext
from svg2ooxml.services import configure_services

def dump_trees(svg_path: Path):
    svg_text = svg_path.read_text()
    xml_root = etree.fromstring(svg_text.encode('utf-8'))
    
    # Initialize resvg bridge
    services = configure_services()
    ctx = IRConverterContext(services=services)
    bridge = ResvgBridge(ctx)
    bridge.build(xml_root)
    
    print(f"--- XML Tree (Drawable Only) ---")
    for el in xml_root.xpath("//*[local-name()='rect' or local-name()='path' or local-name()='circle' or local-name()='use' or local-name()='image']"):
        parent = el.getparent()
        parent_tag = etree.QName(parent).localname if parent is not None else "None"
        print(f"XML: ID={el.get('id', 'None'):<15} Tag={etree.QName(el).localname:<10} Parent={parent_tag}")

    # Recursively dump resvg nodes
    def _dump_node(node, depth=0):
        node_id = str(getattr(node, 'id', 'None'))
        node_type = type(node).__name__
        use_source = getattr(node, 'use_source', None)
        use_source_str = ""
        if use_source is not None:
            use_source_str = f" [UseSource={use_source.get('id', 'None')}]"
        
        print(f"{'  ' * depth}RESVG: ID={node_id:<15} Type={node_type}{use_source_str}")
        if hasattr(node, 'children'):
            for child in node.children:
                _dump_node(child, depth + 1)

    print(f"\n--- Resvg Tree (Normal) ---")
    if bridge.tree:
        _dump_node(bridge.tree.root)
    else:
        print("Normal Resvg tree is empty!")

    # Hypothesis test: Strip animation tags and try again
    print(f"\n--- Resvg Tree (Stripped Animations) ---")
    stripped_root = etree.fromstring(svg_text.encode('utf-8'))
    for tag in ["animate", "animateTransform", "animateColor", "animateMotion", "set"]:
        for el in stripped_root.xpath(f"//*[local-name()='{tag}']"):
            el.getparent().remove(el)
    
    bridge_stripped = ResvgBridge(ctx)
    bridge_stripped.build(stripped_root)
    if bridge_stripped.tree:
        _dump_node(bridge_stripped.tree.root)
    else:
        print("Stripped Resvg tree is STILL empty!")

if __name__ == "__main__":
    dump_trees(Path(sys.argv[1]))
