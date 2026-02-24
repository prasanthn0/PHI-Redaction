"""PDF text extraction using PyMuPDF with OCR fallback for scanned documents."""

import io
import logging
from typing import List

import fitz  # PyMuPDF

from .base import BaseExtractor
from ..models.entities import PageContent

logger = logging.getLogger(__name__)

# Minimum character count to consider a page as having usable text
_MIN_TEXT_LENGTH = 30


class PDFExtractor(BaseExtractor):
    """Extract text content from PDF files with OCR fallback.

    For each page:
    1. Attempt native text extraction (fast, accurate for digital PDFs).
    2. If text is too short (< 30 chars), fall back to OCR via Tesseract.

    This handles both born-digital PDFs and scanned/image-based documents.
    """

    def __init__(self, enable_ocr: bool = True):
        """
        Initialize the extractor.

        Args:
            enable_ocr: Whether to attempt OCR on pages with little/no text.
        """
        self.enable_ocr = enable_ocr
        self._ocr_available: bool | None = None

    def _check_ocr_available(self) -> bool:
        """Check if Tesseract OCR is available."""
        if self._ocr_available is not None:
            return self._ocr_available
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            self._ocr_available = True
            logger.info("Tesseract OCR is available")
        except Exception:
            self._ocr_available = False
            logger.warning("Tesseract OCR is not available — scanned PDFs will have limited text extraction")
        return self._ocr_available

    def extract(self, pdf_path: str) -> List[PageContent]:
        """
        Extract text from all pages of a PDF.

        For scanned/image-based pages, uses OCR via Tesseract if available.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            List of PageContent objects, one per page
        """
        doc = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            is_ocr = False

            # If native text extraction yields too little, try OCR
            if len(text.strip()) < _MIN_TEXT_LENGTH and self.enable_ocr:
                ocr_text = self._ocr_page(page)
                if ocr_text and len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    is_ocr = True
                    logger.info("Page %d: OCR extracted %d characters", page_num + 1, len(text))

            pages.append(
                PageContent(
                    page_number=page_num,
                    text=text,
                    width=page.rect.width,
                    height=page.rect.height,
                    is_ocr=is_ocr,
                )
            )

        doc.close()
        return pages

    def _ocr_page(self, page) -> str:
        """
        Run OCR on a PDF page using Tesseract.

        Renders the page to a high-DPI image and runs Tesseract on it.

        Args:
            page: A PyMuPDF page object.

        Returns:
            OCR-extracted text, or empty string on failure.
        """
        if not self._check_ocr_available():
            return ""

        try:
            import pytesseract
            from PIL import Image

            # Render page at 300 DPI for good OCR quality
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Run Tesseract OCR
            text = pytesseract.image_to_string(img, lang="eng")
            return text
        except Exception as e:
            logger.warning("OCR failed for page: %s", e)
            return ""

    def get_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF."""
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count


class ImageExtractor(BaseExtractor):
    """Extract text from image files (JPEG, PNG, TIFF) using OCR.

    Supports scanned doctor's notes and handwritten text recognition
    via Tesseract OCR.
    """

    def extract(self, image_path: str) -> List[PageContent]:
        """
        Extract text from an image file using OCR.

        Args:
            image_path: Path to the image file

        Returns:
            List containing a single PageContent object
        """
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(image_path)
            width, height = img.size

            # Run OCR
            text = pytesseract.image_to_string(img, lang="eng")

            return [
                PageContent(
                    page_number=0,
                    text=text,
                    width=float(width),
                    height=float(height),
                    is_ocr=True,
                )
            ]
        except ImportError:
            logger.error("pytesseract or Pillow not installed — cannot process images")
            return [PageContent(page_number=0, text="", width=0, height=0, is_ocr=True)]
        except Exception as e:
            logger.error("Image extraction failed: %s", e)
            return [PageContent(page_number=0, text="", width=0, height=0, is_ocr=True)]
