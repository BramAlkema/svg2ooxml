"""Tests for filter provider wiring and lightweight pipeline fallback behavior."""

from __future__ import annotations

import logging

from lxml import etree
import pytest

from svg2ooxml.filters.lightweight import LightweightFilterPlanner, LightweightFilterRenderer
from svg2ooxml.services import filter_service as filter_service_module
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_service_stub import DisabledFilterService
from svg2ooxml.services.providers import filter_provider
from svg2ooxml.services.setup import configure_services


def test_factory_returns_filter_service_without_numpy_gate() -> None:
    service = filter_provider._factory()

    assert isinstance(service, FilterService)
    assert service.runtime_capability == "pending"


def test_configure_services_registers_filter_service() -> None:
    services = configure_services()

    assert isinstance(services.filter_service, FilterService)


def test_filter_service_uses_lightweight_pipeline_when_full_pipeline_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="svg2ooxml.services.filter_service")
    monkeypatch.setattr(
        filter_service_module,
        "_load_filter_pipeline",
        lambda: (
            LightweightFilterPlanner,
            LightweightFilterRenderer,
            RuntimeError("numpy_missing"),
        ),
    )

    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='f'><feFlood flood-color='#336699' flood-opacity='0.5'/></filter>"
    )
    service.register_filter("f", filter_xml)

    class _Tracer:
        def __init__(self) -> None:
            self.events: list[dict[str, object]] = []

        def record_stage_event(
            self,
            *,
            stage: str,
            action: str,
            subject: str,
            metadata: dict[str, object],
        ) -> None:
            self.events.append(
                {
                    "stage": stage,
                    "action": action,
                    "subject": subject,
                    "metadata": dict(metadata),
                }
            )

    tracer = _Tracer()
    effects = service.resolve_effects("f", context={"tracer": tracer})

    assert effects
    first = effects[0]
    assert first.effect is not None
    assert first.metadata.get("disabled") is not True
    assert first.metadata.get("runtime_capability") == "lightweight"
    assert service.runtime_capability == "lightweight"
    assert any(
        event["action"] == "runtime_capability"
        and event["metadata"].get("capability") == "lightweight"
        for event in tracer.events
    )
    assert "Full filter pipeline unavailable" in caplog.text


def test_filter_service_reports_disabled_capability_when_no_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        filter_service_module,
        "_load_filter_pipeline",
        lambda: (None, None, RuntimeError("missing_pipeline")),
    )
    service = FilterService()

    effects = service.resolve_effects("missing")

    assert service.runtime_capability == "disabled"
    assert effects
    assert effects[0].fallback == "emf"
    assert effects[0].metadata.get("runtime_capability") == "disabled"


def test_disabled_filter_service_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("svg2ooxml.tests.filter_stub")
    caplog.set_level(logging.WARNING, logger=logger.name)

    service = DisabledFilterService(logger=logger, reason="numpy_missing")
    first = service.resolve_effects("blur")
    second = service.resolve_effects("blur")

    warning_records = [record for record in caplog.records if record.name == logger.name]
    assert len(warning_records) == 1
    assert "Filter rendering disabled (numpy_missing)" in warning_records[0].message
    assert service.runtime_capability == "disabled"
    assert first[0].metadata["runtime_capability"] == "disabled"
    assert first[0].metadata["fallback"] == "emf"
    assert second[0].metadata["fallback"] == "emf"
