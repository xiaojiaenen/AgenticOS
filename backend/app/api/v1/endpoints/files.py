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

# 明文魔数 → 类型说明。用于判定客户端上传的内容是否被透明加密驱动替换成密文。
_PLAIN_MAGIC: dict[bytes, str] = {
    b"PK\x03\x04": "OOXML/zip 明文（xlsx/docx/pptx）",
    b"\xd0\xcf\x11\xe0": "OLE2 明文（xls/doc/ppt）",
    b"%PDF": "PDF 明文",
    b"PK\x05\x06": "zip 空归档",
}


def _classify_bytes(content: bytes) -> tuple[str, str]:
    """判定上传内容是否为明文。返回 (kind, detail)，kind ∈ {plain, cipher, empty}。

    透明加密环境下，若上传链路正常，浏览器读到的是明文，服务端收到的也应是明文；
    若收到未知魔数，说明客户端读到的是密文（浏览器不在白名单），或链路被二次加密。
    """
    if not content:
        return "empty", "空文件"
    head = content[:16]
    for magic, desc in _PLAIN_MAGIC.items():
        if head.startswith(magic):
            return "plain", desc
    return "cipher", "未知魔数：" + " ".join(f"{b:02X}" for b in head[:8])



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


@router.post("/probe", summary="诊断：判定上传内容是否已被客户端透明加密")
async def probe_upload(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    """不落盘，只回显文件头判定结果。

    用途：确认「浏览器读明文 → HTTP 传明文 → Linux 服务端收明文」这条链路是否成立。
    在前端上传前调用一次即可，不需要每个文件都调。

    返回：
      kind   —— plain / cipher / empty
      detail —— 类型说明或未知魔数
      head   —— 前 16 字节的 hex，便于人工核对
    """
    content = await file.read()
    kind, detail = _classify_bytes(content)
    return {
        "filename": file.filename,
        "size": len(content),
        "kind": kind,
        "detail": detail,
        "head": " ".join(f"{b:02X}" for b in content[:16]),
        "advice": (
            "链路正常，服务端已拿到明文原始字节，可直接用 openpyxl/python-docx 等处理。"
            if kind == "plain"
            else "收到密文：浏览器不在白名单，或上传链路被 DLP 二次加密。"
            if kind == "cipher"
            else "文件为空。"
        ),
    }
