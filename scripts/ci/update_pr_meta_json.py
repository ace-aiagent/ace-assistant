#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import load_json_or_default, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update JSON file with specified key-value pairs"
    )
    parser.add_argument("--meta-file", required=True, help="Path to JSON file")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        help="Set string value: key=value",
    )
    parser.add_argument(
        "--set-json",
        action="append",
        default=[],
        help="Set JSON value: key=json_value",
    )
    parser.add_argument(
        "--set-int",
        action="append",
        default=[],
        help="Set integer value: key=value",
    )
    args = parser.parse_args()

    meta_file = Path(args.meta_file)

    data: dict[str, Any] = load_json_or_default(meta_file)

    # Apply --set (string values)
    for item in args.set:
        key, value = item.split("=", 1)
        data[key] = value

    # Apply --set-int (integer values)
    for item in args.set_int:
        key, value = item.split("=", 1)
        data[key] = int(value)

    # Apply --set-json (JSON values)
    for item in args.set_json:
        key, value = item.split("=", 1)
        data[key] = json.loads(value)

    # Write back to file
    write_json(meta_file, data)

    print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
