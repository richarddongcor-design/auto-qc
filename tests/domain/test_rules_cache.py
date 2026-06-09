"""规则缓存测试"""
import hashlib
import json
from pathlib import Path
import tempfile
from auto_qc.domain.rules import load_or_parse_rules, _hash_file
from auto_qc.domain.schemas import RulePackage


def test_hash_file_consistent():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write("## R01: 测试\n\n**严重程度**: 高\n\n**描述**: d\n\n**检测逻辑**: l\n")
        path = f.name
    try:
        h1 = _hash_file(path)
        h2 = _hash_file(path)
        assert h1 == h2
    finally:
        Path(path).unlink()


def test_load_or_parse_rules_from_md():
    """从 md 解析应正常工作。"""
    md_content = "## R01: 测试\n\n**严重程度**: 高\n\n**描述**: d\n\n**检测逻辑**: l\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(md_content)
        md_path = f.name
    try:
        pkg = load_or_parse_rules(md_path=md_path, cache_dir=tempfile.mkdtemp())
        assert isinstance(pkg, RulePackage)
        assert len(pkg.rules) == 1
        assert pkg.rules[0].rule_id == "R01"
    finally:
        Path(md_path).unlink()


def test_cache_hit_returns_same_data():
    """缓存命中应返回相同数据。"""
    md_content = "## R01: 测试\n\n**严重程度**: 高\n\n**描述**: d\n\n**检测逻辑**: l\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(md_content)
        md_path = f.name
    with tempfile.TemporaryDirectory() as cache_dir:
        try:
            # 第一次：解析 md → 写缓存
            pkg1 = load_or_parse_rules(md_path=md_path, name="test-rules", cache_dir=cache_dir)
            # 第二次：命中缓存
            pkg2 = load_or_parse_rules(name="test-rules", cache_dir=cache_dir)
            assert len(pkg2.rules) == 1
            assert pkg2.rules[0].rule_id == "R01"
        finally:
            Path(md_path).unlink()


def test_cache_miss_raises_without_md():
    """缓存未命中且无 md_path 应抛异常。"""
    import pytest
    with tempfile.TemporaryDirectory() as cache_dir:
        with pytest.raises(FileNotFoundError):
            load_or_parse_rules(name="nonexistent", cache_dir=cache_dir)
