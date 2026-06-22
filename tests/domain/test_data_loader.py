import json
import tempfile
from pathlib import Path
import pytest
from auto_qc.qc.domain.data_loader import (
    _match_columns, _preprocess_conversation, save_batches, load_conversations,
)
from auto_qc.qc.domain.schemas import Batch, Conversation


def test_match_columns_exact():
    headers = ["通话ID", "通话时间", "对话文本", "意向结果"]
    result = _match_columns(headers)
    assert result["id_col"] == "通话ID"
    assert result["conv_col"] == "对话文本"


def test_match_columns_fuzzy():
    headers = ["通话id", "时间", "对话", "意向"]
    result = _match_columns(headers)
    assert result["id_col"] == "通话id"


def test_match_columns_missing_raises():
    with pytest.raises(ValueError, match="未找到"):
        _match_columns(["仅有时间", "仅有对话"])


def test_preprocess_conversation():
    data = [
        {"ttsResult": "你好", "asrResult": "喂"},
        {"ttsResult": "请问是张三吗", "asrResult": ""},
    ]
    result = _preprocess_conversation(data)
    assert "AI: 你好" in result
    assert "用户: 喂" in result
    assert "AI: 请问是张三吗" in result


def test_save_and_load_batches():
    batches = [
        Batch(batch_id=1, conversations=[
            Conversation(id="1", time="2024-01-01", intent="A", conversation="hi"),
            Conversation(id="2", time="2024-01-02", intent="B", conversation="bye"),
        ]),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        save_batches(batches, tmpdir)
        saved = Path(tmpdir) / "batch_1.json"
        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data["batch_id"] == 1
        assert data["total"] == 2
        assert len(data["conversations"]) == 2
