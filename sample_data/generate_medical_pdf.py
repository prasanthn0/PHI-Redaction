"""Generate a sample medical document PDF for testing de-identification.

Usage:
    python sample_data/generate_medical_pdf.py

Requires: pymupdf (pip install pymupdf)
"""

import fitz  # PyMuPDF


def create_sample_medical_pdf(output_path: str = "sample_data/sample_clinical_note.pdf"):
    """Generate a synthetic clinical note PDF with sample PHI."""
    doc = fitz.open()

    # Page 1: Admission Note
    page = doc.new_page(width=612, height=792)  # US Letter

    text = """MERCY GENERAL HOSPITAL
Department of Internal Medicine
Clinical Note - Admission

Patient Name: John Robert Smith
Date of Birth: 03/15/1962
Medical Record Number: MRN-2847593
Social Security Number: 287-65-4321
Health Insurance ID: BCBS-IL-9928374651

Address: 4521 Oakwood Drive, Apt 12B
         Springfield, IL 62704

Phone: (217) 555-3847
Email: john.r.smith@email.com

Date of Admission: 01/22/2025
Attending Physician: Dr. Sarah Elizabeth Chen, MD
Referring Physician: Dr. Michael Brooks, DO

CHIEF COMPLAINT:
Patient presents with progressive shortness of breath and bilateral
lower extremity edema over the past 2 weeks.

HISTORY OF PRESENT ILLNESS:
Mr. Smith is a 62-year-old male with a past medical history significant
for Type 2 Diabetes Mellitus, Hypertension, and Coronary Artery Disease
(s/p CABG in 2019) who presents with worsening dyspnea on exertion and
peripheral edema. Patient reports orthopnea requiring 3 pillows to sleep.
He denies chest pain, palpitations, or syncope. His wife, Mary Smith,
reports he has been increasingly fatigued. His primary care physician,
Dr. Brooks (phone: (312) 555-9021), referred him for evaluation.

PAST MEDICAL HISTORY:
1. Type 2 Diabetes Mellitus - diagnosed 2008, on Metformin 1000mg BID
2. Hypertension - on Lisinopril 20mg daily, Amlodipine 5mg daily
3. Coronary Artery Disease - CABG x3 on 06/15/2019
4. Hyperlipidemia - on Atorvastatin 40mg daily
5. Chronic Kidney Disease Stage 3a - GFR 52 mL/min

MEDICATIONS:
- Metformin 1000mg PO BID
- Lisinopril 20mg PO daily
- Amlodipine 5mg PO daily
- Atorvastatin 40mg PO daily
- Aspirin 81mg PO daily
- Furosemide 40mg PO daily (recently increased)
"""

    page.insert_text(
        fitz.Point(50, 50),
        text,
        fontsize=9,
        fontname="helv",
    )

    # Page 2: Physical Exam and Plan
    page2 = doc.new_page(width=612, height=792)

    text2 = """PHYSICAL EXAMINATION:
Vitals: BP 158/92 mmHg, HR 88 bpm, RR 22, Temp 98.4F, SpO2 93% on RA
        Weight: 198 lbs (up 12 lbs from last visit on 12/10/2024)
General: Alert and oriented, mild respiratory distress at rest
HEENT: JVP elevated to 12 cm H2O
Cardiac: Regular rate and rhythm, S3 gallop noted, no murmurs
Lungs: Bilateral basilar crackles, dull to percussion bilaterally
Abdomen: Soft, non-tender, hepatomegaly 3 cm below costal margin
Extremities: 3+ pitting edema bilateral lower extremities to knees

LABORATORY RESULTS (01/22/2025):
- BNP: 1,842 pg/mL (elevated)
- Troponin I: 0.02 ng/mL (normal)
- BMP: Na 134, K 4.8, Cr 1.6 (baseline 1.3), BUN 38
- CBC: WBC 8.2, Hgb 11.8, Plt 210
- HbA1c: 7.8% (last checked 10/05/2024)
- TSH: 2.4 mIU/L (normal)
- Chest X-ray: Cardiomegaly, bilateral pleural effusions

ASSESSMENT AND PLAN:
1. Acute decompensated heart failure (HFrEF, EF 30% on echo 09/2024)
   - IV Furosemide 40mg q12h, strict I&O, daily weights
   - Continue home medications
   - Cardiology consult - Dr. Anita Patel, MD (pager: 555-2847)

2. Type 2 Diabetes - hold Metformin given renal function
   - Sliding scale insulin, monitor BG QID

3. Chronic Kidney Disease - Cr trending up from baseline
   - Monitor BMP daily, renal consult if Cr > 2.0

4. Hypertension - elevated despite medications
   - Continue current regimen, reassess after volume status optimized

DISPOSITION: Admit to Telemetry, Level 2 acuity
Code Status: Full code (discussed with patient and wife Mary Smith)

Electronically signed by:
Dr. Sarah Elizabeth Chen, MD
License #: IL-MD-036-284759
NPI: 1234567890
Date/Time: 01/22/2025 14:35

-- CONFIDENTIAL: This document contains Protected Health Information --
-- Subject to HIPAA Privacy Rule (45 CFR Parts 160 and 164)          --
"""

    page2.insert_text(
        fitz.Point(50, 50),
        text2,
        fontsize=9,
        fontname="helv",
    )

    doc.save(output_path)
    doc.close()
    print(f"Created sample medical PDF: {output_path}")
    print("This file contains synthetic PHI for testing de-identification.")


if __name__ == "__main__":
    create_sample_medical_pdf()
