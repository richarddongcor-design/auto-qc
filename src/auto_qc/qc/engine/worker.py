"""QC 特有的 worker 逻辑（LLM 调用委托给 core/llm.py）。"""
from auto_qc.core.llm import (
    call_llm_with_retry,
    extract_json,
    extract_json_str,
    get_token_stats,
    reset_token_stats,
)
