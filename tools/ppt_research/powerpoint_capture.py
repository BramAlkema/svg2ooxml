"Capture a PowerPoint window screenshot via osascript + screencapture."

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from tools.ppt_research.powerpoint_capture_backend import (  # noqa: E402
    _capture_window_screen_capture_kit,
)
from tools.ppt_research.powerpoint_capture_scripts import (  # noqa: E402
    _applescript_string,
    _matching_presentation_script,
    build_start_slideshow_script,
)
from tools.ppt_research.pptx_window import (  # noqa: E402
    get_front_window_id as _get_front_window_id,
)
from tools.ppt_research.pptx_window import (
    get_slideshow_window_id as _get_slideshow_window_id,
)
from tools.ppt_research.pptx_window import (
    get_window_id_via_jxa as _get_window_id_via_jxa,
)
from tools.ppt_research.pptx_window import (
    open_presentation_via_ui as _open_presentation_via_ui,
)
from tools.ppt_research.pptx_window import (
    osascript as _osascript,
)

_POWERPOINT_PERMISSION_NOTICE_SHOWN = False


def _powerpoint_stage_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "reports"
        / "visual"
        / "powerpoint"
        / ".capture-stage"
    )


def _prepare_staged_presentation(pptx_path: Path) -> Path:
    source = pptx_path.resolve()
    stage_dir = _powerpoint_stage_dir()
    stage_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix or ".pptx"
    stage_name = f"{source.stem or 'presentation'}-{uuid.uuid4().hex[:12]}{suffix}"
    staged = stage_dir / stage_name
    shutil.copy2(source, staged)
    return staged


def _discard_staged_presentation(pptx_path: Path | None) -> None:
    if pptx_path is None:
        return

    stage_dir = _powerpoint_stage_dir().resolve(strict=False)
    staged_path = pptx_path.resolve(strict=False)
    try:
        staged_path.relative_to(stage_dir)
    except ValueError:
        return

    for path in (staged_path, _powerpoint_lockfile_path(staged_path)):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _powerpoint_lockfile_path(pptx_path: Path) -> Path:
    return pptx_path.resolve().with_name(f"~${pptx_path.name}")


def _diagnostic_artifact_paths(debug_dir: Path) -> tuple[Path, Path]:
    debug_dir = debug_dir.resolve()
    return (
        debug_dir / "powerpoint_diagnostics.json",
        debug_dir / "powerpoint_debug.png",
    )


def _clear_diagnostic_artifacts(debug_dir: Path) -> None:
    for path in _diagnostic_artifact_paths(debug_dir):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _collect_powerpoint_debug_state() -> dict[str, str]:
    script = """
set outText to ""
on appendLine(existingText, keyText, valueText)
    return existingText & keyText & tab & valueText & linefeed
end appendLine

set powerpointRunning to false
set processWindowCount to 0
set frontWindowTitle to ""
set frontWindowSubrole to ""

try
    tell application "System Events"
        set powerpointRunning to exists process "Microsoft PowerPoint"
        if powerpointRunning then
            tell process "Microsoft PowerPoint"
                try
                    set processWindowCount to count of windows
                end try
                if processWindowCount > 0 then
                    try
                        set frontWindowTitle to name of front window
                    end try
                    try
                        set frontWindowSubrole to subrole of front window
                    end try
                end if
            end tell
        end if
    end tell
on error
end try

set outText to my appendLine(outText, "powerpoint_running", (powerpointRunning as string))
set outText to my appendLine(outText, "process_window_count", (processWindowCount as string))
set outText to my appendLine(outText, "front_window_title", frontWindowTitle)
set outText to my appendLine(outText, "front_window_subrole", frontWindowSubrole)
return outText
"""
    state: dict[str, str] = {}
    try:
        output = _osascript(script, timeout=10.0)
    except Exception as exc:
        state["state_error"] = str(exc)
        return state
    for line in output.splitlines():
        if "\t" not in line:
            continue
        key, value = line.split("\t", 1)
        state[key] = value
    try:
        state["powerpoint_window_id"] = _get_window_id_via_jxa(
            ("Microsoft PowerPoint",)
        )
    except Exception as exc:
        state["powerpoint_window_id_error"] = str(exc)
    try:
        state["slideshow_window_id"] = _get_window_id_via_jxa(
            ("Microsoft PowerPoint Slide Show", "PowerPoint Slide Show"),
            name_excludes=("presenter",),
        )
    except Exception as exc:
        state["slideshow_window_id_error"] = str(exc)
    if not state.get("slideshow_window_id"):
        try:
            state["slideshow_window_id"] = _get_window_id_via_jxa(
                ("Microsoft PowerPoint",),
                name_contains=("slide show", "slideshow"),
                name_excludes=("presenter",),
            )
        except Exception as exc:
            state["slideshow_window_id_error"] = str(exc)
    return state


def _capture_debug_screenshot(output_path: Path, *, capture_timeout: float) -> dict[str, str]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    owners = (
        "Microsoft PowerPoint Slide Show",
        "PowerPoint Slide Show",
        "Microsoft PowerPoint",
    )
    window_id = ""
    try:
        window_id = _get_window_id_via_jxa(owners)
    except Exception:
        window_id = ""
    try:
        if window_id:
            _capture_window(
                output_path,
                window_id,
                backend="screencapture",
                timeout=max(1.0, capture_timeout),
            )
        else:
            subprocess.run(
                ["screencapture", "-x", str(output_path)],
                check=True,
                timeout=max(1.0, capture_timeout),
            )
        result = {"debug_screenshot": output_path.name}
        if window_id:
            result["debug_window_id"] = window_id
        return result
    except Exception as exc:
        return {"debug_screenshot_error": str(exc)}


def _write_powerpoint_diagnostics(
    debug_dir: Path,
    *,
    reason: str,
    error: Exception,
    source_pptx: Path,
    staged_pptx: Path | None,
    capture_timeout: float,
) -> Path:
    debug_path, screenshot_path = _diagnostic_artifact_paths(debug_dir)
    payload: dict[str, object] = {
        "reason": reason,
        "error": str(error),
        "source_pptx": str(source_pptx.resolve()),
        "staged_pptx": str(staged_pptx.resolve()) if staged_pptx is not None else None,
        "state": _collect_powerpoint_debug_state(),
    }
    if staged_pptx is not None:
        lockfile_path = _powerpoint_lockfile_path(staged_pptx)
        payload["staged_lockfile"] = str(lockfile_path)
        payload["staged_lockfile_exists"] = lockfile_path.exists()
    payload.update(
        _capture_debug_screenshot(
            screenshot_path,
            capture_timeout=max(3.0, capture_timeout),
        )
    )
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return debug_path


def _raise_with_powerpoint_diagnostics(
    *,
    reason: str,
    error: Exception,
    debug_dir: Path,
    source_pptx: Path,
    staged_pptx: Path | None,
    capture_timeout: float,
) -> None:
    debug_path = _write_powerpoint_diagnostics(
        debug_dir,
        reason=reason,
        error=error,
        source_pptx=source_pptx,
        staged_pptx=staged_pptx,
        capture_timeout=capture_timeout,
    )
    raise RuntimeError(f"{error} [PowerPoint diagnostics: {debug_path}]") from error


def _maybe_prompt_for_permissions() -> None:
    global _POWERPOINT_PERMISSION_NOTICE_SHOWN
    if _POWERPOINT_PERMISSION_NOTICE_SHOWN:
        return
    if platform.system() != "Darwin":
        return
    if os.getenv("SVG2OOXML_POWERPOINT_SKIP_NOTICE", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        _POWERPOINT_PERMISSION_NOTICE_SHOWN = True
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return

    script = """
display dialog "PowerPoint visual capture may trigger macOS prompts for Automation, Screen Recording, and file access.\n\nIf macOS asks, allow your terminal app to control Microsoft PowerPoint and capture the screen. Keeping outputs under reports/visual/powerpoint reduces repeat prompts." with title "svg2ooxml PowerPoint Capture" buttons {"Cancel", "Continue"} default button "Continue" cancel button "Cancel" with icon caution
"""
    try:
        _osascript(script, timeout=30.0)
    except RuntimeError as exc:
        raise RuntimeError(
            "PowerPoint capture cancelled before permission preflight."
        ) from exc
    _POWERPOINT_PERMISSION_NOTICE_SHOWN = True


def _capture_window(
    output_path: Path,
    window_id: str | None,
    *,
    backend: str,
    timeout: float,
) -> None:
    if backend not in {"auto", "screencapture", "sckit"}:
        raise ValueError(f"Unknown capture backend: {backend}")
    if window_id:
        if backend in {"auto", "sckit"}:
            try:
                _capture_window_screen_capture_kit(
                    int(window_id), output_path, timeout=timeout
                )
                return
            except Exception:
                if backend == "sckit":
                    raise
        try:
            subprocess.run(
                [
                    "screencapture",
                    "-x",
                    "-T",
                    "0",
                    "-l",
                    str(window_id),
                    str(output_path),
                ],
                check=True,
                timeout=max(1.0, timeout),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("screencapture timed out while capturing slideshow window") from exc
        return
    if backend == "sckit":
        raise RuntimeError("No window ID for ScreenCaptureKit capture")
    try:
        subprocess.run(
            ["screencapture", "-x", "-T", "0", str(output_path)],
            check=True,
            timeout=max(1.0, timeout),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("screencapture timed out while capturing the screen") from exc


def _get_slide_count() -> int:
    script = """
tell application "Microsoft PowerPoint"
    if (count of presentations) is 0 then
        return "0"
    end if
    return (count slides of active presentation) as string
end tell
"""
    try:
        return int(_osascript(script))
    except Exception:
        return 0


def _has_matching_powerpoint_presentation(pptx_path: Path) -> bool:
    script = (
        _matching_presentation_script(pptx_path)
        + """
tell application "Microsoft PowerPoint"
    set presCount to count of presentations
    repeat with i from 1 to presCount
        set presRef to presentation i
        if my presentationMatches(presRef, targetPosix, targetHfs, targetName) then
            return "true"
        end if
    end repeat
end tell
return "false"
"""
    )
    try:
        return _osascript(script, timeout=5.0).strip().lower() == "true"
    except Exception:
        return False


def _wait_for_powerpoint_window(timeout: float) -> bool:
    deadline = time.time() + max(0.5, timeout)
    while time.time() < deadline:
        try:
            if (
                _osascript(
                    """
tell application "System Events"
    if not (exists process "Microsoft PowerPoint") then
        return "false"
    end if
    tell process "Microsoft PowerPoint"
        return ((count of windows) > 0) as string
    end tell
end tell
""",
                    timeout=5.0,
                ).strip().lower()
                == "true"
            ):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _confirm_powerpoint_recent_open(target_name: str) -> bool:
    script = f"""
set targetName to {_applescript_string(target_name)}
try
    tell application "System Events"
        if not (exists process "Microsoft PowerPoint") then
            return "false"
        end if
        tell process "Microsoft PowerPoint"
            if (count of windows) is 0 then
                return "false"
            end if
            set frontmost to true
            try
                set openButton to button "Open" of window 1
                if enabled of openButton then
                    click openButton
                    return "true"
                end if
            end try
            try
                key code 36
                return "true"
            end try
        end tell
    end tell
on error
end try
return "false"
"""
    try:
        return _osascript(script, timeout=5.0).strip().lower() == "true"
    except Exception:
        return False


def _direct_open_powerpoint_presentation(pptx_path: Path) -> bool:
    script = f"""
set targetPosix to {_applescript_string(str(pptx_path.resolve()))}
tell application "Microsoft PowerPoint"
    activate
    open (POSIX file targetPosix)
end tell
"""
    try:
        _osascript(script, timeout=10.0)
        return True
    except Exception:
        return False


def _wait_for_powerpoint_presentation(pptx_path: Path, timeout: float) -> bool:
    lockfile_path = _powerpoint_lockfile_path(pptx_path)
    wait_start = time.time()
    deadline = wait_start + max(0.5, timeout)
    last_open_confirm = 0.0
    did_direct_open = False
    while time.time() < deadline:
        if _has_matching_powerpoint_presentation(pptx_path):
            return True
        now = time.time()
        if now - last_open_confirm >= 1.0 and _wait_for_powerpoint_window(0.2):
            _confirm_powerpoint_recent_open(pptx_path.name)
            last_open_confirm = now
        if not did_direct_open and now - wait_start >= 2.0:
            _direct_open_powerpoint_presentation(pptx_path)
            did_direct_open = True
        if lockfile_path.exists() and _has_matching_powerpoint_presentation(pptx_path):
            return True
        time.sleep(0.2)
    return _has_matching_powerpoint_presentation(pptx_path)


def _advance_slide() -> None:
    script = """
tell application "System Events"
    key code 124
end tell
"""
    _osascript(script)


def _close_active_presentation() -> None:
    script = """
tell application "Microsoft PowerPoint"
    try
        close active presentation saving no
    end try
end tell
"""
    _osascript(script)


def _close_matching_presentation(pptx_path: Path) -> None:
    script = (
        _matching_presentation_script(pptx_path)
        + """
tell application "Microsoft PowerPoint"
    set presCount to count of presentations
    repeat with i from presCount to 1 by -1
        set presRef to presentation i
        if my presentationMatches(presRef, targetPosix, targetHfs, targetName) then
            try
                close presRef saving no
            end try
            exit repeat
        end if
    end repeat
end tell
"""
    )
    _osascript(script)


def _teardown_powerpoint_session(pptx_path: Path | None = None) -> None:
    try:
        _exit_slideshow()
    except RuntimeError:
        pass
    try:
        if pptx_path is not None:
            _close_matching_presentation(pptx_path)
        else:
            _close_active_presentation()
    except RuntimeError:
        pass


def _cleanup_powerpoint_state() -> None:
    script = """
tell application "Microsoft PowerPoint"
    try
        try
            exit slide show slide show view of slide show window of active presentation
        end try
        set presCount to count of presentations
        repeat with i from presCount to 1 by -1
            close presentation i saving no
        end repeat
    end try
end tell
"""
    try:
        _osascript(script)
    except RuntimeError:
        pass


def _start_slideshow(
    pptx_path: Path,
    delay: float,
    slideshow_delay: float,
    open_timeout: float,
    *,
    use_keys: bool,
    allow_reopen: bool,
) -> None:
    pptx_path = pptx_path.resolve()
    open_attempts = 2 if allow_reopen else 1
    did_open = False
    saw_window = False
    for attempt_index in range(open_attempts):
        _open_presentation_via_ui(
            pptx_path,
            timeout=max(15.0, min(open_timeout, 30.0)),
        )
        if _wait_for_powerpoint_presentation(
            pptx_path,
            timeout=max(5.0, open_timeout / open_attempts),
        ):
            did_open = True
            break
        if _wait_for_powerpoint_window(min(open_timeout, 10.0)):
            saw_window = True
        if attempt_index < (open_attempts - 1):
            time.sleep(0.5)
    if not did_open and not saw_window:
        raise RuntimeError("No PowerPoint presentation after UI open.")
    if not saw_window:
        # Keep probing, but do not fail if the document is already open.
        # The object-model slideshow path can start from the presentation ref
        # even when PowerPoint has not materialized an edit window yet.
        saw_window = _wait_for_powerpoint_window(min(open_timeout, 10.0))
    script = build_start_slideshow_script(
        pptx_path,
        delay=delay,
        slideshow_delay=slideshow_delay,
        use_keys=use_keys,
    )
    timeout = max(60.0, open_timeout + 30.0)
    _osascript(script, timeout=timeout)


def capture_pptx_slideshow_all(
    pptx_path: Path,
    output_dir: Path,
    delay: float,
    slideshow_delay: float,
    slide_delay: float,
    open_timeout: float,
    capture_timeout: float,
    *,
    exit_after: bool,
    use_keys: bool,
    allow_reopen: bool,
    backend: str,
) -> None:
    _maybe_prompt_for_permissions()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_diagnostic_artifacts(output_dir)
    source_pptx = pptx_path.resolve()
    staged_pptx = _prepare_staged_presentation(source_pptx)
    _cleanup_powerpoint_state()
    open_failed_path = output_dir / "open_failed.png"
    if open_failed_path.exists():
        open_failed_path.unlink()

    try:
        _start_slideshow(
            staged_pptx,
            delay,
            slideshow_delay,
            open_timeout,
            use_keys=use_keys,
            allow_reopen=allow_reopen,
        )
        slide_count = _get_slide_count()
        if slide_count <= 0:
            for _ in range(10):
                time.sleep(0.3)
                slide_count = _get_slide_count()
                if slide_count > 0:
                    break
        if slide_count <= 0:
            subprocess.run(
                ["screencapture", "-x", str(open_failed_path)],
                check=True,
            )
            raise RuntimeError("No active slides after repair.")

        slideshow_window_id = _get_slideshow_window_id(
            timeout=max(5.0, slideshow_delay + 5.0)
        )
        for index in range(1, slide_count + 1):
            output_path = output_dir / f"slide_{index}.png"
            if slideshow_window_id:
                try:
                    _capture_window(
                        output_path,
                        slideshow_window_id,
                        backend=backend,
                        timeout=capture_timeout,
                    )
                except Exception:
                    slideshow_window_id = _get_slideshow_window_id(timeout=1.5)
                    _capture_window(
                        output_path,
                        slideshow_window_id,
                        backend=backend,
                        timeout=capture_timeout,
                    )
            else:
                _capture_window(
                    output_path,
                    None,
                    backend=backend,
                    timeout=capture_timeout,
                )
            time.sleep(slide_delay)
            _advance_slide()
    except Exception as exc:
        _raise_with_powerpoint_diagnostics(
            reason="slideshow_all_capture_failed",
            error=exc,
            debug_dir=output_dir,
            source_pptx=source_pptx,
            staged_pptx=staged_pptx,
            capture_timeout=capture_timeout,
        )
    finally:
        if exit_after:
            _teardown_powerpoint_session(staged_pptx)
            _discard_staged_presentation(staged_pptx)


def _exit_slideshow() -> None:
    script = """
tell application "Microsoft PowerPoint"
    try
        exit slide show slide show view of slide show window of active presentation
    end try
end tell
"""
    _osascript(script)
    script = """
tell application "System Events"
    key code 53
end tell
"""
    try:
        _osascript(script)
    except RuntimeError:
        pass


def capture_pptx_window(
    pptx_path: Path,
    output_path: Path,
    delay: float,
    *,
    backend: str,
    capture_timeout: float,
) -> None:
    _maybe_prompt_for_permissions()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _clear_diagnostic_artifacts(output_path.parent)
    source_pptx = pptx_path.resolve()
    staged_pptx = _prepare_staged_presentation(source_pptx)
    try:
        win_id = _get_front_window_id(staged_pptx, delay)
        if not win_id:
            raise RuntimeError("No PowerPoint window ID returned.")
        _capture_window(
            output_path,
            win_id,
            backend=backend,
            timeout=capture_timeout,
        )
    except Exception as exc:
        _raise_with_powerpoint_diagnostics(
            reason="window_capture_failed",
            error=exc,
            debug_dir=output_path.parent,
            source_pptx=source_pptx,
            staged_pptx=staged_pptx,
            capture_timeout=capture_timeout,
        )
    finally:
        _teardown_powerpoint_session(staged_pptx)
        _discard_staged_presentation(staged_pptx)


def capture_pptx_slideshow(
    pptx_path: Path,
    output_path: Path,
    delay: float,
    slideshow_delay: float,
    open_timeout: float,
    capture_timeout: float,
    *,
    exit_after: bool,
    use_keys: bool,
    allow_reopen: bool,
    backend: str,
) -> None:
    _maybe_prompt_for_permissions()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _clear_diagnostic_artifacts(output_path.parent)
    source_pptx = pptx_path.resolve()
    staged_pptx = _prepare_staged_presentation(source_pptx)
    _cleanup_powerpoint_state()
    try:
        _start_slideshow(
            staged_pptx,
            delay,
            slideshow_delay,
            open_timeout,
            use_keys=use_keys,
            allow_reopen=allow_reopen,
        )
        slideshow_window_id = _get_slideshow_window_id(
            timeout=max(5.0, slideshow_delay + 5.0)
        )
        if not slideshow_window_id:
            raise RuntimeError("No slideshow window detected after slideshow start.")
        _capture_window(
            output_path,
            slideshow_window_id,
            backend=backend,
            timeout=capture_timeout,
        )
    except Exception as exc:
        _raise_with_powerpoint_diagnostics(
            reason="slideshow_capture_failed",
            error=exc,
            debug_dir=output_path.parent,
            source_pptx=source_pptx,
            staged_pptx=staged_pptx,
            capture_timeout=capture_timeout,
        )
    finally:
        if exit_after:
            _teardown_powerpoint_session(staged_pptx)
            _discard_staged_presentation(staged_pptx)


def capture_live_animation(
    pptx_path: Path,
    output_dir: Path,
    duration: float,
    *,
    fps: float = 10.0,
    delay: float = 1.5,
    slideshow_delay: float = 1.0,
    open_timeout: float = 120.0,
    capture_timeout: float = 5.0,
    use_keys: bool = True,
    allow_reopen: bool = True,
    backend: str = "auto",
) -> list[Path]:
    """Record a single slide's playback by taking fast screenshots."""
    _maybe_prompt_for_permissions()
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_diagnostic_artifacts(output_dir)
    source_pptx = pptx_path.resolve()
    staged_pptx = _prepare_staged_presentation(source_pptx)
    _cleanup_powerpoint_state()

    captured_files = []
    try:
        _start_slideshow(
            staged_pptx,
            delay,
            slideshow_delay,
            open_timeout,
            use_keys=use_keys,
            allow_reopen=allow_reopen,
        )
        win_id = _get_slideshow_window_id(timeout=max(5.0, slideshow_delay + 5.0))
        if not win_id:
            raise RuntimeError("No slideshow window detected after slideshow start.")
        start_time = time.time()
        interval = 1.0 / fps
        frame_count = max(1, int(duration * fps)) if duration > 0 else 1

        for frame_idx in range(frame_count):
            target_elapsed = frame_idx * interval
            now = time.time()
            wait = target_elapsed - (now - start_time)
            if wait > 0:
                time.sleep(wait)
            frame_path = output_dir / f"frame_{frame_idx:04d}.png"
            if win_id:
                try:
                    _capture_window(
                        frame_path,
                        win_id,
                        backend=backend,
                        timeout=capture_timeout,
                    )
                except Exception:
                    win_id = _get_slideshow_window_id(timeout=1.5)
                    _capture_window(
                        frame_path,
                        win_id or None,
                        backend=backend,
                        timeout=capture_timeout,
                    )
            else:
                _capture_window(
                    frame_path,
                    None,
                    backend=backend,
                    timeout=capture_timeout,
                )
            captured_files.append(frame_path)
    except Exception as exc:
        _raise_with_powerpoint_diagnostics(
            reason="live_capture_failed",
            error=exc,
            debug_dir=output_dir,
            source_pptx=source_pptx,
            staged_pptx=staged_pptx,
            capture_timeout=capture_timeout,
        )
    finally:
        _teardown_powerpoint_session(staged_pptx)
        _discard_staged_presentation(staged_pptx)

    return captured_files


def main() -> int:
    from tools.ppt_research.powerpoint_capture_cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
