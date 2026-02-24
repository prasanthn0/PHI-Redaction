"""Generate benchmark medical PDFs with ground-truth PHI annotations.

Each generated PDF embeds a known set of PHI entities.  The companion
``run_benchmark.py`` script feeds these PDFs through the pipeline and
computes precision / recall / F1 per category.

Usage:
    python -m evaluation.generate_benchmark [--count 10] [--out-dir evaluation/data]

Requires: pymupdf (pip install pymupdf)
"""

import argparse
import json
import random
import string
from pathlib import Path

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Pools of synthetic data used to build the documents
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "James", "Maria", "David", "Linda", "Robert", "Jennifer", "William",
    "Patricia", "Richard", "Barbara", "Thomas", "Elizabeth", "Charles",
    "Susan", "Daniel", "Jessica", "Mark", "Sarah", "Steven", "Karen",
]

LAST_NAMES = [
    "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson",
    "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee",
]

STREET_NAMES = [
    "Main Street", "Oak Avenue", "Park Drive", "Elm Road", "Cedar Lane",
    "Maple Court", "Pine Way", "Birch Boulevard", "Walnut Circle",
]

CITIES = [
    "Springfield", "Riverside", "Georgetown", "Fairview", "Madison",
    "Franklin", "Clinton", "Greenville", "Bristol", "Salem",
]

STATES = ["IL", "CA", "TX", "NY", "FL", "OH", "PA", "GA", "NC", "MI"]

DIAGNOSES = [
    "Type 2 Diabetes Mellitus",
    "Essential Hypertension",
    "Acute Decompensated Heart Failure",
    "Community-Acquired Pneumonia",
    "Chronic Obstructive Pulmonary Disease",
    "Acute Kidney Injury",
    "Major Depressive Disorder",
    "Iron Deficiency Anemia",
    "Atrial Fibrillation",
    "Urinary Tract Infection",
]

MEDICATIONS = [
    "Metformin 1000mg PO BID",
    "Lisinopril 20mg PO daily",
    "Amlodipine 5mg PO daily",
    "Atorvastatin 40mg PO daily",
    "Aspirin 81mg PO daily",
    "Furosemide 40mg PO daily",
    "Omeprazole 20mg PO daily",
    "Metoprolol 50mg PO BID",
    "Albuterol inhaler 2 puffs PRN",
    "Levothyroxine 75mcg PO daily",
]


# ---------------------------------------------------------------------------
# Random helpers
# ---------------------------------------------------------------------------

_rng = random.Random()


def _rand_date(year_lo=1940, year_hi=2006):
    m = _rng.randint(1, 12)
    d = _rng.randint(1, 28)
    y = _rng.randint(year_lo, year_hi)
    return f"{m:02d}/{d:02d}/{y}"


def _rand_recent_date():
    return _rand_date(2024, 2025)


def _rand_phone():
    a = _rng.randint(200, 999)
    b = _rng.randint(200, 999)
    c = _rng.randint(1000, 9999)
    return f"({a}) {b}-{c}"


def _rand_ssn():
    return f"{_rng.randint(100,999)}-{_rng.randint(10,99)}-{_rng.randint(1000,9999)}"


def _rand_mrn():
    return f"MRN-{_rng.randint(1000000,9999999)}"


def _rand_zip():
    return f"{_rng.randint(10000,99999)}"


def _rand_email(first, last):
    domain = _rng.choice(["email.com", "mail.org", "hospital.net"])
    return f"{first.lower()}.{last.lower()}@{domain}"


def _rand_insurance_id():
    pfx = "".join(_rng.choices(string.ascii_uppercase, k=4))
    num = _rng.randint(100000000, 999999999)
    return f"{pfx}-{num}"


def _rand_license(state):
    num = _rng.randint(100000, 999999)
    return f"{state}-MD-{num}"


# ---------------------------------------------------------------------------
# Document generator
# ---------------------------------------------------------------------------

def _build_clinical_note(idx: int):
    """Return (text_page1, text_page2, ground_truth_list)."""

    gt = []  # ground truth PHI items

    # Patient info
    p_first = _rng.choice(FIRST_NAMES)
    p_last = _rng.choice(LAST_NAMES)
    p_full = f"{p_first} {p_last}"
    dob = _rand_date(1940, 1990)
    ssn = _rand_ssn()
    mrn = _rand_mrn()
    ins_id = _rand_insurance_id()
    street_num = _rng.randint(100, 9999)
    street = _rng.choice(STREET_NAMES)
    city = _rng.choice(CITIES)
    state = _rng.choice(STATES)
    zipcode = _rand_zip()
    phone = _rand_phone()
    email = _rand_email(p_first, p_last)
    admit_date = _rand_recent_date()
    doc_first = _rng.choice(FIRST_NAMES)
    doc_last = _rng.choice(LAST_NAMES)
    doc_name = f"Dr. {doc_first} {doc_last}"
    doc_license = _rand_license(state)
    spouse_first = _rng.choice(FIRST_NAMES)
    spouse_last = p_last
    spouse_name = f"{spouse_first} {spouse_last}"
    doc_phone = _rand_phone()
    fax = _rand_phone()
    diag = _rng.sample(DIAGNOSES, k=min(3, len(DIAGNOSES)))
    meds = _rng.sample(MEDICATIONS, k=min(4, len(MEDICATIONS)))

    # Ground truth entries (page, text, category)
    def add(page, text, category, subcategory=""):
        gt.append({
            "text": text,
            "category": category,
            "subcategory": subcategory,
            "page_number": page,
        })

    add(0, p_full, "patient_name", "full_name")
    add(0, dob, "date", "date_of_birth")
    add(0, ssn, "ssn", "social_security")
    add(0, mrn, "medical_record_number", "mrn")
    add(0, ins_id, "health_plan_number", "insurance_id")
    add(0, f"{street_num} {street}", "geographic_data", "street_address")
    add(0, city, "geographic_data", "city")
    add(0, zipcode, "geographic_data", "zip_code")
    add(0, phone, "phone_number", "phone")
    add(0, email, "email_address", "email")
    add(0, admit_date, "date", "admission_date")
    add(0, doc_name, "patient_name", "provider_name")
    add(0, spouse_name, "patient_name", "full_name")
    add(0, doc_phone, "phone_number", "phone")
    add(0, f"Fax: {fax}", "fax_number", "fax")
    add(1, doc_name, "patient_name", "provider_name")
    add(1, doc_license, "license_number", "license")

    page1 = f"""REGIONAL MEDICAL CENTER
Department of Internal Medicine

Patient Name: {p_full}
Date of Birth: {dob}
Medical Record Number: {mrn}
Social Security Number: {ssn}
Health Insurance ID: {ins_id}

Address: {street_num} {street}
         {city}, {state} {zipcode}

Phone: {phone}
Email: {email}
Fax: {fax}

Date of Admission: {admit_date}
Attending Physician: {doc_name}, MD

CHIEF COMPLAINT:
Patient presents with worsening symptoms consistent with {diag[0]}.

HISTORY OF PRESENT ILLNESS:
Patient is a {_rng.randint(30,75)}-year-old admitted for evaluation.
Spouse, {spouse_name}, reports progressive decline over 2 weeks.
Referred by {doc_name} (phone: {doc_phone}).

PAST MEDICAL HISTORY:
"""
    for i, d in enumerate(diag, 1):
        page1 += f"{i}. {d}\n"

    page1 += "\nMEDICATIONS:\n"
    for m in meds:
        page1 += f"- {m}\n"

    discharge_date = _rand_recent_date()
    add(1, discharge_date, "date", "discharge_date")

    page2 = f"""PHYSICAL EXAMINATION:
Vitals: BP {_rng.randint(110,180)}/{_rng.randint(60,100)} mmHg, HR {_rng.randint(60,110)} bpm
General: Alert and oriented x3

ASSESSMENT AND PLAN:
1. {diag[0]} - continue current management
2. Monitor renal function daily

DISPOSITION: Discharge planned for {discharge_date}

Electronically signed by:
{doc_name}, MD
License #: {doc_license}
Date/Time: {admit_date} {_rng.randint(8,17):02d}:{_rng.randint(0,59):02d}
"""

    return page1, page2, gt


def generate_benchmark(count: int, out_dir: str, seed: int = 42):
    """Generate *count* benchmark PDFs with ground-truth JSON files."""
    global _rng
    _rng = random.Random(seed)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest = []

    for i in range(count):
        pdf_name = f"benchmark_{i:03d}.pdf"
        gt_name = f"benchmark_{i:03d}_gt.json"

        page1, page2, gt = _build_clinical_note(i)

        # Write PDF
        doc = fitz.open()
        p1 = doc.new_page(width=612, height=792)
        p1.insert_text(fitz.Point(50, 50), page1, fontsize=9, fontname="helv")
        p2 = doc.new_page(width=612, height=792)
        p2.insert_text(fitz.Point(50, 50), page2, fontsize=9, fontname="helv")
        doc.save(str(out / pdf_name))
        doc.close()

        # Write ground truth
        with open(out / gt_name, "w") as f:
            json.dump({"phi_entities": gt}, f, indent=2)

        manifest.append({"pdf": pdf_name, "ground_truth": gt_name, "phi_count": len(gt)})

    # Write manifest
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Generated {count} benchmark PDFs in {out}")
    print(f"Total PHI entities across all documents: {sum(m['phi_count'] for m in manifest)}")


def main():
    parser = argparse.ArgumentParser(description="Generate HIPAA benchmark PDFs")
    parser.add_argument("--count", type=int, default=10, help="Number of PDFs to generate")
    parser.add_argument("--out-dir", default="evaluation/data", help="Output directory")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    generate_benchmark(args.count, args.out_dir, args.seed)


if __name__ == "__main__":
    main()

