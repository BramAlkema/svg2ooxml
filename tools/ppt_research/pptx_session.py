"""Persistent PowerPoint session controller for animation tuning loops.

Keeps PowerPoint.app running across iterations so only the presentation itself
is closed and reopened when the underlying PPTX file changes. Dramatically
faster than relaunching PowerPoint for every capture.

macOS only — requires AppleScript (osascript) and a licensed install of
Microsoft PowerPoint. Frame capture uses the same ScreenCaptureKit backend as
``tools/ppt_research/powerpoint_capture.py``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from tools.ppt_research.powerpoint_capture import (
    _advance_slide,
    _capture_window,
    _close_matching_presentation,
    _exit_slideshow,
    _maybe_prompt_for_permissions,
    _start_slideshow,
    _wait_for_powerpoint_presentation,
)
from tools.ppt_research.pptx_window import (
    get_slideshow_window_id,
    open_presentation_via_ui,
)

logger = logging.getLogger(__name__)


class PptxSessionError(RuntimeError):
    """Raised when a PowerPoint session operation fails."""


class PptxSession:
    """Hold a PowerPoint presentation open across multiple capture rounds.

    Lifecycle::

        session = PptxSession(pptx_path)
        session.open()
        frames = session.capture_animation(output_dir, duration=1.5, fps=10)
        # ...edit the pptx file on disk...
        session.reload()
        frames = session.capture_animation(output_dir2, duration=1.5, fps=10)
        session.quit()

    Context manager usage is also supported::

        with PptxSession(pptx_path) as session:
            session.capture_animation(...)
    """

    def __init__(
        self,
        pptx_path: Path | str,
        *,
        open_timeout: float = 60.0,
        slideshow_delay: float = 1.0,
        capture_timeout: float = 5.0,
        backend: str = "auto",
        use_keys: bool = True,
    ) -> None:
        self._pptx_path = Path(pptx_path).resolve()
        self._open_timeout = open_timeout
        self._slideshow_delay = slideshow_delay
        self._capture_timeout = capture_timeout
        self._backend = backend
        self._use_keys = use_keys
        self._opened = False

    # ------------------------------------------------------------------ props

    @property
    def pptx_path(self) -> Path:
        return self._pptx_path

    @property
    def is_open(self) -> bool:
        return self._opened

    # ---------------------------------------------------------------- opening

    def open(self) -> None:
        """Launch PowerPoint (if not already running) and open the presentation."""
        if self._opened:
            return
        if not self._pptx_path.exists():
            raise PptxSessionError(f"PPTX not found: {self._pptx_path}")

        _maybe_prompt_for_permissions()
        open_presentation_via_ui(
            self._pptx_path,
            timeout=max(15.0, min(self._open_timeout, 30.0)),
        )
        if not _wait_for_powerpoint_presentation(
            self._pptx_path,
            timeout=self._open_timeout,
        ):
            raise PptxSessionError(
                f"PowerPoint did not register presentation: {self._pptx_path}"
            )
        self._opened = True
        logger.info("PowerPoint session opened for %s", self._pptx_path)

    # ---------------------------------------------------------------- capture

    def capture_animation(
        self,
        output_dir: Path | str,
        *,
        duration: float,
        fps: float = 10.0,
        trigger_advance: bool = True,
        pre_advances: int = 0,
        pre_advance_pause: float = 0.6,
    ) -> list[Path]:
        """Play the first slide and capture frames at the requested rate.

        Captures frame 0 as a pre-animation baseline, then sends an advance
        keystroke to trigger the slide's click-group animation, then captures
        the remaining frames during playback.

        Slideshow mode is entered and then exited on each call. The underlying
        PowerPoint application and presentation stay open across calls.
        """
        if not self._opened:
            raise PptxSessionError("Session is not open; call .open() first.")

        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        self._start_slideshow()
        try:
            win_id = get_slideshow_window_id(
                timeout=max(5.0, self._slideshow_delay + 5.0)
            )
            if not win_id:
                raise PptxSessionError(
                    "No slideshow window detected after slideshow start."
                )
            return self._capture_frames(
                window_id=win_id,
                output_dir=output_dir,
                duration=duration,
                fps=fps,
                trigger_advance=trigger_advance,
                pre_advances=pre_advances,
                pre_advance_pause=pre_advance_pause,
            )
        finally:
            try:
                _exit_slideshow()
            except Exception as exc:  # pragma: no cover - best-effort teardown
                logger.warning("Failed to exit slideshow cleanly: %s", exc)

    def _start_slideshow(self) -> None:
        _start_slideshow(
            self._pptx_path,
            0.2,  # small pre-delay; app already running
            self._slideshow_delay,
            self._open_timeout,
            use_keys=self._use_keys,
            allow_reopen=False,
        )

    def _capture_frames(
        self,
        *,
        window_id: str,
        output_dir: Path,
        duration: float,
        fps: float,
        trigger_advance: bool,
        pre_advances: int,
        pre_advance_pause: float,
    ) -> list[Path]:
        interval = 1.0 / fps if fps > 0 else 0.1
        frame_count = max(1, int(duration * fps)) if duration > 0 else 1
        captured: list[Path] = []
        current_window = window_id

        def _capture(frame_idx: int) -> None:
            nonlocal current_window
            frame_path = output_dir / f"frame_{frame_idx:04d}.png"
            try:
                _capture_window(
                    frame_path,
                    current_window,
                    backend=self._backend,
                    timeout=self._capture_timeout,
                )
            except Exception:
                current_window = (
                    get_slideshow_window_id(timeout=1.5) or current_window
                )
                _capture_window(
                    frame_path,
                    current_window or None,
                    backend=self._backend,
                    timeout=self._capture_timeout,
                )
            captured.append(frame_path)

        frame_idx = 0
        # Frame 0 — initial slideshow baseline.
        _capture(frame_idx)
        frame_idx += 1

        # Pre-animation advances (e.g. navigate from blank slide 1 to the
        # animated slide so PowerPoint's build engine pre-hides entrance
        # shapes). Capture a frame after each advance so the transition is
        # visible in the strip.
        for _ in range(pre_advances):
            if frame_idx >= frame_count:
                break
            try:
                _advance_slide()
            except Exception as exc:  # pragma: no cover - best-effort
                logger.warning("Pre-animation advance failed: %s", exc)
            time.sleep(pre_advance_pause)
            _capture(frame_idx)
            frame_idx += 1

        # Main animation trigger.
        if trigger_advance and frame_idx < frame_count:
            try:
                _advance_slide()
            except Exception as exc:  # pragma: no cover - best-effort
                logger.warning("Animation advance failed: %s", exc)

        trigger_time = time.time()
        anim_frame_offset = frame_idx
        while frame_idx < frame_count:
            target_elapsed = (frame_idx - anim_frame_offset) * interval
            wait = target_elapsed - (time.time() - trigger_time)
            if wait > 0:
                time.sleep(wait)
            _capture(frame_idx)
            frame_idx += 1
        return captured

    # ----------------------------------------------------------------- reload

    def reload(self, new_pptx_path: Path | str | None = None) -> None:
        """Close the current presentation and reopen it from disk.

        Call after rewriting the PPTX file. PowerPoint caches the opened
        document, so a close/reopen is required for edits to take effect.
        Keeps PowerPoint.app running.
        """
        if new_pptx_path is not None:
            new_path = Path(new_pptx_path).resolve()
            if not new_path.exists():
                raise PptxSessionError(f"PPTX not found: {new_path}")
        else:
            new_path = self._pptx_path

        if self._opened:
            try:
                _exit_slideshow()
            except Exception:
                pass
            try:
                _close_matching_presentation(self._pptx_path)
            except Exception as exc:
                logger.warning("Failed to close presentation during reload: %s", exc)

        self._pptx_path = new_path
        self._opened = False
        self.open()

    # ------------------------------------------------------------------- quit

    def quit(self) -> None:
        """Close the presentation. Leaves PowerPoint.app running."""
        if not self._opened:
            return
        try:
            _exit_slideshow()
        except Exception:
            pass
        try:
            _close_matching_presentation(self._pptx_path)
        except Exception as exc:
            logger.warning("Failed to close presentation on quit: %s", exc)
        self._opened = False

    # --------------------------------------------------------------- context

    def __enter__(self) -> PptxSession:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.quit()


__all__ = ["PptxSession", "PptxSessionError"]
