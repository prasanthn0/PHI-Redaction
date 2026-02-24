"""PDF redaction using PyMuPDF."""

from typing import List

import fitz  # PyMuPDF

from .base import BaseRedactor
from ..models.entities import BoundingBox, SensitiveFinding


class PDFRedactor(BaseRedactor):
    """Apply permanent redactions to PDF files.

    Three visual styles depending on ``finding.replacement``:

    * **mask** — replacement is empty → solid black box.
    * **placeholder** — replacement starts with ``[`` (e.g. ``[PATIENT_NAME]``)
      → dark-grey box with white monospace tag text.
    * **synthetic** — any other non-empty replacement → white box with
      blue replacement text.
    """

    def __init__(self, fill_color: tuple = (0, 0, 0)):
        self.fill_color = fill_color

    def apply_redactions(
        self,
        input_path: str,
        output_path: str,
        findings: List[SensitiveFinding],
    ) -> int:
        """Apply redactions to a PDF and save to a new file."""
        doc = fitz.open(input_path)
        redaction_count = 0

        findings_by_page: dict[int, List[SensitiveFinding]] = {}
        for finding in findings:
            findings_by_page.setdefault(finding.page_number, []).append(finding)

        for page_num, page_findings in findings_by_page.items():
            if page_num >= len(doc):
                continue

            page = doc[page_num]

            for finding in page_findings:
                text_instances = page.search_for(finding.text)

                if not text_instances:
                    normalized_text = " ".join(finding.text.split())
                    text_instances = page.search_for(normalized_text)

                bboxes = [BoundingBox.from_rect(rect) for rect in text_instances]
                finding.bounding_boxes = bboxes

                if len(bboxes) > 1:
                    y_positions = set(round(bb.y0, 0) for bb in bboxes)
                    finding.is_multiline = len(y_positions) > 1
                elif len(bboxes) == 1:
                    height = bboxes[0].y1 - bboxes[0].y0
                    finding.is_multiline = height > 20

                for rect in text_instances:
                    self._add_annot(page, rect, finding.replacement)
                    redaction_count += 1

            page.apply_redactions()

        doc.save(output_path)
        doc.close()
        return redaction_count

    def _add_annot(self, page, rect, replacement: str) -> None:
        """Add a single redaction annotation in the appropriate style."""
        if not replacement:
            # Mask mode: solid black box
            page.add_redact_annot(rect, fill=self.fill_color)
            return

        fontsize = self._fit_fontsize(rect, replacement)

        if replacement.startswith("["):
            # Placeholder mode: dark background, white monospace tag
            page.add_redact_annot(
                rect,
                text=replacement,
                fontname="cour",
                fontsize=fontsize,
                fill=(0.15, 0.15, 0.22),
                text_color=(1, 1, 1),
            )
        else:
            # Synthetic mode: white background, blue text
            page.add_redact_annot(
                rect,
                text=replacement,
                fontname="helv",
                fontsize=fontsize,
                fill=(1, 1, 1),
                text_color=(0.1, 0.1, 0.6),
            )

    @staticmethod
    def _fit_fontsize(rect, text: str, max_size: float = 11.0, min_size: float = 5.0) -> float:
        """Pick a font size that fits *text* inside *rect* width."""
        width = rect.x1 - rect.x0
        height = rect.y1 - rect.y0
        if not text:
            return max_size
        estimated = min(width / (len(text) * 0.5), height * 0.9)
        return max(min(estimated, max_size), min_size)

