"""PPTX packaging writer facade."""

from __future__ import annotations

from svg2ooxml.io.pptx_batch_writer import PackageWriter
from svg2ooxml.io.pptx_streaming_writer import StreamingPackageWriter
from svg2ooxml.io.pptx_writer_base import _PackageWriterBase  # noqa: F401

__all__ = ["PackageWriter", "StreamingPackageWriter"]
