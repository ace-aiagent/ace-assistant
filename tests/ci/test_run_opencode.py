from __future__ import annotations

import io
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.ci import run_opencode


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


def test_main_raises_system_exit_for_non_zero_return_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(monkeypatch, stdout_text="", returncode=5)

    with pytest.raises(SystemExit):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)


def test_main_takes_last_match_when_prompt_echoed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """prompt 模板中的 AI_RESULT_BEGIN/<json>/AI_RESULT_END 被回显时，应取最后一个匹配"""
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    echoed_prompt = (
        "AI_RESULT_BEGIN\n"
        "<json>\n"
        "AI_RESULT_END\n"
    )
    real_output = (
        "AI_RESULT_BEGIN\n"
        '{"verdict": "CONFIRMED_BUG", "reason": "test"}\n'
        "AI_RESULT_END\n"
    )
    _mock_popen(monkeypatch, stdout_text=echoed_prompt + real_output)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["verdict"] == "CONFIRMED_BUG"


def test_main_takes_last_match_with_three_markers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    blocks = ""
    for i in range(3):
        blocks += f"AI_RESULT_BEGIN\n{{\"round\": {i}}}\nAI_RESULT_END\n"
    _mock_popen(monkeypatch, stdout_text=blocks)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"round": 2}


def test_main_ignores_inline_marker_text_not_standalone_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    stdout_text = (
        "Could not find AI_RESULT_BEGIN/AI_RESULT_END JSON payload.\n"
        "AI_RESULT_BEGIN\n"
        '{"ok": true}\n'
        "AI_RESULT_END\n"
    )
    _mock_popen(monkeypatch, stdout_text=stdout_text)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_uses_previous_valid_block_when_last_block_invalid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    stdout_text = (
        "AI_RESULT_BEGIN\n"
        '{"ok": true}\n'
        "AI_RESULT_END\n"
        "AI_RESULT_BEGIN\n"
        "/\n"
        "AI_RESULT_END\n"
    )
    _mock_popen(monkeypatch, stdout_text=stdout_text)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_supports_crlf_marker_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    stdout_text = "AI_RESULT_BEGIN\r\n{\"ok\": true}\r\nAI_RESULT_END\r\n"
    _mock_popen(monkeypatch, stdout_text=stdout_text)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_supports_indented_marker_lines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    stdout_text = "  AI_RESULT_BEGIN  \n{\"ok\": true}\n  AI_RESULT_END\n"
    _mock_popen(monkeypatch, stdout_text=stdout_text)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_ignores_truncated_trailing_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    stdout_text = (
        "AI_RESULT_BEGIN\n"
        '{"ok": true}\n'
        "AI_RESULT_END\n"
        "AI_RESULT_BEGIN\n"
        '{"broken": '
    )
    _mock_popen(monkeypatch, stdout_text=stdout_text)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_raises_system_exit_for_unparseable_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(monkeypatch, stdout_text="AI_RESULT_BEGIN\n{not valid json\nAI_RESULT_END\n")

    with pytest.raises(SystemExit, match="Failed to parse JSON"):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)


def test_main_supports_markdown_code_block_without_json_tag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(
        monkeypatch,
        stdout_text="AI_RESULT_BEGIN\n```\n{\"ok\": true}\n```\nAI_RESULT_END\n",
    )

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_writes_raw_log_to_raw_txt(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    _mock_popen(
        monkeypatch,
        stdout_text="\x1b[31mAI_RESULT_BEGIN\n{\"ok\": true}\nAI_RESULT_END\x1b[0m\n",
        stderr_text="warn\n",
    )

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    raw_log = output_file.with_suffix(".raw.txt")
    assert raw_log.exists()
    assert "\x1b" not in raw_log.read_text(encoding="utf-8")


# --- main() with JSONL stdout (--format json mode) ---


def test_main_jsonl_mode_extracts_result_from_text_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("I will analyze the code.\n"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"verdict": "CONFIRMED_BUG", "reason": "test"}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    result = json.loads(output_file.read_text(encoding="utf-8"))
    assert result["verdict"] == "CONFIRMED_BUG"


def test_main_jsonl_mode_with_non_json_prefix_still_extracts_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        "[TODO-DIAG] session.idle fired",
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"ok": true}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_jsonl_mode_raises_when_no_markers_in_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("analysis complete, no markers output"),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    with pytest.raises(SystemExit):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)


def test_main_jsonl_mode_recovers_when_end_marker_missing_but_json_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"summary":"ok","changed_files":[],"verification":[]}'),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {
        "summary": "ok",
        "changed_files": [],
        "verification": [],
    }


def test_main_jsonl_mode_raises_when_end_marker_missing_and_json_truncated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"summary":"ok","verification":[{"command":"pnpm test","result":"pass","details\\'),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    with pytest.raises(SystemExit, match="Could not find AI_RESULT_BEGIN/AI_RESULT_END JSON payload"):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)


def test_main_jsonl_mode_writes_raw_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"ok": true}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines, stderr_text="debug info\n")

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    raw_log = output_file.with_suffix(".raw.txt")
    assert raw_log.exists()
    content = raw_log.read_text(encoding="utf-8")
    assert "debug info" in content


def test_main_jsonl_mode_handles_non_zero_return_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = _make_jsonl_text_event("error") + "\n"
    _mock_popen(monkeypatch, stdout_text=jsonl_lines, returncode=1)

    with pytest.raises(SystemExit):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)


def test_main_retries_once_on_missing_markers_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    attempt_outputs = [
        "\n".join([
            _make_jsonl_step_event("step_start"),
            _make_jsonl_text_event("analysis only"),
            _make_jsonl_step_event("step_finish"),
        ]) + "\n",
        "\n".join([
            _make_jsonl_step_event("step_start"),
            _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
            _make_jsonl_text_event('{"ok": true}\n'),
            _make_jsonl_text_event("AI_RESULT_END\n"),
            _make_jsonl_step_event("step_finish"),
        ]) + "\n",
    ]

    call_idx = {"value": 0}

    def _factory(*args, **kwargs) -> _FakeProc:
        idx = call_idx["value"]
        call_idx["value"] += 1
        return _FakeProc(stdout=io.StringIO(attempt_outputs[idx]), stderr=io.StringIO(""), returncode=0)

    monkeypatch.setattr(subprocess, "Popen", _factory)
    monkeypatch.setenv("OPENCODE_MAX_ATTEMPTS", "2")

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert call_idx["value"] == 2
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_uses_single_attempt_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    call_count = {"value": 0}

    def _factory(*args, **kwargs) -> _FakeProc:
        call_count["value"] += 1
        stdout_text = "\n".join([
            _make_jsonl_step_event("step_start"),
            _make_jsonl_text_event("analysis only"),
            _make_jsonl_step_event("step_finish"),
        ]) + "\n"
        return _FakeProc(stdout=io.StringIO(stdout_text), stderr=io.StringIO(""), returncode=0)

    monkeypatch.setattr(subprocess, "Popen", _factory)
    monkeypatch.setenv("OPENCODE_MAX_ATTEMPTS", "1")

    with pytest.raises(SystemExit, match="Could not find AI_RESULT_BEGIN/AI_RESULT_END JSON payload"):
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert call_count["value"] == 1


def test_main_prefers_latest_incomplete_block_when_json_is_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"round": 1}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"round": 2}'),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"round": 2}


def test_main_falls_back_to_last_closed_block_when_latest_incomplete_is_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    jsonl_lines = "\n".join([
        _make_jsonl_step_event("step_start"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"round": 1}\n'),
        _make_jsonl_text_event("AI_RESULT_END\n"),
        _make_jsonl_text_event("AI_RESULT_BEGIN\n"),
        _make_jsonl_text_event('{"round": '),
        _make_jsonl_step_event("step_finish"),
    ]) + "\n"

    _mock_popen(monkeypatch, stdout_text=jsonl_lines)

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == {"round": 1}


def test_main_retries_once_on_parse_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    attempt_outputs = [
        "AI_RESULT_BEGIN\n{not valid json\nAI_RESULT_END\n",
        "AI_RESULT_BEGIN\n{\"ok\": true}\nAI_RESULT_END\n",
    ]

    call_idx = {"value": 0}

    def _factory(*args, **kwargs) -> _FakeProc:
        idx = call_idx["value"]
        call_idx["value"] += 1
        return _FakeProc(stdout=io.StringIO(attempt_outputs[idx]), stderr=io.StringIO(""), returncode=0)

    monkeypatch.setattr(subprocess, "Popen", _factory)
    monkeypatch.setenv("OPENCODE_MAX_ATTEMPTS", "2")

    _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert call_idx["value"] == 2
    assert json.loads(output_file.read_text(encoding="utf-8")) == {"ok": True}


def test_main_non_zero_return_code_does_not_retry_even_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompt_file = tmp_path / "prompt.md"
    output_file = tmp_path / "result.json"
    prompt_file.write_text("prompt", encoding="utf-8")

    call_count = {"value": 0}

    def _factory(*args, **kwargs) -> _FakeProc:
        call_count["value"] += 1
        return _FakeProc(stdout=io.StringIO(""), stderr=io.StringIO(""), returncode=7)

    monkeypatch.setattr(subprocess, "Popen", _factory)
    monkeypatch.setenv("OPENCODE_MAX_ATTEMPTS", "3")

    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, prompt_file=prompt_file, output_file=output_file)

    assert exc.value.code == 7
    assert call_count["value"] == 1
