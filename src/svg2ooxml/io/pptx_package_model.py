"""Dataclasses describing package parts emitted during PPTX assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from svg2ooxml.drawingml.assets import FontAsset, NavigationAsset
from svg2ooxml.io.pptx_part_names import (
    sanitize_mask_part_name,
    sanitize_media_filename,
    sanitize_slide_filename,
)


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


__all__ = [
    "MaskAsset",
    "MaskMeta",
    "MediaMeta",
    "PackagedFont",
    "PackagedMedia",
    "SlideAssembly",
    "SlideEntry",
]
