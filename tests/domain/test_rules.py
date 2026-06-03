import pytest
from auto_qc.domain.rules import parse_rules_markdown, parse_rules_file, validate_rule_package
from auto_qc.domain.schemas import RulePackage


def test_parse_single_rule():
    text = """## R01: 无视用户明确拒绝

**严重程度**: 高
**发现次数**: 558/25600 (2.2%)

**描述**: 用户明确表示不考虑后，AI 未礼貌结束对话。

**检测逻辑**: 检测用户发言包含明确拒绝关键词后，AI 下一条发言是否继续推进。

**典型案例**:
- 对话A: 用户: 嗯，暂时不考虑了啊 | AI继续: ...
- 对话B: 用户: 不考虑，拜拜 | AI继续: ...
"""
    rules = parse_rules_markdown(text)
    assert len(rules) == 1
    assert rules[0].rule_id == "R01"
    assert rules[0].name == "无视用户明确拒绝"
    assert rules[0].severity == "高"
    assert len(rules[0].examples) == 2


def test_parse_multiple_rules():
    text = """## R01: 规则一

**严重程度**: 高

**描述**: 描述一

**检测逻辑**: 逻辑一

## R02: 规则二

**严重程度**: MEDIUM

**描述**: 描述二

**检测逻辑**: 逻辑二
"""
    rules = parse_rules_markdown(text)
    assert len(rules) == 2
    assert rules[0].rule_id == "R01"
    assert rules[1].rule_id == "R02"
    assert rules[1].severity == "中"  # MEDIUM → 中


def test_validate_empty_package():
    pkg = RulePackage(rules=[])
    errors = validate_rule_package(pkg)
    assert len(errors) == 1
    assert "为空" in errors[0]


def test_validate_duplicate_ids():
    from auto_qc.domain.schemas import Rule
    pkg = RulePackage(rules=[
        Rule(rule_id="R01", name="规则一", severity="高", description="d", detection_logic="l"),
        Rule(rule_id="R01", name="规则二", severity="中", description="d", detection_logic="l"),
    ])
    errors = validate_rule_package(pkg)
    assert any("重复" in e for e in errors)


def test_validate_invalid_severity():
    from auto_qc.domain.schemas import Rule
    pkg = RulePackage(rules=[
        Rule(rule_id="R01", name="x", severity="CRITICAL", description="d", detection_logic="l"),
    ])
    errors = validate_rule_package(pkg)
    assert any("severity" in e for e in errors)


def test_validate_missing_fields():
    from auto_qc.domain.schemas import Rule
    pkg = RulePackage(rules=[
        Rule(rule_id="R01", name="", severity="高", description="", detection_logic=""),
    ])
    errors = validate_rule_package(pkg)
    assert len(errors) == 3  # name empty + description empty + detection_logic empty
