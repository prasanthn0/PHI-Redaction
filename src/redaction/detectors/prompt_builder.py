"""Prompt building strategy for LLM-based HIPAA PHI detection."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from ..models.entities import PageContent


@dataclass
class PromptContext:
    """Everything needed for one LLM API call."""

    messages: List[dict]
    valid_categories: set


class BasePromptBuilder(ABC):
    """Interface for prompt construction strategies."""

    @abstractmethod
    def build(
        self,
        page: PageContent,
        categories: List[dict],
        ai_prompt: Optional[str] = None,
    ) -> PromptContext:
        """Build API messages for a single page."""


class DefaultPromptBuilder(BasePromptBuilder):
    """Builds the HIPAA PHI detection prompt from category definitions."""

    def build(
        self,
        page: PageContent,
        categories: List[dict],
        ai_prompt: Optional[str] = None,
    ) -> PromptContext:
        category_text_parts = []
        valid_categories: set = set()

        for cat in categories:
            cat_id = cat["category"]
            valid_categories.add(cat_id)

            part = f"{cat['display'].upper()} ({cat_id}): {cat['desc']}\n"
            part += f"Examples: {cat['example']}\n"
            part += "Subcategories:\n"
            for sub in cat.get("subcategories", []):
                part += (
                    f"  - {sub['display']} ({sub['subcategory']}): "
                    f"{sub['desc']} (e.g., {sub['example']})\n"
                )
            category_text_parts.append(part)

        category_text = "\n".join(category_text_parts)
        valid_category_ids = "|".join(valid_categories)

        system_prompt = f"""You are a HIPAA-compliant Protected Health Information (PHI) detector for medical documents.
Your task is to identify ALL Protected Health Information (PHI) that must be de-identified per the HIPAA Safe Harbor method (45 CFR § 164.514(b)(2)).

You are analyzing clinical notes, discharge summaries, lab reports, prescriptions, and other medical documents.

PHI CATEGORIES TO DETECT:
{category_text}

CRITICAL RULES — READ CAREFULLY:

1. IDENTIFY ALL PHI - every instance of protected information must be flagged
   - Patient names (full or partial), including relatives and employers
   - All dates more specific than year (birth dates, admission dates, service dates, etc.)
   - Phone numbers, fax numbers, email addresses
   - Social Security Numbers, Medical Record Numbers, Health Plan IDs
   - Geographic data smaller than a state (addresses, cities, ZIP codes)
   - Ages over 89 must be categorized as such

2. PRESERVE CLINICAL CONTEXT — these are NOT PHI and should NOT be flagged:
   - Medical diagnoses (e.g., "Type 2 Diabetes", "Hypertension")
   - Medications and dosages (e.g., "Metformin 500mg", "Lisinopril 10mg daily")
   - Lab values and vital signs (e.g., "BP 120/80", "HbA1c 7.2%")
   - Procedures and treatments (e.g., "appendectomy", "MRI of the brain")
   - Clinical observations (e.g., "patient appears alert and oriented")
   - Generic medical terms and abbreviations (e.g., "PRN", "BID", "CBC")
   - Hospital/facility names that are well-known institutions (keep for context)

3. SUGGEST APPROPRIATE REPLACEMENTS for each finding:
   - Names → [PATIENT_NAME], [PROVIDER_NAME], [RELATIVE_NAME]
   - Dates → [DATE], [DATE_OF_BIRTH], [ADMISSION_DATE], [DISCHARGE_DATE]
   - SSN → [SSN]
   - Phone → [PHONE_NUMBER]
   - Fax → [FAX_NUMBER]
   - Email → [EMAIL_ADDRESS]
   - MRN → [MEDICAL_RECORD_NUMBER]
   - Address → [ADDRESS]
   - ZIP code → [ZIP_CODE]
   - Age over 89 → [AGE_OVER_89]
   - Other identifiers → [IDENTIFIER]

4. Only identify text that EXACTLY appears in the document
5. Be precise — extract the exact text span, not paraphrased versions
6. Assign confidence scores: 0.9+ for clear PHI, 0.7-0.9 for likely PHI
7. When in doubt about whether something is PHI, flag it with a lower confidence

Respond with a JSON object in this exact format:
{{
  "findings": [
    {{
      "text": "exact text from document",
      "category": "{valid_category_ids}",
      "subcategory": "specific subcategory identifier from the list above",
      "confidence": 0.95,
      "rationale": "Brief explanation why this is PHI",
      "replacement": "[PLACEHOLDER_TAG] or synthetic replacement"
    }}
  ]
}}

If no PHI is found, respond with: {{"findings": []}}"""

        if ai_prompt:
            system_prompt += f"\n\nADDITIONAL INSTRUCTIONS:\n{ai_prompt}"

        ocr_note = ""
        if page.is_ocr:
            ocr_note = (
                "\n\nNOTE: This text was extracted via OCR from a scanned document. "
                "There may be OCR errors — be flexible with exact text matching but "
                "still identify any recognizable PHI patterns."
            )

        user_prompt = (
            f"Analyze this medical document page and identify ALL Protected Health "
            f"Information (PHI) that must be de-identified under HIPAA.\n\n"
            f"DOCUMENT TEXT (Page {page.page_number + 1}):\n"
            f"---\n{page.text}\n---{ocr_note}\n\n"
            f"Return findings as JSON."
        )

        return PromptContext(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            valid_categories=valid_categories,
        )
