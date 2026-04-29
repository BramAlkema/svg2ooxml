from __future__ import annotations

import logging

from svg2ooxml.drawingml import shapes_runtime
from svg2ooxml.drawingml.assets import AssetRegistry
from svg2ooxml.drawingml.text_renderer import DrawingMLTextRenderer
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame, WordArtCandidate


def test_text_renderer_ignores_invalid_wordart_threshold(monkeypatch) -> None:
    def render_wordart(*args, **kwargs) -> str:
        return "<wordart/>"

    def render_textframe(*args, **kwargs) -> str:
        return "<text/>"

    monkeypatch.setattr(shapes_runtime, "render_wordart", render_wordart)
    monkeypatch.setattr(shapes_runtime, "render_textframe", render_textframe)

    renderer = DrawingMLTextRenderer(
        text_template="",
        wordart_template="",
        policy_for=lambda metadata, target: {
            "wordart_detection": {"confidence_threshold": "bad"}
        },
        register_run_navigation=lambda run, text: "",
        trace_writer=lambda *args, **kwargs: None,
        assets=AssetRegistry(),
        logger=logging.getLogger(__name__),
    )
    frame = TextFrame(
        origin=Point(0.0, 0.0),
        anchor=TextAnchor.START,
        bbox=Rect(0.0, 0.0, 10.0, 10.0),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=12.0)],
        metadata={"wordart": {"prefer_native": False}},
        wordart_candidate=WordArtCandidate(
            preset="textPlain",
            confidence=0.4,
            fallback_strategy="native",
        ),
    )

    assert renderer.render(frame, 1, hyperlink_xml="") == ("<text/>", 2)
