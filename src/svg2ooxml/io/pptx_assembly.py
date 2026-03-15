"""PPTX assembly layer: data classes, constants, and high-level building facade."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.drawingml.assets import FontAsset, MediaAsset, NavigationAsset
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

if TYPE_CHECKING:  # pragma: no cover - typing only
    from svg2ooxml.core.ir import IRScene
    from svg2ooxml.core.tracing import ConversionTracer

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets" / "pptx_scaffold"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
THEME_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
THEME_FAMILY_NS = "http://schemas.microsoft.com/office/thememl/2012/main"
ET.register_namespace("thm15", THEME_FAMILY_NS)
MASK_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
FONT_STYLE_TAGS: dict[str, str] = {
    "regular": "regular",
    "bold": "bold",
    "italic": "italic",
    "boldItalic": "boldItalic",
}
FONT_STYLE_ORDER: tuple[str, ...] = ("regular", "bold", "italic", "boldItalic")


@dataclass
class PackagedMedia:
    relationship_id: str
    filename: str
    content_type: str
    data: bytes

    @property
    def package_path(self) -> Path:
        return Path("ppt") / "media" / self.filename

    @property
    def relationship_target(self) -> str:
        return f"../media/{self.filename}"


@dataclass
class SlideAssembly:
    index: int
    filename: str
    rel_id: str
    slide_id: int
    slide_xml: str
    slide_size: tuple[int, int]
    media: list[PackagedMedia]
    navigation: list[NavigationAsset] = field(default_factory=list)
    masks: list[MaskAsset] = field(default_factory=list)
    font_assets: list[FontAsset] = field(default_factory=list)


@dataclass
class PackagedFont:
    filename: str
    relationship_id: str
    font_family: str
    subsetted: bool
    content_type: str
    style_kind: str = "regular"
    style_flags: dict[str, bool] = field(default_factory=dict)
    guid: str | None = None
    root_string: str | None = None
    subset_prefix: str | None = None
    pitch_family: int | None = None
    charset: int | None = None


@dataclass
class MaskAsset:
    relationship_id: str
    part_name: str
    content_type: str
    data: bytes

    @property
    def package_path(self) -> Path:
        part = self.part_name.lstrip("/")
        return Path(part)

    @property
    def relationship_target(self) -> str:
        path = self.package_path
        if path.parts and path.parts[0] == "ppt":
            relative_parts = ["..", *path.parts[1:]]
            return "/".join(relative_parts)
        return path.as_posix()


@dataclass(frozen=True, slots=True)
class SlideEntry:
    """Lightweight slide metadata retained during streaming (no XML/binary data)."""

    index: int
    filename: str
    rel_id: str
    slide_id: int
    slide_size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class MediaMeta:
    """Lightweight media metadata for content-type tracking (no binary data)."""

    filename: str
    content_type: str


@dataclass(frozen=True, slots=True)
class MaskMeta:
    """Lightweight mask metadata for content-type tracking (no binary data)."""

    part_name: str
    content_type: str


class PackagingContext:
    """Assign unique identifiers and filenames while packaging."""

    def __init__(self) -> None:
        self._media_by_signature: dict[tuple[str, str], str] = {}
        self._used_media_filenames: set[str] = set()
        self._media_counter = 1
        self._presentation_rel_counter = 2
        self._next_slide_id = 256

    def assign_media_filename(self, asset: MediaAsset, slide_index: int) -> str:
        """Return a deterministic filename for the supplied media payload."""
        digest = hashlib.md5(asset.data, usedforsecurity=False).hexdigest()
        key = (asset.filename, digest)
        existing = self._media_by_signature.get(key)
        if existing:
            return existing

        base = asset.filename or f"media_{self._media_counter}"
        path = Path(base)
        stem = path.stem or "media"
        suffix = path.suffix or self._suffix_for_content_type(asset.content_type)
        candidate = f"{stem}{suffix}"

        while candidate in self._used_media_filenames:
            candidate = f"{stem}_{slide_index}_{self._media_counter}{suffix}"
            self._media_counter += 1

        self._media_by_signature[key] = candidate
        self._used_media_filenames.add(candidate)
        self._media_counter += 1
        return candidate

    def allocate_slide_entry(self) -> tuple[str, int]:
        """Allocate presentation relationship and slide id."""
        rel_id = f"rId{self._presentation_rel_counter}"
        self._presentation_rel_counter += 1
        slide_id = self._next_slide_id
        self._next_slide_id += 1
        return rel_id, slide_id

    @staticmethod
    def _suffix_for_content_type(content_type: str) -> str:
        return suffix_for_content_type(content_type)


def suffix_for_content_type(content_type: str) -> str:
    """Map image MIME type to file extension."""
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/x-emf": ".emf",
    }
    return mapping.get(content_type, ".bin")


class SlideAssembler:
    """Build slide-level packaging metadata from DrawingML render results."""

    def __init__(self, context: PackagingContext) -> None:
        self._context = context

    def assemble_one(self, result: DrawingMLRenderResult, index: int) -> SlideAssembly:
        """Assemble packaging metadata for a single render result."""
        rel_id, slide_id = self._context.allocate_slide_entry()
        slide_filename = f"slide{index}.xml"
        media_parts: list[PackagedMedia] = []
        for asset in result.assets.iter_media():
            assigned_name = self._context.assign_media_filename(asset, index)
            media_parts.append(
                PackagedMedia(
                    relationship_id=asset.relationship_id,
                    filename=assigned_name,
                    content_type=asset.content_type,
                    data=asset.data,
                )
            )

        mask_parts: list[MaskAsset] = []
        for mask in result.assets.iter_masks():
            mask_parts.append(
                MaskAsset(
                    relationship_id=mask["relationship_id"],
                    part_name=mask["part_name"],
                    content_type=mask["content_type"],
                    data=mask["data"],
                )
            )

        return SlideAssembly(
            index=index,
            filename=slide_filename,
            rel_id=rel_id,
            slide_id=slide_id,
            slide_xml=result.slide_xml,
            slide_size=result.slide_size,
            media=media_parts,
            navigation=list(result.assets.iter_navigation()),
            masks=mask_parts,
            font_assets=list(result.assets.iter_fonts()),
        )

    def assemble(self, render_results: Sequence[DrawingMLRenderResult]) -> list[SlideAssembly]:
        return [
            self.assemble_one(result, index)
            for index, result in enumerate(render_results, start=1)
        ]


ALLOWED_SLIDE_SIZE_MODES = {"multipage", "same"}


class PPTXPackageBuilder:
    """Create PPTX packages using the clean-slate template library."""

    def __init__(self, *, assets_root: Path | None = None, slide_size_mode: str | None = None) -> None:
        self._assets_root = assets_root or ASSETS_ROOT
        self._base_template = self._assets_root / "clean_slate"
        self._content_types_template = (self._assets_root / "content_types.xml").read_text(encoding="utf-8")
        self._slide_rels_template = (
            self._base_template / "ppt" / "slides" / "_rels" / "slide.xml.rels"
        ).read_text(encoding="utf-8")
        from svg2ooxml.drawingml.writer import DrawingMLWriter

        self._writer = DrawingMLWriter(template_dir=self._assets_root)
        self._slide_size_mode = slide_size_mode

    def build(
        self,
        scene: IRScene,
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for the supplied IR scene."""
        return self.build_scenes([scene], output_path, tracer=tracer, persist_trace=persist_trace)

    def build_scenes(
        self,
        scenes: Sequence[IRScene],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
    ) -> Path:
        """Materialise a PPTX file for a sequence of IR scenes."""
        render_results = []
        for scene in scenes:
            animation_payload = None
            if isinstance(scene.metadata, dict):
                animation_payload = scene.metadata.get("animation_raw")
            render_results.append(
                self._writer.render_scene_from_ir(
                    scene,
                    tracer=tracer,
                    animation_payload=animation_payload,
                )
            )
        return self.build_from_results(render_results, output_path, tracer=tracer, persist_trace=persist_trace)

    def build_from_results(
        self,
        render_results: Sequence[DrawingMLRenderResult],
        output_path: str | Path,
        *,
        tracer: ConversionTracer | None = None,
        persist_trace: bool | None = None,
        slide_size_mode: str | None = None,
    ) -> Path:
        """Package pre-rendered slides returned by DrawingMLWriter."""
        if not render_results:
            raise ValueError("At least one render result is required to build a PPTX package.")

        from svg2ooxml.io.pptx_writer import PackageWriter

        context = PackagingContext()
        slide_assemblies = SlideAssembler(context).assemble(render_results)
        package_writer = PackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
        )
        return package_writer.write_package(
            slide_assemblies,
            output_path,
            tracer=tracer,
            persist_trace=persist_trace,
            slide_size_mode=slide_size_mode,
        )

    def begin_streaming(
        self,
        *,
        tracer: ConversionTracer | None = None,
    ):
        """Create a streaming writer for incremental slide addition."""
        from svg2ooxml.io.pptx_writer import StreamingPackageWriter

        return StreamingPackageWriter(
            base_template=self._base_template,
            content_types_template=self._content_types_template,
            slide_rels_template=self._slide_rels_template,
            slide_size_mode=self._slide_size_mode,
            tracer=tracer,
        )


def write_pptx(scene: IRScene, output_path: str | Path) -> Path:
    """Public helper mirroring the historical API."""
    builder = PPTXPackageBuilder()
    return builder.build(scene, output_path)


def content_type_for_extension(extension: str) -> str:
    mapping = {
        "ttf": "application/x-fontdata",
        "otf": "application/x-fontdata",
        "woff": "application/font-woff",
        "woff2": "application/font-woff2",
        "odttf": "application/vnd.openxmlformats-officedocument.obfuscatedFont",
        "fntdata": "application/x-fontdata",
    }
    return mapping.get(extension.lower(), "application/octet-stream")


def normalize_style_kind(value: object) -> str:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "bolditalic":
            return "boldItalic"
        if lowered in FONT_STYLE_TAGS:
            return lowered
    return "regular"


def safe_int(value: object | None) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


__all__ = [
    "ALLOWED_SLIDE_SIZE_MODES",
    "ASSETS_ROOT",
    "CONTENT_NS",
    "FONT_STYLE_ORDER",
    "FONT_STYLE_TAGS",
    "MASK_REL_TYPE",
    "P_NS",
    "PPTXPackageBuilder",
    "PackagingContext",
    "R_DOC_NS",
    "REL_NS",
    "SlideAssembler",
    "SlideAssembly",
    "THEME_FAMILY_NS",
    "THEME_NS",
    "content_type_for_extension",
    "normalize_style_kind",
    "safe_int",
    "suffix_for_content_type",
    "write_pptx",
]
