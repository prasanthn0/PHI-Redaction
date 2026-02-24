"""Abstract base class for PDF redactors."""

from abc import ABC, abstractmethod
from typing import List

from ..models.entities import SensitiveFinding


class BaseRedactor(ABC):
    """Interface for document redactors."""

    @abstractmethod
    def apply_redactions(
        self,
        input_path: str,
        output_path: str,
        findings: List[SensitiveFinding],
    ) -> int:
        """
        Apply redactions to a document and write the result.

        Args:
            input_path: Path to the source document.
            output_path: Path for the redacted output.
            findings: Findings to redact (may be updated with bounding boxes).

        Returns:
            Number of redaction annotations applied.
        """
