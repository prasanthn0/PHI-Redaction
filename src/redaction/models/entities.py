"""Data models for the HIPAA medical de-identification pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import uuid


class PHICategory(Enum):
    """HIPAA Safe Harbor de-identification categories (18 identifiers)."""

    PATIENT_NAME = "patient_name"
    DATE = "date"
    PHONE_NUMBER = "phone_number"
    FAX_NUMBER = "fax_number"
    EMAIL_ADDRESS = "email_address"
    SSN = "ssn"
    MEDICAL_RECORD_NUMBER = "medical_record_number"
    HEALTH_PLAN_NUMBER = "health_plan_number"
    ACCOUNT_NUMBER = "account_number"
    LICENSE_NUMBER = "license_number"
    VEHICLE_ID = "vehicle_id"
    DEVICE_ID = "device_id"
    WEB_URL = "web_url"
    IP_ADDRESS = "ip_address"
    BIOMETRIC_ID = "biometric_id"
    PHOTO = "photo"
    GEOGRAPHIC_DATA = "geographic_data"
    AGE_OVER_89 = "age_over_89"


# Default HIPAA PHI category definitions used when caller omits categories
DEFAULT_CATEGORY_DEFINITIONS = [
    {
        "category": "patient_name",
        "display": "Patient Names",
        "desc": "Full or partial names of patients, relatives, employers, or household members",
        "example": "John Smith, Mary O'Brien, Dr. Sarah Johnson",
        "subcategories": [
            {"subcategory": "full_name", "display": "Full Name", "desc": "A person's full name", "example": "John Smith"},
            {"subcategory": "first_name", "display": "First Name", "desc": "First or given name of a person", "example": "John, Sarah"},
            {"subcategory": "last_name", "display": "Last Name", "desc": "Last or family name of a person", "example": "Smith, Johnson"},
            {"subcategory": "provider_name", "display": "Provider Name", "desc": "Names of healthcare providers, doctors, nurses", "example": "Dr. Sarah Johnson, Nurse Williams"},
        ],
    },
    {
        "category": "date",
        "display": "Dates",
        "desc": "All dates (except year) directly related to an individual including birth date, admission date, discharge date, date of death, and all ages over 89",
        "example": "01/15/1990, March 3 2024, DOB: 05/22/1985",
        "subcategories": [
            {"subcategory": "date_of_birth", "display": "Date of Birth", "desc": "Patient or individual date of birth", "example": "DOB: 01/15/1990"},
            {"subcategory": "admission_date", "display": "Admission Date", "desc": "Hospital or facility admission date", "example": "Admitted: 03/15/2024"},
            {"subcategory": "discharge_date", "display": "Discharge Date", "desc": "Hospital or facility discharge date", "example": "Discharged: 03/20/2024"},
            {"subcategory": "date_of_service", "display": "Date of Service", "desc": "Date when medical service was provided", "example": "Visit date: 02/10/2024"},
            {"subcategory": "date_of_death", "display": "Date of Death", "desc": "Date of death of a patient", "example": "DOD: 01/05/2024"},
            {"subcategory": "other_date", "display": "Other Date", "desc": "Any other date directly related to an individual", "example": "Surgery scheduled for 04/01/2024"},
        ],
    },
    {
        "category": "phone_number",
        "display": "Phone Numbers",
        "desc": "Telephone numbers including home, work, mobile, and pager numbers",
        "example": "(555) 123-4567, 555-987-6543",
        "subcategories": [
            {"subcategory": "phone", "display": "Phone Number", "desc": "Any telephone number", "example": "(555) 123-4567"},
        ],
    },
    {
        "category": "fax_number",
        "display": "Fax Numbers",
        "desc": "Fax numbers",
        "example": "Fax: (555) 123-4568",
        "subcategories": [
            {"subcategory": "fax", "display": "Fax Number", "desc": "Any fax number", "example": "Fax: (555) 123-4568"},
        ],
    },
    {
        "category": "email_address",
        "display": "Email Addresses",
        "desc": "Electronic mail addresses",
        "example": "patient@email.com, dr.smith@hospital.org",
        "subcategories": [
            {"subcategory": "email", "display": "Email Address", "desc": "Any email address", "example": "john.doe@email.com"},
        ],
    },
    {
        "category": "ssn",
        "display": "Social Security Numbers",
        "desc": "Social Security numbers",
        "example": "123-45-6789, SSN: 987654321",
        "subcategories": [
            {"subcategory": "social_security", "display": "SSN", "desc": "Social Security Number", "example": "123-45-6789"},
        ],
    },
    {
        "category": "medical_record_number",
        "display": "Medical Record Numbers",
        "desc": "Medical record numbers and health-related identifiers",
        "example": "MRN: 12345678, Patient ID: A987654",
        "subcategories": [
            {"subcategory": "mrn", "display": "Medical Record Number", "desc": "Medical record or patient ID number", "example": "MRN: 12345678"},
        ],
    },
    {
        "category": "health_plan_number",
        "display": "Health Plan Beneficiary Numbers",
        "desc": "Health plan beneficiary numbers and insurance IDs",
        "example": "Insurance ID: XYZ123456789, Plan #: HP98765",
        "subcategories": [
            {"subcategory": "insurance_id", "display": "Health Insurance ID", "desc": "Health plan or insurance ID", "example": "Insurance ID: XYZ123456789"},
        ],
    },
    {
        "category": "account_number",
        "display": "Account Numbers",
        "desc": "Financial account numbers including bank accounts and billing accounts",
        "example": "Account #: 987654321, Billing: AC-12345",
        "subcategories": [
            {"subcategory": "account", "display": "Account Number", "desc": "Financial or billing account number", "example": "Account #: 987654321"},
        ],
    },
    {
        "category": "license_number",
        "display": "Certificate/License Numbers",
        "desc": "Certificate or license numbers including driver's license, professional licenses",
        "example": "DL: S12345678, License #: MD-98765",
        "subcategories": [
            {"subcategory": "license", "display": "License Number", "desc": "Driver's license, DEA number, or professional license", "example": "DL: S12345678"},
        ],
    },
    {
        "category": "geographic_data",
        "display": "Geographic Data",
        "desc": "All geographic subdivisions smaller than a state, including street address, city, county, ZIP code (all 5+ digit codes and their equivalent geocodes)",
        "example": "123 Main Street, Springfield, IL 62704",
        "subcategories": [
            {"subcategory": "street_address", "display": "Street Address", "desc": "Street addresses", "example": "123 Main Street, Apt 4B"},
            {"subcategory": "city", "display": "City", "desc": "City names in the context of patient location", "example": "Springfield, Boston"},
            {"subcategory": "zip_code", "display": "ZIP Code", "desc": "ZIP codes or postal codes", "example": "62704, 02101"},
            {"subcategory": "county", "display": "County", "desc": "County names in geographic context", "example": "Cook County, Middlesex"},
        ],
    },
    {
        "category": "age_over_89",
        "display": "Ages Over 89",
        "desc": "All elements of dates (including year) indicative of age greater than 89",
        "example": "Age: 92, 95-year-old patient",
        "subcategories": [
            {"subcategory": "age", "display": "Age Over 89", "desc": "Age values exceeding 89 years", "example": "92 years old"},
        ],
    },
    {
        "category": "device_id",
        "display": "Device Identifiers & Serial Numbers",
        "desc": "Device identifiers and serial numbers",
        "example": "Device SN: ABC123456, Pacemaker ID: PM-98765",
        "subcategories": [
            {"subcategory": "device_serial", "display": "Device Serial Number", "desc": "Medical device identifiers or serial numbers", "example": "SN: ABC123456"},
        ],
    },
    {
        "category": "web_url",
        "display": "Web URLs",
        "desc": "Web Universal Resource Locators (URLs)",
        "example": "http://patientportal.hospital.com/profile/12345",
        "subcategories": [
            {"subcategory": "url", "display": "URL", "desc": "Web URLs containing identifying information", "example": "http://patientportal.hospital.com"},
        ],
    },
    {
        "category": "ip_address",
        "display": "IP Addresses",
        "desc": "Internet Protocol (IP) address numbers",
        "example": "192.168.1.100, 10.0.0.1",
        "subcategories": [
            {"subcategory": "ip", "display": "IP Address", "desc": "Internet Protocol addresses", "example": "192.168.1.100"},
        ],
    },
]


@dataclass
class BoundingBox:
    """Bounding box coordinates for a text region."""

    x0: float  # Left edge
    y0: float  # Top edge
    x1: float  # Right edge
    y1: float  # Bottom edge

    def to_dict(self) -> list:
        """Convert to [x0, y0, width, height] list."""
        return [
            round(self.x0, 2),
            round(self.y0, 2),
            round(self.x1 - self.x0, 2),
            round(self.y1 - self.y0, 2),
        ]

    @classmethod
    def from_rect(cls, rect) -> "BoundingBox":
        """Create from PyMuPDF Rect object."""
        return cls(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)


@dataclass
class PageContent:
    """Content extracted from a single document page."""

    page_number: int
    text: str
    width: float = 0.0
    height: float = 0.0
    is_ocr: bool = False  # True if text was extracted via OCR


@dataclass
class SensitiveFinding:
    """A detected piece of Protected Health Information (PHI)."""

    text: str
    category: str  # PHI category identifier
    subcategory: str
    page_number: int  # 0-indexed internally
    confidence: float
    rationale: str
    replacement: str = ""  # Replacement text (placeholder or synthetic)
    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Bounding boxes - list to support multi-line text
    bounding_boxes: List[BoundingBox] = field(default_factory=list)
    # Flag indicating if text spans multiple lines
    is_multiline: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        bbox = self.bounding_boxes[0].to_dict() if self.bounding_boxes else []
        return {
            "section_id": self.finding_id,
            "section_text": self.text,
            "category": self.category if isinstance(self.category, str) else self.category.value,
            "subcategory": self.subcategory,
            "page_number": self.page_number + 1,  # 1-indexed
            "conf_score": int(self.confidence * 100),
            "rationale": self.rationale,
            "replacement": self.replacement,
            "bbox": bbox,
        }


@dataclass
class RedactionResult:
    """Result of processing a document through the de-identification pipeline."""

    input_path: str
    output_path: str
    findings: List[SensitiveFinding]
    total_pages: int
    redacted_count: int
    processing_time_seconds: float
    categories_requested: list = field(default_factory=list)
    ocr_pages: int = 0  # Number of pages processed with OCR

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        # Count findings by category
        by_category = {}
        for f in self.findings:
            cat = f.category if isinstance(f.category, str) else f.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "total_pages": self.total_pages,
            "ocr_pages": self.ocr_pages,
            "redacted_count": self.redacted_count,
            "processing_time_seconds": round(self.processing_time_seconds, 2),
            "categories_requested": [
                c.value if isinstance(c, PHICategory) else c
                for c in self.categories_requested
            ],
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                "by_category": by_category,
                "total_findings": len(self.findings),
            },
        }
