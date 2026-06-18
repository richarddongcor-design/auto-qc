# Auto-QC 平台重构设计文档

## 1. 概述

将 auto-qc（质检）和 auto-pi（问题挖掘）两个独立项目融合为统一的 Auto-QC 平台。提供双模式入口：
- **Web UI**：面向人的直观操作界面（FastAPI + Jinja2 + HTMX）
- **CLI**：面向 AI/自动化调用的命令行接口

## 2. 架构总览

```
auto-qc/
├── src/auto_qc/
│   ├── cli.py           # 统一 CLI（子命令: qc / pi）
│   ├── web/             # FastAPI Web 应用
│   │   ├── app.py       # 应用入口
│   │   ├── routers/
│   │   │   ├── qc.py    # 质检页面路由
│   │   │   ├── pi.py    # 问题挖掘页面路由
│   │   │   └── config.py # 配置页面路由
│   │   ├── templates/   # Jinja2 模板
│   │   └── static/      # CSS / JS
│   ├── core/            # 公共组件（两业务共享）
│   │   ├── llm.py       # LLM 客户端统一封装（QC 和 PI 共用）
│   │   ├── config.py    # 全局配置管理（LLM 配置读写）
│   │   └── data.py      # Excel 读取公共逻辑
│   ├── qc/              # 质检业务（从原 src/auto_qc/ 迁移）
│   │   ├── orchestrator.py
│   │   ├── rules.py
│   │   ├── prompts.py
│   │   ├── report.py
│   │   ├── merger.py
│   │   ├── schemas.py
│   │   ├── validator.py
│   │   ├── coordinator.py
│   │   └── worker.py    # 仅保留 QC 特有的 prompt/解析逻辑
│   └── pi/              # 问题挖掘业务（从 auto-pi/harness 迁移）
│       ├── agents/
│       ├── core/
│       ├── domains/
│       ├── engine/
│       └── utils/
├── rules/               # JSON 规则集目录（不变）
├── .env                 # 环境变量
└── output/              # 运行输出目录
```

## 3. LLM 配置全局共享

QC 和 PI 当前各自有一套 LLM 调用代码，重构后统一为 `core/llm.py`：

- 配置来源：`.env` 文件（LLM_BASE_URL、LLM_API_KEY、LLM_MODEL）
- Web UI 的「配置页」读写同一个 `.env` 文件，保存后立即生效
- 两业务调用同一个 `call_llm()` 函数，共享 token 统计和重试逻辑
- 并发数各自独立控制（QC 按批次并发，PI 按任务并发）

## 4. 页面结构

| 导航 | 页面 | 内容 |
|------|------|------|
| 质检 | 质检首页 | 上传 Excel → 选规则集 → 开始质检 → 实时进度 → 结果展示 |
| 问题挖掘 | 挖掘首页 | 上传 Excel → 选领域配置 → 开始挖掘 → 阶段进度 → 结果展示 |
| 配置 | LLM 配置 | API Key / Base URL / 模型 / 并发数 — 表单保存 |
| 配置 | 规则管理 | 规则集列表 → 展开编辑（描述/检测逻辑/严重程度/启用开关） |

各页面采用顶部标签切换、单页内容滚动、不做侧边栏。

## 5. 数据流

```
用户上传 Excel → core/data.py 解析 → 按业务分发
  ├─ qc: 规则加载 → LLM 逐规则打标 → 合并结果 → 生成 xlsx 报告
  └─ pi: 数据分块 → 6 阶段管线处理 → 输出规则/报告

结果保存至 output/{timestamp}_{run_name}/ 目录
Web UI 读取 output/ 目录展示历史记录
```

## 6. 非功能需求

- **CLI**：保持现有 `auto-qc qc run --data ... --rule-sets ...` 格式，新增 `auto-qc pi run --data ...` 子命令
- **安全性**：API Key 只写入 `.env`，不在页面中明文回显完整 key（仅显示掩码尾几位）
- **错误处理**：LLM 调用失败时走现有重试机制 + 失败对话标记为通过（不阻塞全流程）
- **无需数据库**：所有状态存文件系统（output/ 目录 + JSON）

## 7. 排除项（本次不做）

- 用户认证/登录
- 数据库存储
- 实时 WebSocket 推送（HTMX 轮询即可）
- Docker 部署
