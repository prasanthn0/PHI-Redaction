"""Health check endpoints."""

import tempfile
from datetime import datetime
from importlib.metadata import version as pkg_version, PackageNotFoundError
from pathlib import Path

from fastapi import APIRouter

from ..config import get_settings
from ..models.schemas import HealthResponse, ReadyzResponse

router = APIRouter(tags=["Health"])


def _safe_version() -> str:
    try:
        return pkg_version("hipaa-deidentification")
    except PackageNotFoundError:
        return "1.0.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check if the service is running and healthy.",
)
async def health_check() -> HealthResponse:
    """Return service health status."""
    settings = get_settings()

    # Check if OCR is available
    ocr_available = False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        ocr_available = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        version=_safe_version(),
        timestamp=datetime.utcnow(),
        llm_provider=settings.llm_provider,
        ocr_available=ocr_available,
    )


@router.get(
    "/healthz",
    summary="Liveness probe",
    description="Liveness probe for container orchestrators.",
)
async def liveness() -> dict:
    """Return liveness status — no dependency checks."""
    return {"status": "alive"}


@router.get(
    "/readyz",
    response_model=ReadyzResponse,
    summary="Readiness probe",
    description="Readiness probe that checks critical dependencies.",
    responses={503: {"description": "Service not ready"}},
)
async def readiness() -> ReadyzResponse:
    """Check if the service is ready to accept traffic."""
    settings = get_settings()
    checks: dict[str, str] = {}
    all_ok = True

    # Check filesystem writability
    try:
        storage = Path(settings.storage_dir)
        storage.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=storage, delete=True):
            pass
        checks["filesystem"] = "ok"
    except Exception as e:
        checks["filesystem"] = f"error: {e}"
        all_ok = False

    # Check LLM configuration
    if settings.llm_provider == "openai":
        if settings.openai_api_key:
            checks["llm_config"] = "ok"
        else:
            checks["llm_config"] = "error: OPENAI_API_KEY not set"
            all_ok = False
    elif settings.llm_provider == "azure":
        if settings.azure_openai_api_key and settings.azure_openai_endpoint:
            checks["llm_config"] = "ok"
        else:
            checks["llm_config"] = "error: Azure OpenAI credentials not set"
            all_ok = False

    from fastapi.responses import JSONResponse

    response = ReadyzResponse(
        status="ready" if all_ok else "not_ready",
        checks=checks,
    )

    if not all_ok:
        return JSONResponse(status_code=503, content=response.model_dump())

    return response
