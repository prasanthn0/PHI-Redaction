"""Pydantic schemas for the HIPAA de-identification API."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SubcategoryInput(BaseModel):
    subcategory: str
    display: str
    desc: str
    example: str


class CategoryInput(BaseModel):
    category: str
    display: str
    desc: str
    example: str
    subcategories: List[SubcategoryInput]


class CategoriesInput(BaseModel):
    sensitivity_categories: List[CategoryInput]


class ConfigInput(BaseModel):
    ai_prompt: Optional[str] = None
    language: Optional[str] = None
    confidence_threshold: Optional[int] = Field(None, ge=0, le=100)
    deidentification_mode: Optional[str] = None


class FindingResponse(BaseModel):
    section_id: str
    section_text: str
    page_number: int = Field(..., ge=1)
    subcategory: str
    category: str
    bbox: list = Field(default_factory=list)
    conf_score: int = Field(..., ge=0, le=100)
    rationale: str
    replacement: str = ""


class RedactionReportItem(BaseModel):
    category: str
    count: int = Field(..., ge=0)
    examples: List[str] = Field(default_factory=list)


class RedactionReport(BaseModel):
    total_findings: int
    total_redacted: int
    categories_found: List[RedactionReportItem] = Field(default_factory=list)
    processing_time_seconds: float
    ocr_pages: int = 0
    deidentification_mode: str = "placeholder"


class DeidentifyResponse(BaseModel):
    file_id: str
    status: str
    message: str
    original_filename: str = ""
    detected_phi: List[FindingResponse] = Field(default_factory=list)
    redaction_report: Optional[RedactionReport] = None


class DashboardCategorySummary(BaseModel):
    category: str
    display_name: str
    total_count: int
    percentage: float


class DashboardResponse(BaseModel):
    total_documents_processed: int
    total_phi_detected: int
    total_redactions_applied: int
    categories_summary: List[DashboardCategorySummary]
    recent_uploads: List[Dict] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    llm_provider: str = ""
    ocr_available: bool = False


class ReadyzResponse(BaseModel):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
