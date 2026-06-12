---
name: auto-qc
description: 外呼通话对话文本质检 v2.0。指定数据 Excel 和规则集，自动完成逐规则打标，输出宽表 Excel 报告。
---

# auto-qc v2.0：多规则集 + 逐规则打标

## 触发方式

用户输入：`/auto-qc --data <excel路径> --rule-sets intention-recruit-tree [--output <报告路径>]`

## 安装

Skill 安装后，agent 在 skill 目录引导执行首次依赖安装：

```bash
cd ~/.claude/skills/auto-qc/
uv sync
```

## 执行方式

```bash
cd ~/.claude/skills/auto-qc/
uv run -m auto_qc.cli \
  --data /path/to/data.xlsx \
  --rule-sets intention-recruit-tree \
  --output ./质检报告.xlsx
```

说明：
- 代码不复制到终端目录，直接在 skill 目录运行
- 输出默认写到终端当前目录（`--output` 可指定绝对路径）
- 内置规则集：`intention-recruit-tree`（意向人选-tree，4条规则）
- `--rule-sets` 支持多个逗号分隔，规则集定义在 `rules/` 目录下
