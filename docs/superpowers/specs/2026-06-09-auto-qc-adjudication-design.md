# auto-qc 交叉验证自动纠正 + 一致性保障

**日期**: 2026-06-09
**状态**: Final

---

## 1. 动机

当前交叉验证只做检测不做纠正。当 Kappa < 0.6 时仅打印警告，质检结果仍然使用第一次（可能有偏差的）判断。

目标：三步走保障结果一致性
1. 固定 LLM 参数（已完成：`temperature=0` + `seed=42`）
2. 交叉验证低一致性自动纠正（本设计）
3. 最终报告中显式标注一致性水平

---

## 2. 裁决流程

```
Step 5 交叉验证
  │
  ├── 分层抽样 200 条
  ├── LLM 复检
  ├── 规则级 Kappa 计算
  │
  ├── Kappa ≥ 0.6 → 正常通过
  │
  └── Kappa < 0.6 → 对该规则执行裁决
       │
       ├── 找出该规则下 original ≠ recheck 的对话 ID 列表
       ├── 构造裁决 prompt（带上前两次判断让 LLM 对比决定）
       ├── 调 LLM 第三次判断
       ├── 三局两胜：取 majority 作为最终结果
       │
       ├── majority 与 original 不一致 → 修正 qc_results
       ├── 修正后重新算 Kappa
       │
       └── 修正后 Kappa 仍 < 0.6 → 报告标注 "低一致性"
```

---

## 3. 裁决粒度

分歧是 **规则×对话** 级别的，不是全量重跑。

**示例：** 200 条抽检中 RULE-002 有 30 条判罚不一致：

```
不一致对话列表: [conv_01, conv_15, conv_42, ...]
裁决 prompt:
  每条对话给出原始判断和复检判断，让 LLM 决定哪次正确

  "以下是第 X 条对话。请对比两次判断：
   第一次判断: violations=["RULE-002"] (违规)
   第二次判断: violations=[] (通过)
   请给出你的最终裁决（需附推理）"
```

只对这 30 条×该条规则的判断调 LLM，不涉及其他规则或其他对话。

---

## 4. 修改文件

| 文件 | 操作 |
|------|------|
| `src/auto_qc/framework/cross_validator.py` | 新增 `adjudicate()` + `_build_adjudication_prompt()` |
| `src/auto_qc/framework/orchestrator.py` | Step 5 中 Kappa < 0.6 时调用裁决流程 |
| `src/auto_qc/domain/schemas.py` | `CrossValidationResult` 增加 `adjudicated_rules: list[str]` 标记哪些规则被裁决过 |
| `tests/framework/test_cross_validator.py` | 新增裁决测试 |

### 4.1 cross_validator.py 新增函数

```python
def adjudicate(
    original: list[dict],
    recheck: list[dict],
    qc_results: list[dict],
    rule_id: str,
    call_llm_fn,
) -> tuple[list[dict], float]:
    """
    对指定规则的争议对话执行第三次裁决。

    参数:
        original: 第一次抽检结果（200 条）
        recheck: 第二次复检结果（200 条）
        qc_results: 全量质检结果（将被修正）
        rule_id: 需要裁决的规则 ID
        call_llm_fn: LLM 调用函数，用于第三次判断

    返回:
        (修正后的 qc_results, 修正后的 Kappa)
    """
```

### 4.2 orchestrator.py 修改

Step 5 中增加：

```python
cross_result = compare_results(sample, recheck_results)
if cross_result.kappa < 0.6:
    for rule_id, stats in cross_result.per_rule.items():
        if stats["kappa"] < 0.6:
            print(f"  裁决 {rule_id}: Kappa={stats['kappa']:.2f}，开始第三次判断...")
            qc_results, new_kappa = adjudicate(
                sample, recheck_results, qc_results, rule_id, call_llm_with_retry
            )
            cross_result.per_rule[rule_id]["kappa"] = new_kappa
            cross_result.per_rule[rule_id]["adjudicated"] = True
            cross_result.adjudicated_rules.append(rule_id)
```

---

## 5. 测试策略

| 测试 | 场景 |
|------|------|
| `test_adjudicate_no_disagreement` | original == recheck，不应触发裁决 |
| `test_adjudicate_fixes_disagreement` | 构造分歧数据，模拟 LLM 裁决返回 majority，验证结果被修正 |
| `test_adjudicate_prompt_format` | 裁决 prompt 包含前两次判断 |

---

## 6. 与现有功能的关系

- `temperature=0` + `seed=42` 已在前置步骤完成（`worker.py`）
- 裁决调用复用 `call_llm_with_retry`，享受重试、token 统计
- 修正后的 `qc_results` 会体现在最终报告中
- `summary.json` 新增 `adjudication` 字段记录裁决统计

---

## 7. 不做的事

- ❌ 不修改批次处理逻辑（保持 25 条/批）
- ❌ 不引入 1-by-1 模式（本次不做）
- ❌ 不做规则管理 CLI（本次不做）
