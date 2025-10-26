"""IR text metadata helpers."""

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import (
    EmbeddedFontPlan,
    Run,
    TextAnchor,
    TextFrame,
    WordArtCandidate,
)


def test_wordart_candidate_flags_confidence() -> None:
    candidate = WordArtCandidate(preset="auto", confidence=0.6, fallback_strategy="outline")
    assert candidate.is_confident is True


def test_text_frame_holds_optional_metadata() -> None:
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 10, 10),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=12.0)],
        wordart_candidate=WordArtCandidate(preset="auto", confidence=0.4, fallback_strategy="outline"),
        embedding_plan=EmbeddedFontPlan(
            font_family="Arial",
            requires_embedding=True,
            subset_strategy="glyph",
            glyph_count=5,
        ),
    )

    assert frame.wordart_candidate is not None
    assert frame.embedding_plan is not None
    assert frame.embedding_plan.glyph_count == 5
