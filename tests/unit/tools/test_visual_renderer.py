from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from tools.visual.renderer import (
    LibreOfficeRenderer,
    PowerPointRenderer,
    VisualRendererError,
    _detect_slide_crop_box,
    _normalize_pngs,
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
        output_dir = Path(cmd[4])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "slide_1.png").write_bytes(
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
    assert captured["cmd"][4] == str(output_dir)
    assert "--mode" in captured["cmd"]
    assert "slideshow-all" in captured["cmd"]
    assert "--slide-delay" in captured["cmd"]
    assert "--no-keys" in captured["cmd"]


def test_powerpoint_renderer_sorts_slide_images_numerically(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"fake-pptx")
    output_dir = tmp_path / "render"

    renderer = PowerPointRenderer()

    monkeypatch.setattr("tools.visual.renderer.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "tools.visual.renderer.shutil.which", lambda cmd: "/usr/bin/osascript"
    )

    def fake_run(cmd, **kwargs):  # noqa: ARG001
        output_dir = Path(cmd[4])
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
            b"\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c``\x00\x00\x00\x04\x00\x01"
            b"\x0b\xe7\x02\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        for name in ("slide_10.png", "slide_2.png", "slide_1.png"):
            (output_dir / name).write_bytes(payload)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr("tools.visual.renderer.subprocess.run", fake_run)

    result = renderer.render(pptx_path, output_dir)

    assert result.images == (
        output_dir / "slide_1.png",
        output_dir / "slide_2.png",
        output_dir / "slide_10.png",
    )


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


def test_detect_slide_crop_box_finds_square_slide_inside_window() -> None:
    image = Image.new("RGB", (3164, 2070), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((686, 133, 2475, 1921), fill="white")

    crop_box = _detect_slide_crop_box(image, target_size=(1000, 1000))

    assert crop_box == (686, 133, 2476, 1922)


def test_detect_slide_crop_box_finds_widescreenish_slide_inside_window() -> None:
    image = Image.new("RGB", (3164, 2070), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((388, 133, 2773, 1921), fill="white")

    crop_box = _detect_slide_crop_box(image, target_size=(480, 360))

    assert crop_box == (388, 133, 2774, 1922)


def test_detect_slide_crop_box_ignores_center_content_shape() -> None:
    image = Image.new("RGB", (480, 360), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 140, 449, 219), fill="#44AAFF")

    crop_box = _detect_slide_crop_box(image, target_size=(480, 360))

    assert crop_box is None


def test_normalize_pngs_crops_before_resizing(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"fake-pptx")
    image_path = tmp_path / "slide_1.png"

    image = Image.new("RGB", (3164, 2070), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((686, 133, 2475, 1921), fill="white")
    image.save(image_path)

    monkeypatch.setattr(
        "tools.visual.renderer._slide_size_to_pixels",
        lambda pptx_path, dpi: (1000, 1000),
    )

    _normalize_pngs(pptx_path, (image_path,), 96.0)

    with Image.open(image_path) as normalized:
        assert normalized.size == (1000, 1000)
        assert normalized.getpixel((10, 10)) == (255, 255, 255)
        assert normalized.getpixel((normalized.width - 10, 10)) == (255, 255, 255)
