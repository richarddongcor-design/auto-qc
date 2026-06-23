"""OpenAI 兼容 API 子任务调度器。

通过 LlmClient（core/llm.py）委托 LLM 调用，自身聚焦内容级重试
（JSON 解析失败、schema 校验失败时追加反馈后重试）。
支持并发控制、重试、流控、超时。
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from auto_qc.core.llm import LlmConfig, LlmClient, TokenStats, extract_json
from auto_qc.pi.engine.validator import validate_output

logger = logging.getLogger(__name__)

# 内容质量重试模板：仅 JSON 解析或 schema 校验失败时追加到 prompt
RETRY_PROMPT_TEMPLATE = """\n\n⚠️ 上一次输出校验失败：{error}\n请修正后重新输出。要求：\n1. 回复**只包含** JSON 数组，以 `[` 开头、以 `]` 结尾\n2. JSON 前后不要有任何说明文字或 markdown 标记\n3. 确保所有字符串用双引号包裹，没有尾逗号\n4. **字段名必须是英文**：pattern_name、description、severity、found_count、total_checked、examples——不要翻译成中文"""


class Scheduler:
    """LLM 子任务调度器。

    通过 LlmClient（core/llm）执行 API 调用，自身负责 content 级重试
    （JSON 解析失败、schema 校验失败时追加错误反馈到 prompt 后重试）。
    """

    def __init__(self, config: LlmConfig):
        self.config = config
        self._llm_client = LlmClient(config)

    @property
    def usage(self) -> TokenStats:
        """委托给 LlmClient 的 Token 统计。"""
        return self._llm_client.usage

    def run_task(
        self,
        system_prompt: str,
        user_prompt: str,
        output_file: Path,
        validator_phase: str | None = None,
        temperature: float | None = None,
    ) -> tuple[bool, Any, str]:
        """执行单个 LLM 任务。

        重试策略：
        - API 错误（网络、限流、服务端）→ 由 LlmClient 内部处理
        - 内容错误（JSON 解析、schema 校验）→ 追加错误反馈后重试

        此方法为同步包装，内部通过 asyncio.run 调用异步实现。
        """
        return asyncio.run(
            self._run_task_async(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_file=output_file,
                validator_phase=validator_phase,
                temperature=temperature,
            )
        )

    async def _run_task_async(
        self,
        system_prompt: str,
        user_prompt: str,
        output_file: Path,
        validator_phase: str | None = None,
        temperature: float | None = None,
    ) -> tuple[bool, Any, str]:
        """异步执行单个 LLM 任务（含 content 级重试）。

        与 run_task 签名相同，但返回协程。处理：
        1. API 调用（委托 LlmClient）
        2. JSON 提取
        3. Schema 校验
        4. 输出文件写入
        """
        content_prompt = user_prompt

        for attempt in range(1, self.config.max_retries + 1):
            logger.info(f"  LLM 任务 (attempt {attempt}/{self.config.max_retries})...")

            # 1. API 调用（由 LlmClient 处理 API 级重试）
            raw_text, api_error = await self._llm_client.call_async(
                system_prompt=system_prompt,
                user_prompt=content_prompt,
                temperature=temperature,
            )
            if api_error:
                if attempt == self.config.max_retries:
                    return False, None, api_error
                continue

            # 2. JSON 解析 + 自修复
            assert raw_text is not None
            try:
                data = extract_json(raw_text)
            except ValueError:
                data = None

            if data is None:
                error = "无法从输出中提取合法 JSON"
                logger.warning(f"  {error}")
                if attempt == self.config.max_retries:
                    return False, None, "invalid_json"
                content_prompt += RETRY_PROMPT_TEMPLATE.format(error=error)
                continue

            # 3. Schema 校验
            if validator_phase:
                valid, msg = validate_output(validator_phase, data)
                if not valid:
                    logger.warning(f"  Schema 校验失败: {msg}")
                    if attempt == self.config.max_retries:
                        return False, None, f"schema_validation_failed: {msg}"
                    content_prompt += RETRY_PROMPT_TEMPLATE.format(error=msg)
                    continue

            # 成功：写入结果文件
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True, data, ""

        return False, None, "max_retries_exceeded"

    def run_tasks_batch(
        self,
        tasks: list[dict],
        system_prompt: str,
        validator_phase: str | None = None,
        temperature: float | None = None,
    ) -> list[tuple[bool, Any, str]]:
        """批量执行多个 LLM 任务（并发控制）。

        Args:
            tasks: 任务列表，每个 task 包含:
                - user_prompt: 用户 prompt
                - output_file: 输出文件路径（str 或 Path）
                可选:
                - temperature: 该任务专用的 temperature（覆盖 batch 级设置）
                - system_prompt: 该任务专用的 system_prompt（覆盖 batch 级设置）
            system_prompt: 系统 prompt（所有任务共用，可被 task 级覆盖）
            validator_phase: 校验阶段名称

        Returns:
            每个任务的结果列表: [(success, data, error), ...]
        """
        return asyncio.run(
            self._run_batch_async(
                tasks=tasks,
                system_prompt=system_prompt,
                validator_phase=validator_phase,
                temperature=temperature,
            )
        )

    async def _run_batch_async(
        self,
        tasks: list[dict],
        system_prompt: str,
        validator_phase: str | None = None,
        temperature: float | None = None,
    ) -> list[tuple[bool, Any, str]]:
        """异步批量执行（并发控制）。"""
        concurrency = min(self.config.concurrency, len(tasks))
        sem = asyncio.Semaphore(concurrency)

        async def run_one(task: dict) -> tuple[bool, Any, str]:
            async with sem:
                output_file = (
                    Path(task["output_file"])
                    if isinstance(task["output_file"], str)
                    else task["output_file"]
                )
                task_temp = task.get("temperature", temperature)
                task_sys = task.get("system_prompt", system_prompt)
                return await self._run_task_async(
                    system_prompt=task_sys,
                    user_prompt=task["user_prompt"],
                    output_file=output_file,
                    validator_phase=validator_phase,
                    temperature=task_temp,
                )

        results = await asyncio.gather(*[run_one(t) for t in tasks])

        for idx, (success, data, error) in enumerate(results):
            logger.info(
                f"  任务 [{idx+1}/{len(tasks)}] "
                f"{'完成' if success else '失败'}: {error}"
            )

        return results
