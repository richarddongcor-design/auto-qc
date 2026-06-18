"""问题挖掘页面路由。"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from auto_qc.web.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def pi_page(request: Request):
    return templates.TemplateResponse(
        request,
        "pi.html",
        {"request": request, "active_tab": "pi"},
    )
