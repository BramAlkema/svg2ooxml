"""AppleScript/JXA helpers for PowerPoint window discovery and control."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


def osascript(script: str, *, timeout: float | None = 30.0) -> str:
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


def osascript_jxa(script: str, *, timeout: float | None = 30.0) -> str:
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


def get_png_type() -> str:
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


def get_window_id_via_jxa(
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
    if (!windows || !windows.filter) {{
        return [];
    }}
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
if (!windows || !windows.filter) {{
    windows = [];
}}
var matches = findMatches(windows, true);
if (!matches.length) {{
    matches = findMatches(windows, false);
}}
if (!matches.length) {{
    var listAll = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionAll, $.kCGNullWindowID);
    var windowsAll = ObjC.deepUnwrap(ObjC.castRefToObject(listAll));
    if (!windowsAll || !windowsAll.filter) {{
        windowsAll = [];
    }}
    matches = findMatches(windowsAll, false);
}}
if (!matches.length) {{
    "";
}} else {{
    matches.sort(function (a, b) {{ return area(b) - area(a); }});
    matches[0].kCGWindowNumber.toString();
}}
"""
    return osascript_jxa(script)


def get_front_window_id(pptx_path: Path, delay: float) -> str:
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
        win_id = osascript(script)
    except RuntimeError:
        win_id = ""
    if not win_id:
        win_id = get_window_id_via_jxa(("Microsoft PowerPoint",))
    return win_id


def get_slideshow_window_id(timeout: float = 5.0) -> str:
    end_time = time.time() + timeout
    while time.time() < end_time:
        for owner in ("Microsoft PowerPoint Slide Show", "PowerPoint Slide Show"):
            win_id = get_window_id_via_jxa((owner,), name_excludes=("presenter",))
            if win_id:
                return win_id
        win_id = get_window_id_via_jxa(
            ("Microsoft PowerPoint",),
            name_contains=("slide show", "slideshow"),
            name_excludes=("presenter",),
        )
        if win_id:
            return win_id
        time.sleep(0.2)
    return ""
