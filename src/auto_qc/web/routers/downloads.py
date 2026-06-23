"""历史下载页面路由 — 统一展示 QC + PI 历史记录。"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, Response

from auto_qc.web.templates import templates
from auto_qc.web.routers.history import get_runs

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def history_page(request: Request):
    """历史下载总页面。"""
    return templates.TemplateResponse(
        request,
        "history.html",
        {"request": request, "active_tab": "history"},
    )


@router.get("/list", response_class=HTMLResponse)
async def history_list(request: Request, type: str = "all"):
    """返回按类型筛选的历史列表 HTML 片段。"""
    runs = get_runs(run_type=type, limit=50)
    return templates.TemplateResponse(
        request,
        "partials/history_list.html",
        {"request": request, "runs": runs, "type": type},
    )


@router.get("/download/{task_id}")
async def history_download(task_id: str, type: str = "qc"):
    """下载指定运行的结果文件。"""
    save_dir = Path("output") / task_id
    if not save_dir.exists():
        return HTMLResponse("<div class='text-sm text-red-500'>文件不存在</div>")

    if type == "qc":
        report_path = save_dir / "report.xlsx"
        if report_path.exists():
            return FileResponse(
                str(report_path),
                filename="report.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return HTMLResponse("<div class='text-sm text-red-500'>质检报告不存在</div>")

    # PI: 找报告文件
    subdirs = sorted([d for d in save_dir.iterdir() if d.is_dir() and d.name[:4].isdigit()], reverse=True)
    for sd in subdirs:
        for fname in ["rules_summary.md", "rules.md", "report.md"]:
            fp = sd / fname
            if fp.exists():
                return FileResponse(str(fp), filename=fname, media_type="text/markdown")

    # 兜底：整个目录打包
    import tarfile, io
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(str(save_dir), arcname=task_id)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename={task_id}.tar.gz"},
    )


@router.post("/delete/{task_id}")
async def history_delete(task_id: str):
    """删除历史记录。"""
    save_dir = Path("output") / task_id
    if save_dir.exists():
        shutil.rmtree(save_dir)
    return HTMLResponse("")
