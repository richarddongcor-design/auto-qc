"""PI 模块 — Tracer 追溯系统测试。"""

import json

import pytest
from auto_qc.pi.engine.tracer import Tracer


class TestTracerInitial:
    def test_initial_state(self):
        t = Tracer("run-001")
        assert t.run_id == "run-001"
        assert t.trace == {}


class TestTracerPhase2:
    def test_record_phase2_chunk_adds_patterns(self):
        t = Tracer("run-001")
        patterns = [
            {"pattern_name": "拒绝后仍推进", "severity": "高"},
            {"pattern_name": "语气生硬", "severity": "中"},
        ]
        t.record_phase2_chunk("chunk_0.jsonl", patterns)

        assert t._chunk_to_patterns["chunk_0.jsonl"] == ["拒绝后仍推进", "语气生硬"]

    def test_record_phase2_chunk_assigns_pattern_ids(self):
        t = Tracer("run-001")
        patterns = [
            {"pattern_name": "重复推荐"},
            {"pattern_name": "语气生硬"},
        ]
        t.record_phase2_chunk("chunk_0.jsonl", patterns)

        pid0 = patterns[0].get("pattern_id")
        pid1 = patterns[1].get("pattern_id")
        assert pid0 is not None
        assert pid1 is not None
        assert pid0 != pid1

    def test_record_phase2_chunk_empty(self):
        t = Tracer("run-001")
        t.record_phase2_chunk("chunk_0.jsonl", [])
        assert t._chunk_to_patterns["chunk_0.jsonl"] == []

    def test_pattern_to_chunks_mapping(self):
        t = Tracer("run-001")
        t.record_phase2_chunk("chunk_0.jsonl", [{"pattern_name": "重复推荐"}])
        t.record_phase2_chunk("chunk_1.jsonl", [{"pattern_name": "语气生硬"}])

        assert t._pattern_to_chunks["重复推荐"] == ["chunk_0.jsonl"]
        assert t._pattern_to_chunks["语气生硬"] == ["chunk_1.jsonl"]

    def test_pattern_id_to_chunks_mapping(self):
        t = Tracer("run-001")
        p = {"pattern_name": "测试模式"}
        t.record_phase2_chunk("chunk_0.jsonl", [p])
        pid = p["pattern_id"]

        assert t._pattern_id_to_chunks[pid] == ["chunk_0.jsonl"]

    def test_multiple_chunks_same_pattern_name(self):
        """同一 pattern 名称出现在多个 chunk 中。"""
        t = Tracer("run-001")
        t.record_phase2_chunk("chunk_0.jsonl", [{"pattern_name": "重复推荐"}])
        t.record_phase2_chunk("chunk_1.jsonl", [{"pattern_name": "重复推荐"}])

        assert len(t._pattern_to_chunks["重复推荐"]) == 2
        assert "chunk_0.jsonl" in t._pattern_to_chunks["重复推荐"]
        assert "chunk_1.jsonl" in t._pattern_to_chunks["重复推荐"]


class TestTracerPhase4:
    def test_record_phase4_batch_links_rules_to_patterns(self):
        t = Tracer("run-001")
        p = {"pattern_name": "重复推荐"}
        t.record_phase2_chunk("chunk_0.jsonl", [p])
        pid = p["pattern_id"]

        t.record_phase4_batch("batch_0", [
            {"rule_id": "R01", "merged_from": [pid]},
        ])

        assert t._rule_to_patterns["R01"] == [pid]
        assert t._rule_to_chunks["R01"] == ["chunk_0.jsonl"]

    def test_record_phase4_rules_builds_trace(self):
        t = Tracer("run-001")
        p = {"pattern_name": "重复推荐"}
        t.record_phase2_chunk("chunk_0.jsonl", [p])
        pid = p["pattern_id"]
        t.record_phase4_batch("batch_0", [
            {"rule_id": "R01", "merged_from": [pid]},
        ])

        t.record_phase4_rules([
            {"rule_id": "R01", "rule_name": "重复推荐规则", "merged_from": [pid]},
        ])

        entry = t.trace["R01"]
        assert entry["rule_name"] == "重复推荐规则"
        assert entry["origin"]["phase_2_chunks"] == ["chunk_0.jsonl"]


class TestTracerUtility:
    def test_get_rule_chunks(self):
        t = Tracer("run-001")
        p1 = {"pattern_name": "模式A"}
        p2 = {"pattern_name": "模式B"}
        t.record_phase2_chunk("chunk_0.jsonl", [p1, p2])
        pid1, pid2 = p1["pattern_id"], p2["pattern_id"]

        t.record_phase4_batch("batch_0", [
            {"rule_id": "R01", "merged_from": [pid1, pid2]},
        ])
        t.record_phase4_rules([
            {"rule_id": "R01", "rule_name": "综合", "merged_from": [pid1, pid2]},
        ])

        assert "chunk_0.jsonl" in t.get_rule_chunks("R01")

    def test_get_rule_chunks_nonexistent(self):
        assert Tracer("run-001").get_rule_chunks("NONEXISTENT") == []

    def test_record_phase5_validation(self):
        t = Tracer("run-001")
        t.trace["R01"] = {"rule_name": "测试", "origin": {}, "validation": {}}

        t.record_phase5_validation("R01", {
            "status": "confirmed",
            "hit_rate": 0.85,
            "total_checked": 100,
            "hit_count": 85,
        })

        v = t.trace["R01"]["validation"]
        assert v["status"] == "confirmed"
        assert v["hit_rate"] == 0.85
        assert v["total_checked"] == 100
        assert v["hit_count"] == 85

    def test_record_phase5_validation_unknown_rule(self):
        """不存在的 rule_id 不应抛异常。"""
        t = Tracer("run-001")
        t.record_phase5_validation("UNKNOWN", {"status": "confirmed"})  # no raise

    def test_save(self, tmp_path):
        t = Tracer("run-001")
        p = {"pattern_name": "重复推荐"}
        t.record_phase2_chunk("chunk_0.jsonl", [p])
        t.save(tmp_path)

        f = tmp_path / "trace" / "trace.json"
        assert f.exists()
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["run_id"] == "run-001"

    def test_get_trace_for_rule(self):
        t = Tracer("run-001")
        t.trace["R01"] = {"rule_name": "测试", "origin": {}, "validation": {}}
        assert t.get_trace_for_rule("R01") is not None
        assert t.get_trace_for_rule("R01")["rule_name"] == "测试"

    def test_get_trace_for_rule_missing(self):
        assert Tracer("run-001").get_trace_for_rule("N/A") is None


class TestTracerResolvePatternChunks:
    def test_by_id(self):
        t = Tracer("run-001")
        p = {"pattern_name": "测试"}
        t.record_phase2_chunk("chunk_0.jsonl", [p])
        assert t._resolve_pattern_chunks(p["pattern_id"]) == {"chunk_0.jsonl"}

    def test_by_name_exact(self):
        t = Tracer("run-001")
        t.record_phase2_chunk("chunk_0.jsonl", [{"pattern_name": "测试模式"}])
        assert t._resolve_pattern_chunks("测试模式") == {"chunk_0.jsonl"}

    def test_by_name_fuzzy(self):
        t = Tracer("run-001")
        t.record_phase2_chunk("chunk_0.jsonl", [{"pattern_name": "用户拒绝后仍推进"}])
        assert t._resolve_pattern_chunks("拒绝后") == {"chunk_0.jsonl"}

    def test_not_found(self):
        assert Tracer("run-001")._resolve_pattern_chunks("不存在") == set()
