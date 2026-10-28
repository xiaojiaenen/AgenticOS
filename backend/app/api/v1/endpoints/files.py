import asyncio
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.data_path import uploads_dir
from app.db.models import UserModel

router = APIRouter(prefix="/files", tags=["文件"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_upload_dir(user_id: int, session_id: str | None) -> Path:
    """上传落点：会话工作区的 uploads/。

    为什么不放全局 ``data/uploads/<uid>/``：那样同一用户的**所有会话**共享
    一个目录，A 会话能看到 B 会话上传的文件，而且路径是
    ``/app/data/uploads/1/abc123_报告.docx`` —— 把容器内的绝对路径暴露给
    AI 和前端。

    现在落在 ``data/workspaces/u<uid>/s<sid>/uploads/``，AI 看到的是相对路径
    ``uploads/报告.docx``，与「只提供相对路径」的提示词一致。

    没带 session_id 时退回 ``data/uploads/<uid>/``（兼容旧前端调用）。
    """
    if session_id:
        return uploads_dir(user_id, session_id, create=True)
    from app.core.data_path import DATA_DIR

    legacy = DATA_DIR / "uploads" / str(user_id)
    legacy.mkdir(parents=True, exist_ok=True)
    return legacy


@router.post("/upload", summary="上传文件，保存到会话工作区并返回相对路径")
async def upload_file(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空。")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10MB。")

    upload_dir = _get_upload_dir(current_user.id, session_id)
    file_id = uuid.uuid4().hex[:12]
    safe_name = file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stored_name = f"{file_id}_{safe_name}"
    stored_path = upload_dir / stored_name
    await asyncio.to_thread(stored_path.write_bytes, content)

    # 同时给两种路径：
    #   file_path  —— 服务端绝对路径（兼容旧前端 / 旧提示词）
    #   rel_path   —— 相对工作区的路径，AI 直接可用
    rel_path = None
    if session_id:
        try:
            rel_path = str(stored_path.relative_to(upload_dir.parent))
        except ValueError:
            rel_path = None

    return {
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
        "file_path": str(stored_path),
        "rel_path": rel_path,
    }
