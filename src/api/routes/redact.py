"""HIPAA de-identification endpoints."""

import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from starlette.requests import Request
from starlette.responses import FileResponse

from ..config import get_settings
from ..rate_limit import limiter
from ..models.schemas import (
    CategoriesInput,
    ConfigInput,
    DashboardCategorySummary,
    DashboardResponse,
    DeidentifyResponse,
    ErrorResponse,
    FindingResponse,
    RedactionReport,
    RedactionReportItem,
)
from ..storage.file_storage import file_storage

from redaction.factory import build_pipeline
from redaction.models.entities import DEFAULT_CATEGORY_DEFINITIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["De-identification"])

_processing_history: list[dict] = []


def _build_redaction_report(findings, redacted_count, processing_time, ocr_pages, mode) -> RedactionReport:
    by_category = defaultdict(list)
    for f in findings:
        cat = f.category if isinstance(f.category, str) else f.category
        text = f.text if len(f.text) <= 8 else f.text[:6] + "..."
        by_category[cat].append(text)

    categories_found = [
        RedactionReportItem(
            category=cat,
            count=len(examples),
            examples=examples[:3],
        )
        for cat, examples in by_category.items()
    ]

    return RedactionReport(
        total_findings=len(findings),
        total_redacted=redacted_count,
        categories_found=categories_found,
        processing_time_seconds=round(processing_time, 2),
        ocr_pages=ocr_pages,
        deidentification_mode=mode,
    )


@router.post(
    "/deidentify",
    response_model=DeidentifyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
    },
    summary="Upload and de-identify a medical document",
)
@limiter.limit("100/minute")
async def deidentify_document(
    request: Request,
    file: UploadFile = File(...),
    config_json: Optional[str] = Form(None),
    categories_json: Optional[str] = Form(None),
) -> DeidentifyResponse:
    settings = get_settings()
    file_id = str(uuid.uuid4())[:12]
    original_filename = file.filename or "document.pdf"

    config = {}
    if config_json:
        try:
            parsed = json.loads(config_json)
            config_input = ConfigInput(**parsed)
            if config_input.ai_prompt:
                config["ai_prompt"] = config_input.ai_prompt
            if config_input.language:
                config["language"] = config_input.language
            if config_input.confidence_threshold is not None:
                config["confidence_threshold"] = config_input.confidence_threshold
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid config_json")

    categories = None
    if categories_json:
        try:
            parsed = json.loads(categories_json)
            cat_input = CategoriesInput(**parsed)
            categories = [
                {
                    "category": cat.category,
                    "display": cat.display,
                    "desc": cat.desc,
                    "example": cat.example,
                    "subcategories": [
                        {"subcategory": s.subcategory, "display": s.display, "desc": s.desc, "example": s.example}
                        for s in cat.subcategories
                    ],
                }
                for cat in cat_input.sensitivity_categories
            ]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid categories_json")

    upload_dir = file_storage.downloads_dir
    upload_path = upload_dir / f"{file_id}_{original_filename}"

    try:
        contents = await file.read()
        if len(contents) > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed size of {settings.max_file_size_mb}MB.",
            )
        upload_path.write_bytes(contents)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save uploaded file: {e}")

    output_path, _ = file_storage.get_output_paths(file_id)
    deidentification_mode = settings.deidentification_mode
    if config_json:
        try:
            parsed = json.loads(config_json)
            if "deidentification_mode" in parsed:
                deidentification_mode = parsed["deidentification_mode"]
        except Exception:
            pass

    try:
        pipeline = build_pipeline(
            provider=settings.llm_provider,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_model,
            openai_temperature=settings.openai_temperature,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            deployment_name=settings.azure_openai_deployment_name,
            api_version=settings.azure_openai_api_version,
            enable_ocr=settings.ocr_enabled,
            deidentification_mode=deidentification_mode,
        )
        result = await pipeline.process_async(
            input_path=str(upload_path),
            output_path=str(output_path),
            categories=categories,
            config=config if config else None,
        )

        findings_response = [
            FindingResponse(
                section_id=f.finding_id,
                section_text=f.text,
                page_number=f.page_number + 1,
                subcategory=f.subcategory,
                category=f.category if isinstance(f.category, str) else f.category.value,
                bbox=f.bounding_boxes[0].to_dict() if f.bounding_boxes else [],
                conf_score=int(f.confidence * 100),
                rationale=f.rationale,
                replacement=f.replacement,
            )
            for f in result.findings
        ]

        report = _build_redaction_report(
            result.findings,
            result.redacted_count,
            result.processing_time_seconds,
            result.ocr_pages,
            deidentification_mode,
        )

        _processing_history.append({
            "file_id": file_id,
            "filename": original_filename,
            "total_findings": len(result.findings),
            "total_redacted": result.redacted_count,
            "categories": {f.category: 0 for f in result.findings},
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
        })
        for f in result.findings:
            cat = f.category if isinstance(f.category, str) else f.category.value
            _processing_history[-1]["categories"][cat] = _processing_history[-1]["categories"].get(cat, 0) + 1

        return DeidentifyResponse(
            file_id=file_id,
            status="completed",
            message="De-identification completed successfully.",
            original_filename=original_filename,
            detected_phi=findings_response,
            redaction_report=report,
        )

    except Exception as e:
        logger.exception("De-identification failed for file_id=%s", file_id)
        return DeidentifyResponse(
            file_id=file_id,
            status="failed",
            message=f"De-identification failed: {e}",
            original_filename=original_filename,
            detected_phi=[],
            redaction_report=None,
        )
    finally:
        if upload_path.exists():
            upload_path.unlink(missing_ok=True)


@router.get(
    "/download/{file_id}",
    summary="Download de-identified document",
    responses={404: {"model": ErrorResponse}},
)
async def download_deidentified(file_id: str):
    output_path, _ = file_storage.get_output_paths(file_id)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail=f"De-identified document not found for file_id: {file_id}")
    return FileResponse(
        path=str(output_path),
        filename=f"{file_id}_deidentified.pdf",
        media_type="application/pdf",
    )


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Compliance dashboard",
)
async def compliance_dashboard() -> DashboardResponse:
    total_docs = len(_processing_history)
    total_phi = sum(h["total_findings"] for h in _processing_history)
    total_redacted = sum(h["total_redacted"] for h in _processing_history)

    category_counts = defaultdict(int)
    for h in _processing_history:
        for cat, count in h.get("categories", {}).items():
            category_counts[cat] += count

    display_names = {c["category"]: c["display"] for c in DEFAULT_CATEGORY_DEFINITIONS}

    categories_summary = []
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        pct = (count / total_phi * 100) if total_phi > 0 else 0
        categories_summary.append(
            DashboardCategorySummary(
                category=cat,
                display_name=display_names.get(cat, cat),
                total_count=count,
                percentage=round(pct, 1),
            )
        )

    recent = _processing_history[-10:][::-1]

    return DashboardResponse(
        total_documents_processed=total_docs,
        total_phi_detected=total_phi,
        total_redactions_applied=total_redacted,
        categories_summary=categories_summary,
        recent_uploads=recent,
    )
