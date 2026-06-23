"""历史记录查询 — 统一接口，支持 QC / PI 筛选。"""
import json
from pathlib import Path


def get_runs(run_type: str = "all", limit: int = 50) -> list[dict]:
    """扫描 output/ 目录获取运行记录，支持按类型筛选。

    Args:
        run_type: "all" | "qc" | "pi"
        limit: 最大返回条数

    Returns:
        按时间倒序排列的运行记录列表，每条包含 run_type 字段。
    """
    output_dir = Path("output")
    if not output_dir.exists():
        return []

    runs = []
    for d in sorted(output_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        summary_file = d / "summary.json"
        if not summary_file.exists():
            continue
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # 判断运行类型
        has_domain = bool(summary.get("domain"))
        is_qc = (d / "report.xlsx").exists() or "rule_sets" in summary or "rule_sets" in summary.get("rule_sets", {})
        is_qc = is_qc or ("total_conversations" in summary and "domain" not in summary)

        if is_qc and has_domain:
            # 两个字段都有时按 rule_sets 判断
            is_qc = "rule_sets" in summary

        entry = {
            "id": d.name,
            "run_type": "qc" if is_qc else ("pi" if has_domain else None),
            "data_file": summary.get("data_file", ""),
            "status": summary.get("status", "completed"),
        }

        if entry["run_type"] is None:
            continue  # skip unknown entries

        # 类型筛选
        if run_type != "all" and entry["run_type"] != run_type:
            continue

        # QC 专有字段
        if is_qc:
            entry["total"] = summary.get("total_conversations", 0)
            entry["violation_rate"] = summary.get("violation_rate", "")
        else:
            entry["domain"] = summary.get("domain", "")
            entry["run_id"] = summary.get("run_id", "")

        runs.append(entry)
        if len(runs) >= limit:
            break

    return runs


def get_recent_qc_runs(limit: int = 10) -> list[dict]:
    """兼容接口：只返回质检记录。"""
    return get_runs(run_type="qc", limit=limit)


def get_recent_pi_runs(limit: int = 10) -> list[dict]:
    """兼容接口：只返回问题挖掘记录。"""
    return get_runs(run_type="pi", limit=limit)
