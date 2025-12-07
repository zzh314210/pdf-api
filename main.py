from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from utils.pdf_tools import (
    merge_pdfs,
    split_pdf_range,
    TMP_DIR,
    mark_downloaded,
)
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
import time

app = FastAPI(
    title="PDF Tools API",
    description="PDF Split & Merge with Auto Cleanup",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------
# 自动清理任务
# -----------------------

def cleanup_tmp_files():
    now = time.time()
    for filename in os.listdir(TMP_DIR):
        if not filename.endswith(".meta"):
            continue

        meta_path = os.path.join(TMP_DIR, filename)
        pdf_path = meta_path.replace(".meta", "")

        with open(meta_path, "r") as f:
            meta = json.load(f)

        created = meta["created_ts"]
        downloaded = meta["downloaded"]
        download_ts = meta["download_ts"]

        # 未下载 → 保存 3 天
        if not downloaded and now - created > 3 * 86400:
            try:
                os.remove(pdf_path)
                os.remove(meta_path)
                print(f"[Cleanup] 未下载 3 天 → 删除: {pdf_path}")
            except:
                pass

        # 已下载 → 24 小时后删除
        if downloaded and download_ts and now - download_ts > 86400:
            try:
                os.remove(pdf_path)
                os.remove(meta_path)
                print(f"[Cleanup] 下载超过24小时 → 删除: {pdf_path}")
            except:
                pass


scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_tmp_files, "interval", hours=12)
scheduler.start()


@app.get("/")
def root():
    return {"status": "running"}


# -----------------------
# 合并 PDF
# -----------------------

@app.post("/pdf/merge")
async def pdf_merge(
    files: list[UploadFile] = File(...),
    save_path: str = Form(None)
):
    buffer, final_path, out_name, is_temp = await merge_pdfs(files, save_path)

    async def iterator():
        yield buffer.getvalue()
        if is_temp:
            mark_downloaded(final_path + ".meta")

    return StreamingResponse(
        iterator(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename=\"{out_name}\"',
            "X-Saved-Path": final_path
        }
    )


# -----------------------
# 分割 PDF
# -----------------------

@app.post("/pdf/split")
async def pdf_split(
    file: UploadFile = File(...),
    start_page: int = Form(1),
    end_page: int = Form(None),
    save_path: str = Form(None)
):
    buffer, final_path, out_name, is_temp = await split_pdf_range(
        file, start_page, end_page, save_path
    )

    async def iterator():
        yield buffer.getvalue()
        if is_temp:
            mark_downloaded(final_path + ".meta")

    return StreamingResponse(
        iterator(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename=\"{out_name}\"',
            "X-Saved-Path": final_path
        }
    )
