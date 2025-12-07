import io
import os
from pypdf import PdfReader, PdfWriter
import re
import json
import time

OUTPUT_DIR = "output"
TMP_DIR = os.path.join(OUTPUT_DIR, "tmp")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)  # 临时文件目录


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def write_meta(meta_path: str, downloaded: bool = False):
    meta = {
        "downloaded": downloaded,
        "created_ts": int(time.time()),
        "download_ts": None
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f)


def mark_downloaded(meta_path: str):
    if not os.path.exists(meta_path):
        return
    with open(meta_path, "r") as f:
        meta = json.load(f)
    meta["downloaded"] = True
    meta["download_ts"] = int(time.time())
    with open(meta_path, "w") as f:
        json.dump(meta, f)


def resolve_save_path(out_name: str, save_path: str = None):
    """返回最终文件路径 + 是否为临时文件"""
    if save_path:
        os.makedirs(save_path, exist_ok=True)
        return os.path.join(save_path, out_name), False
    else:
        # 临时文件
        path = os.path.join(TMP_DIR, out_name)
        return path, True


async def merge_pdfs(files, save_path: str = None):
    writer = PdfWriter()

    for f in files:
        data = await f.read()
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)

    out_name = safe_filename("merged_output.pdf")
    final_path, is_temp = resolve_save_path(out_name, save_path)

    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    with open(final_path, "wb") as fp:
        fp.write(buffer.getvalue())

    # 写入 meta
    if is_temp:
        write_meta(final_path + ".meta")

    return buffer, final_path, out_name, is_temp


async def split_pdf_range(file, start_page, end_page, save_path: str = None):
    data = await file.read()
    reader = PdfReader(io.BytesIO(data))
    num_pages = len(reader.pages)

    if end_page is None or end_page > num_pages:
        end_page = num_pages
    if start_page < 1 or start_page > end_page:
        raise ValueError("页码不合法")

    writer = PdfWriter()
    for i in range(start_page - 1, end_page):
        writer.add_page(reader.pages[i])

    base = safe_filename(file.filename.rsplit(".", 1)[0])
    out_name = safe_filename(f"{base}_{start_page}-{end_page}.pdf")

    final_path, is_temp = resolve_save_path(out_name, save_path)

    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    with open(final_path, "wb") as fp:
        fp.write(buffer.getvalue())

    if is_temp:
        write_meta(final_path + ".meta")

    return buffer, final_path, out_name, is_temp
