"""PPTX assembly layer: data classes, constants, and high-level building facade."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree as ET

from svg2ooxml.common.boundaries import (
    is_safe_relationship_id,
    resolve_package_child,
    sanitize_package_filename,
)
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

    def allocate_media_relationship_id(
        self,
        preferred_id: object | None = None,
        *,
        existing_ids: set[str] | None = None,
    ) -> str:
        """Return a safe media relationship ID."""

        existing_ids = existing_ids or set()
        if is_safe_relationship_id(preferred_id) and preferred_id not in existing_ids:
            assert isinstance(preferred_id, str)
            return preferred_id

        while True:
            rel_id = f"rIdMedia{self._media_counter}"
            self._media_counter += 1
            if rel_id not in existing_ids:
                return rel_id

    @staticmethod
    def _suffix_for_content_type(content_type: str) -> str:
        return suffix_for_content_type(content_type)


def suffix_for_content_type(content_type: str) -> str:
    """Map image MIME type to file extension."""
    return _suffixes_for_content_type(content_type)[0]


class SlideAssembler:
    """Build slide-level packaging metadata from DrawingML render results."""

    def __init__(
        self,
        context: PackagingContext,
        *,
        slide_rels_template: str,
    ) -> None:
        self._context = context
        self._reserved_relationship_ids = _slide_relationship_template_ids(
            slide_rels_template
        )

    def assemble_one(self, result: DrawingMLRenderResult, index: int) -> SlideAssembly:
        """Assemble packaging metadata for a single render result."""
        rel_id, slide_id = self._context.allocate_slide_entry()
        slide_filename = f"slide{index}.xml"
        relationship_rewrites: dict[str, str] = {}
        used_relationship_ids = set(self._reserved_relationship_ids)
        seen_input_relationship_ids: set[str] = set()
        media_parts: list[PackagedMedia] = []
        for asset in result.assets.iter_media():
            _track_unique_input_relationship_id(
                asset.relationship_id,
                seen_input_relationship_ids,
                kind="media",
            )
            assigned_name = self._context.assign_media_filename(asset, index)
            assigned_relationship_id = self._context.allocate_media_relationship_id(
                asset.relationship_id,
                existing_ids=used_relationship_ids,
            )
            used_relationship_ids.add(assigned_relationship_id)
            _record_relationship_rewrite(
                relationship_rewrites,
                asset.relationship_id,
                assigned_relationship_id,
            )
            media_parts.append(
                PackagedMedia(
                    relationship_id=assigned_relationship_id,
                    filename=assigned_name,
                    content_type=asset.content_type,
                    data=asset.data,
                )
            )

        mask_parts: list[MaskAsset] = []
        for mask in result.assets.iter_masks():
            relationship_id = mask.get("relationship_id")
            _track_unique_input_relationship_id(
                relationship_id,
                seen_input_relationship_ids,
                kind="mask",
            )
            assigned_relationship_id = self._context.allocate_media_relationship_id(
                relationship_id,
                existing_ids=used_relationship_ids,
            )
            used_relationship_ids.add(assigned_relationship_id)
            _record_relationship_rewrite(
                relationship_rewrites,
                relationship_id,
                assigned_relationship_id,
            )
            mask_parts.append(
                MaskAsset(
                    relationship_id=assigned_relationship_id,
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
            slide_xml=_rewrite_slide_relationship_references(
                result.slide_xml,
                relationship_rewrites,
            ),
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


def _slide_relationship_template_ids(slide_rels_template: str) -> set[str]:
    rels_root = ET.fromstring(slide_rels_template.encode("utf-8"))
    return {
        rel_id
        for rel_id in (
            rel.get("Id")
            for rel in rels_root.findall(f"{{{REL_NS}}}Relationship")
        )
        if rel_id
    }


def _track_unique_input_relationship_id(
    relationship_id: object,
    seen_ids: set[str],
    *,
    kind: str,
) -> None:
    if not isinstance(relationship_id, str) or not relationship_id:
        return
    if relationship_id in seen_ids:
        raise ValueError(
            f"Duplicate {kind} relationship ID {relationship_id!r} in one slide."
        )
    seen_ids.add(relationship_id)


def _record_relationship_rewrite(
    rewrites: dict[str, str],
    old_id: object,
    new_id: str,
) -> None:
    if isinstance(old_id, str) and old_id and old_id != new_id:
        rewrites[old_id] = new_id


def _rewrite_slide_relationship_references(
    slide_xml: str,
    relationship_rewrites: Mapping[str, str],
) -> str:
    if not relationship_rewrites:
        return slide_xml

    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    try:
        root = ET.fromstring(slide_xml.encode("utf-8"), parser)
    except ET.XMLSyntaxError as exc:
        raise ValueError(
            "Slide XML must be well-formed to rekey packaged relationships."
        ) from exc

    changed = False
    for element in root.iter():
        for attr_name, attr_value in list(element.attrib.items()):
            if (
                attr_name.startswith(f"{{{R_DOC_NS}}}")
                and attr_value in relationship_rewrites
            ):
                element.set(attr_name, relationship_rewrites[attr_value])
                changed = True
    if not changed:
        return slide_xml

    tostring_kwargs: dict[str, object] = {
        "encoding": "UTF-8",
        "xml_declaration": slide_xml.lstrip().startswith("<?xml"),
    }
    if 'standalone="yes"' in slide_xml[:200] or "standalone='yes'" in slide_xml[:200]:
        tostring_kwargs["standalone"] = True
    return ET.tostring(root, **tostring_kwargs).decode("utf-8")


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
        slide_assemblies = SlideAssembler(
            context,
            slide_rels_template=self._slide_rels_template,
        ).assemble(render_results)
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
