import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from utils.pdf_tools import (
    merge_pdfs,
    split_pdf_range,
    image_to_pdf,
    pdf_to_word,
    pdf_to_long_image, # 引入新的长图函数
    mark_downloaded,
)

app = FastAPI(
    title="PDF Tools API",
    description="PDF Split, Merge, Convert",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "running"}

def create_streaming_response(buffer, final_path, out_name, is_temp, media_type):
    async def iterator():
        yield buffer.getvalue()
        if is_temp:
            mark_downloaded(final_path + ".meta")
            
    return StreamingResponse(
        iterator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{out_name}"',
            "X-Saved-Path": final_path
        }
    )

# ... (原有的 pdf_merge, pdf_split, image_to_pdf, pdf_to_word 接口) ...

@app.post("/pdf/merge")
async def pdf_merge(files: list[UploadFile] = File(...), save_path: str = Form(None)):
    buffer, final_path, out_name, is_temp = await merge_pdfs(files, save_path)
    return create_streaming_response(buffer, final_path, out_name, is_temp, "application/pdf")

@app.post("/pdf/split")
async def pdf_split(file: UploadFile = File(...), start_page: int = Form(1), end_page: int = Form(None), save_path: str = Form(None)):
    buffer, final_path, out_name, is_temp = await split_pdf_range(file, start_page, end_page, save_path)
    return create_streaming_response(buffer, final_path, out_name, is_temp, "application/pdf")

@app.post("/image/to_pdf")
async def image_to_pdf_endpoint(file: UploadFile = File(...), save_path: str = Form(None)):
    buffer, final_path, out_name, is_temp = await image_to_pdf(file, save_path)
    return create_streaming_response(buffer, final_path, out_name, is_temp, "application/pdf")

@app.post("/pdf/to_word")
async def pdf_to_word_endpoint(file: UploadFile = File(...), save_path: str = Form(None)):
    buffer, final_path, out_name, is_temp = await pdf_to_word(file, save_path)
    return create_streaming_response(buffer, final_path, out_name, is_temp, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# --- 修改后的接口 ---

@app.post("/pdf/to_image")
async def pdf_to_image_endpoint(
    file: UploadFile = File(...), 
    save_path: str = Form(None)
):
    # 直接调用生成长图的函数，不需要 mode 参数了
    buffer, final_path, out_name, is_temp = await pdf_to_long_image(file, save_path)
    return create_streaming_response(buffer, final_path, out_name, is_temp, "image/png")
