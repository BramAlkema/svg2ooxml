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

    name: str = Field("", description="Frame name from Figma")
    svg_content: str = Field(..., description="SVG content as string")
    width: float = Field(..., gt=0, description="Frame width in pixels")
    height: float = Field(..., gt=0, description="Frame height in pixels")


__all__ = [
    "RequestedFont",
    "SVGFrame",
]
