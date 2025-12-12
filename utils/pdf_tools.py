import io
import os
import re
import json
import time
from typing import Tuple, BinaryIO
from PIL import Image
from pdf2docx import Converter
from pypdf import PdfReader, PdfWriter
import fitz  # PyMuPDF
import aiofiles

# 防止长图像素过大导致 PIL 报错
Image.MAX_IMAGE_PIXELS = None

OUTPUT_DIR = "output"
TMP_DIR = os.path.join(OUTPUT_DIR, "tmp")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

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
    try:
        with open(meta_path, "r") as f:
            meta = json.load(f)
        meta["downloaded"] = True
        meta["download_ts"] = int(time.time())
        with open(meta_path, "w") as f:
            json.dump(meta, f)
    except (json.JSONDecodeError, FileNotFoundError):
        pass 

def resolve_save_path(out_name: str, save_path: str = None) -> Tuple[str, bool]:
    if save_path:
        os.makedirs(save_path, exist_ok=True)
        return os.path.join(save_path, out_name), False
    else:
        path = os.path.join(TMP_DIR, out_name)
        return path, True

async def handle_output(buffer: BinaryIO, out_name: str, save_path: str = None):
    final_path, is_temp = resolve_save_path(out_name, save_path)
    
    buffer.seek(0)
    async with aiofiles.open(final_path, "wb") as fp:
        await fp.write(buffer.getvalue())
    
    if is_temp:
        write_meta(final_path + ".meta")
        
    buffer.seek(0)
    return buffer, final_path, out_name, is_temp

# --- 现有功能 ---

async def image_to_pdf(image_file, save_path: str = None):
    image = Image.open(image_file.file).convert("RGB")
    out_name = safe_filename(os.path.splitext(image_file.filename)[0] + ".pdf")
    buffer = io.BytesIO()
    image.save(buffer, "PDF")
    return await handle_output(buffer, out_name, save_path)

async def pdf_to_word(pdf_file, save_path: str = None):
    temp_input_filename = f"temp_in_{int(time.time())}_{safe_filename(pdf_file.filename)}"
    temp_input_path = os.path.join(TMP_DIR, temp_input_filename)
    
    content = await pdf_file.read()
    async with aiofiles.open(temp_input_path, "wb") as f:
        await f.write(content)

    out_name = safe_filename(os.path.splitext(pdf_file.filename)[0] + ".docx")
    final_path, _ = resolve_save_path(out_name, save_path)

    try:
        cv = Converter(temp_input_path)
        cv.convert(final_path, start=0, end=None)
        cv.close()
    finally:
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
    
    buffer = io.BytesIO()
    async with aiofiles.open(final_path, "rb") as f:
        buffer.write(await f.read())

    is_temp = save_path is None
    if is_temp:
        write_meta(final_path + ".meta")
        
    buffer.seek(0)
    return buffer, final_path, out_name, is_temp

async def merge_pdfs(files, save_path: str = None):
    writer = PdfWriter()
    for f in files:
        data = await f.read()
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
            
    out_name = safe_filename(f"merged_{int(time.time())}.pdf")
    buffer = io.BytesIO()
    writer.write(buffer)
    return await handle_output(buffer, out_name, save_path)

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
        
    base = safe_filename(os.path.splitext(file.filename)[0])
    out_name = safe_filename(f"{base}_pages_{start_page}-{end_page}.pdf")
    buffer = io.BytesIO()
    writer.write(buffer)
    return await handle_output(buffer, out_name, save_path)

# --- 修复后的 PDF 转长图功能 ---

async def pdf_to_long_image(file, save_path: str = None):
    """PDF 转长图 (仅生成一张图片)"""
    # 1. 保存临时输入文件 (PyMuPDF 需要本地路径以确保稳定)
    temp_input_filename = f"temp_img_in_{int(time.time())}_{safe_filename(file.filename)}"
    temp_input_path = os.path.join(TMP_DIR, temp_input_filename)
    
    content = await file.read()
    async with aiofiles.open(temp_input_path, "wb") as f:
        await f.write(content)

    base_name = safe_filename(os.path.splitext(file.filename)[0])
    out_name = f"{base_name}_long.png"
    buffer = io.BytesIO()
    
    try:
        doc = fitz.open(temp_input_path)
        # 放大系数，2 表示 200% 分辨率，清晰度更好
        # 如果 PDF 页数特别多，可以适当降低这个值，例如 fitz.Matrix(1.5, 1.5)
        mat = fitz.Matrix(2, 2) 

        images = []
        total_height = 0
        max_width = 0

        # 渲染所有页面
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            # 将 pixmap 转换为 PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
            total_height += img.height
            if img.width > max_width:
                max_width = img.width

        # 创建长图背景
        long_image = Image.new("RGB", (max_width, total_height), (255, 255, 255))
        
        # 拼接图片
        y_offset = 0
        for img in images:
            # 居中放置
            x_offset = (max_width - img.width) // 2
            long_image.paste(img, (x_offset, y_offset))
            y_offset += img.height

        # 保存到内存
        long_image.save(buffer, format="PNG")
        doc.close()

    finally:
        # 清理临时文件
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)

    return await handle_output(buffer, out_name, save_path)
