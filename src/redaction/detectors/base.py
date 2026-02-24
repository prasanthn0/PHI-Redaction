"""Abstract base class for sensitive information detectors."""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models.entities import PageContent, SensitiveFinding


class BaseDetector(ABC):
    """Interface for sensitive information detectors."""

    @abstractmethod
    def detect(
        self,
        pages: List[PageContent],
        categories: Optional[List[dict]] = None,
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """
        Detect sensitive information across a list of pages (synchronous).

        Args:
            pages: Extracted page content to analyse.
            categories: Caller-supplied sensitivity categories. Falls back
                to implementation defaults when None.
            ai_prompt: Optional additional instructions for the detector.

        Returns:
            List of SensitiveFinding objects detected across all pages.
        """

    async def detect_async(
        self,
        pages: List[PageContent],
        categories: Optional[List[dict]] = None,
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """
        Detect sensitive information across pages (asynchronous).

        Default implementation runs ``detect`` in a thread-pool executor so
        the event loop is never blocked. Subclasses may override this with a
        fully async implementation (e.g., concurrent per-page API calls).

        Args:
            pages: Extracted page content to analyse.
            categories: Caller-supplied sensitivity categories.
            ai_prompt: Optional additional instructions for the detector.

        Returns:
            List of SensitiveFinding objects detected across all pages.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.detect, pages, categories, ai_prompt
        )
