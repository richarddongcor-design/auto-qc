"""统一 LLM 调用封装 — QC 和 PI 共享。

包含：
- TokenStats：Token 用量统计（全局 + 实例级）
- extract_json / extract_json_str：增强版 JSON 提取（合并 QC + PI 两种实现）
- call_llm / call_llm_with_retry：QC 兼容的简易调用
- LlmConfig：统一 LLM 配置
- LlmClient：统一 LLM 客户端（支持 system/user prompt、温度、API 级重试、Token 统计）
"""
import os
import json
import asyncio
import re
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError
from json_repair import repair_json

logger = logging.getLogger(__name__)

# ─── 默认值 ───
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10
DEFAULT_TIMEOUT = 300
DEFAULT_CONCURRENCY = 10


# ─── Token 统计 ───

@dataclass
class TokenStats:
    """Token 用量统计。"""
    total_input: int = 0
    total_output: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """累加 token 用量。"""
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

    def __str__(self) -> str:
        return (
            f"Token 用量: 输入 {self.total_input:,} | "
            f"输出 {self.total_output:,} | 总计 {self.total:,}"
        )


# 全局 Token 统计（QC 侧传统用法）
_token_stats = TokenStats()


def get_token_stats() -> TokenStats:
    """获取全局 Token 统计。"""
    return _token_stats


def reset_token_stats() -> None:
    """重置全局 Token 统计。"""
    _token_stats.total_input = 0
    _token_stats.total_output = 0


# ─── LLM 配置 ───

@dataclass
class LlmConfig:
    """LLM API 配置。空字段自动从进程环境变量补充。

    优先级（从低到高）：
    1. 代码默认值
    2. 进程环境变量（需先调用 load_env_config() 加载 .env 到 os.environ）
    3. 构造函数显式传入的值（通过 config.yaml 等）
    """
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: int = DEFAULT_RETRY_DELAY
    timeout: int = DEFAULT_TIMEOUT
    concurrency: int = DEFAULT_CONCURRENCY

    def __post_init__(self):
        """空字段从环境变量补充。"""
        if not self.api_key:
            self.api_key = os.getenv("LLM_API_KEY", "")
        if not self.base_url:
            self.base_url = os.getenv("LLM_BASE_URL", "")
        if not self.model:
            self.model = os.getenv("LLM_MODEL", "")


# ─── 客户端工厂 ───

def _build_client(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> AsyncOpenAI:
    """创建 AsyncOpenAI 客户端（禁用 SDK 内置重试，不使用系统代理）。"""
    return AsyncOpenAI(
        base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        api_key=api_key or os.getenv("LLM_API_KEY", ""),
        timeout=httpx.Timeout(timeout, connect=30.0),
        max_retries=0,
        http_client=httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(proxy=None),
        ),
    )


# ═══════════════════════════════════════════════════════════
# JSON 提取（合并 QC + PI 两种实现）
# ═══════════════════════════════════════════════════════════

def _find_first_json(text: str, open_ch: str, close_ch: str) -> Any | None:
    """通过括号匹配提取第一个完整 JSON 结构。"""
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
                        # dict 包裹格式：返回内部第一个非空数组
                        for v in obj.values():
                            if isinstance(v, list) and len(v) > 0:
                                return v
                    return obj
                except json.JSONDecodeError:
                    pass
    return None


def _heal_json(text: str) -> Any | None:
    """自修复常见 JSON 格式错误后尝试解析（不包含 repair_json —— 已在 extract_json 中先尝试过）。"""
    # 1. 修复尾逗号后尝试
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    if cleaned != text:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # 2. 替换单引号为双引号后尝试
    try:
        sq_fixed = re.sub(r"(?<!\\)'", '"', text)
        return json.loads(sq_fixed)
    except json.JSONDecodeError:
        pass

    # 3. 修复未加引号的键名后尝试（含中文字段名）
    try:
        uq_fixed = re.sub(
            r'(?<=[{,])\s*([a-zA-Z_一-鿿][a-zA-Z0-9_一-鿿]*)\s*(?=\s*:)',
            r'"\1"',
            text,
        )
        return json.loads(uq_fixed)
    except json.JSONDecodeError:
        pass

    return None


def extract_json(text: str) -> Any:
    """从 LLM 输出文本中提取并解析 JSON，返回 Python 对象。

    策略顺序（先整体修复、再局部匹配）：
    1. 直接解析
    2. Markdown 代码块提取
    3. json_repair 整体修复（处理尾逗号、单引号等）
    4. 找第一个 JSON 对象 `{...}`（含 dict → array 解包）
    5. 找第一个 JSON 数组 `[...]`
    6. 逐级自修复（尾逗号、单引号、未引号键名）
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
        return json.loads(repair_json(text))
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
    raise ValueError(f"无法从 LLM 响应中提取有效 JSON:\n{preview}")


def extract_json_str(text: str) -> str:
    """从 LLM 输出中提取 JSON 并序列化为字符串（兼容 QC 旧接口）。"""
    result = extract_json(text)
    return json.dumps(result, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════
# 兼容接口（QC 侧使用）
# ═══════════════════════════════════════════════════════════

async def call_llm(prompt: str, max_tokens: int = 8000) -> str:
    """简单的 LLM 调用，仅 user prompt（QC 兼容接口）。"""
    client = _build_client()
    model = os.getenv("LLM_MODEL", "deepseek-chat")
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
    """带简单指数退避重试的 LLM 调用（QC 兼容接口）。"""
    last_error = None
    for attempt in range(DEFAULT_MAX_RETRIES):
        try:
            return await call_llm(prompt, max_tokens)
        except Exception as e:
            last_error = e
            if attempt < DEFAULT_MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(
        f"LLM 调用失败（重试 {DEFAULT_MAX_RETRIES} 次后）: {last_error}"
    )


# ═══════════════════════════════════════════════════════════
# LlmClient（统一 LLM 客户端，替代 Scheduler 的原始实现）
# ═══════════════════════════════════════════════════════════

class LlmClient:
    """统一 LLM 客户端。

    支持 system/user prompt、温度控制、API 级重试（含 429/5xx 区别处理）、
    Token 用量统计。不处理 JSON 解析和 content 级重试——由调用方负责。
    """

    def __init__(self, config: LlmConfig):
        self.config = config
        self._client: AsyncOpenAI | None = None
        self._usage = TokenStats()

    @property
    def usage(self) -> TokenStats:
        return self._usage

    @property
    def client(self) -> AsyncOpenAI:
        """惰性初始化 AsyncOpenAI 客户端。"""
        if self._client is None:
            if not self.config.api_key:
                raise ValueError(
                    "未检测到 API key。请在 .env 文件中设置 LLM_API_KEY，"
                    "或在 config.yaml 的 llm.api_key 中手动设置"
                )
            if not self.config.base_url:
                raise ValueError(
                    "未检测到 base_url。请在 .env 文件中设置 LLM_BASE_URL，"
                    "或在 config.yaml 的 llm.base_url 中手动设置"
                )
            self._client = _build_client(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                timeout=self.config.timeout,
            )
        return self._client

    async def call_async(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int = 16384,
    ) -> tuple[str | None, str | None]:
        """执行 LLM API 调用（含 API 级重试）。

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            temperature: 温度参数（None 使用模型默认值）
            max_tokens: 最大输出 token 数

        Returns:
            (raw_text, None) 成功
            (None, error_code) 失败，error_code 如 "api_error_429"、"network_error"
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(1, self.config.max_retries + 1):
            try:
                kwargs: dict[str, Any] = dict(
                    model=self.config.model or "deepseek-chat",
                    max_tokens=max_tokens,
                    messages=messages,
                    timeout=self.config.timeout,
                )
                if temperature is not None:
                    kwargs["temperature"] = temperature
                response = await self.client.chat.completions.create(**kwargs)
                raw_text = response.choices[0].message.content or ""
                if hasattr(response, "usage") and response.usage:
                    self._usage.add(
                        response.usage.prompt_tokens or 0,
                        response.usage.completion_tokens or 0,
                    )
                return raw_text, None
            except APIStatusError as e:
                status = e.status_code
                if status == 429:
                    delay = self.config.retry_delay * attempt
                    logger.warning("  API 限流 (429)，等待 %ds...", delay)
                elif status >= 500:
                    delay = (self.config.retry_delay * 2) * attempt
                    logger.warning("  服务端错误 (%d)，等待 %ds...", status, delay)
                elif status == 400:
                    logger.error("  请求参数错误 (400): %s", e)
                    return None, "api_error_400"
                else:
                    delay = self.config.retry_delay * attempt
                    logger.warning("  API 错误 (%d): %s", status, e)
                if attempt == self.config.max_retries:
                    return None, f"api_error_{status}"
                await asyncio.sleep(delay)
            except (APITimeoutError, APIConnectionError) as e:
                logger.warning("  网络/超时错误: %s", e)
                if attempt == self.config.max_retries:
                    return None, "network_error"
                await asyncio.sleep(self.config.retry_delay * attempt)
            except Exception as e:
                logger.warning("  未知 API 错误: %s", e)
                if attempt == self.config.max_retries:
                    return None, "api_call_failed"
                await asyncio.sleep(self.config.retry_delay * attempt)

        return None, "max_retries_exceeded"
