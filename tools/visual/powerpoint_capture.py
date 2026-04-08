"Capture a PowerPoint window screenshot via osascript + screencapture."

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    import objc
    from Foundation import NSObject
    import ScreenCaptureKit as SCK

    class _SCKStreamOutput(NSObject):
        def init(self):
            self = objc.super(_SCKStreamOutput, self).init()
            if self is None:
                return None
            self.sample_buffer = None
            self.error = None
            return self

        def stream_didOutputSampleBuffer_ofType_(
            self, stream, sampleBuffer, outputType
        ):
            if outputType != SCK.SCStreamOutputTypeScreen:
                return
            if self.sample_buffer is None:
                self.sample_buffer = sampleBuffer

        def stream_didStopWithError_(self, stream, error):
            self.error = error

except Exception:
    _SCKStreamOutput = None


from tools.visual.pptx_window import (  # noqa: E402
    get_front_window_id as _get_front_window_id,
    get_png_type as _get_png_type,
    get_slideshow_window_id as _get_slideshow_window_id,
    get_window_id_via_jxa as _get_window_id_via_jxa,
    open_presentation_via_ui as _open_presentation_via_ui,
    osascript as _osascript,
    osascript_jxa as _osascript_jxa,
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
    staged = stage_dir / "presentation.pptx"
    shutil.copy2(source, staged)
    return staged


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


def _capture_window_screen_capture_kit(
    window_id: int,
    output_path: Path,
    *,
    timeout: float,
) -> None:
    try:
        from Foundation import NSDate, NSRunLoop, NSURL
        from AppKit import NSApplication
        import CoreMedia
        import Quartz
        import ScreenCaptureKit as SCK
    except Exception as exc:
        raise RuntimeError("ScreenCaptureKit unavailable") from exc
    if _SCKStreamOutput is None:
        raise RuntimeError("ScreenCaptureKit unavailable")
    try:
        import CoreVideo
    except Exception:
        CoreVideo = None

    run_loop = NSRunLoop.currentRunLoop()
    NSApplication.sharedApplication()
    try:
        Quartz.CGMainDisplayID()
    except Exception:
        pass
    content = None
    content_error = None
    content_done = False

    def content_handler(new_content, error):
        nonlocal content, content_error, content_done
        content = new_content
        content_error = error
        content_done = True

    SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
        True,
        False,
        content_handler,
    )

    deadline = time.time() + timeout
    while time.time() < deadline and not content_done:
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    if not content_done:
        raise RuntimeError("Timed out waiting for shareable content")
    if content_error is not None:
        raise RuntimeError(f"ScreenCaptureKit content error: {content_error}")

    def _value(obj, name):
        value = getattr(obj, name)
        return value() if callable(value) else value

    target_window = None
    for window in _value(content, "windows"):
        try:
            if int(_value(window, "windowID")) == window_id:
                target_window = window
                break
        except Exception:
            continue
    if target_window is None:
        raise RuntimeError(f"Window {window_id} not found in ScreenCaptureKit")

    filter_obj = None
    try:
        filter_obj = SCK.SCContentFilter.alloc().initWithDesktopIndependentWindow_(
            target_window
        )
    except Exception as exc:
        raise RuntimeError("ScreenCaptureKit window capture not supported") from exc

    def _set_config_attr(config_obj, name, value):
        try:
            setattr(config_obj, name, value)
            return
        except Exception:
            setter_name = f"set{name[0].upper()}{name[1:]}_"
            setter = getattr(config_obj, setter_name, None)
            if setter is None:
                raise
            setter(value)

    config = SCK.SCStreamConfiguration.alloc().init()
    frame = _value(target_window, "frame")
    scale = 1.0
    try:
        scale = float(_value(target_window, "scaleFactor"))
    except Exception:
        pass
    _set_config_attr(config, "width", max(1, int(frame.size.width * scale)))
    _set_config_attr(config, "height", max(1, int(frame.size.height * scale)))
    _set_config_attr(config, "capturesAudio", False)
    _set_config_attr(config, "showsCursor", False)
    _set_config_attr(config, "queueDepth", 1)
    pixel_format = 1111970369  # kCVPixelFormatType_32BGRA
    if CoreVideo is not None:
        try:
            pixel_format = CoreVideo.kCVPixelFormatType_32BGRA
        except Exception:
            pass
    _set_config_attr(config, "pixelFormat", pixel_format)

    output = _SCKStreamOutput.alloc().init()
    stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
        filter_obj,
        config,
        None,
    )
    try:
        stream.addStreamOutput_type_sampleHandlerQueue_(
            output,
            SCK.SCStreamOutputTypeScreen,
            None,
        )
    except Exception:
        stream.addStreamOutput_type_sampleHandlerQueue_error_(
            output,
            SCK.SCStreamOutputTypeScreen,
            None,
            None,
        )

    start_error = None

    def start_handler(error):
        nonlocal start_error
        start_error = error

    stream.startCaptureWithCompletionHandler_(start_handler)

    deadline = time.time() + timeout
    while (
        time.time() < deadline and output.sample_buffer is None and output.error is None
    ):
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

    stream.stopCaptureWithCompletionHandler_(lambda error: None)

    if start_error is not None:
        raise RuntimeError(f"ScreenCaptureKit start error: {start_error}")
    if output.error is not None:
        raise RuntimeError(f"ScreenCaptureKit stream error: {output.error}")
    if output.sample_buffer is None:
        raise RuntimeError("ScreenCaptureKit timed out waiting for frame")

    image_buffer = CoreMedia.CMSampleBufferGetImageBuffer(output.sample_buffer)
    ci_image = Quartz.CIImage.imageWithCVImageBuffer_(image_buffer)
    context = Quartz.CIContext.contextWithOptions_(None)
    cg_image = context.createCGImage_fromRect_(ci_image, ci_image.extent())
    if cg_image is None:
        raise RuntimeError("ScreenCaptureKit failed to create image")

    output_url = NSURL.fileURLWithPath_(str(output_path))
    png_type = _get_png_type()
    destination = Quartz.CGImageDestinationCreateWithURL(output_url, png_type, 1, None)
    if destination is None:
        raise RuntimeError("ScreenCaptureKit failed to create image destination")
    Quartz.CGImageDestinationAddImage(destination, cg_image, None)
    if not Quartz.CGImageDestinationFinalize(destination):
        raise RuntimeError("ScreenCaptureKit failed to write image")


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


def _wait_for_powerpoint_presentation(pptx_path: Path, timeout: float) -> bool:
    lockfile_path = _powerpoint_lockfile_path(pptx_path)
    deadline = time.time() + max(0.5, timeout)
    while time.time() < deadline:
        if lockfile_path.exists():
            return True
        time.sleep(0.2)
    return lockfile_path.exists()


def _advance_slide() -> None:
    script = """
tell application "System Events"
    key code 49
    delay 0.02
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


def _teardown_powerpoint_session() -> None:
    try:
        _exit_slideshow()
    except RuntimeError:
        pass
    try:
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
        repeat with pres in presentations
            close pres saving no
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
        if attempt_index < (open_attempts - 1):
            time.sleep(0.5)
    if not did_open:
        raise RuntimeError("No PowerPoint presentation lock after UI open.")
    if not _wait_for_powerpoint_window(min(open_timeout, 10.0)):
        raise RuntimeError("No PowerPoint edit window after UI open.")
    script = f"""
on sendSlideshowKeys()
    delay 0.2
    try
        tell application "System Events"
            keystroke return using {{command down, shift down}}
        end tell
    on error
        return false
    end try
    return true
end sendSlideshowKeys

on requestSlideshowStart(useKeys)
    set maxAttempts to 1
    if useKeys then set maxAttempts to 2
    repeat maxAttempts times
        if my sendSlideshowKeys() then
            return true
        end if
        delay 0.5
    end repeat
    return false
end requestSlideshowStart

set useKeys to {str(use_keys).lower()}
delay {delay}
if my requestSlideshowStart(useKeys) is false then
    error "Unable to request slideshow start."
end if
delay {slideshow_delay}
"""
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
            _teardown_powerpoint_session()


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
            _teardown_powerpoint_session()


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
        frame_idx = 0
        interval = 1.0 / fps

        while (time.time() - start_time) < duration:
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
            frame_idx += 1

            # Simple pacing
            elapsed = time.time() - start_time
            next_shot = frame_idx * interval
            wait = next_shot - elapsed
            if wait > 0:
                time.sleep(wait)
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
        _teardown_powerpoint_session()

    return captured_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture PowerPoint window screenshot."
    )
    parser.add_argument("pptx", type=Path, help="Path to the PPTX file to open.")
    parser.add_argument(
        "output",
        type=Path,
        help="Output PNG path (window/slideshow) or output directory (slideshow-all/live).",
    )
    parser.add_argument(
        "--mode",
        choices=("window", "slideshow", "slideshow-all", "live"),
        default="window",
        help="Capture mode: live records a single slide's animation.",
    )
    parser.add_argument(
        "--duration", type=float, default=5.0, help="Duration for live recording."
    )
    parser.add_argument(
        "--fps", type=float, default=10.0, help="FPS for live recording."
    )
    parser.add_argument(
        "--delay", type=float, default=1.5, help="Delay after opening (seconds)."
    )
    parser.add_argument(
        "--slideshow-delay",
        type=float,
        default=1.0,
        help="Delay after slideshow starts (seconds).",
    )
    parser.add_argument(
        "--slide-delay",
        type=float,
        default=0.15,
        help="Delay between slides (seconds) for slideshow-all.",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "screencapture", "sckit"),
        default="auto",
        help="Capture backend: auto uses ScreenCaptureKit when available.",
    )
    parser.add_argument(
        "--capture-timeout",
        type=float,
        default=5.0,
        help="Max seconds to wait for ScreenCaptureKit frame capture.",
    )
    parser.add_argument(
        "--open-timeout",
        type=float,
        default=120.0,
        help="Max seconds to wait for PowerPoint to open/repair the file.",
    )
    parser.add_argument(
        "--no-reopen",
        action="store_true",
        help="Disable periodic reopen attempts while waiting for slides.",
    )
    parser.add_argument(
        "--no-keys",
        action="store_true",
        help="Disable keystroke fallbacks; only click visible buttons.",
    )
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Leave the slideshow running after capture.",
    )
    args = parser.parse_args()

    try:
        if args.mode == "live":
            capture_live_animation(
                args.pptx,
                args.output,
                args.duration,
                fps=args.fps,
                delay=args.delay,
                slideshow_delay=args.slideshow_delay,
                open_timeout=args.open_timeout,
                capture_timeout=args.capture_timeout,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        elif args.mode == "slideshow":
            capture_pptx_slideshow(
                args.pptx,
                args.output,
                args.delay,
                args.slideshow_delay,
                args.open_timeout,
                args.capture_timeout,
                exit_after=not args.keep_open,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        elif args.mode == "slideshow-all":
            capture_pptx_slideshow_all(
                args.pptx,
                args.output,
                args.delay,
                args.slideshow_delay,
                args.slide_delay,
                args.open_timeout,
                args.capture_timeout,
                exit_after=not args.keep_open,
                use_keys=not args.no_keys,
                allow_reopen=not args.no_reopen,
                backend=args.backend,
            )
        else:
            capture_pptx_window(
                args.pptx,
                args.output,
                args.delay,
                backend=args.backend,
                capture_timeout=args.capture_timeout,
            )
    except Exception as exc:
        print(f"PowerPoint capture failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
