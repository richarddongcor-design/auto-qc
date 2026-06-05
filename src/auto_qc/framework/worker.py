"""LLM API 调用封装——发 prompt、收 JSON、过滤 thinking block、json_repair"""
import os
import json
import asyncio
import re
import httpx
from dataclasses import dataclass, field
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv
from json_repair import repair_json

# 启动时自动加载项目根目录的 .env 文件
load_dotenv()

MAX_RETRIES = 3


# ─── Token 统计 ───

@dataclass
class TokenStats:
    """累计 Token 消耗统计。"""
    total_input: int = 0
    total_output: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input += input_tokens
        self.total_output += output_tokens

    @property
    def total(self) -> int:
        return self.total_input + self.total_output

    def summary(self) -> dict:
        return {
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
            "total_tokens": self.total,
        }


_token_stats = TokenStats()


def get_token_stats() -> TokenStats:
    """获取全局 Token 统计。"""
    return _token_stats


def reset_token_stats() -> None:
    """重置 Token 统计（每次新运行前调用）。"""
    _token_stats.total_input = 0
    _token_stats.total_output = 0


# ─── HTTP 传输层 ───


class _BearerAuthTransport(httpx.AsyncHTTPTransport):
    """
    自定义 HTTP 传输层，修复代理认证格式。
    某些 Anthropic 兼容代理（如 tongdaoren.cn）只接受 Authorization: Bearer，
    不接受 Anthropic SDK 默认的 x-api-key 格式。
    此处移除 x-api-key 头，确保只用 Bearer token 认证。
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        # 移除 Anthropic SDK 默认添加的 x-api-key，避免代理拒绝
        request.headers.pop("x-api-key", None)
        return await super().handle_async_request(request)


def _get_client() -> AsyncAnthropic:
    """从环境变量创建 Anthropic 客户端。"""
    transport = _BearerAuthTransport()
    return AsyncAnthropic(
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
        http_client=httpx.AsyncClient(transport=transport),
    )


def _get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "qwen3.6-plus"))


async def call_llm(prompt: str, max_tokens: int = 8000) -> str:
    """
    调用 LLM API，返回仅包含 text 内容的响应字符串。
    自动过滤 ThinkingBlock，只取 TextBlock。
    自动累计 Token 消耗到全局统计。
    """
    client = _get_client()
    model = _get_model()

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    # 记录 Token 消耗
    if response.usage:
        _token_stats.add(
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
        )

    texts = []
    for block in response.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)

    return "\n".join(texts)


async def call_llm_with_retry(prompt: str, max_tokens: int = 8000) -> str:
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
