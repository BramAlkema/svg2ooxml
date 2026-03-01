from __future__ import annotations

import tools.visual.pptx_window as pptx_window


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
