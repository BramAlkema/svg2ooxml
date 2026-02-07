"""Pydantic models shared between API routes and services."""

from __future__ import annotations

from typing import Any

from pydantic import (
    AnyUrl,
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class RequestedFont(BaseModel):
    """Describe a font that should be available during conversion."""

    family: str = Field(..., min_length=1, description="Primary font family name")
    source_url: AnyUrl | None = Field(
        None,
        description="Optional remote location (TTF/OTF/CSS) for downloading the font",
    )
    weight: int | None = Field(
        None,
        ge=100,
        le=900,
        description="Numeric font weight if known (100-900). Defaults to 400.",
    )
    style: str = Field(
        "normal",
        pattern="^(normal|italic|oblique)$",
        description="Font style hint used when matching fonts",
    )
    fallback: list[str] = Field(
        default_factory=list,
        description="Additional fallback family names in order of preference",
    )
    embed: bool = Field(
        True,
        description="Whether to embed the font when available",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"family": value}
        return value

    @field_validator("fallback", mode="before")
    @classmethod
    def _coerce_fallback(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return [str(value)]


class SVGFrame(BaseModel):
    """Single SVG frame to convert into a slide."""

    name: str | None = Field(None, description="Frame name from Figma")
    svg_content: str = Field(..., description="SVG content as string")
    width: float = Field(..., gt=0, description="Frame width in pixels")
    height: float = Field(..., gt=0, description="Frame height in pixels")


class ExportRequest(BaseModel):
    """Request payload for creating an export job."""

    frames: list[SVGFrame] = Field(..., min_length=1, description="SVG frames to convert")
    figma_file_id: str | None = Field(None, description="Figma file ID for reference")
    figma_file_name: str | None = Field(None, description="Figma file name")
    output_format: str = Field(
        "pptx",
        pattern="^(pptx|slides)$",
        description="Desired output surface",
    )
    fonts: list[RequestedFont] = Field(
        default_factory=list,
        description="Optional set of fonts required for the conversion",
    )
    parent_folder_id: str | None = Field(
        None,
        description="Google Drive folder ID where Slides should be created (slides format only)",
    )
    user_refresh_token: str | None = Field(
        None,
        description=(
            "Deprecated. Slides publishing now uses the stored Google OAuth token from Firestore; "
            "this field is ignored."
        ),
    )


class ExportResponse(BaseModel):
    """Response after creating an export job."""

    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Current job status")
    message: str = Field(..., description="Human-readable status message")


class JobStatusResponse(BaseModel):
    """Response for job status queries."""

    job_id: str
    status: str
    message: str
    progress: float = Field(..., ge=0, le=100, description="Progress percentage")
    pptx_url: str | None = Field(None, description="Cloud Storage signed URL for PPTX")
    slides_url: str | None = Field(None, description="Google Slides public URL")
    thumbnail_urls: list[str] | None = Field(None, description="Slide thumbnail URLs")
    error: str | None = Field(None, description="Error message if job failed")
    slides_error: str | None = Field(None, description="Error reported when Slides publishing failed")
    created_at: str
    updated_at: str
    conversion_summary: dict[str, Any] | None = Field(
        None,
        description="Key metrics captured during conversion",
    )
    font_summary: dict[str, Any] | None = Field(
        None,
        description="Information about fonts requested/resolved during conversion",
    )
    slides_embed_url: str | None = Field(None, description="Embeddable iframe URL for the Slides presentation")
    slides_presentation_id: str | None = Field(None, description="Google Slides file identifier")


__all__ = [
    "RequestedFont",
    "SVGFrame",
    "ExportRequest",
    "ExportResponse",
    "JobStatusResponse",
]
