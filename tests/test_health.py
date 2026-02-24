"""Tests for health and readiness endpoints.

These endpoints require no authentication and make no LLM calls,
so they are fast and always safe to run.
"""

import httpx
import pytest

from conftest import BASE_URL


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


class TestHealthEndpoint:
    def test_returns_200(self, http):
        resp = http.get("/health")
        assert resp.status_code == 200

    def test_status_is_healthy(self, http):
        body = http.get("/health").json()
        assert body["status"] == "healthy"

    def test_version_present(self, http):
        body = http.get("/health").json()
        assert "version" in body
        assert body["version"]

    def test_timestamp_present(self, http):
        body = http.get("/health").json()
        assert "timestamp" in body


class TestLivenessEndpoint:
    def test_returns_200(self, http):
        resp = http.get("/healthz")
        assert resp.status_code == 200

    def test_status_is_alive(self, http):
        body = http.get("/healthz").json()
        assert body["status"] == "alive"


class TestReadinessEndpoint:
    def test_returns_200_when_ready(self, http):
        resp = http.get("/readyz")
        assert resp.status_code == 200

    def test_status_is_ready(self, http):
        body = http.get("/readyz").json()
        assert body["status"] == "ready"

    def test_filesystem_check_ok(self, http):
        body = http.get("/readyz").json()
        assert body["checks"].get("filesystem") == "ok"
