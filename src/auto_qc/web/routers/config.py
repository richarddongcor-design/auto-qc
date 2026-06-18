"""配置页面路由。"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from auto_qc.web.templates import templates
from auto_qc.core.config import load_env_config, save_env_config, mask_api_key

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def config_page(request: Request):
    cfg = load_env_config()
    cfg["LLM_API_KEY"] = mask_api_key(cfg["LLM_API_KEY"])
    return templates.TemplateResponse(
        request,
        "config.html",
        {"request": request, "active_tab": "config", "config": cfg},
    )


@router.post("/save-llm")
async def save_llm_config(request: Request):
    form = await request.form()
    save_env_config(
        base_url=form.get("base_url", ""),
        api_key=form.get("api_key", ""),
        model=form.get("model", ""),
    )
    return RedirectResponse(url="/config", status_code=303)
