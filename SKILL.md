---
name: auto-qc
description: 外呼通话对话文本质检。用户指定数据 Excel 和规则文件后，自动完成大规模质检（合规检测 + 归因分析），输出 Excel 报告。支持 1w-5w 条数据。
---

# auto-qc 外呼通话文本质检

## 触发方式

用户输入：`/auto-qc --data <excel路径> --rules <规则路径> [--no-attribution] [--attribution-only] [--output <报告路径>] [--keep-temp]`

参数说明：
- `--data`（必需）：源数据 Excel 文件路径
- `--rules`（必需）：合规规则 Markdown 文件路径（`--attribution-only` 模式下不需要）
- `--no-attribution`（可选）：关闭归因分析，默认开启
- `--attribution-only`（可选）：仅执行归因分析（使用内置归因规则）
- `--output`（可选）：自定义报告输出路径。默认输出到数据文件同目录，文件名格式：`<原始文件名>_质检报告_<时间戳>.xlsx`
- `--keep-temp`（可选）：保留处理过程中的临时文件

**运行模式：**

| 命令 | 行为 |
|------|------|
| `--data <路径> --rules <路径>` | 默认全量：合规检测 + 归因分析 |
| `--data <路径> --rules <路径> --no-attribution` | 仅合规检测 |
| `--data <路径> --attribution-only` | 仅归因分析（内置归因规则，不需要合规规则） |

## 核心原则

**⚠️ LLM 主导原则**：
- 质检判断（合规检测 + 归因分析）必须由 Claude sub-agent 完成
- Python 只负责 I/O：读 Excel、写 Excel、预处理对话、拆分批次
- 禁止用 Python 代码做质检判断

**Harness 范式**：统一框架，两次运行
- 通道一：注入合规规则 → 合规检测
- 通道二：注入归因规则 → 归因分析
- 两通道结构相同：拆分 → 分发 → 收集 → 校验 → 汇总

## 执行流程

### Step 0: 环境检查

1. 检查 Python 依赖是否已安装：
   ```bash
   python -c "import openpyxl, pandas, json_repair; print('OK')"
   ```
   如果报错，执行 `uv pip install -r ~/.agents/skills/auto-qc/requirements.txt`

2. 验证文件路径：
   - 检查 `--data` Excel 文件是否存在
   - 如果是合规检测模式：检查 `--rules` 规则文件是否存在
   - 如果是归因分析模式：检查 skill 目录下的 `templates/attribution-rules.md` 和 `templates/attribution-prompt.md` 是否存在
   - 检查 `templates/worker-prompt.md` 是否存在

### Step 1: 解析规则

**如果是合规检测模式（非 `--attribution-only`）：**

运行规则解析器，将 rules.md 转为 JSON 规则包：

```bash
cd ~/.agents/skills/auto-qc/scripts
python rules_parser.py --rules <规则路径> --output ~/.agents/skills/auto-qc/tmp/rules_package.json
```

读取 `rules_package.json`，确认规则数量和规则 ID 列表。

**如果是 `--attribution-only` 模式：** 跳过合规检测，直接进入 Step 5（归因分析），phase 初始化为 "attribution"。

### Step 2: 加载数据 + 拆分批次

运行数据加载器：

```bash
cd ~/.agents/skills/auto-qc/scripts
mkdir -p ~/.agents/skills/auto-qc/tmp
python data_loader.py load --data <数据路径> --batch-size 100 --output ~/.agents/skills/auto-qc/tmp/batches
```

这会输出：
- N 个批次 JSON 文件：`batch_1.json`, `batch_2.json`, ...
- 每个文件包含 100 条对话（预处理为可读格式）

确认批次数量后，**立即用 Write 工具创建进度文件** `~/.agents/skills/auto-qc/tmp/progress.json`（不要只打印到终端）：

```json
{
  "total_batches": <N>,
  "completed_batches": 0,
  "batch_status": {},
  "retry_count": {},
  "failed_batches": [],
  "phase": "qc",
  "started_at": "<当前时间>",
  "updated_at": "<当前时间>"
}
```

**进度文件字段说明：**
- `batch_status`: `{ "1": "pending", "2": "done", "3": "running", ... }` — 每个批次状态（pending/running/done/failed）
- `retry_count`: `{ "1": 0, "2": 1, ... }` — 每个批次的重试次数
- `phase`: 当前阶段（qc / cross_validation / attribution / reporting / done）

### Step 3: 分发 Worker（合规检测）

**`--attribution-only` 模式下跳过此步骤。**

**并发不超过 5 个 Worker Agent**，按批次逐批分发。如果批次超过 5 个，分批处理（先跑 1-5，等结果回来后更新进度，再跑 6-10）。

对每个批次，执行以下操作：

1. 读取 `batch_N.json`
2. 读取 `worker-prompt.md` 模板
3. 将规则包 JSON + 批次数据 + 模板组合成 Worker Prompt
4. **更新进度**：将 `batch_status[N]` 设为 `"running"`，用 Edit 工具更新 progress.json
5. 使用 `Agent` 工具启动 Worker sub-agent，传入组合后的 Prompt
6. 收集 Worker 返回的 JSON 结果
7. 用 `json_repair` 修复可能的 JSON 格式问题
8. 校验结果：
   - 结果数量 == 批次数量（100 条）？
   - 每条都有 `id`？
   - `rules_checked` 包含所有规则 ID？
9. **校验通过** → 用 Write 工具保存到 `~/.agents/skills/auto-qc/tmp/batches/batch_N_result.json`（**固定命名：`batch_N_result.json`，无其他后缀**）
10. **更新进度**：`batch_status[N] = "done"`, `completed_batches++`，更新 progress.json

**失败重试：**
- 校验失败 → `retry_count[N]++`，更新 progress.json
- `retry_count[N] < 3` → 重新 dispatch 该批次
- `retry_count[N] >= 3` → `batch_status[N] = "failed"`，记录到 `~/.agents/skills/auto-qc/tmp/failed_batches.json`，继续下一批

**关键：结果文件命名必须一致。** 只有 `batch_N_result.json` 格式，禁止 `_final`、`_v2` 等后缀。

**进度汇报：**
- 每完成 10 批（或 10%），向用户汇报一次："已完成 X/N 批（XX%）"

### Step 4: 交叉验证

**`--attribution-only` 模式下跳过此步骤。**

合规检测全部完成后，执行交叉验证：

1. 统计整体违规率
2. 按违规/无违规分层抽样：
   - 违规组抽 2%，无违规组抽 1%
3. 将抽中的对话重新组合成批次，启动新的 Worker sub-agent 做 double-check
4. 对比两次结果（同一条对话同一个规则，两次判断是否一致）
5. 计算差异率：
   - < 5%：正常
   - 5%-10%：标记可疑
   - > 10%：扩大抽样到 5%

### Step 5: 归因分析（可选）

如果用户指定了 `--no-attribution` 或 `--attribution-only` 模式已执行过合规检测，执行归因分析：
- `--no-attribution`：跳过归因分析
- `--attribution-only`：跳过合规检测直接进入此步骤，phase = "attribution"
- 默认模式：合规检测完成后自动进入此步骤，phase = "attribution"

1. 从 Excel 中过滤出意向结果 ≠ "A(有意向)" 的对话
2. 运行数据加载器（带过滤）：
   ```bash
   python data_loader.py load --data <数据路径> --batch-size 100 --output ~/.agents/skills/auto-qc/tmp/attribution_batches --exclude-intent "A(有意向)"
   ```
3. 读取 `attribution-rules.md` 内置归因规则
4. 读取 `attribution-prompt.md` 模板
5. 同样并发不超过 5 个 Worker Agent 逐批归因（每批处理前更新 `batch_status` 为 `"running"`）
6. 收集结果 → 校验 → 保存到 `~/.agents/skills/auto-qc/tmp/attribution_results.json`
7. 更新 `phase = "reporting"` 到 progress.json

### Step 6: 生成报告

1. 合并所有批次结果为完整质检报告 JSON：
   ```bash
   python -c "
   import json, glob
   results = []
   for f in sorted(glob.glob('~/.agents/skills/auto-qc/tmp/batches/batch_*_result.json')):
       with open(f) as fh:
           results.extend(json.load(fh)['results'])
   with open('~/.agents/skills/auto-qc/tmp/all_qc_results.json', 'w') as fh:
       json.dump(results, fh, ensure_ascii=False, indent=2)
   "
   ```

2. 生成统计概览 JSON：
   - 总对话数
   - 违规率（违规对话数 / 总对话数）
   - 各规则违规次数（格式：`{"rules_hit": {"R05": 103, "R02": 128, ...}}`）
   - 规则 ID 到名称的映射（从步骤1解析的规则包中提取，格式：`{"rule_names": {"R01": "无视用户明确拒绝", ...}}`）

3. 确定报告输出路径：
   - 如果用户指定了 `--output`，使用用户指定的路径
   - 否则，默认输出到数据文件同目录：`<数据文件目录>/<数据文件名>_质检报告_<YYYYMMDD_HHMMSS>.xlsx`

4. 生成报告 Excel：
   ```bash
   python report_writer.py write \
     --output <报告输出路径> \
     --qc-results ~/.agents/skills/auto-qc/tmp/all_qc_results.json \
     --attribution ~/.agents/skills/auto-qc/tmp/attribution_results.json \
     --stats ~/.agents/skills/auto-qc/tmp/stats.json
   ```

5. 报告路径告知用户

### Step 7: 清理

- 如果用户未指定 `--keep-temp`，清理临时文件：
   ```bash
   python report_writer.py cleanup --dir ~/.agents/skills/auto-qc/tmp
   ```
- 否则提示用户临时文件保留位置

## 断点续跑

每次启动时检查 `~/.agents/skills/auto-qc/tmp/progress.json`：
- 如果存在且 `phase` 不是 "done" → 提示用户："检测到上次中断的进度（phase: <phase>，已完成 X/Y 批），是否继续？"
- 用户确认 → 根据 `phase` 和 `batch_status` 确定从哪个批次继续
  - 读取进度文件，跳过 `batch_status` 为 "done" 的批次
  - 如果有 `batch_status` 为 "running" 的批次（上次中断时正在处理），将其重置为 "pending" 并重跑
  - 如果有 `failed_batches`，询问用户是否重跑这些
- 用户否认 → 清空进度和所有结果文件，从头开始

## 错误处理

| 错误 | 处理方式 |
|------|----------|
| Excel 文件不存在 | 提示用户检查路径 |
| 规则文件不存在 | 提示用户检查路径 |
| 列名匹配失败 | 提示用户，列出当前表头 |
| Worker JSON 解析失败 | 用 json_repair 尝试修复，修复失败则重试批次 |
| Worker 超时/崩溃 | 重试该批次，最多 3 次 |
| 3 次重试都失败 | 记录到 failed_batches.json，不阻塞流程 |
| 交叉验证差异率 > 10% | 扩大抽样比例到 5%，重新验证 |

## 文件结构

```
~/.agents/skills/auto-qc/
├── SKILL.md                        # 本文件
├── templates/
│   ├── worker-prompt.md            # Worker 打标模板
│   ├── attribution-prompt.md       # 归因分析模板
│   └── attribution-rules.md        # 内置归因规则
├── scripts/
│   ├── data_loader.py              # 数据加载 + 预处理 + 批次拆分
│   ├── report_writer.py            # 报告生成 + 临时文件清理
│   └── rules_parser.py             # Markdown 规则解析
└── requirements.txt                # Python 依赖
```
