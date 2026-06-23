"""PI 模块 — JSON 提取与修复工具测试。"""

import pytest
from auto_qc.pi.utils.json_utils import extract_json_from_text, heal_json


class TestExtractJsonFromText:
    def test_pure_json_object(self):
        assert extract_json_from_text('{"key": "value", "num": 42}') == {
            "key": "value",
            "num": 42,
        }

    def test_pure_json_array(self):
        assert extract_json_from_text('[{"id": 1}, {"id": 2}]') == [
            {"id": 1},
            {"id": 2},
        ]

    def test_markdown_json_block(self):
        text = "```json\n{\"key\": \"value\"}\n```"
        assert extract_json_from_text(text) == {"key": "value"}

    def test_markdown_json_block_inline(self):
        """```json{...}``` 无换行场景。"""
        text = '```json{"key": "value"}```'
        assert extract_json_from_text(text) == {"key": "value"}

    def test_text_before_and_after(self):
        text = """
分析结果如下：
```json
{"patterns": [{"name": "A"}]}
```
以上是全部数据。
"""
        result = extract_json_from_text(text)
        # 走 markdown 提取路径，返回原始 dict
        assert result == {"patterns": [{"name": "A"}]}

    def test_trailing_text_after_object_with_array(self):
        """dict 包裹的数组应解包。"""
        text = """{"patterns": [{"name": "A"}, {"name": "B"}]}
以上是本次分析，共 2 个模式。"""
        result = extract_json_from_text(text)
        assert len(result) == 2
        assert result[0]["name"] == "A"

    def test_empty_object(self):
        assert extract_json_from_text("{}") == {}

    def test_empty_array(self):
        assert extract_json_from_text("[]") == []

    def test_nested_structure(self):
        text = '{"level1": {"level2": [1, 2, 3]}}'
        assert extract_json_from_text(text) == {"level1": {"level2": [1, 2, 3]}}

    def test_plain_markdown_code_block_no_json(self):
        """普通 markdown 代码块（无 ```json 标记）也可能提取。"""
        text = "```\n{\"key\": \"value\"}\n```"
        assert extract_json_from_text(text) == {"key": "value"}

    def test_invalid_no_json_raises(self):
        with pytest.raises(ValueError, match="无法从输出中提取合法 JSON"):
            extract_json_from_text("完全没有 JSON 内容的一段文字")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="无法从输出中提取合法 JSON"):
            extract_json_from_text("")


class TestHealJson:
    """heal_json 测试 — 优先测试不依赖 json_repair 的修复策略。"""

    def test_trailing_comma_in_object(self):
        assert heal_json('{"key": "value",}') == {"key": "value"}

    def test_trailing_comma_in_array(self):
        assert heal_json("[1, 2, 3,]") == [1, 2, 3]

    def test_single_quotes(self):
        assert heal_json("{'key': 'value'}") == {"key": "value"}

    def test_mixed_quotes(self):
        assert heal_json('{"key": \'value\'}') == {"key": "value"}

    def test_already_valid(self):
        assert heal_json('{"key": "value"}') == {"key": "value"}

    def test_heal_with_markdown_block(self):
        text = "```json\n{\"key\": \"value\",}\n```"
        assert heal_json(text) == {"key": "value"}

    def test_nested_trailing_commas(self):
        result = heal_json('{"items": [1, 2,], "name": "test",}')
        assert result == {"items": [1, 2], "name": "test"}

    def test_unquoted_keys(self):
        """未加引号的键名应被自动添加引号。"""
        result = heal_json('{key: "value", 姓名: "张三"}')
        assert result is not None
        assert result.get("key") == "value"
        assert result.get("姓名") == "张三"

    def test_truncated_object(self):
        """json_repair 补全截断 JSON。"""
        result = heal_json('{"key": "value"')
        assert result is not None
        assert isinstance(result, dict)
        assert result.get("key") == "value"

    def test_truncated_array(self):
        """json_repair 补全截断数组。"""
        result = heal_json("[1, 2, 3")
        assert result is not None
        assert isinstance(result, list)
        assert 1 in result
        assert 2 in result
        assert 3 in result

    def test_all_heal_strategies_fail_returns_none(self):
        """所有修复策略均失败时返回 None（而非抛异常）。"""
        text = "\x00\x01\x02"  # 不可解析的二进制内容
        result = heal_json(text)
        assert result is None

    def test_extra_text_around_json_object(self):
        """JSON 对象前后有额外文字也能修复。"""
        result = heal_json("结果: {status: 'ok'}")
        assert result is not None
        assert isinstance(result, dict)
