"""Environment-driven settings for export processing."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_FALSE_VALUES = {"0", "false", "no", "off"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_bool_non_false(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class ParallelExportSettings:
    """Switches controlling parallel batch conversion."""

    force: bool
    disabled: bool
    enabled: bool
    threshold: int
    timeout_s: float | None
    bail: bool
    bundle_dir: Path | None
    openxml_validator: str | None
    openxml_policy: str
    openxml_required: bool

    @classmethod
    def from_env(
        cls,
        *,
        tmp_dir: Path | None = None,
    ) -> ParallelExportSettings:
        bundle_env = os.getenv("SVG2OOXML_BUNDLE_DIR")
        bundle_dir = Path(bundle_env).expanduser() if bundle_env else None
        if bundle_dir is not None:
            try:
                bundle_dir.mkdir(parents=True, exist_ok=True)
                if not bundle_dir.is_dir():
                    raise NotADirectoryError(f"{bundle_dir} is not a directory")
            except Exception as exc:
                logger.warning("Invalid SVG2OOXML_BUNDLE_DIR %s: %s", bundle_dir, exc)
                bundle_dir = None
        if bundle_dir is None and tmp_dir is not None:
            bundle_dir = tmp_dir / "bundles"
            bundle_dir.mkdir(parents=True, exist_ok=True)
        disabled = _env_bool("SVG2OOXML_PARALLEL_DISABLE", False)
        enabled = _env_bool_non_false("SVG2OOXML_PARALLEL_ENABLE", True)
        return cls(
            force=_env_bool("SVG2OOXML_PARALLEL_FORCE", False),
            disabled=disabled,
            enabled=enabled and not disabled,
            threshold=_env_int("SVG2OOXML_PARALLEL_SLIDE_THRESHOLD", 25),
            timeout_s=_env_float("SVG2OOXML_PARALLEL_TIMEOUT_S"),
            bail=_env_bool("SVG2OOXML_PARALLEL_BAIL", True),
            bundle_dir=bundle_dir,
            openxml_validator=os.getenv("OPENXML_VALIDATOR"),
            openxml_policy=os.getenv("OPENXML_POLICY", "strict"),
            openxml_required=_env_bool("OPENXML_REQUIRED", False),
        )

    def should_use_parallel(self, frame_count: int) -> bool:
        if self.disabled:
            return False
        if self.force:
            return True
        if not self.enabled:
            return False
        return frame_count >= max(1, self.threshold)


__all__ = ["ParallelExportSettings"]
