"""Unit tests for LLMDetector._parse_response.

These tests run locally with no container or API calls.
They verify that _parse_response handles valid and malformed LLM output
correctly. All failure cases (invalid JSON, missing keys, unexpected types)
are caught by _detect_page/_detect_page_async which log a warning and
return [].
"""

import json
from unittest.mock import MagicMock

import pytest

from redaction.detectors.llm_detector import LLMDetector
from redaction.models.entities import PageContent


def _detector() -> LLMDetector:
    return LLMDetector(client=MagicMock(), deployment_name="test-deployment")


def _response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    return resp


def _page(text: str = "John Smith, DOB 03/15/1962, SSN 287-65-4321") -> PageContent:
    return PageContent(page_number=0, text=text)


_VALID_CATEGORIES = {"patient_name", "date", "ssn"}

_VALID_FINDING = {
    "text": "John Smith",
    "category": "patient_name",
    "subcategory": "full_name",
    "confidence": 0.95,
    "rationale": "Patient full name.",
}


def _json(**overrides) -> str:
    finding = {**_VALID_FINDING, **overrides}
    return json.dumps({"findings": [finding]})


class TestValidResponse:
    def test_single_finding_returned(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json()), _page(), _VALID_CATEGORIES
        )
        assert len(findings) == 1
        assert findings[0].text == "John Smith"
        assert findings[0].category == "patient_name"
        assert findings[0].subcategory == "full_name"

    def test_multiple_valid_findings_all_returned(self):
        content = json.dumps({
            "findings": [
                {**_VALID_FINDING},
                {
                    "text": "03/15/1962",
                    "category": "date",
                    "subcategory": "date_of_birth",
                    "confidence": 0.99,
                    "rationale": "Date of birth.",
                },
            ]
        })
        detector = _detector()
        findings = detector._parse_response(_response(content), _page(), _VALID_CATEGORIES)
        assert len(findings) == 2

    def test_empty_findings_list_returns_empty(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(json.dumps({"findings": []})), _page(), _VALID_CATEGORIES
        )
        assert findings == []

    def test_missing_findings_key_returns_empty(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(json.dumps({"other_key": "some value"})), _page(), _VALID_CATEGORIES
        )
        assert findings == []

    def test_subcategory_defaults_to_unknown_when_absent(self):
        content = json.dumps({"findings": [{
            "text": "John Smith",
            "category": "patient_name",
            "confidence": 0.9,
            "rationale": "A name.",
        }]})
        detector = _detector()
        findings = detector._parse_response(_response(content), _page(), _VALID_CATEGORIES)
        assert findings[0].subcategory == "unknown"

    def test_rationale_defaults_to_empty_when_absent(self):
        content = json.dumps({"findings": [{
            "text": "John Smith",
            "category": "patient_name",
            "subcategory": "full_name",
            "confidence": 0.9,
        }]})
        detector = _detector()
        findings = detector._parse_response(_response(content), _page(), _VALID_CATEGORIES)
        assert findings[0].rationale == ""


class TestFiltering:
    def test_unknown_category_is_filtered(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(category="invalid_category")),
            _page(),
            _VALID_CATEGORIES,
        )
        assert findings == []

    def test_text_not_in_page_is_filtered(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(text="HALLUCINATED TEXT NOT IN PAGE")),
            _page(),
            _VALID_CATEGORIES,
        )
        assert findings == []

    def test_only_valid_findings_survive_mixed_response(self):
        content = json.dumps({
            "findings": [
                {**_VALID_FINDING},
                {**_VALID_FINDING, "category": "bad_cat"},
                {**_VALID_FINDING, "text": "NOT IN PAGE"},
            ]
        })
        detector = _detector()
        findings = detector._parse_response(_response(content), _page(), _VALID_CATEGORIES)
        assert len(findings) == 1


class TestConfidenceClamping:
    def test_confidence_above_1_clamped_to_1(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(confidence=1.5)), _page(), _VALID_CATEGORIES
        )
        assert findings[0].confidence == 1.0

    def test_confidence_below_0_clamped_to_0(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(confidence=-0.5)), _page(), _VALID_CATEGORIES
        )
        assert findings[0].confidence == 0.0

    def test_confidence_at_boundary_1_preserved(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(confidence=1.0)), _page(), _VALID_CATEGORIES
        )
        assert findings[0].confidence == 1.0

    def test_confidence_at_boundary_0_preserved(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(confidence=0.0)), _page(), _VALID_CATEGORIES
        )
        assert findings[0].confidence == 0.0

    def test_confidence_in_range_preserved(self):
        detector = _detector()
        findings = detector._parse_response(
            _response(_json(confidence=0.85)), _page(), _VALID_CATEGORIES
        )
        assert abs(findings[0].confidence - 0.85) < 1e-9


class TestMalformedOutput:
    def test_invalid_json_raises_json_decode_error(self):
        detector = _detector()
        with pytest.raises(json.JSONDecodeError):
            detector._parse_response(
                _response("Sorry, I cannot help with that."),
                _page(),
                _VALID_CATEGORIES,
            )

    def test_empty_string_raises_json_decode_error(self):
        detector = _detector()
        with pytest.raises(json.JSONDecodeError):
            detector._parse_response(_response(""), _page(), _VALID_CATEGORIES)

    def test_findings_is_a_string_raises(self):
        detector = _detector()
        with pytest.raises((AttributeError, TypeError)):
            detector._parse_response(
                _response(json.dumps({"findings": "not a list"})),
                _page(),
                _VALID_CATEGORIES,
            )

    def test_findings_is_a_dict_raises(self):
        detector = _detector()
        with pytest.raises((AttributeError, TypeError)):
            detector._parse_response(
                _response(json.dumps({"findings": {"text": "John Smith"}})),
                _page(),
                _VALID_CATEGORIES,
            )

    def test_finding_missing_text_key_raises_key_error(self):
        content = json.dumps({"findings": [{
            "category": "patient_name",
            "subcategory": "full_name",
            "confidence": 0.9,
            "rationale": "A name.",
        }]})
        detector = _detector()
        with pytest.raises(KeyError):
            detector._parse_response(_response(content), _page(), _VALID_CATEGORIES)

    def test_empty_choices_raises_index_error(self):
        resp = MagicMock()
        resp.choices = []
        detector = _detector()
        with pytest.raises(IndexError):
            detector._parse_response(resp, _page(), _VALID_CATEGORIES)

    def test_confidence_not_a_number_raises_value_error(self):
        detector = _detector()
        with pytest.raises((ValueError, TypeError)):
            detector._parse_response(
                _response(_json(confidence="high")),
                _page(),
                _VALID_CATEGORIES,
            )
