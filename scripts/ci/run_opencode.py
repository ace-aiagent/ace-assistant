#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from scripts.ci._io_utils import write_json


ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*(?:"|$)', re.DOTALL)
_RESULT_BLOCK_RE = re.compile(
    r"^[ \t]*AI_RESULT_BEGIN[ \t]*\r?\n(.*?)\r?\n[ \t]*AI_RESULT_END[ \t]*\r?$",
    re.MULTILINE | re.DOTALL,
)

def _repair_json_newlines(text: str) -> str:
    """LLM 可能在 JSON 字符串值中输出 literal newline，导致 json.loads 失败。
    将 JSON 字符串值内部的真实换行替换为 \\n 转义。"""

    def _fix_match(m: re.Match[str]) -> str:
        s = m.group(0)
        if "\n" not in s:
            return s
        inner = s[1:-1] if s.endswith('"') else s[1:]
        inner = inner.replace("\n", "\\n")
        end = '"' if s.endswith('"') else ""
        return f'"{inner}{end}'

    return _JSON_STRING_RE.sub(_fix_match, text)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _stream_pipe(pipe, *, dest, buf: list[str]) -> None:
    assert pipe is not None
    for line in pipe:
        dest.write(line)
        dest.flush()
        buf.append(line)


def _extract_payload_candidates(text: str) -> list[str]:
    return _RESULT_BLOCK_RE.findall(text)


def _strip_markdown_code_block(text: str) -> str:
    code_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    return text


def _try_parse_payload(raw_payload: str) -> dict[str, object] | None:
    for candidate in (raw_payload, _repair_json_newlines(raw_payload)):
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None





def _extract_text_from_jsonl(raw_stdout: str) -> str:
    """从 ``opencode run --format json`` 的 JSONL 事件流中提取 text 事件内容。

    text 事件格式: ``{"type":"text", "part":{"text":"<content>"}}``
    """
    parts: list[str] = []
    for line in raw_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict):
            text = part.get("text", "")
            if text:
                parts.append(text)
    return "".join(parts)


def _is_jsonl_event_stream(raw_stdout: str) -> bool:
    event_like_count = 0
    for line in raw_stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type:
            event_like_count += 1
            if event_like_count >= 2:
                return True
    return False


def _parse_result(combined: str, *, is_jsonl: bool) -> dict[str, object]:
    """从 agent 输出中提取 AI_RESULT 标记内的 JSON。

    is_jsonl=True 时先从 JSONL 事件流提取 text 内容再做 marker 匹配。
    """
    if is_jsonl:
        search_text = _extract_text_from_jsonl(combined)
    else:
        search_text = combined

    matches = _extract_payload_candidates(search_text)
    if not matches:
        raise SystemExit("Could not find AI_RESULT_BEGIN/AI_RESULT_END JSON payload.")

    payload: dict[str, object] | None = None
    last_raw_payload = ""
    for candidate in reversed(matches):
        normalized_payload = _strip_markdown_code_block(candidate.strip())
        last_raw_payload = normalized_payload
        parsed = _try_parse_payload(normalized_payload)
        if parsed is not None:
            payload = parsed
            break

    if payload is None:
        print(f"Raw payload:\n{last_raw_payload}", file=sys.stderr)
        raise SystemExit("Failed to parse JSON between AI_RESULT markers.")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")

    cmd = ["opencode", "run", "--format", "json", prompt]

    env = os.environ.copy()
    env.setdefault("CI", "1")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    # stderr 用独立线程读取，避免与 stdout 顺序读取时死锁
    stderr_thread = threading.Thread(
        target=_stream_pipe,
        args=(proc.stderr,),
        kwargs={"dest": sys.stderr, "buf": stderr_buf},
    )
    stderr_thread.start()

    assert proc.stdout is not None
    _stream_pipe(proc.stdout, dest=sys.stdout, buf=stdout_buf)

    stderr_thread.join()
    returncode = proc.wait()

    raw_stdout = "".join(stdout_buf)
    raw_stderr = "".join(stderr_buf)

    is_jsonl = _is_jsonl_event_stream(raw_stdout)

    if is_jsonl:
        combined_for_log = strip_ansi(raw_stdout + "\n" + raw_stderr)
        combined_for_parse = raw_stdout
    else:
        combined_for_log = strip_ansi(raw_stdout + "\n" + raw_stderr)
        combined_for_parse = combined_for_log

    raw_log_path = Path(args.output_file).with_suffix(".raw.txt")
    raw_log_path.write_text(combined_for_log, encoding="utf-8")

    if returncode != 0:
        raise SystemExit(returncode)

    payload = _parse_result(combined_for_parse, is_jsonl=is_jsonl)
    write_json(args.output_file, payload, indent=2)


if __name__ == "__main__":
    main()
