# 移除归因分析实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除归因分析的所有代码，将 auto-qc 简化为纯粹的合规检测工具（6 步流程，2-Sheet 报告）。

**Architecture:** 纯删除操作——删 4 个文件，改 7 个文件。每步删除独立模块的归因代码，最终编排器从 7 步 → 6 步。

**Tech Stack:** Python 3.10+, openpyxl, pytest

## Global Constraints

- 不改动合规检测逻辑、交叉验证、重试机制
- 不引入新功能、新依赖
- 删除后所有测试通过

---

### Task 1: 删除归因相关的独立文件（4 个）

**Files:**
- Delete: `src/auto_qc/domain/attribution.py`
- Delete: `templates/attribution-prompt.md`
- Delete: `templates/attribution-rules.md`
- Delete: `tests/domain/test_attribution.py`

**Interfaces:**
- Produces: 这 4 个文件不再存在，后续 task 会移除对它们的引用

- [ ] **Step 1: 删除文件**

```bash
git rm src/auto_qc/domain/attribution.py \
       templates/attribution-prompt.md \
       templates/attribution-rules.md \
       tests/domain/test_attribution.py
```

- [ ] **Step 2: 验证删除后不破坏其他模块导入**

```bash
.venv/Scripts/python -c "from auto_qc.domain import prompts; print('prompts OK')"
```

Expected: `prompts OK`（prompts.py 不依赖 attribution 模块）

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: 删除归因分析模块、模板和测试（4 文件）"
```

---

### Task 2: 清理 prompts.py 和 test_prompts.py

**Files:**
- Modify: `src/auto_qc/domain/prompts.py:48-69`
- Modify: `tests/domain/test_prompts.py`

**Interfaces:**
- Consumes: Task 1（模板文件和 attribution 模块已删除）
- Produces: prompts.py 仅保留 `build_qc_prompt`、`_load_template`

- [ ] **Step 1: 删除 prompts.py 中的 build_attribution_prompt 函数**

删除 `src/auto_qc/domain/prompts.py` 第 48-69 行（整个 `build_attribution_prompt` 函数）。

- [ ] **Step 2: 删除 test_prompts.py 中归因相关测试**

读取 `tests/domain/test_prompts.py`，删除其中测试 `build_attribution_prompt` 的函数（如有）。

- [ ] **Step 3: 运行 prompts 测试**

```bash
.venv/Scripts/python -m pytest tests/domain/test_prompts.py -v
```

Expected: 测试全部 PASS（仅 `build_qc_prompt` 相关测试保留）

- [ ] **Step 4: Commit**

```bash
git add src/auto_qc/domain/prompts.py tests/domain/test_prompts.py
git commit -m "refactor: 删除 build_attribution_prompt 函数及相关测试"
```

---

### Task 3: 清理 data_loader.py 的 exclude_intent 参数

**Files:**
- Modify: `src/auto_qc/domain/data_loader.py:65-69,92-93`

**Interfaces:**
- Consumes: `load_conversations` 签名
- Produces: `load_conversations(data_path, batch_size=100) -> list[Batch]`

- [ ] **Step 1: 删除 exclude_intent 参数**

将 `load_conversations` 签名从：

```python
def load_conversations(
    data_path: str,
    batch_size: int = 100,
    exclude_intent: Optional[str] = None,
) -> list[Batch]:
```

改为：

```python
def load_conversations(
    data_path: str,
    batch_size: int = 100,
) -> list[Batch]:
```

- [ ] **Step 2: 删除函数体内 exclude_intent 使用**

删除以下两行（函数体内）：

```python
        if exclude_intent and intent == exclude_intent:
            continue
```

- [ ] **Step 3: 删除 Optional import（如无其他引用）**

文件顶部 `from typing import Optional` 改为不导入 `Optional`（仅此参数使用了它）。

- [ ] **Step 4: 运行 data_loader 测试**

```bash
.venv/Scripts/python -m pytest tests/domain/test_data_loader.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/auto_qc/domain/data_loader.py
git commit -m "refactor: load_conversations 删除归因专用的 exclude_intent 参数"
```

---

### Task 4: 清理 report.py 的归因分析 Sheet

**Files:**
- Modify: `src/auto_qc/domain/report.py:23-28,66-82`

**Interfaces:**
- Consumes: `write_report(output_path, qc_results, attr_data, stats)` 旧签名
- Produces: `write_report(output_path, qc_results, stats)` 新签名（3 Sheet → 2 Sheet）

- [ ] **Step 1: 修改 write_report 签名——删除 attribution_results 参数**

```python
def write_report(
    output_path: str,
    qc_results: list[dict],
    stats: dict,
) -> None:
```

- [ ] **Step 2: 删除 "归因分析" Sheet 全部代码**

删除原第 66-82 行（`ws_attr = wb.create_sheet("归因分析")` 到该 Sheet 写完的所有代码），包括：
- `ws_attr` 的创建
- `ws_attr.sheet_properties.tabColor`
- `attr_headers` 定义和写入
- 归因数据行循环

- [ ] **Step 3: 将原 "统计概览" Sheet 索引从 3 改为 2（无需代码修改）**

代码中 `wb.create_sheet("统计概览")` 会自动成为 Sheet 2，无版本号硬编码。标签颜色保持 `"FFD93D"`。

- [ ] **Step 4: 运行 report 测试**

```bash
.venv/Scripts/python -m pytest tests/domain/test_report.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/auto_qc/domain/report.py
git commit -m "refactor: write_report 删除归因分析 Sheet（3→2 Sheet）"
```

---

### Task 5: 清理 orchestrator.py 的归因流程

**Files:**
- Modify: `src/auto_qc/framework/orchestrator.py:11,94-148,268-275,341-364,390,426-458`

**Interfaces:**
- Consumes: `build_attribution_prompt`（已删除）、`_process_attribution_batch`、`_group_attribution`
- Produces: `run_qc(data_path, rules_path, output_path, work_dir, token_stats=None)`（6 步，无 `skip_attribution`）
- Produces: `_dispatch_phase` 保留 `process_func` 参数但无归因调用方

- [ ] **Step 1: 删除 build_attribution_prompt import**

将第 11 行：

```python
from auto_qc.domain.prompts import build_qc_prompt, build_attribution_prompt
```

改为：

```python
from auto_qc.domain.prompts import build_qc_prompt
```

- [ ] **Step 2: 删除 _process_attribution_batch 函数**

删除第 94-147 行（整个函数，约 54 行）。

- [ ] **Step 3: 删除 _group_attribution 函数**

删除第 426-458 行（整个函数，约 33 行）。

- [ ] **Step 4: 修改 run_qc 签名——删除 skip_attribution 参数**

```python
async def run_qc(
    data_path: str,
    rules_path: str,
    output_path: str,
    work_dir: str = "./auto_qc_work",
    token_stats: "TokenStats | None" = None,
) -> None:
```

- [ ] **Step 5: 删除 run_qc 中 Step 6 全部代码**

删除第 341-364 行（`attr_data = {}` 到整个 Step 6 结束），约 25 行。

- [ ] **Step 6: 修改 write_report 调用**

将第 371 行：

```python
    write_report(output_path, qc_results, attr_data, qc_stats)
```

改为：

```python
    write_report(output_path, qc_results, qc_stats)
```

- [ ] **Step 7: 修改 summary.json——删除 attribution_enabled 字段**

将第 385-397 行中 `summary_data` 的 `"attribution_enabled": not skip_attribution,` 行删除。

- [ ] **Step 8: 运行全量测试**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 9: Commit**

```bash
git add src/auto_qc/framework/orchestrator.py
git commit -m "refactor: 从 orchestrator 中移除归因分析流程（7步→6步）"
```

---

### Task 6: 清理 cli.py 的归因参数

**Files:**
- Modify: `src/auto_qc/cli.py:15-18,38-48`

**Interfaces:**
- Produces: `auto-qc --data <xlsx> --rules <md> [--output <path>] [--work-dir <path>] [--run-name <name>]`

- [ ] **Step 1: 删除归因相关参数定义**

删除第 15-16 行：

```python
parser.add_argument("--no-attribution", action="store_true", help="关闭归因分析")
parser.add_argument("--attribution-only", action="store_true", help="仅执行归因分析")
```

- [ ] **Step 2: 简化 main 函数逻辑**

删除第 38-48 行（`attribution_only`/`skip_attribution` 变量和 if-else 分支），替换为直接调用：

```python
    if not args.rules:
        parser.error("需要 --rules 参数")

    from auto_qc.framework.orchestrator import run_qc
    asyncio.run(run_qc(
        data_path=args.data,
        rules_path=args.rules,
        output_path=output_path,
        work_dir=work_dir,
    ))
```

- [ ] **Step 3: 验证 CLI 参数**

```bash
.venv/Scripts/python -m auto_qc.cli --help
```

Expected: 输出中不包含 `--no-attribution`、`--attribution-only`

- [ ] **Step 4: Commit**

```bash
git add src/auto_qc/cli.py
git commit -m "refactor: CLI 删除归因相关参数（--no-attribution/--attribution-only）"
```

---

### Task 7: 清理 test_integration.py 的归因引用

**Files:**
- Modify: `tests/test_integration.py`

**Interfaces:**
- Consumes: 删除归因相关的 import 和测试方法

- [ ] **Step 1: 删除归因相关 import**

检查 `tests/test_integration.py` 顶部的 import，删除对 `build_attribution_prompt` 的引用（如有）。

- [ ] **Step 2: 删除归因相关测试方法**

删除任何测试归因（attribution）的测试方法。

- [ ] **Step 3: 运行测试**

```bash
.venv/Scripts/python -m pytest tests/test_integration.py -v
```

Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: 清理集成测试中的归因分析引用"
```

---

### Task 8: 最终验证

**Files:**
- 全部文件

- [ ] **Step 1: 全量测试**

```bash
.venv/Scripts/python -m pytest tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 2: 确认无残留引用**

```bash
grep -r "attribution" src/ tests/ 2>/dev/null || echo "无残留引用"
```

Expected: `无残留引用`

- [ ] **Step 3: 确认 import 无循环依赖**

```bash
.venv/Scripts/python -c "
from auto_qc.framework.orchestrator import run_qc
from auto_qc.domain.prompts import build_qc_prompt
from auto_qc.domain.report import write_report
from auto_qc.cli import main
print('All imports OK')
"
```

Expected: `All imports OK`
