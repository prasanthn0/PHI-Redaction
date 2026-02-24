"""Shared pytest fixtures for integration tests.

Tests run against a live container at http://localhost:8000.
The docker-compose.yml mounts ./tests/data -> /app/testdata (read-only).
"""

import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("TEST_API_URL", "http://localhost:8000")

CONTAINER_TESTDATA = "/app/testdata"
CONTAINER_CORRUPT_PDF = f"{CONTAINER_TESTDATA}/corrupt.pdf"
CONTAINER_NOT_A_PDF = f"{CONTAINER_TESTDATA}/not_a_pdf.txt"
CONTAINER_NONEXISTENT = f"{CONTAINER_TESTDATA}/does_not_exist.pdf"
CONTAINER_OUTPUT_DIR = "/app/storage/outputs"


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as c:
        yield c


@pytest.fixture
def unique_file_id() -> str:
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def output_pdf_path(unique_file_id: str) -> str:
    return f"{CONTAINER_OUTPUT_DIR}/{unique_file_id}_redacted.pdf"


def make_file_id() -> str:
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"
