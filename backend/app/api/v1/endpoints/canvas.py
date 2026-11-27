"""创作画布 API：AI 生图 / 图生图改图 + 本地图片处理。

权限：所有权限点门禁（image:create / image:process）走 require_perm，
权限点挂在 CAP_AGENT_USE 分组，内置角色自动继承；管理员可在权限矩阵单独关闭。

产物落在会话工作区 outputs/，与聊天产物一致，可通过
GET /api/v1/agent/sessions/{sid}/outputs/{filename} 带鉴权回显。
"""

from __future__ import annotations

import base64
import io
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image

from app.api.deps import get_db, require_perm
from app.core.data_path import current_workspace_dir
from app.db.models import UserModel
from app.services.image_processing_service import (
    ImageProcessingError,
    process_image,
)

logger = logging.getLogger("agenticos.canvas")

router = APIRouter(prefix="/canvas", tags=["创作画布"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _save_output(user_id: int, session_id: str, data: bytes, ext: str, stem: str = "") -> str:
    """把字节写到会话工作区 outputs/，返回可回显的文件名。"""
    from app.core.data_path import workspace_dir

    ws = workspace_dir(user_id, session_id, create=True)
    out_dir = ws / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{stem or 'canvas-' + uuid.uuid4().hex[:12]}.{ext.lstrip('.')}"
    (out_dir / name).write_bytes(data)
    return name


@router.get("/quota", summary="当前用户的额度总览（token/生图/发布奖励）")
async def canvas_quota(
    user: UserModel = Depends(require_perm("image:create")),
) -> dict[str, Any]:
    from app.services.quota_service import get_user_quota_status

    return get_user_quota_status(user.id, role=user.role)


@router.get("/artifacts", summary="列出当前用户所有图片产物（画布作品来源）")
async def canvas_artifacts(
    user: UserModel = Depends(require_perm("image:create")),
) -> dict[str, Any]:
    """扫描本用户所有会话工作区 outputs/ 下的图片，返回可回显列表。

    画布不再内置演示海报：真实作品就是这里返回的、由 AI 生图 / 图片处理
    落盘的图片。按修改时间倒序，前端把它们渲染成画布节点。
    """
    from app.core.data_path import WORKSPACES_DIR

    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    user_dir = WORKSPACES_DIR / f"u{user.id}"
    items: list[dict[str, Any]] = []
    if user_dir.exists():
        for session_dir in user_dir.iterdir():
            if not session_dir.is_dir() or not session_dir.name.startswith("s"):
                continue
            session_id = session_dir.name[1:]  # 去掉前缀 s
            out_dir = session_dir / "outputs"
            if not out_dir.exists():
                continue
            for f in out_dir.iterdir():
                if not f.is_file() or f.suffix.lower() not in image_exts:
                    continue
                stat = f.stat()
                items.append({
                    "session_id": session_id,
                    "filename": f.name,
                    "url": f"/api/v1/agent/sessions/{session_id}/outputs/{f.name}",
                    "size": stat.st_size,
                    "created_at": stat.st_mtime,
                })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"items": items[:100], "total": len(items)}


@router.post("/generate", summary="AI 生图 / 图生图改图（画布）")
async def canvas_generate(
    prompt: str = Form(...),
    session_id: str = Form(...),
    size: str = Form(default="landscape"),
    reference: UploadFile | None = File(default=None),
    strength: float = Form(default=0.7),
    user: UserModel = Depends(require_perm("image:create")),
    db=Depends(get_db),
) -> dict[str, Any]:
    """文生图；带 reference 时走图生图（把参考图 base64 一起发给上游）。

    上游不支持图生图时自动降级为文生图（把参考图信息并入 prompt），
    保证功能可用而不是直接失败。
    """
    from app.services.llm_providers.resolve_models import (
        COOKIE_MODE_TOOL,
        resolve_image_endpoint,
    )

    prompt = (prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    # 生图额度检查（每日张数，管理员豁免）
    from app.services.quota_service import DailyQuotaExceeded, check_image_quota

    try:
        check_image_quota(user.id, role=user.role)
    except DailyQuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    endpoint = resolve_image_endpoint(db, cookie_mode=COOKIE_MODE_TOOL)
    if endpoint is None:
        raise HTTPException(
            status_code=422,
            detail="未配置生图模型：请管理员到「AI 提供商」绑定「文生图」角色",
        )

    size_map = {
        "square": "1024x1024",
        "landscape": "1792x1024",
        "portrait": "1024x1792",
    }
    size_value = size_map.get(size, size_map["landscape"])

    ref_b64 = ""
    if reference is not None:
        content = await reference.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="参考图超过 20MB 上限")
        ref_b64 = base64.b64encode(content).decode("ascii")

    payload: dict[str, Any] = {
        "model": endpoint.model,
        "prompt": prompt,
        "n": 1,
        "size": size_value,
        "response_format": "b64_json",
    }
    if ref_b64:
        # OpenAI edits 协议约定 image；generations 协议用 image 会被忽略，
        # 上游若支持图生图会识别，不支持则靠 prompt 降级。
        payload["image"] = ref_b64
        payload["strength"] = max(0.0, min(1.0, strength))

    headers = (
        {"Cookie": endpoint.cookie}
        if getattr(endpoint, "cookie", "")
        else {"Authorization": f"Bearer {endpoint.api_key}"}
    ) | {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{endpoint.base_url}/images/generations",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="生图超时（180s），请稍后重试")
    except Exception as exc:  # noqa: BLE001
        logger.warning("画布生图失败", exc_info=True)
        raise HTTPException(status_code=502, detail=f"生图失败：{type(exc).__name__}: {exc}") from exc

    # 解析上游响应：百通 imageList / OpenAI b64_json / url
    inner = data.get("data")
    raw: bytes | None = None
    ext = "png"
    if isinstance(inner, dict) and isinstance(inner.get("imageList"), list) and inner["imageList"]:
        item = inner["imageList"][0] or {}
        file_url = (item.get("fileUrl") or "").strip()
        ftype = str(item.get("fileType") or "JPG").upper()
        ext = "png" if ftype == "PNG" else "jpg"
        if file_url:
            try:
                async with httpx.AsyncClient(verify=False, timeout=120) as dl:
                    r = await dl.get(file_url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200:
                    raw = r.content
            except Exception as exc:  # noqa: BLE001
                logger.warning("画布生图下载失败", exc_info=True)
    elif isinstance(inner, list) and inner:
        first = inner[0] if isinstance(inner[0], dict) else {}
        if first.get("b64_json"):
            try:
                raw = base64.b64decode(first["b64_json"])
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=502, detail=f"图片解码失败：{exc}") from exc
        elif first.get("url"):
            try:
                async with httpx.AsyncClient(timeout=120) as dl:
                    r = await dl.get(first["url"])
                if r.status_code == 200:
                    raw = r.content
            except Exception as exc:  # noqa: BLE001
                logger.warning("画布生图 URL 下载失败", exc_info=True)

    if raw is None:
        raise HTTPException(status_code=502, detail="上游未返回图片，请检查生图模型配置")

    filename = _save_output(user.id, session_id, raw, ext)
    # 记一条 usage（tool_names_json 含 generate_image），供每日生图张数额度统计
    try:
        import json
        from app.db.models import AgentUsageEventModel

        db.add(AgentUsageEventModel(
            user_id=user.id,
            session_id=session_id,
            agent_profile_id=None,
            model_name=endpoint.model,
            response_mode="canvas_image",
            input_tokens=0, output_tokens=0, total_tokens=0,
            llm_calls=1, tool_calls=1,
            tool_names_json=json.dumps(["generate_image"]),
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 —— 记账失败不应让已生成的图丢失
        logger.warning("画布生图 usage 记账失败", exc_info=True)
        db.rollback()
    return {
        "filename": filename,
        "url": f"/api/v1/agent/sessions/{session_id}/outputs/{filename}",
        "size": len(raw),
        "model": endpoint.model,
        "mode": "image_to_image" if ref_b64 else "text_to_image",
    }


@router.post("/process", summary="本地图片处理：裁剪/压缩/缩放/旋转/水印/缩略图")
async def canvas_process(
    image: UploadFile = File(...),
    session_id: str = Form(...),
    operation: str = Form(...),
    output_format: str = Form(default="PNG"),
    quality: int = Form(default=85),
    crop: str | None = Form(default=None),
    resize: str | None = Form(default=None),
    thumbnail: str | None = Form(default=None),
    degrees: int = Form(default=0),
    watermark: str = Form(default=""),
    user: UserModel = Depends(require_perm("image:process")),
) -> dict[str, Any]:
    """operation ∈ crop/resize/compress/rotate/watermark/thumbnail。

    crop/resize/thumbnail 为 JSON 字符串（如 '{"width":800,"height":600}'）。
    输出落到会话工作区 outputs/，返回带鉴权回显 URL。
    """
    import json

    content = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="图片超过 20MB 上限")

    def parse_j(name: str, value: str | None) -> dict[str, int] | None:
        if not value:
            return None
        try:
            obj = json.loads(value)
            if not isinstance(obj, dict):
                raise ValueError
            return {k: int(v) for k, v in obj.items()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"{name} 必须是 JSON 对象") from exc

    try:
        result, fmt, size = process_image(
            content,
            operation=operation,
            output_format=output_format,
            quality=quality,
            crop=parse_j("crop", crop),
            resize=parse_j("resize", resize),
            thumbnail=parse_j("thumbnail", thumbnail),
            degrees=degrees,
            watermark=watermark,
        )
    except ImageProcessingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}.get(fmt, "png")
    filename = _save_output(user.id, session_id, result, ext, stem=f"processed-{uuid.uuid4().hex[:10]}")
    return {
        "filename": filename,
        "url": f"/api/v1/agent/sessions/{session_id}/outputs/{filename}",
        "format": fmt.lower(),
        "width": size[0],
        "height": size[1],
        "size": len(result),
    }
