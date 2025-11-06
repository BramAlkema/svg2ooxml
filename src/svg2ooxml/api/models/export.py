"""Pydantic models shared between API routes and services."""

from __future__ import annotations

from typing import Any, List, Optional

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
    source_url: Optional[AnyUrl] = Field(
        None,
        description="Optional remote location (TTF/OTF/CSS) for downloading the font",
    )
    weight: Optional[int] = Field(
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
    fallback: List[str] = Field(
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
    def _coerce_fallback(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return [str(value)]


class SVGFrame(BaseModel):
    """Single SVG frame to convert into a slide."""

    name: Optional[str] = Field(None, description="Frame name from Figma")
    svg_content: str = Field(..., description="SVG content as string")
    width: float = Field(..., gt=0, description="Frame width in pixels")
    height: float = Field(..., gt=0, description="Frame height in pixels")


class ExportRequest(BaseModel):
    """Request payload for creating an export job."""

    frames: List[SVGFrame] = Field(..., min_length=1, description="SVG frames to convert")
    figma_file_id: Optional[str] = Field(None, description="Figma file ID for reference")
    figma_file_name: Optional[str] = Field(None, description="Figma file name")
    output_format: str = Field(
        "pptx",
        pattern="^(pptx|slides)$",
        description="Desired output surface",
    )
    fonts: List[RequestedFont] = Field(
        default_factory=list,
        description="Optional set of fonts required for the conversion",
    )
    parent_folder_id: Optional[str] = Field(
        None,
        description="Google Drive folder ID where Slides should be created (slides format only)",
    )
    user_refresh_token: Optional[str] = Field(
        None,
        description="Firebase refresh token for OAuth operations (required for Slides publishing)",
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
    pptx_url: Optional[str] = Field(None, description="Cloud Storage signed URL for PPTX")
    slides_url: Optional[str] = Field(None, description="Google Slides public URL")
    thumbnail_urls: Optional[List[str]] = Field(None, description="Slide thumbnail URLs")
    error: Optional[str] = Field(None, description="Error message if job failed")
    slides_error: Optional[str] = Field(None, description="Error reported when Slides publishing failed")
    created_at: str
    updated_at: str
    conversion_summary: Optional[dict[str, Any]] = Field(
        None,
        description="Key metrics captured during conversion",
    )
    font_summary: Optional[dict[str, Any]] = Field(
        None,
        description="Information about fonts requested/resolved during conversion",
    )
    slides_embed_url: Optional[str] = Field(None, description="Embeddable iframe URL for the Slides presentation")
    slides_presentation_id: Optional[str] = Field(None, description="Google Slides file identifier")


__all__ = [
    "RequestedFont",
    "SVGFrame",
    "ExportRequest",
    "ExportResponse",
    "JobStatusResponse",
]
