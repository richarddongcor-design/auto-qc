"""工具路由 — 模板下载 + 数据上传转换。"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.responses import RedirectResponse

from auto_qc.web.templates import templates
from auto_qc.core.data_converter import generate_template, convert_xlsx

router = APIRouter()


@router.get("/template/download")
async def download_template():
    """下载对话数据模板 xlsx。"""
    tmp = Path(tempfile.mkdtemp()) / "对话数据模板.xlsx"
    path = generate_template(tmp)
    return FileResponse(
        str(path),
        filename="对话数据模板.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/data/convert")
async def upload_and_convert(file: UploadFile):
    """上传已填写的 xlsx，返回转换后的 JSON。"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        return HTMLResponse("<div class='text-sm text-red-500'>请上传 .xlsx 文件</div>")

    tmp = Path(tempfile.mkdtemp()) / file.filename
    content = await file.read()
    tmp.write_bytes(content)

    try:
        data = convert_xlsx(str(tmp))
    except ValueError as e:
        return HTMLResponse(f"<div class='text-sm text-red-500'>{e}</div>")
    finally:
        tmp.unlink(missing_ok=True)

    if not data:
        return HTMLResponse("<div class='text-sm text-red-500'>未读取到数据</div>")

    import json
    json_str = json.dumps(data, ensure_ascii=False, indent=2)

    # 返回 HTML 片段，同时嵌入 JSON 数据供复制
    total = len(data)
    json_escaped = json_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(f"""
<div class="space-y-4">
  <div class="flex items-center gap-3 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg">
    <span class="text-sm text-emerald-700">✅ 转换完成：{total} 条对话</span>
    <button onclick="navigator.clipboard.writeText(document.getElementById('json-output').textContent)"
            class="ml-auto px-3 py-1 text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-100 rounded-lg transition-all cursor-pointer bg-transparent border border-emerald-200">
      复制 JSON
    </button>
  </div>
  <pre id="json-output" class="bg-gray-50 border border-gray-200 rounded-lg p-4 text-xs font-mono leading-relaxed max-h-96 overflow-auto whitespace-pre-wrap">{json_escaped}</pre>
</div>""")


@router.post("/data/upload-for-qc")
async def upload_for_qc(file: UploadFile, request: Request):
    """上传转换后供 QC 管线使用。"""
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        return HTMLResponse("<div class='text-sm text-red-500'>请上传 .xlsx 文件</div>")

    tmp = Path(tempfile.mkdtemp()) / file.filename
    content = await file.read()
    tmp.write_bytes(content)

    try:
        data = convert_xlsx(str(tmp))
    except ValueError as e:
        return HTMLResponse(f"<div class='text-sm text-red-500'>{e}</div>")
    finally:
        tmp.unlink(missing_ok=True)

    if not data:
        return HTMLResponse("<div class='text-sm text-red-500'>未读取到数据</div>")

    # 保存为 JSON 供后续处理
    import uuid, json
    from pathlib import Path as P

    task_id = str(uuid.uuid4())[:8]
    save_dir = P("output") / task_id
    save_dir.mkdir(parents=True, exist_ok=True)
    json_path = save_dir / "converted.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return templates.TemplateResponse(
        request,
        "partials/convert_result.html",
        {"request": request, "task_id": task_id, "total": len(data)},
    )
