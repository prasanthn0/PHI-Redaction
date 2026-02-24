"""LLM-based PHI detection using OpenAI (or Azure OpenAI)."""

import asyncio
import json
import logging
from typing import List, Optional

import openai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .base import BaseDetector
from .prompt_builder import BasePromptBuilder, DefaultPromptBuilder
from ..models.entities import (
    DEFAULT_CATEGORY_DEFINITIONS,
    PageContent,
    SensitiveFinding,
)

logger = logging.getLogger(__name__)

# Retry on transient OpenAI errors; do not retry auth or bad-request errors.
_RETRYABLE = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)

_retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)


class LLMDetector(BaseDetector):
    """Detect PHI using an LLM (OpenAI or Azure OpenAI)."""

    def __init__(
        self,
        client,
        deployment_name: str,
        prompt_builder: Optional[BasePromptBuilder] = None,
        async_client=None,
        temperature: Optional[float] = None,
    ):
        self.client = client
        self.deployment_name = deployment_name
        self.prompt_builder = prompt_builder or DefaultPromptBuilder()
        self.async_client = async_client
        self.temperature = temperature

    def detect(
        self,
        pages: List[PageContent],
        categories: Optional[List[dict]] = None,
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """Detect PHI across pages (sequential)."""
        if categories is None:
            categories = DEFAULT_CATEGORY_DEFINITIONS

        all_findings: List[SensitiveFinding] = []
        for page in pages:
            if not page.text.strip():
                continue
            all_findings.extend(self._detect_page(page, categories, ai_prompt))

        return all_findings

    def _detect_page(
        self,
        page: PageContent,
        categories: List[dict],
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """Run detection on a single page (sync)."""
        ctx = self.prompt_builder.build(page, categories, ai_prompt)
        try:
            response = self._call_api(ctx.messages)
            return self._parse_response(response, page, ctx.valid_categories)
        except Exception as e:
            logger.warning("LLM detection failed for page %d: %s", page.page_number, e)
            return []

    @_retry_policy
    def _call_api(self, messages: List[dict]):
        """Call OpenAI synchronously with retry on transient errors."""
        kwargs = dict(
            model=self.deployment_name,
            messages=messages,
            response_format={"type": "json_object"},
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return self.client.chat.completions.create(**kwargs)

    async def detect_async(
        self,
        pages: List[PageContent],
        categories: Optional[List[dict]] = None,
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """Detect PHI across pages concurrently."""
        if categories is None:
            categories = DEFAULT_CATEGORY_DEFINITIONS

        if self.async_client is None:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self.detect, pages, categories, ai_prompt
            )

        non_empty = [p for p in pages if p.text.strip()]
        results = await asyncio.gather(
            *[self._detect_page_async(p, categories, ai_prompt) for p in non_empty],
            return_exceptions=True,
        )

        all_findings: List[SensitiveFinding] = []
        for page, result in zip(non_empty, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Async LLM detection failed for page %d: %s",
                    page.page_number,
                    result,
                )
            else:
                all_findings.extend(result)

        return all_findings

    async def _detect_page_async(
        self,
        page: PageContent,
        categories: List[dict],
        ai_prompt: Optional[str] = None,
    ) -> List[SensitiveFinding]:
        """Run detection on a single page (async)."""
        ctx = self.prompt_builder.build(page, categories, ai_prompt)
        try:
            response = await self._call_api_async(ctx.messages)
            return self._parse_response(response, page, ctx.valid_categories)
        except Exception as e:
            logger.warning(
                "Async LLM detection failed for page %d: %s", page.page_number, e
            )
            return []

    @_retry_policy
    async def _call_api_async(self, messages: List[dict]):
        """Call OpenAI asynchronously with retry on transient errors."""
        kwargs = dict(
            model=self.deployment_name,
            messages=messages,
            response_format={"type": "json_object"},
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        return await self.async_client.chat.completions.create(**kwargs)

    def _parse_response(self, response, page: PageContent, valid_categories: set) -> List[SensitiveFinding]:
        """Parse and validate the LLM JSON response into SensitiveFinding objects."""
        content = response.choices[0].message.content
        data = json.loads(content)

        findings = []
        for item in data.get("findings", []):
            item_category = item.get("category", "")
            if item_category not in valid_categories:
                continue
            if item.get("text", "") not in page.text:
                continue

            raw_confidence = float(item.get("confidence", 0.8))
            confidence = max(0.0, min(1.0, raw_confidence))

            # Get the replacement suggestion from the LLM
            replacement = item.get("replacement", "")
            if not replacement:
                # Fallback to placeholder based on category
                replacement = self._default_placeholder(item_category)

            findings.append(
                SensitiveFinding(
                    text=item["text"],
                    category=item_category,
                    subcategory=item.get("subcategory", "unknown"),
                    page_number=page.page_number,
                    confidence=confidence,
                    rationale=item.get("rationale", ""),
                    replacement=replacement,
                )
            )

        return findings

    @staticmethod
    def _default_placeholder(category: str) -> str:
        """Return a default placeholder tag for a given PHI category."""
        placeholders = {
            "patient_name": "[PATIENT_NAME]",
            "date": "[DATE]",
            "phone_number": "[PHONE_NUMBER]",
            "fax_number": "[FAX_NUMBER]",
            "email_address": "[EMAIL_ADDRESS]",
            "ssn": "[SSN]",
            "medical_record_number": "[MEDICAL_RECORD_NUMBER]",
            "health_plan_number": "[HEALTH_PLAN_NUMBER]",
            "account_number": "[ACCOUNT_NUMBER]",
            "license_number": "[LICENSE_NUMBER]",
            "geographic_data": "[ADDRESS]",
            "age_over_89": "[AGE_OVER_89]",
            "device_id": "[DEVICE_ID]",
            "web_url": "[URL]",
            "ip_address": "[IP_ADDRESS]",
        }
        return placeholders.get(category, "[REDACTED]")
