"""Main HIPAA de-identification pipeline orchestrator."""

import logging
import time
from pathlib import Path
from typing import List, Optional

from .detectors.base import BaseDetector
from .extractors.base import BaseExtractor
from .redactors.base import BaseRedactor
from .models.entities import RedactionResult
from .synthesizer import SyntheticDataGenerator

logger = logging.getLogger(__name__)


class RedactionPipeline:
    """Orchestrates extract -> detect -> redact for HIPAA de-identification."""

    VALID_MODES = ("mask", "placeholder", "synthetic")

    def __init__(
        self,
        extractor: BaseExtractor,
        detector: BaseDetector,
        redactor: BaseRedactor,
        synthesizer: Optional[SyntheticDataGenerator] = None,
        mode: str = "placeholder",
    ):
        self.extractor = extractor
        self.detector = detector
        self.redactor = redactor
        self.synthesizer = synthesizer
        self.mode = mode if mode in self.VALID_MODES else "placeholder"

    def process(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        categories: Optional[List[dict]] = None,
        config: Optional[dict] = None,
    ) -> RedactionResult:
        """Run the full de-identification pipeline synchronously."""
        config = config or {}
        output_path = output_path or self._default_output_path(input_path)

        logger.info("Extracting text from %s...", input_path)
        pages = self.extractor.extract(input_path)
        logger.info("Found %d pages", len(pages))

        ocr_pages = sum(1 for p in pages if p.is_ocr)
        if ocr_pages:
            logger.info("%d pages processed with OCR", ocr_pages)

        logger.info("Detecting Protected Health Information...")
        findings = self.detector.detect(pages, categories, ai_prompt=config.get("ai_prompt"))
        logger.info("Found %d PHI items", len(findings))

        findings = self._apply_confidence_filter(findings, config)
        self._apply_mode(findings)

        logger.info("Applying de-identification redactions...")
        start_time = time.time()
        redacted_count = self.redactor.apply_redactions(input_path, output_path, findings)
        processing_time = time.time() - start_time
        logger.info("Applied %d redactions in %.2fs", redacted_count, processing_time)

        return RedactionResult(
            input_path=input_path,
            output_path=output_path,
            findings=findings,
            total_pages=len(pages),
            redacted_count=redacted_count,
            processing_time_seconds=processing_time,
            categories_requested=categories or [],
            ocr_pages=ocr_pages,
        )

    async def process_async(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        categories: Optional[List[dict]] = None,
        config: Optional[dict] = None,
    ) -> RedactionResult:
        """Run the full de-identification pipeline asynchronously."""
        config = config or {}
        output_path = output_path or self._default_output_path(input_path)

        logger.info("Extracting text from %s...", input_path)
        pages = self.extractor.extract(input_path)
        logger.info("Found %d pages", len(pages))

        ocr_pages = sum(1 for p in pages if p.is_ocr)
        if ocr_pages:
            logger.info("%d pages processed with OCR", ocr_pages)

        logger.info("Detecting Protected Health Information (async)...")
        findings = await self.detector.detect_async(
            pages, categories, ai_prompt=config.get("ai_prompt")
        )
        logger.info("Found %d PHI items", len(findings))

        findings = self._apply_confidence_filter(findings, config)
        self._apply_mode(findings)

        logger.info("Applying de-identification redactions...")
        start_time = time.time()
        redacted_count = self.redactor.apply_redactions(input_path, output_path, findings)
        processing_time = time.time() - start_time
        logger.info("Applied %d redactions in %.2fs", redacted_count, processing_time)

        return RedactionResult(
            input_path=input_path,
            output_path=output_path,
            findings=findings,
            total_pages=len(pages),
            redacted_count=redacted_count,
            processing_time_seconds=processing_time,
            categories_requested=categories or [],
            ocr_pages=ocr_pages,
        )

    def _apply_mode(self, findings):
        """Set finding.replacement according to the active mode.

        * mask        — clear replacement (PDFRedactor draws a black box)
        * placeholder — keep the [TAG] placeholders from the LLM
        * synthetic   — overwrite with SyntheticDataGenerator output
        """
        if self.mode == "mask":
            for f in findings:
                f.replacement = ""
        elif self.mode == "synthetic" and self.synthesizer:
            self.synthesizer.reset()
            for f in findings:
                f.replacement = self.synthesizer.generate(
                    f.category, f.subcategory, f.text
                )
        # "placeholder" — keep LLM-provided [TAG] values unchanged

    @staticmethod
    def _default_output_path(input_path: str) -> str:
        p = Path(input_path)
        return str(p.parent / f"{p.stem}_DEIDENTIFIED{p.suffix}")

    @staticmethod
    def _apply_confidence_filter(findings, config: dict):
        threshold = config.get("confidence_threshold")
        if threshold is None:
            return findings
        t = threshold / 100.0 if threshold > 1 else threshold
        filtered = [f for f in findings if f.confidence >= t]
        logger.info("After confidence filter (>= %.2f): %d items", t, len(filtered))
        return filtered
