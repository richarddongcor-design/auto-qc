# auto-qc 移除归因分析设计文档

**日期**: 2026-06-17
**状态**: Draft
**基于**: 2026-06-17 代码质量优化

---

## 1. 动机

auto-qc 定位为纯粹的合规检测工具，基于 harness 思想——结果可控、可追溯。归因分析是早期设计遗留的半成品（`--attribution-only` 只打了一行 TODO），从未实际运行。移除它以简化代码、减少维护负担。

---

## 2. 删除清单

| 文件 | 原因 |
|------|------|
| `src/auto_qc/domain/attribution.py` | 归因规则内置模块（A01-A06），仅被归因流程引用 |
| `templates/attribution-prompt.md` | 归因 Worker prompt 模板 |
| `templates/attribution-rules.md` | 内置归因规则文档 |
| `tests/domain/test_attribution.py` | 归因模块测试 |

---

## 3. 修改清单

### 3.1 CLI（`src/auto_qc/cli.py`）

- 删除 `--no-attribution`、`--attribution-only` 参数
- 删除 `attribution_only`/`skip_attribution` 变量和相关 if-else 分支
- 删除 `--attribution-only` 但没传 `--rules` 的特殊校验
- 最终接口：`auto-qc --data <xlsx> --rules <md> [--output <path>] [--work-dir <path>] [--run-name <name>]`

### 3.2 Prompt 模板（`src/auto_qc/domain/prompts.py`）

- 删除 `build_attribution_prompt()` 函数
- 删除 `_TEMPLATES_DIR` 中对上述函数的依赖（函数内引用，随函数一起删）

### 3.3 数据加载（`src/auto_qc/domain/data_loader.py`）

- `load_conversations()` 删除 `exclude_intent` 参数
- 函数体内删除 `if exclude_intent and intent == exclude_intent: continue` 逻辑

### 3.4 报告（`src/auto_qc/domain/report.py`）

- `write_report()` 删除 `attribution_results` 参数
- 删除 "归因分析" Sheet（原 Sheet 2）的全部代码
- 原 Sheet 3 "统计概览" 变为 Sheet 2

### 3.5 编排器（`src/auto_qc/framework/orchestrator.py`）

- 删除 `_process_attribution_batch()` 函数
- 删除 `_group_attribution()` 函数
- 删除 `run_qc()` 中 Step 6 全部代码（归因分析）
- 删除 `run_qc()` 的 `skip_attribution` 参数
- 删除 import：`build_attribution_prompt`
- `_dispatch_phase` 的 `process_func` 参数不再需要（仅 `_process_batch` 一个实现），但保留签名兼容

### 3.6 测试

| 文件 | 改动 |
|------|------|
| `tests/domain/test_attribution.py` | 删除 |
| `tests/domain/test_prompts.py` | 删除 `build_attribution_prompt` 相关测试 |
| `tests/test_integration.py` | 删除归因相关 import 和测试 |

---

## 4. 最终项目结构

```
src/auto_qc/
├── framework/
│   ├── orchestrator.py      # 6 步流程（原 7 步去掉归因）
│   ├── coordinator.py
│   ├── worker.py
│   ├── validator.py
│   ├── cross_validator.py
│   ├── retry.py
│   └── progress.py
├── domain/
│   ├── rules.py
│   ├── prompts.py           # 仅 build_qc_prompt
│   ├── schemas.py
│   ├── report.py            # 2 Sheet（原 3 Sheet）
│   └── data_loader.py       # 无 exclude_intent
└── cli.py                   # 3 个选项，单模式
```

---

## 5. run_qc 最终签名

```python
async def run_qc(
    data_path: str,
    rules_path: str,
    output_path: str,
    work_dir: str = "./auto_qc_work",
    token_stats: TokenStats | None = None,
) -> None:
```

---

## 6. 执行流程（6 步）

```
Step 1: 环境检查
Step 2: 规则解析 + 校验
Step 3: 数据加载 + 批次拆分
Step 4: 并发质检
Step 5: 交叉验证
Step 6: 报告生成（2 Sheet：合规检测 + 统计概览）
```

---

## 7. 不做的事

- 不改动合规检测逻辑、交叉验证、重试机制
- 不改动 rules.md 格式、worker-prompt.md 模板
- 不改动 Excel 报告的合规检测 Sheet 和统计概览 Sheet 的内容
- 不引入新功能、新依赖
