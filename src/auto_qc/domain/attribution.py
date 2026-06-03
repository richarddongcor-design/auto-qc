"""内置归因规则"""
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates"


def get_attribution_rules_path() -> str:
    """返回内置归因规则文件路径。"""
    path = _TEMPLATES_DIR / "attribution-rules.md"
    if not path.exists():
        raise FileNotFoundError(f"内置归因规则文件不存在: {path}")
    return str(path)


def get_attribution_rules_text() -> str:
    """返回内置归因规则的文本内容。"""
    return Path(get_attribution_rules_path()).read_text(encoding="utf-8")
