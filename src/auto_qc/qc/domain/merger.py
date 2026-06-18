"""逐规则打标结果合并为宽表"""


def merge_to_wide_rows(
    per_rule_results: dict[str, dict[str, dict]],
    conversations: list[dict],
    rule_names: dict[str, str],
) -> list[dict]:
    """
    将逐规则打标结果合并为宽表行。

    per_rule_results: {
        "auto-pi_R01": {"001": {"violates": True, "evidence": "..."}, ...},
        ...
    }
    conversations: [{"id": "001", "time": "...", "intent": "..."}, ...]

    返回:
    [{
        "id": "001", "time": "...", "intent": "...",
        "rules": {
            "auto-pi_R01": {"result": "违规", "evidence": "...", "rule_name": "答非所问"},
            ...
        },
        "summary": "答非所问：证据\n语气生硬：证据"
    }, ...]
    """
    wide_rows = []
    for conv in conversations:
        cid = conv["id"]
        rules_result = {}
        for rule_id, conv_results in per_rule_results.items():
            result = conv_results.get(cid, {})
            is_violation = result.get("violates", False)
            rules_result[rule_id] = {
                "result": "违规" if is_violation else "通过",
                "evidence": result.get("evidence", ""),
                "rule_name": rule_names.get(rule_id, rule_id),
            }

        summary_lines = []
        for rule_id, rr in rules_result.items():
            if rr["result"] == "违规":
                summary_lines.append(f"{rr['rule_name']}：{rr['evidence']}")
        summary = "\n".join(summary_lines)

        wide_rows.append({
            "id": cid,
            "time": conv.get("time", ""),
            "intent": conv.get("intent", ""),
            "rules": rules_result,
            "summary": summary,
        })

    return wide_rows
