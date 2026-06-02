"""测试 data_loader.py 的列匹配和预处理功能"""
import json
import tempfile
from pathlib import Path

import pytest

# Make sure we can import from the same directory
import sys
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import match_columns, preprocess_conversation, load_excel


def test_match_columns_exact():
    """测试精确列名匹配"""
    headers = ["id", "时间", "对话文本", "意向结果"]
    result = match_columns(headers)
    assert result["id_col"] == "id"
    assert result["intent_col"] == "意向结果"


def test_match_columns_fuzzy():
    """测试模糊列名匹配（关键词）"""
    headers = ["call_id", "通话时间", "conversation", "intent_result"]
    result = match_columns(headers)
    assert result["id_col"] == "call_id"
    assert result["time_col"] == "通话时间"
    assert result["conv_col"] == "conversation"
    assert result["intent_col"] == "intent_result"


def test_match_columns_missing():
    """测试缺失列时报错"""
    headers = ["id", "时间"]
    with pytest.raises(ValueError):
        match_columns(headers)


def test_preprocess_conversation():
    """测试对话 JSON → 可读文本转换"""
    conv_json = [
        {"ttsResult": "你好，请问是张三吗？", "asrResult": "用户无应答"},
        {"ttsResult": "您好，我是猎聘这边的...", "asrResult": "是的哪位？"}
    ]
    result = preprocess_conversation(conv_json)
    assert "AI: 你好，请问是张三吗？" in result
    assert "用户: 用户无应答" in result
    assert "AI: 您好，我是猎聘这边的..." in result
    assert "用户: 是的哪位？" in result


def test_load_excel_and_batch(tmp_path):
    """测试完整加载+拆分流程"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "时间", "对话文本", "意向结果"])
    for i in range(1, 251):  # 250 条
        conv = json.dumps([
            {"ttsResult": f"你好 {i}", "asrResult": "嗯"}
        ], ensure_ascii=False)
        ws.append([i, "2026-06-01 10:00:00", conv, "A(有意向)"])

    test_xlsx = str(tmp_path / "test.xlsx")
    wb.save(test_xlsx)

    result = load_excel(test_xlsx, batch_size=100)
    assert result["total"] == 250
    assert result["num_batches"] == 3  # 250 / 100 = 3 批
    assert len(result["batches"][0]) == 100
    assert len(result["batches"][2]) == 50  # 最后一批
