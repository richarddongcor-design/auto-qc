"""
data_loader.py — Excel 读取、列匹配、对话预处理、批次拆分、进度管理

通过子命令调用：
  python data_loader.py load --data <excel路径> --batch-size <int> --output <输出目录>
  python data_loader.py resume --data <excel路径> --output <输出目录>
  python data_loader.py save_progress --data <excel路径> --progress <progress.json路径>
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import openpyxl


# ─── 列名映射 ───

COLUMN_PATTERNS = {
    "id_col": ["id", "通话ID", "call_id", "callId", "通话id"],
    "time_col": ["时间", "通话时间", "call_time", "callTime", "通话日期"],
    "conv_col": ["对话", "对话文本", "conversation", "conv", "通话内容", "对话内容"],
    "intent_col": ["意向", "意向结果", "intent_result", "intentResult", "结果"],
}


def match_columns(headers: list[str]) -> dict[str, str]:
    """按关键词匹配 Excel 列名，返回映射字典。匹配失败时抛出 ValueError。"""
    result = {}
    lower_headers = {h.strip().lower(): h for h in headers}

    for key, keywords in COLUMN_PATTERNS.items():
        matched = None
        # 精确匹配（忽略大小写）
        for kw in keywords:
            if kw.lower() in lower_headers:
                matched = lower_headers[kw.lower()]
                break
        # 模糊匹配：关键词在列名中
        if matched is None:
            for h in headers:
                for kw in keywords:
                    if kw.lower() in h.lower():
                        matched = h
                        break
                if matched:
                    break
        if matched is None:
            raise ValueError(
                f"未找到 {key} 对应的列。当前表头: {headers}。"
                f"期望包含以下关键词之一: {keywords}"
            )
        result[key] = matched

    return result


# ─── 对话预处理 ───

def preprocess_conversation(conv_json: list[dict]) -> str:
    """将 TTS/ASR JSON 转为 'AI: xxx / 用户: xxx' 的可读对话文本。"""
    lines = []
    for turn in conv_json:
        tts = turn.get("ttsResult", "").strip()
        asr = turn.get("asrResult", "").strip()
        if tts:
            lines.append(f"AI: {tts}")
        if asr:
            lines.append(f"用户: {asr}")
    return "\n".join(lines)


def preprocess_conversations(conv_raw: str) -> str:
    """处理原始单元格字符串（可能双重编码的 JSON）。"""
    if conv_raw.startswith('"['):
        try:
            conv_raw = json.loads(conv_raw)
        except json.JSONDecodeError:
            pass

    if isinstance(conv_raw, str):
        conv_data = json.loads(conv_raw)
    else:
        conv_data = conv_raw

    return preprocess_conversation(conv_data)


# ─── Excel 加载 + 批次拆分 ───

def load_excel(
    data_path: str,
    batch_size: int = 100,
    filter_intent: Optional[str] = None,
    exclude_intent: Optional[str] = None,
) -> dict[str, Any]:
    """
    读取 Excel，预处理对话，拆分为批次。
    """
    wb = openpyxl.load_workbook(data_path, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    headers = next(rows_iter)
    col_map = match_columns(list(headers))

    id_idx = headers.index(col_map["id_col"])
    time_idx = headers.index(col_map["time_col"])
    conv_idx = headers.index(col_map["conv_col"])
    intent_idx = headers.index(col_map["intent_col"])

    conversations = []
    for row in rows_iter:
        if row[id_idx] is None:
            continue

        intent = str(row[intent_idx]).strip() if row[intent_idx] else ""

        if filter_intent and intent != filter_intent:
            continue

        if exclude_intent and intent == exclude_intent:
            continue

        try:
            conv_text = preprocess_conversations(str(row[conv_idx]))
        except (json.JSONDecodeError, TypeError):
            conv_text = "[对话解析失败]"

        conversations.append({
            "id": str(row[id_idx]),
            "time": str(row[time_idx]).strip() if row[time_idx] else "",
            "intent": intent,
            "conversation": conv_text,
        })

    wb.close()

    # 拆分批次
    batches = []
    for i in range(0, len(conversations), batch_size):
        batches.append(conversations[i:i + batch_size])

    return {
        "total": len(conversations),
        "num_batches": len(batches),
        "batches": batches,
    }


# ─── 进度管理 ───

def load_progress(progress_path: str) -> dict[str, Any]:
    """读取进度文件。不存在时返回空结构。"""
    if os.path.exists(progress_path):
        with open(progress_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "total_batches": 0,
        "completed_batches": 0,
        "batch_status": {},
        "completed_ids": [],
        "failed_batches": [],
        "status": "not_started",
    }


def save_progress(progress_path: str, progress: dict[str, Any]) -> None:
    """写入进度文件。首次创建时自动设置 started_at。"""
    now = datetime.now().isoformat()
    progress["updated_at"] = now
    if "started_at" not in progress:
        progress["started_at"] = now
    with open(progress_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


# ─── CLI 入口 ───

def main():
    parser = argparse.ArgumentParser(description="auto-qc 数据加载器")
    sub = parser.add_subparsers(dest="command", required=True)

    # load 子命令
    load_p = sub.add_parser("load", help="读取 Excel、预处理、拆分批次")
    load_p.add_argument("--data", required=True, help="Excel 文件路径")
    load_p.add_argument("--batch-size", type=int, default=100, help="每批数量")
    load_p.add_argument("--output", required=True, help="批次 JSON 输出目录")
    load_p.add_argument("--filter-intent", help="过滤特定意向结果（保留）")
    load_p.add_argument("--exclude-intent", help="排除特定意向结果（过滤掉）")

    # resume 子命令
    resume_p = sub.add_parser("resume", help="读取进度，返回未完成批次")
    resume_p.add_argument("--data", required=True, help="Excel 文件路径")
    resume_p.add_argument("--output", required=True, help="批次 JSON 输出目录")
    resume_p.add_argument("--progress", required=True, help="进度文件路径")
    resume_p.add_argument("--batch-size", type=int, default=100, help="每批数量")
    resume_p.add_argument("--filter-intent", help="过滤特定意向结果（保留）")
    resume_p.add_argument("--exclude-intent", help="排除特定意向结果（过滤掉）")

    # save_progress 子命令
    save_p = sub.add_parser("save_progress", help="更新进度文件")
    save_p.add_argument("--progress", required=True, help="进度文件路径")
    save_p.add_argument("--batch-id", required=True, help="完成的批次 ID")
    save_p.add_argument("--result-file", required=True, help="该批次的结果 JSON 路径")

    args = parser.parse_args()

    if args.command == "load":
        try:
            result = load_excel(args.data, args.batch_size, args.filter_intent, args.exclude_intent)
        except FileNotFoundError:
            print(f"错误：Excel 文件不存在: {args.data}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"错误：读取 Excel 失败: {e}", file=sys.stderr)
            sys.exit(1)
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, batch in enumerate(result["batches"]):
            batch_file = output_dir / f"batch_{i+1}.json"
            with open(batch_file, "w", encoding="utf-8") as f:
                json.dump({
                    "batch_id": i + 1,
                    "total": len(batch),
                    "conversations": batch,
                }, f, ensure_ascii=False, indent=2)

        print(json.dumps({
            "total": result["total"],
            "num_batches": result["num_batches"],
            "output_dir": str(output_dir),
        }, ensure_ascii=False))

    elif args.command == "resume":
        progress_path = args.progress
        if not os.path.exists(progress_path):
            print(f"错误：进度文件不存在: {progress_path}", file=sys.stderr)
            sys.exit(1)

        progress = load_progress(progress_path)

        if progress["status"] == "not_started":
            # 首次运行，加载全部
            try:
                result = load_excel(args.data, args.batch_size, args.filter_intent, args.exclude_intent)
            except FileNotFoundError:
                print(f"错误：Excel 文件不存在: {args.data}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"错误：读取 Excel 失败: {e}", file=sys.stderr)
                sys.exit(1)
            output_dir = Path(args.output)
            output_dir.mkdir(parents=True, exist_ok=True)

            for i, batch in enumerate(result["batches"]):
                batch_file = output_dir / f"batch_{i+1}.json"
                with open(batch_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "batch_id": i + 1,
                        "total": len(batch),
                        "conversations": batch,
                    }, f, ensure_ascii=False, indent=2)

            progress["total_batches"] = result["num_batches"]
            save_progress(args.progress, progress)

            print(json.dumps({
                "action": "full_load",
                "total": result["total"],
                "num_batches": result["num_batches"],
                "pending_batches": list(range(1, result["num_batches"] + 1)),
            }, ensure_ascii=False))
        else:
            # 检查哪些批次未完成
            pending = []
            for i in range(1, progress["total_batches"] + 1):
                if progress["batch_status"].get(str(i)) != "done":
                    pending.append(i)

            print(json.dumps({
                "action": "resume",
                "completed_batches": progress["completed_batches"],
                "total_batches": progress["total_batches"],
                "pending_batches": pending,
            }, ensure_ascii=False))

    elif args.command == "save_progress":
        progress = load_progress(args.progress)
        batch_id = args.batch_id

        progress["batch_status"][batch_id] = "done"
        progress["completed_batches"] = sum(
            1 for v in progress["batch_status"].values() if v == "done"
        )

        # 读取该批次结果 ID
        if os.path.exists(args.result_file):
            with open(args.result_file, "r", encoding="utf-8") as f:
                batch_result = json.load(f)
            for r in batch_result.get("results", []):
                progress["completed_ids"].append(r.get("id"))

        if progress["completed_batches"] >= progress["total_batches"]:
            progress["status"] = "done"

        save_progress(args.progress, progress)
        print(f"Progress saved: batch {batch_id} done ({progress['completed_batches']}/{progress['total_batches']})")


if __name__ == "__main__":
    main()
