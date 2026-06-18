"""全局配置管理 — LLM 配置读写。"""
import os
import re
from pathlib import Path


def _find_env_path() -> Path:
    """从项目根目录查找 .env 文件。"""
    return Path(__file__).resolve().parent.parent.parent.parent / ".env"


def load_env_config() -> dict:
    """读取当前 .env 配置并设置到进程环境变量。"""
    env_path = _find_env_path()
    config = {
        "LLM_BASE_URL": "https://api.deepseek.com",
        "LLM_API_KEY": "",
        "LLM_MODEL": "deepseek-chat",
    }
    if not env_path.exists():
        return config
    content = env_path.read_text(encoding="utf-8")
    for key in config:
        m = re.search(rf"^{re.escape(key)}=(.+)$", content, re.MULTILINE)
        if m:
            config[key] = m.group(1).strip()
    # 设置到进程环境变量，供 LLM 客户端读取
    for key, val in config.items():
        os.environ[key] = val
    return config


def mask_api_key(key: str) -> str:
    """掩码 API Key，仅显示末 4 位。"""
    if len(key) <= 8:
        return "****"
    return "****" + key[-4:]


def save_env_config(base_url: str, api_key: str, model: str) -> None:
    """保存 LLM 配置到 .env 文件。"""
    env_path = _find_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    keys = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"]
    values = [base_url, api_key, model]

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
    else:
        content = "# auto-qc API 配置\n"

    for key, val in zip(keys, values):
        if re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
            content = re.sub(
                rf"^{re.escape(key)}=.*$",
                f"{key}={val}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content += f"{key}={val}\n"

    env_path.write_text(content, encoding="utf-8")

    # 立即更新当前进程环境变量
    os.environ["LLM_BASE_URL"] = base_url
    os.environ["LLM_API_KEY"] = api_key
    os.environ["LLM_MODEL"] = model
