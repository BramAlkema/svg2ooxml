from __future__ import annotations

from lxml import etree

from svg2ooxml.core.parser.switch_evaluator import SwitchEvaluator
from svg2ooxml.core.traversal.hooks import TraversalHooksMixin


class SwitchHarness(TraversalHooksMixin):
    def __init__(self, languages: tuple[str, ...]):
        self._system_languages = languages
        self._logger = None
        self._clip_usage: set[str] = set()
        self._mask_usage: set[str] = set()

    def _trace_stage(self, *args, **kwargs) -> None:  # pragma: no cover - test stub
        pass

    def _trace_geometry_decision(self, *args, **kwargs) -> None:  # pragma: no cover - test stub
        pass

    def _apply_filter_metadata(self, *args, **kwargs) -> None:  # pragma: no cover - test stub
        pass

    def _resolve_clip_ref(self, element):  # pragma: no cover - unused in tests
        return None

    def _resolve_mask_ref(self, element):  # pragma: no cover - unused in tests
        return (None, None)

    def navigation_from_attributes(self, element):  # pragma: no cover - unused in tests
        return None


def _make_switch(markup: str) -> etree._Element:
    switch = etree.fromstring(markup).find("{http://www.w3.org/2000/svg}switch")
    assert switch is not None
    return switch


def test_switch_selects_matching_language() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <switch>
                <g systemLanguage='fr'>FR</g>
                <g systemLanguage='en'>EN</g>
                <g>Fallback</g>
            </switch>
        </svg>
    """
    switch = _make_switch(markup)
    harness = SwitchHarness(languages=("en",))

    result = harness._convert_switch(
        element=switch,
        coord_space=None,
        current_navigation=None,
        traverse_callback=lambda node, nav: [node.text],
    )
    assert result == ['EN']


def test_switch_uses_fallback_when_no_match() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <switch>
                <g systemLanguage='de'>DE</g>
                <g requiredFeatures='http://www.w3.org/TR/SVG11/feature#Unknown'>Bad</g>
                <g>Fallback</g>
            </switch>
        </svg>
    """
    switch = _make_switch(markup)
    harness = SwitchHarness(languages=("en",))

    result = harness._convert_switch(
        element=switch,
        coord_space=None,
        current_navigation=None,
        traverse_callback=lambda node, nav: [node.text],
    )
    assert result == ['Fallback']


def test_switch_respects_required_features() -> None:
    markup = """
        <svg xmlns='http://www.w3.org/2000/svg'>
            <switch>
                <g requiredFeatures='http://www.w3.org/TR/SVG11/feature#BasicText'>Feature</g>
                <g>Fallback</g>
            </switch>
        </svg>
    """
    switch = _make_switch(markup)
    harness = SwitchHarness(languages=("en",))

    result = harness._convert_switch(
        element=switch,
        coord_space=None,
        current_navigation=None,
        traverse_callback=lambda node, nav: [node.text],
    )
    assert result == ['Feature']


def test_switch_evaluator_matches_language_directly() -> None:
    markup = """
        <switch xmlns='http://www.w3.org/2000/svg'>
            <g systemLanguage='es'>ES</g>
            <g systemLanguage='en-US'>EN-US</g>
            <g>Fallback</g>
        </switch>
    """
    switch = etree.fromstring(markup)
    evaluator = SwitchEvaluator(system_languages=("en-GB", "en-US"), supported_features={})
    target = evaluator.select_child(switch)
    assert target is not None
    assert target.text == 'EN-US'
