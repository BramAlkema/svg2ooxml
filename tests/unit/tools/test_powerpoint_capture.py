from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import tools.visual.pptx_window as pptx_window
from tools.visual import powerpoint_capture


def test_get_window_id_via_jxa_guards_non_array_window_lists(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_osascript_jxa(script: str, *, timeout: float | None = 30.0) -> str:
        captured["script"] = script
        return "12345"

    monkeypatch.setattr(pptx_window, "osascript_jxa", fake_osascript_jxa)

    result = pptx_window.get_window_id_via_jxa(("microsoft powerpoint",))

    assert result == "12345"
    script = captured["script"]
    assert "if (!windows || !windows.filter)" in script
    assert "if (!windowsAll || !windowsAll.filter)" in script


def test_start_slideshow_prefers_windowed_object_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_osascript(script: str, *, timeout: float | None = 30.0) -> str:
        captured["script"] = script
        captured["timeout"] = timeout
        return ""

    monkeypatch.setattr(powerpoint_capture, "_osascript", fake_osascript)

    powerpoint_capture._start_slideshow(
        Path("/tmp/sample.pptx"),
        delay=1.5,
        slideshow_delay=1.0,
        open_timeout=120.0,
        use_keys=False,
        allow_reopen=True,
    )

    script = captured["script"]
    assert "launch" in script
    assert "repeat with pres in presentations" in script
    assert "run slide show slide show settings of active presentation" in script
    assert (
        "set show type of slide show settings of active presentation "
        "to slide show type window"
    ) in script
    assert 'set targetName to "sample.pptx"' in script
    assert "Unable to start slideshow via PowerPoint object model." in script


def test_capture_pptx_slideshow_closes_presentation_after_capture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        powerpoint_capture,
        "_start_slideshow",
        lambda *args, **kwargs: calls.append("start"),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_get_slideshow_window_id", lambda timeout=0.0: "123"
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_capture_window",
        lambda output_path, window_id, *, backend, timeout: (
            calls.append(f"capture:{window_id}:{backend}"),
            output_path.parent.mkdir(parents=True, exist_ok=True),
            output_path.write_bytes(b"png"),
        ),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_exit_slideshow", lambda: calls.append("exit")
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_close_active_presentation",
        lambda: calls.append("close"),
    )

    output_path = tmp_path / "slide_1.png"
    powerpoint_capture.capture_pptx_slideshow(
        Path("/tmp/sample.pptx"),
        output_path,
        delay=1.0,
        slideshow_delay=0.5,
        open_timeout=30.0,
        capture_timeout=5.0,
        exit_after=True,
        use_keys=False,
        allow_reopen=False,
        backend="auto",
    )

    assert output_path.exists()
    assert calls == ["start", "capture:123:auto", "exit", "close"]


def test_permission_notice_is_shown_once(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(powerpoint_capture.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(powerpoint_capture.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(powerpoint_capture.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("SVG2OOXML_POWERPOINT_SKIP_NOTICE", raising=False)
    monkeypatch.setattr(
        powerpoint_capture,
        "_osascript",
        lambda script, *, timeout=30.0: calls.append(script) or "",
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_POWERPOINT_PERMISSION_NOTICE_SHOWN",
        False,
    )

    powerpoint_capture._maybe_prompt_for_permissions()
    powerpoint_capture._maybe_prompt_for_permissions()

    assert len(calls) == 1
    assert "Automation" in calls[0]
    assert "Screen Recording" in calls[0]


def test_capture_pptx_slideshow_runs_permission_preflight_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        powerpoint_capture,
        "_maybe_prompt_for_permissions",
        lambda: calls.append("prompt"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_start_slideshow",
        lambda *args, **kwargs: calls.append("start"),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_get_slideshow_window_id", lambda timeout=0.0: "123"
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_capture_window",
        lambda output_path, window_id, *, backend, timeout: (
            calls.append(f"capture:{window_id}:{backend}"),
            output_path.parent.mkdir(parents=True, exist_ok=True),
            output_path.write_bytes(b"png"),
        ),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_exit_slideshow", lambda: calls.append("exit")
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_close_active_presentation",
        lambda: calls.append("close"),
    )

    output_path = tmp_path / "slide_1.png"
    powerpoint_capture.capture_pptx_slideshow(
        Path("/tmp/sample.pptx"),
        output_path,
        delay=1.0,
        slideshow_delay=0.5,
        open_timeout=30.0,
        capture_timeout=5.0,
        exit_after=True,
        use_keys=False,
        allow_reopen=False,
        backend="auto",
    )

    assert calls[:2] == ["prompt", "start"]


def test_capture_pptx_slideshow_cleans_up_existing_powerpoint_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        powerpoint_capture,
        "_maybe_prompt_for_permissions",
        lambda: calls.append("prompt"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_cleanup_powerpoint_state",
        lambda: calls.append("cleanup"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_start_slideshow",
        lambda *args, **kwargs: calls.append("start"),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_get_slideshow_window_id", lambda timeout=0.0: "123"
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_capture_window",
        lambda output_path, window_id, *, backend, timeout: (
            calls.append(f"capture:{window_id}:{backend}"),
            output_path.parent.mkdir(parents=True, exist_ok=True),
            output_path.write_bytes(b"png"),
        ),
    )
    monkeypatch.setattr(
        powerpoint_capture, "_exit_slideshow", lambda: calls.append("exit")
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_close_active_presentation",
        lambda: calls.append("close"),
    )

    output_path = tmp_path / "slide_1.png"
    powerpoint_capture.capture_pptx_slideshow(
        Path("/tmp/sample.pptx"),
        output_path,
        delay=1.0,
        slideshow_delay=0.5,
        open_timeout=30.0,
        capture_timeout=5.0,
        exit_after=True,
        use_keys=False,
        allow_reopen=False,
        backend="auto",
    )

    assert calls[:3] == ["prompt", "cleanup", "start"]


def test_capture_live_animation_cleans_up_and_recovers_window_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []
    time_values = iter([100.0, 100.0, 100.2, 100.5, 100.55, 100.9])
    window_ids = iter(["123", "456"])

    monkeypatch.setattr(
        powerpoint_capture,
        "_maybe_prompt_for_permissions",
        lambda: calls.append("prompt"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_cleanup_powerpoint_state",
        lambda: calls.append("cleanup"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_start_slideshow",
        lambda *args, **kwargs: calls.append("start"),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_get_slideshow_window_id",
        lambda timeout=0.0: next(window_ids),
    )

    state = {"fail_once": True}

    def fake_capture(output_path, window_id, *, backend, timeout):
        if state["fail_once"]:
            state["fail_once"] = False
            raise RuntimeError("stale window id")
        calls.append(f"capture:{window_id}:{backend}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"png")

    monkeypatch.setattr(powerpoint_capture, "_capture_window", fake_capture)
    monkeypatch.setattr(powerpoint_capture.time, "time", lambda: next(time_values))
    monkeypatch.setattr(powerpoint_capture.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        powerpoint_capture, "_exit_slideshow", lambda: calls.append("exit")
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_close_active_presentation",
        lambda: calls.append("close"),
    )

    frames = powerpoint_capture.capture_live_animation(
        Path("/tmp/sample.pptx"),
        tmp_path / "frames",
        duration=0.6,
        fps=2.0,
        delay=1.0,
        slideshow_delay=0.5,
        open_timeout=30.0,
        capture_timeout=5.0,
        use_keys=False,
        allow_reopen=False,
        backend="auto",
    )

    assert calls[:3] == ["prompt", "cleanup", "start"]
    assert calls[-2:] == ["exit", "close"]
    assert [frame.name for frame in frames] == ["frame_0000.png", "frame_0001.png"]
    assert "capture:456:auto" in calls


def test_teardown_still_closes_presentation_if_exit_slideshow_fails(
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        powerpoint_capture,
        "_exit_slideshow",
        lambda: (_ for _ in ()).throw(RuntimeError("slideshow still busy")),
    )
    monkeypatch.setattr(
        powerpoint_capture,
        "_close_active_presentation",
        lambda: calls.append("close"),
    )

    powerpoint_capture._teardown_powerpoint_session()

    assert calls == ["close"]


def test_capture_window_times_out_screencapture_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        powerpoint_capture,
        "_capture_window_screen_capture_kit",
        lambda window_id, output_path, *, timeout: (_ for _ in ()).throw(
            RuntimeError("sckit unavailable")
        ),
    )

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(powerpoint_capture.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="screencapture timed out"):
        powerpoint_capture._capture_window(
            tmp_path / "slide_1.png",
            "123",
            backend="auto",
            timeout=2.0,
        )
