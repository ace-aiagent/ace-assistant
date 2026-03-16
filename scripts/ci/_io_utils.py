#!/usr/bin/env python3
"""Thin JSON file I/O helpers shared across CI scripts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(
    path: str | Path,
    data: Any,
    *,
    indent: int | None = None,
) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )


def load_json_or_default(
    path: str | Path,
    default: Any = None,
) -> Any:
    """当 *default* 为 None 时返回空 dict 而非 None。"""
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return default if default is not None else {}
