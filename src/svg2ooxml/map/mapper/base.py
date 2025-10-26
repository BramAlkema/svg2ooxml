"""Shared mapper interfaces for svg2ooxml."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OutputFormat(Enum):
    """Output format for mapped elements."""

    NATIVE_DML = "native_dml"
    EMF_VECTOR = "emf_vector"
    EMF_RASTER = "emf_raster"


@dataclass
class MapperResult:
    """Result of mapping an IR element to an output format."""

    element: Any
    output_format: OutputFormat
    xml_content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    policy_decision: Any | None = None
    estimated_quality: float = 1.0
    estimated_performance: float = 1.0
    processing_time_ms: float = 0.0
    output_size_bytes: int = 0
    compression_ratio: float = 1.0
    media_files: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.estimated_quality <= 1.0):
            raise ValueError(f"Quality must be 0.0-1.0, got {self.estimated_quality}")
        if not (0.0 <= self.estimated_performance <= 1.0):
            raise ValueError(f"Performance must be 0.0-1.0, got {self.estimated_performance}")


class MapperError(Exception):
    """Exception raised when mapping fails."""

    def __init__(self, message: str, element: Any | None = None, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.element = element
        self.cause = cause


class Mapper(ABC):
    """Base class for IR to DrawingML mappers."""

    def __init__(self, policy: Any | None = None) -> None:
        self.policy = policy
        self._stats = {
            "total_mapped": 0,
            "native_count": 0,
            "emf_count": 0,
            "error_count": 0,
            "total_time_ms": 0.0,
        }

    @abstractmethod
    def can_map(self, element: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    def map(self, element: Any) -> MapperResult:
        raise NotImplementedError

    def _record_mapping(self, result: MapperResult) -> None:
        self._stats["total_mapped"] += 1
        self._stats["total_time_ms"] += result.processing_time_ms
        if result.output_format == OutputFormat.NATIVE_DML:
            self._stats["native_count"] += 1
        else:
            self._stats["emf_count"] += 1

    def _record_error(self, _: Exception) -> None:
        self._stats["error_count"] += 1

    def get_statistics(self) -> dict[str, Any]:
        total = max(self._stats["total_mapped"], 1)
        return {
            **self._stats,
            "native_ratio": self._stats["native_count"] / total,
            "emf_ratio": self._stats["emf_count"] / total,
            "error_ratio": self._stats["error_count"] / total,
            "avg_time_ms": self._stats["total_time_ms"] / total,
        }

    def reset_statistics(self) -> None:
        self._stats = {
            "total_mapped": 0,
            "native_count": 0,
            "emf_count": 0,
            "error_count": 0,
            "total_time_ms": 0.0,
        }


def validate_mapper_result(result: MapperResult) -> bool:
    """Validate mapper result for correctness."""

    if not result.xml_content.strip():
        raise ValueError("XML content cannot be empty")

    if result.output_size_bytes < 0:
        raise ValueError("Output size cannot be negative")

    try:
        from lxml import etree

        etree.fromstring(f"<root>{result.xml_content}</root>")
    except Exception as exc:  # pragma: no cover - defensive validation
        raise ValueError(f"Invalid XML content: {exc}") from exc

    return True


__all__ = ["Mapper", "MapperError", "MapperResult", "OutputFormat", "validate_mapper_result"]
