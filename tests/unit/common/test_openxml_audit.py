from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from svg2ooxml.common import openxml_audit as module


@dataclass
class _FakeError:
    description: str
    part_uri: str = ""
    path: str = ""
    node: str | None = None
    severity: str = "error"


@dataclass
class _FakeResult:
    is_valid: bool
    errors: list[_FakeError]


class _FakeSeverity:
    ERROR = "error"


def test_run_openxml_audit_reuses_inprocess_runner(monkeypatch, tmp_path: Path) -> None:
    state = {"init_calls": 0, "validate_calls": 0}

    class FakeValidator:
        def __init__(self, *, file_format, strict: bool):
            assert file_format == "office2019"
            assert strict is True
            state["init_calls"] += 1

        def validate(self, path: Path) -> _FakeResult:
            assert path == tmp_path / "sample.pptx"
            state["validate_calls"] += 1
            return _FakeResult(is_valid=True, errors=[])

    monkeypatch.setattr(
        module,
        "_OPENXML_AUDIT_API",
        (FakeValidator, SimpleNamespace(OFFICE_2019="office2019"), _FakeSeverity),
    )
    monkeypatch.setattr(module, "_THREAD_LOCAL_STATE", SimpleNamespace())
    monkeypatch.setattr(module, "_supports_inprocess_timeout", lambda timeout_s: True)

    called = {"subprocess": 0}

    def fake_subprocess_run(*args, **kwargs):
        called["subprocess"] += 1
        raise AssertionError("subprocess runner should not be used")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"pptx")

    first = module.run_openxml_audit(
        pptx_path,
        ["/usr/local/bin/openxml-audit"],
        60.0,
        validator_path_value="openxml-audit",
    )
    second = module.run_openxml_audit(
        pptx_path,
        ["/usr/local/bin/openxml-audit"],
        60.0,
        validator_path_value="openxml-audit",
    )

    assert first == (True, ["Errors: 0"])
    assert second == (True, ["Errors: 0"])
    assert state == {"init_calls": 1, "validate_calls": 2}
    assert called["subprocess"] == 0


def test_run_openxml_audit_formats_errors_from_inprocess_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FakeValidator:
        def __init__(self, *, file_format, strict: bool):
            assert file_format == "office2019"
            assert strict is False

        def validate(self, path: Path) -> _FakeResult:
            assert path == tmp_path / "broken.pptx"
            return _FakeResult(
                is_valid=False,
                errors=[
                    _FakeError(
                        description="Missing relationship target",
                        part_uri="/ppt/slides/slide1.xml",
                        path="/p:sld/p:cSld",
                        node="p:cSld",
                    ),
                ],
            )

    monkeypatch.setattr(
        module,
        "_OPENXML_AUDIT_API",
        (FakeValidator, SimpleNamespace(OFFICE_2019="office2019"), _FakeSeverity),
    )
    monkeypatch.setattr(module, "_THREAD_LOCAL_STATE", SimpleNamespace())
    monkeypatch.setattr(module, "_supports_inprocess_timeout", lambda timeout_s: True)

    pptx_path = tmp_path / "broken.pptx"
    pptx_path.write_bytes(b"pptx")

    valid, messages = module.run_openxml_audit(
        pptx_path,
        ["/usr/local/bin/openxml-audit"],
        60.0,
        validator_path_value="openxml-audit",
        strict=False,
    )

    assert valid is False
    assert messages == [
        "1. Missing relationship target",
        "   Part: /ppt/slides/slide1.xml",
        "   Path: /p:sld/p:cSld",
        "   Node: p:cSld",
        "Errors: 1",
    ]


def test_run_openxml_audit_falls_back_to_subprocess_for_other_validators(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(module, "_THREAD_LOCAL_STATE", SimpleNamespace())

    def fake_subprocess_run(cmd, capture_output, text, timeout):
        assert cmd == ["custom-validator", str(tmp_path / "sample.pptx")]
        assert capture_output is True
        assert text is True
        assert timeout == 12.0
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="Errors: 0\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    pptx_path = tmp_path / "sample.pptx"
    pptx_path.write_bytes(b"pptx")

    valid, messages = module.run_openxml_audit(
        pptx_path,
        ["custom-validator"],
        12.0,
        validator_path_value="custom-validator",
    )

    assert valid is True
    assert messages == ["Errors: 0"]
