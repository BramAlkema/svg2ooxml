"""Font service scaffolding tests."""

import os

from svg2ooxml.services.fonts import (
    FontMatch,
    FontQuery,
    FontService,
    FontSystem,
    FontSystemConfig,
    collect_font_directories,
)
from svg2ooxml.services.fonts.providers import DirectoryFontProvider
from svg2ooxml.services.setup import configure_services


def test_collect_font_directories_honours_env(monkeypatch, tmp_path) -> None:
    system_dir = tmp_path / "system"
    system_dir.mkdir()
    env_dir = tmp_path / "env"
    env_dir.mkdir()

    import svg2ooxml.services.fonts.system as font_system

    monkeypatch.setattr(font_system, "_platform_default_directories", lambda: (str(system_dir),))
    monkeypatch.setenv("SVG2OOXML_FONT_DIRS", os.pathsep.join([str(env_dir), str(system_dir)]))

    directories = collect_font_directories()

    assert system_dir.resolve() in directories
    assert env_dir.resolve() in directories
    assert len(directories) == 2

    monkeypatch.delenv("SVG2OOXML_FONT_DIRS", raising=False)


class _StaticFontProvider:
    def __init__(self, match: FontMatch) -> None:
        self._match = match
        self.calls = 0

    def resolve(self, query: FontQuery) -> FontMatch | None:
        self.calls += 1
        if query.family.lower() == self._match.family.lower():
            return self._match
        return None

    def list_alternatives(self, query: FontQuery):
        if query.family.lower() == self._match.family.lower():
            yield self._match


def test_configure_services_wires_font_services() -> None:
    services = configure_services()

    assert services.font_service is not None
    assert services.font_embedding_engine is not None


def test_font_service_uses_registered_provider() -> None:
    provider = _StaticFontProvider(
        FontMatch(
            family="Inter",
            path="/fonts/Inter-Regular.ttf",
            weight=400,
            style="normal",
            found_via="static",
        )
    )
    service = FontService()
    service.register_provider(provider)

    query = FontQuery(family="Inter")
    match = service.find_font(query)

    assert match is not None
    assert match.family == "Inter"
    assert provider.calls == 1

    # Cached result should avoid additional provider calls.
    cached = service.find_font(query)
    assert cached is match
    assert provider.calls == 1


def test_directory_provider_indexes_fonts(tmp_path) -> None:
    font_path = tmp_path / "Demo-Bold.ttf"
    font_path.write_text("", encoding="utf-8")

    provider = DirectoryFontProvider((tmp_path,))
    service = FontService()
    service.register_provider(provider)

    query = FontQuery(family="Demo", weight=700)
    match = service.find_font(query)

    assert match is not None
    assert match.path == str(font_path)
    assert match.family == "Demo"


def test_font_provider_registers_default_directories(monkeypatch, tmp_path) -> None:
    font_path = tmp_path / "Family-Regular.ttf"
    font_path.write_text("", encoding="utf-8")

    from svg2ooxml.services.providers import font_provider

    monkeypatch.setattr(font_provider, "collect_font_directories", lambda: (tmp_path,))

    service = font_provider._build_font_service()
    query = FontQuery(family="Family")
    match = service.find_font(query)

    assert match is not None
    assert match.path == str(font_path)


def test_font_system_registers_directories(monkeypatch, tmp_path) -> None:
    font_path = tmp_path / "SystemFont.ttf"
    font_path.write_text("", encoding="utf-8")

    service = FontService()
    config = FontSystemConfig(directories=(tmp_path,))
    system = FontSystem(service, config=config)

    query = FontQuery(family="SystemFont")
    match = system.find_font(query)

    assert match is not None
    assert match.path == str(font_path)
