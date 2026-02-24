"""Abstract base class for document extractors."""

from abc import ABC, abstractmethod
from typing import List

from ..models.entities import PageContent


class BaseExtractor(ABC):
    """Interface for document text extractors.

    Supports PDF documents, scanned PDFs (via OCR), and image files.
    """

    @abstractmethod
    def extract(self, file_path: str) -> List[PageContent]:
        """
        Extract text content from a document.

        Args:
            file_path: Path to the source document (PDF or image).

        Returns:
            List of PageContent objects, one per page.
        """
