from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from scripts.ci import upsert_comment


@dataclass
class _FakeRunResult:
    stdout: str = ""
    returncode: int = 0


def _run_main(monkeypatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["upsert_comment.py", *args])
    upsert_comment.main()


def test_upsert_comment_patches_when_existing_comment_found(monkeypatch, write_json, write_text) -> None:
    comments_file = write_json(
        "comments.json",
        [
            {"id": 99, "body": "<!-- ai-pr-meta -->\nold"},
        ],
    )
    body_file = write_text("body.md", "<!-- ai-pr-meta -->\nnew")
    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _FakeRunResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _run_main(
        monkeypatch,
        [
            "--repo",
            "org/repo",
            "--issue-number",
            "7",
            "--comments-file",
            str(comments_file),
            "--marker",
            "ai-pr-meta",
            "--body-file",
            str(body_file),
        ],
    )

    assert any("PATCH" in call for call in calls)


def test_upsert_comment_posts_when_no_existing_comment(monkeypatch, write_json, write_text) -> None:
    comments_file = write_json("comments.json", [{"id": 1, "body": "other"}])
    body_file = write_text("body.md", "<!-- ai-pr-meta -->\nnew")
    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _FakeRunResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _run_main(
        monkeypatch,
        [
            "--repo",
            "org/repo",
            "--issue-number",
            "7",
            "--comments-file",
            str(comments_file),
            "--marker",
            "ai-pr-meta",
            "--body-file",
            str(body_file),
        ],
    )

    assert any("POST" in call for call in calls)


def test_upsert_comment_ignores_inline_marker_text_and_posts(monkeypatch, write_json, write_text) -> None:
    comments_file = write_json(
        "comments.json",
        [{"id": 99, "body": "inline <!-- ai-pr-meta --> marker"}],
    )
    body_file = write_text("body.md", "<!-- ai-pr-meta -->\nnew")
    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _FakeRunResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _run_main(
        monkeypatch,
        [
            "--repo",
            "org/repo",
            "--issue-number",
            "7",
            "--comments-file",
            str(comments_file),
            "--marker",
            "ai-pr-meta",
            "--body-file",
            str(body_file),
        ],
    )

    assert any("POST" in call for call in calls)


def test_upsert_comment_accepts_indented_marker_line_and_patches(monkeypatch, write_json, write_text) -> None:
    comments_file = write_json(
        "comments.json",
        [{"id": 99, "body": "   <!--   ai-pr-meta   -->\nold"}],
    )
    body_file = write_text("body.md", "<!-- ai-pr-meta -->\nnew")
    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return _FakeRunResult()

    monkeypatch.setattr(subprocess, "run", _fake_run)

    _run_main(
        monkeypatch,
        [
            "--repo",
            "org/repo",
            "--issue-number",
            "7",
            "--comments-file",
            str(comments_file),
            "--marker",
            "ai-pr-meta",
            "--body-file",
            str(body_file),
        ],
    )

    assert any("PATCH" in call for call in calls)
