"""
rules_parser.py — Markdown 规则文件解析器

将 rules.md 格式的规则解析为 JSON 规则包。

调用方式：
  python rules_parser.py --rules <规则文件路径> --output <输出JSON路径>
  python rules_parser.py --rules <规则文件路径> --stdout
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional


def parse_rules(markdown_text: str) -> list[dict]:
    """
    解析 Markdown 规则文本，返回结构化规则列表。

    支持的格式：
    ## R01: 规则名称

    **严重程度**: 高/中/低
    **发现次数**: 数字

    **描述**: 描述文本

    **检测逻辑**: 条件描述

    **典型案例**:
    - 案例1
    - 案例2
    """
    rules = []

    # Find all rule blocks via header pattern
    pattern = re.compile(r"(?:\n|^)## (R\d+):\s*(.+?)\n(.*?)(?=(?:\n|^)## R|\Z)", re.DOTALL)
    for match in pattern.finditer(markdown_text):
        rule_id = match.group(1)
        name = match.group(2).strip()
        content = match.group(3)

        # 提取严重程度
        severity_match = re.search(r"\*\*严重程度\*\*[:：]\s*(.+)", content)
        severity = severity_match.group(1).strip() if severity_match else ""

        # 提取描述
        desc_match = re.search(r"\*\*描述\*\*[:：]\s*(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        # 提取检测逻辑
        logic_match = re.search(r"\*\*检测逻辑\*\*[:：]\s*(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        detection_logic = logic_match.group(1).strip() if logic_match else ""

        # 提取典型案例
        examples = []
        examples_match = re.search(r"\*\*典型案例\*\*[:：]\s*\n?(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        if examples_match:
            examples_text = examples_match.group(1).strip()
            examples = [
                line.strip().lstrip("- ").strip()
                for line in examples_text.split("\n")
                if line.strip().startswith("-")
            ]

        rules.append({
            "rule_id": rule_id,
            "name": name,
            "severity": severity,
            "description": description,
            "detection_logic": detection_logic,
            "examples": examples,
        })
    return rules


def main():
    parser = argparse.ArgumentParser(description="规则解析器")
    parser.add_argument("--rules", required=True, help="规则文件路径")
    parser.add_argument("--output", help="输出 JSON 路径（可选，默认 stdout）")
    parser.add_argument("--stdout", action="store_true", help="输出到标准输出")

    args = parser.parse_args()

    if not os.path.exists(args.rules):
        print(f"错误：规则文件不存在: {args.rules}", file=sys.stderr)
        sys.exit(1)

    try:
        rules_text = Path(args.rules).read_text(encoding="utf-8")
    except Exception as e:
        print(f"错误：读取规则文件失败: {e}", file=sys.stderr)
        sys.exit(1)
    rules = parse_rules(rules_text)
    package = {"rules": rules}

    output_json = json.dumps(package, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"规则包已保存: {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
