"""统一 LLM 调用封装 — QC 和 PI 共享。"""
import os
import json
import asyncio
import re
import httpx
from dataclasses import dataclass
from openai import AsyncOpenAI
from json_repair import repair_json

MAX_RETRIES = 3


@dataclass
class TokenStats:
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
    return _token_stats


def reset_token_stats() -> None:
    _token_stats.total_input = 0
    _token_stats.total_output = 0


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        timeout=httpx.Timeout(120.0, connect=30.0),
    )


def _get_model() -> str:
    return os.environ.get("LLM_MODEL", "deepseek-chat")


async def call_llm(prompt: str, max_tokens: int = 8000) -> str:
    client = _get_client()
    model = _get_model()
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    if usage:
        _token_stats.add(
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
        )
    return response.choices[0].message.content or ""


async def call_llm_with_retry(prompt: str, max_tokens: int = 8000) -> str:
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return await call_llm(prompt, max_tokens)
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"LLM 调用失败（重试 {MAX_RETRIES} 次后）: {last_error}")


def extract_json(text: str) -> str:
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    try:
        repaired = repair_json(text)
        json.loads(repaired)
        return repaired
    except (json.JSONDecodeError, Exception):
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        inner = match.group(1).strip()
        try:
            repair_json(inner)
            return inner
        except Exception:
            pass
    raise ValueError("无法从 LLM 响应中提取有效 JSON")
