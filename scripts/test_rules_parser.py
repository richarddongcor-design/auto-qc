"""测试 rules_parser.py 的规则解析功能"""
import json
from rules_parser import parse_rules


def test_parse_single_rule():
    """测试解析单条规则"""
    text = """## R01: 无视用户明确拒绝

**严重程度**: 高
**发现次数**: 558/25600 (2.2%)

**描述**: 用户明确表示不考虑后，AI 未礼貌结束对话。

**检测逻辑**: 检测用户发言包含明确拒绝关键词后，AI 下一条发言是否继续推进。

**典型案例**:
- 对话 11237419617 (轮次 4): 用户: 嗯，暂时不考虑了啊，谢谢 | AI继续: ...
- 对话 11149319380 (轮次 4): 用户: 啊，不考虑，拜拜 | AI继续: ...
"""
    rules = parse_rules(text)
    assert len(rules) == 1
    assert rules[0]["rule_id"] == "R01"
    assert rules[0]["name"] == "无视用户明确拒绝"
    assert rules[0]["severity"] == "高"
    assert "不考虑" in rules[0]["description"]
    assert "拒绝关键词" in rules[0]["detection_logic"]
    assert len(rules[0]["examples"]) == 2


def test_parse_multiple_rules():
    """测试解析多条规则"""
    text = """## R01: 规则一

**严重程度**: 高
**发现次数**: 100

**描述**: 描述一

**检测逻辑**: 逻辑一

**典型案例**:
- 案例1

## R02: 规则二

**严重程度**: 中
**发现次数**: 50

**描述**: 描述二

**检测逻辑**: 逻辑二

**典型案例**:
- 案例2
"""
    rules = parse_rules(text)
    assert len(rules) == 2
    assert rules[0]["rule_id"] == "R01"
    assert rules[1]["rule_id"] == "R02"
    assert rules[0]["severity"] == "高"
    assert rules[1]["severity"] == "中"


def test_parse_rules_to_package():
    """测试输出规则包 JSON"""
    text = """## R01: 测试规则

**严重程度**: 低
**发现次数**: 10

**描述**: 这是一条测试规则

**检测逻辑**: 测试用

**典型案例**:
- 案例1
"""
    rules = parse_rules(text)
    package = {"rules": rules}
    assert "rules" in package
    assert package["rules"][0]["rule_id"] == "R01"
