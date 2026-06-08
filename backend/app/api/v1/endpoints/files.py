import mimetypes
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.core.data_path import DATA_DIR
from app.db.models import UserModel

router = APIRouter(prefix="/files", tags=["文件"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_upload_dir(user_id: int) -> Path:
    upload_dir = DATA_DIR / "uploads" / str(user_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@router.post("/upload", summary="上传文件，保存到服务端并返回文件路径")
async def upload_file(
    file: UploadFile = File(...),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空。")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 10MB。")

    upload_dir = _get_upload_dir(current_user.id)
    file_id = uuid.uuid4().hex[:12]
    safe_name = file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stored_name = f"{file_id}_{safe_name}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)

    return {
        "filename": file.filename,
        "size": len(content),
        "mime_type": file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
        "file_path": str(stored_path),
    }
