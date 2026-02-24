"""Synthetic data generator for HIPAA de-identification."""

import random
import string
from datetime import datetime, timedelta
from typing import Dict, Optional


class SyntheticDataGenerator:
    """Generate synthetic replacements for PHI to preserve clinical context."""

    # Pools of synthetic data
    FIRST_NAMES = [
        "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Quinn",
        "Avery", "Parker", "Drew", "Jamie", "Sam", "Chris", "Pat", "Robin",
        "Blake", "Sage", "Reese", "Finley", "Hayden", "Dakota", "Emery",
    ]

    LAST_NAMES = [
        "Anderson", "Baker", "Clark", "Davis", "Edwards", "Foster", "Green",
        "Harris", "Irving", "Jenkins", "Klein", "Lewis", "Mitchell", "Nelson",
        "O'Connor", "Patterson", "Quinn", "Roberts", "Stevens", "Turner",
    ]

    STREET_NAMES = [
        "Oak Lane", "Maple Drive", "Cedar Avenue", "Pine Street",
        "Elm Road", "Birch Way", "Willow Court", "Spruce Boulevard",
    ]

    CITIES = [
        "Anytown", "Springfield", "Riverside", "Fairview", "Lakewood",
        "Greenville", "Centerville", "Hillcrest", "Pleasanton", "Meadowbrook",
    ]

    STATES = ["CA", "NY", "TX", "FL", "IL", "PA", "OH", "GA", "NC", "MI"]

    PROVIDERS = [
        "Dr. A. Smith", "Dr. B. Johnson", "Dr. C. Williams", "Dr. D. Brown",
        "Dr. E. Jones", "Dr. F. Garcia", "Dr. G. Miller", "Dr. H. Davis",
    ]

    def __init__(self, seed: Optional[int] = None):
        """Initialize with optional random seed for reproducibility."""
        self._rng = random.Random(seed)
        self._cache: Dict[str, str] = {}  # Consistent mappings within a document

    def generate(self, category: str, subcategory: str, original_text: str = "") -> str:
        """Generate a synthetic replacement, cached per original text."""
        cache_key = f"{category}:{original_text}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        generator_map = {
            "patient_name": self._generate_name,
            "date": self._generate_date,
            "phone_number": self._generate_phone,
            "fax_number": self._generate_fax,
            "email_address": self._generate_email,
            "ssn": self._generate_ssn,
            "medical_record_number": self._generate_mrn,
            "health_plan_number": self._generate_health_plan,
            "account_number": self._generate_account,
            "license_number": self._generate_license,
            "geographic_data": self._generate_address,
            "age_over_89": self._generate_age,
            "device_id": self._generate_device_id,
            "web_url": self._generate_url,
            "ip_address": self._generate_ip,
        }

        generator = generator_map.get(category, self._generate_placeholder)
        result = generator(subcategory, original_text)
        self._cache[cache_key] = result
        return result

    def _generate_name(self, subcategory: str, original: str) -> str:
        first = self._rng.choice(self.FIRST_NAMES)
        last = self._rng.choice(self.LAST_NAMES)

        if subcategory == "first_name":
            return first
        elif subcategory == "last_name":
            return last
        elif subcategory == "provider_name":
            return self._rng.choice(self.PROVIDERS)
        return f"{first} {last}"

    def _generate_date(self, subcategory: str, original: str) -> str:
        # Generate a plausible shifted date (shift by random days)
        shift_days = self._rng.randint(30, 365)
        fake_date = datetime.now() - timedelta(days=shift_days)

        if subcategory == "date_of_birth":
            # Generate a plausible birth date
            years_ago = self._rng.randint(20, 80)
            fake_date = datetime.now() - timedelta(days=years_ago * 365)

        return fake_date.strftime("%m/%d/%Y")

    def _generate_phone(self, subcategory: str, original: str) -> str:
        area = self._rng.randint(200, 999)
        prefix = self._rng.randint(200, 999)
        line = self._rng.randint(1000, 9999)
        return f"({area}) {prefix}-{line}"

    def _generate_fax(self, subcategory: str, original: str) -> str:
        return f"Fax: {self._generate_phone(subcategory, original)}"

    def _generate_email(self, subcategory: str, original: str) -> str:
        first = self._rng.choice(self.FIRST_NAMES).lower()
        last = self._rng.choice(self.LAST_NAMES).lower()
        domain = self._rng.choice(["email.com", "mail.org", "example.com"])
        return f"{first}.{last}@{domain}"

    def _generate_ssn(self, subcategory: str, original: str) -> str:
        area = self._rng.randint(100, 999)
        group = self._rng.randint(10, 99)
        serial = self._rng.randint(1000, 9999)
        return f"{area}-{group}-{serial}"

    def _generate_mrn(self, subcategory: str, original: str) -> str:
        num = self._rng.randint(10000000, 99999999)
        return f"MRN-{num}"

    def _generate_health_plan(self, subcategory: str, original: str) -> str:
        prefix = "".join(self._rng.choices(string.ascii_uppercase, k=3))
        num = self._rng.randint(100000000, 999999999)
        return f"{prefix}{num}"

    def _generate_account(self, subcategory: str, original: str) -> str:
        num = self._rng.randint(100000000, 999999999)
        return f"ACCT-{num}"

    def _generate_license(self, subcategory: str, original: str) -> str:
        letter = self._rng.choice(string.ascii_uppercase)
        num = self._rng.randint(10000000, 99999999)
        return f"{letter}{num}"

    def _generate_address(self, subcategory: str, original: str) -> str:
        if subcategory == "zip_code":
            return f"{self._rng.randint(10000, 99999)}"
        elif subcategory == "city":
            return self._rng.choice(self.CITIES)
        elif subcategory == "county":
            return f"{self._rng.choice(self.CITIES)} County"
        else:
            num = self._rng.randint(100, 9999)
            street = self._rng.choice(self.STREET_NAMES)
            return f"{num} {street}"

    def _generate_age(self, subcategory: str, original: str) -> str:
        return "90+"

    def _generate_device_id(self, subcategory: str, original: str) -> str:
        prefix = "".join(self._rng.choices(string.ascii_uppercase, k=2))
        num = self._rng.randint(100000, 999999)
        return f"DEV-{prefix}{num}"

    def _generate_url(self, subcategory: str, original: str) -> str:
        return "http://example.com/redacted"

    def _generate_ip(self, subcategory: str, original: str) -> str:
        return f"10.{self._rng.randint(0,255)}.{self._rng.randint(0,255)}.{self._rng.randint(0,255)}"

    def _generate_placeholder(self, subcategory: str, original: str) -> str:
        return "[REDACTED]"

    def reset(self):
        """Reset the cache for a new document."""
        self._cache.clear()

