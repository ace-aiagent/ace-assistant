from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci._io_utils import load_json_or_default, read_json, write_json


class TestReadJson:
    def test_reads_valid_json_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}', encoding="utf-8")

        assert read_json(f) == {"key": "value"}

    def test_reads_unicode_content(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"名前": "太郎"}', encoding="utf-8")

        assert read_json(f) == {"名前": "太郎"}

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("[1, 2, 3]", encoding="utf-8")

        assert read_json(str(f)) == [1, 2, 3]

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_json(tmp_path / "nonexistent.json")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{broken", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_json(f)


class TestWriteJson:
    def test_writes_json_file(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        write_json(f, {"a": 1})

        assert json.loads(f.read_text(encoding="utf-8")) == {"a": 1}

    def test_writes_with_indent(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        write_json(f, {"a": 1}, indent=2)

        content = f.read_text(encoding="utf-8")
        assert content == '{\n  "a": 1\n}'

    def test_writes_without_indent(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        write_json(f, {"a": 1})

        content = f.read_text(encoding="utf-8")
        assert "\n" not in content

    def test_preserves_unicode(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        write_json(f, {"emoji": "🎉", "中文": "测试"})

        raw = f.read_text(encoding="utf-8")
        assert "🎉" in raw
        assert "测试" in raw

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        write_json(str(f), [1, 2])

        assert json.loads(f.read_text(encoding="utf-8")) == [1, 2]

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "out.json"
        f.write_text('{"old": true}', encoding="utf-8")

        write_json(f, {"new": True})
        assert json.loads(f.read_text(encoding="utf-8")) == {"new": True}


class TestLoadJsonOrDefault:
    def test_reads_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"exists": true}', encoding="utf-8")

        assert load_json_or_default(f) == {"exists": True}

    def test_returns_empty_dict_when_missing_and_no_default(self, tmp_path: Path) -> None:
        result = load_json_or_default(tmp_path / "missing.json")
        assert result == {}

    def test_returns_custom_default_when_missing(self, tmp_path: Path) -> None:
        result = load_json_or_default(tmp_path / "missing.json", default=[])
        assert result == []

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "data.json"
        f.write_text("[1]", encoding="utf-8")

        assert load_json_or_default(str(f)) == [1]

    def test_raises_on_invalid_json_in_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{broken", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            load_json_or_default(f)
