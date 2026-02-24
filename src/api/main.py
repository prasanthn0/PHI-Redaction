"""FastAPI application for HIPAA Medical De-identification Service."""

import logging
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version, PackageNotFoundError

import gradio as gr
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import get_settings, load_settings
from .logging_config import setup_logging
from .middleware import RequestIDMiddleware
from .rate_limit import limiter
from .routes import health_router, redact_router

logger = logging.getLogger(__name__)


def _get_version() -> str:
    try:
        return pkg_version("hipaa-deidentification")
    except PackageNotFoundError:
        return "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    setup_logging(log_level=settings.log_level, log_format=settings.log_format)
    logger.info("Starting HIPAA De-identification API")
    logger.info("LLM provider=%s, mode=%s, ocr=%s", settings.llm_provider, settings.deidentification_mode, settings.ocr_enabled)
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="HIPAA Medical De-identification API",
    description=(
        "Detects and removes Protected Health Information (PHI) "
        "from medical documents per the HIPAA Safe Harbor method."
    ),
    version=_get_version(),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

settings = get_settings()
allow_all = settings.cors_origins_list == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=not allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred.",
            "detail": str(exc) if logger.level <= logging.DEBUG else None,
        },
    )


app.include_router(health_router)
app.include_router(redact_router)

from ui.app import create_ui

gradio_app = create_ui()
app = gr.mount_gradio_app(app, gradio_app, path="/")


def main():
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
