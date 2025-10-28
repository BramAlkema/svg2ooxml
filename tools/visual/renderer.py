"""Utilities for rendering PPTX slides to bitmap images for visual tests."""

from __future__ import annotations

import logging
import os
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

        cmd: list[str] = [
            self._command_path or "soffice",  # guarded above
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

        logger.debug("Running soffice renderer: %s", " ".join(cmd))
        try:
            completed = subprocess.run(
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

        if completed.returncode != 0:
            message = "\n".join(
                [
                    "LibreOffice failed to render PPTX.",
                    f"stdout:\n{completed.stdout}",
                    f"stderr:\n{completed.stderr}",
                ]
            )
            raise VisualRendererError(message)

        generated = sorted(output_dir.glob("*.png"))
        if not generated:
            raise VisualRendererError(
                f"LibreOffice completed but produced no PNG files in {output_dir}."
            )

        logger.debug("Generated %d slide image(s).", len(generated))
        return RenderedSlideSet(images=tuple(generated), renderer="soffice")


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
