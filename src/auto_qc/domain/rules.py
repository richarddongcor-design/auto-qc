"""规则文件解析与校验"""
import re
from pathlib import Path
from auto_qc.domain.schemas import Rule, RulePackage

_SEVERITY_MAP = {"高": "高", "中": "中", "低": "低", "HIGH": "高", "MEDIUM": "中", "LOW": "低"}


def parse_rules_markdown(markdown_text: str) -> list[Rule]:
    """解析 Markdown 格式的规则文本，返回 Rule 列表。

    支持两种规则 ID 格式:
      - ## R01: 规则名称
      - ## RULE-001: 规则名称
    支持两种严重程度字段:
      - **严重程度**: 高/中/低
      - **置信度**: HIGH/MEDIUM/LOW
    """
    rules = []
    # 匹配 ## R01: 或 ## RULE-001: 格式
    # 捕获组1: 完整规则ID (如 "R01" 或 "RULE-001")
    pattern = re.compile(
        r"(?:\n|^)## (R\d+|RULE-\d+):\s*(.+?)\n(.*?)(?=(?:\n|^)## (?:R|RULE-)|\Z)",
        re.DOTALL,
    )

    for match in pattern.finditer(markdown_text):
        rule_id = match.group(1)
        name = match.group(2).strip()
        content = match.group(3)

        # 兼容两种字段名：严重程度 / 置信度
        severity_match = re.search(r"\*\*(?:严重程度|置信度)\*\*[:：]\s*(.+)", content)
        severity = severity_match.group(1).strip() if severity_match else ""
        severity = _SEVERITY_MAP.get(severity, severity)

        desc_match = re.search(r"\*\*描述\*\*[:：]\s*(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        logic_match = re.search(r"\*\*检测逻辑\*\*[:：]\s*(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        detection_logic = logic_match.group(1).strip() if logic_match else ""

        examples = []
        examples_match = re.search(r"\*\*典型案例\*\*[:：]\s*\n?(.+?)(?=\n\*\*|\n##|$)", content, re.DOTALL)
        if examples_match:
            examples_text = examples_match.group(1).strip()
            examples = [
                line.strip().lstrip("- ").strip()
                for line in examples_text.split("\n")
                if line.strip().startswith("-")
            ]

        rules.append(Rule(
            rule_id=rule_id,
            name=name,
            severity=severity,
            description=description,
            detection_logic=detection_logic,
            examples=examples,
        ))
    return rules


def parse_rules_file(file_path: str) -> RulePackage:
    """读取规则文件并解析为 RulePackage。"""
    text = Path(file_path).read_text(encoding="utf-8")
    rules = parse_rules_markdown(text)
    return RulePackage(rules=rules)


def validate_rule_package(pkg: RulePackage) -> list[str]:
    """
    校验规则包的完整性。返回错误列表，空列表表示通过。
    """
    errors = []

    if not pkg.rules:
        errors.append("规则包为空，至少需要一条规则")
        return errors

    seen_ids = set()
    for rule in pkg.rules:
        # 规则 ID 唯一性
        if rule.rule_id in seen_ids:
            errors.append(f"规则 ID 重复: {rule.rule_id}")
        seen_ids.add(rule.rule_id)

        # 必填字段
        if not rule.name:
            errors.append(f"{rule.rule_id}: 规则名称为空")
        if not rule.description:
            errors.append(f"{rule.rule_id}: 规则描述为空")
        if not rule.detection_logic:
            errors.append(f"{rule.rule_id}: 检测逻辑为空")

        # severity 合法性
        if rule.severity not in ("高", "中", "低"):
            errors.append(f"{rule.rule_id}: severity 不合法 ({rule.severity})，应为 高/中/低")

    return errors
