import json
import pytest
from auto_qc.framework.worker import extract_json


def test_extract_valid_json():
    text = '{"batch_id": 1, "results": []}'
    result = extract_json(text)
    parsed = json.loads(result)
    assert parsed["batch_id"] == 1


def test_extract_with_markdown_wrapper():
    text = '```json\n{"batch_id": 1, "results": []}\n```'
    result = extract_json(text)
    parsed = json.loads(result)
    assert parsed["batch_id"] == 1


def test_extract_trailing_comma():
    text = '{"batch_id": 1, "results": [],}'
    result = extract_json(text)
    parsed = json.loads(result)
    assert parsed["batch_id"] == 1


def test_extract_invalid_raises():
    with pytest.raises(ValueError):
        extract_json("这是纯文本，不是 JSON")
