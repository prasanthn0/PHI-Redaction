"""Document text extraction module with OCR support."""

from .base import BaseExtractor
from .pdf_extractor import PDFExtractor, ImageExtractor

__all__ = ["BaseExtractor", "PDFExtractor", "ImageExtractor"]
