from __future__ import annotations

import subprocess
from pathlib import Path

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
        return subprocess.CompletedProcess(
            args=["soffice"], returncode=1, stdout="boom", stderr="bad"
        )

    monkeypatch.setattr("tools.visual.renderer.platform.system", lambda: "Darwin")
    monkeypatch.setattr("tools.visual.renderer.subprocess.run", fake_run)

    with pytest.raises(VisualRendererError, match="LibreOffice failed to render PPTX"):
        renderer.render(pptx_path, output_dir)


def test_resolve_renderer_supports_powerpoint() -> None:
    renderer = resolve_renderer(renderer_name="powerpoint")

    assert isinstance(renderer, PowerPointRenderer)
    assert renderer._delay == 0.5
    assert renderer._slideshow_delay == 0.25
    assert renderer._open_timeout == 30.0
    assert renderer._capture_timeout == 3.0
    assert renderer._use_keys is False


def test_resolve_renderer_allows_powerpoint_key_fallback_override() -> None:
    renderer = resolve_renderer(
        renderer_name="powerpoint",
        powerpoint_use_keys=True,
    )

    assert isinstance(renderer, PowerPointRenderer)
    assert renderer._use_keys is True


def test_resolve_renderer_rejects_unknown_renderer() -> None:
    with pytest.raises(ValueError, match="Unknown visual renderer"):
        resolve_renderer(renderer_name="bogus")


def test_default_visual_stack_respects_renderer_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SVG2OOXML_VISUAL_RENDERER", "powerpoint")

    stack = default_visual_stack()

    assert isinstance(stack.renderer, PowerPointRenderer)


def test_powerpoint_renderer_uses_slideshow_capture(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"fake-pptx")
    output_dir = tmp_path / "render"

    renderer = PowerPointRenderer()
    captured: dict[str, object] = {}

    monkeypatch.setattr("tools.visual.renderer.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "tools.visual.renderer.shutil.which", lambda cmd: "/usr/bin/osascript"
    )

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs["timeout"]
        output_path = Path(cmd[4])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("tools.visual.renderer.subprocess.run", fake_run)

    result = renderer.render(pptx_path, output_dir)

    assert result.images == (output_dir / "slide_1.png",)
    assert captured["cmd"][1:4] == ["-m", "tools.visual.powerpoint_capture", str(pptx_path)]
    assert captured["cmd"][4] == str(output_dir / "slide_1.png")
    assert "--mode" in captured["cmd"]
    assert "slideshow" in captured["cmd"]
    assert "--no-keys" in captured["cmd"]


def test_powerpoint_renderer_captures_live_animation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"fake-pptx")
    output_dir = tmp_path / "render_animation"

    renderer = PowerPointRenderer()
    captured: dict[str, object] = {}

    monkeypatch.setattr("tools.visual.renderer.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "tools.visual.renderer.shutil.which", lambda cmd: "/usr/bin/osascript"
    )

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["timeout"] = kwargs["timeout"]
        output_dir = Path(cmd[4])
        output_dir.mkdir(parents=True, exist_ok=True)
        frame = output_dir / "frame_0000.png"
        frame.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("tools.visual.renderer.subprocess.run", fake_run)

    result = renderer.capture_animation(
        pptx_path,
        output_dir,
        duration=2.5,
        fps=8.0,
    )

    assert result == (output_dir / "frame_0000.png",)
    assert captured["cmd"][1:4] == ["-m", "tools.visual.powerpoint_capture", str(pptx_path)]
    assert captured["cmd"][4] == str(output_dir)
    assert "live" in captured["cmd"]
    assert "2.5" in captured["cmd"]
    assert "8.0" in captured["cmd"]
