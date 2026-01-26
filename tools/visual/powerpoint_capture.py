"Capture a PowerPoint window screenshot via osascript + screencapture."

from __future__ import annotations

import argparse
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

        def stream_didOutputSampleBuffer_ofType_(self, stream, sampleBuffer, outputType):
            if outputType != SCK.SCStreamOutputTypeScreen:
                return
            if self.sample_buffer is None:
                self.sample_buffer = sampleBuffer

        def stream_didStopWithError_(self, stream, error):
            self.error = error
except Exception:
    _SCKStreamOutput = None


def _osascript(script: str, *, timeout: float | None = 30.0) -> str:
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


def _osascript_jxa(script: str, *, timeout: float | None = 30.0) -> str:
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


def _get_png_type() -> str:
    try:
        from UniformTypeIdentifiers import UTTypePNG

        return UTTypePNG.identifier()
    except Exception:
        try:
            import CoreServices

            return CoreServices.kUTTypePNG
        except Exception:
            try:
                import MobileCoreServices

                return MobileCoreServices.kUTTypePNG
            except Exception:
                return "public.png"


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
    while time.time() < deadline and output.sample_buffer is None and output.error is None:
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
                _capture_window_screen_capture_kit(int(window_id), output_path, timeout=timeout)
                return
            except Exception:
                if backend == "sckit":
                    raise
        subprocess.run(
            ["screencapture", "-x", "-T", "0", "-l", str(window_id), str(output_path)],
            check=True,
        )
        return
    if backend == "sckit":
        raise RuntimeError("No window ID for ScreenCaptureKit capture")
    subprocess.run(["screencapture", "-x", "-T", "0", str(output_path)], check=True)


def _get_window_id_via_jxa(
    owner_names: tuple[str, ...],
    *,
    name_contains: tuple[str, ...] = (),
    name_excludes: tuple[str, ...] = (),
) -> str:
    owners = ", ".join(f"\"{owner.lower()}\"" for owner in owner_names)
    name_contains_list = ", ".join(f"\"{name.lower()}\"" for name in name_contains)
    name_excludes_list = ", ".join(f"\"{name.lower()}\"" for name in name_excludes)
    script = f"""
ObjC.import("CoreGraphics");
var owners = [{owners}];
var nameContains = [{name_contains_list}];
var nameExcludes = [{name_excludes_list}];
function ownerMatches(w) {{
    var owner = (w.kCGWindowOwnerName || "").toLowerCase();
    return owners.indexOf(owner) !== -1;
}}
function nameMatches(w) {{
    if (!nameContains.length && !nameExcludes.length) {{
        return true;
    }}
    var name = (w.kCGWindowName || "").toLowerCase();
    if (nameContains.length) {{
        var ok = false;
        for (var i = 0; i < nameContains.length; i++) {{
            if (name.indexOf(nameContains[i]) !== -1) {{
                ok = true;
                break;
            }}
        }}
        if (!ok) {{
            return false;
        }}
    }}
    for (var j = 0; j < nameExcludes.length; j++) {{
        if (name.indexOf(nameExcludes[j]) !== -1) {{
            return false;
        }}
    }}
    return true;
}}
function area(w) {{
    var b = w.kCGWindowBounds || {{}};
    return (b.Width || 0) * (b.Height || 0);
}}
function findMatches(windows, requireOnscreen) {{
    return windows.filter(function (w) {{
        if (!ownerMatches(w) || !nameMatches(w)) {{
            return false;
        }}
        if (w.kCGWindowLayer !== 0) {{
            return false;
        }}
        if (requireOnscreen && !w.kCGWindowIsOnscreen) {{
            return false;
        }}
        return true;
    }});
}}
var list = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID);
var windows = ObjC.deepUnwrap(ObjC.castRefToObject(list));
var matches = findMatches(windows, true);
if (!matches.length) {{
    matches = findMatches(windows, false);
}}
if (!matches.length) {{
    var listAll = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionAll, $.kCGNullWindowID);
    var windowsAll = ObjC.deepUnwrap(ObjC.castRefToObject(listAll));
    matches = findMatches(windowsAll, false);
}}
if (!matches.length) {{
    "";
}} else {{
    matches.sort(function (a, b) {{ return area(b) - area(a); }});
    matches[0].kCGWindowNumber.toString();
}}
"""
    return _osascript_jxa(script)


def _get_front_window_id(pptx_path: Path, delay: float) -> str:
    pptx_path = pptx_path.resolve()
    script = f"""
set pptPath to POSIX file "{pptx_path}"
tell application "Microsoft PowerPoint"
    activate
    open pptPath
end tell
delay {delay}
tell application "System Events"
    tell process "Microsoft PowerPoint"
        set frontmost to true
        delay 0.2
        set winId to value of attribute "AXWindowNumber" of front window
    end tell
end tell
return winId
"""
    try:
        win_id = _osascript(script)
    except RuntimeError:
        win_id = ""
    if not win_id:
        win_id = _get_window_id_via_jxa(("Microsoft PowerPoint",))
    return win_id


def _get_slideshow_window_id(timeout: float = 5.0) -> str:
    end_time = time.time() + timeout
    while time.time() < end_time:
        for owner in ("Microsoft PowerPoint Slide Show", "PowerPoint Slide Show"):
            win_id = _get_window_id_via_jxa((owner,), name_excludes=("presenter",))
            if win_id:
                return win_id
        win_id = _get_window_id_via_jxa(
            ("Microsoft PowerPoint",),
            name_contains=("slide show", "slideshow"),
            name_excludes=("presenter",),
        )
        if win_id:
            return win_id
        time.sleep(0.2)
    return ""


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
    script = f"""
using terms from application "System Events"
on clickButtonByName(targetWindow, buttonName)
    tell application "System Events"
        try
            if exists (button buttonName of targetWindow) then
                click button buttonName of targetWindow
                return true
            end if
        end try
    end tell
    return false
end clickButtonByName

on clickDialogButtons(targetWindow)
    tell application "System Events"
        if my clickButtonByName(targetWindow, "Repair") then
            return true
        end if
        if my clickButtonByName(targetWindow, "Open") then
            return true
        end if
        if my clickButtonByName(targetWindow, "OK") then
            return true
        end if
        if my clickButtonByName(targetWindow, "Yes") then
            return true
        end if
        if exists (button 1 of targetWindow) then
            click button 1 of targetWindow
            return true
        end if
    end tell
    return false
end clickDialogButtons

on openPresentation(pptPosix)
    tell application "Microsoft PowerPoint"
        open (POSIX file pptPosix)
    end tell
end openPresentation

on dismissDialogs(aggressive, maxSeconds)
    tell application "System Events"
        if not (exists process "Microsoft PowerPoint") then
            return false
        end if
        tell process "Microsoft PowerPoint"
            if aggressive then
                try
                    set frontmost to true
                end try
            end if
            set t0 to (current date)
            set lastReturn to (current date) - 10
            repeat while ((current date) - t0) < maxSeconds
                set clickedAny to false
                try
                    set repairButtons to (buttons whose name is "Repair")
                    if (count of repairButtons) > 0 then
                        click item 1 of repairButtons
                        set clickedAny to true
                    end if
                end try
                try
                    set okButtons to (buttons whose name is "OK")
                    if (count of okButtons) > 0 then
                        click item 1 of okButtons
                        set clickedAny to true
                    end if
                end try
                if exists (front window) then
                    if my clickDialogButtons(front window) then
                        set clickedAny to true
                    else
                        try
                            if aggressive and useKeys and subrole of front window is "AXDialog" then
                                if ((current date) - lastReturn) > 0.5 then
                                    key code 36
                                    set lastReturn to (current date)
                                    set clickedAny to true
                                end if
                            end if
                        end try
                    end if
                end if
                repeat with w in (windows whose subrole is "AXDialog")
                    if my clickDialogButtons(w) then
                        set clickedAny to true
                    end if
                end repeat
                repeat with w in windows
                    if my clickDialogButtons(w) then
                        set clickedAny to true
                    end if
                    try
                        repeat with s in sheets of w
                            if my clickDialogButtons(s) then
                                set clickedAny to true
                            end if
                        end repeat
                    end try
                end repeat
                if clickedAny is false then exit repeat
                delay 0.2
            end repeat
        end tell
    end tell
    return true
end dismissDialogs

on isPowerPointRunning()
    tell application "System Events"
        return exists process "Microsoft PowerPoint"
    end tell
end isPowerPointRunning

on waitForPresentation(maxSeconds, pptPosix, allowReopen)
    set t0 to (current date)
    set didReopen to false
    set lastOpen to (current date)
    repeat while ((current date) - t0) < maxSeconds
        set presCount to 0
        try
            tell application "Microsoft PowerPoint"
                set presCount to count of presentations
            end tell
        end try
        if presCount > 0 then
            return true
        end if
        my dismissDialogs(true, 2)
        if allowReopen and (didReopen is false) then
            try
                if my isPowerPointRunning() is false then
                    do shell script "open -a " & quoted form of "Microsoft PowerPoint"
                    delay 0.5
                    my openPresentation(pptPosix)
                    set didReopen to true
                    set lastOpen to (current date)
                end if
            end try
        end if
        if allowReopen and ((current date) - lastOpen) > 5 then
            try
                my openPresentation(pptPosix)
                set lastOpen to (current date)
            end try
        end if
        delay 0.5
    end repeat
    return false
end waitForPresentation

on waitForSlides(maxSeconds)
    set t0 to (current date)
    repeat while ((current date) - t0) < maxSeconds
        set slideCount to 0
        try
            tell application "Microsoft PowerPoint"
                set slideCount to count slides of active presentation
            end tell
        end try
        if slideCount > 0 then
            return true
        end if
        my dismissDialogs(true, 2)
        delay 0.5
    end repeat
    return false
end waitForSlides
end using terms from

set pptPath to POSIX file "{pptx_path}"
set pptPosix to POSIX path of pptPath
set useKeys to {str(use_keys).lower()}
set allowReopen to {str(allow_reopen).lower()}
tell application "Microsoft PowerPoint"
    activate
end tell
delay 0.2
my openPresentation(pptPosix)
delay 0.1
delay {delay}
my dismissDialogs(true, 10)
if my waitForPresentation({open_timeout}, pptPosix, allowReopen) is false then
    error "No active presentation after repair."
end if
if my waitForSlides({open_timeout}) is false then
    error "No active slides after repair."
end if
tell application "Microsoft PowerPoint"
    if (count of presentations) is 0 then
        error "Presentation closed before slideshow."
    end if
    activate
end tell
delay 0.2
tell application "System Events"
    tell process "Microsoft PowerPoint"
        set frontmost to true
    end tell
    keystroke return using {{command down, shift down}}
end tell
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
    pptx_path = pptx_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    open_failed_path = output_dir / "open_failed.png"
    if open_failed_path.exists():
        open_failed_path.unlink()

    _start_slideshow(
        pptx_path,
        delay,
        slideshow_delay,
        open_timeout,
        use_keys=use_keys,
        allow_reopen=allow_reopen,
    )
    try:
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
    finally:
        if exit_after:
            _exit_slideshow()
            _close_active_presentation()


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
    win_id = _get_front_window_id(pptx_path, delay)
    if not win_id:
        raise RuntimeError("No PowerPoint window ID returned.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _capture_window(
        output_path,
        win_id,
        backend=backend,
        timeout=capture_timeout,
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
    _start_slideshow(
        pptx_path,
        delay,
        slideshow_delay,
        open_timeout,
        use_keys=use_keys,
        allow_reopen=allow_reopen,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        slideshow_window_id = _get_slideshow_window_id(
            timeout=max(5.0, slideshow_delay + 5.0)
        )
        _capture_window(
            output_path,
            slideshow_window_id or None,
            backend=backend,
            timeout=capture_timeout,
        )
    finally:
        if exit_after:
            _exit_slideshow()


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
    pptx_path = pptx_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    _start_slideshow(
        pptx_path,
        delay,
        slideshow_delay,
        open_timeout,
        use_keys=use_keys,
        allow_reopen=allow_reopen,
    )
    
    captured_files = []
    try:
        win_id = _get_slideshow_window_id(timeout=slideshow_delay + 2.0)
        start_time = time.time()
        frame_idx = 0
        interval = 1.0 / fps
        
        while (time.time() - start_time) < duration:
            frame_path = output_dir / f"frame_{frame_idx:04d}.png"
            _capture_window(
                frame_path,
                win_id or None,
                backend=backend,
                timeout=capture_timeout,
            )
            captured_files.append(frame_path)
            frame_idx += 1
            
            # Simple pacing
            elapsed = time.time() - start_time
            next_shot = (frame_idx * interval)
            wait = next_shot - elapsed
            if wait > 0:
                time.sleep(wait)
                
    finally:
        _exit_slideshow()
        _close_active_presentation()
        
    return captured_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture PowerPoint window screenshot.")
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
    parser.add_argument("--duration", type=float, default=5.0, help="Duration for live recording.")
    parser.add_argument("--fps", type=float, default=10.0, help="FPS for live recording.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay after opening (seconds).")
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