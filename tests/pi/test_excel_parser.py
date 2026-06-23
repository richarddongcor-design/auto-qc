"""PI 模块 — Excel 数据解析 + chunk 切分测试。"""

import json

import pytest
from auto_qc.pi.utils.excel_parser import generate_phase1_report, split_into_chunks


class TestSplitIntoChunks:
    def test_basic_split(self, tmp_path):
        dialogues = [{"id": str(i), "turns": []} for i in range(10)]
        count = split_into_chunks(dialogues, chunk_size=3, output_dir=tmp_path)
        assert count == 4  # 10/3 → 4 chunks

        chunks = sorted(tmp_path.glob("chunk_*.jsonl"))
        assert len(chunks) == 4

        # first chunk: 3 items
        lines = chunks[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

        # last chunk: 1 item
        lines = chunks[-1].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_exact_split(self, tmp_path):
        """chunk_size 整除时每 chunk 数量一致。"""
        dialogues = [{"id": str(i), "turns": []} for i in range(9)]
        count = split_into_chunks(dialogues, chunk_size=3, output_dir=tmp_path)
        assert count == 3
        for c in sorted(tmp_path.glob("chunk_*.jsonl")):
            assert len(c.read_text(encoding="utf-8").strip().splitlines()) == 3

    def test_empty_list(self, tmp_path):
        count = split_into_chunks([], chunk_size=10, output_dir=tmp_path)
        assert count == 0
        assert list(tmp_path.glob("chunk_*.jsonl")) == []

    def test_chunk_size_zero_raises(self, tmp_path):
        with pytest.raises(ValueError, match="chunk_size 必须大于 0"):
            split_into_chunks([{"id": "1"}], chunk_size=0, output_dir=tmp_path)

    def test_chunk_size_negative_raises(self, tmp_path):
        with pytest.raises(ValueError, match="chunk_size 必须大于 0"):
            split_into_chunks([{"id": "1"}], chunk_size=-1, output_dir=tmp_path)

    def test_output_dir_automatically_created(self, tmp_path):
        new_dir = tmp_path / "nonexistent" / "subdir"
        assert not new_dir.exists()
        split_into_chunks([{"id": "1"}], chunk_size=1, output_dir=new_dir)
        assert new_dir.exists()

    def test_jsonl_format(self, tmp_path):
        """验证每行均为合法 JSON。"""
        dialogues = [{"id": "1", "turns": [{"role": "ai", "content": "你好"}]}]
        split_into_chunks(dialogues, chunk_size=1, output_dir=tmp_path)
        obj = json.loads((tmp_path / "chunk_0.jsonl").read_text(encoding="utf-8"))
        assert obj["id"] == "1"
        assert obj["turns"][0]["content"] == "你好"

    def test_chunk_file_numbering(self, tmp_path):
        """验证 chunk 文件从 0 开始递增编号。"""
        dialogues = [{"id": str(i)} for i in range(5)]
        split_into_chunks(dialogues, chunk_size=2, output_dir=tmp_path)
        names = sorted(c.name for c in tmp_path.glob("chunk_*.jsonl"))
        assert names == ["chunk_0.jsonl", "chunk_1.jsonl", "chunk_2.jsonl"]


class TestGeneratePhase1Report:
    def test_basic_report(self):
        report = generate_phase1_report(
            total=100, success=95, errors=[], chunk_count=10, avg_turns=5.5,
        )
        assert "Phase 1" in report
        assert "总对话数: 100" in report
        assert "成功解析: 95" in report
        assert "解析失败: 0" in report
        assert "生成 chunk: 10 个" in report
        assert "平均对话轮次: 5.5" in report
        assert "错误详情" not in report

    def test_report_with_errors(self):
        report = generate_phase1_report(
            total=50, success=48,
            errors=["行3: 缺少 id 字段", "行7: JSON 格式错误"],
            chunk_count=5, avg_turns=3.2,
        )
        assert "解析失败: 2" in report
        assert "错误详情" in report
        assert "缺少 id 字段" in report
        assert "JSON 格式错误" in report

    def test_no_dialogues(self):
        report = generate_phase1_report(
            total=0, success=0, errors=[], chunk_count=0, avg_turns=0.0,
        )
        assert "总对话数: 0" in report
        assert "平均对话轮次: 0.0" in report

    def test_markdown_format(self):
        """验证报告以 Markdown 标题开头。"""
        report = generate_phase1_report(
            total=10, success=10, errors=[], chunk_count=2, avg_turns=4.0,
        )
        assert report.startswith("# ")
        # 有空行分隔段落
        assert any(line == "" for line in report.splitlines())
