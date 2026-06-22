# auto-qc 代码质量优化设计文档

**日期**: 2026-06-17
**状态**: Draft
**基于**: 2026-06-03 CLI 重构设计文档

---

## 1. 动机

当前代码在多次迭代中积累了一些可维护性问题：重试逻辑重叠导致 Token 浪费、主流程函数膨胀、测试间共享状态、测试代码未跟随重构更新。本 spec 聚焦四项独立但互不冲突的优化，不引入新功能，不改变外部行为。

---

## 2. 优化项

### 2.1 修复测试导入和调用签名

**问题**: `cross_validator.py` 中的 `stratified_sample` 已重构为 `fixed_sample`，函数签名也完全改变（`violation_ratio`/`non_violation_ratio` → `sample_size`/`random_seed`），但两个测试文件仍引用旧名和旧参数：
- `tests/framework/test_cross_validator.py:1` — `from ...cross_validator import stratified_sample`
- `tests/test_integration.py:13` — 同上
- 两文件中调用 `stratified_sample(results, violation_ratio=..., non_violation_ratio=...)` 会因参数名不匹配而报 `TypeError`

执行 `pytest` 时这两文件收集阶段即报 `ImportError`，测试无法运行，隐藏了后续的签名问题。

**方案**: 两个测试文件的 import 改为 `fixed_sample`，调用处按新签名重写：

```python
# 旧
from auto_qc.framework.cross_validator import stratified_sample, compare_results
sample = stratified_sample(results, violation_ratio=0.2, non_violation_ratio=0.2)

# 新
from auto_qc.framework.cross_validator import fixed_sample, compare_results
sample = fixed_sample(results, sample_size=200)
```

**影响**: 2 个测试文件各改 2-3 行，无生产代码改动。

---

### 2.2 统一重试机制

#### 2.2.1 现状

两层独立重试，效果是乘法叠加：

| 层级 | 位置 | 最大次数 | 触发条件 |
|------|------|---------|---------|
| 外层 | `_process_batch` for 循环 | 3 | catch 任意 Exception（含 API 错误、JSON 错误、校验错误） |
| 内层 | `call_llm_with_retry` | 3 | API 调用抛异常 |

最坏情况：同一批对话因 API 超时连续调用 9 次后放弃。

#### 2.2.2 方案

引入一个统一的 `retry` 工具函数，按异常类型区分重试行为：

```python
# src/auto_qc/framework/retry.py（新增）

MAX_RETRIES_PER_API = 3       # API 层面最多重试 3 次（网络波动/超时）
MAX_RETRIES_PER_BATCH = 2     # 业务层面最多重试 2 次（JSON/校验失败）


class ApiRetryableError(Exception):
    """API 层面可重试的异常：超时、连接错误、5xx。"""


class NonRetryableError(Exception):
    """不需重试的业务异常：必填字段缺失、数据结构不合法。"""


async def retry_api_call(fn, max_retries=MAX_RETRIES_PER_API):
    """网络层重试：退避递增，最后一次失败抛 ApiRetryableError。"""
    ...


async def retry_business(fn, max_retries=MAX_RETRIES_PER_BATCH):
    """业务层重试：仅在捕获 ApiRetryableError 或校验异常时重试。"""
    ...
```

两层关系变为**互补而非重叠**：

```
_process_batch:
  for attempt in range(MAX_RETRIES_PER_BATCH + 1):      ← 业务层循环
    try:
      raw = await retry_api_call(call_llm)               ← 网络层重试（内部3次）
      json_text = extract_json(raw)
      output = validate_worker_output(...)
      return enriched
    except ApiRetryableError:
      # 网络层已重试 3 次，业务层不再重试 API 错误
      # 继续外层循环，但大概率再次失败 → 走下面的 fallthrough
    except (json.JSONDecodeError, ValidationError):
      # prompt 层面的问题（LLM 输出格式不对），值得再试
```

batch 实际最多 3 次（1 次初始 + 2 次业务重试），每**次里面** API 最多 3 次。独立网络故障时最多 3 次放弃，不再 9 次。

#### 2.2.3 涉及改动

| 文件 | 改动 |
|------|------|
| `src/auto_qc/framework/retry.py` | **新增**：`retry_api_call`、`retry_business`、异常定义 |
| `src/auto_qc/framework/worker.py` | `call_llm` 保留原始 1 次调用，`call_llm_with_retry` 改为调用 `retry_api_call` |
| `src/auto_qc/framework/orchestrator.py` | `_process_batch`、`_process_attribution_batch` 改用新的重试模式 |

---

### 2.3 提取交叉验证为独立函数

#### 2.3.1 现状

`run_qc()` 第 224-274 行直接内联交叉验证逻辑，约 50 行包含：抽样、逐批调 LLM、重试控制、Kappa 标签映射、结果打印。主流程函数因此膨胀至 ~170 行。

#### 2.3.2 方案

将 Step 5 提取为 `orchestrator.py` 中的顶层 async 函数：

```python
async def _run_cross_validation(
    qc_results: list[dict],
    conv_text_map: dict[str, str],
    rule_package: RulePackage,
    work_dir: str,
    sem: asyncio.Semaphore,
) -> CrossValidationResult | None:
    """交叉验证：分层抽样 → LLM 复检 → Kappa 对比。

    返回 CrossValidationResult（含总体 Kappa、逐规则 Kappa、差异率）；
    样本不足时返回 None。
    """
    sample = fixed_sample(qc_results, sample_size=200)
    if not sample:
        return None
    ...
    return compare_results(sample, recheck_results)
```

`run_qc()` 中替换为：

```python
cross_result = await _run_cross_validation(
    qc_results, conv_text_map, rule_package, work_dir, sem
)
if cross_result:
    _print_cross_validation_summary(cross_result)
```

打印逻辑也提取为 `_print_cross_validation_summary()`，不再内联 if-elif 标签映射。

#### 2.3.3 涉及改动

| 文件 | 改动 |
|------|------|
| `src/auto_qc/framework/orchestrator.py` | 新增 `_run_cross_validation`、`_print_cross_validation_summary`；`run_qc()` 中替换内联代码为函数调用 |

---

### 2.4 TokenStats 依赖注入

#### 2.4.1 现状

```python
# worker.py — 模块级全局单例
_token_stats = TokenStats()

def get_token_stats() -> TokenStats:
    return _token_stats
```

所有 LLM 调用共享同一个 `TokenStats` 实例。测试间互相污染，mock 困难。

#### 2.4.2 方案

`TokenStats` 改为由调用方创建并注入：

```python
# worker.py
async def call_llm(prompt: str, stats: TokenStats | None = None, max_tokens: int = 8000) -> str:
    stats = stats or TokenStats()   # 没传时使用临时实例（测试默认用这个）
    ...
    stats.add(input_tokens=..., output_tokens=...)
    return text

# orchestrator.py
async def run_qc(..., token_stats: TokenStats | None = None) -> None:
    stats = token_stats or TokenStats()
    # 向下传递
    raw = await call_llm(prompt, stats=stats)
    ...
    print(stats.summary())
```

保持 `get_token_stats()` / `reset_token_stats()` 作为便利接口，但内部改为 `contextvars.ContextVar` 或在 `run_qc()` 中统一管理，不强制使用全局。

#### 2.4.3 涉及改动

| 文件 | 改动 |
|------|------|
| `src/auto_qc/framework/worker.py` | `call_llm` 增加 `stats` 参数；`_token_stats` 全局单例降级为 fallback |
| `src/auto_qc/framework/orchestrator.py` | `run_qc()` 创建 `TokenStats` 实例并传递；`_process_batch` 等函数增加 `stats` 参数 |
| 测试文件 | 测试中创建独立 `TokenStats`，不再依赖全局 reset |

---

## 3. 项目结构变化

```
src/auto_qc/framework/
├── orchestrator.py    # 不变，run_qc() 瘦身
├── coordinator.py     # 不变
├── worker.py          # call_llm 增加 stats 参数
├── validator.py       # 不变
├── cross_validator.py # 不变
├── progress.py        # 不变
└── retry.py           # 新增：统一重试工具函数
```

不改变项目目录结构，不添加新依赖。

---

## 4. 测试策略

| 优化项 | 测试 |
|--------|------|
| 修复 import | 恢复 `pytest` 收集通过即可 |
| 统一重试 | 用 mock `call_llm` 模拟 API 超时和 JSON 错误，验证重试次数和放弃路径 |
| 交叉验证提取 | 现有 `test_cross_validator.py` 不变；补充一个 `_run_cross_validation` 的集成测试 |
| TokenStats 注入 | 测试中创建独立 `TokenStats`，验证不会互相干扰 |

---

## 5. 不做的事

- 不添加新功能
- 不改动 Excel 报告格式、Prompt 模板、规则格式
- 不修改 CLI 参数和外部接口
- 不碰 Coordinator 的 `progress.json` I/O 设计
- 不引入 logging 框架
- 不修改 `Semaphore` 与 `MAX_CONCURRENCY` 双重限流（语义正确，非本 spec 范围）
