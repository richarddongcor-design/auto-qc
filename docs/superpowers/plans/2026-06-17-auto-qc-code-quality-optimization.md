# auto-qc 代码质量优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 四项独立代码质量优化：修复测试导入、统一重试机制、提取交叉验证函数、TokenStats 依赖注入。不引入新功能，不改变外部行为。

**Architecture:** 新增 `retry.py` 封装 API 重试；`orchestrator.py` 中 `_process_batch` 改为按异常类型区分重试行为；`run_qc()` 中交叉验证内联代码提取为 `_run_cross_validation` + `_print_cross_validation_summary`；`call_llm` 增加可选的 `stats` 参数实现依赖注入。

**Tech Stack:** Python 3.10+, asyncio, httpx, pytest, pytest-asyncio

## Global Constraints

- 不改动外部行为（CLI 参数、输出格式、并发控制）
- 不引入新的 pip 依赖
- 所有改动后 `pytest` 全部通过（含已修复的 2 个测试文件）
- 每个任务独立可测，commit 粒度为任务级

---

### Task 1: 修复测试文件的 import 和调用签名

**Files:**
- Modify: `tests/framework/test_cross_validator.py:1,9`
- Modify: `tests/test_integration.py:13,121`

**Interfaces:**
- Consumes: `fixed_sample` from `auto_qc.framework.cross_validator`
- Produces: 2 个测试文件恢复收集通过

- [ ] **Step 1: 修改 test_cross_validator.py 的 import 和调用**

将第 1 行 import 改为 `fixed_sample`，第 9 行调用按新签名重写：

```python
from auto_qc.framework.cross_validator import fixed_sample, compare_results


def test_stratified_sample():
    results = (
        [{"id": f"v{i}", "violations": [{"rule_id": "R01"}]} for i in range(50)] +
        [{"id": f"p{i}", "violations": []} for i in range(50)]
    )
    sample = fixed_sample(results, sample_size=100)
    assert len(sample) > 0
    assert any(r.get("violations") for r in sample)
    assert any(not r.get("violations") for r in sample)
```

> `sample_size=100` 确保从 100 条数据中抽出足够多的样本，且 `fixed_sample` 的内置封顶（75%）不会截断。分层特性由 `fixed_sample` 内部保证。

- [ ] **Step 2: 修改 test_integration.py 的 import 和调用**

将第 13 行 import 从 `stratified_sample` 改为 `fixed_sample`，第 121 行调用改为：

```python
from auto_qc.framework.cross_validator import fixed_sample, compare_results
```

```python
def test_cross_validation_pipeline(self):
    """测试交叉验证完整流程"""
    results = (
        [{"id": f"v{i}", "violations": [{"rule_id": "R01"}]} for i in range(20)] +
        [{"id": f"p{i}", "violations": []} for i in range(80)]
    )
    sample = fixed_sample(results, sample_size=50)
    assert len(sample) > 0

    # 模拟 recheck 结果（与 original 一致）
    result = compare_results(sample, sample)
    assert result.mismatches == 0
    assert result.status == "ok"
```

- [ ] **Step 3: 验证测试通过**

```bash
.venv/Scripts/python -m pytest tests/framework/test_cross_validator.py tests/test_integration.py -v
```

Expected: 所有测试 PASS（无 ImportError）

- [ ] **Step 4: Commit**

```bash
git add tests/framework/test_cross_validator.py tests/test_integration.py
git commit -m "fix: 修复测试文件中 stratified_sample → fixed_sample 的重命名遗漏"
```

---

### Task 2: 创建 retry.py 统一重试工具

**Files:**
- Create: `src/auto_qc/framework/retry.py`

**Interfaces:**
- Produces: `with_api_retry(fn, *args, max_retries=3, **kwargs) -> T` — 对 `fn(*args, **kwargs)` 调用，遇到 `RETRYABLE_EXCEPTIONS` 时退避重试（1s, 2s, 4s），耗尽后抛 `ApiExhaustedError`；非网络错误直接传播
- Produces: `ApiExhaustedError(Exception)` — API 重试耗尽异常
- Produces: `RETRYABLE_EXCEPTIONS` — `(httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)`

- [ ] **Step 1: 创建 retry.py**

```python
"""统一 API 重试工具——按异常类型决定是否重试。"""
import asyncio
from typing import TypeVar, Callable, Awaitable, Any
import httpx

T = TypeVar("T")

# 网络层可重试的异常（这些错误重试有意义）
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.WriteError,
)


class ApiExhaustedError(Exception):
    """API 调用在 max_retries 次重试后仍失败。"""
    pass


async def with_api_retry(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    **kwargs: Any,
) -> T:
    """调用可等待函数 fn，遇到网络错误时退避重试。

    只重试 RETRYABLE_EXCEPTIONS（超时、连接错误等）。
    非网络类异常（认证错误、4xx 等）不重试，直接抛出。
    耗尽重试次数后抛出 ApiExhaustedError。
    """
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except RETRYABLE_EXCEPTIONS as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s

    raise ApiExhaustedError(
        f"API 调用失败（重试 {max_retries} 次后）: {last_error}"
    )
```

- [ ] **Step 2: 验证模块可导入**

```bash
.venv/Scripts/python -c "from auto_qc.framework.retry import with_api_retry, ApiExhaustedError, RETRYABLE_EXCEPTIONS; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/auto_qc/framework/retry.py
git commit -m "feat: 新增 retry.py 统一 API 重试工具（按异常类型区分重试行为）"
```

---

### Task 3: 编写 retry.py 的单元测试

**Files:**
- Create: `tests/framework/test_retry.py`

**Interfaces:**
- Consumes: `with_api_retry`, `ApiExhaustedError`, `RETRYABLE_EXCEPTIONS` from `auto_qc.framework.retry`

- [ ] **Step 1: 创建测试文件**

```python
"""测试 retry.py 的重试行为。"""
import asyncio
import pytest
import httpx
from auto_qc.framework.retry import with_api_retry, ApiExhaustedError, RETRYABLE_EXCEPTIONS


class TestWithApiRetry:

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """第一次就成功，不应重试。"""
        call_count = 0

        async def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        result = await with_api_retry(ok)
        assert result == "done"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_succeed(self):
        """超时后重试，第二次成功。"""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.TimeoutException("timeout")
            return "ok"

        result = await with_api_retry(flaky)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_exhausted_after_max_retries(self):
        """连续 3 次失败后抛 ApiExhaustedError。"""
        async def always_timeout():
            raise httpx.TimeoutException("timeout")

        with pytest.raises(ApiExhaustedError) as exc_info:
            await with_api_retry(always_timeout, max_retries=3)
        assert "重试 3 次" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_non_retryable_raises_immediately(self):
        """非网络错误（如认证错误）不重试，直接抛。"""
        call_count = 0

        async def auth_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("invalid auth")

        with pytest.raises(ValueError):
            await with_api_retry(auth_error)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_connect_error_is_retryable(self):
        """ConnectError 在 RETRYABLE_EXCEPTIONS 中。"""
        assert httpx.ConnectError in RETRYABLE_EXCEPTIONS
```

- [ ] **Step 2: 运行测试**

```bash
.venv/Scripts/python -m pytest tests/framework/test_retry.py -v
```

Expected: 5/5 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/framework/test_retry.py
git commit -m "test: 添加 retry.py 的单元测试（成功/重试/耗尽/非重试异常）"
```

---

### Task 4: worker.py 集成 retry + 增加 stats 参数

**Files:**
- Modify: `src/auto_qc/framework/worker.py:91-134`
  - `call_llm_with_retry`：用 `with_api_retry` 替换内联重试循环
  - `call_llm`：增加可选 `stats: TokenStats | None = None` 参数

**Interfaces:**
- Consumes: `with_api_retry` from `auto_qc.framework.retry`
- Produces: `call_llm(prompt, max_tokens=8000, stats=None)` — stats 非 None 时使用传入实例，None 时回退到模块级 `_token_stats`
- Produces: `call_llm_with_retry(prompt, max_tokens=8000, stats=None)` — 透传 stats 给 `call_llm`

- [ ] **Step 1: 添加 import**

在 `worker.py` 顶部新增一行：

```python
from auto_qc.framework.retry import with_api_retry
```

放在 `from dotenv import load_dotenv` 之后、`from json_repair import repair_json` 之前。

- [ ] **Step 2: 修改 call_llm——增加 stats 参数**

将函数签名和 Token 记录逻辑改为：

```python
async def call_llm(prompt: str, max_tokens: int = 8000, stats: "TokenStats | None" = None) -> str:
    """
    调用 LLM API，返回仅包含 text 内容的响应字符串。
    自动过滤 ThinkingBlock，只取 TextBlock。
    stats 为 None 时使用模块级全局 _token_stats（向后兼容）。
    """
    client = _get_client()
    model = _get_model()

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    # 记录 Token 消耗
    effective_stats = stats if stats is not None else _token_stats
    if response.usage:
        effective_stats.add(
            input_tokens=response.usage.input_tokens or 0,
            output_tokens=response.usage.output_tokens or 0,
        )

    texts = []
    for block in response.content:
        if isinstance(block, TextBlock):
            texts.append(block.text)

    return "\n".join(texts)
```

- [ ] **Step 3: 重写 call_llm_with_retry**

```python
async def call_llm_with_retry(prompt: str, max_tokens: int = 8000, stats: "TokenStats | None" = None) -> str:
    """
    调用 LLM，网络错误时自动重试（3 次退避）。
    耗尽后抛出 ApiExhaustedError。
    """
    return await with_api_retry(call_llm, prompt, max_tokens=max_tokens, stats=stats)
```

- [ ] **Step 4: 验证现有测试不受影响**

```bash
.venv/Scripts/python -m pytest tests/framework/test_worker.py -v
```

Expected: 4/4 PASS（`extract_json` 相关测试不受影响）

- [ ] **Step 5: Commit**

```bash
git add src/auto_qc/framework/worker.py
git commit -m "refactor: call_llm 增加 stats 参数 + call_llm_with_retry 改用 with_api_retry"
```

---

### Task 5: orchestrator.py 集成 retry——按异常类型区分重试

**Files:**
- Modify: `src/auto_qc/framework/orchestrator.py:17,23-75,78-120`

**Interfaces:**
- Consumes: `ApiExhaustedError` from `auto_qc.framework.retry`
- Consumes: `ValidationError` from `auto_qc.framework.validator`
- Produces: `_process_batch` — API 耗尽后直接标记失败，JSON/校验错误可重试
- Produces: `_process_attribution_batch` — 同上

- [ ] **Step 1: 添加 import**

在 orchestrator.py 顶部新增两行：

```python
from auto_qc.framework.retry import ApiExhaustedError
from auto_qc.framework.validator import ValidationError
```

`ValidationError` 已通过 `validate_worker_output, validate_merge_results` 间接暴露，但这里需要直接引用做 `except` 匹配，所以显式导入。

- [ ] **Step 2: 重写 _process_batch 异常处理**

将第 36-75 行（`for attempt in range(3):` 到函数末尾）改为按异常类型区分处理：

```python
    prompt = prompt_builder(batch)

    for attempt in range(3):
        try:
            raw = await call_llm_with_retry(prompt)
            json_text = extract_json(raw)
            output = validate_worker_output(json_text, batch.size, rule_ids)
            coordinator.mark_done(batch.batch_id)

            # 返回带原始字段（id/time/intent）的结果
            conv_map = {c.id: c for c in batch.conversations}
            enriched = []
            for r in output.results:
                conv = conv_map.get(r.id, None)
                enriched.append({
                    "id": r.id,
                    "time": conv.time if conv else "",
                    "intent": conv.intent if conv else "",
                    "status": r.status,
                    "violations": [
                        {"rule_id": v.rule_id, "rule_name": v.rule_name,
                         "severity": v.severity, "evidence": v.evidence,
                         "suggestion": v.suggestion}
                        for v in r.violations
                    ],
                })

            # 保存单批结果
            result_path = Path(work_dir) / f"batch_{batch.batch_id}_result.json"
            result_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

            return enriched

        except ApiExhaustedError as e:
            # API 层面已重试 3 次，不应再由业务层重试
            coordinator.mark_failed(batch.batch_id)
            print(f"批次 {batch.batch_id} API 调用失败: {e}")
            return []

        except (ValueError, ValidationError) as e:
            # JSON 解析或校验失败——可能是 prompt 层面的问题，值得重试
            retries = coordinator.increment_retry(batch.batch_id)
            if retries >= 3:
                coordinator.mark_failed(batch.batch_id)
                print(f"批次 {batch.batch_id} 失败（已重试 3 次）: {e}")
                return []
            print(f"批次 {batch.batch_id} 第 {retries} 次重试: {e}")

        except Exception as e:
            # 未预期的异常，不重试
            coordinator.mark_failed(batch.batch_id)
            print(f"批次 {batch.batch_id} 意外错误: {e}")
            return []

    return []
```

- [ ] **Step 3: 重写 _process_attribution_batch 异常处理**

同样的模式应用到第 91-120 行：

```python
    prompt = build_attribution_prompt(batch)

    for attempt in range(3):
        try:
            raw = await call_llm_with_retry(prompt)
            json_text = extract_json(raw)
            data = json.loads(json_text)

            if "attribution_results" not in data:
                raise ValueError("缺少 attribution_results 字段")

            total = data.get("total_conversations", 0)
            if total != batch.size:
                raise ValueError(f"对话数不匹配: 期望 {batch.size}，实际 {total}")

            coordinator.mark_done(batch.batch_id)

            result_path = Path(work_dir) / f"attr_batch_{batch.batch_id}_result.json"
            result_path.write_text(json_text, encoding="utf-8")

            # 用列表包裹，兼容 _dispatch_phase 的 extend 语义
            return [data["attribution_results"]]

        except ApiExhaustedError as e:
            coordinator.mark_failed(batch.batch_id)
            print(f"归因批次 {batch.batch_id} API 调用失败: {e}")
            return []

        except (ValueError, ValidationError) as e:
            retries = coordinator.increment_retry(batch.batch_id)
            if retries >= 3:
                coordinator.mark_failed(batch.batch_id)
                print(f"归因批次 {batch.batch_id} 失败（已重试 3 次）: {e}")
                return []
            print(f"归因批次 {batch.batch_id} 第 {retries} 次重试: {e}")

        except Exception as e:
            coordinator.mark_failed(batch.batch_id)
            print(f"归因批次 {batch.batch_id} 意外错误: {e}")
            return []

    return []
```

- [ ] **Step 4: 运行现有测试确保不破坏行为**

```bash
.venv/Scripts/python -m pytest tests/ --ignore=tests/framework/test_cross_validator.py --ignore=tests/test_integration.py -v
```

Expected: 47/47 PASS（Task 4 引入的 `call_llm_with_retry` 行为改变不影响不调 LLM 的测试）

- [ ] **Step 5: Commit**

```bash
git add src/auto_qc/framework/orchestrator.py
git commit -m "refactor: _process_batch/_process_attribution_batch 按异常类型区分重试（API错误不重试）"
```

---

### Task 6: 提取交叉验证为独立函数

**Files:**
- Modify: `src/auto_qc/framework/orchestrator.py:222-274` → 替换为函数调用

**Interfaces:**
- Consumes: `Batch`, `Conversation` from `auto_qc.domain.schemas`（已导入）
- Consumes: `fixed_sample`, `compare_results` from `auto_qc.framework.cross_validator`（已导入）
- Consumes: `build_qc_prompt` from `auto_qc.domain.prompts`（已导入）
- Produces: `_run_cross_validation(qc_results, conv_text_map, rule_package, rule_ids, work_dir)` — 返回 `(sample, cross_result) | ([], None)`
- Produces: `_print_cross_validation_summary(sample_size, cross_result)` — 纯打印

- [ ] **Step 1: 在 run_qc 之前新增 _run_cross_validation 函数**

在 `_dispatch_phase` 函数之后、`run_qc` 函数之前插入：

```python
async def _run_cross_validation(
    qc_results: list[dict],
    conv_text_map: dict[str, str],
    rule_package,
    rule_ids: list[str],
    work_dir: str,
) -> tuple[list[dict], "CrossValidationResult | None"]:
    """交叉验证：分层抽样 → LLM 复检 → Kappa 对比。

    Returns:
        (sample, cross_result) — sample 为抽检的原始结果列表；
        cross_result 为 None 表示样本不足。
    """
    sample = fixed_sample(qc_results, sample_size=200)
    if not sample:
        return [], None

    recheck_results: list[dict] = []
    for i in range(0, len(sample), 25):
        chunk = sample[i:i + 25]
        chunk_batch = Batch(batch_id=999, conversations=[
            Conversation(
                id=s["id"],
                time=s.get("time", ""),
                intent=s.get("intent", ""),
                conversation=conv_text_map.get(s["id"], ""),
            )
            for s in chunk
        ])

        recheck_output = None
        for attempt in range(3):
            try:
                prompt = build_qc_prompt(chunk_batch, rule_package)
                raw = await call_llm_with_retry(prompt)
                json_text = extract_json(raw)
                recheck_output = validate_worker_output(json_text, chunk_batch.size, rule_ids)
                break
            except ApiExhaustedError as e:
                print(f"  交叉验证抽样批次 {i//25+1} API 调用失败: {e}")
                break
            except (ValueError, ValidationError) as e:
                if attempt >= 2:
                    print(f"  交叉验证抽样批次 {i//25+1} 失败: {e}")
                    break
                print(f"  交叉验证抽样批次 {i//25+1} 第 {attempt+1} 次重试: {e}")

        if recheck_output is None:
            continue
        recheck_results.extend([
            {"id": r.id, "violations": [{"rule_id": v.rule_id} for v in r.violations]}
            for r in recheck_output.results
        ])

    cross_result = compare_results(sample, recheck_results)
    return sample, cross_result


def _print_cross_validation_summary(sample_size: int, cross_result) -> None:
    """打印交叉验证摘要（Kappa 标签映射 + 逐规则明细）。"""
    print(f"  [OK] 交叉验证: 抽检 {sample_size} 条")
    print(f"     总体 Kappa={cross_result.kappa:.3f} ({cross_result.kappa_status}), 差异率 {cross_result.discrepancy_rate:.1%}")

    kappa_labels = [
        (0.8, "几乎完全一致"),
        (0.6, "高度一致"),
        (0.4, "中等一致"),
        (0.2, "一致性低"),
        (-float("inf"), "一致性差"),
    ]
    for rule_id, s in cross_result.per_rule.items():
        label = next(lbl for threshold, lbl in kappa_labels if s["kappa"] >= threshold)
        print(f"     {rule_id}: Kappa={s['kappa']:.2f} ({label}), 一致率 {s['agreement']:.0%} ({s['total_judgments']}次判断)")
```

- [ ] **Step 2: 替换 run_qc() 中 Step 5 的内联代码**

将第 222-274 行替换为：

```python
    # ─── Step 5: 交叉验证 ───
    print("[Step 5] 交叉验证...")
    sample, cross_result = await _run_cross_validation(
        qc_results, conv_text_map, rule_package, rule_ids, work_dir,
    )
    if cross_result:
        _print_cross_validation_summary(len(sample), cross_result)
    else:
        print("  [!] 跳过交叉验证（样本不足）")
```

- [ ] **Step 3: 运行现有测试**

```bash
.venv/Scripts/python -m pytest tests/ --ignore=tests/framework/test_cross_validator.py --ignore=tests/test_integration.py -v
```

Expected: 47/47 PASS（交叉验证函数不调 LLM 时不执行）

- [ ] **Step 4: Commit**

```bash
git add src/auto_qc/framework/orchestrator.py
git commit -m "refactor: 将交叉验证逻辑从 run_qc() 提取为 _run_cross_validation + _print_cross_validation_summary"
```

---

### Task 7: TokenStats 穿透 orchestrator 全链路

**Files:**
- Modify: `src/auto_qc/framework/orchestrator.py:17,161-175,208-218,287-294`
- 涉及函数：`run_qc`, `_dispatch_phase`, `_process_batch`, `_process_attribution_batch`, `_run_cross_validation`

**Interfaces:**
- Consumes: `TokenStats` from `auto_qc.framework.worker`
- Produces: 所有函数签名增加 `stats: TokenStats | None = None` 参数；`run_qc()` 创建实例并向下传递
- 移除 `reset_token_stats()` 调用

- [ ] **Step 1: 更新 import**

在 orchestrator.py 顶部更新 worker 的 import：

```python
from auto_qc.framework.worker import call_llm_with_retry, extract_json, TokenStats
```

（移除 `reset_token_stats, get_token_stats`，不再需要；新增 `TokenStats` 用于类型标注和实例化）

- [ ] **Step 2: 更新 _process_batch 签名——增加 stats 参数**

```python
async def _process_batch(
    batch: Batch,
    rule_ids: list[str],
    prompt_builder,
    coordinator: Coordinator,
    work_dir: str,
    stats: "TokenStats | None" = None,
) -> list[dict]:
```

内部调用改为透传 stats：

```python
raw = await call_llm_with_retry(prompt, stats=stats)
```

- [ ] **Step 3: 更新 _process_attribution_batch 签名**

```python
async def _process_attribution_batch(
    batch: Batch,
    rule_ids: list[str],
    prompt_builder,
    coordinator: Coordinator,
    work_dir: str,
    stats: "TokenStats | None" = None,
) -> list[dict]:
```

内部调用改为：

```python
raw = await call_llm_with_retry(prompt, stats=stats)
```

- [ ] **Step 4: 更新 _dispatch_phase——透传 stats**

```python
async def _dispatch_phase(
    batches: list[Batch],
    rule_ids: list[str],
    prompt_builder,
    coordinator: Coordinator,
    work_dir: str,
    sem: asyncio.Semaphore,
    process_func=None,
    stats: "TokenStats | None" = None,
) -> list[dict]:
```

内部 `_run_one` 改为：

```python
async def _run_one(batch: Batch):
    async with sem:
        func = process_func or _process_batch
        return await func(batch, rule_ids, prompt_builder, coordinator, work_dir, stats=stats)
```

- [ ] **Step 5: 更新 _run_cross_validation——增加 stats 参数并透传**

```python
async def _run_cross_validation(
    qc_results: list[dict],
    conv_text_map: dict[str, str],
    rule_package,
    rule_ids: list[str],
    work_dir: str,
    stats: "TokenStats | None" = None,
) -> tuple[list[dict], "CrossValidationResult | None"]:
```

内部调用改为：

```python
raw = await call_llm_with_retry(prompt, stats=stats)
```

- [ ] **Step 6: 更新 run_qc——创建 TokenStats 并向下传递**

```python
async def run_qc(
    data_path: str,
    rules_path: str,
    output_path: str,
    work_dir: str = "./auto_qc_work",
    skip_attribution: bool = False,
    token_stats: "TokenStats | None" = None,
) -> None:
    Path(work_dir).mkdir(parents=True, exist_ok=True)

    stats = token_stats or TokenStats()
    # 移除 reset_token_stats() 调用

    # Step 1-3: 不变
    ...

    # Step 4: 透传 stats
    qc_results = await _dispatch_phase(
        batches, rule_ids,
        prompt_builder=lambda b: build_qc_prompt(b, rule_package),
        coordinator=coordinator,
        work_dir=work_dir,
        sem=sem,
        stats=stats,
    )

    # Step 5: 透传 stats
    sample, cross_result = await _run_cross_validation(
        qc_results, conv_text_map, rule_package, rule_ids, work_dir,
        stats=stats,
    )

    # Step 6: 透传 stats
    attr_results = await _dispatch_phase(
        attr_batches, attr_rule_ids,
        prompt_builder=build_attribution_prompt,
        coordinator=attr_coordinator,
        work_dir=work_dir,
        sem=sem,
        process_func=_process_attribution_batch,
        stats=stats,
    )

    # Token 消耗（使用注入的 stats 实例）
    token_summary = stats.summary()
    ...
```

- [ ] **Step 7: 运行全部测试**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 所有测试 PASS（47 + 5 retry + 2 恢复的 cross_validator/integration = 54+）

- [ ] **Step 8: Commit**

```bash
git add src/auto_qc/framework/orchestrator.py
git commit -m "refactor: TokenStats 依赖注入——run_qc 创建实例并穿透全链路传递"
```

---

### Task 8: 最终验证

**Files:**
- 全部文件

- [ ] **Step 1: 全量测试**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 全部 PASS（约 54 项测试），无 skip，无 error。

- [ ] **Step 2: 确认模块导入无循环依赖**

```bash
.venv/Scripts/python -c "
from auto_qc.framework.retry import with_api_retry, ApiExhaustedError
from auto_qc.framework.worker import call_llm, call_llm_with_retry, TokenStats
from auto_qc.framework.orchestrator import run_qc
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: Commit（如有未提交的改动）**

```bash
git status
```

如有测试文件在过程中调整，一并提交。
