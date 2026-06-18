import json
import pytest
from auto_qc.qc.framework.validator import (
    ValidationError, validate_rule_package, validate_batches,
    validate_worker_output, validate_merge_results, validate_single_rule_output,
)
from auto_qc.qc.domain.schemas import RulePackage, Rule, Batch, Conversation


class TestValidateRulePackage:
    def test_valid_package(self):
        pkg = RulePackage(rules=[
            Rule(rule_id="R01", name="x", severity="高", description="d", detection_logic="l"),
        ])
        validate_rule_package(pkg)  # 不抛异常

    def test_invalid_severity_raises(self):
        pkg = RulePackage(rules=[
            Rule(rule_id="R01", name="x", severity="CRITICAL", description="d", detection_logic="l"),
        ])
        with pytest.raises(ValidationError, match="severity"):
            validate_rule_package(pkg)


class TestValidateBatches:
    def test_empty_batches_raises(self):
        with pytest.raises(ValidationError, match="为空"):
            validate_batches([])

    def test_valid_batches(self):
        batches = [Batch(batch_id=1, conversations=[
            Conversation(id="1", time="", intent="", conversation=""),
        ])]
        validate_batches(batches)  # 不抛异常


class TestValidateWorkerOutput:
    def test_valid_output(self):
        raw = json.dumps({
            "batch_id": 1,
            "rules_checked": ["R01", "R02"],
            "spot_check_details": [
                {"id": "1", "reasoning": "..."},
                {"id": "2", "reasoning": "..."},
                {"id": "3", "reasoning": "..."},
            ],
            "results": [
                {"id": "1", "status": "pass", "violations": []},
                {"id": "2", "status": "pass", "violations": []},
            ],
        }, ensure_ascii=False)
        output = validate_worker_output(raw, batch_size=2, expected_rule_ids=["R01", "R02"])
        assert output.batch_id == 1
        assert len(output.results) == 2

    def test_count_mismatch_raises(self):
        raw = json.dumps({
            "batch_id": 1,
            "rules_checked": ["R01"],
            "spot_check_details": [{"id": "1", "reasoning": ""}] * 3,
            "results": [{"id": "1", "status": "pass", "violations": []}],
        }, ensure_ascii=False)
        with pytest.raises(ValidationError, match="数量不匹配"):
            validate_worker_output(raw, batch_size=3, expected_rule_ids=["R01"])

    def test_missing_rules_checked_raises(self):
        raw = json.dumps({
            "batch_id": 1,
            "rules_checked": ["R01"],
            "spot_check_details": [{"id": "1", "reasoning": ""}] * 3,
            "results": [{"id": "1", "status": "pass", "violations": []}],
        }, ensure_ascii=False)
        with pytest.raises(ValidationError, match="未检查的规则"):
            validate_worker_output(raw, batch_size=1, expected_rule_ids=["R01", "R02", "R03"])

    def test_insufficient_spot_check_raises(self):
        raw = json.dumps({
            "batch_id": 1,
            "rules_checked": ["R01"],
            "spot_check_details": [{"id": "1", "reasoning": ""}],
            "results": [{"id": "1", "status": "pass", "violations": []}],
        }, ensure_ascii=False)
        with pytest.raises(ValidationError, match="spot_check"):
            validate_worker_output(raw, batch_size=1, expected_rule_ids=["R01"])

    def test_missing_evidence_raises(self):
        raw = json.dumps({
            "batch_id": 1,
            "rules_checked": ["R01"],
            "spot_check_details": [{"id": "1", "reasoning": ""}] * 3,
            "results": [{
                "id": "1",
                "status": "violation",
                "violations": [{
                    "rule_id": "R01",
                    "rule_name": "x",
                    "severity": "高",
                    "evidence": "",
                    "suggestion": "",
                }],
            }],
        }, ensure_ascii=False)
        with pytest.raises(ValidationError, match="evidence"):
            validate_worker_output(raw, batch_size=1, expected_rule_ids=["R01"])


class TestValidateMergeResults:
    def test_count_match(self):
        validate_merge_results([{"id": "1"}, {"id": "2"}], 2)  # 不抛异常

    def test_count_mismatch(self):
        with pytest.raises(ValidationError, match="总数不匹配"):
            validate_merge_results([{"id": "1"}], 3)


class TestValidateSingleRuleOutput:
    def test_valid_output(self):
        raw = json.dumps({
            "batch_id": 1,
            "rule_id": "auto-pi_R01",
            "results": [
                {"id": "001", "violates": True, "evidence": "用户: X | AI: Y", "reasoning": "违规"},
                {"id": "002", "violates": False, "evidence": "", "reasoning": ""},
            ],
        })
        data = validate_single_rule_output(raw, 2, "auto-pi_R01", {"001", "002"})
        assert data["rule_id"] == "auto-pi_R01"
        assert len(data["results"]) == 2

    def test_invalid_json_raises(self):
        with pytest.raises(ValidationError, match="JSON"):
            validate_single_rule_output("not json", 1, "R01", {"001"})

    def test_rule_id_mismatch_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "wrong",
            "results": [{"id": "001", "violates": False, "evidence": "", "reasoning": ""}],
        })
        with pytest.raises(ValidationError, match="rule_id"):
            validate_single_rule_output(raw, 1, "expected", {"001"})

    def test_count_mismatch_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "R01",
            "results": [{"id": "001", "violates": False, "evidence": "", "reasoning": ""}],
        })
        with pytest.raises(ValidationError, match="数量不匹配"):
            validate_single_rule_output(raw, 3, "R01", {"001"})

    def test_missing_evidence_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "R01",
            "results": [
                {"id": "001", "violates": True, "evidence": "", "reasoning": ""},
            ],
        })
        with pytest.raises(ValidationError, match="evidence"):
            validate_single_rule_output(raw, 1, "R01", {"001"})

    def test_missing_reasoning_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "R01",
            "results": [
                {"id": "001", "violates": True, "evidence": "证据", "reasoning": ""},
            ],
        })
        with pytest.raises(ValidationError, match="reasoning"):
            validate_single_rule_output(raw, 1, "R01", {"001"})

    def test_invalid_violates_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "R01",
            "results": [
                {"id": "001", "violates": "yes", "evidence": "", "reasoning": ""},
            ],
        })
        with pytest.raises(ValidationError, match="violates"):
            validate_single_rule_output(raw, 1, "R01", {"001"})

    def test_unexpected_id_raises(self):
        raw = json.dumps({
            "batch_id": 1, "rule_id": "R01",
            "results": [
                {"id": "999", "violates": False, "evidence": "", "reasoning": ""},
            ],
        })
        with pytest.raises(ValidationError, match="999"):
            validate_single_rule_output(raw, 1, "R01", {"001"})
