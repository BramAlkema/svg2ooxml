from __future__ import annotations

import subprocess

import pytest

from tools.visual.renderer import (
    LibreOfficeRenderer,
    PowerPointRenderer,
    VisualRendererError,
    resolve_renderer,
)
from tools.visual.stack import default_visual_stack


def test_libreoffice_renderer_darwin_failure_raises_visual_error(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"fake-pptx")
    output_dir = tmp_path / "render"

    renderer = LibreOfficeRenderer(soffice_path="/usr/bin/soffice", png_dpi=None)

    def fake_run(*args, **kwargs):  # noqa: ARG001
        return subprocess.CompletedProcess(args=["soffice"], returncode=1, stdout="boom", stderr="bad")

    monkeypatch.setattr("tools.visual.renderer.platform.system", lambda: "Darwin")
    monkeypatch.setattr("tools.visual.renderer.subprocess.run", fake_run)

    with pytest.raises(VisualRendererError, match="LibreOffice failed to render PPTX"):
        renderer.render(pptx_path, output_dir)


def test_resolve_renderer_supports_powerpoint() -> None:
    renderer = resolve_renderer(renderer_name="powerpoint")

    assert isinstance(renderer, PowerPointRenderer)


def test_resolve_renderer_rejects_unknown_renderer() -> None:
    with pytest.raises(ValueError, match="Unknown visual renderer"):
        resolve_renderer(renderer_name="bogus")


def test_default_visual_stack_respects_renderer_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SVG2OOXML_VISUAL_RENDERER", "powerpoint")

    stack = default_visual_stack()

    assert isinstance(stack.renderer, PowerPointRenderer)
