import pytest
from auto_qc.qc.domain.schemas import (
    Violation, ResultItem, WorkerOutput, Rule, RulePackage,
    Conversation, Batch, CrossValidationResult, Progress,
)


class TestWorkerOutput:
    def test_from_valid_dict(self):
        data = {
            "batch_id": 1,
            "rules_checked": ["R01", "R02"],
            "spot_check_details": [{"id": "123", "reasoning": "..."}],
            "results": [
                {
                    "id": "123",
                    "status": "violation",
                    "violations": [
                        {
                            "rule_id": "R01",
                            "rule_name": "测试规则",
                            "severity": "高",
                            "evidence": "用户: 不考虑 | AI: 好的",
                            "suggestion": "立刻结束对话",
                        }
                    ],
                },
                {"id": "456", "status": "pass", "violations": []},
            ],
        }
        output = WorkerOutput.from_dict(data)
        assert output.batch_id == 1
        assert len(output.rules_checked) == 2
        assert len(output.results) == 2
        assert output.results[0].status == "violation"
        assert output.results[0].violations[0].rule_id == "R01"

    def test_from_empty_dict(self):
        output = WorkerOutput.from_dict({})
        assert output.batch_id == 0
        assert output.results == []
        assert output.rules_checked == []


class TestRulePackage:
    def test_rule_ids_property(self):
        pkg = RulePackage.from_dict({
            "rules": [
                {"rule_id": "R01", "name": "a", "severity": "高",
                 "description": "", "detection_logic": ""},
                {"rule_id": "R02", "name": "b", "severity": "中",
                 "description": "", "detection_logic": ""},
            ]
        })
        assert pkg.rule_ids == ["R01", "R02"]


class TestBatch:
    def test_ids_and_size(self):
        convs = [
            Conversation(id="1", time="",  conversation=""),
            Conversation(id="2", time="",  conversation=""),
        ]
        batch = Batch(batch_id=1, conversations=convs)
        assert batch.ids == ["1", "2"]
        assert batch.size == 2


class TestCrossValidationResult:
    def test_ok_rate(self):
        r = CrossValidationResult.compute(mismatches=2, total=100)
        assert r.discrepancy_rate == 0.02
        assert r.status == "ok"

    def test_suspicious_rate(self):
        r = CrossValidationResult.compute(mismatches=7, total=100)
        assert r.status == "suspicious"

    def test_high_rate(self):
        r = CrossValidationResult.compute(mismatches=15, total=100)
        assert r.status == "high"
