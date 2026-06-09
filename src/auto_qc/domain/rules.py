"""规则文件解析与校验"""
import hashlib
import json
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


# ── 规则缓存 ──────────────────────────────────────────────


def _cache_dir() -> Path:
    """返回规则缓存目录（全局 skill 目录）。"""
    return Path.home() / ".claude" / "skills" / "auto-qc"


def _hash_file(file_path: str) -> str:
    """计算文件的 SHA256 哈希。"""
    content = Path(file_path).read_bytes()
    return hashlib.sha256(content).hexdigest()


def _write_cache(cache_dir: str, name: str, rules_data: dict, source_hash: str) -> None:
    """将规则数据写入缓存 JSON。"""
    from datetime import datetime
    cache_path = Path(cache_dir) / f"{name}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_source_hash": source_hash,
        "_parsed_at": datetime.now().isoformat(),
        **rules_data,
    }
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_cache(cache_dir: str, name: str, source_hash: str | None = None) -> dict | None:
    """读取缓存，hash 不匹配或缓存不存在时返回 None。"""
    cache_path = Path(cache_dir) / f"{name}.json"
    if not cache_path.exists():
        return None
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    if source_hash is not None and data.get("_source_hash") != source_hash:
        return None
    return data


def load_or_parse_rules(
    md_path: str | None = None,
    name: str | None = None,
    cache_dir: str | None = None,
) -> RulePackage:
    """
    加载规则：优先从缓存读取，否则解析 markdown 并写入缓存。

    参数:
        md_path: rules.md 路径。传 None 时仅从缓存加载。
        name: 规则名称，用于缓存文件名。不传时从 md_path 文件名推断。
        cache_dir: 缓存目录，默认 ~/.claude/skills/auto-qc/
    """
    if cache_dir is None:
        cache_dir = str(_cache_dir())

    # 确定 name：从 md_path 文件名推断
    if name is None and md_path:
        name = Path(md_path).stem

    # 计算 source_hash
    source_hash = _hash_file(md_path) if md_path else None

    # 尝试从缓存加载
    if name:
        cached = _read_cache(cache_dir, name, source_hash)
        if cached:
            return RulePackage.from_dict(cached)

    # 没有缓存或 hash 不匹配 → 解析 markdown
    if not md_path:
        raise FileNotFoundError(
            f"缓存未命中且未提供规则文件: name={name}"
        )

    pkg = parse_rules_file(md_path)
    source_hash = _hash_file(md_path)

    # 写入缓存
    if name:
        _write_cache(cache_dir, name, {"rules": [
            {"rule_id": r.rule_id, "name": r.name, "severity": r.severity,
             "description": r.description, "detection_logic": r.detection_logic,
             "examples": r.examples}
            for r in pkg.rules
        ]}, source_hash)

    return pkg
