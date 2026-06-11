import json
import pytest
from auto_qc.domain.prompts import build_single_rule_prompt
from auto_qc.domain.schemas import Batch, Conversation, Rule


def test_build_single_rule_prompt():
    """单规则 prompt 应包含规则和对话信息。"""
    batch = Batch(batch_id=1, conversations=[
        Conversation(id="1", time="2024-01-01", intent="A", conversation="你好"),
        Conversation(id="2", time="2024-01-02", intent="B", conversation="再见"),
    ])
    rule = Rule(rule_id="R01", name="规则一", severity="高",
                description="d", detection_logic="l")
    prompt = build_single_rule_prompt(batch, rule)
    assert "R01" in prompt
    assert "规则一" in prompt
    assert "2024-01-01" in prompt
    assert '"id": "1"' in prompt


def test_build_single_rule_prompt_contains_rule_id():
    """单规则 prompt 应包含指定的 rule_id。"""
    from auto_qc.domain.prompts import build_single_rule_prompt
    from auto_qc.domain.schemas import Rule, Batch, Conversation

    rule = Rule(rule_id="auto-pi_R01", name="答非所问", severity="高",
                description="AI 回答与问题无关", detection_logic="检查")
    batch = Batch(batch_id=1, conversations=[
        Conversation(id="001", time="", intent="", conversation="test"),
    ])
    prompt = build_single_rule_prompt(batch, rule)
    assert "auto-pi_R01" in prompt
    assert "答非所问" in prompt


def test_build_single_rule_prompt_only_one_rule():
    """单规则 prompt 中应只包含一条规则的 rule_id。"""
    from auto_qc.domain.prompts import build_single_rule_prompt
    from auto_qc.domain.schemas import Rule, Batch, Conversation

    rule = Rule(rule_id="R01", name="测试规则", severity="高",
                description="描述", detection_logic="逻辑")
    batch = Batch(batch_id=1, conversations=[
        Conversation(id="001", time="", intent="", conversation="test"),
    ])
    prompt = build_single_rule_prompt(batch, rule)
    # 规则定义是 JSON 对象（以 { 开头），不是数组（以 [ 开头）
    rule_section = prompt.split("## 规则\n\n")[1].split("\n\n## 对话数据")[0]
    assert rule_section.strip().startswith("{")
