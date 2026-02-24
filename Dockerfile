# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.in-project true

WORKDIR /build

# Copy dependency files first (for layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev dependencies in production)
RUN poetry install --no-root --no-interaction --no-ansi --only main || \
    poetry install --no-root --no-interaction --no-ansi --only main

# Verify critical imports
RUN poetry run python -c "import fitz; print('PyMuPDF OK')"
RUN poetry run python -c "import openai; print('OpenAI OK')"

# Stage 2: Runtime
FROM python:3.12-slim

# Install runtime dependencies including Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    ca-certificates \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Copy application code
COPY src/ ./src/
RUN find /app/src -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /app/src -name "*.pyc" -delete 2>/dev/null || true

# Create non-root user and storage directory
RUN useradd -m -u 1000 emplay && \
    mkdir -p /app/storage && \
    chown -R emplay:emplay /app

USER emplay

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Use tini as PID 1
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30"]
