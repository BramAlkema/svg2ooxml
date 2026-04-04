"""Utilities for rendering PPTX slides to bitmap images for visual tests."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from lxml import etree as ET
from PIL import Image

logger = logging.getLogger(__name__)


class VisualRendererError(RuntimeError):
    """Raised when the external rendering tool fails."""


@dataclass
class RenderedSlideSet:
    """Container describing the output from a rendering pass."""

    images: Sequence[Path]
    renderer: str


def _normalize_user_installation(user_installation: str | None) -> str | None:
    if not user_installation:
        return None
    if user_installation.startswith("file:"):
        return user_installation
    return Path(user_installation).resolve().as_uri()


def _kill_running_soffice() -> None:
    """Kill any running LibreOffice/soffice processes so headless mode can start cleanly."""
    try:
        result = subprocess.run(
            ["pkill", "-f", "soffice"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            import time
            time.sleep(0.5)
            logger.debug("Killed existing soffice process(es) before headless render.")
    except FileNotFoundError:
        pass


class LibreOfficeRenderer:
    """Render PPTX files to PNG using LibreOffice (soffice) headless mode."""

    def __init__(
        self,
        soffice_path: str | None = None,
        *,
        timeout: float | None = 90.0,
        user_installation: str | None = None,
        png_dpi: float | None = 96.0,
    ) -> None:
        self._timeout = timeout
        self._command_path = soffice_path or shutil.which("soffice")
        self._user_installation = _normalize_user_installation(user_installation)
        if png_dpi is not None and png_dpi <= 0:
            raise ValueError("png_dpi must be > 0 or None to disable normalization.")
        self._png_dpi = png_dpi

    # ------------------------------------------------------------------
    # Capability helpers
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return True if a working soffice binary has been located."""

        return self._command_path is not None

    @property
    def command_path(self) -> str | None:
        return self._command_path

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def base_args(self) -> list[str]:
        args = [
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            "--nolockcheck",
        ]
        if self._user_installation:
            args.append(f"-env:UserInstallation={self._user_installation}")
        return args

    def render(self, pptx_path: Path | str, output_dir: Path | str) -> RenderedSlideSet:
        """Render *pptx_path* into PNG images under *output_dir*."""

        if not self.available:
            raise VisualRendererError("LibreOffice (soffice) is not installed or not on PATH.")

        _kill_running_soffice()

        pptx_path = Path(pptx_path)
        if not pptx_path.exists():
            raise VisualRendererError(f"PPTX path does not exist: {pptx_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create a unique temporary directory for this render pass to avoid locking issues
        import tempfile
        user_install_dir = Path(tempfile.mkdtemp(prefix="soffice_user_"))
        user_install_uri = user_install_dir.resolve().as_uri()

        soffice_args = [
            *self.base_args(),
            f"-env:UserInstallation={user_install_uri}",
            "--convert-to",
            "png:impress_png_Export",
            "--outdir",
            str(output_dir),
            str(pptx_path),
        ]

        def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            logger.debug("Running soffice renderer: %s", " ".join(cmd))
            try:
                return subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=self._timeout,
                    text=True,
                )
            except FileNotFoundError as exc:  # pragma: no cover - defensive
                raise VisualRendererError("LibreOffice soffice command not found.") from exc
            except subprocess.TimeoutExpired as exc:
                raise VisualRendererError(f"LibreOffice timed out after {self._timeout} seconds.") from exc

        cmd = [self._command_path or "soffice", *soffice_args]  # guarded above
        try:
            completed = _run(cmd)
            tried_open = False
            if completed.returncode != 0 and platform.system() == "Darwin":
                open_cmd = self._macos_open_command(soffice_args)
                if open_cmd:
                    tried_open = True
                    completed = _run(open_cmd)

            if completed.returncode != 0:
                message_lines = [
                    "LibreOffice failed to render PPTX.",
                    f"exit code: {completed.returncode}",
                ]
                if tried_open:
                    message_lines.append("LibreOffice failed when launched via open(1) as well.")
                if completed.stdout:
                    message_lines.append(f"stdout:\n{completed.stdout}")
                if completed.stderr:
                    message_lines.append(f"stderr:\n{completed.stderr}")
                if completed.returncode == 134 and platform.system() == "Darwin":
                    mac_version = platform.mac_ver()[0]
                    if mac_version.startswith("26."):
                        message_lines.append(
                            "hint: LibreOffice headless appears to crash on macOS 26.x here. "
                            "Try a different LibreOffice build or run visual tests on macOS 25.x."
                        )
                raise VisualRendererError("\n".join(message_lines))
        finally:
            # Clean up the temporary user installation directory
            try:
                shutil.rmtree(user_install_dir)
            except Exception:
                pass

        generated = sorted(output_dir.glob("*.png"))
        if not generated:
            raise VisualRendererError(
                f"LibreOffice completed but produced no PNG files in {output_dir}."
            )

        if self._png_dpi is not None:
            _normalize_pngs(pptx_path, generated, self._png_dpi)

        logger.debug("Generated %d slide image(s).", len(generated))
        return RenderedSlideSet(images=tuple(generated), renderer="soffice")

    def _macos_open_command(self, args: Sequence[str]) -> list[str] | None:
        open_path = shutil.which("open")
        app_path = self._macos_app_path()
        if not open_path or not app_path:
            return None

        # Always use -a with the .app path.  The bundle-id route
        # (`open -b org.libreoffice.script`) fails on many macOS installs
        # with "LSCopyApplicationURLsForBundleIdentifier() failed" because
        # LaunchServices doesn't register the id reliably.
        return [open_path, "-W", "-a", app_path, "--args", *args]

    def _macos_app_path(self) -> str | None:
        if not self._command_path:
            return None
        for parent in Path(self._command_path).parents:
            if parent.suffix == ".app":
                return str(parent)
        return None



class PowerPointRenderer:
    """Render PPTX files to PNG using Microsoft PowerPoint via AppleScript."""

    def __init__(
        self,
        *,
        backend: str = "auto",
        delay: float = 1.5,
        slideshow_delay: float = 1.0,
        slide_delay: float = 0.15,
        open_timeout: float = 120.0,
        capture_timeout: float = 5.0,
        use_keys: bool = True,
        allow_reopen: bool = True,
        png_dpi: float | None = None,
    ) -> None:
        self._backend = backend
        self._delay = delay
        self._slideshow_delay = slideshow_delay
        self._slide_delay = slide_delay
        self._open_timeout = open_timeout
        self._capture_timeout = capture_timeout
        self._use_keys = use_keys
        self._allow_reopen = allow_reopen
        self._png_dpi = _resolve_png_dpi() if png_dpi is None else png_dpi

    @property
    def available(self) -> bool:
        return platform.system() == "Darwin" and shutil.which("osascript") is not None

    def render(self, pptx_path: Path | str, output_dir: Path | str) -> RenderedSlideSet:
        if not self.available:
            raise VisualRendererError("PowerPoint capture requires macOS with osascript available.")

        pptx_path = Path(pptx_path)
        if not pptx_path.exists():
            raise VisualRendererError(f"PPTX path does not exist: {pptx_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            from tools.visual import powerpoint_capture

            output_path = output_dir / "slide_1.png"
            powerpoint_capture.capture_pptx_window(
                pptx_path,
                output_path,
                self._delay,
                backend=self._backend,
                capture_timeout=self._capture_timeout,
            )
            
            # Post-process: Trim window chrome and black borders
            if output_path.exists():
                subprocess.run(
                    ["magick", str(output_path), "-fuzz", "15%", "-trim", "+repage", str(output_path)],
                    check=False
                )
        except Exception as exc:
            raise VisualRendererError(str(exc)) from exc

        generated = sorted(output_dir.glob("slide_*.png"))
        if not generated:
            raise VisualRendererError(
                f"PowerPoint capture completed but produced no PNG files in {output_dir}."
            )

        if self._png_dpi is not None:
            self._normalize_pngs(pptx_path, generated, self._png_dpi)

        logger.debug("Generated %d slide image(s).", len(generated))
        return RenderedSlideSet(images=tuple(generated), renderer="powerpoint")

    def _normalize_pngs(
        self,
        pptx_path: Path,
        images: Sequence[Path],
        png_dpi: float,
    ) -> None:
        _normalize_pngs(pptx_path, images, png_dpi)


def _normalize_pngs(
    pptx_path: Path,
    images: Sequence[Path],
    png_dpi: float,
) -> None:
    target_size = _slide_size_to_pixels(pptx_path, png_dpi)
    if target_size is None:
        logger.warning("Unable to resolve slide size for %s; skipping PNG normalization.", pptx_path)
        return

    for image_path in images:
        with Image.open(image_path) as img:
            if img.size == target_size:
                continue
            resized = img.resize(target_size, resample=Image.LANCZOS)
            resized.save(image_path)


def default_renderer(
    *,
    timeout: float | None = 90.0,
    user_installation: str | None = None,
) -> LibreOfficeRenderer:
    """Return a renderer using an explicit path, macOS default, or PATH lookup."""

    soffice_override = os.getenv("SVG2OOXML_SOFFICE_PATH")
    if not soffice_override:
        mac_default = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if mac_default.exists():
            soffice_override = str(mac_default)
    if user_installation is None:
        user_installation = os.getenv("SVG2OOXML_SOFFICE_USER_INSTALL")
    png_dpi = _resolve_png_dpi()
    return LibreOfficeRenderer(
        soffice_path=soffice_override,
        timeout=timeout,
        user_installation=user_installation,
        png_dpi=png_dpi,
    )


PptxRenderer = LibreOfficeRenderer | PowerPointRenderer


def resolve_renderer(
    *,
    renderer_name: str | None = None,
    soffice_path: str | None = None,
    timeout: float | None = 90.0,
    user_installation: str | None = None,
    powerpoint_backend: str = "auto",
    powerpoint_open_timeout: float = 120.0,
    powerpoint_capture_timeout: float = 5.0,
    powerpoint_no_reopen: bool = False,
) -> PptxRenderer:
    """Resolve the configured visual renderer."""

    selected = (renderer_name or os.getenv("SVG2OOXML_VISUAL_RENDERER") or "soffice").strip().lower()
    if selected in {"soffice", "libreoffice"}:
        if soffice_path:
            return LibreOfficeRenderer(
                soffice_path=soffice_path,
                timeout=timeout,
                user_installation=user_installation,
                png_dpi=_resolve_png_dpi(),
            )
        return default_renderer(timeout=timeout, user_installation=user_installation)
    if selected == "powerpoint":
        return PowerPointRenderer(
            backend=powerpoint_backend,
            open_timeout=powerpoint_open_timeout,
            capture_timeout=powerpoint_capture_timeout,
            allow_reopen=not powerpoint_no_reopen,
        )
    raise ValueError(f"Unknown visual renderer: {selected!r}")


def _resolve_png_dpi() -> float | None:
    env_value = os.getenv("SVG2OOXML_SOFFICE_PNG_DPI")
    if env_value is None or env_value == "":
        return 96.0
    if env_value.lower() in {"none", "off", "false"}:
        return None
    try:
        dpi = float(env_value)
    except ValueError as exc:
        raise ValueError(f"Invalid SVG2OOXML_SOFFICE_PNG_DPI value: {env_value!r}") from exc
    if dpi <= 0:
        return None
    return dpi


def _slide_size_to_pixels(pptx_path: Path, dpi: float) -> tuple[int, int] | None:
    size_emu = _read_slide_size_emu(pptx_path)
    if size_emu is None:
        return None
    width_emu, height_emu = size_emu
    emu_per_inch = 914400
    width_px = int(round((width_emu / emu_per_inch) * dpi))
    height_px = int(round((height_emu / emu_per_inch) * dpi))
    if width_px <= 0 or height_px <= 0:
        return None
    return (width_px, height_px)


def _read_slide_size_emu(pptx_path: Path) -> tuple[int, int] | None:
    try:
        with zipfile.ZipFile(pptx_path, "r") as archive:
            xml = archive.read("ppt/presentation.xml")
    except (KeyError, FileNotFoundError, zipfile.BadZipFile) as exc:
        logger.warning("Unable to read presentation.xml from %s: %s", pptx_path, exc)
        return None

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        logger.warning("Unable to parse presentation.xml from %s: %s", pptx_path, exc)
        return None

    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    node = root.find("p:sldSz", ns)
    if node is None:
        return None
    try:
        return (int(node.attrib["cx"]), int(node.attrib["cy"]))
    except (KeyError, ValueError):
        return None


__all__ = [
    "LibreOfficeRenderer",
    "PptxRenderer",
    "PowerPointRenderer",
    "RenderedSlideSet",
    "VisualRendererError",
    "default_renderer",
    "resolve_renderer",
]
