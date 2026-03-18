from __future__ import annotations

import io
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.ci import run_opencode


# ---------------------------------------------------------------------------
# Shared test fixtures for envelope-based tests
# ---------------------------------------------------------------------------

_VALID_TRIAGE_RESULT = {
    "verdict": "CONFIRMED_BUG",
    "reason": "test reason",
    "confidence": "high",
    "suspected_files": ["src/foo.ts"],
    "fix_strategy": "fix it",
    "verification_plan": ["run tests"],
    "branch_slug": "fix-foo",
}
_VALID_FIX_RESULT = {
    "summary": "fixed it",
    "changed_files": ["src/foo.ts"],
    "verification": [{"command": "pytest", "result": "pass", "details": "ok"}],
}
_VALID_REVIEW_RESULT = {
    "decision": "APPROVE",
    "summary": "looks good",
    "blocking_issues": [],
    "non_blocking_suggestions": [],
    "recommended_checks": [],
}
_VALID_RESULTS_BY_MODE: dict[str, dict] = {
    "triage": _VALID_TRIAGE_RESULT,
    "fix": _VALID_FIX_RESULT,
    "review": _VALID_REVIEW_RESULT,
}


def _make_envelope(*, mode: str = "triage", result: dict | None = None, protocol_version: str = "result-envelope.v1") -> dict:
    return {
        "protocol_version": protocol_version,
        "mode": mode,
        "status": "ok",
        "result": result if result is not None else _VALID_RESULTS_BY_MODE[mode],
        "diagnostics": None,
    }


@dataclass
class _FakeProc:
    stdout: io.StringIO
    stderr: io.StringIO
    returncode: int

    def wait(self) -> int:
        return self.returncode


def _mock_popen(monkeypatch: pytest.MonkeyPatch, *, stdout_text: str, stderr_text: str = "", returncode: int = 0) -> None:
    def _factory(*args, **kwargs) -> _FakeProc:
        return _FakeProc(stdout=io.StringIO(stdout_text), stderr=io.StringIO(stderr_text), returncode=returncode)

    monkeypatch.setattr(subprocess, "Popen", _factory)


def _run_main(monkeypatch: pytest.MonkeyPatch, *, prompt_file: Path, output_file: Path) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_opencode.py",
            "--prompt-file",
            str(prompt_file),
            "--output-file",
            str(output_file),
        ],
    )
    run_opencode.main()


def _make_jsonl_text_event(text: str) -> str:
    event = {"type": "text", "timestamp": "2025-01-01T00:00:00Z", "sessionID": "s1", "part": {"id": "p1", "type": "text", "text": text}}
    return json.dumps(event)


def _make_jsonl_step_event(event_type: str) -> str:
    event = {"type": event_type, "timestamp": "2025-01-01T00:00:00Z", "sessionID": "s1"}
    return json.dumps(event)


# --- strip_ansi ---


def test_strip_ansi_strips_color_codes() -> None:
    assert run_opencode.strip_ansi("\x1b[31mERR\x1b[0m") == "ERR"


def test_strip_ansi_preserves_non_ansi_text() -> None:
    assert run_opencode.strip_ansi("plain text") == "plain text"


def test_strip_ansi_empty_string_returns_empty() -> None:
    assert run_opencode.strip_ansi("") == ""


def test_strip_ansi_handles_multiple_sequences() -> None:
    assert run_opencode.strip_ansi("\x1b[32mOK\x1b[0m and \x1b[31mNO\x1b[0m") == "OK and NO"


# --- _repair_json_newlines ---


def test_repair_json_newlines_fixes_literal_newlines_in_json_values() -> None:
    raw = '{"msg":"hello\nworld"}'.replace("\\n", "\n")
    repaired = run_opencode._repair_json_newlines(raw)
    assert repaired == '{"msg":"hello\\nworld"}'


def test_repair_json_newlines_does_not_modify_valid_json() -> None:
    raw = '{"ok":"yes","n":1}'
    assert run_opencode._repair_json_newlines(raw) == raw


def test_repair_json_newlines_handles_unclosed_string() -> None:
    raw = '{"msg":"line1\nline2'
    repaired = run_opencode._repair_json_newlines(raw)
    assert "line1\\nline2" in repaired


def test_repair_json_newlines_handles_multiple_strings_with_newlines() -> None:
    raw = '{"a":"x\ny","b":"p\nq"}'.replace("\\n", "\n")
    repaired = run_opencode._repair_json_newlines(raw)
    assert repaired == '{"a":"x\\ny","b":"p\\nq"}'


# --- _extract_text_from_jsonl ---


def test_extract_text_from_jsonl_collects_text_events() -> None:
    lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("hello "),
        _make_jsonl_text_event("world"),
        _make_jsonl_step_event("step_finish"),
    ])
    assert run_opencode._extract_text_from_jsonl(lines) == "hello world"


def test_extract_text_from_jsonl_skips_non_text_events() -> None:
    lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_step_event("step_finish"),
    ])
    assert run_opencode._extract_text_from_jsonl(lines) == ""


def test_extract_text_from_jsonl_handles_empty_input() -> None:
    assert run_opencode._extract_text_from_jsonl("") == ""


def test_extract_text_from_jsonl_skips_malformed_lines() -> None:
    lines = "\n".join([
        "not json at all",
        _make_jsonl_text_event("valid"),
        "{broken json",
    ])
    assert run_opencode._extract_text_from_jsonl(lines) == "valid"


def test_extract_text_from_jsonl_skips_text_event_without_part() -> None:
    lines = json.dumps({"type": "text", "timestamp": "x"})
    assert run_opencode._extract_text_from_jsonl(lines) == ""


def test_extract_text_from_jsonl_skips_blank_lines() -> None:
    lines = "\n\n" + _make_jsonl_text_event("ok") + "\n\n"
    assert run_opencode._extract_text_from_jsonl(lines) == "ok"


# --- _parse_result ---


def test_parse_result_plain_text_mode() -> None:
    text = "some output\nAI_RESULT_BEGIN\n{\"ok\": true}\nAI_RESULT_END\n"
    result = run_opencode._parse_result(text, is_jsonl=False)
    assert result == {"ok": True}


def test_parse_result_jsonl_mode() -> None:
    jsonl = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"ok": true}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
        _make_jsonl_step_event("step_finish"),
    ])
    result = run_opencode._parse_result(jsonl, is_jsonl=True)
    assert result == {"ok": True}


def test_parse_result_raises_when_no_markers_in_jsonl() -> None:
    jsonl = "\n".join([
        _make_jsonl_text_event("no markers here"),
    ])
    with pytest.raises(SystemExit):
        run_opencode._parse_result(jsonl, is_jsonl=True)


def test_parse_result_raises_when_no_markers_in_plain_text() -> None:
    with pytest.raises(SystemExit):
        run_opencode._parse_result("no markers", is_jsonl=False)


def test_parse_result_raises_for_unparseable_json() -> None:
    text = "AI_RESULT_BEGIN\n{not valid\nAI_RESULT_END\n"
    with pytest.raises(SystemExit, match="Failed to parse JSON"):
        run_opencode._parse_result(text, is_jsonl=False)


# --- main() with plain text stdout (legacy fallback) ---


def test_main_success_with_valid_ai_result_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(
        monkeypatch,
        stdout_text="AI_RESULT_BEGIN\n{\"ok\": true}\nAI_RESULT_END\n",
    )

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_supports_json_wrapped_in_markdown_code_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(
        monkeypatch,
        stdout_text="AI_RESULT_BEGIN\n```json\n{\"ok\": true}\n```\nAI_RESULT_END\n",
    )

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_repairs_json_with_literal_newlines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    broken_json = '{"msg":"line1\nline2"}'.replace("\\n", "\n")
    _mock_popen(monkeypatch, stdout_text=f"AI_RESULT_BEGIN\n{broken_json}\nAI_RESULT_END\n")

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"msg": "line1\nline2"}


def test_main_raises_system_exit_when_no_markers_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(monkeypatch, stdout_text="no markers")

    with pytest.raises(SystemExit):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert not output_file.exists()


def test_main_reads_trim_meta_sidecar_into_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "triage_prompt.md"
    output_file = tmp_path / "triage_result.json"
    prompt_file.write_text("prompt", encoding="utf-8")
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "legacy")

    trim_meta = {
        "context_trimmed": True,
        "trim_report": {
            "issue_body": {"input_bytes": 5000, "output_bytes": 2000, "trimmed_bytes": 3000},
        },
    }
    Path(str(prompt_file) + ".trim_meta.json").write_text(json.dumps(trim_meta), encoding="utf-8")

    _mock_popen(monkeypatch, stdout_text='AI_RESULT_BEGIN\n{"ok": true}\nAI_RESULT_END\n')

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    diagnostics = json.loads(Path(str(output_file) + ".diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["context_trimmed"] is True
    assert diagnostics["trim_report"] == trim_meta["trim_report"]
    assert not output_file.with_suffix(".raw.txt").exists()


def test_main_strict_envelope_incomplete_tail_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "triage_result.json"
    prompt_file.write_text("prompt", encoding="utf-8")
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "strict-envelope")
    monkeypatch.setenv("OPENCODE_MAX_ATTEMPTS", "2")

    envelope = json.dumps(_make_envelope(mode="triage", result=_VALID_TRIAGE_RESULT))
    outputs = [
        '{"protocol_version":"result-envelope.v1","mode":"triage"',
        envelope,
    ]
    call_idx = {"value": 0}

    def _factory(*args, **kwargs) -> _FakeProc:
        idx = call_idx["value"]
        call_idx["value"] += 1
        return _FakeProc(stdout=io.StringIO(outputs[idx]), stderr=io.StringIO(""), returncode=0)

    monkeypatch.setattr(subprocess, "Popen", _factory)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert call_idx["value"] == 2
    assert json.loads(output_file.read_text(encoding="utf-8")) == _VALID_TRIAGE_RESULT
    diagnostics = json.loads(Path(f"{output_file}.diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostics["attempt"] == 2
    assert diagnostics["error_code"] is None


def test_protocol_mode_raises_for_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "banana")
    with pytest.raises(ValueError, match="Unknown ACE_RESULT_PROTOCOL_MODE"):
        run_opencode._protocol_mode()


def test_main_envelope_status_error_exits_and_does_not_write_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "triage_prompt.md"
    output_file = tmp_path / "triage_result.json"
    prompt_file.write_text("prompt", encoding="utf-8")
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "strict-envelope")

    error_envelope = json.dumps({
        "protocol_version": "result-envelope.v1",
        "mode": "triage",
        "status": "error",
        "result": {},
        "diagnostics": None,
    })
    _mock_popen(monkeypatch, stdout_text=f"analysis\n{error_envelope}\n")

    with pytest.raises(SystemExit):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert not output_file.exists()
