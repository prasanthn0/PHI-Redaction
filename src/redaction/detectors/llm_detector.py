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
        logger.info(
            "LLMDetector initialised | model: %s | async_client: %s | temperature: %s",
            deployment_name,
            "yes" if async_client is not None else "no (will use thread executor)",
            temperature if temperature is not None else "model-default",
        )

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
        logger.debug(
            "Calling LLM (sync) | model: %s | page: %d | text_length: %d chars",
            self.deployment_name,
            page.page_number,
            len(page.text),
        )
        try:
            response = self._call_api(ctx.messages)
            findings = self._parse_response(response, page, ctx.valid_categories)
            logger.debug(
                "LLM response received | page: %d | findings: %d",
                page.page_number,
                len(findings),
            )
            return findings
        except Exception as e:
            logger.warning(
                "LLM detection failed | model: %s | page: %d | error_type: %s | error: %s",
                self.deployment_name,
                page.page_number,
                type(e).__name__,
                e,
            )
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
        logger.debug("HTTP POST -> chat.completions | model: %s", self.deployment_name)
        response = self.client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content if response.choices else "<empty>"
        logger.debug("Raw LLM response (first 500 chars): %.500s", raw)
        return response

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
        logger.debug(
            "Calling LLM (async) | model: %s | page: %d | text_length: %d chars",
            self.deployment_name,
            page.page_number,
            len(page.text),
        )
        try:
            response = await self._call_api_async(ctx.messages)
            findings = self._parse_response(response, page, ctx.valid_categories)
            logger.debug(
                "LLM response received | page: %d | findings: %d",
                page.page_number,
                len(findings),
            )
            return findings
        except Exception as e:
            logger.warning(
                "Async LLM detection failed | model: %s | page: %d | error_type: %s | error: %s",
                self.deployment_name,
                page.page_number,
                type(e).__name__,
                e,
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
        logger.debug("HTTP POST -> chat.completions (async) | model: %s", self.deployment_name)
        response = await self.async_client.chat.completions.create(**kwargs)
        raw = response.choices[0].message.content if response.choices else "<empty>"
        logger.debug("Raw LLM response (first 500 chars): %.500s", raw)
        return response

    def _parse_response(self, response, page: PageContent, valid_categories: set) -> List[SensitiveFinding]:
        """Parse and validate the LLM JSON response into SensitiveFinding objects."""
        content = response.choices[0].message.content
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(
                "JSON parse error on LLM response | page: %d | error: %s | raw: %.300s",
                page.page_number,
                e,
                content,
            )
            return []

        raw_items = data.get("findings", [])
        logger.debug(
            "Parsing LLM findings | page: %d | raw_count: %d",
            page.page_number,
            len(raw_items),
        )

        findings = []
        for item in raw_items:
            item_category = item.get("category", "")
            if item_category not in valid_categories:
                logger.debug(
                    "Dropping finding — unknown category: %r | text: %.80r",
                    item_category,
                    item.get("text", ""),
                )
                continue
            if item.get("text", "") not in page.text:
                logger.debug(
                    "Dropping finding — text not found in page: %.80r",
                    item.get("text", ""),
                )
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
