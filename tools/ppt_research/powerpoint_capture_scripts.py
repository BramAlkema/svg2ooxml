"""AppleScript builders for PowerPoint visual capture."""

from __future__ import annotations

import json
from pathlib import Path


def _applescript_string(value: str) -> str:
    return json.dumps(value)


def _matching_presentation_script(pptx_path: Path) -> str:
    target_posix = _applescript_string(str(pptx_path.resolve()))
    target_name = _applescript_string(pptx_path.name)
    return f"""
set targetPosix to {target_posix}
set targetName to {target_name}
set targetHfs to ""
try
    set targetHfs to ((POSIX file targetPosix) as text)
end try

on presentationMatches(presRef, targetPosix, targetHfs, targetName)
    -- Callers MUST use index-based iteration (repeat with i from 1 to count).
    -- "repeat with presRef in presentations" + this nested tell causes infinite loops.
    tell application "Microsoft PowerPoint"
    try
        set presFullName to (full name of presRef) as text
        if presFullName is targetPosix then
            return true
        end if
        if targetHfs is not "" and presFullName is targetHfs then
            return true
        end if
    end try
    try
        set presPath to (path of presRef) as text
        set presName to (name of presRef) as text
        set combinedPath to presPath & presName
        if combinedPath is targetPosix then
            return true
        end if
        if targetHfs is not "" and combinedPath is targetHfs then
            return true
        end if
    end try
    try
        if ((name of presRef) as text) is targetName then
            return true
        end if
    end try
    end tell
    return false
end presentationMatches
"""




def build_start_slideshow_script(
    pptx_path: Path,
    *,
    delay: float,
    slideshow_delay: float,
    use_keys: bool,
) -> str:
    selector_script = _matching_presentation_script(pptx_path)
    script = selector_script + f"""
on slideShowWindowCount()
    tell application "Microsoft PowerPoint"
        try
            return count of slide show windows
        on error
            return 0
        end try
    end tell
end slideShowWindowCount

on findTargetPresentation(targetPosix, targetHfs, targetName)
    tell application "Microsoft PowerPoint"
        set presCount to count of presentations
        repeat with i from 1 to presCount
            set presRef to presentation i
            if my presentationMatches(presRef, targetPosix, targetHfs, targetName) then
                return presRef
            end if
        end repeat
    end tell
    return missing value
end findTargetPresentation

on focusTargetPresentationWindow(targetPosix, targetHfs, targetName)
    set foundTarget to false
    tell application "Microsoft PowerPoint"
        activate
        set presRef to my findTargetPresentation(targetPosix, targetHfs, targetName)
        if presRef is missing value then
            return false
        end if
        set foundTarget to true
        try
            if (count of document windows of presRef) > 0 then
                set targetWindow to document window 1 of presRef
                try
                    set index of targetWindow to 1
                end try
            end if
        end try
    end tell
    if not foundTarget then
        return false
    end if
    try
        tell application "System Events"
            tell process "Microsoft PowerPoint"
                set frontmost to true
                repeat with uiWindow in windows
                    try
                        if (name of uiWindow) contains targetName then
                            try
                                perform action "AXRaise" of uiWindow
                            end try
                            try
                                click uiWindow
                            end try
                            try
                                set value of attribute "AXMain" of uiWindow to true
                            end try
                            try
                                set value of attribute "AXFocused" of uiWindow to true
                            end try
                            exit repeat
                        end if
                    end try
                end repeat
            end tell
        end tell
    end try
    return true
end focusTargetPresentationWindow

on tryObjectModelStart(targetPosix, targetHfs, targetName)
    if not my focusTargetPresentationWindow(targetPosix, targetHfs, targetName) then
        return false
    end if
    tell application "Microsoft PowerPoint"
        if (count of presentations) is 0 then
            return false
        end if
        try
            set pres to my findTargetPresentation(targetPosix, targetHfs, targetName)
            if pres is missing value then
                return false
            end if
            set ss to slide show settings of pres
            try
                set show type of ss to slide show type window
            end try
            try
                set show with presenter of ss to false
            end try
            try
                set loop until stopped of ss to true
            end try
            run slide show ss
            return true
        on error
            return false
        end try
    end tell
end tryObjectModelStart

on sendSlideshowKeys()
    delay 0.2
    try
        tell application "System Events"
            tell process "Microsoft PowerPoint"
                set frontmost to true
            end tell
            keystroke return using {{command down, shift down}}
        end tell
    on error
        return false
    end try
    return true
end sendSlideshowKeys

on tryDirectOpen(targetPosix)
    tell application "Microsoft PowerPoint"
        try
            open (POSIX file targetPosix)
            delay 1.0
        end try
    end tell
end tryDirectOpen

on tryMenuStart()
    try
        tell application "System Events"
            tell process "Microsoft PowerPoint"
                set frontmost to true
                try
                    click menu item "Play from Start" of menu 1 of menu bar item "Slide Show" of menu bar 1
                    return true
                end try
                try
                    click menu item "Play From Start" of menu 1 of menu bar item "Slide Show" of menu bar 1
                    return true
                end try
                try
                    click menu item "From Beginning" of menu 1 of menu bar item "Slide Show" of menu bar 1
                    return true
                end try
            end tell
        end tell
    on error
        return false
    end try
    return false
end tryMenuStart

set useKeys to {str(use_keys).lower()}
delay {delay}
repeat with attemptIndex from 1 to 8
    if my findTargetPresentation(targetPosix, targetHfs, targetName) is missing value then
        my tryDirectOpen(targetPosix)
    end if
    if my tryObjectModelStart(targetPosix, targetHfs, targetName) then
        delay {slideshow_delay}
        if my slideShowWindowCount() > 0 then
            return "object-model"
        end if
    end if

    if my tryMenuStart() then
        delay {slideshow_delay}
        if my slideShowWindowCount() > 0 then
            return "menu"
        end if
    end if

    if useKeys then
        if my sendSlideshowKeys() then
            delay {slideshow_delay}
            if my slideShowWindowCount() > 0 then
                return "keystroke"
            end if
        end if
    end if
    delay 0.35
end repeat

error "Unable to request slideshow start."
"""
    return script
