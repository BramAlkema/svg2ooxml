from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from svg2ooxml.services.fonts import fontforge_utils


def test_suppress_stderr_restores_fd_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        fontforge_utils.os,
        "dup",
        lambda fd: calls.append(("dup", fd)) or 99,
    )
    monkeypatch.setattr(
        fontforge_utils.os,
        "dup2",
        lambda src, dst: calls.append(("dup2", src, dst)),
    )
    monkeypatch.setattr(
        fontforge_utils.os,
        "close",
        lambda fd: calls.append(("close", fd)),
    )

    with pytest.raises(RuntimeError, match="boom"):
        with fontforge_utils.suppress_stderr():
            raise RuntimeError("boom")

    assert ("dup", 2) in calls
    assert ("dup2", 99, 2) in calls
    assert calls[-1] == ("close", 99)


def test_open_font_wraps_fontforge_open_with_suppressed_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    @contextmanager
    def fake_suppress() -> object:
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    class FakeFont:
        def close(self) -> None:
            events.append("close")

    class FakeFontForge:
        def open(self, path: str) -> FakeFont:
            events.append(("open", path))
            return FakeFont()

    monkeypatch.setattr(fontforge_utils, "FONTFORGE_AVAILABLE", True)
    monkeypatch.setattr(fontforge_utils, "fontforge", FakeFontForge())
    monkeypatch.setattr(fontforge_utils, "suppress_stderr", fake_suppress)

    with fontforge_utils.open_font("/tmp/sample.ttf") as font:
        assert isinstance(font, FakeFont)

    assert events == ["enter", ("open", "/tmp/sample.ttf"), "exit", "close"]


def test_generate_font_bytes_wraps_generate_with_suppressed_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    @contextmanager
    def fake_suppress() -> object:
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    class FakeFont:
        def generate(self, path: str) -> None:
            events.append(("generate", path))
            Path(path).write_bytes(b"font-bytes")

    monkeypatch.setattr(fontforge_utils, "suppress_stderr", fake_suppress)

    payload = fontforge_utils.generate_font_bytes(FakeFont(), suffix=".ttf")

    assert payload == b"font-bytes"
    assert events[0] == "enter"
    assert events[1][0] == "generate"
    assert events[2] == "exit"
    generated_path = Path(events[1][1])
    assert not generated_path.exists()
