"""Helpers for invoking OpenXML validators efficiently."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_OPENXML_AUDIT_NAMES = frozenset({"openxml-audit", "openxml-audit.py"})
_THREAD_LOCAL_STATE = threading.local()
_API_UNSET = object()
_OPENXML_AUDIT_API: object | tuple[type[Any], Any, Any] | None = _API_UNSET


def resolve_openxml_validator(path_value: str | None) -> list[str] | None:
    """Resolve an OpenXML validator path to a subprocess command."""
    if not path_value:
        return None
    candidate = Path(path_value).expanduser()
    if candidate.is_dir():
        for name in (
            "openxml-validator",
            "openxml-validator.py",
            "openxml-audit",
            "openxml-audit.py",
        ):
            path = candidate / name
            if path.exists():
                candidate = path
                break
    if candidate.exists():
        if candidate.suffix == ".py":
            return [sys.executable, str(candidate)]
        return [str(candidate)]

    import shutil

    found = shutil.which(path_value)
    if found:
        return [found]
    return None


def run_openxml_audit(
    pptx_path: Path,
    validator_cmd: list[str] | None,
    timeout_s: float | None,
    *,
    validator_path_value: str | None = None,
    strict: bool = True,
    subprocess_args: list[str] | None = None,
) -> tuple[bool | None, list[str] | None]:
    """Run the configured OpenXML validator against a PPTX file."""
    if validator_cmd is None:
        return None, None

    if _is_openxml_audit_command(validator_path_value, validator_cmd):
        runner = _get_inprocess_runner(strict=strict)
        if runner is not None and _supports_inprocess_timeout(timeout_s):
            return runner.run(pptx_path, timeout_s)

    return _run_openxml_audit_subprocess(
        pptx_path,
        validator_cmd,
        timeout_s,
        subprocess_args=subprocess_args,
    )


class _InProcessOpenXmlAuditRunner:
    """Reusable in-process wrapper around openxml-audit's Python API."""

    def __init__(self, *, strict: bool):
        api = _load_openxml_audit_api()
        if api is None:  # pragma: no cover - guarded by caller
            raise ImportError("openxml-audit is not importable")
        OpenXmlValidator, FileFormat, ValidationSeverity = api
        self._validator = OpenXmlValidator(
            file_format=FileFormat.OFFICE_2019,
            strict=strict,
        )
        self._validation_severity = ValidationSeverity

    def run(
        self,
        pptx_path: Path,
        timeout_s: float | None,
    ) -> tuple[bool | None, list[str] | None]:
        try:
            result = _call_with_timeout(
                lambda: self._validator.validate(pptx_path),
                timeout_s,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return False, [str(exc)]
        return result.is_valid, _format_validation_messages(
            result,
            self._validation_severity,
        )


def _run_openxml_audit_subprocess(
    pptx_path: Path,
    validator_cmd: list[str],
    timeout_s: float | None,
    *,
    subprocess_args: list[str] | None = None,
) -> tuple[bool | None, list[str] | None]:
    try:
        result = subprocess.run(
            [*validator_cmd, *(subprocess_args or []), str(pptx_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, [str(exc)]
    output = "\n".join([result.stdout.strip(), result.stderr.strip()]).strip()
    messages = [line for line in output.splitlines() if line.strip()]
    if len(messages) > 25:
        messages = messages[:25]
    return result.returncode == 0, messages or None


def _is_openxml_audit_command(
    validator_path_value: str | None,
    validator_cmd: list[str],
) -> bool:
    candidate_names: set[str] = set()
    if validator_path_value:
        candidate_names.add(Path(validator_path_value).name)
    for part in validator_cmd:
        name = Path(part).name
        if name:
            candidate_names.add(name)
    return bool(candidate_names & _OPENXML_AUDIT_NAMES)


def _get_inprocess_runner(*, strict: bool) -> _InProcessOpenXmlAuditRunner | None:
    if _load_openxml_audit_api() is None:
        return None
    cache = getattr(_THREAD_LOCAL_STATE, "runner_cache", None)
    if cache is None:
        cache = {}
        _THREAD_LOCAL_STATE.runner_cache = cache
    cache_key = ("openxml-audit", strict)
    runner = cache.get(cache_key)
    if runner is None:
        runner = _InProcessOpenXmlAuditRunner(strict=strict)
        cache[cache_key] = runner
    return runner


def _load_openxml_audit_api() -> tuple[type[Any], Any, Any] | None:
    global _OPENXML_AUDIT_API

    if _OPENXML_AUDIT_API is not _API_UNSET:
        return _OPENXML_AUDIT_API if isinstance(_OPENXML_AUDIT_API, tuple) else None

    try:
        from openxml_audit import OpenXmlValidator
        from openxml_audit.errors import FileFormat, ValidationSeverity
    except ImportError:
        sibling_src = Path(__file__).resolve().parents[3].parent / "openxml-audit" / "src"
        if sibling_src.is_dir() and str(sibling_src) not in sys.path:
            sys.path.insert(0, str(sibling_src))
            try:
                from openxml_audit import OpenXmlValidator
                from openxml_audit.errors import FileFormat, ValidationSeverity
            except ImportError:
                _OPENXML_AUDIT_API = None
                return None
        else:
            _OPENXML_AUDIT_API = None
            return None

    _OPENXML_AUDIT_API = (OpenXmlValidator, FileFormat, ValidationSeverity)
    return _OPENXML_AUDIT_API


def _supports_inprocess_timeout(timeout_s: float | None) -> bool:
    if timeout_s is None or timeout_s <= 0:
        return True
    return (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, "SIGALRM")
        and hasattr(signal, "ITIMER_REAL")
        and hasattr(signal, "getitimer")
        and hasattr(signal, "setitimer")
    )


def _call_with_timeout(callback: Any, timeout_s: float | None) -> Any:
    if timeout_s is None or timeout_s <= 0:
        return callback()

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _handle_timeout(_signum: int, _frame: Any) -> None:
        raise TimeoutError(f"timed out after {timeout_s:.1f}s")

    signal.signal(signal.SIGALRM, _handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _format_validation_messages(result: Any, validation_severity: Any) -> list[str] | None:
    errors = [error for error in result.errors if error.severity == validation_severity.ERROR]
    messages: list[str] = []
    for idx, error in enumerate(errors, start=1):
        messages.append(f"{idx}. {error.description}")
        messages.append(f"   Part: {error.part_uri}")
        messages.append(f"   Path: {error.path}")
        messages.append(f"   Node: {error.node or ''}")
    messages.append(f"Errors: {len(errors)}")
    if len(messages) > 25:
        messages = messages[:25]
    return messages or None


__all__ = [
    "resolve_openxml_validator",
    "run_openxml_audit",
]
