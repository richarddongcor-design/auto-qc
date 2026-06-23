"""PI 模块 — RunState 状态机测试。"""

import json
from pathlib import Path

import pytest
from auto_qc.pi.engine.pipeline import RunState


class TestRunState:
    def test_initial_state(self):
        state = RunState("run-001")
        assert state.run_id == "run-001"
        assert state.started_at is not None

        for i in range(1, 7):
            p = state.phases[str(i)]
            assert p["status"] == "pending"
            assert p["started_at"] is None
            assert p["finished_at"] is None

    def test_mark_running(self):
        state = RunState("test")
        state.mark_running(1)
        assert state.phases["1"]["status"] == "running"
        assert state.phases["1"]["started_at"] is not None
        assert state.phases["1"]["finished_at"] is None

    def test_mark_completed(self):
        state = RunState("test")
        state.mark_completed(2)
        assert state.phases["2"]["status"] == "completed"
        assert state.phases["2"]["finished_at"] is not None

    def test_mark_completed_with_result(self):
        state = RunState("test")
        result = {"chunk_count": 10, "dialogue_count": 100}
        state.mark_completed(1, result)
        assert state.phases["1"]["result"] == result

    def test_mark_failed(self):
        state = RunState("test")
        state.mark_failed(3, "模拟错误")
        assert state.phases["3"]["status"] == "failed"
        assert state.phases["3"]["finished_at"] is not None
        assert state.phases["3"]["error"] == "模拟错误"

    def test_mark_failed_empty_error(self):
        state = RunState("test")
        state.mark_failed(4)
        assert state.phases["4"]["status"] == "failed"
        assert state.phases["4"]["finished_at"] is not None
        assert state.phases["4"].get("error", "") == ""

    def test_save(self, tmp_path):
        state = RunState("test-save")
        state.mark_completed(1, {"done": True})
        state.mark_running(2)
        state.save(tmp_path)

        sf = tmp_path / ".state.json"
        assert sf.exists()

        raw = json.loads(sf.read_text(encoding="utf-8"))
        assert raw["run_id"] == "test-save"
        assert raw["phases"]["1"]["status"] == "completed"
        assert raw["phases"]["2"]["status"] == "running"

    def test_load(self, tmp_path):
        original = RunState("test-load")
        original.mark_completed(5, {"pattern_count": 20})
        original.save(tmp_path)

        loaded = RunState.load(tmp_path)
        assert loaded is not None
        assert loaded.run_id == "test-load"
        assert loaded.phases["5"]["status"] == "completed"
        assert loaded.phases["5"]["result"]["pattern_count"] == 20

    def test_load_nonexistent_returns_none(self):
        assert RunState.load(Path("nonexistent_path_xyz")) is None

    def test_phases_independent(self):
        """各 phase 状态互不影响。"""
        state = RunState("test")
        state.mark_completed(1)
        state.mark_failed(3)
        state.mark_running(5)

        assert state.phases["1"]["status"] == "completed"
        assert state.phases["2"]["status"] == "pending"
        assert state.phases["3"]["status"] == "failed"
        assert state.phases["4"]["status"] == "pending"
        assert state.phases["5"]["status"] == "running"
        assert state.phases["6"]["status"] == "pending"
