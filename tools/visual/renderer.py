"""Utilities for rendering PPTX slides to bitmap images for visual tests."""

from __future__ import annotations

import logging
import os
import platform
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


logger = logging.getLogger(__name__)


class VisualRendererError(RuntimeError):
    """Raised when the external rendering tool fails."""


@dataclass
class RenderedSlideSet:
    """Container describing the output from a rendering pass."""

    images: Sequence[Path]
    renderer: str


class LibreOfficeRenderer:
    """Render PPTX files to PNG using LibreOffice (soffice) headless mode."""

    def __init__(
        self,
        soffice_path: str | None = None,
        *,
        timeout: float | None = 90.0,
    ) -> None:
        self._timeout = timeout
        self._command_path = soffice_path or shutil.which("soffice")

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

    def render(self, pptx_path: Path | str, output_dir: Path | str) -> RenderedSlideSet:
        """Render *pptx_path* into PNG images under *output_dir*."""

        if not self.available:
            raise VisualRendererError("LibreOffice (soffice) is not installed or not on PATH.")

        pptx_path = Path(pptx_path)
        if not pptx_path.exists():
            raise VisualRendererError(f"PPTX path does not exist: {pptx_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        soffice_args = [
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
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

        generated = sorted(output_dir.glob("*.png"))
        if not generated:
            raise VisualRendererError(
                f"LibreOffice completed but produced no PNG files in {output_dir}."
            )

        logger.debug("Generated %d slide image(s).", len(generated))
        return RenderedSlideSet(images=tuple(generated), renderer="soffice")

    def _macos_open_command(self, args: Sequence[str]) -> list[str] | None:
        open_path = shutil.which("open")
        app_path = self._macos_app_path()
        if not open_path or not app_path:
            return None

        bundle_id, app_name = self._macos_bundle_info(app_path)
        if bundle_id:
            return [open_path, "-W", "-b", bundle_id, "--args", *args]
        if app_name:
            return [open_path, "-W", "-a", app_name, "--args", *args]
        return [open_path, "-W", "-a", app_path, "--args", *args]

    def _macos_app_path(self) -> str | None:
        if not self._command_path:
            return None
        for parent in Path(self._command_path).parents:
            if parent.suffix == ".app":
                return str(parent)
        return None

    def _macos_bundle_info(self, app_path: str) -> tuple[str | None, str | None]:
        info_path = Path(app_path) / "Contents" / "Info.plist"
        if not info_path.exists():
            return None, None
        try:
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
        except Exception:  # pragma: no cover - defensive
            return None, None
        bundle_id = info.get("CFBundleIdentifier")
        app_name = info.get("CFBundleName") or info.get("CFBundleDisplayName")
        return bundle_id, app_name


def default_renderer() -> LibreOfficeRenderer:
    """Return a renderer using an explicit path, macOS default, or PATH lookup."""

    soffice_override = os.getenv("SVG2OOXML_SOFFICE_PATH")
    if not soffice_override:
        mac_default = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        if mac_default.exists():
            soffice_override = str(mac_default)
    return LibreOfficeRenderer(soffice_path=soffice_override)


__all__ = [
    "LibreOfficeRenderer",
    "RenderedSlideSet",
    "VisualRendererError",
    "default_renderer",
]
