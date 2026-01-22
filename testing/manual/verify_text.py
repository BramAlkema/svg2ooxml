import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.ir.text import TextFrame

svg_content = """
<svg width="500" height="400" xmlns="http://www.w3.org/2000/svg">
  <rect width="100%" height="100%" fill="#f0f0f0"/>
  <path id="arcPath" d="M 50,300 Q 250,150 450,300" fill="none" stroke="blue" stroke-dasharray="5,5"/>
  <text font-family="Arial" font-size="40">
    <textPath href="#arcPath" fill="orange" stroke="black" stroke-width="2">
      WARPED WORDART
    </textPath>
  </text>
</svg>
"""

policy_overrides = {
    "text": {
        "text.wordart.prefer_native": True,
        "text.wordart.enable": True,
        "text.wordart.confidence_threshold": 0.1
    }
}

exporter = SvgToPptxExporter(slide_size_mode="same")
# Generate the PPTX
exporter.convert_string(svg_content, Path("testing/manual/text_styles_verify.pptx"), policy_overrides=policy_overrides)

# Inspect IR
render_result, scene = exporter._render_svg(svg_content, None, policy_overrides=policy_overrides)

for element in scene.elements:
    if isinstance(element, TextFrame):
        print(f"TextFrame: '{element.text_content}'")
        policy_text = element.metadata.get("policy", {}).get("text", {})
        threshold = policy_text.get("wordart_detection", {}).get("confidence_threshold", 0.5)
        print(f"  Threshold: {threshold}")
        if element.wordart_candidate:
            print(f"  Candidate: {element.wordart_candidate.preset} (Conf: {element.wordart_candidate.confidence:.2f})")
            print(f"  Is Confident: {element.wordart_candidate.confidence >= threshold}")
