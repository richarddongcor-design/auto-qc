"""LLM API 调用封装——发 prompt、收 JSON、过滤 thinking block、json_repair"""
import os
import json
import asyncio
import re
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from json_repair import repair_json

MAX_RETRIES = 3


def _get_client() -> AsyncAnthropic:
    """从环境变量创建 Anthropic 客户端。"""
    return AsyncAnthropic(
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
    )


def _get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6"))


async def call_llm(prompt: str, max_tokens: int = 4000) -> str:
    """
    调用 LLM API，返回仅包含 text 内容的响应字符串。
    自动过滤 ThinkingBlock，只取 TextBlock。
    """
    client = _get_client()
    model = _get_model()

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    texts = []
    for block in response.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)

    return "\n".join(texts)


async def call_llm_with_retry(prompt: str, max_tokens: int = 4000) -> str:
    """
    调用 LLM，失败时重试最多 MAX_RETRIES 次。
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return await call_llm(prompt, max_tokens)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s 退避

    raise RuntimeError(f"LLM 调用失败（重试 {MAX_RETRIES} 次后）: {last_error}")


def extract_json(text: str) -> str:
    """
    从 LLM 返回的文本中提取 JSON。
    先用 json_repair 修复常见格式问题，再验证解析。
    """
    # 尝试直接解析
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 尝试 json_repair 修复
    try:
        repaired = repair_json(text)
        json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, Exception):
        pass

    # 尝试从 text 中提取 JSON 块（```json ... ```）
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        inner = match.group(1).strip()
        try:
            repair_json(inner)
            return inner
        except Exception:
            pass

    raise ValueError("无法从 LLM 响应中提取有效 JSON")
