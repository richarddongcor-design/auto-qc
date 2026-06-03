"""交叉验证引擎——分层抽样、规则级对比、差异率计算"""
import random
from auto_qc.domain.schemas import CrossValidationResult


def stratified_sample(
    results: list[dict],
    violation_ratio: float = 0.02,
    non_violation_ratio: float = 0.01,
    random_seed: int = 42,
) -> list[dict]:
    """
    分层抽样：违规组抽 violation_ratio，非违规组抽 non_violation_ratio。
    返回抽中的完整结果列表。
    """
    random.seed(random_seed)

    violation_items = []
    non_violation_items = []

    for r in results:
        if r.get("violations"):
            violation_items.append(r)
        else:
            non_violation_items.append(r)

    sample_size_v = max(1, int(len(violation_items) * violation_ratio))
    sample_size_nv = max(1, int(len(non_violation_items) * non_violation_ratio))

    sample = (
        random.sample(violation_items, min(sample_size_v, len(violation_items))) +
        random.sample(non_violation_items, min(sample_size_nv, len(non_violation_items)))
    )

    return sample


def compare_results(
    original: list[dict],
    recheck: list[dict],
) -> CrossValidationResult:
    """
    规则级对比：同一条对话同一个规则，两次判断是否一致。
    original 和 recheck 的每条结果格式：
    {"id": "...", "violations": [{"rule_id": "R01", ...}, ...]}
    """
    original_map = {}
    for r in original:
        original_map[r["id"]] = {v["rule_id"] for v in r.get("violations", [])}

    recheck_map = {}
    for r in recheck:
        recheck_map[r["id"]] = {v["rule_id"] for v in r.get("violations", [])}

    # 统计所有规则判断
    total_judgments = 0
    mismatches = 0

    all_rule_ids = set()
    for rules in original_map.values():
        all_rule_ids.update(rules)
    for rules in recheck_map.values():
        all_rule_ids.update(rules)

    for item_id in original_map:
        if item_id not in recheck_map:
            continue
        for rule_id in all_rule_ids:
            total_judgments += 1
            in_original = rule_id in original_map[item_id]
            in_recheck = rule_id in recheck_map[item_id]
            if in_original != in_recheck:
                mismatches += 1

    return CrossValidationResult.compute(mismatches, total_judgments)
