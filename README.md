# HIPAA Medical De-identification System

Automated detection and removal of Protected Health Information (PHI) from medical documents for HIPAA compliance. Uses a FastAPI backend, Gradio UI, OpenAI-based LLM detection, Tesseract OCR for scanned documents, and Docker Compose for deployment.

## Features

- Detects all 18 HIPAA Safe Harbor identifiers via GPT-4o (or Azure OpenAI)
- OCR pipeline for scanned PDFs and images (JPEG, PNG, TIFF) via Tesseract
- Three de-identification modes:
  - **Mask** — solid black box over PHI (traditional redaction)
  - **Placeholder** — replaces PHI with semantic tags like `[PATIENT_NAME]`, `[DATE]`, `[SSN]`
  - **Synthetic** — generates realistic fake data to preserve clinical context
- Audit trail with a per-document redaction report
- Compliance dashboard with aggregate PHI detection statistics
- Before/after side-by-side comparison in the UI
- Single container (UI + API + OCR)

---

## Architecture

```
+------------------------------------------+
|       Single Container (:8000)           |
|                                          |
|  +------------------------------------+  |
|  |       Gradio UI (at /)             |  |
|  +----------------+-------------------+  |
|                   |                      |
|  +----------------v-------------------+  |
|  |   FastAPI Backend (at /api/v1/*)   |  |
|  +----------------+-------------------+  |
|                   |                      |
|  +----------------v-------------------+  |
|  |   De-identification Pipeline       |  |
|  |                                    |  |
|  |  1. Extract text (PyMuPDF)         |  |
|  |     + OCR fallback (Tesseract)     |  |
|  |  2. Detect PHI (LLM)               |  |
|  |  3. Synthesize fakes (optional)    |  |
|  |  4. Redact PDF (PyMuPDF)           |  |
|  +------------------------------------+  |
+------------------------------------------+
```

### File Structure

```
src/
  api/                        # FastAPI application
    main.py                   # Entry point, Gradio mount
    config.py                 # Settings (LLM provider, OCR, modes)
    rate_limit.py
    middleware.py
    logging_config.py
    models/schemas.py         # Request/response models
    routes/
      health.py               # /health, /healthz, /readyz
      redact.py               # /deidentify, /download, /dashboard
    storage/file_storage.py
  redaction/                  # Core pipeline
    pipeline.py               # Extract -> detect -> redact
    factory.py                # Wires pipeline to LLM provider
    synthesizer.py            # Synthetic data generation
    detectors/
      base.py
      llm_detector.py         # OpenAI / Azure LLM detection
      prompt_builder.py       # HIPAA prompt construction
    extractors/
      base.py
      pdf_extractor.py        # PyMuPDF + Tesseract OCR
    redactors/
      base.py
      pdf_redactor.py         # PDF redaction (black-box or synthetic overlay)
    models/entities.py        # PHI categories, findings, results
  ui/
    app.py                    # Gradio frontend (3 tabs)
evaluation/
  generate_benchmark.py       # Generate PDFs with known PHI
  run_benchmark.py            # Score pipeline: precision/recall/F1
docker-compose.yml
Dockerfile
.env.example
pyproject.toml
sample_data/
```

---

## Implementation Design

### Model Choice

GPT-4o via the OpenAI API. It handles structured JSON output well and recognises medical PHI in context. Azure OpenAI is also supported — switch with the `LLM_PROVIDER` env var.

### OCR Strategy

Two-tier extraction:

1. Native text extraction via PyMuPDF (fast, for digital PDFs).
2. Tesseract OCR fallback when a page has fewer than 30 characters of native text (scanned/image pages rendered at 300 DPI).

### De-identification Modes

| Mode | PDF Output | Use Case |
|------|-----------|----------|
| `mask` | Solid black box | Legal/regulatory submissions where no trace of PHI should remain |
| `placeholder` | Dark-grey box with white `[TAG]` text | Internal review — readers can see *what type* of PHI was removed |
| `synthetic` | White box with blue fake data | Research datasets — preserves clinical context with realistic fakes |

### Context Preservation

- The LLM prompt instructs the model to preserve medical terminology, diagnoses, medications, and lab values.
- Placeholder mode uses semantic tags (`[PATIENT_NAME]`, `[DATE_OF_BIRTH]`) so clinical meaning is retained.
- Synthetic mode generates consistent fake data per document (same original PHI always maps to the same replacement).

### UI

Gradio — Python-native, mounts directly onto FastAPI, no separate frontend build.

---

## Prerequisites

- **Docker** and **Docker Compose** (recommended — everything runs in a single container)
- Or for local development:
  - Python 3.10+
  - [Poetry](https://python-poetry.org/docs/#installation) (dependency manager)
  - Tesseract OCR
  - An OpenAI API key (or Azure OpenAI credentials)

---

## Quick Start (Docker)

```bash
git clone <repo-url>
cd hipaa-deidentification

# Create .env from the example and set your API key
cp .env.example .env
# Edit .env → set OPENAI_API_KEY=sk-...

# Build and start the container
docker compose up --build
```

The container bundles FastAPI + Gradio UI + Tesseract OCR in a single image.
On first build it installs all Python dependencies via Poetry inside the
Docker builder stage — no local Python setup needed.

| Service | URL |
|---------|-----|
| UI (Gradio) | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

To stop:

```bash
docker compose down
```

To rebuild after code changes:

```bash
docker compose up --build
```

### Usage Walkthrough

1. Open http://localhost:8000
2. Upload a medical PDF or image on the **De-identify** tab
3. Choose a mode (Mask, Placeholder, or Synthetic) and set the confidence threshold
4. Click **De-identify Document**
5. View the **Before / After** comparison side-by-side
6. Download the de-identified PDF
7. Check the **Redaction Report** tab for the audit trail
8. Visit the **Compliance Dashboard** tab for aggregated statistics

---

## Local Development (Poetry)

### 1. Install Poetry

If you don't have Poetry installed yet:

```bash
# Windows (PowerShell)
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Linux / macOS
curl -sSL https://install.python-poetry.org | python3 -
```

Verify:

```bash
poetry --version
```

### 2. Install dependencies

```bash
cd hipaa-deidentification

# Install all project dependencies into a virtual environment
poetry install
```

This reads `pyproject.toml`, creates a `.venv` inside the project (or in
Poetry's cache), and installs every dependency listed under
`[tool.poetry.dependencies]`.

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env → set OPENAI_API_KEY=sk-...
```

### 4. Run the application

```bash
poetry run python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

This starts the FastAPI server with hot-reload enabled. Open
http://127.0.0.1:8000 for the Gradio UI, or http://127.0.0.1:8000/docs
for the Swagger API explorer.

Alternatively, activate the Poetry shell first and then run uvicorn
directly:

```bash
poetry shell
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Install Tesseract (for OCR support)

- **Windows**: https://github.com/UB-Mannheim/tesseract/wiki
- **macOS**: `brew install tesseract`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr tesseract-ocr-eng`

---

## API Endpoints

### `POST /api/v1/deidentify`

Upload a medical document for PHI detection and redaction.

Request (multipart/form-data):
- `file` — PDF or image
- `config_json` (optional) — `{"confidence_threshold": 70, "deidentification_mode": "mask|placeholder|synthetic"}`

Response:
```json
{
  "file_id": "abc123def456",
  "status": "completed",
  "original_filename": "clinical_notes.pdf",
  "detected_phi": [
    {
      "section_text": "John Smith",
      "page_number": 1,
      "category": "patient_name",
      "subcategory": "full_name",
      "conf_score": 95,
      "replacement": "[PATIENT_NAME]"
    }
  ],
  "redaction_report": {
    "total_findings": 12,
    "total_redacted": 12,
    "processing_time_seconds": 4.52
  }
}
```

### `GET /api/v1/download/{file_id}`

Download the de-identified PDF.

### `GET /api/v1/dashboard`

Aggregated PHI detection statistics.

### Health Checks

```
GET /health    # Full health info
GET /healthz   # Liveness probe
GET /readyz    # Readiness probe
```

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | No | `openai` | `openai` or `azure` |
| `OPENAI_API_KEY` | Yes* | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o` | Model name |
| `AZURE_OPENAI_ENDPOINT` | Yes** | — | Azure endpoint |
| `AZURE_OPENAI_API_KEY` | Yes** | — | Azure API key |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes** | — | Azure deployment |
| `DEIDENTIFICATION_MODE` | No | `placeholder` | `mask`, `placeholder`, or `synthetic` |
| `OCR_ENABLED` | No | `true` | Enable Tesseract OCR |
| `MAX_FILE_SIZE_MB` | No | `50` | Max upload size |
| `STORAGE_DIR` | No | `/tmp/hipaa-deidentification-storage` | Storage directory |
| `CORS_ORIGINS` | No | `*` | Allowed CORS origins |
| `RATE_LIMIT` | No | `100/minute` | API rate limit |
| `LOG_LEVEL` | No | `INFO` | Logging level |

\* Required when `LLM_PROVIDER=openai`
\** Required when `LLM_PROVIDER=azure`

---

## Bonus Features

### Synthetic Data Generation

The "synthetic" mode overlays realistic fake data onto the PDF instead
of blacking out or tagging PHI:

- Fake patient names, addresses, phone numbers, SSNs, MRNs, etc.
- Date shifting (random offset from the original date).
- Consistent mapping within a document — the same original PHI always maps
  to the same synthetic replacement.
- Toggle via the UI radio button (mask / placeholder / synthetic) or the
  `DEIDENTIFICATION_MODE` env var.

Visual output per mode:
- **Mask** — solid black box
- **Placeholder** — dark-grey box, white monospace `[TAG]` text
- **Synthetic** — white box, blue replacement text

### Handwritten Text Recognition

The OCR pipeline uses Tesseract for both printed and handwritten text.
Pages are rendered at 300 DPI for optimal recognition quality before
OCR extraction.

### Compliance Dashboard

The third tab in the Gradio UI shows:

- Total documents processed, total PHI detected, total redactions applied.
- Breakdown by PHI category with counts and percentages.
- Recent upload history with timestamps.

The dashboard auto-refreshes after each document is processed.

---

## Evaluation / Benchmarking

An evaluation suite measures detection accuracy against ground-truth
medical PDFs:

```bash
# Generate benchmark PDFs with known PHI
poetry run python -m evaluation.generate_benchmark --count 10

# Run the pipeline and compute precision / recall / F1
poetry run python -m evaluation.run_benchmark
```

Results are saved to `evaluation/data/benchmark_results.json` with
per-document and per-category breakdowns.

---

## Testing

```bash
poetry install                        # includes dev dependencies by default
poetry run pytest -m "not llm"        # skip tests requiring API keys
poetry run pytest                     # all tests (needs valid key in .env)
poetry run pytest --cov=src           # with coverage
```

---

## License

This project is provided for assessment purposes.
