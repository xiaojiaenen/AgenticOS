import mimetypes
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from markitdown import MarkItDown

from app.api.deps import get_current_user
from app.db.models import UserModel

router = APIRouter(prefix="/files", tags=["文件"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TEXT_LENGTH = 50 * 1024  # 50KB 注入上下文


def extract_text(filename: str, content: bytes) -> str:
    try:
        converter = MarkItDown()
        result = converter.convert(BytesIO(content))
        return result.text_content
    except Exception as exc:
        raise ValueError(f"文件转换失败 ({filename}): {exc}") from exc


@router.post("/upload", summary="上传文件并提取文本内容")
async def upload_file(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空。")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10MB。")

    try:
        text = extract_text(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    truncated = text[:MAX_TEXT_LENGTH]
    return {
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
        "text_content": truncated,
        "text_truncated": len(text) > MAX_TEXT_LENGTH,
        "text_length": len(text),
    }
