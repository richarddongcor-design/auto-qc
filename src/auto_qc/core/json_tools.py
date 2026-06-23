"""统一 JSON 预处理 — 提取、修复、校验。

纯函数工具层，不依赖 LLM 客户端 / openai / httpx。
QC 和 PI 共用同一套 JSON 提取和修复逻辑。

用法:
    from auto_qc.core.json_tools import extract_json, repair_json

    data = extract_json(llm_output)       # 从 LLM 输出提取 JSON → Python 对象
    text = extract_json_str(llm_output)   # 提取后序列化为 JSON 字符串
    repaired = repair_json(broken_text)   # 修复常见 JSON 错误
"""
import json
import re
from typing import Any

from json_repair import repair_json as _repair_json_lib


# ═══════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════


def _find_first_json(text: str, open_ch: str, close_ch: str) -> Any | None:
    """通过括号匹配提取第一个完整 JSON 结构。

    如果匹配到的是 dict，且内部含非空数组，优先返回该数组
    （处理 LLM 常输出的 `{"patterns": [...]}` 包裹格式）。
    """
    count = 0
    start = None
    for i, ch in enumerate(text):
        if ch == open_ch:
            if count == 0:
                start = i
            count += 1
        elif ch == close_ch:
            count -= 1
            if count == 0 and start is not None:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        for v in obj.values():
                            if isinstance(v, list) and len(v) > 0:
                                return v
                    return obj
                except json.JSONDecodeError:
                    pass
    return None


# ═══════════════════════════════════════════════════════════
# 公开接口
# ═══════════════════════════════════════════════════════════


def extract_json(text: str) -> Any:
    """从文本中提取并解析 JSON，返回 Python 对象。

    策略顺序（先整体修复、再局部匹配）：
    1. 直接解析
    2. Markdown 代码块提取（```json ... ```）
    3. json_repair 整体修复（尾逗号、单引号、截断等）
    4. 找第一个完整 JSON 对象 `{...}`（含 dict → array 解包）
    5. 找第一个完整 JSON 数组 `[...]`
    6. 逐级自修复（尾逗号 → 单引号 → 未引号键名）
    """
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown 代码块
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. json_repair 整体修复（在 bracket 匹配之前，防止内部空数组/对象被误提取）
    try:
        return json.loads(_repair_json_lib(text))
    except Exception:
        pass

    # 4. 找第一个完整 JSON 对象（含 dict → array 解包）
    result = _find_first_json(text, '{', '}')
    if result is not None:
        return result

    # 5. 找第一个完整 JSON 数组
    result = _find_first_json(text, '[', ']')
    if result is not None:
        return result

    # 6. 逐级自修复（尾逗号 → 单引号 → 未引号键名）
    result = _heal_json(text)
    if result is not None:
        return result

    preview = text[:500] + ("..." if len(text) > 500 else "")
    raise ValueError(f"无法从文本中提取有效 JSON:\n{preview}")


def extract_json_str(text: str) -> str:
    """从文本中提取 JSON 并序列化为字符串。"""
    result = extract_json(text)
    return json.dumps(result, ensure_ascii=False)


def repair_json(text: str) -> str | None:
    """修复常见 JSON 格式错误后返回合法 JSON 字符串。

    处理（按顺序）：
    - 尾逗号 (trailing comma)
    - 单引号代替双引号
    - 键名缺少引号
    - json_repair 库兜底

    Returns:
       修复后的 JSON 字符串，或 None（所有修复策略都失败）
    """
    original = text.strip()
    if not original:
        return None

    # 1. 修复尾逗号
    cleaned = re.sub(r",\s*([}\]])", r"\1", original)
    if cleaned != original:
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            pass

    # 2. 修复单引号
    try:
        sq_fixed = re.sub(r"(?<!\\)'", '"', original)
        json.loads(sq_fixed)
        return sq_fixed
    except json.JSONDecodeError:
        pass

    # 3. 修复未加引号的键名（含中文）
    try:
        uq_fixed = re.sub(
            r'(?<=[{,])\s*([a-zA-Z_一-鿿][a-zA-Z0-9_一-鿿]*)\s*(?=\s*:)',
            r'"\1"',
            original,
        )
        json.loads(uq_fixed)
        return uq_fixed
    except json.JSONDecodeError:
        pass

    # 4. json_repair 库兜底
    try:
        return _repair_json_lib(original)
    except Exception:
        return None


def _heal_json(text: str) -> Any | None:
    """自修复后尝试解析（不包含 repair_json —— 已在 extract_json 中先尝试过）。"""
    result = repair_json(text)
    if result is not None:
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            pass
    return None
