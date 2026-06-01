# 并发协调器 (coordinator.py) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Worker 并发控制从 SKILL.md 软约束改为 coordinator.py 代码硬兜底

**Architecture:** 新增 coordinator.py 脚本管理批次状态和并发槽位。Claude 每轮通过 `get-next` 从脚本获取可启动的批次列表（脚本硬限制最多 10 个），完成后通过 `mark-done` / `mark-failed` 汇报结果。SKILL.md 改为指导 Claude 调用脚本而非自行计数。

**Tech Stack:** Python, argparse, json, pathlib

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `scripts/coordinator.py` | **新增** | 并发协调器：get-next / mark-done / mark-failed / summary |
| `scripts/test_coordinator.py` | **新增** | coordinator.py 的单元测试 |
| `SKILL.md` | 修改 | Step 2（进度文件创建改用 coordinator）、Step 3（合规检测）、Step 5（归因分析）改为调用 coordinator.py |

---

### Task 1: coordinator.py — get-next 子命令

**Files:**
- Create: `~/.agents/skills/auto-qc/scripts/coordinator.py`
- Create: `~/.agents/skills/auto-qc/scripts/test_coordinator.py`

- [ ] **Step 1: 写测试 — get-next 返回 pending 批次，数量不超过 max_concurrency**

```python
# test_coordinator.py
import json
import os
import tempfile
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
COORDINATOR = os.path.join(SKILL_DIR, "coordinator.py")
MAX_CONCURRENCY = 10  # 与 coordinator.py 一致

def run_cmd(*args):
    """运行 coordinator.py 子命令，返回 JSON 解析结果。"""
    result = subprocess.run(
        [sys.executable, COORDINATOR] + list(args),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError(f"coordinator.py failed: {result.stderr}")
    return json.loads(result.stdout)

def _make_progress(progress_path, total=50, completed=0):
    """创建包含 total 个 pending 批次的 progress.json。"""
    data = {
        "total_batches": total,
        "completed_batches": completed,
        "batch_status": {str(i): "pending" for i in range(1, total + 1)},
        "retry_count": {},
        "failed_batches": [],
        "phase": "qc",
        "started_at": "2026-06-01T00:00:00",
        "updated_at": "2026-06-01T00:00:00",
    }
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
```

```python
def test_get_next_returns_max_10_batches(tmp_path):
    """50 个 pending 批次，get-next 最多返回 10 个。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")
    _make_progress(progress_path, total=50)

    result = run_cmd("get-next", "--progress", progress_path)

    assert len(result["batches"]) == 10, f"Expected 10, got {len(result['batches'])}"
    assert result["running"] == 10
    assert result["slots"] == 0

def test_get_next_returns_fewer_when_near_end(tmp_path):
    """剩余 3 个 pending，get-next 返回 3 个。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")
    _make_progress(progress_path, total=13, completed=10)
    # 标记 10 个为 done
    with open(progress_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for i in range(1, 11):
        data["batch_status"][str(i)] = "done"
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    result = run_cmd("get-next", "--progress", progress_path)
    assert len(result["batches"]) == 3
    assert result["running"] == 3
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_get_next_returns_max_10_batches -v
python -m pytest test_coordinator.py::test_get_next_returns_fewer_when_near_end -v
```
预期：FAIL — `coordinator.py not found`

- [ ] **Step 3: 编写 coordinator.py 基础结构 + get-next**

```python
"""
coordinator.py — 并发协调器：管理批次状态和并发槽位

子命令：
  get-next        获取本轮可启动的批次列表（最多 MAX_CONCURRENCY 个）
  mark-done       标记批次完成
  mark-failed     标记批次失败
  summary         查看当前进度
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any

MAX_CONCURRENCY = 10  # 硬限制：同一时刻最多 10 个 Worker 在跑


def load_progress(progress_path: str) -> dict[str, Any]:
    """读取进度文件，不存在时报错。"""
    if not os.path.exists(progress_path):
        raise FileNotFoundError(f"进度文件不存在: {progress_path}")
    with open(progress_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_progress(progress_path: str, progress: dict[str, Any]) -> None:
    """写入进度文件，自动更新 updated_at。"""
    progress["updated_at"] = datetime.now().isoformat()
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_next_batches(progress_path: str) -> dict[str, Any]:
    """
    获取本轮可启动的批次列表。

    逻辑：
    1. 统计当前 running 状态的批次数
    2. available_slots = MAX_CONCURRENCY - running_count
    3. 如果 ≤0，返回空列表
    4. 从 pending 中取前 available_slots 个（按编号升序）
    5. 同时将这些批次标记为 running，写入 progress.json
    """
    progress = load_progress(progress_path)
    batch_status = progress.get("batch_status", {})

    running_count = sum(1 for s in batch_status.values() if s == "running")
    available_slots = MAX_CONCURRENCY - running_count

    if available_slots <= 0:
        return {
            "batches": [],
            "running": running_count,
            "slots": 0,
        }

    # 找所有 pending 批次，按编号升序
    pending = sorted(
        [int(b) for b, s in batch_status.items() if s == "pending"]
    )

    # 取前 available_slots 个
    selected = pending[:available_slots]
    selected_str = [str(b) for b in selected]

    # 原子性标记：选中的批次立即设为 running
    for batch_id in selected_str:
        batch_status[batch_id] = "running"

    save_progress(progress_path, progress)

    return {
        "batches": selected_str,
        "running": running_count + len(selected_str),
        "slots": MAX_CONCURRENCY - (running_count + len(selected_str)),
    }


def main():
    parser = argparse.ArgumentParser(description="auto-qc 并发协调器")
    sub = parser.add_subparsers(dest="command", required=True)

    # get-next
    get_next_p = sub.add_parser("get-next", help="获取本轮可启动的批次列表")
    get_next_p.add_argument("--progress", required=True, help="progress.json 路径")
    get_next_p.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY,
                            help="最大并发数（默认 10）")

    # mark-done
    mark_done_p = sub.add_parser("mark-done", help="标记批次完成")
    mark_done_p.add_argument("batch_id", help="批次编号")
    mark_done_p.add_argument("--progress", required=True, help="progress.json 路径")

    # mark-failed
    mark_failed_p = sub.add_parser("mark-failed", help="标记批次失败")
    mark_failed_p.add_argument("batch_id", help="批次编号")
    mark_failed_p.add_argument("--progress", required=True, help="progress.json 路径")

    # summary
    summary_p = sub.add_parser("summary", help="查看当前进度")
    summary_p.add_argument("--progress", required=True, help="progress.json 路径")

    args = parser.parse_args()

    try:
        if args.command == "get-next":
            result = get_next_batches(args.progress)
        elif args.command == "mark-done":
            result = mark_done(args.progress, args.batch_id)
        elif args.command == "mark-failed":
            result = mark_failed(args.progress, args.batch_id)
        elif args.command == "summary":
            result = show_summary(args.progress)
        else:
            print(f"错误：未知命令 {args.command}", file=sys.stderr)
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except FileNotFoundError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

> **注意**：`mark_done` 和 `mark_failed` 和 `show_summary` 尚未定义，会在后续 Task 中补充。测试 Step 先只跑 get-next 相关的测试。

- [ ] **Step 4: 运行测试验证 get-next 通过**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_get_next_returns_max_10_batches -v
python -m pytest test_coordinator.py::test_get_next_returns_fewer_when_near_end -v
```
预期：PASS

- [ ] **Step 5: 手动验证 get-next 原子性**

```bash
cd ~/.agents/skills/auto-qc/scripts

# 创建测试 progress.json
python -c "
import json
data = {
    'total_batches': 25, 'completed_batches': 0,
    'batch_status': {str(i): 'pending' for i in range(1, 26)},
    'retry_count': {}, 'failed_batches': [], 'phase': 'qc',
    'started_at': '2026-06-01T00:00:00', 'updated_at': '2026-06-01T00:00:00'
}
with open('/tmp/test_progress.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
"

# 连续调用 3 次 get-next（不 mark-done），验证第 2、3 次返回空
python coordinator.py get-next --progress /tmp/test_progress.json
python coordinator.py get-next --progress /tmp/test_progress.json
python coordinator.py get-next --progress /tmp/test_progress.json
```
预期：第 1 次返回 10 个批次，第 2、3 次返回空列表（因为第 1 次已经把 10 个标记为 running，slots=0）

- [ ] **Step 6: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add scripts/coordinator.py scripts/test_coordinator.py
git commit -m "feat: 添加 coordinator.py get-next 子命令

新增并发协调器脚本，get-next 子命令从 progress.json 读取批次状态，
硬限制最多返回 MAX_CONCURRENCY=10 个 pending 批次，并原子性标记为
running 防止重复领取。附带 2 个单元测试。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: coordinator.py — mark-done / mark-failed 子命令

**Files:**
- Modify: `~/.agents/skills/auto-qc/scripts/coordinator.py` (添加 mark_done, mark_failed 函数)
- Modify: `~/.agents/skills/auto-qc/scripts/test_coordinator.py` (添加测试)

- [ ] **Step 1: 写测试 — mark-done 更新状态和计数**

```python
def test_mark_done_updates_status(tmp_path):
    """mark-done 将批次状态设为 done，递增 completed_batches。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")
    _make_progress(progress_path, total=20)

    # 先获取一些批次
    run_cmd("get-next", "--progress", progress_path)

    # 标记 batch 1 为 done
    result = run_cmd("mark-done", "1", "--progress", progress_path)

    assert result["ok"] is True
    assert result["completed"] >= 1

    with open(progress_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["batch_status"]["1"] == "done"


def test_mark_failed_updates_status(tmp_path):
    """mark-failed 将批次状态设为 failed，记录到 failed_batches。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")
    _make_progress(progress_path, total=20)

    run_cmd("get-next", "--progress", progress_path)

    result = run_cmd("mark-failed", "3", "--progress", progress_path)

    assert result["ok"] is True

    with open(progress_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["batch_status"]["3"] == "failed"
    assert "3" in data["failed_batches"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_mark_done_updates_status -v
python -m pytest test_coordinator.py::test_mark_failed_updates_status -v
```
预期：FAIL — `name 'mark_done' is not defined`

- [ ] **Step 3: 实现 mark_done 和 mark_failed 函数**

在 `coordinator.py` 的 `get_next_batches` 函数后添加：

```python
def mark_done(progress_path: str, batch_id: str) -> dict[str, Any]:
    """标记批次完成。更新 batch_status 为 done，递增 completed_batches。"""
    progress = load_progress(progress_path)
    batch_status = progress.get("batch_status", {})

    if batch_id not in batch_status:
        raise ValueError(f"批次 {batch_id} 不存在于进度文件中")

    batch_status[batch_id] = "done"
    progress["completed_batches"] = sum(
        1 for s in batch_status.values() if s == "done"
    )

    # 检查是否全部完成
    if progress["completed_batches"] >= progress["total_batches"]:
        progress["phase"] = "done"

    save_progress(progress_path, progress)

    return {
        "ok": True,
        "completed": progress["completed_batches"],
        "total": progress["total_batches"],
        "remaining": progress["total_batches"] - progress["completed_batches"],
    }


def mark_failed(progress_path: str, batch_id: str) -> dict[str, Any]:
    """标记批次失败。更新 batch_status 为 failed，记录到 failed_batches。"""
    progress = load_progress(progress_path)
    batch_status = progress.get("batch_status", {})

    if batch_id not in batch_status:
        raise ValueError(f"批次 {batch_id} 不存在于进度文件中")

    batch_status[batch_id] = "failed"

    if batch_id not in progress.get("failed_batches", []):
        progress.setdefault("failed_batches", []).append(batch_id)

    save_progress(progress_path, progress)

    return {
        "ok": True,
        "failed": progress["failed_batches"],
    }
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_mark_done_updates_status -v
python -m pytest test_coordinator.py::test_mark_failed_updates_status -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add scripts/coordinator.py scripts/test_coordinator.py
git commit -m "feat: 添加 coordinator.py mark-done / mark-failed 子命令

mark-done 将批次标记为 done 并递增 completed_batches；
mark-failed 将批次标记为 failed 并记录到 failed_batches。
附带 2 个单元测试验证状态更新正确。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: coordinator.py — summary 子命令

**Files:**
- Modify: `~/.agents/skills/auto-qc/scripts/coordinator.py` (添加 show_summary 函数)
- Modify: `~/.agents/skills/auto-qc/scripts/test_coordinator.py` (添加测试)

- [ ] **Step 1: 写测试 — summary 返回各状态数量**

```python
def test_summary_returns_correct_counts(tmp_path):
    """summary 返回 completed/running/pending/failed 各状态数量。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")
    _make_progress(progress_path, total=50)

    # 获取一批（10 个变 running）
    run_cmd("get-next", "--progress", progress_path)

    # 标记几个 done
    for i in range(1, 4):
        run_cmd("mark-done", str(i), "--progress", progress_path)

    result = run_cmd("summary", "--progress", progress_path)

    assert result["completed"] == 3
    assert result["running"] == 7  # 10 - 3
    assert result["pending"] == 40  # 50 - 10
    assert result["failed"] == 0
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_summary_returns_correct_counts -v
```
预期：FAIL — `name 'show_summary' is not defined`

- [ ] **Step 3: 实现 show_summary 函数**

```python
def show_summary(progress_path: str) -> dict[str, Any]:
    """读取 progress.json，返回各状态批次数量统计。"""
    progress = load_progress(progress_path)
    batch_status = progress.get("batch_status", {})

    counts = {"completed": 0, "running": 0, "pending": 0, "failed": 0}
    for status in batch_status.values():
        if status in counts:
            counts[status] += 1

    return {
        **counts,
        "total": progress.get("total_batches", 0),
        "phase": progress.get("phase", "unknown"),
    }
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_summary_returns_correct_counts -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add scripts/coordinator.py scripts/test_coordinator.py
git commit -m "feat: 添加 coordinator.py summary 子命令

summary 读取 progress.json 返回各状态（completed/running/pending/failed）
的批次数量统计。附带 1 个单元测试。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: SKILL.md 改造 — 进度文件创建改用 coordinator

**Files:**
- Modify: `~/.agents/skills/auto-qc/SKILL.md`

当前 Step 2 中进度文件是 Claude 用 Write 工具手动创建的，且 `batch_status` 为空对象 `{}`。改为让 Claude 调用 coordinator.py 初始化。

- [ ] **Step 1: 修改 Step 2 的进度文件创建部分**

找到 SKILL.md 中 `确认批次数量后，**立即用 Write 工具创建进度文件**` 这段，替换为：

```markdown
确认批次数量后，**立即调用 coordinator.py 初始化进度文件**：

```bash
python coordinator.py init --progress ~/.agents/skills/auto-qc/tmp/progress.json --total-batches <N>
```

`coordinator.py init` 会创建 `progress.json`，将所有批次初始状态设为 `pending`：

```json
{
  "total_batches": <N>,
  "completed_batches": 0,
  "batch_status": { "1": "pending", "2": "pending", ..., "<N>": "pending" },
  "retry_count": {},
  "failed_batches": [],
  "phase": "qc",
  "started_at": "<当前时间>",
  "updated_at": "<当前时间>"
}
```

> **`--attribution-only` 模式**：phase 初始化为 "attribution"，批次输出目录为 `~/.agents/skills/auto-qc/tmp/attribution_batches`。
```

- [ ] **Step 2: 在 coordinator.py 中添加 init 子命令**

在 `coordinator.py` 的 argparse 部分添加：

```python
# init
init_p = sub.add_parser("init", help="初始化进度文件")
init_p.add_argument("--progress", required=True, help="progress.json 输出路径")
init_p.add_argument("--total-batches", type=int, required=True, help="批次总数")
init_p.add_argument("--phase", default="qc", help="初始阶段（默认 qc）")
```

在 `main()` 的 `if args.command ==` 分支前添加处理：

```python
if args.command == "init":
    result = init_progress(args.progress, args.total_batches, args.phase)
```

添加 `init_progress` 函数（放在 `load_progress` 之前）：

```python
def init_progress(progress_path: str, total_batches: int, phase: str = "qc") -> dict[str, Any]:
    """创建初始进度文件，所有批次状态设为 pending。"""
    progress = {
        "total_batches": total_batches,
        "completed_batches": 0,
        "batch_status": {str(i): "pending" for i in range(1, total_batches + 1)},
        "retry_count": {},
        "failed_batches": [],
        "phase": phase,
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    # 确保输出目录存在
    os.makedirs(os.path.dirname(progress_path) or ".", exist_ok=True)
    save_progress(progress_path, progress)
    return {
        "ok": True,
        "total_batches": total_batches,
        "phase": phase,
    }
```

- [ ] **Step 3: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add SKILL.md scripts/coordinator.py
git commit -m "refactor: Step 2 进度文件创建改用 coordinator.py init

SKILL.md 不再指导 Claude 手动创建 progress.json，改为调用
coordinator.py init --total-batches <N> 初始化，所有批次状态
预设为 pending，为后续 get-next 提供完整数据源。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: SKILL.md 改造 — Step 3 合规检测改为 coordinator 调度

**Files:**
- Modify: `~/.agents/skills/auto-qc/SKILL.md`

这是本次改动最核心的部分：将 Step 3 从"Claude 自己数并发"改为"循环调用 coordinator.py get-next"。

- [ ] **Step 1: 替换 Step 3 的 Worker 分发描述**

找到 SKILL.md 中 `### Step 3: 分发 Worker（合规检测）` 整个段落，替换为：

```markdown
### Step 3: 分发 Worker（合规检测）

**`--attribution-only` 模式下跳过此步骤。**

**使用 `coordinator.py` 脚本控制并发。** 循环执行以下操作：

1. **获取任务**：调用 `coordinator.py get-next --progress ~/.agents/skills/auto-qc/tmp/progress.json`
   - 脚本返回 `batches` 列表（最多 10 个），已自动标记为 `running`
   - 如果 `batches` 为空，退出循环（所有批次处理完成）

2. **分发 Worker**：对 `batches` 中的每个批次 N：
   - 读取 `batch_N.json`
   - 读取 `worker-prompt.md` 模板
   - 将规则包 JSON + 批次数据 + 模板组合成 Worker Prompt
   - 使用 `Agent` 工具启动 Worker sub-agent（`run_in_background=true`），传入组合后的 Prompt

3. **收集结果**：等待所有 Worker 返回后，对每个批次：
   - 用 `json_repair` 修复可能的 JSON 格式问题
   - 校验结果（数量、id、rules_checked）
   - **校验通过** → 保存到 `batch_N_result.json`，调用 `coordinator.py mark-done N --progress ~/.agents/skills/auto-qc/tmp/progress.json`
   - **校验失败** → `retry_count[N]++`，如果 `< 3` 则不调用 mark-done（下次 get-next 会自动重新领取）；如果 `>= 3` 则调用 `coordinator.py mark-failed N --progress ~/.agents/skills/auto-qc/tmp/progress.json`

4. **汇报**：每完成 10 批（或 10%），向用户汇报一次

> **重试逻辑**：校验失败的批次不调用 mark-done，其状态保持为 `running`。下次循环时 coordinator.py 不会再次返回该批次。需要手动处理：如果 retry_count < 3，将批次状态重置为 `pending`（通过直接编辑 progress.json），下次 get-next 会重新领取。
```

> **注意**：重试逻辑需要协调。当前设计下，get-next 已经把批次标记为 running，如果校验失败，批次保持 running 状态不会重新领取。需要一种方式让失败的批次回到 pending 池。

修改重试策略为：校验失败时，Claude 直接将该批次状态重置为 `pending`（通过编辑 progress.json），retry_count++。这样下次 get-next 会重新领取。

- [ ] **Step 2: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add SKILL.md
git commit -m "refactor: Step 3 合规检测改为 coordinator.py 调度

Worker 分发不再由 Claude 自行计数控制并发，改为循环调用
coordinator.py get-next 获取批次（硬限制最多 10 个），完成后调用
mark-done / mark-failed 汇报结果。校验失败的批次重置为 pending
进入下一轮重新领取。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: SKILL.md 改造 — Step 5 归因分析改为 coordinator 调度

**Files:**
- Modify: `~/.agents/skills/auto-qc/SKILL.md`

- [ ] **Step 1: 替换 Step 5 的归因分发描述**

找到 SKILL.md 中 Step 5 的第 5 步，将：

```markdown
5. 同样并发不超过 10 个 Worker Agent 逐批归因（每批处理前更新 `batch_status` 为 `"running"`）
6. 收集结果 → 校验 → 保存到 `~/.agents/skills/auto-qc/tmp/attribution_results.json`
```

替换为：

```markdown
5. **使用 `coordinator.py` 控制并发**，循环执行：
   a. 调用 `coordinator.py get-next --progress ~/.agents/skills/auto-qc/tmp/progress.json`
   b. 如果 `batches` 为空，退出循环
   c. 对每个批次：读取数据 + attribution-rules.md + attribution-prompt.md → 启动 Worker Agent
   d. 收集结果 → 校验 → 调用 `coordinator.py mark-done N` 或 `mark-failed N`
6. 所有归因完成后，汇总结果保存到 `~/.agents/skills/auto-qc/tmp/attribution_results.json`
7. 更新 `phase = "reporting"` 到 progress.json
```

- [ ] **Step 2: 更新文件结构**

将 SKILL.md 末尾的文件结构树更新，添加 coordinator.py：

```markdown
```
~/.agents/skills/auto-qc/
├── SKILL.md                        # 本文件
├── templates/
│   ├── worker-prompt.md            # Worker 打标模板
│   ├── attribution-prompt.md       # 归因分析模板
│   └── attribution-rules.md        # 内置归因规则
├── scripts/
│   ├── coordinator.py              # 并发协调器（新增）
│   ├── data_loader.py              # 数据加载 + 预处理 + 批次拆分
│   ├── report_writer.py            # 报告生成 + 临时文件清理
│   └── rules_parser.py             # Markdown 规则解析
└── requirements.txt                # Python 依赖
```
```

- [ ] **Step 3: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add SKILL.md
git commit -m "refactor: Step 5 归因分析改为 coordinator.py 调度

同 Step 3，归因 Worker 分发也改为通过 coordinator.py get-next
获取批次，硬限制并发数。完成后调用 mark-done/mark-failed。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: 集成测试 — 完整流程 mock 验证

**Files:**
- Modify: `~/.agents/skills/auto-qc/scripts/test_coordinator.py`

- [ ] **Step 1: 写集成测试 — 模拟 50 批完整调度流程**

```python
def test_full_workflow_50_batches(tmp_path):
    """模拟 50 个批次的完整 get-next → mark-done 循环。"""
    progress_path = os.path.join(str(tmp_path), "progress.json")

    # 初始化
    init_result = run_cmd("init", "--progress", progress_path, "--total-batches", "50")
    assert init_result["ok"] is True

    completed = 0
    rounds = 0
    while completed < 50:
        rounds += 1

        # 获取本轮任务
        next_result = run_cmd("get-next", "--progress", progress_path)
        batches = next_result["batches"]
        assert len(batches) <= MAX_CONCURRENCY, f"Round {rounds}: got {len(batches)} > {MAX_CONCURRENCY}"

        if not batches:
            # 可能所有 running 都没完成，模拟完成几个
            # 在实际场景中这是 Worker 完成后 mark-done
            # 测试中我们模拟：把前几个 running 的标记为 done
            with open(progress_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            running_ids = [b for b, s in data["batch_status"].items() if s == "running"]
            if not running_ids:
                raise AssertionError(f"No running batches to complete in round {rounds}")
            for bid in running_ids[:3]:  # 模拟完成 3 个
                run_cmd("mark-done", bid, "--progress", progress_path)
                completed += 1
            continue

        # 模拟全部完成
        for bid in batches:
            run_cmd("mark-done", bid, "--progress", progress_path)
            completed += 1

    # 最终验证
    summary = run_cmd("summary", "--progress", progress_path)
    assert summary["completed"] == 50
    assert summary["running"] == 0
    assert summary["pending"] == 0
    assert rounds > 1  # 必须多轮完成
```

- [ ] **Step 2: 运行测试验证通过**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py::test_full_workflow_50_batches -v
```
预期：PASS

- [ ] **Step 3: 运行全部测试**

```bash
cd ~/.agents/skills/auto-qc/scripts
python -m pytest test_coordinator.py -v
```
预期：全部 PASS（6 个测试）

- [ ] **Step 4: Commit**

```bash
cd ~/.agents/skills/auto-qc
git add scripts/test_coordinator.py
git commit -m "test: 添加 50 批次完整调度集成测试

模拟 50 个批次的 init → get-next → mark-done 完整循环，验证
coordinator.py 在完整工作流中正确管理并发槽位和批次状态。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage 检查：**

| 设计需求 | 覆盖任务 |
|---------|---------|
| get-next 获取 pending 批次，≤10 | Task 1 |
| 原子性标记 running 防重复 | Task 1 |
| mark-done 更新状态 | Task 2 |
| mark-failed 记录失败 | Task 2 |
| summary 统计 | Task 3 |
| init 初始化进度文件 | Task 4 |
| SKILL.md Step 2 改用 coordinator | Task 4 |
| SKILL.md Step 3 改为 coordinator 调度 | Task 5 |
| SKILL.md Step 5 改为 coordinator 调度 | Task 6 |
| 完整流程验证 | Task 7 |

全部覆盖，无遗漏。

**2. Placeholder 扫描：**

无 TBD/TODO/TODO/占位符。所有步骤包含完整代码。

**3. 类型一致性：**

- `progress.json` 的 `batch_status` 值类型统一为 `str`（"pending"/"running"/"done"/"failed"）
- `batch_id` 统一为 `str` 类型（progress.json 中 key 是字符串）
- `retry_count` 统一为 `{str: int}` 字典
- 所有函数返回值格式一致（dict with consistent keys）

**4. 重试逻辑：**

设计中发现一个关键问题：get-next 已经把批次标记为 running，如果校验失败，批次保持 running 不会自动重新领取。Task 5 中明确了处理方式——校验失败时 Claude 将批次状态重置为 `pending`（通过 Edit 工具修改 progress.json），retry_count++。这个逻辑在 SKILL.md 中写清楚即可，不需要 coordinator.py 额外支持。
