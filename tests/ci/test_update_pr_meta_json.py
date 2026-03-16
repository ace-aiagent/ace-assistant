from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts.ci import update_pr_meta_json


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["update_pr_meta_json.py", *args])
    update_pr_meta_json.main()


def test_update_set_string_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Test --set key=value sets a string field."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set",
            "name=test-branch",
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["name"] == "test-branch"

    captured = capsys.readouterr()
    assert "test-branch" in captured.out


def test_update_set_json_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Test --set-json key=json sets a JSON field."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set-json",
            'config={"nested": true, "count": 42}',
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["config"] == {"nested": True, "count": 42}

    captured = capsys.readouterr()
    assert "nested" in captured.out


def test_update_set_int_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Test --set-int key=num sets an integer field."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set-int",
            "round=2",
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["round"] == 2
    assert isinstance(result["round"], int)

    captured = capsys.readouterr()
    assert "2" in captured.out


def test_update_multiple_set_args(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test multiple --set args in one call are all applied."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set",
            "key1=value1",
            "--set",
            "key2=value2",
            "--set-int",
            "count=10",
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["key1"] == "value1"
    assert result["key2"] == "value2"
    assert result["count"] == 10


def test_update_existing_file_preserves_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test update existing file — existing keys preserved, new keys added."""
    meta = tmp_path / "meta.json"
    initial = {"branch": "main", "status": "reviewing"}
    meta.write_text(json.dumps(initial), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set",
            "status=approved",
            "--set",
            "reviewer=alice",
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["branch"] == "main"  # preserved
    assert result["status"] == "approved"  # updated
    assert result["reviewer"] == "alice"  # new key


def test_update_missing_file_creates_new(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test missing file creates new file with empty {} base then applies updates."""
    meta = tmp_path / "meta.json"
    assert not meta.exists()

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set",
            "issue=123",
        ],
    )

    assert meta.exists()
    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result == {"issue": "123"}


def test_update_set_json_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test --set-json key=null sets field to JSON null."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"some_key": "some_value"}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set-json",
            "some_key=null",
        ],
    )

    result = json.loads(meta.read_text(encoding="utf-8"))
    assert result["some_key"] is None


def test_update_invalid_set_int_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Test invalid --set-int key=notanumber raises error."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(ValueError):
        _run_main(
            monkeypatch,
            [
                "--meta-file",
                str(meta),
                "--set-int",
                "round=notanumber",
            ],
        )


def test_update_stdout_matches_file_contents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    """Test output to stdout matches file contents."""
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({}), encoding="utf-8")

    _run_main(
        monkeypatch,
        [
            "--meta-file",
            str(meta),
            "--set",
            "key=value",
            "--set-int",
            "num=42",
        ],
    )

    file_content = json.loads(meta.read_text(encoding="utf-8"))
    captured = capsys.readouterr()
    stdout_content = json.loads(captured.out.strip())

    assert file_content == stdout_content
    assert stdout_content["key"] == "value"
    assert stdout_content["num"] == 42
