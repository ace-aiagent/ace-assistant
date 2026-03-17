"""验证 AI 工作流 YAML 的结构完整性。

检查项：
1. YAML 文件可正常解析
2. 各工作流必需的 inputs 仍然存在
3. 并发组键格式正确
4. 关键 marker 名称仍在脚本中被引用
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from scripts.ci._config import get_workflow_validation, load_ace_config

# TODO: After reusable workflow migration, these paths need adaptation.
# In the reusable workflow context, REPO_ROOT points to the ace-assistant repo,
# but workflows live in the BUSINESS repo ($GITHUB_WORKSPACE).
# WORKFLOWS_DIR should be configurable or resolved via env var (e.g. BUSINESS_REPO_ROOT).
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
SCRIPTS_DIR = REPO_ROOT / "scripts" / "ci"


def _load_workflow(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_yaml_parseable(
    required_inputs: dict[str, list[str]], errors: list[str]
) -> dict[str, dict[str, object]]:
    workflows: dict[str, dict[str, object]] = {}
    for name in required_inputs:
        path = WORKFLOWS_DIR / name
        if not path.exists():
            errors.append(f"[MISSING] 工作流文件不存在：{path.relative_to(REPO_ROOT)}")
            continue
        try:
            data = _load_workflow(path)
            if not isinstance(data, dict):
                errors.append(f"[PARSE] {name}：解析结果不是 dict")
                continue
            workflows[name] = data
        except yaml.YAMLError as exc:
            errors.append(f"[PARSE] {name}：YAML 解析失败 - {exc}")
    return workflows


def check_required_inputs(
    workflows: dict[str, dict[str, object]],
    required_inputs: dict[str, list[str]],
    errors: list[str],
) -> None:
    for name, required in required_inputs.items():
        data = workflows.get(name)
        if data is None:
            continue

        # 提取 inputs：支持 on.workflow_dispatch.inputs 和 on.[key].workflow_dispatch.inputs
        # YAML 中 `on` 可能被解析为 True，所以需要检查两个键
        on_data = data.get("on")
        if on_data is None:
            on_data = data.get(True)  # pyright: ignore[reportArgumentType]
        triggers = on_data
        if not isinstance(triggers, dict):
            errors.append(f"[INPUT] {name}：无法解析 triggers (on:)")
            continue

        wd = triggers.get("workflow_dispatch")
        if not isinstance(wd, dict):
            errors.append(f"[INPUT] {name}：缺少 workflow_dispatch trigger")
            continue

        inputs = wd.get("inputs") or {}
        existing_inputs = set(inputs.keys()) if isinstance(inputs, dict) else set()

        for inp in required:
            if inp not in existing_inputs:
                errors.append(f"[INPUT] {name}：缺少必需 input '{inp}'")


def check_concurrency_keys(
    workflows: dict[str, dict[str, object]],
    expected_concurrency_prefixes: dict[str, str],
    errors: list[str],
) -> None:
    for name, prefix in expected_concurrency_prefixes.items():
        data = workflows.get(name)
        if data is None:
            continue

        concurrency = data.get("concurrency")
        if not isinstance(concurrency, dict):
            errors.append(f"[CONCURRENCY] {name}：缺少 concurrency 配置")
            continue

        group = concurrency.get("group", "")
        if not isinstance(group, str) or prefix not in group:
            errors.append(
                f"[CONCURRENCY] {name}：concurrency group 不包含预期前缀 '{prefix}'，实际值：'{group}'"
            )

        cancel = concurrency.get("cancel-in-progress")
        if cancel is not False:
            errors.append(
                f"[CONCURRENCY] {name}：cancel-in-progress 应为 false，实际值：{cancel}"
            )


def check_marker_references(required_markers: list[str], errors: list[str]) -> None:
    if not SCRIPTS_DIR.exists():
        errors.append(
            f"[MARKER] scripts/ci 目录不存在：{SCRIPTS_DIR.relative_to(REPO_ROOT)}"
        )
        return

    all_script_content = ""
    for py_file in SCRIPTS_DIR.glob("*.py"):
        all_script_content += py_file.read_text(encoding="utf-8")

    for marker in required_markers:
        if marker not in all_script_content:
            errors.append(f"[MARKER] marker '{marker}' 未在 scripts/ci/*.py 中找到引用")


def check_marker_in_workflows(
    workflows: dict[str, dict[str, object]],
    required_inputs: dict[str, list[str]],
    required_markers: list[str],
    errors: list[str],
) -> None:
    for marker in required_markers:
        found = False
        for name, data in workflows.items():
            yaml_str = yaml.dump(data, default_flow_style=False)
            if marker in yaml_str:
                found = True
                break
        if not found:
            # 也检查原始文件内容（YAML dump 可能丢失某些格式）
            for wf_name in required_inputs:
                path = WORKFLOWS_DIR / wf_name
                if path.exists() and marker in path.read_text(encoding="utf-8"):
                    found = True
                    break
        if not found:
            errors.append(
                f"[MARKER] marker '{marker}' 未在任何 AI 工作流 YAML 中找到引用"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", required=False, default=None)
    args = parser.parse_args()

    errors: list[str] = []

    print("=== AI Workflow Structure Validation ===\n")

    config = load_ace_config(config_path=args.config_path)
    wv = get_workflow_validation(config)
    required_inputs = wv.required_inputs
    expected_concurrency_prefixes = wv.expected_concurrency_prefixes
    required_markers = wv.required_markers

    workflows = check_yaml_parseable(required_inputs, errors)
    check_required_inputs(workflows, required_inputs, errors)
    check_concurrency_keys(workflows, expected_concurrency_prefixes, errors)
    check_marker_references(required_markers, errors)
    check_marker_in_workflows(workflows, required_inputs, required_markers, errors)

    if errors:
        print(f"❌ 发现 {len(errors)} 个问题：\n")
        for err in errors:
            print(f"  {err}")
        print()
        return 1

    print("✅ 所有检查通过\n")
    print(f"  - {len(workflows)} 个工作流 YAML 解析正常")
    print(f"  - {sum(len(v) for v in required_inputs.values())} 个必需 inputs 全部存在")
    print(f"  - {len(expected_concurrency_prefixes)} 个并发组键格式正确")
    print(f"  - {len(required_markers)} 个 marker 引用完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
