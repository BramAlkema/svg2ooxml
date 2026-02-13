from __future__ import annotations

from pathlib import Path

from svg2ooxml.api.services.export_settings import ParallelExportSettings


def test_enable_parses_non_false(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SVG2OOXML_PARALLEL_ENABLE", "enabled")
    monkeypatch.delenv("SVG2OOXML_PARALLEL_DISABLE", raising=False)
    settings = ParallelExportSettings.from_env(tmp_dir=tmp_path)
    assert settings.enabled is True
    assert settings.should_use_parallel(settings.threshold) is True


def test_disable_overrides_force(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SVG2OOXML_PARALLEL_FORCE", "1")
    monkeypatch.setenv("SVG2OOXML_PARALLEL_DISABLE", "1")
    settings = ParallelExportSettings.from_env(tmp_dir=tmp_path)
    assert settings.disabled is True
    assert settings.should_use_parallel(settings.threshold) is False


def test_bundle_dir_falls_back_on_invalid_path(monkeypatch, tmp_path: Path) -> None:
    bogus_path = tmp_path / "not_a_dir"
    bogus_path.write_text("nope")
    monkeypatch.setenv("SVG2OOXML_BUNDLE_DIR", str(bogus_path))
    settings = ParallelExportSettings.from_env(tmp_dir=tmp_path)
    expected_dir = tmp_path / "bundles"
    assert settings.bundle_dir == expected_dir
    assert expected_dir.is_dir()
