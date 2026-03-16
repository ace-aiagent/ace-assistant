"""验证 ace-config.json 的配置完整性。

检查项：
1. JSON 文件可正常解析
2. tech_stack 字段完整（5 个子字段非空）
3. branch.prefix 不含非法 git 字符
4. branch.detection_patterns 与 prefix 一致性
5. labels 键值格式正确
6. 未知的顶层字段（警告而非错误）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci._config import load_ace_config, validate_branch_config

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ".github/ace-config.json"

# Git 非法字符集合（参考 git refs 限制）
ILLEGAL_GIT_CHARS = {"..", "~", "^", ":", "\\", " ", "?", "*", "["}


def check_tech_stack(config, errors: list[str]) -> None:
    """验证 tech_stack 所有 5 个子字段都非空字符串。"""
    ts = config.tech_stack
    required_fields = ["language", "package_manager", "test_command", "type_check_command", "runner"]
    for field in required_fields:
        value = getattr(ts, field, None)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"[TECH_STACK] {field} 必须是非空字符串，实际值：{repr(value)}")


def check_branch_prefix(config, errors: list[str]) -> None:
    """验证 branch.prefix 不含非法 git 字符。"""
    prefix = config.branch.prefix
    if not isinstance(prefix, str):
        errors.append(f"[BRANCH_PREFIX] prefix 必须是字符串，实际值：{repr(prefix)}")
        return

    for illegal in ILLEGAL_GIT_CHARS:
        if illegal in prefix:
            errors.append(f"[BRANCH_PREFIX] prefix 含有非法字符 '{illegal}'：'{prefix}'")
            return


def check_branch_consistency(config, errors: list[str]) -> None:
    """验证 branch 配置一致性（使用 validate_branch_config）。"""
    warnings = validate_branch_config(config)
    for warning in warnings:
        errors.append(f"[BRANCH_CONSISTENCY] {warning}")


def check_label_keys(config, errors: list[str]) -> None:
    """验证 labels 键只能包含 [a-zA-Z0-9_-]。"""
    labels = config.labels
    if not isinstance(labels, dict):
        errors.append(f"[LABELS] labels 必须是字典，实际值：{type(labels).__name__}")
        return

    # 允许的字符：字母、数字、下划线、连字符
    allowed_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
    for key in labels.keys():
        if not isinstance(key, str):
            errors.append(f"[LABELS] label 键必须是字符串，实际值：{repr(key)}")
        elif not allowed_pattern.match(key):
            errors.append(f"[LABELS] label 键 '{key}' 包含非法字符，只能用 [a-zA-Z0-9_-]")


def check_unknown_fields(raw_data: dict[str, object], warnings: list[str]) -> None:
    """检测未知的顶层字段（警告而非错误）。"""
    known = {
        "tech_stack",
        "bot",
        "branch",
        "labels",
        "review",
        "ci_paths",
        "error_recovery",
        "workflow_validation",
        "chatops",
    }
    unknown = sorted(set(raw_data.keys()) - known)
    if unknown:
        warnings.append(f"[UNKNOWN_FIELDS] 发现未知字段：{', '.join(unknown)}")


def main(config_path: str | None = None) -> int:
    """验证 ace-config.json 并返回 0（成功）或 1（失败）。"""
    errors: list[str] = []
    warnings: list[str] = []
    config = None

    print("=== ACE Config Validation ===\n")

    # 解析 config_path 为绝对路径
    if config_path:
        resolved_path = Path(config_path).resolve()
    else:
        resolved_path = REPO_ROOT / DEFAULT_CONFIG_PATH

    # 1. 加载配置（load_ace_config 会捕获 JSON 解析和 tech_stack 缺失）
    try:
        config = load_ace_config(str(resolved_path))
    except ValueError as exc:
        errors.append(f"[CONFIG] {str(exc)}")

    # 2. 如果加载失败，尝试读取原始 JSON 用于检查未知字段
    if errors:
        print(f"❌ 发现 {len(errors)} 个问题：\n")
        for err in errors:
            print(f"  {err}")
        if warnings:
            print(f"\n⚠️  {len(warnings)} 个警告：\n")
            for warn in warnings:
                print(f"  {warn}")
        print()
        return 1

    # 3. 如果加载成功，运行所有检查
    try:
        raw_data = json.loads(resolved_path.read_text(encoding="utf-8"))
        if isinstance(raw_data, dict):
            check_unknown_fields(raw_data, warnings)
    except (json.JSONDecodeError, OSError):
        pass  # 已在 load_ace_config 中处理过

    if config is not None:
        check_tech_stack(config, errors)
        check_branch_prefix(config, errors)
        check_branch_consistency(config, errors)
        check_label_keys(config, errors)

    # 4. 输出结果
    if errors:
        print(f"❌ 发现 {len(errors)} 个问题：\n")
        for err in errors:
            print(f"  {err}")
        if warnings:
            print(f"\n⚠️  {len(warnings)} 个警告：\n")
            for warn in warnings:
                print(f"  {warn}")
        print()
        return 1

    # 成功
    print("✅ Config valid\n")
    if warnings:
        print(f"⚠️  {len(warnings)} 个警告：\n")
        for warn in warnings:
            print(f"  {warn}")
        print()
    return 0


if __name__ == "__main__":
    config_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(config_arg))
