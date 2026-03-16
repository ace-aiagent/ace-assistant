from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest


@pytest.fixture
def write_json(tmp_path: Path) -> Callable[[str, Any], Path]:
    def _write(name: str, payload: Any) -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_text(tmp_path: Path) -> Callable[[str, str], Path]:
    def _write(name: str, content: str) -> Path:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def set_ci_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def _set(**kwargs: str) -> None:
        for key, value in kwargs.items():
            monkeypatch.setenv(key, value)

    return _set
