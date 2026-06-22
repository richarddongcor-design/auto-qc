"""历史记录查询。"""
import json
from pathlib import Path


def get_recent_qc_runs(limit: int = 10) -> list[dict]:
    """扫描 output/ 目录获取最近的质检运行记录。

    质检运行目录以 report.xlsx 为标志，同时需要 summary.json。
    """
    output_dir = Path("output")
    if not output_dir.exists():
        return []

    runs = []
    for d in sorted(output_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        summary_file = d / "summary.json"
        report_file = d / "report.xlsx"
        if summary_file.exists() and report_file.exists():
            try:
                summary = json.loads(summary_file.read_text(encoding="utf-8"))
                runs.append({
                    "id": d.name,
                    "data_file": summary.get("data_file", ""),
                    "violation_rate": summary.get("violation_rate", ""),
                    "total": summary.get("total_conversations", 0),
                    "status": summary.get("status", "completed"),
                })
            except (json.JSONDecodeError, OSError):
                continue
        if len(runs) >= limit:
            break
    return runs


def get_recent_pi_runs(limit: int = 10) -> list[dict]:
    """扫描 output/ 目录获取最近的问题挖掘运行记录。

    问题挖掘运行目录以 summary.json（内容含 domain 字段）为标志，
    且没有同级的 report.xlsx（以此与 QC 运行区分）。
    """
    output_dir = Path("output")
    if not output_dir.exists():
        return []

    runs = []
    for d in sorted(output_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not d.is_dir():
            continue
        summary_file = d / "summary.json"
        report_file = d / "report.xlsx"
        # PI 运行有 summary.json 但没有 report.xlsx
        if summary_file.exists() and not report_file.exists():
            try:
                summary = json.loads(summary_file.read_text(encoding="utf-8"))
                runs.append({
                    "id": d.name,
                    "data_file": summary.get("data_file", ""),
                    "domain": summary.get("domain", ""),
                    "status": summary.get("status", ""),
                    "run_id": summary.get("run_id", ""),
                })
            except (json.JSONDecodeError, OSError):
                continue
        if len(runs) >= limit:
            break
    return runs
