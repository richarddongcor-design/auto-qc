"""配置页面路由 — LLM 配置 + 规则集管理。"""
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from auto_qc.web.templates import templates
from auto_qc.core.config import load_env_config, save_env_config, mask_api_key

router = APIRouter()

RULES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "rules"


@router.get("/", response_class=HTMLResponse)
async def config_page(request: Request):
    cfg = load_env_config()
    cfg["LLM_API_KEY"] = mask_api_key(cfg["LLM_API_KEY"])
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "request": request,
            "active_tab": "config",
            "config": cfg,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/save-llm")
async def save_llm_config(request: Request):
    form = await request.form()
    api_key = form.get("api_key", "")
    # 如果提交的是掩码后的 key（以 **** 开头），保留现有值不覆盖
    if api_key.startswith("****"):
        existing = load_env_config()
        api_key = existing.get("LLM_API_KEY", api_key)
    save_env_config(
        base_url=form.get("base_url", ""),
        api_key=api_key,
        model=form.get("model", ""),
    )
    return RedirectResponse(url="/config?saved=1", status_code=303)


# ─── 规则集管理 ────────────────────────────────────────────


@router.get("/rule-sets", response_class=HTMLResponse)
async def list_rule_sets(request: Request):
    """列出所有规则集。"""
    if not RULES_DIR.exists():
        return HTMLResponse("<div class='text-sm text-gray-400 py-4 text-center'>规则目录不存在</div>")

    rule_sets = []
    for f in sorted(RULES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            rule_sets.append({
                "name": data.get("name", f.stem),
                "display_name": data.get("display_name", f.stem),
                "description": data.get("description", ""),
                "rule_count": len(data.get("rules", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue

    return templates.TemplateResponse(
        request,
        "partials/rules_sets.html",
        {"request": request, "rule_sets": rule_sets},
    )


@router.get("/rule-sets/{name}", response_class=HTMLResponse)
async def view_rule_set(request: Request, name: str):
    """查看并编辑指定规则集。"""
    file_path = RULES_DIR / f"{name}.json"
    if not file_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>规则集不存在</div>")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return HTMLResponse(f"<div class='text-sm text-red-500'>解析失败: {e}</div>")

    return templates.TemplateResponse(
        request,
        "partials/rules_editor.html",
        {"request": request, "name": name, "data": data},
    )


@router.post("/rule-sets/{name}/save")
async def save_rule_set(
    name: str,
    display_name: str = Form(...),
    description: str = Form(...),
    rules_json: str = Form(...),
):
    """保存规则集。"""
    file_path = RULES_DIR / f"{name}.json"
    try:
        rules = json.loads(rules_json)
    except json.JSONDecodeError as e:
        return HTMLResponse(f"<div class='text-sm text-red-500'>规则 JSON 解析失败: {e}</div>")

    data = {
        "name": name,
        "display_name": display_name,
        "description": description,
        "rules": rules,
    }
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return HTMLResponse("<div class='text-sm text-emerald-600 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg'>✅ 规则集已保存</div>")


@router.post("/rule-sets/create")
async def create_rule_set(
    name: str = Form(...),
    display_name: str = Form(...),
    description: str = Form(default=""),
):
    """创建新的规则集。"""
    # 文件已存在则报错（前端应该已做校验，但后端也检查）
    file_path = RULES_DIR / f"{name}.json"
    if file_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>规则集已存在</div>")

    data = {
        "name": name,
        "display_name": display_name,
        "description": description,
        "rules": [
            {
                "rule_id": "R01",
                "name": "示例规则",
                "description": "请编辑规则描述",
                "detection_logic": "请编辑检测逻辑",
            }
        ],
    }
    file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return HTMLResponse("<div class='text-sm text-emerald-600 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg'>✅ 规则集已创建</div>")


@router.post("/rule-sets/{name}/delete")
async def delete_rule_set(name: str):
    """删除规则集。"""
    file_path = RULES_DIR / f"{name}.json"
    if not file_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>规则集不存在</div>")
    file_path.unlink()
    return HTMLResponse("")


@router.post("/rule-sets/{name}/copy")
async def copy_rule_set(name: str, target: str = Form(...)):
    """复制规则集。"""
    src_path = RULES_DIR / f"{name}.json"
    dst_path = RULES_DIR / f"{target}.json"
    if not src_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>源规则集不存在</div>")
    if dst_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>目标名称已存在</div>")
    shutil.copy2(str(src_path), str(dst_path))
    return HTMLResponse("<div class='text-sm text-emerald-600 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg'>✅ 已复制</div>")


@router.get("/rule-sets/{name}/export")
async def export_rule_set(name: str):
    """导出规则集为 JSON 文件。"""
    file_path = RULES_DIR / f"{name}.json"
    if not file_path.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>规则集不存在</div>")
    return FileResponse(
        str(file_path),
        filename=f"{name}.json",
        media_type="application/json",
    )
