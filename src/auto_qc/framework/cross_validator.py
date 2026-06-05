"""交叉验证引擎——固定样本分层抽样、规则级 Cohen's Kappa 一致性"""
import random
from auto_qc.domain.schemas import CrossValidationResult


def fixed_sample(
    results: list[dict],
    sample_size: int = 200,
    random_seed: int = 42,
) -> list[dict]:
    """
    固定样本量分层抽样。
    违规组和通过组各抽一半，保证两类都有代表。
    样本量自动封顶：不超过 total × 3/4，防止某组不够时另一组全抽光。
    """
    random.seed(random_seed)

    # 总量太小时直接全量返回
    if len(results) <= sample_size:
        return list(results)

    violation_items = [r for r in results if r.get("violations")]
    non_violation_items = [r for r in results if not r.get("violations")]

    cap = int(len(results) * 0.75)
    actual_size = min(sample_size, cap)

    # 两组尽量均分，但不超过各自的总数
    half = actual_size // 2
    v_sample = random.sample(violation_items, min(half, len(violation_items)))
    nv_remaining = actual_size - len(v_sample)
    nv_sample = random.sample(non_violation_items, min(nv_remaining, len(non_violation_items)))

    combined = v_sample + nv_sample
    random.shuffle(combined)
    return combined


def _cohen_kappa_for_rule(
    original_hit: set[str],
    recheck_hit: set[str],
    all_ids: list[str],
) -> dict:
    """
    对单条规则计算 Cohen's Kappa。

    混淆矩阵：
                 复检违规  复检通过
    原始违规        a        b
    原始通过        c        d

    Returns: {kappa, po, pe, agreement, total_judgments, tp, fp, fn, tn}
    """
    a = b = c = d = 0
    for item_id in all_ids:
        in_orig = item_id in original_hit
        in_recheck = item_id in recheck_hit
        if in_orig and in_recheck:
            a += 1
        elif in_orig and not in_recheck:
            b += 1
        elif not in_orig and in_recheck:
            c += 1
        else:
            d += 1

    total = a + b + c + d
    if total == 0:
        return {"kappa": 0.0, "po": 0.0, "pe": 0.0, "agreement": 0.0,
                "total_judgments": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0}

    po = (a + d) / total
    p_yes_orig = (a + b) / total
    p_yes_recheck = (a + c) / total
    p_no_orig = (c + d) / total
    p_no_recheck = (b + d) / total
    pe = p_yes_orig * p_yes_recheck + p_no_orig * p_no_recheck

    kappa = (po - pe) / (1 - pe) if pe < 1 else 0.0

    return {
        "kappa": round(kappa, 4),
        "po": round(po, 4),
        "pe": round(pe, 4),
        "agreement": round(po, 4),
        "total_judgments": total,
        "tp": a, "fp": c, "fn": b, "tn": d,
    }


def compare_results(
    original: list[dict],
    recheck: list[dict],
) -> CrossValidationResult:
    """
    规则级对比 + Cohen's Kappa。

    original / recheck 每条格式：
    {"id": "...", "violations": [{"rule_id": "R01", ...}, ...]}

    对每条规则分别计算：
    - Cohen's Kappa（排除随机一致）
    - 简单一致率
    - 混淆矩阵 (tp/fp/fn/tn)
    """
    # 建立每条对话的违规规则集合
    orig_map = {}
    for r in original:
        orig_map[r["id"]] = {v["rule_id"] for v in r.get("violations", [])}

    recheck_map = {}
    for r in recheck:
        recheck_map[r["id"]] = {v["rule_id"] for v in r.get("violations", [])}

    # 收集所有出现过的规则 ID
    all_rule_ids: set[str] = set()
    for rules in orig_map.values():
        all_rule_ids.update(rules)
    for rules in recheck_map.values():
        all_rule_ids.update(rules)

    # 两次都有的对话 ID 列表
    common_ids = [i for i in orig_map if i in recheck_map]

    per_rule = {}
    total_judgments = 0
    total_mismatches = 0

    for rule_id in sorted(all_rule_ids):
        orig_hit = {i for i in common_ids if rule_id in orig_map[i]}
        recheck_hit = {i for i in common_ids if rule_id in recheck_map[i]}

        stats = _cohen_kappa_for_rule(orig_hit, recheck_hit, common_ids)
        mismatches = stats["fp"] + stats["fn"]

        total_judgments += stats["total_judgments"]
        total_mismatches += mismatches

        per_rule[rule_id] = {
            "kappa": stats["kappa"],
            "agreement": stats["agreement"],
            "total_judgments": stats["total_judgments"],
            "mismatches": mismatches,
            "tp": stats["tp"], "fp": stats["fp"],
            "fn": stats["fn"], "tn": stats["tn"],
        }

    return CrossValidationResult.compute(total_mismatches, total_judgments, per_rule)
