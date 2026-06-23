"""Excel 读取、列匹配、对话预处理、批次拆分"""
import json
from pathlib import Path
import openpyxl
from auto_qc.qc.domain.schemas import Conversation, Batch


COLUMN_PATTERNS = {
    "id_col": ["id", "通话ID", "call_id", "callId", "通话id"],
    "time_col": ["时间", "通话时间", "call_time", "callTime", "通话日期"],
    "conv_col": ["对话", "对话文本", "conversation", "conv", "通话内容", "对话内容"],
}


def _match_columns(headers: list[str]) -> dict[str, str]:
    """按关键词匹配 Excel 列名。"""
    result = {}
    for key, keywords in COLUMN_PATTERNS.items():
        matched = None
        for kw in keywords:
            for h in headers:
                if kw.lower() in h.lower():
                    matched = h
                    break
            if matched:
                break
        if matched is None:
            raise ValueError(
                f"未找到 {key} 对应的列。当前表头: {headers}。期望关键词: {keywords}"
            )
        result[key] = matched
    return result


def _preprocess_conversation(conv_json: list[dict]) -> str:
    """将 TTS/ASR JSON 转为可读文本。"""
    lines = []
    for turn in conv_json:
        tts = turn.get("ttsResult", "").strip()
        asr = turn.get("asrResult", "").strip()
        if tts:
            lines.append(f"AI: {tts}")
        if asr:
            lines.append(f"用户: {asr}")
    return "\n".join(lines)


def _preprocess_raw(conv_raw: str) -> str:
    """处理原始单元格数据（可能双重编码的 JSON）。"""
    text = str(conv_raw)
    if text.startswith('"['):
        try:
            text = json.loads(text)
        except json.JSONDecodeError:
            pass
    if isinstance(text, str):
        data = json.loads(text)
    else:
        data = text
    return _preprocess_conversation(data)


def load_conversations(
    data_path: str,
    batch_size: int = 100,
) -> list[Batch]:
    """
    读取 Excel，预处理对话，按 batch_size 拆分为 Batch 列表。
    """
    wb = openpyxl.load_workbook(data_path, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    headers = list(next(rows_iter))
    col_map = _match_columns(headers)

    id_idx = headers.index(col_map["id_col"])
    time_idx = headers.index(col_map["time_col"])
    conv_idx = headers.index(col_map["conv_col"])

    conversations = []
    for row in rows_iter:
        if row[id_idx] is None:
            continue

        try:
            conv_text = _preprocess_raw(str(row[conv_idx]))
        except (json.JSONDecodeError, TypeError):
            conv_text = "[对话解析失败]"

        conversations.append(Conversation(
            id=str(row[id_idx]),
            time=str(row[time_idx]).strip() if row[time_idx] else "",
            conversation=conv_text,
        ))

    wb.close()

    if not conversations:
        raise ValueError("未从 Excel 中读取到任何有效数据")

    batches = []
    for i in range(0, len(conversations), batch_size):
        chunk = conversations[i:i + batch_size]
        batches.append(Batch(batch_id=i // batch_size + 1, conversations=chunk))

    return batches


def save_batches(batches: list[Batch], output_dir: str) -> None:
    """将批次列表保存为 JSON 文件到指定目录。"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for batch in batches:
        file_path = out / f"batch_{batch.batch_id}.json"
        data = {
            "batch_id": batch.batch_id,
            "total": batch.size,
            "ids": batch.ids,
            "conversations": [
                {"id": c.id, "time": c.time, "conversation": c.conversation}
                for c in batch.conversations
            ],
        }
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
