"""Factory for constructing a fully wired De-identification Pipeline."""

import logging

from openai import AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI, OpenAI

from .pipeline import RedactionPipeline
from .detectors.llm_detector import LLMDetector
from .extractors.pdf_extractor import PDFExtractor
from .redactors.pdf_redactor import PDFRedactor
from .synthesizer import SyntheticDataGenerator

logger = logging.getLogger(__name__)

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def build_pipeline(
    # Provider selection
    provider: str = "openai",
    # OpenAI settings
    openai_api_key: str = "",
    openai_model: str = "gpt-4o",
    openai_temperature: float = -1.0,
    # Azure OpenAI settings
    azure_endpoint: str = "",
    api_key: str = "",
    deployment_name: str = "",
    api_version: str = "2024-02-15-preview",
    # Groq settings
    groq_api_key: str = "",
    groq_model: str = "llama-3.3-70b-versatile",
    # Feature flags
    enable_ocr: bool = True,
    deidentification_mode: str = "placeholder",
) -> RedactionPipeline:
    """Build a RedactionPipeline wired with the configured LLM provider.

    deidentification_mode: "mask" | "placeholder" | "synthetic"
    """
    if provider == "azure":
        logger.info(
            "LLM provider: Azure OpenAI | endpoint: %s | deployment: %s | api_version: %s",
            azure_endpoint,
            deployment_name,
            api_version,
        )
        client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        async_client = AsyncAzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        model_name = deployment_name
    elif provider == "groq":
        logger.info(
            "LLM provider: Groq | base_url: %s | model: %s",
            _GROQ_BASE_URL,
            groq_model,
        )
        client = OpenAI(api_key=groq_api_key, base_url=_GROQ_BASE_URL)
        async_client = AsyncOpenAI(api_key=groq_api_key, base_url=_GROQ_BASE_URL)
        model_name = groq_model
    else:
        logger.info("LLM provider: OpenAI | model: %s", openai_model)
        client = OpenAI(api_key=openai_api_key)
        async_client = AsyncOpenAI(api_key=openai_api_key)
        model_name = openai_model

    synthesizer = None
    if deidentification_mode == "synthetic":
        synthesizer = SyntheticDataGenerator()

    # Resolve temperature: -1 means "omit" (use model default)
    temperature = openai_temperature if openai_temperature >= 0 else None
    logger.info(
        "Pipeline config: mode=%s | ocr=%s | temperature=%s",
        deidentification_mode,
        enable_ocr,
        temperature if temperature is not None else "model-default",
    )

    return RedactionPipeline(
        extractor=PDFExtractor(enable_ocr=enable_ocr),
        detector=LLMDetector(
            client=client,
            deployment_name=model_name,
            async_client=async_client,
            temperature=temperature,
        ),
        redactor=PDFRedactor(),
        synthesizer=synthesizer,
        mode=deidentification_mode,
    )
