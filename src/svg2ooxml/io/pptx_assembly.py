"""PPTX assembly layer: data classes, constants, and high-level building facade."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.ooxml_relationships import is_safe_relationship_id
from svg2ooxml.drawingml.assets import FontAsset, MediaAsset, NavigationAsset
from svg2ooxml.drawingml.result import DrawingMLRenderResult

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
MASK_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.drawingml.mask+xml"
_SAFE_PACKAGE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_PACKAGE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,16}\Z")
_CONTENT_TYPE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/gif": (".gif",),
    "image/svg+xml": (".svg",),
    "image/x-emf": (".emf",),
    MASK_CONTENT_TYPE: (".xml",),
}


def _normalized_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _suffixes_for_content_type(content_type: str | None) -> tuple[str, ...]:
    return _CONTENT_TYPE_SUFFIXES.get(_normalized_content_type(content_type), (".bin",))


def _normalize_package_suffix(suffix: str | None, fallback: str) -> str:
    fallback_suffix = fallback if fallback.startswith(".") else f".{fallback}"
    fallback_suffix = fallback_suffix.lower()
    if not _SAFE_PACKAGE_SUFFIX_RE.fullmatch(fallback_suffix):
        fallback_suffix = ".bin"

    candidate = (suffix or "").strip()
    if candidate and not candidate.startswith("."):
        candidate = f".{candidate}"
    candidate = candidate.lower()
    if _SAFE_PACKAGE_SUFFIX_RE.fullmatch(candidate):
        return candidate
    return fallback_suffix


def sanitize_package_filename(
    filename: str | None,
    *,
    fallback_stem: str = "part",
    fallback_suffix: str = ".bin",
) -> str:
    """Return a single safe OPC filename with no directory components."""

    raw = str(filename or "").replace("\\", "/").rstrip("/")
    name = raw.rsplit("/", 1)[-1].strip()
    if name in {"", ".", ".."}:
        name = ""

    path = Path(name)
    stem = path.stem if path.stem not in {"", ".", ".."} else ""
    safe_stem = _SAFE_PACKAGE_FILENAME_RE.sub("_", stem).strip("._")
    if not safe_stem:
        safe_stem = fallback_stem
    suffix = _normalize_package_suffix(path.suffix, fallback_suffix)
    return f"{safe_stem}{suffix}"


def _sanitize_filename_for_content_type(
    filename: str | None,
    content_type: str | None,
    *,
    fallback_stem: str,
) -> str:
    suffixes = _suffixes_for_content_type(content_type)
    fallback_suffix = suffixes[0]
    candidate = sanitize_package_filename(
        filename,
        fallback_stem=fallback_stem,
        fallback_suffix=fallback_suffix,
    )
    path = Path(candidate)
    suffix = path.suffix.lower()
    if suffix not in suffixes:
        suffix = fallback_suffix
    stem = path.stem or fallback_stem
    return f"{stem}{suffix}"


def sanitize_media_filename(filename: str | None, content_type: str | None) -> str:
    """Return a safe package filename for media parts."""

    return _sanitize_filename_for_content_type(
        filename,
        content_type,
        fallback_stem="media",
    )


def sanitize_mask_part_name(part_name: str | None, content_type: str | None) -> str:
    """Return a safe absolute OPC part name for DrawingML mask assets."""

    filename = sanitize_package_filename(part_name, fallback_stem="mask")
    safe_filename = _sanitize_filename_for_content_type(
        filename,
        content_type,
        fallback_stem="mask",
    )
    return f"/ppt/masks/{safe_filename}"


def sanitize_slide_filename(filename: str | None, *, fallback_index: object = None) -> str:
    """Return a safe slide XML filename with no directory components."""

    index = _positive_int(fallback_index)
    fallback_stem = f"slide{index}" if index is not None else "slide"
    candidate = sanitize_package_filename(
        filename,
        fallback_stem=fallback_stem,
        fallback_suffix=".xml",
    )
    stem = Path(candidate).stem or fallback_stem
    return f"{stem}.xml"


def resolve_package_child(
    package_root: Path,
    package_path: Path,
    *,
    required_prefix: Path | None = None,
) -> Path:
    """Resolve an OPC child path and reject traversal outside the package root."""

    root = package_root.resolve()
    target = (package_root / package_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Package part escapes PPTX staging directory: {package_path}") from exc

    if required_prefix is not None:
        prefix = (package_root / required_prefix).resolve()
        try:
            target.relative_to(prefix)
        except ValueError as exc:
            raise ValueError(
                f"Package part is outside required prefix {required_prefix}: {package_path}"
            ) from exc

    return target


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return parsed


@dataclass
class PackagedMedia:
    relationship_id: str
    filename: str
    content_type: str
    data: bytes

    def __post_init__(self) -> None:
        self.filename = sanitize_media_filename(self.filename, self.content_type)

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

    def __post_init__(self) -> None:
        self.filename = sanitize_slide_filename(self.filename, fallback_index=self.index)


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

    def __post_init__(self) -> None:
        self.part_name = sanitize_mask_part_name(self.part_name, self.content_type)

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "filename",
            sanitize_slide_filename(self.filename, fallback_index=self.index),
        )


@dataclass(frozen=True, slots=True)
class MediaMeta:
    """Lightweight media metadata for content-type tracking (no binary data)."""

    filename: str
    content_type: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "filename",
            sanitize_media_filename(self.filename, self.content_type),
        )


@dataclass(frozen=True, slots=True)
class MaskMeta:
    """Lightweight mask metadata for content-type tracking (no binary data)."""

    part_name: str
    content_type: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "part_name",
            sanitize_mask_part_name(self.part_name, self.content_type),
        )


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

        base = sanitize_media_filename(
            asset.filename or f"media_{self._media_counter}",
            asset.content_type,
        )
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

    def allocate_media_relationship_id(self, preferred_id: object | None = None) -> str:
        """Return a safe media relationship ID."""

        if is_safe_relationship_id(preferred_id):
            assert isinstance(preferred_id, str)
            return preferred_id
        rel_id = f"rIdMedia{self._media_counter}"
        self._media_counter += 1
        return rel_id

    @staticmethod
    def _suffix_for_content_type(content_type: str) -> str:
        return suffix_for_content_type(content_type)


def suffix_for_content_type(content_type: str) -> str:
    """Map image MIME type to file extension."""
    return _suffixes_for_content_type(content_type)[0]


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
                    relationship_id=self._context.allocate_media_relationship_id(
                        asset.relationship_id
                    ),
                    filename=assigned_name,
                    content_type=asset.content_type,
                    data=asset.data,
                )
            )

        mask_parts: list[MaskAsset] = []
        for mask in result.assets.iter_masks():
            mask_parts.append(
                MaskAsset(
                    relationship_id=self._context.allocate_media_relationship_id(
                        mask.get("relationship_id")
                    ),
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
    "MASK_CONTENT_TYPE",
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
    "resolve_package_child",
    "safe_int",
    "sanitize_mask_part_name",
    "sanitize_media_filename",
    "sanitize_package_filename",
    "sanitize_slide_filename",
    "suffix_for_content_type",
    "write_pptx",
]
