import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter, SvgPageSource
from svg2ooxml.core.slide_orchestrator import build_fidelity_tier_variants, expand_page_with_variants

svg_content = """
<svg width="500" height="400" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="blurFilter">
      <feGaussianBlur stdDeviation="5" />
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="white"/>
  
  <!-- 1. Simple Shape -->
  <rect x="50" y="50" width="100" height="100" fill="blue" />
  
  <!-- 2. Path with many points -->
  <path d="M 200,50 L 210,60 L 220,50 L 230,60 L 240,50 L 250,60 L 260,50 L 270,60 L 280,50 L 290,60" 
        fill="none" stroke="green" stroke-width="5" />

  <!-- 3. Shape with Filter -->
  <rect x="50" y="200" width="100" height="100" fill="red" filter="url(#blurFilter)" />

  <!-- 4. Outlined Text -->
  <text x="200" y="250" font-family="Arial" font-size="40" fill="yellow" stroke="black" stroke-width="2">
    OUTLINE
  </text>
</svg>
"""

exporter = SvgToPptxExporter()
page = SvgPageSource(svg_text=svg_content, name="fallback_test", title="Fallback Test")
variants = build_fidelity_tier_variants()
pages = expand_page_with_variants(page, variants)

output_path = Path("testing/manual/fallback_ladder_demo.pptx")
result = exporter.convert_pages(pages, output_path)

print(f"Generated {result.pptx_path}")
for res in result.page_results:
    print(f"\nSlide: {res.title}")
    # Inspect trace for decisions
    report = res.trace_report
    # Geometry decisions are stored in geometry_events
    for event in report.get("geometry_events", []):
         print(f"  Geometry: <{event.get('tag', 'shape')}> -> {event.get('decision', 'unknown')}")
    # Paint decisions are stored in paint_events
    for event in report.get("paint_events", []):
         print(f"  Paint: {event.get('paint_type', 'unknown')} -> {event.get('decision', 'unknown')}")
