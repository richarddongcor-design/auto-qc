# 模块重构设计方案

> 日期: 2026-06-23
> 分支: refactor/unify-modules

## 一、目标

1. **统一命名约定** — 同层概念同名，文件名见名知意
2. **消除重复代码** — 废弃文件清理，JSON 处理统一
3. **职责分离** — `core/llm.py` 只做 LLM 调用，JSON 处理独立
4. **保持兼容** — 对外 CLI 入口不变，内部 import 全部更新

---

## 二、目标目录结构

```
src/auto_qc/
├── cli.py                          # 不变
├── core/
│   ├── __init__.py
│   ├── config.py                   # 不动（配置读写）
│   ├── json_tools.py               # ★ 新增：统一 JSON 预处理
│   └── llm.py                      # ★ 精简：纯 LLM 调用层
├── qc/
│   ├── __init__.py
│   ├── engine/                     # ★ 改名（原 framework/）
│   │   ├── __init__.py
│   │   ├── coordinator.py
│   │   ├── cross_validator.py
│   │   ├── orchestrator.py
│   │   ├── progress.py
│   │   ├── validator.py
│   │   └── worker.py
│   └── rules/                      # ★ 改名（原 domain/）
│       ├── __init__.py
│       ├── loader.py               # ★ 改名（原 data_loader.py）
│       ├── merger.py               # 不变
│       ├── prompts.py              # 不变
│       ├── report.py               # 不变
│       ├── rules.py                # 不变
│       └── schemas.py              # 不变
├── pi/
│   ├── __init__.py
│   ├── agents/
│   │   ├── __init__.py
│   │   └── config.yaml             # 不变（LLM 参数）
│   ├── data/                       # ★ 改名（原 core/）
│   │   ├── __init__.py
│   │   ├── domain_loader.py        # 不变
│   │   └── prompt_loader.py        # 不变
│   ├── domains/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── recruitment/
│   ├── engine/                     # 不变
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   ├── scheduler.py
│   │   ├── tracer.py
│   │   └── validator.py            # ★ 精简：schema 校验移至 core/json_tools.py
│   └── utils/                      # ★ 精简：删 json_utils.py
│       ├── __init__.py
│       ├── excel_parser.py
│       └── report_generator.py
└── web/                            # 不动
    ├── app.py
    ├── templates.py
    ├── routers/
    └── templates/
```

### 命名变更对照

| 旧路径 | 新路径 | 变更类型 |
|---|---|---|
| `core/llm.py`（JSON 部分） | `core/json_tools.py` | 拆出新文件 |
| `core/llm.py`（LLM 部分） | `core/llm.py`（精简） | 删除 JSON |
| `pi/utils/json_utils.py` | — | 删除 |
| `qc/domain/data_loader.py` | `qc/rules/loader.py` | 改名 |
| `qc/domain/` 其余文件 | `qc/rules/` | 目录改名 |
| `qc/framework/` 全目录 | `qc/engine/` | 目录改名 |
| `pi/core/` 全目录 | `pi/data/` | 目录改名 |

---

## 三、分步实施

### Step 1: `core/json_tools.py` — 新增统一 JSON 层

**来源**：从 `core/llm.py` 搬过来 + `pi/utils/json_utils.py` 的功能合并

**包含**：
- `extract_json(text) -> Any` — 从 LLM 输出提取 JSON
- `extract_json_str(text) -> str` — 返回 JSON 字符串（兼容 QC 旧接口）
- `repair_json(text) -> str | None` — 修复常见 JSON 格式错误
- `validate_schema(data, schema_name) -> tuple[bool, str]` — schema 校验

**不包含**：
- 不依赖 `openai` / `httpx`
- 不依赖任何业务模块
- 纯函数，可独立测试

**依赖**：`json_repair` 库（生产已有）

### Step 2: `core/llm.py` — 精简

**删除**：
- `_heal_json()` 函数
- `extract_json()` 函数
- `extract_json_str()` 函数

**改为引用**：
- `from auto_qc.core.json_tools import extract_json, extract_json_str`

**保留**：
- `TokenStats` dataclass
- `LlmConfig` dataclass
- `LlmClient` 类
- `call_llm()`、`call_llm_with_retry()`（QC 兼容接口）

### Step 3: 删除废弃文件

删除 `pi/utils/json_utils.py`（功能已由 `core/json_tools.py` 覆盖）

### Step 4: `qc/framework/` → `qc/engine/`

git mv + 更新所有 import 路径。

### Step 5: `qc/domain/` → `qc/rules/`

git mv + 文件名调整：
- `data_loader.py` → `loader.py`

### Step 6: `pi/core/` → `pi/data/`

git mv 纯目录名，文件内容不变。

### Step 7: `pi/engine/validator.py` 精简

将 schema 校验函数移至 `core/json_tools.py`，validator 层保持轻量。

---

## 四、影响分析

### 需要更新 import 的文件

估算约 15-20 个 Python 文件需要改 import 路径：

| 搜索模式 | 命中数 | 说明 |
|---|---|---|
| `from auto_qc.qc.framework` | ~7 | → `from auto_qc.qc.engine` |
| `from auto_qc.qc.domain` | ~10 | → `from auto_qc.qc.rules` |
| `from auto_qc.pi.core` | ~3 | → `from auto_qc.pi.data` |
| `from auto_qc.pi.utils.json_utils` | ~0 | 已无引用，但要确认 |
| `from auto_qc.core.llm import.*json` | ~3 | → `from auto_qc.core.json_tools` |

### 测试文件

- `tests/framework/` → `tests/engine/`（目录名跟随）
- `tests/domain/` → `tests/rules/`（目录名跟随）
- 新增 `tests/core/test_json_tools.py`

### 不影响

- CLI 命令（`auto-qc-tool qc` / `auto-qc-tool pi`）
- Web URL 路由
- 规则集 JSON 文件（`rules/*.json`）
- 配置文件（`.env` / `config.yaml`）

---

## 五、测试策略

1. 每一步改完后运行 `pytest tests/ -q`，保证不红
2. 新增 `tests/core/test_json_tools.py` 覆盖所有 JSON 提取/修复场景
3. `git mv` 目录时用 `--move` 保留文件历史
