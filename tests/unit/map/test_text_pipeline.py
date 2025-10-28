"""Text conversion pipeline tests."""

import math

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.ir.text_path import PathPoint
from svg2ooxml.core.ir.text_pipeline import TextConversionPipeline
from svg2ooxml.policy.text_policy import resolve_text_policy
from svg2ooxml.services.fonts import FontEmbeddingEngine, FontEmbeddingResult, FontMatch, FontQuery, FontService


def _make_frame(text: str) -> TextFrame:
    run = Run(text=text, font_family="Arial", font_size_pt=20.0)
    return TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(0, 0, 100, 40),
        runs=[run],
    )


def _circle_points(radius: float = 1.0, count: int = 48) -> list[PathPoint]:
    points: list[PathPoint] = []
    for i in range(count):
        theta = 2 * math.pi * (i / count)
        x = radius * math.cos(theta)
        y = radius * math.sin(theta)
        tangent = theta + math.pi / 2.0
        points.append(PathPoint(x=x, y=y, tangent_angle=tangent, distance_along_path=i))
    points.append(points[0])
    return points


def _wave_points(amplitude: float = 1.0, periods: int = 2, count: int = 120) -> list[PathPoint]:
    points: list[PathPoint] = []
    prev_x = prev_y = 0.0
    distance = 0.0
    for i in range(count):
        t = (i / (count - 1)) * (math.pi * periods)
        x = t
        y = amplitude * math.sin(t)
        if i > 0:
            dx = x - prev_x
            dy = y - prev_y
            distance += math.hypot(dx, dy)
            tangent = math.atan2(dy, dx)
        else:
            tangent = 0.0
        points.append(PathPoint(x=x, y=y, tangent_angle=tangent, distance_along_path=distance))
        prev_x, prev_y = x, y
    return points


def _bulge_points(amplitude: float = 1.0, width: float = 4.0, count: int = 80) -> list[PathPoint]:
    points: list[PathPoint] = []
    prev_x = prev_y = 0.0
    distance = 0.0
    for i in range(count):
        t = i / (count - 1)
        x = width * (t - 0.5)
        y = amplitude * (1.0 - (2 * (t - 0.5)) ** 2)
        if i > 0:
            dx = x - prev_x
            dy = y - prev_y
            distance += math.hypot(dx, dy)
            tangent = math.atan2(dy, dx)
        else:
            tangent = 0.0
        points.append(PathPoint(x=x, y=y, tangent_angle=tangent, distance_along_path=distance))
        prev_x, prev_y = x, y
    return points


def test_pipeline_populates_metadata_when_detection_enabled() -> None:
    pipeline = TextConversionPipeline(font_service=None, embedding_engine=None, logger=None)
    frame = _make_frame("Hello")
    decision = resolve_text_policy("balanced")

    updated = pipeline.plan_frame(frame, frame.runs, decision)

    assert updated.wordart_candidate is not None
    assert updated.wordart_candidate.preset in {"textTriangle", "textWave1", "textCircle", "textArchUp"}
    assert updated.wordart_candidate.is_confident is True
    assert updated.embedding_plan is not None
    assert updated.embedding_plan.requires_embedding is False
    assert updated.metadata.get("wordart", {}).get("preset") == updated.wordart_candidate.preset


def test_pipeline_skips_annotations_when_detection_disabled() -> None:
    pipeline = TextConversionPipeline(font_service=None, embedding_engine=None, logger=None)
    frame = _make_frame("Hello")
    decision = resolve_text_policy("low")

    updated = pipeline.plan_frame(frame, frame.runs, decision)

    assert updated.wordart_candidate is None
    assert updated.embedding_plan is None


def test_pipeline_uses_font_service_for_embedding(monkeypatch) -> None:
    service = FontService()

    class _StaticProvider:
        def resolve(self, query: FontQuery) -> FontMatch | None:  # pragma: no cover - simple stub
            if query.family.lower() == "arial" or "arial" in [fam.lower() for fam in query.fallback_chain]:
                return FontMatch(
                    family="Arial",
                    path="/fonts/Arial.ttf",
                    weight=query.weight,
                    style=query.style,
                    found_via="static",
                )
            return None

        def list_alternatives(self, query: FontQuery):  # pragma: no cover - simple stub
            match = self.resolve(query)
            if match:
                yield match

    service.register_provider(_StaticProvider())
    embedding_engine = FontEmbeddingEngine()
    monkeypatch.setattr(embedding_engine, "can_embed", lambda path: True)
    monkeypatch.setattr(
        embedding_engine,
        "subset_font",
        lambda request: FontEmbeddingResult(
            relationship_id="rIdFont1",
            subset_path=None,
            glyph_count=len(request.glyph_ids),
            bytes_written=256,
            packaging_metadata={"font_data": b"subset-bytes", "font_path": request.font_path},
        ),
    )

    pipeline = TextConversionPipeline(font_service=service, embedding_engine=embedding_engine, logger=None)
    frame = _make_frame("Embed")
    decision = resolve_text_policy("high")

    updated = pipeline.plan_frame(frame, frame.runs, decision)

    assert updated.embedding_plan is not None
    assert updated.embedding_plan.requires_embedding is True
    assert updated.embedding_plan.metadata.get("font_path") == "/fonts/Arial.ttf"
    assert updated.embedding_plan.metadata.get("resolution") == "embed"
    assert updated.embedding_plan.metadata.get("font_data") == b"subset-bytes"
    assert updated.embedding_plan.metadata.get("subset_bytes") == 256


def test_pipeline_prefers_classifier_when_path_points_present() -> None:
    pipeline = TextConversionPipeline(font_service=None, embedding_engine=None, logger=None)
    circle_points = _circle_points()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(-1, -1, 2, 2),
        runs=[Run(text="Hello", font_family="Arial", font_size_pt=24.0)],
        metadata={
            "text_path_id": "circle",
            "text_path_points": circle_points,
            "text_path_data": "M1 0 A1 1 0 1 1 -1 0 A1 1 0 1 1 1 0",
            "wordart": {"prefer_native": True},
        },
    )
    decision = resolve_text_policy("balanced")

    updated = pipeline.plan_frame(frame, frame.runs or [], decision)

    assert updated.wordart_candidate is not None
    assert updated.wordart_candidate.preset == "textCircle"
    assert updated.wordart_candidate.metadata.get("reason") == "Closed near-circular baseline"


def test_pipeline_classifies_wave_wordart() -> None:
    pipeline = TextConversionPipeline(font_service=None, embedding_engine=None, logger=None)
    points = _wave_points()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(-1, -1, 6, 2),
        runs=[Run(text="Wave", font_family="Arial", font_size_pt=24.0)],
        metadata={
            "text_path_id": "wave",
            "text_path_points": points,
            "wordart": {"prefer_native": True},
        },
    )
    decision = resolve_text_policy("balanced")

    updated = pipeline.plan_frame(frame, frame.runs or [], decision)

    assert updated.wordart_candidate is not None
    assert updated.wordart_candidate.preset == "textWave1"
    assert updated.wordart_candidate.metadata.get("reason") == "Baseline exhibits wave-like oscillation"


def test_pipeline_classifies_bulge_wordart() -> None:
    pipeline = TextConversionPipeline(font_service=None, embedding_engine=None, logger=None)
    points = _bulge_points()
    frame = TextFrame(
        origin=Point(0, 0),
        anchor=TextAnchor.START,
        bbox=Rect(-2, -1, 4, 2),
        runs=[Run(text="Bulge", font_family="Arial", font_size_pt=24.0)],
        metadata={
            "text_path_id": "bulge",
            "text_path_points": points,
            "wordart": {"prefer_native": True},
        },
    )
    decision = resolve_text_policy("balanced")

    updated = pipeline.plan_frame(frame, frame.runs or [], decision)

    assert updated.wordart_candidate is not None
    assert updated.wordart_candidate.preset in {"textInflate", "textDeflate", "textArchUp"}
    assert updated.wordart_candidate.metadata.get("text_path_id") == "bulge"
