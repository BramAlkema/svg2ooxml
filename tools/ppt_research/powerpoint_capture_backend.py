"""ScreenCaptureKit backend for PowerPoint visual capture."""

from __future__ import annotations

import time
from pathlib import Path

from tools.ppt_research.pptx_window import get_png_type as _get_png_type

try:
    import objc
    import ScreenCaptureKit as SCK  # noqa: N817
    from Foundation import NSObject

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




def _capture_window_screen_capture_kit(
    window_id: int,
    output_path: Path,
    *,
    timeout: float,
) -> None:
    try:
        import CoreMedia
        import Quartz
        import ScreenCaptureKit as SCK  # noqa: N817
        from AppKit import NSApplication
        from Foundation import NSURL, NSDate, NSRunLoop
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
