"""Processing options inspired by `usvg::Options`."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from svg2ooxml.common.boundaries import decode_data_uri, resolve_local_resource_path
from svg2ooxml.core.resvg.config import DEFAULT_CONFIG, Config
from svg2ooxml.core.resvg.constants import DEFAULT_DPI
from svg2ooxml.core.resvg.text.fonts import FontResolver, default_font_resolver
from svg2ooxml.core.resvg.utils.mimesniff import sniff_image_mime


class ShapeRendering(StrEnum):
    GEOMETRIC_PRECISION = "geometricPrecision"
    CRISP_EDGES = "crispEdges"
    OPTIMIZE_SPEED = "optimizeSpeed"


class TextRendering(StrEnum):
    OPTIMIZE_LEGIBILITY = "optimizeLegibility"
    OPTIMIZE_SPEED = "optimizeSpeed"
    GEOMETRIC_PRECISION = "geometricPrecision"


class ImageRendering(StrEnum):
    OPTIMIZE_QUALITY = "optimizeQuality"
    OPTIMIZE_SPEED = "optimizeSpeed"
    AUTO = "auto"


@dataclass(frozen=True)
class Size:
    """Viewport size when width/height are omitted on the SVG root."""

    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Size dimensions must be > 0")

    @classmethod
    def from_wh(cls, width: float, height: float) -> Size:
        return cls(width=width, height=height)


DataHrefResolver = Callable[[str], bytes | None]
FileHrefResolver = Callable[[str], Path | None]


def _default_data_resolver(_: str) -> bytes | None:
    return None


def _default_file_resolver(_: str) -> Path | None:
    return None


@dataclass
class ImageHrefResolver:
    """Callbacks that resolve <image href> payloads."""

    resolve_data: DataHrefResolver = _default_data_resolver
    resolve_file: FileHrefResolver = _default_file_resolver


@dataclass
class Options:
    """Configuration object roughly equivalent to `usvg::Options`."""

    resources_dir: Path | None = None
    asset_root: Path | None = None
    dpi: float = DEFAULT_DPI
    font_family: str = "Times New Roman"
    font_size: float = 12.0
    languages: list[str] = field(default_factory=lambda: ["en"])
    shape_rendering: ShapeRendering = ShapeRendering.GEOMETRIC_PRECISION
    text_rendering: TextRendering = TextRendering.OPTIMIZE_LEGIBILITY
    image_rendering: ImageRendering = ImageRendering.OPTIMIZE_QUALITY
    default_size: Size = field(default_factory=lambda: Size.from_wh(100.0, 100.0))
    image_href_resolver: ImageHrefResolver = field(default_factory=ImageHrefResolver)
    style_sheet: str | None = None
    font_resolver: FontResolver | None = None

    def __post_init__(self) -> None:
        if self.dpi <= 0:
            raise ValueError("dpi must be > 0")
        if self.font_size <= 0:
            raise ValueError("font_size must be > 0")
        if not self.languages:
            raise ValueError("languages must contain at least one locale tag")

    def with_languages(self, languages: Iterable[str]) -> Options:
        langs = [lang.strip() for lang in languages if lang.strip()]
        if not langs:
            raise ValueError("languages iterable produced no valid entries")
        return self.clone(languages=langs)

    def get_abs_path(self, rel_path: Path | str) -> Path:
        rel_path = Path(rel_path)
        if rel_path.is_absolute() or self.resources_dir is None:
            return rel_path
        return self.resources_dir / rel_path

    def resolve_resource(self, href: str) -> Path:
        path = Path(href)
        if not path.is_absolute() and self.resources_dir is not None:
            path = (self.resources_dir / path).resolve()
        return path

    def clone(self, **updates: object) -> Options:
        data = {
            "resources_dir": self.resources_dir,
            "asset_root": self.asset_root,
            "dpi": self.dpi,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "languages": list(self.languages),
            "shape_rendering": self.shape_rendering,
            "text_rendering": self.text_rendering,
            "image_rendering": self.image_rendering,
            "default_size": self.default_size,
            "image_href_resolver": self.image_href_resolver,
            "style_sheet": self.style_sheet,
            "font_resolver": self.font_resolver,
        }
        data.update(updates)
        return Options(**data)


def _noop_image_resolver() -> ImageHrefResolver:
    return ImageHrefResolver(
        resolve_data=_default_data_resolver,
        resolve_file=_default_file_resolver,
    )


def _build_image_resolver(
    config: Config,
    resources_dir: Path | None,
    asset_root: Path | None,
) -> ImageHrefResolver:
    if not config.feature_enabled("raster-images"):
        return _noop_image_resolver()

    def resolve_file(href: str) -> Path | None:
        if resources_dir is None:
            return None
        path = resolve_local_resource_path(
            href,
            resources_dir,
            asset_root=asset_root or resources_dir,
        )
        if path is None or path.stat().st_size == 0:
            return None
        mime = sniff_image_mime(path)
        return path if mime else None

    def resolve_data(href: str) -> bytes | None:
        decoded = decode_data_uri(href)
        return decoded.data if decoded is not None else None

    return ImageHrefResolver(resolve_data=resolve_data, resolve_file=resolve_file)


def build_default_options(
    config: Config | None = None,
    *,
    resources_dir: Path | None = None,
    asset_root: Path | None = None,
    **overrides: object,
) -> Options:
    cfg = config or DEFAULT_CONFIG
    options = Options(resources_dir=resources_dir or None, asset_root=asset_root or None)

    if cfg.feature_enabled("raster-images"):
        options.image_href_resolver = _build_image_resolver(
            cfg,
            options.resources_dir,
            options.asset_root,
        )
    else:
        options.image_href_resolver = _noop_image_resolver()

    if cfg.feature_enabled("text"):
        options.font_resolver = default_font_resolver(cfg)
    else:
        options.font_resolver = None

    for key, value in overrides.items():
        setattr(options, key, value)

    return options
