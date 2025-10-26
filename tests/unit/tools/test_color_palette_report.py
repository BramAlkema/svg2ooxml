from __future__ import annotations

import io
import textwrap

import importlib

import pytest

try:
    color_palette_report = importlib.import_module("tools.color_palette_report")
except ImportError as exc:
    pytest.skip(
        f"Advanced colour stack not installed: {exc}",
        allow_module_level=True,
    )


def test_palette_report_basic(capsys):
    exit_code = color_palette_report.main(["#ff0000", "#00ff00", "#0000ff"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Palette Summary" in output
    assert "#FF0000" in output


def test_palette_report_requires_colour_input():
    with pytest.raises(SystemExit):
        color_palette_report.main([])
