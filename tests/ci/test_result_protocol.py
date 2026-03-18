from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import result_protocol


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "result_protocol"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture_name", "mode"),
    [
        ("triage_envelope_ok.json", "triage"),
        ("fix_issue_envelope_ok.json", "fix"),
        ("fix_retry_envelope_ok.json", "fix"),
        ("review_envelope_ok.json", "review"),
    ],
)
def test_validate_envelope_accepts_canonical_fixtures(fixture_name: str, mode: str) -> None:
    envelope = _load_fixture(fixture_name)
    result_protocol.validate_envelope(envelope, requested_mode=mode)


@pytest.mark.parametrize(
    ("envelope_fixture", "expected_fixture"),
    [
        ("triage_envelope_ok.json", "triage_result_expected.json"),
        ("fix_issue_envelope_ok.json", "fix_issue_result_expected.json"),
        ("fix_retry_envelope_ok.json", "fix_retry_result_expected.json"),
        ("review_envelope_ok.json", "review_result_expected.json"),
    ],
)
def test_unwrap_result_matches_expected_fixture_byte_for_byte(
    envelope_fixture: str,
    expected_fixture: str,
) -> None:
    envelope = _load_fixture(envelope_fixture)
    expected_json = (FIXTURES_DIR / expected_fixture).read_text(encoding="utf-8")
    actual = result_protocol.unwrap_result(envelope)
    actual_json = json.dumps(actual, ensure_ascii=False, indent=2)
    assert actual_json == expected_json.strip()


def test_normalize_diagnostics_matches_frozen_schema_structure() -> None:
    frozen_schema = _load_fixture("diagnostics_schema.json")
    envelope = _load_fixture("triage_envelope_ok.json")

    diagnostics = result_protocol.normalize_diagnostics(
        envelope,
        parser_mode="envelope",
        fallback_used=False,
        attempt=1,
        max_attempts=2,
        context_trimmed=False,
        trim_report=None,
        legacy_fallback_reason=None,
        raw_log_path="path/to/fix_result.raw.txt",
        error_code=None,
    )

    assert set(diagnostics.keys()) == set(frozen_schema.keys())
    assert diagnostics == {
        "protocol_version": result_protocol.PROTOCOL_VERSION,
        "requested_mode": "triage",
        "parser_mode": "envelope",
        "fallback_used": False,
        "attempt": 1,
        "max_attempts": 2,
        "context_trimmed": False,
        "trim_report": None,
        "legacy_fallback_reason": None,
        "raw_log_path": "path/to/fix_result.raw.txt",
        "error_code": None,
    }


def test_validate_envelope_rejects_wrong_protocol_version() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["protocol_version"] = "result-envelope.v2"

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="triage")

    assert exc_info.value.error_code == "WRONG_PROTOCOL_VERSION"


def test_validate_envelope_rejects_mismatched_mode() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="fix")

    assert exc_info.value.error_code == "MODE_MISMATCH"


def test_validate_envelope_rejects_extra_top_level_fields() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["unexpected"] = True

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="triage")

    assert exc_info.value.error_code == "EXTRA_FIELDS"


def test_validate_envelope_rejects_invalid_status() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["status"] = "partial"

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="triage")

    assert exc_info.value.error_code == "INVALID_STATUS"


def test_validate_envelope_rejects_missing_required_fields_with_typed_error_codes() -> None:
    cases = [
        ("protocol_version", "MISSING_PROTOCOL_VERSION"),
        ("mode", "MISSING_MODE"),
        ("status", "MISSING_STATUS"),
        ("result", "MISSING_RESULT"),
        ("diagnostics", "MISSING_DIAGNOSTICS"),
    ]

    for field_name, error_code in cases:
        envelope = _load_fixture("triage_envelope_ok.json")
        envelope.pop(field_name)
        with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
            result_protocol.validate_envelope(envelope, requested_mode="triage")
        assert exc_info.value.error_code == error_code


def test_validate_envelope_rejects_invalid_mode_value() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["mode"] = "dispatch"

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="triage")

    assert exc_info.value.error_code == "INVALID_MODE"


def test_protocol_validation_error_exposes_error_code_attribute() -> None:
    err = result_protocol.ProtocolValidationError("INVALID_STATUS", "status invalid")
    assert err.error_code == "INVALID_STATUS"


def test_validate_envelope_rejects_triage_result_missing_verdict() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["result"] = {"reason": "missing verdict field"}

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="triage")

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"


def test_validate_envelope_rejects_review_result_missing_decision() -> None:
    envelope = _load_fixture("review_envelope_ok.json")
    envelope["result"] = {"summary": "no decision"}

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="review")

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"


def test_validate_envelope_rejects_fix_result_missing_summary() -> None:
    envelope = _load_fixture("fix_issue_envelope_ok.json")
    envelope["result"] = {"changed_files": []}

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="fix")

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"


def test_validate_envelope_skips_result_schema_for_status_error() -> None:
    envelope = _load_fixture("triage_envelope_ok.json")
    envelope["status"] = "error"
    envelope["result"] = {}

    result_protocol.validate_envelope(envelope, requested_mode="triage")


def test_fix_mode_with_only_followups_passes() -> None:
    """Valid issue-fix result with only followups field."""
    envelope = _load_fixture("fix_issue_envelope_ok.json")
    assert "followups" in envelope["result"]
    assert "remaining_risks" not in envelope["result"]
    result_protocol.validate_envelope(envelope, requested_mode="fix")


def test_fix_mode_with_only_remaining_risks_passes() -> None:
    """Valid retry-fix result with only remaining_risks field."""
    envelope = _load_fixture("fix_retry_envelope_ok.json")
    assert "remaining_risks" in envelope["result"]
    assert "followups" not in envelope["result"]
    result_protocol.validate_envelope(envelope, requested_mode="fix")


def test_fix_mode_with_both_variants_fails() -> None:
    """fix result with both followups and remaining_risks should fail."""
    envelope = _load_fixture("fix_issue_envelope_ok.json")
    envelope["result"]["remaining_risks"] = ["some risk"]

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="fix")

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"


def test_fix_mode_with_neither_variant_fails() -> None:
    """fix result with neither followups nor remaining_risks should fail."""
    envelope = _load_fixture("fix_issue_envelope_ok.json")
    envelope["result"].pop("followups")

    with pytest.raises(result_protocol.ProtocolValidationError) as exc_info:
        result_protocol.validate_envelope(envelope, requested_mode="fix")

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"
